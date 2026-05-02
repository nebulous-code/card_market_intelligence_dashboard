# M03_S09 — Enhance Price Snapshot Ingestion

## Summary

Update the price snapshot ingestion pipeline to capture the full richness of data returned by the PokemonPriceTracker API. The current loader writes a single `NM` row per card using only `prices.market`. The PPT API actually returns condition-specific and variant-specific price history — this story updates the schema and loader to capture all of it.

---

## Background

The PPT API response for a card with `includeHistory=true` contains a nested `priceHistory` structure broken out by variant and condition:

```json
"priceHistory": {
  "variants": {
    "Holofoil": {
      "Near Mint": {
        "history": [
          { "date": "2025-10-17T00:00:00.000Z", "market": 62.32, "volume": null },
          ...
        ],
        "dataPoints": 26,
        "latestPrice": 62.32
      },
      "Lightly Played": { ... },
      "Moderately Played": { ... },
      "Heavily Played": { ... },
      "Damaged": { ... }
    },
    "1st Edition Holofoil": {
      "Moderately Played": { ... }
    }
  },
  "conditions_tracked": ["Lightly Played", "Heavily Played", "Damaged", "Near Mint", "Moderately Played"],
  "variants_tracked": ["Holofoil", "1st Edition Holofoil"],
  "totalDataPoints": 776,
  "earliestDate": "2025-01-27T00:00:00.000Z",
  "latestDate": "2026-04-15T00:00:00.000Z"
}
```

Each variant/condition combination has its own `history` array of dated price points. This means condition-specific pricing (LP, MP, HP, DMG) is available without any additional API calls — it was always in the response, just not being read.

1st Edition variants are already pre-separated by PPT — no title parsing or variant detection is needed for this data source.

---

## Database Changes

### Add `variant` column to `price_snapshots`

```sql
ALTER TABLE price_snapshots
ADD COLUMN variant TEXT;
```

This column stores the PPT variant string after normalization (see Variant Normalization below). Null for cards where no variant distinction exists.

The `condition` column already exists and continues to store the normalized condition abbreviation. Both columns together uniquely identify a price tier for a card.

### Updated unique constraint

The existing unique constraint on `price_snapshots` is `(card_id, source, condition, captured_date)`. With the addition of `variant` this must be updated to prevent duplicate rows when the same card has multiple variants:

```sql
-- Drop existing constraint (name may differ — check schema)
ALTER TABLE price_snapshots DROP CONSTRAINT IF EXISTS price_snapshots_card_id_source_condition_captured_date_key;

-- Add updated constraint including variant
ALTER TABLE price_snapshots
ADD CONSTRAINT price_snapshots_unique_snapshot
UNIQUE (card_id, source, condition, variant, captured_date);
```

### Alembic migration

Create a new Alembic migration that:
1. Adds the `variant` column to `price_snapshots`
2. Drops the old unique constraint
3. Adds the new unique constraint including `variant`

The migration must be reversible.

---

## Condition Normalization

PPT returns full English condition names. These must be mapped to the abbreviated vocabulary used throughout the rest of the application before writing to the database.

Add the following mapping to `ingestion/loader.py`:

```python
CONDITION_MAP = {
    "Near Mint":          "NM",
    "Lightly Played":     "LP",
    "Moderately Played":  "MP",
    "Heavily Played":     "HP",
    "Damaged":            "DMG",
}
```

Any condition string not in this map should be stored as-is with a `WARNING` log message so it is not silently lost.

---

## Variant Normalization

PPT variant strings should be stored in a normalized form. Add the following mapping:

```python
VARIANT_MAP = {
    "Holofoil":              "holofoil",
    "1st Edition Holofoil":  "1st_edition_holofoil",
    "Reverse Holofoil":      "reverse_holofoil",
    "Normal":                None,   # No variant — store as null
    "1st Edition Normal":    "1st_edition_normal",
}
```

`None` as a mapped value means the variant column is stored as `NULL` — standard non-variant printings do not need a variant label.

Any variant string not in this map should be stored as-is (lowercased, spaces replaced with underscores) with a `WARNING` log message.

---

## Changes to `loader.py`

### Replace `_build_snapshot_rows`

The existing function reads only `prices.market`, `prices.low`, and `prices.high` and writes a single `NM` row. Replace it entirely with a new implementation that iterates the `priceHistory.variants` structure.

**New behavior:**

For each card returned by PPT:

