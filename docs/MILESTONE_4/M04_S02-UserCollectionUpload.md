# M04_S02 — User Collection Upload

## Summary

Build the user-facing infrastructure for uploading a personal card collection. This story covers the new "Analyze Your Collection" page, the downloadable Excel template, the upload and validation flow, the mock collection feature, the session-based storage that keeps the user's data accessible across refreshes, and a placeholder privacy policy page.

This story is responsible for getting the user's collection into a state where the backend has matched it against the database and stored it for the session. It does not include the dashboard rendering itself — that lives in M04_S03.

---

## User Flow

1. User clicks **Analyze Your Collection** in the sidebar
2. Lands on the upload page with three primary actions:
   - **Download Template** — gets a pre-formatted Excel file with column dropdowns
   - **Upload Collection** — submits a filled-out template
   - **Use Mock Collection** — loads a demo collection bundled with the app
3. After a successful upload or mock load, the user is redirected to the dashboard view (built in M04_S03)
4. If validation fails, the user sees an error summary on the page and can download an annotated workbook showing which rows failed

---

## Page Structure

### Route — `/collection`

**File:** `frontend/src/views/CollectionView.vue`
**Breadcrumb:** `Analyze Your Collection`
**Sidebar nav item:** Add **Analyze Your Collection** to the sidebar in `AppLayout.vue` between Market Trends and any future entries. Use the `mdi-book-search` icon.

### Layout

**Top section — page title and intro**

A heading "Analyze Your Collection" with a brief subtitle explaining the feature in one sentence. Below that, a short paragraph describing how it works in plain language: download the template, fill it out, upload it back, get a dashboard.

**Privacy note**

Below the intro, a small line in secondary text:

> Your collection is stored privately for this session and automatically deleted after 24 hours. [View privacy policy](/privacy)

The link goes to the placeholder privacy policy page (see below).

**Three action cards arranged horizontally**

| Card | Action |
|---|---|
| Download Template | Triggers download of the Excel template |
| Upload Collection | Opens a file picker (or accepts drag-and-drop) for `.xlsx` files |
| Use Mock Collection | Loads the bundled demo collection without requiring a file |

Each card uses the surface color, has a relevant `mdi-` icon, a title, a one-sentence description, and a primary-accent button. Hovering elevates the card slightly per the existing design language.

**Validation error area** (conditionally shown)

When an upload fails validation, this section appears below the action cards showing:
- A header: "We couldn't process your upload"
- A summary line: "X of Y rows had errors"
- A list of distinct error types found (e.g. "3 rows have an invalid card number", "1 row is missing a condition")
- A primary button: **Download Annotated Workbook** — returns the user's uploaded file with an `Error` column added explaining each row's issue
- A secondary button: **Try Another File** — clears the error and reopens the file picker

---

## Excel Template

### Filename

Generated dynamically with the current date: `card-collection-template-2026-04-15.xlsx`

### Columns

| Column | Required | Type | Notes |
|---|---|---|---|
| Set | Yes | Dropdown | Populated from sets currently in the database |
| Card Number | Yes | Number | Card's number within the set (e.g. `4`) |
| Card Name | No | Text | For user reference only — not used for matching |
| Condition | Yes | Dropdown | `NM`, `LP`, `MP`, `HP`, `DMG` |
| Variant | No | Free-form text | E.g. `Reverse Holo`, `Shadowless` |
| Is 1st Edition | Yes | Dropdown | `TRUE` / `FALSE` |
| Quantity | Yes | Number | Integer ≥ 1 |
| Purchase Price | No | Number | If provided across all rows, enables ROI KPIs |

### Excel features to apply

- **Frozen header row** so the column titles stay visible while scrolling
- **Data validation dropdowns** on Set, Condition, and Is 1st Edition columns
- **Number format** on Quantity (integer) and Purchase Price (currency)
- **Column widths** sized to fit the longest expected value
- **A second worksheet titled "Instructions"** with brief usage notes including a sample filled-out row, an explanation of the Variant column being free-form, and the note that columns the app doesn't expect (like an `Error` column from a previous failed upload) are ignored on re-upload

