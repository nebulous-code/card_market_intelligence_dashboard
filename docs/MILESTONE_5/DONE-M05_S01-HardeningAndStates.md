# M05_S01 — Hardening and Interface States

## Summary

Milestone 5 was originally scoped as "Polish and Hardening" with four items: API key authentication, error and empty states, expanded documentation, and production hardening. This story covers what turned out to be genuinely necessary and records why the rest was dropped.

Three things shipped: resource caps on the upload endpoints, rate limiting on the three write endpoints, and a pass over every view that fetches data so a failure looks like a failure rather than an empty database.

---

## Why there is no API key authentication

The original scope called for it. It is not here, and this is not a deferral.

The frontend is a public single-page app. Any key it carries ships inside the JavaScript bundle and is readable from devtools in seconds, so it would authenticate nothing while adding a step between a reviewer and a working demo.

There is also nothing to protect. Of the 23 endpoints, 19 are public reads of card and price data that is not secret. The four writes — `POST /collection/upload`, `POST /collection/upload/annotated`, `POST /collection/mock`, and `DELETE /collection/session` — all operate on a single row scoped to the caller's own session cookie. There are no accounts, no admin surface, no cross-user access, and no personal data beyond a collection the user chose to upload about themselves.

**The real threat model is resource abuse, not unauthorized access**, and keys do not address it. What does is bounding what a single request can consume and how often a caller can make one. That is what this story builds.

Authentication becomes necessary the moment the Milestone 6 admin panel exists, or a third-party API is exposed. Not before.

---

## Upload resource caps

### The problem

Both upload endpoints read the request body with no bound at all:

```python
file_bytes = await file.read()
```

That exposes three separate failure modes, and a naive byte cap only closes the first.

**Raw size.** An arbitrarily large body is read into the process.

**Decompression.** An `.xlsx` is a zip archive, and openpyxl expands it on open. Measured by building collection workbooks of varying size and loading them under `tracemalloc`:

| rows | on-wire | uncompressed | ratio | openpyxl heap | heap / uncompressed |
| --- | --- | --- | --- | --- | --- |
| 1,000 | 30,408 | 384,965 | 12.7x | 3,168,416 | 8.2x |
| 5,000 | 129,982 | 1,896,965 | 14.6x | 15,240,910 | 8.0x |
| 20,000 | 503,626 | 7,656,984 | 15.2x | 61,110,816 | 8.0x |

Two findings drive the thresholds. openpyxl's in-memory model costs a consistent **8x the uncompressed XML**, and the compression ratio **rises with row count** — repeated cell XML compresses well, so a cap calibrated against a near-empty template would reject large-but-legitimate uploads.

**Row count.** `collection_validator._resolve_card_id` issues one database query per row, so a tall sheet is a database problem at a trivial file size, entirely independent of bytes.

### Thresholds

| guard | default | reasoning |
| --- | --- | --- |
| `MAX_UPLOAD_BYTES` | 5 MB | ~40x a large real collection |
| `MAX_UNCOMPRESSED_BYTES` | 8 MB | caps openpyxl near 64 MB; two concurrent uploads survive a 512 MB instance |
| `MAX_COMPRESSION_RATIO` | 100x | 6.6x clear of the observed 15.2x maximum |
| `MAX_ZIP_MEMBERS` | 1,000 | a zip of many tiny entries is its own denial of service |
| `MAX_DATA_ROWS` | 2,000 | see below; a large personal collection, inside the frontend's timeout |

The uncompressed cap is the load-bearing one. `check_row_count` runs *after* `load_workbook`, so it protects the database but cannot protect memory — by the time it executes, openpyxl has already materialized every cell. An earlier draft used 50 MB here, which would have permitted roughly 400 MB of heap from a 3 MB upload that passed every other check: an out-of-memory kill rather than a 413.

All five are environment-overridable and read at call time, so they can be tightened in production without a code change.

### The row-count message

`sheet.max_row` reports the sheet's *used range*, not its populated rows. Excel routinely leaves a stale used range behind when someone clears row contents rather than deleting the rows, so a visibly small workbook can legitimately report hundreds of thousands of rows. Rejecting it is still correct — iteration really would walk them — but the message has to tell an honest user how to fix a file that looks fine to them, so it explains deleting the rows rather than their contents.

### Malformed payloads no longer return 500

`validate_workbook` and `annotate_workbook` call `openpyxl.load_workbook` on untrusted bytes, and nothing caught what it threw. Three payloads were probed:

