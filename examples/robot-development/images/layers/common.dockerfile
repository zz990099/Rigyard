# Rigyard supplies FROM ubuntu:24.04 from images/image.yaml.
ENV LANG=C.UTF-8 LC_ALL=C.UTF-8

RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        build-essential \
        ca-certificates \
        curl \
    && rm -rf /var/lib/apt/lists/*
