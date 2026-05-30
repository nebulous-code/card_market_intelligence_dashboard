#!/bin/bash
# Connect to the dev or prod database using psql.
# Usage: ./psql_launcher.sh d   (dev)
#        ./psql_launcher.sh p   (prod)

if [[ "$1" != "d" && "$1" != "p" ]]; then
    echo "Usage: $0 [d|p]"
    echo "  d = dev (DATABASE_URL)"
    echo "  p = prod (DATABASE_URL_PROD)"
    exit 1
fi

# Load .env from the same directory as this script.
ENV_FILE="$(dirname "$0")/.env"
if [[ ! -f "$ENV_FILE" ]]; then
    echo "Error: .env not found at $ENV_FILE"
    exit 1
fi

while IFS='=' read -r key rest; do
    key="${key// /}"
    [[ -z "$key" || "${key:0:1}" == "#" ]] && continue
    # Strip inline comments and surrounding quotes from value.
    value="${rest%%#*}"
    value="${value%"${value##*[^ ]}"}"  # rtrim
    value="${value#\"}" value="${value%\"}"
    value="${value#\'}" value="${value%\'}"
    export "$key=$value"
done < "$ENV_FILE"

if [[ "$1" == "p" ]]; then
    DB_CONNECTION="$DATABASE_URL_PROD"
    echo "Connecting to: prod environment..."
else
    DB_CONNECTION="$DATABASE_URL"
    echo "Connecting to: dev environment..."
fi

if [[ -z "$DB_CONNECTION" ]]; then
    echo "Error: connection string is empty. Check your .env file."
    exit 1
fi

psql "$DB_CONNECTION"
