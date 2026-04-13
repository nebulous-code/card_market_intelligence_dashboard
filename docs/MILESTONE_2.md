# Milestone 2 — Real Market Pricing

This document covers the technical structure for Milestone 2. The goal is to introduce real market pricing data via the PokemonPriceTracker API, establish a scheduled ingestion pipeline that grows automatically with the database, and surface price history in the dashboard through a new card detail page.

---

## Goals

- Integrate the PokemonPriceTracker API as the sole pricing data source
- Implement daily price snapshot ingestion for all sets in the database, automatically expanding as new sets are added
- Build a watermark system to track ingestion progress and handle rate limit interruptions gracefully
- Expose price history through a new API endpoint
- Add a card detail page and price history chart to the Vue frontend

---

## What Changed from the Original Plan

The original Milestone 2 design was built around eBay completed sales data, which required a card identity matching system, title parsing, confidence scoring, and variant detection from free-form listing text. The eBay Finding API has since been decommissioned and access to sold listing data is now restricted to approved partners only.

PokemonPriceTracker replaces eBay as the pricing source. It aggregates TCGPlayer market prices and eBay graded sale data and exposes it through a clean REST API. Because the data comes back structured and keyed to card IDs already in our database, the matching layer is no longer needed. Milestone 2 is simpler and more focused as a result.

---

## PokemonPriceTracker Integration

### Tier Strategy

The ingestion script is designed to work on both the free tier (100 credits/day) and the API tier ($9.99/month, 20,000 credits/day) with behavior controlled entirely by environment variables. No code changes are required to switch tiers — only the API key and feature flags need to change.

On the free tier, daily snapshots of current prices are ingested for as many cards as the credit limit allows, rotating through sets across days. On the API tier, a one-time backfill pulls 6 months of price history per set using `includeHistory=true&days=180`, after which daily runs revert to current-price-only snapshots that accumulate naturally in Neon over time.

See `docs/POKEMON_PRICE_TRACKER_API.md` for full endpoint documentation, parameter reference, and schema mapping.

### Dynamic Set Coverage

The ingestion script queries the `sets` table at the start of each run and fetches prices for every set it finds. As new sets are added to the database in later milestones, pricing for those sets is automatically included in the next ingestion run without any script changes.

---

## Database Changes

### New Table — `ingestion_watermarks`

Tracks ingestion state per set per source. Allows the script to resume from where it left off if a run is interrupted by a rate limit or other failure.

| Column | Type | Notes |
|---|---|---|
| `id` | SERIAL | Primary key |
| `source` | TEXT | e.g. `pokemonpricetracker` |
| `set_id` | TEXT | FK → `sets.id` |
| `last_ingested_at` | TIMESTAMP | When this set was last successfully ingested |
| `backfilled` | BOOLEAN | Whether the historical backfill has been completed for this set |
| `updated_at` | TIMESTAMP | When this row was last updated |

### Changes to `price_snapshots`

No new columns are required. The existing `source` and `condition` fields handle both raw TCGPlayer prices and eBay graded prices cleanly:

| Field | Raw card row | Graded card row |
|---|---|---|
| `source` | `tcgplayer` | `psa`, `bgs`, `cgc` |
| `condition` | `NM`, `LP`, `MP`, etc. | `PSA-10`, `BGS-9.5`, etc. |

Graded prices returned from the API when `includeEbay=true` are stored as separate rows alongside the raw TCGPlayer prices for the same card.

---

## New API Endpoint

| Method | Endpoint | Description |
|---|---|---|
| GET | `/cards/{card_id}/price-history` | Returns all price snapshots for a card ordered by date, filterable by source and condition |

---

## Frontend Changes

### Card Detail Page — `/cards/{card_id}`

A new route accessible via a **Details** button on the far right column of the existing card table. A back button returns the user to the dashboard.

The card detail page includes:

- Card image, name, set, number, rarity, and supertype
- A price history line chart filterable by condition and source
- A data table of individual price snapshots with date, source, condition, and price

---

## GitHub Actions — Scheduled Ingestion

A workflow file at `.github/workflows/ingest.yml` runs nightly at 2:00 AM US Eastern (07:00 UTC). It checks out the repository, sets up Python, installs dependencies, and runs the ingestion script. The PokemonPriceTracker API key is stored as a GitHub Actions secret and also documented in `.env.example` for local runs.

---

## Repository Changes

### New Files

```
ingestion/
    pokemonpricetracker.py    # PokemonPriceTracker API client
    watermark.py              # Watermark read/write logic

.github/
    workflows/
        ingest.yml            # Scheduled nightly ingestion workflow
```

### Modified Files

```
ingestion/
    run.py                    # Updated to orchestrate PPT pull across all sets
    loader.py                 # Updated to write price snapshots from PPT response

api/
    routers/
        cards.py              # New price-history endpoint added
    schemas/
        card.py               # New response schema for price history

api/models/
    watermark.py              # New model for ingestion_watermarks

.env.example                  # PPT API key and tier flags added
```
