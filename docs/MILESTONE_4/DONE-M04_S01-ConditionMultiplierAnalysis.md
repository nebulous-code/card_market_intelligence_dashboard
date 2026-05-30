# M04_S01 — Condition Multiplier Analysis

## Summary

Build a data analysis feature that calculates average price ratios between card conditions (NM, LP, MP, HP, DMG) using 6 months of historical price data. Aggregations are computed per set, broken down by rarity and supertype. Results are stored in a new `condition_multipliers` table refreshed nightly via the existing GitHub Actions ingestion pipeline. The data is surfaced under the Market Trends page as an interactive heatmap visualization and serves as the inferential fallback for the Excel collection workbook in later stories.

---

## Why This Exists

Most card pricing tools either use fixed industry multipliers (e.g. "LP is always 70% of NM") or skip cards with sparse condition data entirely. This feature builds multipliers from real observed price ratios in the database — per set, rarity, and supertype — which is novel in the TCG space and produces more accurate inference than fixed multipliers.

The output serves two purposes:

1. **Web feature** — interactive heatmap on the Market Trends page showing how price drops across the condition ladder for each rarity and supertype within a set
2. **Data pipeline output** — the `condition_multipliers` table is consumed by the Excel collection workbook (M04_S04) as a fallback when a user owns a card with sparse condition pricing

---

## Database Changes

### New Table — `condition_multipliers`

```sql
CREATE TABLE condition_multipliers (
    id              SERIAL PRIMARY KEY,
    set_id          TEXT NOT NULL REFERENCES sets(id) ON DELETE CASCADE,
    grouping_type   TEXT NOT NULL,         -- 'rarity' or 'supertype'
    grouping_value  TEXT NOT NULL,         -- e.g. 'Rare Holo', 'Pokémon'
    from_condition  TEXT NOT NULL,         -- 'NM', 'LP', 'MP', 'HP'
    to_condition    TEXT NOT NULL,         -- 'LP', 'MP', 'HP', 'DMG'
    multiplier      NUMERIC(5,4) NOT NULL, -- e.g. 0.6800
    data_points     INT NOT NULL,          -- number of card-month observations used
    last_refreshed  TIMESTAMP NOT NULL DEFAULT NOW(),
    UNIQUE (set_id, grouping_type, grouping_value, from_condition, to_condition)
);

CREATE INDEX idx_condition_multipliers_set ON condition_multipliers (set_id);
CREATE INDEX idx_condition_multipliers_lookup ON condition_multipliers (set_id, grouping_type, grouping_value);
```

The `multiplier` column uses `NUMERIC(5,4)` to allow values like `0.6843` — four decimal places of precision, capped at 9.9999.

### Alembic migration

Create a reversible Alembic migration that creates the table and indexes.

---

## Stored Procedure — `refresh_condition_multipliers`

A PostgreSQL stored procedure that rebuilds the `condition_multipliers` table from current `price_snapshots` data. Called nightly by the GitHub Actions ingestion workflow.

### Signature

```sql
CREATE OR REPLACE PROCEDURE refresh_condition_multipliers()
LANGUAGE plpgsql
AS $$
...
$$;
```

No parameters — operates on all sets present in the database.

### Algorithm

For each set in the `sets` table:

1. **Identify relevant snapshots** — pull all rows from `price_snapshots` for cards in this set where:
   - `source = 'tcgplayer'`
   - `variant IS NULL` (raw cards only — graded and variant cards are excluded as discussed)
   - `captured_date >= NOW() - INTERVAL '6 months'`
   - `market_price IS NOT NULL`

2. **Aggregate to monthly average per card per condition** — for each (card_id, condition) pair, calculate the average market_price per calendar month over the 6-month window. This smooths out outliers without requiring an arbitrary minimum threshold.

3. **Compute pairwise ratios per card per month** — for each card and each month where both `from_condition` and `to_condition` have a price, calculate `to_condition_price / from_condition_price`.

4. **Aggregate ratios by grouping** — for each (set, grouping_type, grouping_value, from_condition, to_condition) combination, calculate:
   - Average ratio across all card-month observations
   - Count of observations (this becomes `data_points`)

5. **Two grouping types are written** — once with `grouping_type = 'rarity'` (using `cards.rarity` as the grouping value), once with `grouping_type = 'supertype'` (using `cards.supertype` as the grouping value).

