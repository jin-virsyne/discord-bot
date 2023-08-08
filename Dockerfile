FROM python:3.10-slim

# Prevents OS buffering of logs to stdout.
ENV PYTHONUNBUFFERED 1

RUN adduser --uid 101 --system --group python --home /app

RUN apt-get update && \
    apt-get install -y \
    # Quality of life
    nano htop curl iputils-ping dnsutils \
    # Python dependencies
    build-essential

WORKDIR /app
RUN chown python.python /app

USER python

COPY . /app
RUN /app/bin/install-deps

ARG BUILD_TAG
ENV BUILD_TAG $BUILD_TAG

ENTRYPOINT [ "/app/bin/start" ]