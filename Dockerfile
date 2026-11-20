# OpenCut IMEJI: the whole lesson pipeline in one image (Linux x86_64).
#
#   docker build -t opencut-imeji .
#   docker run --rm -v "$PWD/lessons:/app/lessons" opencut-imeji \
#       python scripts/opencut_ptc.py lesson --script lessons/x/x.script.vi.txt --out lessons/x --render
#
# Stages:
#   ffmpeg   FFmpeg 8.1.3 from source (the version pinned in crates/media/setup/ffmpeg.json):
#            shared libraries for the Rust build AND the ffmpeg/ffprobe programs the pipeline calls,
#            so both come from one version.
#   rust     the `opencut` CLI, linked against those libraries.
#   runtime  Node 24 + Bun 1.3.11 (Remotion, lesson.ts), Python (QC, audio, PTC), Chromium for
#            Remotion, Japanese fonts. textts, AivisSpeech and QBank are separate services: see compose.yaml.

ARG FFMPEG_VERSION=8.1.3
ARG FFMPEG_SHA256=7138d28c96d9d3e3af4ee3d8cad72741f8ffb40da90c1112235dea3ecd3178a3
ARG RUST_VERSION=1.97.0
ARG BUN_VERSION=1.3.11

# ---- ffmpeg ---------------------------------------------------------------
FROM debian:bookworm-slim AS ffmpeg
ARG FFMPEG_VERSION
ARG FFMPEG_SHA256
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates curl xz-utils build-essential pkg-config nasm yasm \
        libopenh264-dev \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /src
RUN curl -fsSL -o ffmpeg.tar.xz "https://ffmpeg.org/releases/ffmpeg-${FFMPEG_VERSION}.tar.xz" \
    && echo "${FFMPEG_SHA256}  ffmpeg.tar.xz" | sha256sum -c - \
    && tar -xf ffmpeg.tar.xz && mv "ffmpeg-${FFMPEG_VERSION}" ffmpeg
# Same switches as the pinned build (crates/media/setup/ffmpeg.json, .cache/media/current/BUILD.md),
# with two differences: the programs are built (the pipeline runs ffmpeg/ffprobe), and avfilter is kept
# (lesson.ts uses -af loudnorm). OpenH264 comes from Debian, so H.264 still works without Cisco's download.
RUN cd ffmpeg && ./configure --prefix=/opt/ffmpeg \
        --enable-shared --disable-static --disable-doc --disable-network \
        --disable-autodetect --enable-libopenh264 \
    && make -j"$(nproc)" && make install

# ---- rust -----------------------------------------------------------------
FROM rust:${RUST_VERSION}-bookworm AS rust
RUN apt-get update && apt-get install -y --no-install-recommends \
        clang libclang-dev pkg-config libopenh264-dev \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY . .
# .cargo/config.toml sets FFMPEG_DIR=.cache/media/current; put the FFmpeg build exactly there.
COPY --from=ffmpeg /opt/ffmpeg/ .cache/media/current/
RUN cargo build --release -p opencut-cli \
    && cp target/release/opencut /usr/local/bin/opencut

# ---- bun ------------------------------------------------------------------
FROM oven/bun:${BUN_VERSION} AS bun

# ---- runtime --------------------------------------------------------------
FROM node:24-bookworm-slim AS runtime
COPY --from=bun /usr/local/bin/bun /usr/local/bin/bun

RUN apt-get update && apt-get install -y --no-install-recommends \
        python3 python3-venv ca-certificates libopenh264-7 \
        fonts-noto-cjk \
        libnss3 libatk-bridge2.0-0 libgbm1 libasound2 libxkbcommon0 libxcomposite1 \
        libxdamage1 libxfixes3 libxrandr2 libpango-1.0-0 libcairo2 libdrm2 \
    && rm -rf /var/lib/apt/lists/*

# Python: lesson_qc (Pillow), lesson_audio and opencut_ptc (standard library), slice_sheet (numpy).
RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:${PATH}"
RUN pip install --no-cache-dir "pillow>=10" "numpy>=1.26"

WORKDIR /app
# Pipeline binaries and libraries, at the paths the Rust build and the environment variables expect.
COPY --from=rust /usr/local/bin/opencut /usr/local/bin/opencut
COPY --from=rust /app/.cache/media/current /app/.cache/media/current
ENV OPENCUT_BIN=/usr/local/bin/opencut \
    OPENCUT_FFMPEG=/app/.cache/media/current/bin/ffmpeg \
    OPENCUT_FFPROBE=/app/.cache/media/current/bin/ffprobe \
    OPENCUT_NODE=/usr/local/bin/node \
    LD_LIBRARY_PATH=/app/.cache/media/current/lib \
    QBANK_URL=http://host.docker.internal:8765 \
    TEXTTS_URL=http://host.docker.internal:8000 \
    AIVIS_URL=http://host.docker.internal:10101 \
    PATH=/app/.cache/media/current/bin:/opt/venv/bin:${PATH}

# Repository (without the ignored build outputs, see .dockerignore), then the JS dependencies from the lock.
COPY . .
RUN cd apps/intro && bun install --frozen-lockfile \
    && bun x remotion browser ensure

# Whisper (for `lesson words`) is not baked in: its model is ~150 MB. Run once in a volume:
#   docker compose run --rm opencut bun run --cwd apps/intro lesson whisper-setup
ENV WHISPER_DIR=/app/.cache/whisper

CMD ["python", "scripts/opencut_ptc.py", "check"]
