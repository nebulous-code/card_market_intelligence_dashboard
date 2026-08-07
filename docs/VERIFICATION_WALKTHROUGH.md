# Verification walkthrough — pricing coverage, catalogue ingest, custom domain

Everything below was validated by me. None of it is verified — that is what this document is for.

Part 1 is what has to happen before any of it is testable. Part 2 is the walkthrough. Part 3 is what I could not check and what I would expect to be wrong first.

Work Part 1 in order. Several steps depend on the one before, and two of them are the kind that fail silently.

---

# Part 1 — Getting to a testable state

## 1.1 Clear the working tree

`docs/PRICING_COVERAGE_DESIGN.md` is still marked unmerged from the stash pop. Content is correct and has no conflict markers — git just needs telling.

```bash
git add docs/PRICING_COVERAGE_DESIGN.md
git stash drop stash@{0}        # already applied; safe to discard
git status --short              # expect no UU lines
```

Then review and commit everything. New files worth knowing about:

| Path | What it is |
| --- | --- |
| `ingestion/run_catalogue.py` | Walks all 218 TCGdex sets, identity only |
| `ingestion/priced_sets.yml` | The list of sets we pay to price |
| `ingestion/priced_sets.py`, `run_sync_priced_sets.py` | Reconciles that file into `set_identifiers` |
| `api/services/pricing_coverage.py` | The single source of truth for "why is there no price" |
| `docs/test_collections/*.xlsx` | Three upload files for Part 2 |
| `docs/WRITEUP_MATERIAL.md` | Source material for the writeup task |

## 1.2 Do the Excel work — this gates everything in section 2.6

I widened `collection_details` in the template from 19 to 21 columns by direct ZIP surgery. I cannot reach the Power Query blob, so the query side is yours. **Until this is done the workbook will refresh with two columns Power Query does not know about, and the ranked sheets will not show them.**

In `api/assets/collection_template.xlsx`:

1. **`qCollection`** — the `Table.TransformColumnTypes` step needs `price_missing` (logical) and `price_missing_reason` (text) added. Without this the two columns arrive untyped or get dropped.
2. **`qCardsRanked`** — add both to its `Table.SelectColumns` list if you want them visible on Cards Ranked.
3. **Conditional formatting** — a rule on `price_missing`, matching how `pricing_warning` is already highlighted. Without it the column only helps someone reading row by row.
4. **About sheet** — a line explaining what the two columns mean, plus the contact line agreed in the design doc:

   > Contact me@nebulouscode.com with questions, comments, concerns, or requests for set additions.

Then save, and confirm the asset test still passes:

```bash
tools/test.sh api/tests/test_collection_template_asset.py -q --no-cov
```

That test compares the template's table columns against what the backend writes. It is the guard against exactly this step being forgotten — if it fails, the header row and the ListObject have drifted.

**Commit the modified `.xlsx`.** The backend serves this asset, so an uncommitted change means production keeps the old one.

## 1.3 Deploy

`render.yaml` describes services named `dev-*`, so I could not tell from the repo which branch drives production — confirm that in the Render dashboard before merging.

```bash
git checkout main && git merge dev && git push
```

Watch both services redeploy. The API applies Alembic migrations at startup, though this change added none.

## 1.4 Point CORS at the new domain

In the Render dashboard, on the **API** service:

```
FRONTEND_URL = https://cards.nebulouscode.com
```

Scheme included, no trailing slash. This is the one that fails quietly — if it is wrong the app loads fine and only the collection upload breaks, with an opaque browser network error rather than anything readable.

Leave `VITE_API_BASE_URL` on the dashboard service pointing at the Render API hostname; the API is deliberately not moving.

## 1.5 Cut over DNS

1. Render → dashboard service → Settings → Custom Domains → add `cards.nebulouscode.com`
2. Create the CNAME your registrar/DNS provider requires, pointing at the value Render shows
3. Wait for Render to report the domain verified and the certificate issued

Then confirm before moving on:

