"""
Entry point for the TCGdex catalogue ingest.

Walks every set TCGdex publishes and writes identity-only rows -- the set
metadata plus each card's id, name and number. No rarity, no supertype:
those come from the per-card endpoint, which costs one HTTP call per card
and is only worth paying for sets we actually price.

The point of this job is to let the collection upload validator tell three
things apart:

    "Jungle"      -> a real set we do not price yet
    "Jungel"      -> a typo
    "base1-4"     -> a real card in a set we do price

Without a full catalogue, the first two are indistinguishable and the user
gets told they made a mistake when they did not.

Runs nightly, before the price ingestion. Costs nothing -- TCGdex is free
and unauthenticated -- and takes a little over a minute.

Usage (manual):
    uv run python run_catalogue.py

Usage (GitHub Actions):
    See .github/workflows/ingest.yml

Environment variables:
    DATABASE_URL  -- required: PostgreSQL connection string
"""

import logging
import os
import sys
import time

from dotenv import find_dotenv, load_dotenv
from logging_setup import configure_logging

# Configure logging before loading any local modules so that log lines from
# tcgdex.py and loader.py all go to both the console and ingestion.log.
configure_logging()

# Load .env before importing any local modules that read env vars at import time.
load_dotenv(find_dotenv())

from loader import engine, load_set_identity                          # noqa: E402
from sqlalchemy import text                                           # noqa: E402
from sqlalchemy.orm import Session                                    # noqa: E402
from tcgdex import CATALOGUE_DELAY_SECONDS, get_set, get_sets         # noqa: E402

log = logging.getLogger(__name__)

# TCGdex series id for Pokemon TCG Pocket, the digital-only phone game.
# Those cards cannot be physically owned, graded, or sold, so every feature
# downstream of the catalogue -- condition multipliers, upgrade cost,
# purchase price -- is meaningless for them. Ingesting them would put ~15
# sets in the upload template's dropdown that can never be priced.
EXCLUDED_SERIES = {"tcgp"}

# Cap on how many new set names are listed in the summary. A first run finds
# every set, and a 218-line email is not a summary.
MAX_NEW_SETS_LISTED = 20


def _existing_set_ids() -> set[str]:
    """Set ids already in the database, for new-set detection."""
    with Session(engine) as session:
        rows = session.execute(text("SELECT id FROM sets")).fetchall()
    return {r.id for r in rows}


def main() -> None:
    """
    Walk the TCGdex catalogue and upsert identity rows for every set.

    Each set is fetched and written independently, so one bad set is skipped
    rather than aborting the run. Only a failure to fetch the set list itself
    is fatal -- without it there is nothing to iterate.
    """
    log.info("Starting TCGdex catalogue ingest.")

    try:
        briefs = get_sets()
    except Exception as e:
        log.error("Failed to fetch the set list from TCGdex: %s", e)
        _write_summary(
            status="Failed",
            summary=f"Could not fetch the set list from TCGdex: {e}",
        )
        sys.exit(1)

    log.info("TCGdex published %d sets.", len(briefs))

    known_set_ids = _existing_set_ids()

    sets_upserted = 0
    sets_excluded = 0
    cards_upserted = 0
    duplicates_skipped = 0
    malformed_skipped = 0
    new_sets: list[str] = []
    failures: list[tuple[str, str]] = []

    total = len(briefs)
    for i, brief in enumerate(briefs, start=1):
        set_id = brief["id"]

        try:
            set_data = get_set(set_id)
        except Exception as e:
            log.error("[%d/%d] %s: fetch failed: %s. Skipping.", i, total, set_id, e)
            failures.append((set_id, f"fetch: {e}"))
            continue
        finally:
            # Pace the walk whether or not the call succeeded, so a run of
            # failures cannot turn into a burst of retries against the API.
            time.sleep(CATALOGUE_DELAY_SECONDS)

        serie_id = (set_data.get("serie") or {}).get("id")
        if serie_id in EXCLUDED_SERIES:
            log.info("[%d/%d] %s: skipping -- series '%s' is excluded.", i, total, set_id, serie_id)
            sets_excluded += 1
            continue

        try:
            stats = load_set_identity(set_data)
        except Exception as e:
            log.error("[%d/%d] %s: load failed: %s. Skipping.", i, total, set_id, e)
            failures.append((set_id, f"load: {e}"))
            continue

        sets_upserted += 1
        cards_upserted += stats["cards_upserted"]
        duplicates_skipped += stats["duplicates_skipped"]
        malformed_skipped += stats["malformed_skipped"]
        if set_id not in known_set_ids:
            new_sets.append(f"{set_id} ({set_data.get('name')})")

        log.info(
            "[%d/%d] %s: %d card identities upserted.",
            i, total, set_id, stats["cards_upserted"],
        )

    _report(
        total=total,
        sets_upserted=sets_upserted,
        sets_excluded=sets_excluded,
        cards_upserted=cards_upserted,
        duplicates_skipped=duplicates_skipped,
        malformed_skipped=malformed_skipped,
        new_sets=new_sets,
        failures=failures,
    )


