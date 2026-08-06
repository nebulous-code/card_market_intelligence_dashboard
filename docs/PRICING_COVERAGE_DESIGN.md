# Pricing Coverage — Design

How the app should behave when a user uploads a card or set that is genuinely real but that we do not have pricing data for.

Status: design, not yet built. Open decisions are at the bottom.

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

Requires three additions that are absences rather than couplings: a `get_sets()` client function, a driver that loops sets, and some throttling.

### 2. A YAML drives which sets we pay to price

`set_identifiers` is **already** the priced-sets list — `run.py:153-158` resolves a set's PPT name before any HTTP call and skips it at zero credit cost when there is no `('ppt', 'name')` row.

So the YAML should generate those rows, not replace them. A file listing canonical id, TCGdex id, and PPT name, plus a sync step that upserts into `set_identifiers`. That gives the intended workflow — buy a set, add a line, commit — without creating a second source of truth or touching a tested code path.

The nightly run also needs filtering: `get_all_sets()` is currently unfiltered, so 218 sets would produce roughly 213 skip-errors per night and swamp the summary email.

### 3. Coverage is derived from data, never from the YAML

The YAML expresses **intent**. The database expresses **truth**. A set added this morning has no prices until tonight's run, and a user uploading right now must still be told there is no data.

So the API answers "do we have prices for this set?" with an `EXISTS` against `price_snapshots`, following the `/trends/sets-with-multipliers` precedent. Self-maintaining, cannot drift, no flag to forget to flip.

### 4. Accept the upload, exclude the rows, and say so in three places

A row from an unpriced set is **not** a validation error. The upload succeeds. The rows are excluded from valuation and reported.

Disclosure happens at three levels, deliberately, because each covers a failure of the others:

**Immediate — on upload.** A message naming the sets we could not price and how many rows that affected.

**Durable — a column on the collection table.** A new column in `collection_details` that is blank when a row priced normally and carries a short reason when it did not. This is the load-bearing piece: a popup is transient, but the workbook gets saved, emailed, and opened three weeks later. Row-level data is also what makes a support request debuggable — "which cards are missing" is answerable at a glance.

**Discoverable — a count on the Dashboard.** A single figure such as "cards without pricing". One cell, no layout problem, and it sits where the user is already looking. Without this, the column only helps someone who already suspects a problem.

The About sheet stays **static**. It explains what the column means and gives a contact address for requesting a set. Dynamic content at the top of a sheet would have to size itself and push the ListObjects down, which the patcher is not built for and does not need to be.

### 5. `/sets` filters, the upload template does not

- **`/sets` screen** shows only sets we have data on, via the same `EXISTS` filter. Showing 218 sets where 214 are empty would be worse than showing four.
- **Upload template dropdown** shows everything. `collection_template._query_set_names` already queries `SELECT name FROM sets` live per request, explicitly so "the dropdown grows with the database without code changes" — so a full catalogue appears with no code change at all.

That is the split the user needs: the dropdown is what you may *enter*, `/sets` is what we have *data* on. The dropdown is also the better place for it, since it is in front of the user at the moment they are filling the form.

### 6. The same treatment at card level

After a full catalogue ingest, "card number does not exist in this set" becomes a genuine user error rather than a coverage gap. That leaves the three-way split above, and the reason column is what carries the distinction into the workbook.

---

## What it costs to add the column

The Excel column is cheap but not free, and one step is easy to miss.

`_DETAILS_COLUMNS` in `api/services/collection_excel.py` and the template's `collection_details` header currently match exactly at 19 columns. Nothing in the test suite pins the count.

The patcher **preserves the template's header row verbatim** and only rewrites data rows. So adding a column means:

