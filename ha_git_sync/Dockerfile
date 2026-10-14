# syntax=docker/dockerfile:1
FROM python:3.13-slim-bookworm
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
