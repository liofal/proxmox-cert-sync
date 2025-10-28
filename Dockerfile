FROM python:3.14-alpine

ENV PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=UTF-8

RUN set -eux; \
    apk add --no-cache curl jq openssl ca-certificates; \
    addgroup -S app -g 65532; \
    adduser -S -D -H -u 65532 -G app app; \
    pip install --no-cache-dir requests cryptography

WORKDIR /app
COPY cmd/sync.py /app/sync.py

USER 65532:65532

ENTRYPOINT ["python", "/app/sync.py"]
