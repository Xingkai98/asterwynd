FROM python:3.12-slim

RUN apt-get update && apt-get install -y git && \
    rm -rf /var/lib/apt/lists/*

COPY dist/asterwynd-*.whl /tmp/
RUN pip install --no-cache-dir /tmp/asterwynd-*.whl
