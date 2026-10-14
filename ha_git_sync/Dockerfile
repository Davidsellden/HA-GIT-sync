# syntax=docker/dockerfile:1
FROM python:3.13-slim-bookworm
ARG BUILD_VERSION=dev
ARG BUILD_ARCH=amd64
LABEL io.hass.name="HA Git Sync" \
    io.hass.description="Review, back up and sync selected Home Assistant files with GitHub." \
    io.hass.version="${BUILD_VERSION}" \
    io.hass.type="app" \
    io.hass.arch="${BUILD_ARCH}"
RUN --mount=type=secret,id=proxy_ca \
    apt_safe() { if [ -f /run/secrets/proxy_ca ]; then apt-get -o Acquire::https::CaInfo=/run/secrets/proxy_ca "$@"; else apt-get "$@"; fi; }; \
    apt_safe update \
    && apt_safe install -y --no-install-recommends git openssh-client ca-certificates \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN --mount=type=secret,id=proxy_ca \
    if [ -f /run/secrets/proxy_ca ]; then export PIP_CERT=/run/secrets/proxy_ca; fi; \
    pip install --no-cache-dir -r requirements.txt
COPY app/ .
ENV PYTHONUNBUFFERED=1
CMD ["python", "server.py"]
