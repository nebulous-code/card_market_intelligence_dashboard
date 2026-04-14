# M03_S02 — Improve Card Matching Logs, Artifacts, and Email Summary

## Summary

Improve the visibility of card number matching during ingestion by adding structured per-card and per-set logging, ensuring all ingestion modules write to a shared log file, uploading the full log as a GitHub Actions artifact after each run, and emailing a nightly summary on completion.

---

## Goals

- Per-card log messages at appropriate levels (DEBUG for success, WARNING for skips, ERROR for failures)
- A human-readable summary line per set at INFO level showing matched vs. skipped counts and which cards were skipped
- All ingestion modules writing to the same `ingestion.log` file
- The complete log uploaded as a GitHub Actions artifact with a 7-day retention window
- A nightly email summary delivered via Gmail SMTP containing the per-set summary and any errors, with a link to the full artifact

---

## Logging Changes

### Shared Log File

All ingestion modules must write to the same log file. The `FileHandler` currently configured in `loader.py` must be moved to a central logging setup module or to `run.py` so it is initialized once at startup and inherited by all child loggers.

The log file path should be `ingestion/ingestion.log`. GitHub Actions will upload this file as an artifact at the end of the workflow.

**Every module in the ingestion package must use:**
```python
log = logging.getLogger(__name__)
```

And must NOT configure its own `FileHandler` or call `logging.basicConfig()`. Only `run.py` (the entry point) should configure handlers. This ensures a single log file captures output from all modules.

### Log Levels

| Event | Level | Notes |
|---|---|---|
| Card matched successfully | `DEBUG` | Includes card name, PPT number, resolved card ID, price values |
| Card skipped — no match found | `WARNING` | Includes card name, PPT number, what was searched, similar numbers found nearby |
| Card skipped — no price data | `WARNING` | Card matched but PPT returned no prices |
| Card skipped — promo or variant | `WARNING` | Card number contains non-numeric characters |
| Matching process error | `ERROR` | Unexpected exception during matching — includes full traceback |
| Per-set summary | `INFO` | Always shown — see format below |
| Run-level summary | `INFO` | Always shown — see format below |

### Per-Card Log Format

**Success (DEBUG):**
```
[base1] MATCHED: 'Charizard' PPT#4 → base1-4 | market=$399.99 low=$275.00
```

**Skip — no match (WARNING):**
```
[base1] SKIPPED (no match): 'Pikachu' PPT#58 — searched for '58', not found in cards table.
  Cards with nearby numbers: 57 (Pidgey), 59 (Poliwag), 60 (Poliwhirl)
```

**Skip — no price data (WARNING):**
```
[base1] SKIPPED (no price): 'Machamp' PPT#8 matched base1-8 but PPT returned no price data
```

**Error (ERROR):**
```
[base1] ERROR matching 'Voltorb' PPT#99: <exception message>
```

### Per-Set Summary Format

Logged at `INFO` level after each set completes. Always includes the skipped card list, even if empty:

```
─────────────────────────────────────────────
Base Set ingestion complete
  PPT cards returned : 100
  Matched            : 97
  Skipped            : 3
  Errors             : 0
  Skipped cards      : base1-8 (Machamp), base1-58 (Pikachu), base1-62 (Poliwrath)
─────────────────────────────────────────────
```

If no cards were skipped:
```
  Skipped cards      : none
```

### Run-Level Summary Format

Logged at `INFO` level after all sets complete. This is what gets included in the email body:

```
═════════════════════════════════════════════
Nightly ingestion complete — 2026-04-14
  Sets processed : 4
  Total matched  : 389
  Total skipped  : 11
  Total errors   : 0
  Overall status : ✅ Success

Per-set breakdown:
  Base Set    97/102 matched, 5 skipped
  Jungle     63/64  matched, 1 skipped
  Fossil     61/62  matched, 1 skipped
  151       162/165 matched, 3 skipped

Warnings:
  [base1] base1-8 (Machamp) — no match
  [jungle] jungle-1 (Clefable) — no match
  ... (full list)
═════════════════════════════════════════════
```