def _report(
    total: int,
    sets_upserted: int,
    sets_excluded: int,
    cards_upserted: int,
    duplicates_skipped: int,
    malformed_skipped: int,
    new_sets: list[str],
    failures: list[tuple[str, str]],
) -> None:
    """Log the run summary and hand it to GitHub Actions."""
    # A single transient 502 out of 218 sets is a warning, not a failed run.
    # Only a run that wrote nothing at all counts as failed.
    if sets_upserted == 0:
        status = "Failed"
    elif failures or duplicates_skipped or malformed_skipped:
        status = "Warnings"
    else:
        status = "Success"

    if new_sets:
        listed = new_sets[:MAX_NEW_SETS_LISTED]
        new_section = "\n".join(f"  {s}" for s in listed)
        if len(new_sets) > MAX_NEW_SETS_LISTED:
            new_section += f"\n  ... and {len(new_sets) - MAX_NEW_SETS_LISTED} more"
    else:
        new_section = "  (none)"

    failure_section = (
        "\n".join(f"  {set_id} -- {reason}" for set_id, reason in failures)
        if failures else "  (none)"
    )

    # Deliberately no per-set breakdown. The price run prints one line per
    # set, which is readable for four sets and useless for two hundred.
    sep = "=" * 45
    summary = (
        f"\n{sep}\n"
        f"TCGdex catalogue ingest complete\n"
        f"  Sets published : {total}\n"
        f"  Sets upserted  : {sets_upserted}\n"
        f"  Sets excluded  : {sets_excluded} (digital-only series)\n"
        f"  Sets failed    : {len(failures)}\n"
        f"  Cards upserted : {cards_upserted}\n"
        f"  Cards skipped  : {duplicates_skipped + malformed_skipped} "
        f"(duplicate {duplicates_skipped}, malformed {malformed_skipped})\n"
        f"  Overall status : {status}\n"
        f"\nNew sets since last run:\n{new_section}\n"
        f"\nFailed sets:\n{failure_section}\n"
        f"{sep}"
    )
    log.info("%s", summary)
    _write_summary(status=status, summary=summary)


def _write_summary(status: str, summary: str) -> None:
    """
    Write the catalogue status to the GitHub Actions environment file.

    A no-op locally, where GITHUB_ENV is not set. The nightly workflow reads
    these two into the summary email.
    """
    github_env = os.environ.get("GITHUB_ENV")
    if github_env:
        with open(github_env, "a", encoding="utf-8") as f:
            f.write(f"CATALOGUE_STATUS={status}\n")
            f.write(f"CATALOGUE_SUMMARY<<EOF\n{summary}\nEOF\n")


if __name__ == "__main__":
    main()
