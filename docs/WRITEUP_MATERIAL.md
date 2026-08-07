# Writeup material — raw facts and threads

Not a draft. Source material for `t_0216 — card dash writeup`, organised by the kind of thing you write about: what you expected versus what happened, architectural forks, and what the project taught you. Nitty-gritty service internals are deliberately left out.

---

## The shape of the thing

Started 2026-04-08. 126 commits. Roughly 10,000 lines of Python source, 7,800 lines of Python tests, 6,400 lines of frontend, and 8,100 lines of design docs — the docs are nearly as large as the backend, which is itself a fact worth a sentence.

Five milestones, each one intended to end at a deployable state with a live URL. Stack: FastAPI + SQLAlchemy + Alembic on Python, Vue 3 + Vuetify + Chart.js on the frontend, Postgres on Neon, hosting on Render, nightly ingestion on GitHub Actions cron. Two external data sources: TCGdex for card and set identity (free, unauthenticated) and PokemonPriceTracker for prices (paid, credit-metered).

Test suite runs at an enforced 100% branch coverage. That was a choice, not an accident, and it is worth being honest in the writeup about what it bought and what it cost.

---

## The biggest gap between expectation and reality: Excel

**What you expected:** "Generate an Excel file" is a solved problem. Pick a library, write rows, ship it.

**What actually happened:** The deliverable was not a spreadsheet, it was a *workbook* — Power Query connections, pivot tables, slicers, charts, a dashboard sheet. Those are the parts that demonstrate the data skill. And openpyxl, the obvious library, silently drops every part of the `.xlsx` format it does not model. Open a workbook with it and save it again and the Power Query blob, the slicers, and the pivot caches are simply gone. No error. The file still opens.

That forced learning what an `.xlsx` actually is: a ZIP archive of XML parts. Power Query lives in `customXml/item1.xml` as a base64-encoded, UTF-16 blob called `DataMashup`. Slicers, pivot caches, and charts are all separate parts with their own relationship graph.

The resolution was to stop trying to *generate* the workbook and start *patching* it. A hand-built template workbook is the source of truth; the backend opens it as a ZIP, rewrites only the sheet XML for the data tables and their table definitions, and copies every other part through byte for byte. Roughly 109 parts in the file; a data refresh touches two or three.

**The thread for the writeup:** the instinct to reach for a library was right, and the library was the wrong tool — not because it was bad but because the problem was not the one it solves. The interesting work was in understanding the file format well enough to know what to leave alone.

**A related smaller one:** it also means a class of change can only be made by hand, in Excel, because the Power Query blob is not safely editable programmatically. That is a permanent seam between what the code owns and what a person owns, and it needed a test to guard it — an automated check that the template's columns still match what the backend writes, so a forgotten manual step fails CI instead of producing a silently wrong workbook.

---

## The architectural fork that shaped everything: partial coverage is permanent

**What you expected:** ingest the sets, price the cards, done. Coverage is a gap you close over time.

**What actually happened:** pricing costs money per card, per data type. There are around 218 Pokémon sets and roughly 23,000 cards. Full coverage is not a backlog item, it is a recurring bill. Meanwhile the free metadata source has pricing too — but one price per card, no condition grades, and the entire product (condition multipliers, upgrade cost analysis, collection valuation) is built on per-condition prices. So the free source could never substitute.

That turns "which sets do we cover?" from an operational question into an architectural one. The app has to be able to say three different things:

- not a real set — you made a typo
- real, but we do not price it — our limitation, not yours
- real and priced, but no data for that card — a narrower version of the same

Before this, an upload of a genuinely real set returned "Set 'Jungle' is not recognized," which reads as an accusation. The user was right and the app was wrong, and it blamed them anyway.

**The design principle that fell out of it:** the failure mode to design against is not the error, it is the *silent success*. Someone downloads a workbook, reads a total, and never learns that a third of their collection was dropped from it. A loud error is recoverable. A confident wrong number is not.

**The architecture that followed:** ingest every set's identity from the free source (cheap — one call per set, about 70 seconds for the whole catalogue) so validation always has the truth, and keep a small committed file listing the sets we actually pay to price. Coverage is then derived from the data itself rather than declared anywhere, which means it cannot drift.

---

## Three names for the same thing

Every external source names sets differently. TCGdex uses slugs (`base1`, `sv03.5`). PokemonPriceTracker uses display names, and not the obvious ones — "SV: Scarlet & Violet 151" for the set everyone calls 151. Your own database needs a canonical id.

The easy version is a dictionary in code. The version that survived is a database table of identifier mappings, with a resolver that every ingestion script must call before making any API request. The rule became: never pass a string to an external API directly.

**Why it matters for the writeup:** this is a small, unglamorous piece of infrastructure that quietly prevented a whole category of bug — the kind where a wrong name produces not an error but an empty result set that looks exactly like a set with no data.

---

## Bugs that only exist in production

Worth a section, because these are the ones that teach something.

**The silent success.** A nightly run failed completely — every set skipped — and the summary email said "Success" with zeros across the board. The counter for skipped sets existed but was never surfaced in the report, and the script exited zero. A monitoring system that reports success on total failure is worse than no monitoring, because you stop looking.

