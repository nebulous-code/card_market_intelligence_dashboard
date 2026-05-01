#!/bin/bash
# Runs the Milestone 2 price ingestion script.
#
# Fetches current card prices from PokemonPriceTracker for all sets in the
# database and writes them to the price_snapshots table.
#
# Run this after the TCGdex ingestion (run_ingest.sh) has populated the
# sets and cards tables.
#
# Tier behaviour is controlled by environment variables in .env:
#   PPT_INCLUDE_HISTORY=false   # set to true for historical backfill (API tier)
#   PPT_INCLUDE_EBAY=false      # set to true for graded prices (API tier)
#
# Usage: ./run_prices.sh

uv run python run.py
