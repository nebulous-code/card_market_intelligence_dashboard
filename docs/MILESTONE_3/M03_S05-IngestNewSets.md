# M03_S05 — Ingest New Sets

## Summary

Operational story — no agent involvement. Work through this checklist manually to add Jungle, Fossil, and Pokémon 151 to the database and verify pricing data is ingesting correctly for all sets including Base Set.

Complete S01 (Set Mapping Table) before starting this story.

---

## Prerequisites

- [x] M03_S01 is merged and deployed — `set_identifiers` table exists
- [x] PPT paid API tier is active — free tier (100 credits/day) is insufficient for multi-set ingestion
- [x] `PPT_INCLUDE_HISTORY=true` and `PPT_HISTORY_DAYS=180` are set in `.env` and GitHub Actions variables

---

## Step 1 — Verify TCGdex Set IDs

Confirm these are the correct TCGdex IDs by hitting the API directly before running ingestion:

- [x] Jungle — expected ID: `base2` (verified)
- [x] Fossil — expected ID: `base3` (verified)
- [x] Pokémon 150 — expected ID: `sv03.5` (verified)

```
https://api.tcgdex.net/v2/en/sets/{set_id}
```

If an ID is wrong, find the correct one by browsing:
```
https://api.tcgdex.net/v2/en/sets
```

---

## Step 2 — Verify PPT Set Names

Find the exact display name PPT uses for each set. Check the PPT site or hit their API directly:

```
GET /api/v2/sets
Authorization: Bearer YOUR_API_KEY
```

- [x] Confirm PPT name for Jungle - `Jungle` (verified)
- [x] Confirm PPT name for Fossil - `Fossil` (verified)
- [x] Confirm PPT name for Pokémon 151 - `SV: Scarlet & Violet 151` (verified)
- [x] Confirm PPT name for Base Set matches what is already in `set_identifiers` (`"Base Set"`) (verified)

---

## Step 3 — Register New Sets in `set_identifiers`

Once you have confirmed IDs and names, insert the mappings. Template — fill in confirmed values:

```sql
-- Jungle
INSERT INTO set_identifiers (set_id, source, identifier, identifier_type) VALUES
    ('base2', 'tcgdex', 'base2',         'id'),
    ('base2', 'tcgdex', 'Jungle',         'name'),
    ('base2', 'ppt',    'Jungle', 'name');

-- Fossil
INSERT INTO set_identifiers (set_id, source, identifier, identifier_type) VALUES
    ('base3', 'tcgdex', 'base3',         'id'),
    ('base3', 'tcgdex', 'Fossil',         'name'),
    ('base3', 'ppt',    'Fossil', 'name');

-- Pokémon 151
INSERT INTO set_identifiers (set_id, source, identifier, identifier_type) VALUES
    ('sv03.5', 'tcgdex', 'sv03.5', 'id'),
    ('sv03.5', 'tcgdex', 'Pokemon 151',    'name'),
    ('sv03.5', 'ppt',    'SV: Scarlet & Violet 151', 'name');
```

- [x] Jungle entries inserted
- [x] Fossil entries inserted
- [x] Pokémon 151 entries inserted

---

## Step 4 — Run TCGdex Ingestion for Each Set

Run in this order. Verify each set before moving to the next.

```bash
python run.py --set-id base2
python run.py --set-id base3 
python run.py --set-id sv03.5
```

After each run verify the set landed correctly:

```sql
SELECT id, name, printed_total FROM sets ORDER BY release_date;
SELECT COUNT(*) FROM cards WHERE set_id = 'base2';
SELECT COUNT(*) FROM cards WHERE set_id = 'base3';
SELECT COUNT(*) FROM cards WHERE set_id = 'sv03.5';
```

- [x] Jungle — confirm card count matches expected (`64` cards)
- [x] Fossil — confirm card count matches expected (`62` cards)
- [x] Pokémon 151 — confirm card count matches expected (`165` cards)

If counts are wrong, check the ingestion logs for errors or skipped cards.

---

## Step 5 — Run PPT Pricing Ingestion for All Sets

Run the full pricing ingestion. With history enabled this will take multiple runs across a few days on the paid tier — the watermark system handles resuming automatically.

- [ ] Trigger the GitHub Actions workflow manually or run locally
- [ ] Check the ingestion summary email/log after each run
- [ ] Verify price snapshots exist for each set:

```sql
SELECT c.set_id, COUNT(ps.id) as snapshot_count
FROM price_snapshots ps
JOIN cards c ON ps.card_id = c.id
GROUP BY c.set_id
ORDER BY c.set_id;
```

- [x] Base Set has snapshots
- [x] Jungle has snapshots
- [x] Fossil has snapshots
- [x] Pokémon 151 has snapshots

---

## Step 6 — Review Match Quality

Check the ingestion logs or summary email for each set and note:

- [x] Base Set match rate is acceptable (document actual number e.g. `97/102`)
- [x] Jungle match rate is acceptable
- [x] Fossil match rate is acceptable
- [x] Pokémon 151 match rate is acceptable

If a match rate is unexpectedly low (below ~85%) investigate whether it is a card numbering format issue, a PPT coverage gap, or a bug. Document findings here for future reference.

---

## Step 7 — Verify Frontend

Once data is in the database, open the app and confirm:

- [x] All four sets appear on the Set List page with logos and pricing data
- [x] Each set detail page loads the correct cards and chart
- [x] No sets show stale or cross-contaminated data
- [x] Box and whiskers chart renders correctly for each set (some sets may have sparser rarity data than Base Set)

---

## Known Risks

**Pokémon 151 data shape** — 151 is a modern set and may have different card fields, rarity naming conventions, or numbering formats than the classic sets. If the TCGdex ingestion produces unexpected results for 151, review the raw API response before debugging the loader.

**PPT coverage gaps** — PPT may not have pricing data for every card in every set, particularly older or lower-value commons. Low match rates on Jungle and Fossil commons are expected and not necessarily a bug.

**Credit consumption** — With history enabled, ingesting three new sets on the paid tier will consume significant credits on the first run. Monitor the `X-RateLimit-Daily-Remaining` header in the logs and expect the full backfill to take 2-3 days.
