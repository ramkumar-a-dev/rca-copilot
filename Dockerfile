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

# Document the port the service listens on
EXPOSE 8000

# The command that runs when the container starts
CMD ["uvicorn", "rca_copilot.api:app", "--host", "0.0.0.0", "--port", "8000"]