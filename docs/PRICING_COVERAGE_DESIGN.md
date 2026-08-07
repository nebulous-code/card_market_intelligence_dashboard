# Pricing Coverage — Design

How the app should behave when a user uploads a card or set that is genuinely real but that we do not have pricing data for.

Status: built. The decisions this raised, and how they were settled, are at the bottom.

---

## The problem

Today the app knows about four sets. A user uploading anything else gets `Set 'Jungle' is not recognized`, which reads like they made a typo. The truth is that the set is real and we simply do not cover it.

There are around 218 Pokemon TCG sets. Pricing costs money per card, so we will never cover all of them — this is a permanent condition to design for, not a gap to close. The app needs to tell three different stories:

| condition | whose fault | what the user should hear |
| --- | --- | --- |
| not a real set or card | theirs | check the spelling |
| real, but we do not price that set | ours | we know it, we just do not have data yet |
| real and priced set, but no data for that card | ours | narrower version of the same |

The failure mode we are most concerned about is silent incompleteness: a user downloads an Excel workbook, sees a total, and does not realise a third of their collection was dropped. That is worse than an error.

---

## What we measured

Everything below was verified against the live APIs and the running app rather than taken from documentation. Several of the existing docs turned out to be stale.

### The free catalogue is large, cheap, and complete enough to validate against

TCGdex is free and unauthenticated.

- **218 sets, 23,746 cards** available.
- The set list is one call. Each `/sets/{id}` call returns the set **and its cards**, with `id`, `name`, and `localId` (the card number) bundled in.
- A complete identity catalogue is therefore **219 calls, about 50 seconds**.
- `rarity` and `supertype` are the only fields needing a per-card call — roughly 23,746 requests, about 1.2 hours at the observed 5.3 requests/second.

Both `cards.rarity` and `cards.supertype` are nullable, and the `fk_cards_rarity` foreign key tolerates NULL. So identity-only ingestion is viable.

### TCGdex also carries free pricing, but it cannot replace the paid source

Sampling 90 cards across 14 sets spanning every era:

- tcgplayer pricing present on 82/90 (91%), refreshed daily, with `lowPrice`, `midPrice`, `highPrice`, `marketPrice`, `directLowPrice`.
- cardmarket pricing present on 84/90, in EUR, with `avg1`/`avg7`/`avg30` already computed.
- **Promo sets (`basep`) returned 0/6.**

The blocker is granularity. TCGdex gives one price per card *variant*; `low`/`mid`/`high`/`market` are listing price tiers, not condition grades. There is no `NM`/`LP`/`MP`/`HP`/`DMG` anywhere in the payload, and pricing is absent from every list endpoint, so it is one call per card with no bulk option.

Per-condition pricing is what the condition-multiplier analysis, the collection valuation, and the Excel Upgrade Cost sheet are all built on. Snapshotting TCGdex nightly would accumulate history but would never add conditions.

**Conclusion: TCGdex is the metadata source. It is not a pricing source for this app.**

### The paid tier comfortably covers the sets we care about

Verified live against the API tier:

```
daily limit: 20,000 credits

 5 sets (~550 cards):  1,100 credits =  5.5% of daily budget
10 sets (~1100 cards): 2,200 credits = 11.0%
20 sets (~2200 cards): 4,400 credits = 22.0%
```

Credit cost is **per card, per data type**, confirmed from response headers (`X-Api-Calls-Breakdown: cards=1,history=1,ebay=0`):

- 1 credit — current price, **Near Mint only**
- 2 credits — adds `priceHistory.variants`, which is where all five conditions come from

The app needs 2 credits per card. At the scale we care about that is single-digit percent of the daily budget. A full-catalogue nightly refresh would be 47,492 credits and is not on the table, but nothing about this design wants that.

**`docs/POKEMON_PRICE_TRACKER_API.md:104` is wrong** and should be corrected: it claims `priceHistory` is not returned even when requested. It is returned — 24 points across 10 condition-variant buckets for a single common card, dated today.

### The architecture already supports "known but unpriced"

- Every price-dependent read path is already null-tolerant. `collection_pricing`, `collection_excel`, and the frontend aggregations all branch on a missing price and continue.
- `SetListView.vue` already renders **"No pricing data yet"** for a set with null price aggregates.
- `/sets` hand-rolls a left join in Python, so unpriced sets return with null aggregates rather than disappearing.
- `_build_set_lookup` never touches `price_snapshots`, so any set in the table resolves. This is the mechanism that lets us distinguish "real but unpriced" from "not real".
- `/trends/sets-with-multipliers` already filters to sets with data using a correlated `EXISTS`, and documents why. That is the pattern to reuse.

What does **not** exist is any way to express coverage at the set level: no `is_active`, no `has_prices`, no `priced_at`.

### The card-level case is already live

`base1-8` (Machamp) has zero price snapshots inside a fully priced set. So "priced set, unpriced card" is not hypothetical — it exists in the data today and currently produces a silently blank row.

