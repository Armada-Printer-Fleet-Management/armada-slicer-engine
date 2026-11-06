# The environment the engine is built in, locally and in CI. scripts/build.py builds and runs it.
# Every input is pinned: the base image by digest, Python packages by hash, and Debian packages are
# signature-checked by apt. Emscripten and Node arrive as Conan tool-requires fixed by conan.lock.

FROM python:3.13-slim-bookworm@sha256:281d39ff02e3b389401586134ff9e6572954687822a58055ec07a60ded4e0b7f

RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential cmake ninja-build patch git ca-certificates \
 && rm -rf /var/lib/apt/lists/*

COPY build/requirements.txt /tmp/requirements.txt
RUN grep -q '^conan==' /tmp/requirements.txt \
    || { echo "error: build/requirements.txt has not been generated; see AGENTS.md" >&2; exit 1; } \
 && pip install --no-cache-dir --require-hashes -r /tmp/requirements.txt \
 && rm /tmp/requirements.txt

RUN useradd --create-home --uid 1000 builder \
 && mkdir /conan /work \
 && chown builder:builder /conan /work

ENV CONAN_HOME=/conan \
    ARMADA_ENGINE_BUILDER=1
USER builder
WORKDIR /work