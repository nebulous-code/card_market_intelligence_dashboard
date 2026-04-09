FROM python:3.11-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY . .

# No default command — this container is run on demand:
#   docker compose run ingestion uv run python run.py --set-id base1
CMD ["echo", "Run with: docker compose run ingestion uv run python run.py --set-id <set_id>"]