---

## The design

### 1. Ingest the full catalogue from TCGdex

Two tiers, because the cost difference is 50 seconds versus 1.2 hours:

- **Identity for all 218 sets** — set metadata plus each card's `id`, `name`, `number`. Enough to answer "is this real?". Cheap enough to run nightly so newly released sets appear automatically.
- **Full metadata only for priced sets** — `rarity` and `supertype`, which are only needed for cards we actually display, slice, and price.

`rarity` and `supertype` are **not** backfilled for unpriced sets. They serve no purpose for validation, they are the expensive tier, and both columns are nullable with a NULL-tolerant foreign key. If unpriced sets ever surface somewhere that needs rarity, that is the point to reconsider.

Requires three additions that are absences rather than couplings: a `get_sets()` client function, a driver that loops sets, and some throttling.

### 2. A YAML drives which sets we pay to price

`set_identifiers` is **already** the priced-sets list — `run.py:153-158` resolves a set's PPT name before any HTTP call and skips it at zero credit cost when there is no `('ppt', 'name')` row.

So the YAML should generate those rows, not replace them. A file listing canonical id, TCGdex id, and PPT name, plus a sync step that upserts into `set_identifiers`. That gives the intended workflow — buy a set, add a line, commit — without creating a second source of truth or touching a tested code path.

The sync is **a module in `ingestion/` with a thin entry point, invoked by the nightly workflow** -- `priced_sets.py` plus `run_sync_priced_sets.py`, matching the shape of `refresh_multipliers.py`. It does not live in `tools/`: that directory sits outside the coverage config's `source` list, which makes it the wrong home for the code that decides what we pay for, and a script there would need a `sys.path` hack to import `set_resolver`. Keeping it in a script rather than a migration means it cannot drift from the YAML, and calling it from the workflow means the workflow file documents when it runs. It has an ordering dependency: a set must exist in `sets` before `register_identifier` will accept a mapping for it, so the catalogue ingest has to precede the sync, which has to precede the price run.

**Removing a set from the YAML stops future refreshes but keeps the accumulated history.** Such a set still satisfies the coverage check below and continues to be treated as priced — its data simply stops advancing. That is the intended behaviour: deleting months of price history because a line was removed from a config file would be a surprising amount of destruction for a small edit.

The nightly run also needs filtering: `get_all_sets()` is currently unfiltered, so 218 sets would produce roughly 213 skip-errors per night and swamp the summary email.

### 3. Coverage is derived from data, never from the YAML

The YAML expresses **intent**. The database expresses **truth**. A set added this morning has no prices until tonight's run, and a user uploading right now must still be told there is no data.

So the API answers "do we have prices for this set?" with an `EXISTS` against `price_snapshots`, following the `/trends/sets-with-multipliers` precedent. Self-maintaining, cannot drift, no flag to forget to flip.

### 4. Accept the upload, exclude the rows, and say so

A row from an unpriced set is **not** a validation error. The upload succeeds. The rows are excluded from valuation and reported.

Disclosure happens in three places, because each covers a failure of the others:

**Immediate — on upload.** A message naming the sets we could not price and how many rows that affected. No contact address here; see below.

**Durable — two columns on the collection table.** Added to `collection_details`:

- `price_missing` — boolean. `TRUE` means we have no price at all for this row.
- `price_missing_reason` — short explanatory string, populated only when `price_missing` is `TRUE`.

This is the load-bearing piece. A popup is transient, but the workbook gets saved, emailed, and opened three weeks later. Row-level data is also what makes a support request debuggable — "which cards are missing" is answerable at a glance, by the user or by whoever they email.

Note this is distinct from the existing `pricing_warning`, which means the opposite kind of thing: we *do* have a price, but it was derived by falling back to a different condition. `price_missing` means there is no price to show.

**Persistent — a banner on the web dashboard.** The web view has the same silent-incompleteness problem as the workbook, so it carries a header warning when any row is excluded.

The About sheet stays **static**. Dynamic content at the top of a sheet would have to size itself and push the ListObjects down, which the patcher is not built for and does not need to be. It explains what the two columns mean and carries the contact line — placed near the top, under the generated-by attribution:

> Contact me@nebulouscode.com with questions, comments, concerns, or requests for set additions.

**The contact address appears only on the About sheet** — not in the upload response, not on the web dashboard.

A Dashboard KPI counting unpriced cards was considered and **deferred**. The column is the durable record; a KPI would only make it more discoverable. It is recorded in the Milestone 6+ roadmap rather than built now.

### 5. `/sets` filters, the upload template does not

- **`/sets` screen** shows only sets we have data on, via the same `EXISTS` filter. Showing 218 sets where 214 are empty would be worse than showing four.
- **Upload template dropdown** shows everything. `collection_template._query_set_names` already queries `SELECT name FROM sets` live per request, explicitly so "the dropdown grows with the database without code changes" — so a full catalogue appears with no code change at all.

