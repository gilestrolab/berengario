# Multi-stage Dockerfile for Berengario
# Builds both production and development images with shared base

# ============================================================================
# Builder stage - Install Python dependencies
# ============================================================================
FROM python:3.12-slim AS builder

WORKDIR /app

# Install system dependencies for building Python packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Copy only requirements first to leverage Docker layer caching
COPY pyproject.toml ./

# Install Python dependencies (including MariaDB support)
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -e ".[mariadb]"

# ============================================================================
# Base stage - Common setup for both dev and production
# ============================================================================
FROM python:3.12-slim AS base

WORKDIR /app

# Create non-root user for security
RUN useradd -m -u 1000 -s /bin/bash berengario && \
    chown -R berengario:berengario /app

# Install runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy Python packages from builder
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code
COPY --chown=berengario:berengario . .

# Create data directories with proper permissions
RUN mkdir -p data/documents data/chroma_db data/logs data/config data/temp_attachments && \
    chown -R berengario:berengario data/

# Copy CLI wrapper script to PATH
COPY --chmod=755 scripts/berengario-cli /usr/local/bin/berengario-cli

# Set Python to run in unbuffered mode (better for Docker logs)
ENV PYTHONUNBUFFERED=1

# Expose API port
EXPOSE 8000

# ============================================================================
# Development stage - Includes testing and linting tools
# ============================================================================
FROM base AS dev

# Install build tools needed for some dev dependencies
USER root
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Install package with dev dependencies
RUN pip install --no-cache-dir -e ".[dev,mariadb]"

# Switch to non-root user
USER berengario

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import sys; sys.exit(0)"

# Default command
CMD ["python", "run_email_service.py"]

# ============================================================================
# Production stage (default) - Minimal size, runtime dependencies only
# ============================================================================
FROM base AS production

# Install the package (production dependencies only)
RUN pip install --no-cache-dir -e ".[mariadb]"

# Switch to non-root user
USER berengario

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import sys; sys.exit(0)"

# Default command
CMD ["python", "run_email_service.py"]
