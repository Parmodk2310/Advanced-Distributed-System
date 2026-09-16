FROM python:3.12.14-alpine3.24@sha256:b64631e04e4920160c50fbe8d8df828f7f35f06f425cb44aa09bca53e708a35a AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

RUN apk upgrade --no-cache

WORKDIR /build

COPY pyproject.toml README.md ./
COPY src ./src

RUN python -m pip wheel \
    --wheel-dir /wheelhouse \
    --no-deps \
    .

FROM python:3.12.14-alpine3.24@sha256:b64631e04e4920160c50fbe8d8df828f7f35f06f425cb44aa09bca53e708a35a AS runtime

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TMPDIR=/tmp

RUN apk upgrade --no-cache \
    && addgroup -S -g 10001 distsys \
    && adduser -S -D -H \
       -u 10001 \
       -G distsys \
       distsys \
    && mkdir -p /data /tmp /wheelhouse \
    && chown -R 10001:10001 /data /tmp

COPY --from=builder /wheelhouse /wheelhouse

RUN python -m pip install /wheelhouse/*.whl \
    && rm -rf /wheelhouse

USER 10001:10001

WORKDIR /data

VOLUME ["/data"]

EXPOSE 8000 9100

ENTRYPOINT ["python", "-m", "distsys.main"]