Status is `✅ Success` if errors = 0, `⚠️ Warnings` if skipped > 0 but errors = 0, `❌ Failed` if errors > 0.

---

## GitHub Actions Changes

### Artifact Upload

Add an artifact upload step to `.github/workflows/ingest.yml` that runs after the ingestion script completes, even if the script fails (`if: always()`).

```yaml
- name: Upload ingestion log
  if: always()
  uses: actions/upload-artifact@v4
  with:
    name: ingestion-log-${{ github.run_id }}
    path: ingestion/ingestion.log
    retention-days: 7
```

The `retention-days: 7` setting is intentional — logs older than 7 days are automatically deleted to avoid consuming GitHub storage quota.

### Email Summary

Add an email step after the artifact upload. Uses `dawidd6/action-send-mail` with Gmail SMTP.

```yaml
- name: Send ingestion summary email
  if: always()
  uses: dawidd6/action-send-mail@v3
  with:
    server_address: smtp.gmail.com
    server_port: 465
    secure: true
    username: ${{ secrets.GMAIL_USERNAME }}
    password: ${{ secrets.GMAIL_APP_PASSWORD }}
    subject: "[Card Market] Nightly Ingestion — ${{ env.RUN_DATE }} — ${{ env.RUN_STATUS }}"
    to: ${{ secrets.NOTIFY_EMAIL }}
    from: Card Market Ingestion <${{ secrets.GMAIL_USERNAME }}>
    body: ${{ env.EMAIL_BODY }}
```

The `RUN_DATE`, `RUN_STATUS`, and `EMAIL_BODY` environment variables must be written by the ingestion script to `$GITHUB_ENV` at the end of the run so the workflow step can read them.

### Writing to GITHUB_ENV

At the end of `run.py`, after the run-level summary is logged, write the summary to the GitHub Actions environment file if it exists:

```python
import os

github_env = os.environ.get("GITHUB_ENV")
if github_env:
    with open(github_env, "a") as f:
        f.write(f"RUN_DATE={run_date}\n")
        f.write(f"RUN_STATUS={run_status}\n")
        # EMAIL_BODY is multiline — use GitHub's heredoc syntax
        f.write(f"EMAIL_BODY<<EOF\n{email_body}\nEOF\n")
```

This block only fires when running inside GitHub Actions (when `GITHUB_ENV` is set). It does nothing when running locally.

### GitHub Secrets Required

Add the following secrets to the repository under **Settings → Secrets and variables → Actions**:

| Secret | Description |
|---|---|
| `GMAIL_USERNAME` | The Gmail address used to send the email (e.g. `yourname@gmail.com`) |
| `GMAIL_APP_PASSWORD` | A Gmail App Password — NOT your regular Gmail password. Generate one at myaccount.google.com → Security → App Passwords |
| `NOTIFY_EMAIL` | The address to send the summary to (can be the same as `GMAIL_USERNAME`) |

**Important:** `GMAIL_APP_PASSWORD` requires 2-factor authentication to be enabled on the Gmail account before App Passwords can be generated.

---

## Updated `ingest.yml` Structure

The full workflow file should follow this step order:

1. Checkout repository
2. Set up Python
3. Install dependencies
4. Run ingestion script
5. Upload ingestion log artifact (`if: always()`)
6. Send email summary (`if: always()`)

Steps 5 and 6 use `if: always()` so they run even when the ingestion script exits with a non-zero status code. This ensures you always get an email and always get a log file, even on failure.

---

## Test Cases

---

### TC01 — Single log file captures all modules

**Steps:**
1. Delete `ingestion/ingestion.log` if it exists
2. Run the ingestion script locally:
```bash
python run.py --set-id base1
```
3. Open `ingestion/ingestion.log`

**Expected:** The log file exists and contains output from all modules — lines referencing `loader`, `pokemonpricetracker`, `set_resolver`, and `run`. No module should be missing from the log.

---

