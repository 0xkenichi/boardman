# syntax=docker/dockerfile:1
# Production image for the ClawStation gaming backend and bot.
#
# The runtime imports gaming.src.backend.* (and backend.* via the codebase's
# backend.X convention), which normally requires the gitignored gaming/ and
# backend/ shim dirs in the build context. This image materializes those shims
# from the tracked src/ tree, so it builds cleanly from a fresh checkout.
#
# The default command starts the FastAPI API; override the command in
# docker-compose.yml to start the Telegram bot.
FROM python:3.12-slim

# Install system build dependencies and curl for the Dockerfile HEALTHCHECK.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    libffi-dev \
    libssl-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

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
RUN groupadd -r clawstation && useradd -r -g clawstation -d /app clawstation && \
    chown -R clawstation:clawstation /app

USER clawstation

# Make the venv binaries available on PATH for downstream commands.
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONPATH=/app

# Expose the FastAPI port. The bot service does not need an exposed port but
# shares this image.
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/api/healthz || exit 1

# Default command runs the FastAPI API. Override with CMD in compose to run bot.
CMD ["uvicorn", "gaming.src.backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