1. Add the entry to `_DETAILS_COLUMNS`.
2. **Manually add the header cell in the template workbook** and extend the ListObject. Without this the patcher writes data into a column with no header, and Power Query names it something arbitrary.
3. Add it to `qCollection`'s type transform. Not strictly required — `Table.TransformColumnTypes` passes unlisted columns through — but leaving it out means the column arrives untyped.
4. Add it to `qCardsRanked`'s `Table.SelectColumns` list, or it will not appear on the Cards Ranked sheet.

Step 2 is manual Excel work and is the one that will bite if forgotten.

---

## Open decisions

**1. What is the new column called, and what does it contain?**
Options include a status string that is blank when priced (`price_status`), a nullable reason (`missing_price_reason`), or a boolean plus a separate reason. Note `pricing_warning` already exists and means something different — we have a price but it was derived by fallback. The new column means we have no price at all. The two should not be confused in the naming.
- price_missing - boolean TRUE is missing FALSE is we're fine. price_missing_reason for the explaination string, only filled when price_missing = TRUE

**2. Should the template dropdown distinguish priced from unpriced sets?**
Simplest is one flat list of every real set, with the upload response explaining what could not be priced. A two-tier list, a marker on unpriced entries, or a note on the Instructions sheet are all possible but add build cost.
- Let's end the string with a * if we're missing a price and then call that out in the about page

**3. What happens when a set is removed from the YAML?**
Recommend keeping the accumulated history and simply ceasing to refresh it. But it would then still satisfy the `EXISTS` check and count as priced. Whether that matters depends on whether "priced" should mean "ever priced" or "currently maintained".
- That works

**4. Should the mock collection stay inside the priced set list?**
It currently spans four sets. Keeping it priced means the demo button never leads with a warning. Deliberately including one unpriced set would demo the feature, at the cost of a messier first impression.
- yes mock collection should stay inside the priced set. We don't need to show off how we handle edge cases and make people question the data

**5. Does the Dashboard KPI get built, or is the column enough?**
The column is the durable record; the KPI is what makes it discoverable. Skipping the KPI is cheaper but relies on the user reading the About sheet.
- I'm skipping the KPI for now. Add this as a possible enhancement in the enhancement doc

**6. Does the web dashboard get the same row-level treatment?**
The Excel is the artifact most likely to be misread later, but the web dashboard has exactly the same silent-incompleteness problem.
- Yeah let's put a header warning or something on the web dashboard.

**7. Is `rarity`/`supertype` ever backfilled for unpriced sets?**
Not needed for validation, and it is the expensive tier at roughly 1.2 hours. Only becomes relevant if unpriced sets ever get surfaced somewhere that needs rarity.
- No need to backfill it for now.

**8. Where does the YAML live, and what runs the sync?**
Candidates: a step in the nightly workflow, a manual script in `tools/`, or an Alembic data migration. The nightly option keeps it automatic; the migration option keeps it auditable.
- a script in tools that gets called by the nightly workflow is my prefered approach that way there's no drift and the workflow documents the calling.

**9. Exact wording, and where the contact address goes.**
The address `me@nebulouscode.com` should appear on the About sheet. Whether it also appears in the upload response and on the web dashboard is a separate call.
- Don't put the email on the dashboard or the upload. Only in the about. 
- Just do a generic message at the top of the page under the generated by cards.neb.com and designed by nebulous-code 
- Message: "Contact me@nebulouscode.com with questions, comments, concerns, or requests for set additions."

---

## Related items already tracked

- `t_0136 — Add more sets to prod` is the immediate cause of the current failure and is independent of this design.
- `docs/MILESTONE_3/MILESTONE_6_PLUS_ROADMAP.md` treats set expansion as "primarily an operational task of registering new sets and running ingestion". This design changes that framing: the catalogue becomes complete by default and pricing becomes the selective part.
- `docs/POKEMON_PRICE_TRACKER_API.md:104` needs correcting — `priceHistory` is returned, contrary to the note there.
- Price data is stale in both environments as of writing: prod 7 days, dev 97 days. The paid key was reactivated during this investigation, so prod should recover on the next scheduled run; dev needs one triggered.
