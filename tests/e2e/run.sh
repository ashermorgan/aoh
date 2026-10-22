#!/bin/bash

set -e

cd $(dirname $0)

DOCKER=${DOCKER:-docker} # Set DOCKER=podman to use podman instead of docker

log=$(mktemp)

function on_exit() {
    echo 'Cleaning up...'
    rm -f $log
    if [ $($DOCKER ps --filter name=aoh-test-client | wc -l) -gt 1 ]; then
        $DOCKER stop aoh-test-client
    fi
    if [ $($DOCKER ps --filter name=aoh-test-server | wc -l) -gt 1 ]; then
        $DOCKER stop aoh-test-server
    fi
}
trap on_exit EXIT

$DOCKER build -t aoh-test-client -f client.Dockerfile .
$DOCKER build -t aoh-test-server ../../
if [ $($DOCKER network ls --filter name=aoh-test | wc -l) -eq 1 ]; then
    $DOCKER network create aoh-test
fi

for i in {1..4}; do
    echo ================================
    echo Running test$i.yml...
    echo ================================

    echo > $log

    $DOCKER run --rm --network aoh-test --detach -h aoh-test-server \
        --name aoh-test-server -v ./:/aoh aoh-test-server
    sleep 1
    $DOCKER run --rm --network aoh-test --tty aoh-test-client bash -c \
        "curl http://aoh-test-server:8000/run | python3 - test$i.yml" \
        | tee $log
    $DOCKER stop aoh-test-server
    sleep 1

    if grep 'failed=0' < $log; then
        echo ================================
        echo test$i.yml passed.
        echo ================================
        echo
    else
        echo ================================
        echo test$i.yml failed.
        echo ================================
        exit 1
    fi
done

# Test 5 is different: start a long-running playbook, kill the client, and then
# check to make sure that server cleans everything up
i=5
echo ================================
echo Running test$i.yml...
echo ================================

$DOCKER run --rm --network aoh-test --detach -h aoh-test-server \
    --name aoh-test-server -v ./:/aoh \
    -e AOH_GC_INTERVAL=1 -e AOH_GC_THRESHOLD=1 aoh-test-server
sleep 1
$DOCKER run --rm --network aoh-test --detach --name aoh-test-client \
    aoh-test-client bash -c \
    "curl http://aoh-test-server:8000/run | python3 - test$i.yml"

for j in {1..10}; do
    if $DOCKER exec aoh-test-server sh -c \
        'find /tmp -maxdepth 1 -type d -name "aoh-*" -print -quit | grep -q .\
        && ps -eo comm | grep -qx ansible-playboo'
    then
        break
    elif [ "$j" -eq 10 ]; then
        echo Timed out waiting for server to start runner
        $DOCKER exec aoh-test-server sh -c \
            'find /tmp -maxdepth 1 -type d -name "aoh-*" -print -quit; \
            ps -eo comm'
        echo ================================
        echo test$i.yml failed.
        echo ================================
        exit 1
    else
        sleep 1
    fi
done

sleep 1
$DOCKER stop aoh-test-client

for j in {1..10}; do
    if $DOCKER exec aoh-test-server sh -c \
        '! find /tmp -maxdepth 1 -type d -name "aoh-*" -print -quit | grep -q .\
        && ! ps -eo comm | grep -qx ansible-playboo'
    then
        echo ================================
        echo test$i.yml passed.
        echo ================================
        break
    elif [ "$j" -eq 10 ]; then
        echo Timed out waiting for server to clean up runner
        $DOCKER exec aoh-test-server sh -c \
            'find /tmp -maxdepth 1 -type d -name "aoh-*" -print -quit; \
            ps -eo comm'
        echo ================================
        echo test$i.yml failed.
        echo ================================
        exit 1
    else
        sleep 1
    fi
done

$DOCKER stop aoh-test-server
sleep 1

echo ================================
echo All tests passed.
echo ================================
