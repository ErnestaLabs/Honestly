# ────────────────────────────────────────────────────────
# Honestly Backend — FastAPI + Uvicorn
# Base: python:3.11-slim for a lean production image
# ────────────────────────────────────────────────────────
FROM python:3.11-slim AS builder

# Prevent Python from writing .pyc / buffering stdout
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Install build dependencies for psycopg2, geopandas, numpy/scipy
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    gdal-bin \
    libgdal-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy and install Python dependencies first (maximises Docker layer cache)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── Runtime stage ───────────────────────────────────────
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive

# Install ONLY runtime system deps (much smaller than build deps)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    libgdal34 \
    ca-certificates \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy the venv from the builder stage
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code
COPY . .

# Expose the FastAPI port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -sf http://localhost:8000/health || exit 1

# Run with 4 uvicorn workers
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
