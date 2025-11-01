# Multi-stage Dockerfile for RAGInbox
# Builds a production-ready container with minimal size

FROM python:3.12-slim AS builder

# Set working directory
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

# Production stage
FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Create non-root user for security
RUN useradd -m -u 1000 -s /bin/bash raginbox && \
    chown -R raginbox:raginbox /app

# Install runtime dependencies only
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Copy Python packages from builder
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code
COPY --chown=raginbox:raginbox . .

# Create data directories with proper permissions
RUN mkdir -p data/documents data/chroma_db data/logs data/config data/temp_attachments && \
    chown -R raginbox:raginbox data/

# Install the package to ensure CLI entry points are available
# This must be done after copying the code so pyproject.toml is available
RUN pip install --no-cache-dir -e ".[mariadb]"

# Copy CLI wrapper script to PATH
COPY --chmod=755 scripts/raginbox-cli /usr/local/bin/raginbox-cli

# Switch to non-root user
USER raginbox

# Set Python to run in unbuffered mode (better for Docker logs)
ENV PYTHONUNBUFFERED=1

# Expose API port (if needed)
EXPOSE 8000

# Health check for the service
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import sys; sys.exit(0)"

# Default command: run email service
# Can be overridden in docker-compose or at runtime
CMD ["python", "run_email_service.py"]
