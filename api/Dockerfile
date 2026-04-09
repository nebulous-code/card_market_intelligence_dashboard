FROM python:3.11-slim AS base

WORKDIR /app

# Install dependencies in a separate layer for better cache reuse.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code.
COPY . .

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
