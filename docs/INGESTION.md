# Ingestion

End-to-end reference for getting card metadata and pricing data into the
database. The pipeline is two passes -- TCGdex for set/card structure,
then PokemonPriceTracker (PPT) for prices -- run independently.

This is the runbook for adding a new set, refreshing prices, and reacting
to unrecognized values in the run summary. Pattern follows the M03_S05
playbook that worked for adding Jungle / Fossil / 151.

---

## Prerequisites

Before any ingestion command, confirm:

- **`.env` exists at the repo root** with at minimum:
  ```
  DATABASE_URL=postgresql://...                  # dev (Neon)
  DATABASE_URL_PROD=postgresql://...             # prod (Neon)
  POKEMON_PRICE_TRACKER_API_KEY=...
  PPT_INCLUDE_HISTORY=true                       # API tier only
  PPT_HISTORY_DAYS=180                           # API tier only
  PPT_INCLUDE_EBAY=true                          # API tier only
  PPT_OUTPUT_DIR=./ingestion/api_output          # only for the *.ps1 explorers
  ```
- **Schema is up to date.** The API runs `alembic upgrade head` on startup;
  if you have not started the API since pulling the latest migrations:
  ```bash
  cd api && uv run alembic upgrade head
  ```
- **`uv` is installed** (the ingestion + API both use `uv run`).
- **`psql` is installed** for the connect-and-poke flow. Use the helpers:
  ```bash
  ./psql_launcher.sh d   # dev
  ./psql_launcher.sh p   # prod
  ```
  (PowerShell equivalent: `./psql_launcher.ps1 d`.)

---

## Script inventory

| Script | What it does | When to use |
|---|---|---|
| `ingestion/run_ingest.sh <set-id> [--new-set]` | Pull set + cards from TCGdex into the `sets` and `cards` tables. | Adding a new set, refreshing card metadata. |
| `ingestion/run_prices.sh` | Pull prices from PPT for every set in the DB and write `price_snapshots`. Resumes via watermarks. | Daily/nightly price refresh. |
| `ingestion/tcgdex_api_get_set.ps1` | Search TCGdex by name, print matching set IDs. No API key needed. | Confirming a TCGdex set ID before adding a set. |
| `ingestion/ppt_api_get_set.ps1` | Search PPT by name, print matching set names. | Confirming the exact display name PPT uses for a set. |
| `ingestion/fetch_historic_data.ps1` | One-off: fetch a single card's full price history and save the JSON. | Debugging history-shape issues. |

The `*.sh` scripts are the primary path on Mac/Linux; `*.ps1` exists for
Windows (and the `*api_get_set.ps1` files are Windows-only exploration
tools). Behavior is identical between the two on the run-ingest side.

---

## Adding a new set

Step-by-step. Everything is idempotent -- safe to re-run any step.

### 1. Confirm the TCGdex set ID

Browse:

```
https://api.tcgdex.net/v2/en/sets
```

…or run the helper (Windows):

```powershell
./ingestion/tcgdex_api_get_set.ps1 -SearchTerm "Jungle"
```

Note the `id` field -- e.g. `base2`, `sv03.5`. This is the canonical set
ID stored in `sets.id` and used as `set_id` in every other table.

### 2. Confirm the PPT display name

PPT does not use TCGdex IDs -- it matches on its own display name. Find it via:

```powershell
./ingestion/ppt_api_get_set.ps1 -SearchTerm "Jungle"
```

…or hit the PPT `/api/v2/sets` endpoint directly with your bearer key.
Record the exact `name` PPT returns -- e.g. `"Jungle"`, `"SV: Scarlet & Violet 151"`.

### 3. Insert into `set_identifiers`

The ingestion pipeline always resolves the per-source name through this
table rather than hardcoding it. Three rows per set (TCGdex id, TCGdex
name, PPT name):

```sql
INSERT INTO set_identifiers (set_id, source, identifier, identifier_type) VALUES
    ('<tcgdex_id>', 'tcgdex', '<tcgdex_id>', 'id'),
    ('<tcgdex_id>', 'tcgdex', '<tcgdex_name>', 'name'),
    ('<tcgdex_id>', 'ppt',    '<ppt_name>',    'name');
```

