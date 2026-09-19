#!/bin/bash

set -e

cd $(dirname $0)

DOCKER=${DOCKER:-docker} # Set DOCKER=podman to use podman instead of docker

log=$(mktemp)

function on_exit() {
    echo 'Cleaning up...'
    rm -f $log
    $DOCKER stop aoh-test-server || true # ignore if already stopped
}
trap on_exit EXIT

$DOCKER build -t aoh-test-client -f client.Dockerfile .
$DOCKER build -t aoh-test-server ../../
$DOCKER network create aoh-test  || true # ignore if already created

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

echo ================================
echo All tests passed.
echo ================================
