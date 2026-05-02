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
**Sidebar nav item:** Add **Analyze Your Collection** to the sidebar in `AppLayout.vue` between Market Trends and any future entries. Use the `mdi-folder-account` icon.

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
| Is 1st Edition not in {TRUE, FALSE} | "Is 1st Edition must be TRUE or FALSE" |
| Quantity not a positive integer | "Quantity must be a whole number greater than 0" |
| Purchase Price present but not numeric | "Purchase Price must be a number or left blank" |
| Variant present but parser returns low confidence | "Variant '{value}' could not be confidently identified — remove this row or update the variant value" |

Columns the app doesn't expect (e.g. `Error`, custom user notes) are silently ignored.

### Validation Behavior

The upload is rejected if **any** required column is missing from the header. If the structure is correct but individual rows have errors, the upload is also rejected — but the user gets the annotated workbook back showing which rows failed.

This means: structural problems = hard fail with a clear error, row problems = soft fail with downloadable feedback.

### Variant Parsing via PPT

If a row has a Variant value, the backend constructs a search string and calls the PokemonPriceTracker `parse-title` endpoint:

```
"{card_name} {set_display_name} {variant} {condition}{ 1st Edition if applicable}"
```

Example: `"Charizard Base Set Reverse Holo NM 1st Edition"`

The parser response is checked for confidence:
- `confidence >= 0.85` — accept the variant as-is
- `confidence < 0.85` — flag the row as an error with the suggestion to remove it

**Caveat for credit budget:** parse-title calls cost API credits. If the user uploads 200 rows with 50 variant entries, that's 50 credits per upload. Worth noting in the docs but not a blocker for Milestone 4.

If the Variant column is blank, no parser call is made and the row is treated as a standard card.

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

The `collection` JSONB column stores the parsed and matched collection — a list of objects each containing the card_id, condition, variant, is_1st_edition, quantity, and optional purchase_price.

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

`backend/assets/mock_collection.xlsx`

A pre-filled version of the collection template with realistic data. The user (you) will create and maintain this file.

### Behavior

Clicking "Use Mock Collection" hits a backend endpoint that reads this file and processes it through the same upload validation logic as a real upload. This ensures the mock collection passes through the exact same code path as a real upload — making it useful as both a demo feature and a debugging tool.

### API Endpoint

```
POST /collection/mock
```

No request body. Returns the same response shape as `/collection/upload` on success.

### Constraints

The mock collection should not contain Variant values to avoid burning PPT credits on every demo click. The doc note about variants being parsed via PPT applies — keeping mock collections variant-free keeps demos fast and free.

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

## Test Cases

---

### TC01 — Sidebar nav includes Analyze Your Collection

**Steps:** Open the app and look at the sidebar.

**Expected:** A new nav item "Analyze Your Collection" appears below Market Trends with the folder-account icon. Clicking it navigates to `/collection`.

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

**Expected:** The page redirects to the dashboard (which won't render data until M04_S03 is complete, but the route should change). A `collection_sessions` row exists in the database with the parsed collection in the `collection` JSONB column. A session cookie is set on the browser.

---

### TC04 — Mock collection loads the bundled file

**Steps:** Click **Use Mock Collection**.

**Expected:** The mock collection processes through the same validation flow and a session is created. No file picker appears. The redirect to the dashboard happens.

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

### TC07 — Variant parsing via PPT

**Steps:** Fill in a row with `Card Name = "Charizard"`, `Variant = "Reverse Holo"`. Upload.

**Expected:** The backend calls the PPT parse-title endpoint. If confidence is high, the row is accepted with the variant stored. If confidence is low, the row is flagged in the error report with the suggestion to remove it.

---

### TC08 — Variant column blank skips PPT call

**Steps:** Upload a collection with all Variant cells blank.

**Expected:** No PPT parse-title API calls are made. Verify by checking the API response logs or PPT credit consumption.

---

### TC09 — Session persists across refresh

**Steps:**
1. Upload a valid collection
2. Refresh the browser

**Expected:** The session is restored — the dashboard still shows the user's collection data without requiring a re-upload. The session cookie is still present.

---

### TC10 — Session expires after 24 hours

**Steps:**
1. Upload a collection
2. Manually update the session's `expires_at` in the database to a time in the past
3. Refresh the browser

**Expected:** The dashboard shows the empty state (no collection loaded) and the user is prompted to upload again. The expired session row is eventually cleaned up by the nightly job.

---

### TC11 — Privacy policy link works

**Steps:** From the collection page, click the **View privacy policy** link.

**Expected:** Navigates to `/privacy` showing the placeholder content. Breadcrumb reads `Privacy Policy`.

---

### TC12 — Cookie has correct security flags

**Steps:** After uploading, inspect the session cookie in browser dev tools.

**Expected:** Cookie has `HttpOnly`, `Secure`, and `SameSite=Strict` flags set.

---

### TC13 — Re-upload replaces previous session

**Steps:**
1. Upload a collection
2. Without leaving the app, upload a different collection

**Expected:** The previous session is cleared and replaced. The dashboard reflects the new collection data, not the old one.

---

### TC14 — Unrecognized columns are ignored on re-upload

**Steps:**
1. Upload a collection with errors
2. Download the annotated workbook
3. Without removing the Error column, fix the rows and re-upload

**Expected:** The re-upload succeeds. The Error column is silently ignored. No error about an unexpected column.

---

### TC15 — Cleanup job removes expired sessions

**Steps:**
1. Manually create a session with `expires_at` in the past
2. Trigger the nightly workflow

**Expected:** After the workflow completes, the expired session row is no longer in the database. Active sessions are not affected.
