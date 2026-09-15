FROM python:3.12-slim@sha256:78387bc3881b8273120a12ebe6c1ab22b018ccc2c9adf565ae1ac9b536e184ea AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /build

COPY pyproject.toml README.md ./
COPY src ./src

RUN python -m pip wheel --wheel-dir /wheelhouse .

FROM python:3.12-slim@sha256:78387bc3881b8273120a12ebe6c1ab22b018ccc2c9adf565ae1ac9b536e184ea AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PERSISTENCE_DB_PATH=/data/node.db

RUN groupadd --gid 10001 distsys \
    && useradd --uid 10001 --gid 10001 --no-create-home --shell /usr/sbin/nologin distsys \
    && install -d -o 10001 -g 10001 /data /tmp/distsys

COPY --from=builder /wheelhouse/ /wheelhouse/

RUN python -m pip install --no-index --find-links=/wheelhouse advanced-distributed-system==0.6.0 \
    && rm -rf /wheelhouse

WORKDIR /app

USER 10001:10001

EXPOSE 8000 9100

ENTRYPOINT ["python", "-m", "distsys.main"]
