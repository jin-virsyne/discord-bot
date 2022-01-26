FROM python:3.9-slim-bullseye

# Prevents OS buffering of logs to stdout.
ENV PYTHONUNBUFFERED 1

RUN adduser --uid 101 --system --group python

RUN apt-get update && \
    apt-get install -y \
    # Quality of life
    nano htop curl iputils-ping dnsutils \
    # Python dependencies
    build-essential

WORKDIR /app

COPY . /app
RUN /app/bin/install-deps
RUN chown -R python /app

ARG BUILD_TAG
ENV BUILD_TAG $BUILD_TAG

USER python