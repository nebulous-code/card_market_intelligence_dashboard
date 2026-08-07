#!/usr/bin/env bash
#
# Verify a set name against PokemonPriceTracker before adding it to
# ingestion/priced_sets.yml, and show the TCGdex set_id to pair it with.
#
# Usage:
#   tools/check_ppt_set.sh "Team Rocket"
#   tools/check_ppt_set.sh "Team Rocket" "Gym Heroes" "Neo Genesis"
#
# Why this exists: a wrong ppt_name is not an error. PokemonPriceTracker
# returns an empty result, the nightly run records zero prices, and the set
# looks exactly like one we simply have no data for. This asks the API
# directly so a typo fails here instead of silently, weeks later.
#
# Costs 1 credit per name checked (against a 20,000/day budget) and writes
# nothing to any database.

set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

if [ $# -eq 0 ]; then
    echo "usage: tools/check_ppt_set.sh \"<PPT set name>\" [more names...]" >&2
    exit 2
fi

uv run python - "$@" <<'PY'
import os
import sys

import requests
from dotenv import load_dotenv

load_dotenv(".env")

key = os.environ.get("POKEMON_PRICE_TRACKER_API_KEY")
if not key:
    sys.exit("POKEMON_PRICE_TRACKER_API_KEY is not set (check .env)")

# Optional: match the name against the local catalogue to suggest a set_id.
# dev and prod carry the same TCGdex catalogue, so either database answers.
catalogue = {}
db_url = os.environ.get("DATABASE_URL")
if db_url:
    try:
        from sqlalchemy import create_engine, text
        from sqlalchemy.orm import Session

        with Session(create_engine(db_url, pool_pre_ping=True)) as s:
            rows = s.execute(
                text("SELECT id, name, printed_total FROM sets ORDER BY name")
            ).fetchall()
        catalogue = {r.name.lower(): (r.id, r.printed_total) for r in rows}
    except Exception as e:  # pragma: no cover -- operator convenience only
        print(f"(catalogue lookup unavailable: {e})\n")

remaining = "?"
for name in sys.argv[1:]:
    r = requests.get(
        "https://www.pokemonpricetracker.com/api/v2/cards",
        headers={"Authorization": f"Bearer {key}"},
        params={"set": name, "limit": 1},
        timeout=30,
    )
    remaining = r.headers.get("X-RateLimit-Daily-Remaining", remaining)
    found = len((r.json() or {}).get("data", [])) if r.ok else -1

    if not r.ok:
        print(f"  FAIL   {name!r}  HTTP {r.status_code}")
        continue
    if found == 0:
        print(f"  NO MATCH  {name!r}")
        print("           PokemonPriceTracker returns nothing for this name.")
        print("           Check the exact spelling on pokemonpricetracker.com.")
        continue

    sid, printed = catalogue.get(name.lower(), (None, None))
    print(f"  MATCH  {name!r}")
    if sid:
        cost = (printed or 0) * 2
        print(f"           set_id: {sid}   ({printed} cards, ~{cost} credits/night)")
        print("           add to ingestion/priced_sets.yml:")
        print(f"             - set_id: {sid}")
        quoted = f'"{name}"' if any(c in name for c in ':&#') else name
        print(f"               ppt_name: {quoted}")
    else:
        print("           No catalogue set with this exact name -- the TCGdex")
        print("           name may differ from PPT's. Find the set_id yourself.")

print(f"\n  credits remaining today: {remaining}")
PY