6. **Replace the table contents** — for each set processed, delete existing rows for that set in `condition_multipliers`, then insert the new ones. This is done set-by-set so a partial failure doesn't wipe the entire table.

### Condition pairs to compute

All forward transitions on the condition ladder:

| From | To |
|---|---|
| NM | LP, MP, HP, DMG |
| LP | MP, HP, DMG |
| MP | HP, DMG |
| HP | DMG |

Backward transitions (e.g. LP→NM) are not computed — multipliers are intentionally one-directional, representing the discount applied as a card degrades.

### Logging

The procedure should log progress using `RAISE NOTICE`. At minimum log:
- Start of refresh with timestamp
- Per-set: how many rows were written
- Total rows written across all sets
- Completion timestamp

This output appears in the GitHub Actions log and the nightly email summary.

---

## GitHub Actions Integration

Add a new step to `.github/workflows/ingest.yml` that runs after the price snapshot ingestion completes successfully:

```yaml
- name: Refresh condition multipliers
  if: success()
  env:
    DATABASE_URL: ${{ secrets.DATABASE_URL }}
  run: |
    python -c "
    import os
    from sqlalchemy import create_engine, text
    engine = create_engine(os.environ['DATABASE_URL'])
    with engine.begin() as conn:
        conn.execute(text('CALL refresh_condition_multipliers()'))
    print('Condition multipliers refreshed')
    "
```

The step uses `if: success()` because there is no point refreshing multipliers if the snapshot ingestion failed — the data didn't change.

The email summary should include a line confirming whether the multiplier refresh ran and how many rows were written.

---

## API Changes

### New Endpoint — `GET /trends/condition-multipliers`

Returns the condition multiplier data for the frontend heatmap.

**Query parameters:**

| Param | Type | Required | Notes |
|---|---|---|---|
| `set_id` | string | Yes | The canonical set ID (e.g. `base1`) |
| `grouping_type` | string | Yes | `rarity` or `supertype` |

**Response:**

```json
{
  "set_id": "base1",
  "set_display_name": "Base Set",
  "grouping_type": "rarity",
  "last_refreshed": "2026-04-15T07:00:00Z",
  "groupings": [
    {
      "grouping_value": "Rare Holo",
      "transitions": [
        { "from_condition": "NM", "to_condition": "LP",  "multiplier": 0.5800, "data_points": 23 },
        { "from_condition": "NM", "to_condition": "MP",  "multiplier": 0.3800, "data_points": 18 },
        { "from_condition": "NM", "to_condition": "HP",  "multiplier": 0.2200, "data_points": 9  },
        { "from_condition": "NM", "to_condition": "DMG", "multiplier": 0.1200, "data_points": 4  },
        { "from_condition": "LP", "to_condition": "MP",  "multiplier": 0.6500, "data_points": 16 },
        ...
      ]
    },
    {
      "grouping_value": "Rare",
      "transitions": [...]
    }
  ]
}
```

### New Endpoint — `GET /trends/sets-with-multipliers`

Returns the list of sets that have multiplier data available, used to populate the set selector chips on the frontend. A set appears in this list only if `condition_multipliers` has at least one row for that set.

```json
{
  "sets": [
    { "set_id": "base1",  "set_display_name": "Base Set" },
    { "set_id": "jungle", "set_display_name": "Jungle"   }
  ]
}
```

---

## Frontend Changes

### New Component — `ConditionMultiplierHeatmap.vue`

**Location:** `frontend/src/views/trends/ConditionMultiplierHeatmap.vue`
**Route:** `/trends/condition-multipliers`

A new sub-page under Market Trends. The Market Trends page (currently a placeholder from M03_S03) becomes a landing page that links to this and any future trend analyses. For Milestone 4 the Market Trends page can be a simple list with one card linking to the heatmap — additional trend analyses can be added in later milestones.

### Heatmap Layout

The visualization is a grid where:

- **Rows** are grouping values (rarity tiers like `Common`, `Uncommon`, `Rare`, `Rare Holo`, OR supertypes like `Pokémon`, `Trainer`, `Energy` depending on grouping toggle)
- **Columns** are condition steps along the ladder — `NM`, `LP`, `MP`, `HP`, `DMG`
- **Cells** show the multiplier from `NM` to that column's condition. Multipliers cascade — the displayed value is always the price ratio versus NM, regardless of where the cell sits on the ladder.

