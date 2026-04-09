FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# No default command — this container is run on demand:
#   docker compose run ingestion python run.py --set-id base1
CMD ["echo", "Run with: docker compose run ingestion python run.py --set-id <set_id>"]
