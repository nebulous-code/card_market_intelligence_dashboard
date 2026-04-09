#!/bin/bash
if [ -z "$1" ]; then
    echo "Usage: ./run_ingest.sh <set-id>"
    echo "Example: ./run_ingest.sh base1"
    exit 1
fi

uv run python run.py --set-id "$1"
