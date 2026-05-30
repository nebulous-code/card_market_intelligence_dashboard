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
# Usage:
#   .\run_ingest.ps1 -SetId base1           # existing set (must be in set_identifiers)
#   .\run_ingest.ps1 -SetId base2 -NewSet   # first-time ingest, bypasses resolver

param(
    # The TCGdex set ID to ingest. Required.
    # Example values: base1 (Base Set), base2 (Jungle), base3 (Fossil)
    [Parameter(Mandatory=$true)]
    [string]$SetId,

    # Pass -NewSet when ingesting a set for the first time.
    # Bypasses the set_identifiers resolver so the set can be fetched directly
    # from TCGdex before its mapping row exists. After ingestion completes,
    # insert the set_identifiers rows and omit this flag on future runs.
    [switch]$NewSet
)

if ($NewSet) {
    uv run python run_ingest.py --set-id $SetId --new-set
} else {
    uv run python run_ingest.py --set-id $SetId
}