| payload | raised | before | after |
| --- | --- | --- | --- |
| plain text | `zipfile.BadZipFile` | 500 | 422 |
| valid zip, not an xlsx | `KeyError: [Content_Types].xml` | 500 | 422 |
| xlsx with corrupt sheet XML | `xml.etree.ElementTree.ParseError` | 500 | 422 |

The second is caught by asserting the OOXML skeleton is present in the archive, which is free — the central directory is already parsed. The third needs a `try` around `load_workbook` itself. That clause catches bare `Exception` deliberately: openpyxl has no common base class for its failure modes, so an explicit tuple would silently regress on the next release.

`POST /collection/upload/annotated` previously raised no `HTTPException` at all and now shares the same guards.

---

## Rate limiting

Hand-rolled in `api/middleware/rate_limit.py` rather than pulled from a library. Render's free tier runs a single instance, so in-process state is the correct scope, and the behaviour needed is small enough that a dependency would cost more than it saves.

**Default: 10 write requests per IP per 10 minutes.** Uploading a collection is a once-then-fix activity — upload, hit validation errors, correct the sheet, retry. Ten in ten minutes sits comfortably above that and far below what a script does.

Design points that were not obvious:

**Client identity comes from `X-Forwarded-For`.** Behind Render's proxy the socket peer is always the proxy, so keying on `request.client.host` would put every user in the world in one bucket and throttle the entire site the moment one person uploaded too often.

**A sliding window, not a fixed one.** A fixed window lets a caller spend a full allowance either side of the boundary — twice the intended burst at exactly the wrong moment.

**The store evicts.** A plain dict keyed by a caller-supplied header is a slow memory leak that an attacker could drive deliberately by rotating the header. Expired entries are dropped on each check and the total key count is capped.

### The middleware ordering trap

Starlette's `add_middleware` inserts at position 0, so **the last middleware registered is the outermost**. Registering the limiter after CORS put it outside, and its 429 went out with no `Access-Control-Allow-Origin` — a browser reports that as an opaque network failure, so the frontend never sees the status or the message. Verified before and after:

```
middleware order (outermost first): RateLimitMiddleware, CORSMiddleware
second request: 429   ACAO=None
```

The limiter is now registered **before** CORS, and `expose_headers=["Retry-After"]` was added so cross-origin JavaScript can read the wait time — that header is not on the CORS-safelisted list, so without it the frontend can see the 429 but not how long to wait. A regression test asserts both.

### What this is and is not

Client identity comes from a header the client can set, and counters reset when the process restarts. Both are acceptable, because the worst outcome is that a determined attacker evades their own limit — no worse than having no limiter. **This is a politeness control, not a security boundary.** The protection that cannot be bypassed is the size caps above, which apply per request regardless of who the caller claims to be.

---

## Empty and error states

### What was wrong

| location | defect |
| --- | --- |
| `SetListView` | `try/finally` with no `catch`. A failed request rendered "No sets found" — reporting the database as empty during an outage |
| `SetDetailView` | No `catch`. `/sets/bogus` rendered a breadcrumb, an empty chart and an empty table, with no indication the set did not exist |
| `CollectionDashboardView` | Content gated on `cards.length > 0`, so a zero-row session rendered a header and a button over blank space |
| `ConditionMultiplierHeatmap` | Errors deliberately collapsed into the empty state, so an outage read as "not enough price data yet" |
| `CardDetail` | Leaked axios' own string to the user: `Failed to load card: Request failed with status code 404` |
| `router/index.js` | No catch-all route. An unmatched URL rendered the nav bar and a blank body |

The through-line is that **an error and an absence were being rendered identically**, which tells the user a story about their data when the truth was about the server.

### What was built

**`src/utils/errorMessage.js`** — a pure function mapping a thrown request error to human copy. Deliberately placed in `src/utils` because that path is inside the coverage allow-list, so the branchy status-mapping logic is gated at 100% instead of living untested inside `.vue` files. Handles 404, 413, 422, 429, 5xx, timeout and offline, prefers the server's own `detail` when it sent a usable one, and reads `Retry-After` off a 429.

The timeout copy says the server "may be waking up" — the API sleeps on Render's free tier and takes about 30 seconds to wake, while the axios timeout is 15 seconds, so a first visit routinely times out through no fault of anyone's.

**`src/components/ErrorState.vue`** — the missing sibling to the existing `EmptyState.vue`, rendered as the `v-alert` treatment that was already copy-pasted across four views. Carries an optional retry button, since every previous error state was terminal and the only way out was a manual refresh.

