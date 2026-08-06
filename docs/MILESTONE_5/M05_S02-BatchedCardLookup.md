# M05_S02 — Batched Card Lookup and Card Index

## Summary

Collection validation resolved each uploaded row to a card with its own database query. The query was free to execute and expensive to reach, so upload time was a function of network round trips and nothing else. This story replaces it with a single prefetch, and adds the index the `cards` table never had.

Left over from M05_S01, where it was recorded as a known limitation rather than fixed — the hardening story capped row count to bound the damage; this one removes the reason the cap existed.

---

## The measurement that framed it

`_resolve_card_id` ran one `SELECT` per row. Against the Neon dev instance:

```
EXPLAIN ANALYZE:     Seq Scan on cards ... Execution Time: 0.041 ms
lookup round trip:   43.8 ms
SELECT 1 round trip: 43.5 ms   <- pure network
query work:           0.3 ms
```

The query itself was 0.04 ms. `SELECT 1` cost the same as the lookup, so effectively all of the 48 ms per row was network. End-to-end uploads confirmed it was linear: 100 rows in 5.2 s, 400 in 19.4 s, 1,000 in 48.2 s.

That is why `MAX_DATA_ROWS` was 2,000 — the point where the round trips stayed inside a tolerable wait, not a limit the data or the database imposed.

---

## Batching

One query, keyed on **the sets a workbook references rather than the rows it contains**:

```sql
SELECT id, set_id, number FROM cards WHERE set_id = ANY(:set_ids)
```

The result is bounded by how many sets a collection spans — a handful in practice — instead of by upload size. A collection touching every set currently in the database returns 435 rows.

`set_id` is resolved per row, so a cheap first pass over the sheet collects which sets are referenced before the prefetch. Iterating a non-read-only openpyxl sheet twice is safe and costs no additional parsing; the rows are already in memory. Labels that fail to resolve are skipped in that pass — row validation reports them properly, with a row number.

`_validate_one` took a `Session` **solely** to perform this lookup and did no other database work. It now takes the prefetched dict instead, which makes it a pure function — and directly unit-testable, where previously it could only be reached through `validate_workbook` and a live session.

### The part that could have failed silently

A batched rewrite loses matches if the key drifts from what the SQL compared. The key had to stay byte-identical:

- The card number goes through `_coerce_number_to_text`, which renders `4` and `4.0` as `"4"`, keeps `4.5` as `"4.5"`, turns `True` into `"True"`, and strips whitespace only on the string branch. It does **no case folding**, and the SQL comparison was likewise exact — `SV01` and `sv01` are different cards.
- The set component is the resolved canonical `set_id`, never the user's label.

The miss message keeps its exact previous wording, including its quirks: it interpolates the *normalized* number but the *raw* set label, and has no trailing period.

### Result

| rows | before | after | speedup |
| --- | --- | --- | --- |
| 100 | 5.23 s | 1.13 s | 5x |
| 400 | 19.43 s | 0.39 s | 50x |
| 1,000 | 48.24 s | 0.49 s | 98x |

400 and 1,000 rows now take essentially the same time, which is the real result: upload cost no longer scales with row count. The 100-row figure includes connection warm-up.

---

## The index

`cards` carried no index beyond its primary key on `id`. Postgres does not index a foreign key column automatically, so **every query filtering on `set_id` was a sequential scan** — six in production, including the ingestion loader's per-set prefetch, three endpoints in `routers/sets.py`, and two in the multiplier refresh. One of them filters `set_id` and orders by `number`, which the composite pair serves exactly.

Migration `013_add_cards_set_number_index.py` adds `idx_cards_set_number` on `(set_id, number)`, mirrored in `models/card.py` so `Base.metadata` stays in step with the live schema.

**Deliberately not unique.** The pair is unique in the data today — 435 rows, 435 distinct pairs — but ingestion runs unattended nightly against TCGdex, and a unique constraint would turn one upstream duplicate into a hard ingest failure rather than a stray row. The lookup gains nothing from uniqueness.

The upsert in `ingestion/loader.py` conflicts on `(id)` only, so the index does not interact with `ON CONFLICT`. Card writes are already row-at-a-time inside one transaction, roughly 100-400 per set, so index maintenance is negligible.

### It has no measurable effect yet, and that is expected

At 435 rows the whole table fits in a couple of pages and the planner correctly prefers a sequential scan. Disabling `enable_seqscan` confirms the index is the right *shape* for all three access patterns:

```
batched validator lookup     index usable: YES   Bitmap Heap Scan on cards
set detail, filter + sort    index usable: YES
single card by set+number    index usable: YES   Index Scan using idx_cards_set_number
```

The planner will switch when the economics change. This is future-proofing against ingesting the full ~20,000-card catalogue, not a fix for a problem visible today.

---

## The row cap stays at 2,000

Nothing technical holds it there any more. Card resolution is one query regardless of row count, and the remaining constraint is openpyxl memory, already bounded by `MAX_UNCOMPRESSED_BYTES` at roughly 20,000 rows.

It is now a **product decision**: this app is for a personal collection, not a dealer's inventory. The comments in `upload_guard.py` and `.env.example` were rewritten to say so, specifically so nobody later "fixes" a number that is intentional.

---

## Validation

- `tools/test.sh` — 476 tests, 100% coverage. The migration runs automatically via the session fixture in the root `conftest.py`.
- Roughly two dozen existing tests use the default `Card Number=4` and assert no errors, so a regression in matching fails them en masse. `test_card_number_alphanumeric_string` is the sharpest single check that exact, case-sensitive keying survived.
- New tests cover `_build_card_lookup` directly (populated result, empty short circuit, set scoping, case sensitivity), `_validate_one` without a session, a workbook spanning two sets, and a workbook where no set resolves.
- End to end through the running app: the mock collection returns 23 rows with **zero unresolved cards** across all four sets, with the three duplicate cards still appearing twice.