### TC02 — DEBUG messages appear when log level is DEBUG

**Steps:**
```bash
LOG_LEVEL=DEBUG python run.py --set-id base1
```

**Expected:** The log contains per-card `MATCHED` lines for every successfully matched card. Each line includes the card name, PPT number, resolved card ID, and price values.

---

### TC03 — WARNING appears for unmatched card

**Steps:**
1. Temporarily insert a fake PPT card number that won't match anything. This can be simulated by temporarily adding a card number that doesn't exist in the database to the matching logic, or by checking existing skip warnings in a normal run.
2. Run ingestion and check the log.

**Expected:** A `SKIPPED (no match)` WARNING line appears containing the card name, PPT number, what was searched, and a list of nearby card numbers from the database.

---

### TC04 — Per-set summary line appears at INFO level

**Steps:**
```bash
python run.py --set-id base1
```

**Expected:** The log contains a per-set summary block showing PPT cards returned, matched count, skipped count, error count, and the list of skipped card IDs with names.

---

### TC05 — Run-level summary appears at end of log

**Steps:**
```bash
python run.py --set-id base1
```

**Expected:** The last section of the log contains the run-level summary with total counts across all sets and an overall status of `✅ Success`, `⚠️ Warnings`, or `❌ Failed`.

---

### TC06 — Log file is uploaded as artifact in GitHub Actions

**Steps:**
1. Trigger the workflow manually from the GitHub Actions tab
2. Wait for the run to complete
3. On the completed run page, look for the **Artifacts** section

**Expected:** An artifact named `ingestion-log-{run_id}` is present and downloadable. Verify the artifact retention is set to 7 days by checking the expiry date shown next to the artifact.

**Note:** Set artifact retention to 7 days in the workflow file (`retention-days: 7`). This prevents the log files from accumulating and consuming GitHub storage quota. GitHub's free plan has a 500 MB storage limit for artifacts — at one log file per day, even a 1 MB log would fill 500 days of storage if retention is left at the default 90 days.

---

### TC07 — Email is received after successful run

**Steps:**
1. Ensure `GMAIL_USERNAME`, `GMAIL_APP_PASSWORD`, and `NOTIFY_EMAIL` secrets are set in GitHub
2. Trigger the workflow manually
3. Check the inbox of `NOTIFY_EMAIL`

**Expected:** An email arrives with:
- Subject containing `✅ Success`, `⚠️ Warnings`, or `❌ Failed` depending on the run outcome
- Body containing the per-set breakdown and any warning/error messages
- The run date in the subject line

---

### TC08 — Email is received even when ingestion fails

**Steps:**
1. Temporarily introduce a failure — e.g. set `DATABASE_URL` to an invalid value in the GitHub Actions secrets, or add a deliberate syntax error to `run.py` on a test branch
2. Trigger the workflow
3. Check the inbox

**Expected:** The workflow run shows as failed but an email is still received. The subject contains `❌ Failed`. The artifact log is also still uploaded.

**Restore:** Revert the deliberate failure before merging.

---

### TC09 — Email is not sent when running locally

**Steps:**
```bash
python run.py --set-id base1
```

**Expected:** No email is sent. The `GITHUB_ENV` block in `run.py` does nothing because the `GITHUB_ENV` environment variable is not set locally. Confirm by checking that no SMTP connection attempt appears in the log.

---

### TC10 — Gmail App Password setup

This is a setup verification step, not a code test.

**Steps:**
1. Go to [myaccount.google.com](https://myaccount.google.com)
2. Navigate to **Security → 2-Step Verification** — confirm it is enabled
3. Navigate to **Security → App Passwords**
4. Generate a new App Password with the name `GitHub Actions Card Market`
5. Copy the 16-character password immediately — it is only shown once
6. Add it as the `GMAIL_APP_PASSWORD` secret in GitHub

**Expected:** The App Password is stored in GitHub secrets and the email step in TC07 succeeds. If the App Passwords option is not visible, 2-Step Verification is not enabled — enable it first.