1. Read `card.get("priceHistory", {}).get("variants", {})`
2. For each variant key (e.g. `"Holofoil"`, `"1st Edition Holofoil"`):
   - Normalize the variant using `VARIANT_MAP`
   - For each condition key within that variant (e.g. `"Near Mint"`, `"Lightly Played"`):
     - Normalize the condition using `CONDITION_MAP`
     - Read the `history` array
     - For each history point `{"date": ..., "market": ..., "volume": ...}`:
       - Build one snapshot row with `captured_date` set to the history point's date
3. Also write the **current price** as a snapshot row using `captured_date = TODAY` for each variant/condition combination found in `prices.variants` — this ensures the most recent price is always written even if `includeHistory` is false

**Snapshot row structure:**

```python
{
    "card_id":       card_id,
    "source":        "tcgplayer",
    "condition":     normalized_condition,   # "NM", "LP", etc.
    "variant":       normalized_variant,     # "holofoil", "1st_edition_holofoil", or None
    "market_price":  history_point["market"],
    "low_price":     None,                   # not available in history points
    "high_price":    None,                   # not available in history points
    "captured_date": date_from_history_point,
}
```

For current price rows (not from history), read `low` from `prices.variants.{variant}.{condition}.price` where available.

### Idempotency

The `ON CONFLICT` clause on the INSERT must include `variant` to match the new unique constraint:

```sql
INSERT INTO price_snapshots
    (card_id, source, condition, variant, market_price, low_price, high_price, captured_at, captured_date)
VALUES
    (:card_id, :source, :condition, :variant, :market_price, :low_price, :high_price, NOW(), :captured_date)
ON CONFLICT (card_id, source, condition, variant, captured_date) DO UPDATE SET
    market_price = EXCLUDED.market_price,
    low_price    = EXCLUDED.low_price,
    high_price   = EXCLUDED.high_price,
    captured_at  = EXCLUDED.captured_at
```

### Logging updates

Update the per-card success log to include variant and condition counts:

```
[base1] MATCHED: 'Alakazam' PPT#1 → base1-1 | 2 variants, 5 conditions, 776 history points
```

If `priceHistory` is absent or empty on a matched card, log a WARNING:

```
[base1] WARNING: 'Alakazam' matched base1-1 but priceHistory is empty — current price only written
```

---

## Backfill Consideration

Existing `price_snapshots` rows written before this story have `variant = NULL` and `condition = 'NM'`. These rows are not wrong — they represent the market price at the time of ingestion. They do not need to be deleted or corrected.

After this story is deployed the next ingestion run will write new rows with proper variant and condition data for the same dates. The unique constraint includes `variant` so the new rows (with variant set) will not conflict with the old rows (with variant NULL).

Over time the old NULL-variant rows will become a minority of the dataset and can be excluded from analysis by filtering `WHERE variant IS NOT NULL` or left in as historical context.

---

## API Changes

### `GET /cards/{card_id}` — Update latest prices response

The card detail endpoint currently returns the latest price snapshot per condition. With the addition of `variant` the deduplication logic must be updated to return the latest snapshot per `(condition, variant)` combination rather than per `condition` alone.

Update `routers/cards.py`:

```python
# Old — deduplicate by condition only
seen: set[str] = set()
for snap in card.price_snapshots:
    if snap.condition not in seen:
        seen.add(snap.condition)
        latest_prices.append(snap)

# New — deduplicate by (condition, variant) pair
seen: set[tuple] = set()
for snap in card.price_snapshots:
    key = (snap.condition, snap.variant)
    if key not in seen:
        seen.add(key)
        latest_prices.append(snap)
```

### `GET /cards/{card_id}/price-history` — Update to accept variant filter

Add an optional `variant` query parameter so the frontend can request history for a specific variant:

```
GET /cards/base1-1/price-history?condition=NM&variant=holofoil
GET /cards/base1-1/price-history?condition=NM&variant=1st_edition_holofoil
```

If `variant` is omitted, return all variants.

### Pydantic schema updates

Update `PriceSnapshotResponse` in `schemas/card.py` to include the `variant` field:

```python
class PriceSnapshotResponse(BaseModel):
    id:           int
    card_id:      str
    source:       str
    condition:    str
    variant:      str | None
    market_price: Decimal | None
    low_price:    Decimal | None
    high_price:   Decimal | None
    captured_at:  datetime
    captured_date: date
```

---

## Frontend Changes

### Card Detail — Price history chart

Update the price history chart on the card detail page to add a variant filter alongside the existing condition filter. A user should be able to select both a condition and a variant to see that specific price series.

The variant filter should only show variants that exist in the data for that card — do not show `1st Edition Holofoil` if no such snapshots exist.

Default selection: `holofoil` + `NM` if available, otherwise the first available combination.

