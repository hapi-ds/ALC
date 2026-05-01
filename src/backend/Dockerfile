# AlcoaBase Backend - Multi-stage Dockerfile
# Uses uv for dependency management, runs as non-root user.

# ─────────────────────────────────────────────────────────────────────────────
# Stage 1: Builder — install dependencies with uv
# ─────────────────────────────────────────────────────────────────────────────
FROM python:3.13-slim AS builder

WORKDIR /build

# Install uv from the official standalone installer
COPY --from=ghcr.io/astral-sh/uv:0.7.12 /uv /usr/local/bin/uv

# Copy dependency files first for layer caching
COPY pyproject.toml uv.lock ./

# Install production dependencies into a virtual environment
RUN uv sync --frozen --no-dev --no-install-project

# Copy application source
COPY src/ ./src/

# Install the project itself
RUN uv sync --frozen --no-dev

# ─────────────────────────────────────────────────────────────────────────────
# Stage 2: Runtime — minimal image with non-root user
# ─────────────────────────────────────────────────────────────────────────────
FROM python:3.13-slim AS runtime

WORKDIR /app

# Create non-root user
RUN groupadd --gid 1000 appuser \
    && useradd --uid 1000 --gid 1000 --shell /bin/bash --create-home appuser

# Copy the virtual environment from builder
COPY --from=builder /build/.venv /app/.venv

# Copy application source
COPY --from=builder /build/src /app/src

# Ensure the venv binaries are on PATH
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Switch to non-root user
USER appuser

EXPOSE 8080

CMD ["uvicorn", "alcoabase.main:app", "--host", "0.0.0.0", "--port", "8080"]
