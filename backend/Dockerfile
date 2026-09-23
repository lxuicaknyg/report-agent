# Built on a machine with internet access, then moved into the offline network
# with `docker save` / `docker load` — see DEPLOY.md. Nothing here reaches the
# network at run time except the LLM gateway and the databases users configure.

# 3.10 to match the environment this is developed and tested against. Bookworm
# rather than Alpine because several dependencies ship manylinux wheels only —
# on musl they would have to be compiled from source, which is exactly the kind
# of build that cannot be repaired inside an air-gapped network.
FROM python:3.10-slim-bookworm AS builder

WORKDIR /build
COPY requirements.txt .
# No compiler installed on purpose: every dependency here resolves to a
# manylinux wheel for cp310/x86_64 (psycopg is pinned to [binary] for exactly
# this reason), and the few sdists left are pure Python. If this step ever
# fails asking for gcc, a dependency changed — add build-essential back to this
# stage rather than to the runtime image below.
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt


FROM python:3.10-slim-bookworm

# libgomp1: pulled in by pandas/duckdb at import time.
# curl: the healthcheck below.
# openjdk-17-jre-headless: openLooKeng has no SQLAlchemy dialect and is reached
#   over JDBC, which means jpype has to dlopen a libjvm.so. Installed here, at
#   build time, while there is still a network — the target network is offline,
#   so anything not in the image cannot be added later. headless because this
#   process will never draw a window, and that variant is roughly half the size.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgomp1 \
        curl \
        openjdk-17-jre-headless \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /install /usr/local

# Never run as root: this process writes files that users uploaded and executes
# SQL they wrote.
RUN useradd --create-home --uid 10001 appuser

WORKDIR /app
COPY --chown=appuser:appuser app ./app

# Everything that must survive a restart lives under one directory, so the
# container needs exactly one volume. Created here so it is owned by appuser
# even when the volume is empty on first start.
ENV STATE_DIR=/var/lib/report-agent
RUN mkdir -p ${STATE_DIR} && chown -R appuser:appuser ${STATE_DIR}

# 0.0.0.0, not the 127.0.0.1 default: a container bound to loopback is
# unreachable from nginx, which is the only thing that talks to it.
ENV HOST=0.0.0.0 \
    PORT=8000 \
    ENVIRONMENT=production \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# jpype finds libjvm.so through JAVA_HOME, and nothing else in the image sets
# it. Pinned to the versioned Debian path rather than the `default-java` symlink
# so that a base-image upgrade that changes the default JDK breaks the build
# here, loudly, instead of breaking openLooKeng connections at run time.
#
# The driver jar is a separate matter: it is vendor-licensed and version-matched
# to the cluster, so it stays a mount rather than a layer. See deploy/jdbc/.
ENV JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64

USER appuser
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/health || exit 1

# One worker, deliberately. Report generation runs as an asyncio task inside
# this process and its progress lives in memory plus JSON files on the volume:
# a second worker would poll a session the first one is running (404s for the
# user) and race it writing those files. Scaling this service means fixing that
# first — do not "just add workers".
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
