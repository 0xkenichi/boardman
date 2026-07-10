# syntax=docker/dockerfile:1
# Multi-stage, production-ready image for the ClawStation gaming backend and bot.
#
# Build context must be the repository root so that both backend/ and gaming/
# are available. The default command starts the FastAPI API; override the
# command in docker-compose.yml to start the Telegram bot.
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

# Copy requirement files first to leverage Docker layer caching.
COPY backend/requirements.txt ./backend/requirements.txt
COPY gaming/src/backend/requirements.txt ./gaming/src/backend/requirements.txt

# Create the shared Python virtual environment and install all dependencies.
RUN python -m venv /app/.venv && \
    /app/.venv/bin/pip install --no-cache-dir --upgrade pip && \
    /app/.venv/bin/pip install --no-cache-dir \
        -r ./backend/requirements.txt \
        -r ./gaming/src/backend/requirements.txt

# Copy the full repository into the image so imports from backend/ and gaming/
# resolve correctly.
COPY . /app

# Create a non-root user and ensure it owns the application directory.
RUN groupadd -r clawstation && useradd -r -g clawstation -d /app clawstation && \
    chown -R clawstation:clawstation /app

USER clawstation

# Make the venv binaries available on PATH for downstream commands.
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Expose the FastAPI port. The bot service does not need an exposed port but
# shares this image.
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/api/healthz || exit 1

# Default command runs the FastAPI API. Override with CMD in compose to run bot.
CMD ["uvicorn", "gaming.src.backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