### Generation

Use `openpyxl` on the backend to generate the template dynamically each time it's requested. The Set column dropdown is populated from a query against the `sets` table at request time so newly added sets appear without a code change.

### API Endpoint

```
GET /collection/template
```

Returns the `.xlsx` file as a binary response with `Content-Disposition: attachment; filename=...`.

---

## Upload and Validation

### API Endpoint

```
POST /collection/upload
Content-Type: multipart/form-data
Body: file (the .xlsx file)
```

### Validation Rules

The backend reads the workbook with `openpyxl` and validates row by row:

| Rule | Error Message |
|---|---|
| Required column missing from header | "Required column '{name}' is missing — please use the latest template" |
| Set value not in `set_identifiers` | "Set '{value}' is not recognized" |
| Card Number doesn't match a card in the resolved set | "Card number {value} does not exist in {set}" |
| Condition not in {NM, LP, MP, HP, DMG} | "Condition must be NM, LP, MP, HP, or DMG" |
| Is 1st Edition not in {TRUE, FALSE, blank} | "Is 1st Edition must be TRUE or FALSE" |
| Quantity not a positive integer | "Quantity must be a whole number greater than 0" |
| Purchase Price present but not numeric | "Purchase Price must be a number or left blank" |

Columns the app doesn't expect (e.g. `Error`, custom user notes) are silently ignored.

### Validation Behavior

The upload is rejected if **any** required column is missing from the header. If the structure is correct but individual rows have errors, the upload is also rejected — but the user gets the annotated workbook back showing which rows failed.

This means: structural problems = hard fail with a clear error, row problems = soft fail with downloadable feedback.

### Variant Handling — No External Parsing

**The Variant column is free-form text and does NOT use any external API for parsing or normalization.** Apply simple in-process normalization to the user's input:

1. **Split** the input on `,`, `|`, `/`, and `&` separators. Each result becomes a separate variant value.
2. **Trim** leading/trailing whitespace from each split value.
3. **Collapse** multiple internal spaces to a single space.
4. **Title Case with acronym preservation:**
   - Split each variant on whitespace
   - For each word, if the input is entirely uppercase (e.g. `PSA`), preserve it as-is
   - Otherwise, apply Title Case (first letter capitalized, rest lowercase)
   - Rejoin with spaces

Examples:
- `reverse holo` → `Reverse Holo`
- `REVERSE HOLO` → `Reverse Holo` (entirely-uppercase short single words still title-case unless they look like acronyms — see note below)
- `Reverse Holo, Misprint` → `[Reverse Holo, Misprint]` (two separate variants)
- `1st edition holo` → `1st Edition Holo`
- `PSA graded` → `PSA Graded`
- `(blank)` → no variant — store as null/blank

**On the acronym rule edge case:** "ENTIRELY UPPERCASE" means the user typed a word in all caps as an apparent acronym. A word like `PSA` (3 letters, all caps in original input) is preserved. A word like `REVERSE` would also be preserved by this rule strictly speaking — that's fine, we accept the user's intent.

A row with both `Variant = "Reverse Holo"` AND `Is 1st Edition = TRUE` stores both separately:
- `variant` field: `"Reverse Holo"` (normalized)
- `is_first_edition` field: `true`

These are stored as two separate columns on the parsed collection row. The is_first_edition boolean is NOT folded into the variant string. The dashboard's variant chart and slicer (M04_S04) treat them as two separate filter dimensions where the same card can contribute to both — see those stories for the full treatment.

### Annotated Workbook

When validation fails, the backend returns the user's uploaded file with two modifications:

1. **Error column added** at the right-hand side. Blank for valid rows. Contains the error message for invalid rows.
2. **Invalid rows highlighted** with a light red fill (`#5C2828` — a dark red that fits the dark theme even though Excel renders it in its own light theme). Valid rows untouched.

Returned via:

```
POST /collection/upload/annotated
```

This endpoint accepts the original file plus the validation results from the previous upload attempt and returns the annotated `.xlsx`.

