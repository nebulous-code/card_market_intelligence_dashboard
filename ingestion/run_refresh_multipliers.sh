#!/bin/bash
# Wrapper for run_refresh_multipliers.py. Mirrors run_prices.sh / run_ingest.sh.
#
# Usage:
#   ./run_refresh_multipliers.sh

set -euo pipefail

cd "$(dirname "$0")"
uv run python run_refresh_multipliers.py