That is the split: the dropdown is what you may *enter*, `/sets` is what we have *data* on. The dropdown is also the better place for it, since it is in front of the user at the moment they are filling the form.

The dropdown does **not** mark which sets are priced. Marking them was considered and dropped: Excel data-validation lists have no separate display and stored value, so whatever the user picks lands verbatim in the `Set` column. A marker like `Jungle *` would arrive at the validator, fail to match `sets.name`, and resolve as unrecognized — producing exactly the "you made a typo" message this design exists to eliminate, and only for the sets the marker was meant to help. Making it work would mean stripping the marker during normalization, which is a permanent obligation on the validator for a cosmetic hint.

Instead, `/sets` is the place to check what is priced. The user finds out either by looking there beforehand or from the upload response afterwards, and the upload response is the more reliable of the two because it is specific to what they actually submitted.

### 6. The same treatment at card level

After a full catalogue ingest, "card number does not exist in this set" becomes a genuine user error rather than a coverage gap. That leaves the three-way split above, and the reason column is what carries the distinction into the workbook.

---

## What it costs to add the columns

Cheap but not free, and one step is easy to miss. Both new columns pay this cost.

`_DETAILS_COLUMNS` in `api/services/collection_excel.py` and the template's `collection_details` header currently match exactly at 19 columns, going to 21. Nothing in the test suite pins the count.

The patcher **preserves the template's header row verbatim** and only rewrites data rows. So adding a column means:

1. Add the entry to `_DETAILS_COLUMNS`.
2. **Manually add the header cell in the template workbook** and extend the ListObject. Without this the patcher writes data into a column with no header, and Power Query names it something arbitrary.
3. Add it to `qCollection`'s type transform. Not strictly required — `Table.TransformColumnTypes` passes unlisted columns through — but leaving it out means the column arrives untyped, and `price_missing` in particular wants to be a real boolean so it can drive conditional formatting.
4. Add it to `qCardsRanked`'s `Table.SelectColumns` list, or it will not appear on the Cards Ranked sheet.

Step 2 is manual Excel work and is the one that will bite if forgotten.

Worth pairing with a conditional-formatting rule on `price_missing`, matching how `pricing_warning` is already highlighted — otherwise the column only helps someone reading row by row.

---

## Decisions taken

The questions this design raised, and how they were settled.

| Question | Decision |
| --- | --- |
| Wording of `price_missing_reason` | A fixed two-value vocabulary, never free text: `Set not priced yet` and `Card not priced yet`. It is user-facing copy and the thing you grep when someone emails about a missing card, so it has to be stable. It does not name the set -- `set_name` is already its own column. |
| Can `price_missing` and `pricing_warning` both be TRUE? | No. Mutually exclusive by construction, asserted in a test. `pricing_warning` means a price was derived by fallback; `price_missing` means there is no price at all. The variant leg of `pricing_warning` has to be suppressed when a row is unpriced, or a variant row with no price would set both. |
| Web dashboard banner | Dismissible, sitting above the KPI row -- the KPIs are the numbers being undercounted. Dismissibility puts more weight on the other two disclosure points, which is why the upload response matters. |
| Every row unpriced | Accepted, but with its own message. A dashboard with no valuations anywhere is the case most likely to read as broken, and "some cards are not included" badly undersells it. |
| Is the reason stored or re-derived? | **Re-derived**, through one shared helper. Storing it on the session row would mean threading the field through the schema, the validator, and both hand-written serialization lists, and it would go stale whenever coverage changed. The usual objection to re-deriving is that two outputs could disagree; they cannot, because there is exactly one implementation and all three callers use it. |
| One workflow or two? | One job, ordered catalogue then sync then prices, with `continue-on-error` on the two new steps. That keeps the ordering guaranteed while ensuring a TCGdex outage degrades to "last night's catalogue" rather than blocking the paid price run. |
| TCG Pocket sets | Excluded. 15 of the 218 sets are the digital-only phone game, and every feature downstream -- conditions, upgrade cost, purchase price -- is meaningless for a card that cannot be physically owned. They would otherwise sit in the dropdown as permanently unpriced. |
| Where the sync script lives | `ingestion/`, not `tools/`. `tools/` is outside the coverage config's `source` list, which makes it the wrong home for the code that decides what we pay for. |

---

## Related items already tracked

- `t_0136 — Add more sets to prod` is the immediate cause of the current failure and is independent of this design.
- `docs/MILESTONE_3/MILESTONE_6_PLUS_ROADMAP.md` treats set expansion as "primarily an operational task of registering new sets and running ingestion". This design changes that framing: the catalogue becomes complete by default and pricing becomes the selective part.
- `docs/POKEMON_PRICE_TRACKER_API.md:104` needs correcting — `priceHistory` is returned, contrary to the note there.
- Price data is stale in both environments as of writing: prod 7 days, dev 97 days. The paid key was reactivated during this investigation, so prod should recover on the next scheduled run; dev needs one triggered.