**`src/views/NotFoundView.vue`** and a catch-all route. The deployment rewrites every path to `index.html` so client-side routing survives a refresh, which meant a typo'd URL previously rendered the nav bar and nothing else.

Ordering matters in every template that got both: **the error branch is checked before the empty branch**, because a failed request also leaves the collection empty and the empty state would otherwise win.

### Dead code removed

`LoadingSkeleton.vue` was imported by nothing. `Dashboard.vue` was not routed and imported nowhere, and was the sole importer of `SetSummaryCard.vue` and `PriceChart.vue` — a self-contained island of four files. All deleted. Beyond tidiness, `Dashboard.vue` and `PriceChart.vue` were the only users of a `v-alert type="info"` empty-state dialect, so removing them retired an entire competing style for free.

---

## Configuration

New optional variables, all with safe defaults and all read at call time:

| variable | default |
| --- | --- |
| `MAX_UPLOAD_BYTES` | 5242880 |
| `MAX_UNCOMPRESSED_BYTES` | 8388608 |
| `MAX_COMPRESSION_RATIO` | 100 |
| `MAX_ZIP_MEMBERS` | 1000 |
| `MAX_DATA_ROWS` | 2000 |
| `RATE_LIMIT_MAX_REQUESTS` | 10 |
| `RATE_LIMIT_WINDOW_SECONDS` | 600 |

A malformed value falls back to the default rather than raising, so a typo in the Render dashboard cannot take the API down at request time, and cannot widen a limit to zero or negative.

`.env.example` was also brought back in line — it had drifted, documenting neither `FRONTEND_URL` nor `SESSION_COOKIE_SECURE` despite both being read by the code.

---

## Known limitations

**Upload time is network round trips, not database work.** `_resolve_card_id` runs one query per row. Measured against the Neon dev instance:

```
EXPLAIN ANALYZE:     Seq Scan on cards ... Execution Time: 0.041 ms
lookup round trip:   43.8 ms
SELECT 1 round trip: 43.5 ms   <- pure network
query work:           0.3 ms
```

The query costs nothing to execute; the entire per-row cost is the round trip. End-to-end uploads confirmed it is linear at ~48 ms/row from a developer machine (100 rows in 5.2 s, 400 in 19.4 s, 1,000 in 48.2 s).

That means the practical ceiling is set by how far the API sits from the database, not by anything about Neon's capacity. **Both the Render service and the Neon instance are in `us-east-1`**, so in production the per-row cost is a same-region round trip and 2,000 rows lands in the low seconds.

From a developer machine it will not be — the round trip measured 43.5 ms from here, so a 2,000-row upload takes around 96 seconds locally. That is an artifact of the developer's distance from `us-east-1`, not a production limit, and it now completes rather than timing out because uploads carry their own 120-second budget.

Both follow-ups this raised were done in [M05_S02](./M05_S02-BatchedCardLookup.md): the lookup is now a single batched query, and `cards` gained a composite index on `(set_id, number)`. A 1,000-row upload went from 48 seconds to under one, and the row cap became a product decision rather than a technical ceiling.

**`read_capped` cannot prevent a large body being received**, because FastAPI awaits `request.form()` before resolving dependencies — Starlette has already spooled the body before any handler code runs. This surfaced in testing as a real defect: a large file uploaded from a browser timed out at 15 seconds and reported "the server took too long to respond", hiding the 413 the server was about to send.

Two changes closed it. `api/middleware/body_limit.py` refuses an oversized upload on its `Content-Length` header, before a single byte is read — a 1.5 GB upload went from a 3.7-second rejection to 0.0012 seconds. And uploads now carry a 120-second axios timeout instead of the global 15 seconds, which suits a small JSON read but not a transfer that spends most of its budget pushing bytes.

The header check is a courtesy rather than a boundary: `Content-Length` is client-supplied and absent under chunked encoding, so `read_capped` still counts real bytes and remains the enforcement.

---

## Validation

- `tools/test.sh` — 457 tests, 100% coverage including both new modules.
- `npm run test:coverage` — 171 tests, 100% on the allow-list including `errorMessage.js` (23 cases).
- `npm run build` — clean.
- Probed against a running local API: plain text and non-workbook zips return 422, a decompression bomb returns 413, and the eighth write in a window returns 429 carrying `Retry-After`, `Access-Control-Allow-Origin` and `Access-Control-Expose-Headers`.

Interface states need to be exercised by hand — views sit outside the coverage allow-list by a documented decision, so no automated test asserts what a person actually sees.
