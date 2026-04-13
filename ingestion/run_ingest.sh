#!/bin/bash
# Runs the ingestion script to fetch card data from TCGdex and save it
# to the database.
#
# Requires one argument: the TCGdex set ID to ingest. A full list of valid
# set IDs is available at https://tcgdex.dev.
#
# This script is safe to run more than once. Sets and cards are upserted
# (inserted or updated) so re-running it will not create duplicate rows.
#
# The API server must have been started at least once before running this
# script so that Alembic has created the database tables.
#
# Usage: ./run_ingest.sh base1

# Exit immediately if no set ID was provided, with a helpful usage message.
if [ -z "$1" ]; then
    echo "Usage: ./run_ingest.sh <set-id>"
    echo "Example: ./run_ingest.sh base1"
    exit 1
fi

uv run python run_ingest.py --set-id "$1"
