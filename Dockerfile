FROM python:3.12.11-slim-bookworm@sha256:519591d6871b7bc437060736b9f7456b8731f1499a57e22e6c285135ae657bf7 AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /build

COPY pyproject.toml README.md ./
COPY src ./src

RUN python -m pip wheel --wheel-dir /wheelhouse --no-deps .


FROM python:3.12.11-slim-bookworm@sha256:519591d6871b7bc437060736b9f7456b8731f1499a57e22e6c285135ae657bf7 AS runtime

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TMPDIR=/tmp

RUN groupadd --gid 10001 distsys \
    && useradd --uid 10001 --gid 10001 --no-create-home --shell /usr/sbin/nologin distsys \
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
