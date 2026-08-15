# SuperGuard Core - Dockerfile

# Build stage
FROM python:3.11-slim as builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install poetry for dependency management
RUN pip install --no-cache-dir poetry==1.8.3

# Copy project files
COPY pyproject.toml poetry.lock* ./

# Install dependencies
RUN poetry config virtualenvs.create false \
    && poetry install --no-dev --no-interaction --no-ansi

# Runtime stage
FROM python:3.11-slim

WORKDIR /app

# Install runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    libgl1-mesa-glx \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgomp1 \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Create non-root user
RUN groupadd -r superguard && useradd -r -g superguard superguard

# Copy application code
COPY --chown=superguard:superguard . .

# Create storage directories
RUN mkdir -p /app/storage/media /app/storage/thumbnails /app/storage/recordings /app/models \
    && chown -R superguard:superguard /app/storage /app/models

# Switch to non-root user
USER superguard

# Environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    SG_HOST=0.0.0.0 \
    SG_PORT=8000 \
    SG_WORKERS=4

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/system/health || exit 1

# Run application
CMD ["python", "-m", "uvicorn", "superguard_core.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]