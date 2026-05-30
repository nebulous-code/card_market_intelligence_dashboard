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
# Usage:
#   ./run_ingest.sh base1           # existing set (must be in set_identifiers)
#   ./run_ingest.sh base2 --new-set # first-time ingest, bypasses resolver

# Exit immediately if no set ID was provided, with a helpful usage message.
if [ -z "$1" ]; then
    echo "Usage: ./run_ingest.sh <set-id> [--new-set]"
    echo "Example: ./run_ingest.sh base1"
    echo "         ./run_ingest.sh base2 --new-set"
    exit 1
fi

if [ "$2" = "--new-set" ]; then
    uv run python run_ingest.py --set-id "$1" --new-set
else
    uv run python run_ingest.py --set-id "$1"
fi