---

## Collection Row → Card Matching

For each row in the uploaded workbook, the backend resolves the row to a canonical `card_id` and stores the structured data in the session.

**Matching steps:**

1. `set_name` → `set_id` via the existing `set_identifiers` table (M03_S01)
2. `(set_id, card_number)` → `cards.id` via existing card lookup logic
3. `condition` is stored as-is from the user input (validation guarantees it's one of NM/LP/MP/HP/DMG)
4. `variant` is normalized in-process (per the Variant Handling section above) and stored as the normalized text
5. `is_first_edition` is stored as a separate boolean column on the parsed row
6. `quantity` and `purchase_price` are stored as user-provided

The is_first_edition flag is **not** folded into the variant string. The variant column and the is_first_edition column are independent fields on the parsed collection row.

---

## Session Storage

### Approach

After a successful upload (or mock load), the parsed collection is stored server-side and tied to a session token returned to the client. The token is stored in an `HttpOnly`, `Secure`, `SameSite=Strict` cookie.

### Storage Backend

Use a new database table for session storage. Avoids needing Redis or another service for a portfolio project.

```sql
CREATE TABLE collection_sessions (
    id            TEXT PRIMARY KEY,           -- UUID
    collection    JSONB NOT NULL,             -- the parsed collection
    created_at    TIMESTAMP NOT NULL DEFAULT NOW(),
    expires_at    TIMESTAMP NOT NULL          -- created_at + 24 hours
);

CREATE INDEX idx_collection_sessions_expires ON collection_sessions (expires_at);
```

The `collection` JSONB column stores the parsed and matched collection — a list of objects each containing the `card_id`, `condition`, `variant`, `is_first_edition`, `quantity`, and optional `purchase_price`.

JSONB is intentional. The expected workflow is "load my entire collection" rather than "query across collections," and the entire JSONB blob comes back in a single read. A normalized child table would add complexity without enabling any required workflow.

### No Authentication

This story does not implement authentication. Sessions are anonymous and tied solely to the session cookie. Anyone with the deployed URL can upload a collection. For a portfolio project this is acceptable.

### Session Cleanup

A simple cleanup query runs as part of the nightly GitHub Actions ingestion workflow:

```sql
DELETE FROM collection_sessions WHERE expires_at < NOW();
```

Add this as a step in `.github/workflows/ingest.yml` after the multiplier refresh.

### Session API

```
POST /collection/session
```
Creates a new session from a parsed collection. Returns the session ID and sets the cookie. Called internally after a successful upload or mock load — not directly exposed to the user as a separate action.

```
GET /collection/session
```
Reads the cookie, looks up the session, returns the parsed collection. Used by the dashboard view (M04_S03) to populate itself on page load. Returns 404 if no session exists or the session has expired.

```
DELETE /collection/session
```
Clears the session and the cookie. Called when the user uploads a new collection or clicks "Reset Collection."

---

## Mock Collection

### File Location

`api/assets/mock_collection.xlsx`

A pre-filled version of the collection template with realistic data. The user (you) will create and maintain this file.

**For development purposes, the agent should create a starter mock collection file** containing 15-25 valid rows drawn from sets currently in the database. This ensures the feature can be tested end-to-end immediately. The user can replace this starter file with a curated mock collection later — the file path is what matters, not the specific contents.

The starter mock should:
- Contain only sets currently ingested in the database
- Use a realistic mix of conditions
- Have NO non-standard variants (Variant column blank for all rows) to avoid complicating early testing
- Mix purchase price values — some rows with prices, some blank — to exercise both the with-purchase-price and without-purchase-price code paths

### Behavior

Clicking "Use Mock Collection" hits a backend endpoint that reads this file and processes it through the same upload validation logic as a real upload. This ensures the mock collection passes through the exact same code path as a real upload — making it useful as both a demo feature and a debugging tool.

### API Endpoint

```
POST /collection/mock
```

No request body. Returns the same response shape as `/collection/upload` on success.

---

## Privacy Policy Placeholder

### Route — `/privacy`

**File:** `frontend/src/views/PrivacyView.vue`
**Breadcrumb:** `Privacy Policy`
**Sidebar nav:** Not added to the sidebar — this page is only accessed via the link on the collection page.

### Content

A single page with a heading "Privacy Policy" and placeholder text:

> *Privacy policy content coming soon. Until then, here's what to know:*
>
> - Uploaded collections are stored only for the duration of your session and are automatically deleted after 24 hours.
> - No personal information (name, email, IP address) is collected or retained.
> - Session cookies are used only to associate your uploaded collection with your browser. They contain no tracking data.
> - The data you upload is not shared with third parties or used for any analytics.

This placeholder is sufficient for Milestone 4. A full policy can be drafted in a later milestone.

---

## Dependencies and Setup

### Python Dependencies

Add `openpyxl` to `api/pyproject.toml` if not already present. It's needed for both:
- Generating the upload template (`GET /collection/template`)
- Parsing user-uploaded workbooks (`POST /collection/upload`)
- Annotating workbooks for error feedback (`POST /collection/upload/annotated`)
- Reading the mock collection file (`POST /collection/mock`)

### Post-Upload Redirect

After a successful upload or mock load, redirect the user to `/collection/dashboard`. This route is built in M04_S03. For this story, the route should exist as a placeholder view that shows a brief message:

> Your collection has been loaded. The dashboard is coming in the next update.

The placeholder view can show the count of cards loaded (e.g. "Loaded 47 cards across 3 sets") to confirm the upload worked. Once M04_S03 is implemented, this placeholder is replaced by the full dashboard.

---

## Test Cases

---

### TC01 — Sidebar nav includes Analyze Your Collection

**Steps:** Open the app and look at the sidebar.

**Expected:** A new nav item "Analyze Your Collection" appears below Market Trends with the `mdi-book-search` icon. Clicking it navigates to `/collection`.

---

### TC02 — Template downloads with current sets

**Steps:** From the collection page click **Download Template**.

**Expected:** An `.xlsx` file downloads. The Set column has a dropdown populated with the current sets in the database (Base Set, Jungle, Fossil, Pokémon 151). The Condition and Is 1st Edition columns also have dropdowns. The Instructions worksheet is present.

---

### TC03 — Valid upload creates a session

**Steps:**
1. Download the template
2. Fill in 3-5 valid rows
3. Upload the file

**Expected:** The page redirects to the dashboard placeholder route. A `collection_sessions` row exists in the database with the parsed collection in the `collection` JSONB column. A session cookie is set on the browser.

---

### TC04 — Mock collection loads the bundled file

**Steps:** Click **Use Mock Collection**.

**Expected:** The mock collection processes through the same validation flow and a session is created. No file picker appears. The redirect to the dashboard placeholder happens.

---

### TC05 — Missing required column rejects upload

**Steps:**
1. Open the template, delete the Condition column entirely
2. Upload the modified file

**Expected:** Validation fails. The error area shows "Required column 'Condition' is missing — please use the latest template". No annotated workbook download is offered for structural errors. The user is not redirected to the dashboard.

---

### TC06 — Row errors return annotated workbook

**Steps:**
1. Fill the template with a mix of valid and invalid rows (e.g. one row with `Card Number = 999` for Base Set)
2. Upload

**Expected:** The error area appears showing the count of errored rows and a list of error types. The **Download Annotated Workbook** button is available. Clicking it downloads the user's original file with an Error column added — invalid rows have error messages, valid rows have blank Error cells. Invalid rows have a red fill.

---

### TC07 — Variant normalization splits on separators

**Steps:** Upload a row with `Variant = "Reverse Holo, Misprint"`.

**Expected:** The parsed collection stores two variants for this row: `"Reverse Holo"` and `"Misprint"`. The session JSON reflects this as two separate values associated with the same card.

---

### TC08 — Variant Title Case with acronym preservation

**Steps:** Upload three rows with these variant values:
- Row A: `reverse holo`
- Row B: `1st edition holo`
- Row C: `PSA graded`

**Expected:** Stored variants are `Reverse Holo`, `1st Edition Holo`, `PSA Graded` respectively.

---

### TC09 — Variant column blank treated as Standard

**Steps:** Upload rows with the Variant column empty.

**Expected:** The parsed row's variant field is null/blank. No PPT call is made. No external API is hit during normalization.

---

### TC10 — is_first_edition stored as separate field

**Steps:** Upload a row with `Variant = "Reverse Holo"` and `Is 1st Edition = TRUE`.

**Expected:** The parsed row has both `variant = "Reverse Holo"` AND `is_first_edition = true` as separate fields. The variant string is NOT modified to include "1st Edition".

---

### TC11 — Blank Is 1st Edition treated as FALSE

**Steps:** Upload a row with the Is 1st Edition column blank.

**Expected:** Validation passes. The parsed row has `is_first_edition = false`.

---

### TC12 — Session persists across refresh

**Steps:**
1. Upload a valid collection
2. Refresh the browser

**Expected:** The session is restored — the dashboard placeholder still shows the collection's card count without requiring a re-upload. The session cookie is still present.

---

### TC13 — Session expires after 24 hours

**Steps:**
1. Upload a collection
2. Manually update the session's `expires_at` in the database to a time in the past
3. Refresh the browser

**Expected:** The dashboard placeholder shows the empty state (no collection loaded) and the user is prompted to upload again. The expired session row is eventually cleaned up by the nightly job.

---

### TC14 — Privacy policy link works

**Steps:** From the collection page, click the **View privacy policy** link.

**Expected:** Navigates to `/privacy` showing the placeholder content. Breadcrumb reads `Privacy Policy`.

---

### TC15 — Cookie has correct security flags

**Steps:** After uploading, inspect the session cookie in browser dev tools.

**Expected:** Cookie has `HttpOnly`, `Secure`, and `SameSite=Strict` flags set.

---

### TC16 — Re-upload replaces previous session

**Steps:**
1. Upload a collection
2. Without leaving the app, upload a different collection

**Expected:** The previous session is cleared and replaced. The dashboard placeholder reflects the new collection data, not the old one.

---

### TC17 — Unrecognized columns are ignored on re-upload

**Steps:**
1. Upload a collection with errors
2. Download the annotated workbook
3. Without removing the Error column, fix the rows and re-upload

**Expected:** The re-upload succeeds. The Error column is silently ignored. No error about an unexpected column.

---

### TC18 — Cleanup job removes expired sessions

**Steps:**
1. Manually create a session with `expires_at` in the past
2. Trigger the nightly workflow

**Expected:** After the workflow completes, the expired session row is no longer in the database. Active sessions are not affected.

---

### TC19 — No external API calls during upload

**Steps:** Upload a collection containing rows with various non-standard variants. Watch network egress from the API server.

**Expected:** No outbound calls to `pokemonpricetracker.com` or any other external API are made during the upload flow. Variant normalization is purely in-process.

---

## Notes for the Agent

**No external parser is used for variant handling.** The PPT parse-title API is explicitly not part of this story. All variant normalization happens in-process using the rules described in the Variant Handling section. Do not add PPT credit costs, caching tables, or any infrastructure related to external parsing.

**`is_first_edition` and `variant` are independent fields on the parsed row.** They are NOT combined into a single variant string. The dashboard's variant chart and slicer (M04_S04) treat them as two separate filter dimensions where the same card can contribute to both.

**Mock collection is variant-free for early testing.** The starter mock you generate should have all variants blank to keep early testing simple. The user may expand the mock with variants later.

**JSONB for session storage is intentional.** Don't second-guess this in favor of a normalized child table. The workflow is "load my full collection in one read" — JSONB is the right shape for that.

**No authentication.** Sessions are anonymous and tied to a cookie only. Anyone with the deployed URL can upload. Do not add auth.

**Backend directory is `api/`, not `backend/`.** Earlier drafts of this doc referenced `backend/assets/mock_collection.xlsx`. The correct path is `api/assets/mock_collection.xlsx`.