Connect via `./psql_launcher.sh d` and run the insert.

### 4. Pull TCGdex set + cards

```bash
cd ingestion
./run_ingest.sh <tcgdex_id> --new-set    # first ingest of this set
./run_ingest.sh <tcgdex_id>              # subsequent refreshes
```

`--new-set` skips the `set_identifiers` resolver (the row may not be in
the table yet on first run -- after step 3 it will be). On every re-run
without the flag, the resolver verifies the mapping exists.

Verify:

```sql
SELECT id, name, printed_total FROM sets WHERE id = '<tcgdex_id>';
SELECT COUNT(*) FROM cards WHERE set_id = '<tcgdex_id>';
```

The card count should match (or modestly exceed) `printed_total` -- modern
sets include secret rares with numbers above the printed total.

### 5. Pull PPT prices

```bash
cd ingestion
./run_prices.sh
```

The script discovers every set in the DB and processes them in
release-date order, oldest first. Watermarks resume mid-set if a previous
run hit the daily credit cap.

Cost on the API tier with both `PPT_INCLUDE_HISTORY=true` and
`PPT_INCLUDE_EBAY=true`: **3 credits per card** (1 base + 1 history + 1
ebay). With 180-day history, expect ~900 snapshot rows per card on the
first ingest.

Verify per-set:

```sql
SELECT c.set_id, COUNT(ps.id) AS snapshot_count, MIN(captured_date), MAX(captured_date)
FROM price_snapshots ps
JOIN cards c ON ps.card_id = c.id
GROUP BY c.set_id
ORDER BY c.set_id;
```

### 6. Sanity-check the run summary

The script prints a per-set summary plus a run-level summary at the end.
Look at:

- **Per-set "Skipped cards"** -- cards PPT returned that didn't match a
  card in our DB. Code Cards / ETB exclusives skipping is normal. A real
  card skipping means the card-number normalization is misaligned -- see
  Troubleshooting below.
- **Run-level "Unrecognized values"** -- raw condition/variant strings
  PPT sent that aren't in our alias tables. Each entry comes with a
  copy-paste `INSERT INTO …_aliases (…)` snippet. See the next section.

---

## Reacting to "Unrecognized values"

Three alias tables drive the canonical normalization:

| Table | Used by | What it normalizes |
|---|---|---|
| `condition_aliases` | `run_prices.sh` (PPT loader) | Raw PPT condition strings (e.g. "Near Mint Unlimited Holofoil") |
| `variant_aliases` | `run_prices.sh` (PPT loader) | Raw PPT variant strings (e.g. "1st Edition Holofoil") |
| `rarity_aliases` | `run_ingest.sh` (TCGdex loader) | Raw TCGdex rarity strings (e.g. "Hyper rare") |

Strict mode skips any price row whose condition or variant isn't in the
alias tables -- this prevents dirty data accumulating but means new PPT
spellings come through as zero rows until you add the mapping. Cards
ingested with an unrecognized rarity are stored with `rarity=NULL` and
the unknown is logged so the alias can be added and the set re-ingested.

**Workflow when an unknown shows up:**

1. Look at the run-summary section. It prints something like:
   ```
   Unrecognized values (rows skipped, add aliases to capture):
     [variant] 'Holographic Promo'  (47 rows skipped)
        INSERT INTO variant_aliases (raw_value, canonical_value)
        VALUES ($$Holographic Promo$$, '<choose canonical>');
   ```
2. Decide which canonical value the raw string should map onto. Check
   `canonical_conditions.value` / `canonical_variants.value`:
   ```sql
   SELECT value, display_label FROM canonical_conditions ORDER BY display_order;
   SELECT value, display_label FROM canonical_variants   ORDER BY display_order;
   ```
3. If a suitable canonical exists, edit the snippet to fill in the
   canonical and run it. If you genuinely need a new canonical (e.g.
   PPT introduces a brand-new printing kind), insert it first:
   ```sql
   INSERT INTO canonical_variants (value, display_label, display_order)
   VALUES ('promo_holo', 'Promo Holo', 70);
   ```
   …then add the alias row referencing it.
