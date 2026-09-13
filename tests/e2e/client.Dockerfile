FROM docker.io/ubuntu:26.04

RUN apt-get update && apt-get -y install curl python3 sudo

# Not used by e2e tests, but useful for testing during development:
RUN echo 'hunter2' | passwd --stdin ubuntu