This means the heatmap reads left-to-right as a degradation curve. The leftmost column is always `1.00` (NM vs itself, shown in a muted style). Each subsequent column shows the cumulative multiplier from NM. So a row for Rare Holo might read:

| NM | LP | MP | HP | DMG |
|----|----|----|----|----|
| 1.00 | 0.58 | 0.38 | 0.22 | 0.12 |

**Important — the underlying data still includes all pairwise transitions (LP→MP, LP→HP, etc.).** Only the displayed view is simplified to the cascade. The full pairwise data is available in the API response and used by:
- The Excel workbook in M04_S04 (which needs LP→MP and similar transitions for upgrade calculations starting from non-NM conditions)
- Tooltips on the heatmap (see below)

### Cell Color Scale

Cells use a gradient from gold (close to 1.0, minimal discount) to red (close to 0.0, steep discount). Use the Magikarp palette:

| Multiplier range | Color |
|---|---|
| 0.90+ | Gold `rgba(245,200,66,0.85)` |
| 0.80–0.89 | Amber-gold `rgba(238,175,48,0.80)` |
| 0.70–0.79 | Orange `rgba(224,140,36,0.75)` |
| 0.60–0.69 | Red-orange `rgba(220,100,30,0.70)` |
| 0.50–0.59 | Magikarp red `rgba(220,70,28,0.65)` |
| 0.40–0.49 | Deeper red `rgba(210,50,25,0.60)` |
| 0.30–0.39 | Dark red `rgba(200,38,22,0.55)` |
| Below 0.30 | Darkest red `rgba(180,28,18,0.50)` |

The NM column (always 1.0) uses a muted/dashed surface style rather than the gold to visually anchor it as the reference point rather than implying it's "the best" value.

### Cell Tooltips

On hover, show:
- Grouping value (e.g. `Rare Holo`)
- The displayed transition (e.g. `NM → MP`)
- The displayed multiplier (e.g. `0.38`)
- Underlying data points for the displayed transition
- A small section showing all pairwise transitions ending at this column — useful when the user wants to see "if I have LP, what's the MP multiplier?" without switching views. Example for the MP column on a Rare Holo row:
  ```
  Cumulative from NM:  0.38  (18 data points)
  From LP:             0.65  (16 data points)
  ```

### Slicers / Controls

Three controls at the top of the page:

1. **Set selector** — chip group, populated from `GET /trends/sets-with-multipliers`. Single-select. Default to first available set alphabetically.
2. **Group by** — chip toggle: `Rarity` or `Supertype`. Single-select. Default to `Rarity`.

### Summary Cards Below the Heatmap

Four summary cards showing headline numbers for the selected set:

- **Avg LP / NM ratio** across all rarities (or supertypes depending on toggle)
- **Avg MP / NM ratio** across all rarities (or supertypes)
- **Steepest drop** — the grouping with the steepest NM→LP cliff. Show the grouping name and the multiplier. Useful for quickly answering "which cards lose value the fastest?"
- **Total data points** — sum of `data_points` across all displayed cells. Gives the user a sense of the statistical confidence behind the data.

### Empty State

If a set has no multiplier data yet (e.g. just ingested, less than 6 months of price history), show an `EmptyState` component with the message:

```
Not enough price data yet
Condition multipliers require at least 30 days of historical pricing.
This set will populate once enough data has been collected.
```

### Loading State

Use the existing `LoadingSkeleton` component while data loads.

---

## Test Cases

---

### TC01 — Stored procedure exists and is callable

**Steps:**
```sql
CALL refresh_condition_multipliers();
```

**Expected:** The procedure executes without error. NOTICE messages appear in the output showing per-set progress.

---

### TC02 — Table populated after first refresh

**Steps:** After running the procedure:
```sql
SELECT COUNT(*) FROM condition_multipliers;
SELECT DISTINCT set_id FROM condition_multipliers;
```

**Expected:** The first query returns a non-zero count. The second returns one row per set that had enough price data — at minimum Base Set should appear.

---

### TC03 — All forward condition pairs computed

**Steps:**
```sql
SELECT DISTINCT from_condition, to_condition
FROM condition_multipliers
WHERE set_id = 'base1' AND grouping_type = 'rarity'
ORDER BY from_condition, to_condition;
```

