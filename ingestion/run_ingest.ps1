# Runs the ingestion script to fetch card data from TCGdex and save it
# to the database.
#
# Requires a -SetId argument specifying which set to ingest. The set ID
# must be a valid TCGdex identifier. A full list of IDs is available at
# https://tcgdex.dev.
#
# This script is safe to run more than once. Sets and cards are upserted
# (inserted or updated) so re-running it will not create duplicate rows.
#
# The API server must have been started at least once before running this
# script so that Alembic has created the database tables.
#
# Usage: .\run_ingest.ps1 -SetId base1

param(
    # The TCGdex set ID to ingest. Required.
    # Example values: base1 (Base Set), base2 (Jungle), base3 (Fossil)
    [Parameter(Mandatory=$true)]
    [string]$SetId
)

uv run python run.py --set-id $SetId
