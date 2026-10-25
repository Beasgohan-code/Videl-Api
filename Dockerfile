# Videl-Api v3.2.0 - Multi-Source Media REST API
# Multi-stage build for smaller production image

# ------------------------------------------------------------
# Stage 1: Build / Dependencies
# ------------------------------------------------------------
FROM python:3.11-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# System dependencies for building
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

# Install Python dependencies first (better layer caching)
COPY requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt

# ------------------------------------------------------------
# Stage 2: Runtime
# ------------------------------------------------------------
FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH=/home/videl/.local/bin:$PATH \
    VIDEL_LOG_LEVEL=INFO \
    VIDEL_LOG_FORMAT=json \
    VIDEL_LOG_DIR=/app/logs \
    DOWNLOAD_DIR=/app/downloads \
    DOWNLOAD_MAX_CONCURRENT=3 \
    API_HOST=0.0.0.0 \
    API_PORT=8000 \
    API_BASE_URL=http://localhost:8000

# Runtime system dependencies (ffmpeg for audio processing, curl for healthcheck)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN groupadd -r videl && useradd -r -g videl -d /home/videl -s /sbin/nologin videl

WORKDIR /app

# Copy Python packages from builder
COPY --from=builder /root/.local /home/videl/.local

# Copy application code
COPY main.py .
COPY auth.py .
COPY cache.py .
COPY config.py .
COPY download_manager.py .
COPY downloader.py .
COPY logger.py .
COPY metrics.py .
COPY m3u8_downloader.py .
COPY models.py .
COPY plugins.py .
COPY rate_limit.py .
COPY scheduler.py .
COPY security.py .
COPY telegram_bot.py .
COPY watchdog.py .
COPY websocket_manager.py .
COPY webapp ./webapp

# Copy environment template (actual .env should be mounted at runtime)
COPY .env.example .env.example

# Create directories with proper ownership
RUN mkdir -p /app/downloads /app/logs && \
    chown -R videl:videl /app

# Switch to non-root user
USER videl

# Expose API port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Copy entrypoint script
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# Default command uses the entrypoint script
ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