---

## Test Cases

---

### TC01 — `variant` column exists in `price_snapshots`

**Steps:**
```sql
SELECT column_name, data_type
FROM information_schema.columns
WHERE table_name = 'price_snapshots'
AND column_name = 'variant';
```

**Expected:** One row returned with `data_type = 'text'`.

---

### TC02 — Unique constraint includes variant

**Steps:**
```sql
SELECT constraint_name, constraint_type
FROM information_schema.table_constraints
WHERE table_name = 'price_snapshots'
AND constraint_type = 'UNIQUE';
```

**Expected:** A unique constraint exists that covers `(card_id, source, condition, variant, captured_date)`.

---

### TC03 — Condition normalization

**Steps:** Run ingestion for Base Set. Then:
```sql
SELECT DISTINCT condition FROM price_snapshots WHERE source = 'tcgplayer';
```

**Expected:** Values are abbreviated — `NM`, `LP`, `MP`, `HP`, `DMG`. No full English strings like `"Near Mint"` appear.

---

### TC04 — Variant normalization

**Steps:**
```sql
SELECT DISTINCT variant FROM price_snapshots WHERE source = 'tcgplayer';
```

**Expected:** Values are normalized — `holofoil`, `1st_edition_holofoil`, `reverse_holofoil`, or `NULL`. No raw PPT strings like `"1st Edition Holofoil"` appear.

---

### TC05 — Multiple conditions written per card

**Steps:**
```sql
SELECT condition, variant, COUNT(*) as snapshots
FROM price_snapshots
WHERE card_id = 'base1-1'
AND source = 'tcgplayer'
GROUP BY condition, variant
ORDER BY variant, condition;
```

**Expected:** Multiple rows — at minimum `NM/holofoil`, `LP/holofoil`, `MP/holofoil`, `HP/holofoil`, `DMG/holofoil`. If PPT has 1st Edition data, `NM/1st_edition_holofoil` etc. also appear.

---

### TC06 — Historic data points written per condition/variant

**Steps:**
```sql
SELECT condition, variant, COUNT(*) as data_points
FROM price_snapshots
WHERE card_id = 'base1-1'
AND source = 'tcgplayer'
GROUP BY condition, variant
ORDER BY data_points DESC;
```

**Expected:** Each condition/variant combination has multiple rows (one per historic date point). The count should roughly match the `dataPoints` value in the PPT API response for that combination.

---

### TC07 — Ingestion is idempotent with new schema

**Steps:**
1. Run ingestion for Base Set
2. Note the row count: `SELECT COUNT(*) FROM price_snapshots WHERE card_id = 'base1-1';`
3. Run ingestion again
4. Check row count again

**Expected:** Row count is identical after both runs. No duplicate rows created.

---

### TC08 — Old NULL-variant rows coexist with new rows

**Steps:**
```sql
SELECT
    SUM(CASE WHEN variant IS NULL THEN 1 ELSE 0 END) as old_rows,
    SUM(CASE WHEN variant IS NOT NULL THEN 1 ELSE 0 END) as new_rows
FROM price_snapshots
WHERE card_id = 'base1-1';
```

**Expected:** Both counts are non-zero after the first post-migration ingestion run. Old rows with `variant = NULL` are preserved alongside new rows with variant values.

---

### TC09 — Card detail API returns variant in response

**Steps:**
```
GET /cards/base1-1
```

**Expected:** The `latest_prices` array contains multiple entries — one per `(condition, variant)` combination. Each entry includes a `variant` field. Example: two `NM` entries if both `holofoil` and `1st_edition_holofoil` exist.

---

### TC10 — Price history endpoint filters by variant

**Steps:**
```
GET /cards/base1-1/price-history?condition=NM&variant=holofoil
GET /cards/base1-1/price-history?condition=NM&variant=1st_edition_holofoil
```

**Expected:** Each request returns only snapshots matching the requested variant. The two responses contain different data sets.

---

### TC11 — Card detail frontend shows variant filter

**Steps:** Open the card detail page for a card that has both `holofoil` and `1st_edition_holofoil` data.

**Expected:** A variant filter appears alongside the condition filter. Selecting `1st Edition Holofoil` updates the price history chart to show only that variant's data.

---

### TC12 — Unknown condition logged as warning

**Steps:** Temporarily add an unknown condition key to the `_build_snapshot_rows` function (e.g. `"Excellent"`) and run ingestion.

**Expected:** A `WARNING` log message appears noting the unrecognized condition. The value is stored as-is rather than being silently dropped. Restore the function after verifying.
