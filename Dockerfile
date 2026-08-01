# ---- Stage 1: builder ----
FROM python:3.12-slim AS builder

# Install uv (our package manager) into the builder
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Copy only dependency files first (for layer caching)
COPY pyproject.toml uv.lock README.md ./

# Install dependencies into a virtual environment
RUN uv sync --frozen --no-install-project --no-dev

# Now copy the actual source code
COPY src ./src

# Install the project itself
RUN uv sync --frozen --no-dev

# ---- Stage 2: runtime ----
FROM python:3.12-slim AS runtime

WORKDIR /app

# Copy the finished virtual environment and code from the builder
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/src /app/src

# Put the venv's tools on the PATH
ENV PATH="/app/.venv/bin:$PATH"

# Document the port the service listens on (local default)
EXPOSE 8000

# Bind to the platform-provided $PORT when present (Railway/Render/Cloud Run
# all inject it), falling back to 8000 for local `docker run`. Shell form is
# required so ${PORT} expands — exec form would pass it as a literal string.
CMD uvicorn rca_copilot.api:app --host 0.0.0.0 --port ${PORT:-8000}