**Expected:** 10 distinct pairs covering all forward transitions on the condition ladder:
NM→LP, NM→MP, NM→HP, NM→DMG, LP→MP, LP→HP, LP→DMG, MP→HP, MP→DMG, HP→DMG.

---

### TC04 — Both grouping types present

**Steps:**
```sql
SELECT grouping_type, COUNT(*) AS rows
FROM condition_multipliers
WHERE set_id = 'base1'
GROUP BY grouping_type;
```

**Expected:** Two rows — one for `rarity`, one for `supertype`. Both have non-zero counts.

---

### TC05 — Multipliers are within reasonable range

**Steps:**
```sql
SELECT MIN(multiplier), MAX(multiplier), AVG(multiplier)
FROM condition_multipliers
WHERE from_condition = 'NM' AND to_condition = 'LP';
```

**Expected:** All values between 0 and 1. Average should be roughly in the range 0.55–0.85 — outside that range suggests a data quality issue worth investigating.

---

### TC06 — Variant rows excluded from calculation

**Steps:**
```sql
-- Verify that variant snapshots aren't influencing the calculation
WITH variant_check AS (
  SELECT card_id FROM price_snapshots
  WHERE variant IS NOT NULL AND source = 'tcgplayer'
  GROUP BY card_id
)
SELECT COUNT(*) FROM variant_check;
```

Then re-run the procedure and check that the multiplier values are unchanged from a baseline run.

**Expected:** Variant rows exist in `price_snapshots` but the multiplier results are calculated from non-variant rows only.

---

### TC07 — Refresh is idempotent

**Steps:**
1. Run the procedure
2. Note the row count and a sample multiplier value
3. Run the procedure again
4. Compare row count and the sample value

**Expected:** Row count is identical. Multiplier values may differ very slightly if new snapshots were ingested between runs but should be substantially the same.

---

### TC08 — GitHub Actions workflow runs the refresh

**Steps:** Trigger the nightly workflow manually from the GitHub Actions tab.

**Expected:** The workflow log shows the "Refresh condition multipliers" step running successfully. The email summary mentions the refresh completing.

---

### TC09 — `GET /trends/sets-with-multipliers` returns populated sets

**Steps:**
```
GET /trends/sets-with-multipliers
```

**Expected:** Returns a JSON array of sets that have at least one row in `condition_multipliers`. Sets without multiplier data are not included.

---

### TC10 — `GET /trends/condition-multipliers` returns full pairwise data

**Steps:**
```
GET /trends/condition-multipliers?set_id=base1&grouping_type=rarity
```

**Expected:** Returns groupings for every rarity present in Base Set. Each grouping's `transitions` array contains all 10 forward condition pairs (not just the cascade from NM).

---

### TC11 — Heatmap shows cascade from NM, not all pairs

**Steps:** Open the Market Trends → Condition Multipliers page for Base Set.

**Expected:** The visible heatmap has 5 columns — `NM`, `LP`, `MP`, `HP`, `DMG`. The NM column shows `1.00` in muted styling. Subsequent columns show the multiplier from NM (not from the previous column). The grid is not the noisy 10-column variant.

---

### TC12 — Hovering a cell shows pairwise transitions

**Steps:** Hover any non-NM cell on the heatmap.

**Expected:** A tooltip appears showing the cumulative multiplier from NM and at least one alternate pairwise transition (e.g. LP→that condition). All pairwise transitions ending at the hovered column are shown.

---

### TC13 — Group-by toggle switches between rarity and supertype

**Steps:** Toggle the group-by control from `Rarity` to `Supertype`.

**Expected:** The heatmap rows change. Rarity tiers (`Common`, `Uncommon`, etc.) are replaced by supertype values (`Pokémon`, `Trainer`, `Energy`). Cell values update accordingly.

---

### TC14 — Empty state for sets with no multiplier data

**Steps:** Select a set that has no rows in `condition_multipliers` (e.g. a newly added set with less than 30 days of pricing).

**Expected:** The heatmap is replaced by the `EmptyState` component with the "Not enough price data yet" message.

---

### TC15 — Summary cards reflect current selection

**Steps:** Switch the set selector from Base Set to Jungle.

**Expected:** All four summary cards update with values calculated from the Jungle data. The "Steepest drop" card shows a different grouping if the steepest cliff differs between sets.
