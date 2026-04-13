# Dockerfile for the FastAPI backend service.
#
# This file describes how to build a Docker container image for the API.
# Docker reads this file top to bottom and executes each instruction to
# produce a reproducible, self-contained environment that runs identically
# on any machine regardless of what is installed locally.
#
# The uv package manager is used instead of pip for faster dependency
# installation. The uv binary is copied from its official image rather
# than installed via pip to keep the image lean.

# Use the official Python 3.11 slim image as the base. "slim" means it
# contains only what Python needs to run, keeping the image size small.
FROM python:3.11-slim

# Copy the uv binary from the official uv image.
# This avoids installing uv via pip and keeps the image size minimal.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Set the working directory inside the container.
# All subsequent commands run relative to this path.
WORKDIR /app

# Test print to validate that the dockerfile is being hit.
RUN echo "=== Docker build is running ==="

# Copy only the dependency files first and install before copying the
# application code. Docker caches each instruction as a layer. By
# installing dependencies in a separate layer, Docker can reuse the
# cached layer on rebuilds as long as the dependency files have not
# changed -- which makes rebuilds much faster during development.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev
# --frozen: use exact versions from uv.lock, do not update anything
# --no-dev: skip development-only dependencies (linters, test tools, etc.)

# Copy the rest of the application code into the container.
COPY . .

# Document that this container listens on port 8000.
# This does not actually open the port -- that is done in docker-compose.yml.
EXPOSE 8000

# Default command: start the Uvicorn ASGI server.
# 0.0.0.0 makes the server accessible from outside the container
# (within the Docker network), which is required for the frontend to
# reach it. In native development mode, 127.0.0.1 is used instead.
CMD ["uv", "run", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