4. Re-run `./run_prices.sh`. Subsequent runs pick up the new mapping
   without a code change or a deploy.

The same pattern applies to graded conditions (PSA-10, BGS-9.5, etc.) --
they go through `condition_aliases` too, so a new grading service or
rare grade tier is a SQL insert away.

---

## Daily price refresh (nightly)

Production runs via GitHub Actions (`.github/workflows/ingest.yml`).
Locally, the equivalent is just:

```bash
cd ingestion && ./run_prices.sh
```

Notes:

- **Credit budget**: ~3 credits/card with history+ebay. A nightly refresh
  of the full set library re-fetches the ~180-day window, so most days
  the inserts collapse onto existing rows via `ON CONFLICT DO UPDATE`.
- **Watermarks**: stored in `ingestion_watermarks(source, set_id)`. They
  track pagination offset only (the `backfilled` flag was removed); a
  partial run resumes from where it stopped.
- **Idempotency**: the unique constraint on `price_snapshots` is
  `(card_id, source, condition, variant, captured_date)` with
  `NULLS NOT DISTINCT`. Re-running on the same day updates the existing
  row rather than appending.

---

## Backfill considerations

- **First ingest of a set with `PPT_INCLUDE_HISTORY=true`** writes ~900
  rows per card (~178 history points × variants × conditions plus
  latest-price + eBay rows). For Base Set (102 cards) that's ~90,000
  rows; for 151 (~165 cards plus secret rares) closer to ~180,000.
- The bulk-insert path in `loader.py` collapses each card into one
  multi-row `INSERT` statement, so the wall-clock time is dominated by
  HTTP fetch latency, not DB writes.
- **Old single-NM rows** written before the variant column existed are
  preserved (variant=NULL). They sit alongside new variant-bearing rows
  thanks to `NULLS NOT DISTINCT`.

---

## Troubleshooting

**Every card in a set logs "no match"**
The `cards.number` column for that set is stored in a different format
than PPT's `cardNumber`. The loader normalizes both sides via
`lstrip("0")`, so this should be rare; if it happens, check the actual
shape of `cards.number` for the affected set:

```sql
SELECT number, name FROM cards WHERE set_id = '<id>' ORDER BY number LIMIT 10;
```

**Run goes silent mid-set, no completion summary**
Most likely cause historically: an uncaught exception during the
`set_watermark` write after the set finished inserting. Check
`ingestion/ingestion.log` for a Python traceback. The strict-mode
unknowns reporting fires only after the per-set transaction commits, so
a crash before that point looks like silence.

**FK violation on `price_snapshots` insert**
A PPT condition/variant slipped through that is not in the alias tables
**and** somehow bypassed strict-mode. Should not happen with current
code, but the FK is a hard backstop -- the run will surface the offending
value in the traceback. Add the missing alias and re-run.

**Daily credit limit hit**
The script logs the current `X-RateLimit-Daily-Remaining` after every
page. When it drops below the safety threshold the script stops
processing new sets and exits cleanly; tomorrow's run picks up where
this one stopped via the watermark.

---

## Reference: directory layout

```
ingestion/
├── run.py               -- price ingestion entry point (called by run_prices.sh)
├── run_ingest.py        -- card/set ingestion entry point (called by run_ingest.sh)
├── loader.py            -- DB writes (upsert, snapshots, alias-driven normalization)
├── pokemonpricetracker.py -- HTTP client + pagination + rate-limit handling
├── tcgdex.py            -- HTTP client for TCGdex
├── set_resolver.py      -- set_identifiers lookups
├── watermark.py         -- ingestion_watermarks read/write
├── logging_setup.py     -- shared logging config (writes to ingestion.log)
├── run_prices.sh / .ps1 -- shell wrapper for run.py
├── run_ingest.sh / .ps1 -- shell wrapper for run_ingest.py
├── *_api_get_set.ps1    -- exploratory: search TCGdex / PPT for a set
└── fetch_historic_data.ps1 -- one-off: full history JSON for a single card
```
