# Dockerfile for the ingestion service.
#
# This container is not started automatically. It is run on demand to
# fetch card data from TCGdex and write it to the database.
#
# Run it with:
#   docker compose run ingestion uv run python run.py --set-id base1
#
# The command above overrides the default CMD defined at the bottom of
# this file, so the default CMD serves only as a reminder message.

FROM python:3.11-slim

# Copy the uv binary from the official uv image.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Install dependencies before copying app code for better layer caching.
# See api/Dockerfile for a detailed explanation of why this order matters.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

# Copy the ingestion scripts into the container.
COPY . .

# The default command prints a usage reminder. When running the ingestion
# script for real, the command is overridden via "docker compose run":
#   docker compose run ingestion uv run python run.py --set-id base1
CMD ["echo", "Run with: docker compose run ingestion uv run python run.py --set-id <set_id>"]
