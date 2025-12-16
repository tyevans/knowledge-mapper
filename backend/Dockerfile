# Multi-stage Dockerfile for Knowledge Mapper Backend

# Stage 1: Base image with Python 3.13
FROM python:3.13-slim AS base

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_LINK_MODE=copy

# Set working directory
WORKDIR /app

# Install system dependencies and uv
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    gcc \
    python3-dev \
    postgresql-client \
    curl \
    && rm -rf /var/lib/apt/lists/* && \
    curl -LsSf https://astral.sh/uv/install.sh | UV_INSTALL_DIR=/usr/local/bin sh

ENV PATH="/usr/local/bin:$PATH"


# Stage 2: Dependencies
FROM base AS dependencies

# Copy uv files and README for dependency installation
COPY pyproject.toml uv.lock README.md ./

# Sync dependencies using uv
RUN uv sync --frozen --no-dev


# Stage 3: Development image
FROM dependencies AS development

# Build args for user mapping (defaults to 1000:1000)
ARG UID=1000
ARG GID=1000

# Create non-root user matching host UID/GID for proper file permissions
RUN groupadd -g ${GID} appuser 2>/dev/null || true && \
    useradd -m -u ${UID} -g ${GID} appuser 2>/dev/null || true && \
    chown -R ${UID}:${GID} /app

# Switch to non-root user
USER appuser

# Copy application code
COPY . .

# Expose port
EXPOSE 8000

# Run with hot-reload for development
CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]


# Stage 4: Production image
FROM dependencies AS production

# OCI Labels for container metadata
# See: https://github.com/opencontainers/image-spec/blob/main/annotations.md
LABEL org.opencontainers.image.title="Knowledge Mapper Backend"
LABEL org.opencontainers.image.description="FastAPI backend service for Knowledge Mapper"
LABEL org.opencontainers.image.vendor="Tyler Evans"
LABEL org.opencontainers.image.licenses="MIT"
LABEL org.opencontainers.image.source="https://github.com/your-github-username/knowledge-mapper"

# Create non-root user for security
# Using UID 1000 for compatibility with host user mapping
RUN useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app

# Copy application code with correct ownership
COPY --chown=appuser:appuser . .

# Switch to non-root user (security best practice)
USER appuser

# Expose port
EXPOSE 8000

# Health check configuration
# Aligns with Kubernetes probe patterns:
#   --interval=30s    -> periodSeconds: 30
#   --timeout=10s     -> timeoutSeconds: 10
#   --start-period=10s -> initialDelaySeconds: 10
#   --retries=3       -> failureThreshold: 3
# Uses curl (already installed in base stage for uv installation)
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/api/v1/health || exit 1

# Run with production settings (4 workers for multi-core utilization)
CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