```bash
curl -sI https://cards.nebulouscode.com | head -3          # expect 200
curl -s -D- -o /dev/null -H "Origin: https://cards.nebulouscode.com" \
     https://card-market-api.onrender.com/sets | grep -i access-control-allow-origin
```

That second command is the real check on 1.4. If the header is missing or shows the old Render origin, the upload will fail later in a way that is hard to read back to this step.

## 1.6 Run the ingestion workflow against production

Actions → **Nightly Price Ingestion** → Run workflow.

It now runs four things in order: TCGdex catalogue, priced-set sync, prices, condition multipliers. The first two are new. Expect roughly 90 seconds of catalogue on top of the usual runtime.

Check the summary email. It now leads with two new blocks:

```
TCGdex catalogue: Success
  Sets published : 218
  Sets upserted  : 203
  Sets excluded  : 15 (digital-only series)
  Sets failed    : 0
  Cards upserted : ~21000

Priced-set sync: Success
  Rows unchanged : 8
```

**`Sets excluded : 15` is correct, not a failure** — those are Pokémon TCG Pocket, the digital-only game, deliberately skipped.

Then confirm production actually took it:

```bash
curl -s https://card-market-api.onrender.com/sets | python3 -c "import json,sys; d=json.load(sys.stdin); print(len(d), [s['name'] for s in d])"
```

Expect the four priced sets — **not** 203. `/sets` now filters to sets that have price data. If you see 203, the filter did not deploy. If you see 1, the price run has not populated the other three yet.

---

# Part 2 — The walkthrough

## 2.1 The domain

- `https://cards.nebulouscode.com` loads
- Certificate is valid, no browser warning
- Deep links work on direct navigation, not just in-app clicks — try `https://cards.nebulouscode.com/sets/base1` pasted fresh into the address bar. A 404 here means the SPA rewrite rule did not survive.
- The old Render URL still works — nothing was moved, only added

## 2.2 The sets page reflects coverage

The catalogue put ~203 sets in the database. The sets page should show only the ones with prices.

- Sets page lists the four priced sets, not 203
- No card opens onto an empty page
- Clicking through to a set and then a card still works

**Why this matters:** before the filter, every catalogued set would appear, and ~199 of them would open onto a page with no data.

## 2.3 The mock demo

This is the highest-traffic path and it was returning a wall of errors before today.

- Load the collection page, click through the mock/demo flow
- It should succeed, not 422

Before this change the mock referenced Jungle, Fossil and 151 while production only had Base Set, so 17 of 23 rows failed with `Set 'Jungle' is not recognized`. That message is the exact thing this work exists to eliminate — it told the user they were wrong when they were right.

## 2.4 Upload the three test files

In `docs/test_collections/`. Each isolates one concern, so if something misbehaves you are not diagnosing two things at once.

### `1_small_all_priced.xlsx` — 12 rows, nothing unpriced

The happy path. If this is wrong the problem is not about coverage.

- Upload succeeds
- **No banner appears** on the dashboard
- KPIs, treemap, pie, tables all populate
- One row has no purchase price — its gain columns should be blank, not zero

### `2_mixed_priced_and_unpriced.xlsx` — 16 rows, 8 unpriced

The one that exercises everything new.

- Upload succeeds — it does **not** get rejected
- The upload response names the unpriced sets. Expect wording like: *"N cards are not included in the totals because we do not have pricing for them yet (Base Set 2, Gym Heroes, Neo Genesis and 1 more). Everything else is valued as normal."*
- A dismissible info banner sits **above the KPI row** on the dashboard
- The banner names sets and gives a quantity-weighted count — three copies of one card read as three cards
- Dismissing it works, and it **comes back on reload**. That is deliberate: a banner that stays dismissed reintroduces the silent-incompleteness problem.
- KPI totals **exclude** the unpriced rows
- The unpriced cards still appear in the collection table, with no price

The four unpriced sets are Base Set 2, Team Rocket, Neo Genesis and Gym Heroes — real, recognisable sets. The point of the test is that they read as *real cards we do not price*, never as typos.