**The config typo that degraded data quality invisibly.** A flag controlling whether price *history* was requested was being read from one GitHub configuration namespace while being set in another. It defaulted to off. For months, production recorded only Near Mint prices — the condition multipliers, which are the analytical centrepiece, were quietly running on incomplete data. Nothing errored. The dev environment, configured differently, had the full data, which is why it went unnoticed.

**The duplicate-key crash that only appears with real data.** The pricing API returns both a price history *and* a current price, and the history includes today. Insert both in one statement and Postgres rejects it — a single statement cannot update the same row twice via conflict resolution. This is invisible with test fixtures and immediate with a live API response.

**The near-miss (today).** Adding the catalogue ingest meant writing card rows from a payload that carries identity but no rarity or supertype. The obvious implementation reuses the existing upsert, whose conflict clause overwrites those columns from the incoming row — which would have blanked rarity and supertype on every card in every set already priced. Caught before it ran, but only by looking. Also found a second instance of the same shape: about 1,600 of 23,000 cards omit the image field entirely, which would have blanked images the same way.

**The thread:** the common factor is that all four are invisible at the point of failure. None of them throw. The lesson is less "write more tests" than "the dangerous class of bug is the one that produces a plausible result."

---

## Free-tier hosting as a design constraint

The API sleeps when idle. A cold visitor waits thirty-plus seconds for the first response, which on a portfolio piece means they leave before seeing anything.

That produced a deliberate loading experience — a wake endpoint the frontend polls, an animation, cycling status messages, and skeleton loaders behind it — rather than pretending the constraint does not exist. The honest framing is that the constraint was designed *around*, not hidden.

Small detail with a good story: the endpoint was originally called `/health`, and ad blockers flag that path. Renamed to `/wake`. A perfectly correct name that was wrong for reasons that have nothing to do with correctness.

---

## Decisions that were reversed or descoped, and why

**Power BI, dropped.** Originally scoped as a companion artifact. Dropped once the Excel workbook covered the same ground, for two concrete reasons: a `.pbix` cannot be opened by a reviewer without Power BI Desktop, and publishing to a shareable link needs a paid tier for most scenarios. The workbook opens anywhere. For a portfolio piece, "the reviewer can actually open it" outranks "it uses the more enterprise tool."

**Treemap in Excel, dropped.** Deliberately let the web app be the place that visualisation shines rather than reproducing it worse in a second medium.

**User accounts, never built.** Collection uploads are held in a server-side session with a TTL rather than behind auth. Avoided building a login system for a project where nobody needs an account, at the cost of collections not persisting.

**A marker for unpriced sets in the upload dropdown, designed then dropped.** The idea was to append an asterisk to sets we do not price. It collides with how Excel data validation works — the dropdown value *is* the cell value, so the marker would have travelled into the data and broken the set lookup for exactly the sets it was meant to help. Fixable, but it would have put a permanent obligation on the validator to strip a cosmetic hint. Dropped in favour of pointing at the sets page.

That last one is a good small example of a design that is obviously right until you understand the medium.

---

## Things that turned out to be about round trips, not algorithms

The collection upload validated one row at a time, with a database query per row. The query itself measured 0.04 ms. Uploading 1,000 rows took about 48 seconds — entirely network round trips to a cloud database. The row cap was set at 2,000 because that was where the *waiting* became unreasonable, not because of anything about the data.

Replacing it with a single prefetch keyed on the sets a workbook references made the same work about 655 times faster. The row cap stayed where it was, but it is now a product decision rather than a technical ceiling — which needed writing down, so nobody later "fixes" a number that is intentional.

Adjacent discovery: the cards table had no index on its set id at all. Postgres does not automatically index foreign key columns, and six production queries were sequential-scanning because of it.

**The thread:** the interesting performance work was not making anything cleverer. It was noticing that the cost was in a completely different place from where it looked.

---

## On the 100% coverage gate

Enforced across backend and ingestion. Worth being candid in the writeup about both sides:

It caught real things, and it makes a certain kind of carelessness impossible. It also means every new branch is a negotiation, and it occasionally pushes toward deleting a defensive guard rather than testing an unreachable path — which is usually the right answer but does not always feel like it. There is a version of this that is discipline and a version that is theatre, and the honest writeup says which parts were which.

---

## Numbers you might want

- 218 sets published by the metadata source; ~23,000 cards
- Full identity catalogue: 219 API calls, about 70 seconds, free
- Full metadata for every card: ~23,000 calls, about 1.2 hours — which is why it is only done for priced sets
- Pricing: 2 credits per card against a 20,000/day budget; a 5-set refresh is about 5.5% of a day
- Dev database currently holds ~519,000 price snapshots across five condition grades
- 13 database migrations
- 554 backend tests, 175 frontend tests

---

## Threads worth pulling that are not yet written anywhere

- The project is a portfolio piece *about* data work that itself kept generating real data problems — bad joins, duplicate keys, silent nulls, three names for one entity. The subject matter and the engineering kept converging.
- Almost every hard decision was about what to *not* build, or what to hand back to a human, rather than what to add.
- The docs directory is nearly as large as the backend source. Whether that is a strength or an indulgence is a genuine question and probably an interesting paragraph.
