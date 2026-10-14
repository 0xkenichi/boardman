# syntax=docker/dockerfile:1
# Production image for the ClawStation gaming backend and bot.
#
# The runtime imports gaming.src.backend.* (and backend.* via the codebase's
# backend.X convention), which normally requires the gitignored gaming/ and
# backend/ shim dirs in the build context. This image materializes those shims
# from the tracked src/ tree, so it builds cleanly from a fresh checkout.
#
# The default command starts the FastAPI API; override the command to
# start the Telegram bot.
#
# docker-compose and production both use Dockerfile.akash now; this image is
# kept for single-process API runs and mirrors its engine + data layout.

# Ethereal (Sheila's engine), built portable — see Dockerfile.akash.
FROM python:3.12-slim AS ethereal
ARG ETHEREAL_REF=0e47e9b67f345c75eb965d9fb3e2493b6a11d09a
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential git ca-certificates \
    && rm -rf /var/lib/apt/lists/*
RUN mkdir -p /out \
    && ( git init -q /build \
         && git -C /build remote add origin https://github.com/AndyGrant/Ethereal.git \
         && git -C /build fetch -q --depth 1 origin "${ETHEREAL_REF}" \
         && git -C /build checkout -q FETCH_HEAD \
         && make -C /build/src basic CC=gcc EXE=ethereal \
              CFLAGS="-O2 -std=gnu11 -DNDEBUG -DUSE_NNUE=0" \
         && install -m 0755 /build/src/ethereal /out/ethereal \
         && printf 'uci\nquit\n' | /out/ethereal | grep -q uciok ) \
    || (rm -f /out/ethereal; echo "WARN: Ethereal build failed; Sheila will use Stockfish")

FROM python:3.12-slim

# System build deps, curl for HEALTHCHECK, and a local Stockfish
# (/usr/games/stockfish) so chess never depends on stockfish.online.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    libffi-dev \
    libssl-dev \
    curl \
    stockfish \
    && rm -rf /var/lib/apt/lists/* \
    && ln -sf /usr/games/stockfish /usr/local/bin/stockfish \
    && printf 'uci\nquit\n' | /usr/games/stockfish | grep -q uciok

WORKDIR /app

# Copy requirement file first to leverage Docker layer caching.
COPY src/backend/requirements.txt /app/requirements.txt

# Create the shared Python virtual environment and install all dependencies.
RUN python -m venv /app/.venv && \
    /app/.venv/bin/pip install --no-cache-dir --upgrade pip && \
    /app/.venv/bin/pip install --no-cache-dir -r /app/requirements.txt

# Copy the tracked source tree and config (brand assets are optional for the bot).
COPY src /app/src
COPY config /app/config
COPY frontend/public /app/frontend/public
COPY --from=ethereal /out/ /app/engines/Ethereal/src/

# Materialize the gaming/ and backend/ import shims from the tracked tree:
#   gaming.src.*  ->  src/*
#   backend.*     ->  src/backend/*
RUN mkdir -p /app/gaming \
    && ln -sfn /app/src /app/gaming/src \
    && touch /app/gaming/__init__.py \
    && ln -sfn /app/config /app/gaming/config \
    && ln -sfn /app/src/backend /app/backend \
    && test -f /app/backend/supabase_client.py \
    && test -f /app/gaming/src/bot/main.py

# Create a non-root user and ensure it owns the application directory.
# /data is the persistent volume mount point (agentic ledger, escrows, books).
RUN groupadd -r clawstation && useradd -r -g clawstation -d /app clawstation && \
    mkdir -p /data/agentic && \
    chown -R clawstation:clawstation /app /data

USER clawstation

# Make the venv binaries available on PATH for downstream commands.
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONPATH=/app
ENV BOARDMAN_AGENTIC_DATA=/data/agentic
ENV STOCKFISH_PATH=/usr/games/stockfish

# Expose the FastAPI port. The bot service does not need an exposed port but
# shares this image.
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/api/healthz || exit 1

# Default command runs the FastAPI API. Override with CMD in compose to run bot.
CMD ["uvicorn", "gaming.src.backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
