FROM docker.io/ubuntu:26.04

RUN apt-get update && apt-get -y install curl python3 sudo

RUN echo 'hunter2' | passwd --stdin ubuntu

USER ubuntu