### `3_large_1950_rows_all_priced.xlsx` — 1,950 rows

Volume only, near the 2,000-row product cap.

- Upload completes without a timeout
- It should feel fast. Validation measured **0.44 s** for these 1,950 rows against dev; the pre-batching baseline was roughly 48 s for 1,000 rows. Anything in the tens of seconds means the batched lookup is not being hit.
- Dashboard renders, charts are legible with that much data
- No banner — every row is priced

## 2.5 The error path still blames the right party

Take any test file, change one set name to something fake like `Jungel`, upload it.

- It is rejected with `Set 'Jungel' is not recognized`
- A *real* set never produces that message

This is the distinction the whole feature turns on: a typo is the user's problem, an unpriced set is ours, and they must not look the same.

## 2.6 The Excel export

Requires section 1.2 to be done.

Download the workbook from a session that had unpriced rows (file 2).

- Opens without a repair prompt. **A repair prompt is a serious finding** — it would mean the ZIP surgery damaged a part.
- Collection Details has 21 columns, ending in `price_missing` and `price_missing_reason`
- Unpriced rows show `TRUE` and a reason: `Set not priced yet` or `Card not priced yet`
- Priced rows show `FALSE` and a blank reason
- **No row has both `price_missing` and `pricing_warning` set to TRUE.** They mean opposite things — one says "treat this number with care", the other says "there is no number".
- Power Query refreshes without error
- Pivots, slicers and charts all still work
- The About sheet carries the new explanation and contact line

I verified programmatically that only 2 of the workbook's 109 internal parts changed, but that is not the same as Excel being happy with it. Your eyes are the test.

## 2.7 Nightly ingestion end to end

Trigger the workflow once more, now that the catalogue is populated.

- The catalogue step reports `Sets upserted: 203`, `Sets failed: 0`, and **no new sets** the second time
- The sync reports `Rows unchanged: 8` and no changes. A clean no-op is the proof `priced_sets.yml` matches reality.
- The price run processes **4 sets, not 203** — it now filters to sets with a PPT mapping. If it tries all 203 you will see a wall of resolver errors.
- The email carries all four status blocks

### The one that matters most

The catalogue writes card rows carrying no rarity and no supertype. Confirm it did not blank the ones you have:

```sql
SELECT count(*) FROM cards WHERE rarity IS NOT NULL;      -- expect 435
SELECT count(*) FROM cards WHERE supertype IS NOT NULL;   -- expect 435
SELECT count(*) FROM cards;                               -- expect ~21000
```

If the first two come back near zero, stop and tell me. The naive implementation of this would have overwritten both columns with NULL for every card in every priced set. I proved against real rows that it does not, but that proof was on dev.

---

# Part 3 — Known gaps and where I would look first

**Not tested by anyone yet:**

- The template with your Power Query changes applied. My asset test checks the columns line up; it cannot check that a refresh produces sensible output.
- Any of this against production data. Every number above came from dev.
- The banner on a phone. I checked it builds, not that it reads well narrow.

**Most likely to be wrong, in order:**

1. **`FRONTEND_URL`** — wrong value or a trailing slash. Symptom: everything works except the upload, which fails with an opaque network error.
2. **The Power Query type step** — symptom is the two columns present in Collection Details but absent or untyped on Cards Ranked after a refresh.
3. **`/sets` returning 203 instead of 4** — the filter did not deploy.
4. **Prod missing the three non-Base sets** — the mock demo still errors. Data problem, not code.

**Deliberately not changed:**

- The API stays on Render, so the session cookie is still `SameSite=None; Secure`. Correct for two different registrable domains. Moving the API under `nebulouscode.com` later would let it relax to `Lax` — noted in the roadmap.
- `render.yaml` still names services `dev-*`. Those are Render service names, not DNS-facing.
- `MAX_DATA_ROWS` stays at 2,000. After batching it is a product decision, not a technical ceiling.
