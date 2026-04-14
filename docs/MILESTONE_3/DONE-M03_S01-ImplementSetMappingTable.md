# M03_S01 — Implement Set Mapping Table

## Summary

Introduce a `set_identifiers` table that maps canonical set IDs to the names and IDs used by each external data source (TCGdex, PokemonPriceTracker, etc.). Update the ingestion scripts to resolve set identifiers through this table before making any API calls, with hard errors when a mapping is missing.

---

## Problem Being Solved

Different data sources refer to the same Pokémon set using different names and ID formats:

- TCGdex uses IDs like `base1`
- PokemonPriceTracker uses display names like `Base Set`
- TCGPlayer uses numeric IDs

Currently the ingestion scripts pass names directly to APIs without validation, which causes silent failures when names don't match. This story establishes a canonical mapping layer so every API call uses the exact identifier that source expects, and fails loudly when a mapping is missing.

---

## Database Changes

### New Table — `set_identifiers`

```sql
CREATE TABLE set_identifiers (
    id               SERIAL PRIMARY KEY,
    set_id           TEXT NOT NULL REFERENCES sets(id) ON DELETE CASCADE,
    source           TEXT NOT NULL,
    identifier       TEXT NOT NULL,
    identifier_type  TEXT NOT NULL DEFAULT 'name',
    created_at       TIMESTAMP NOT NULL DEFAULT NOW(),
    UNIQUE (set_id, source, identifier_type)
);

CREATE INDEX idx_set_identifiers_source ON set_identifiers (source);
CREATE INDEX idx_set_identifiers_identifier ON set_identifiers (identifier);
```

### Column Definitions

| Column | Type | Description |
|---|---|---|
| `set_id` | TEXT | FK → `sets.id` — the canonical set ID (e.g. `base1`) |
| `source` | TEXT | The data source this identifier belongs to (e.g. `tcgdex`, `ppt`) |
| `identifier` | TEXT | The name or ID that source uses for this set |
| `identifier_type` | TEXT | `id` for numeric/slug identifiers, `name` for display names |

### Source Values

Use these exact strings as the `source` value:

| Source | Description |
|---|---|
| `tcgdex` | TCGdex REST API |
| `ppt` | PokemonPriceTracker API |
| `tcgplayer` | TCGPlayer (reserved for future use) |

### Seed Data — Base Set

Insert the following rows immediately after the migration runs. This covers Base Set which is already in the database:

```sql
INSERT INTO set_identifiers (set_id, source, identifier, identifier_type) VALUES
    ('base1', 'tcgdex', 'base1',    'id'),
    ('base1', 'tcgdex', 'Base Set', 'name'),
    ('base1', 'ppt',    'Base Set', 'name');
```

---

## New Module — `ingestion/set_resolver.py`

Create a new module at `ingestion/set_resolver.py` that handles all set identifier lookups. The ingestion scripts (`tcgdex.py`, `pokemonpricetracker.py`) must never pass a set name directly to an API — they always call this module first.

### `resolve_identifier(search_term, source)` → `str`

Looks up the correct identifier for a given source given any recognizable form of the set name or ID.

**Behavior:**

1. Query `set_identifiers` for any row where:
   - `source` matches the requested source, AND
   - `identifier` matches `search_term` (case-insensitive), OR `set_id` matches `search_term` (case-insensitive)
2. If a match is found, return the `identifier` value for that source and `identifier_type = 'name'` (since most APIs are queried by name). If the source uses an ID type, return that instead — see source-specific notes below.
3. If no match is found, raise a `SetIdentifierNotFoundError` with a clear message telling the operator exactly what to do (see Error Handling section below).

**Source-specific return behavior:**

| Source | Returns |
|---|---|
| `tcgdex` | The `identifier` where `identifier_type = 'id'` (e.g. `base1`) |
| `ppt` | The `identifier` where `identifier_type = 'name'` (e.g. `Base Set`) |

### `register_identifier(set_id, source, identifier, identifier_type)` → `None`

Inserts a new row into `set_identifiers`. Used when an operator has verified a new name and wants to add it before running ingestion.

Raises a `ValueError` if:
- `set_id` does not exist in the `sets` table
- The `(set_id, source, identifier_type)` combination already exists

### `SetIdentifierNotFoundError`

A custom exception class defined in this module. Raised by `resolve_identifier` when no mapping exists.

The error message must include:
- The search term that was used
- The source that was being resolved for
- Exact instructions for what to do next

Example message:
```
No identifier found for search_term='Jungle' source='ppt'.

To fix this:
1. Look up the exact name PokemonPriceTracker uses for this set.
   Visit https://www.pokemonpricetracker.com and search for the set.
2. Once you have the correct name, add it to the set_identifiers table:

   INSERT INTO set_identifiers (set_id, source, identifier, identifier_type)
   VALUES ('jungle', 'ppt', '<correct name here>', 'name');

3. Re-run the ingestion script.
```

---

## Changes to Existing Ingestion Scripts

### `ingestion/tcgdex.py`

Replace any direct use of a set ID string passed to the TCGdex API with a call to `resolve_identifier(search_term, 'tcgdex')` before making the request.

```python
from set_resolver import resolve_identifier, SetIdentifierNotFoundError

tcgdex_id = resolve_identifier(set_id_or_name, 'tcgdex')
# use tcgdex_id in the API call
```

### `ingestion/pokemonpricetracker.py`

Replace any direct use of a set name passed to the PPT API with a call to `resolve_identifier(search_term, 'ppt')` before making the request.

```python
from set_resolver import resolve_identifier, SetIdentifierNotFoundError

ppt_name = resolve_identifier(set_id_or_name, 'ppt')
# use ppt_name in the API call
```

### `ingestion/run.py`

The entry point already accepts a `--set-id` argument. No change to the interface is needed — `run.py` passes the value straight through to the resolver, which handles all lookup logic.

---

## Alembic Migration

Create a new Alembic migration that:
1. Creates the `set_identifiers` table with the schema above
2. Inserts the Base Set seed data

The migration must be reversible — the `downgrade()` function should drop the table.

---

## Test Cases

Run these manually after the agent has implemented the story to verify correct behavior. Use the Neon SQL editor for database queries and run ingestion commands from the `ingestion/` directory with the venv active.

---

### TC01 — Table exists with correct structure

**Steps:**
```sql
SELECT column_name, data_type 
FROM information_schema.columns 
WHERE table_name = 'set_identifiers'
ORDER BY ordinal_position;
```

**Expected:** Columns `id`, `set_id`, `source`, `identifier`, `identifier_type`, `created_at` are present with correct types.

---

### TC02 — Base Set seed data is present

**Steps:**
```sql
SELECT * FROM set_identifiers WHERE set_id = 'base1' ORDER BY source, identifier_type;
```

**Expected:** Three rows — one for `tcgdex/id`, one for `tcgdex/name`, one for `ppt/name`.

---

### TC03 — Resolve by canonical ID

**Steps:** Run the following in a Python shell from `ingestion/`:
```python
from set_resolver import resolve_identifier
print(resolve_identifier('base1', 'tcgdex'))
print(resolve_identifier('base1', 'ppt'))
```

**Expected:**
- `base1` for tcgdex
- `Base Set` for ppt

---

### TC04 — Resolve by display name (case-insensitive)

**Steps:**
```python
from set_resolver import resolve_identifier
print(resolve_identifier('base set', 'tcgdex'))
print(resolve_identifier('BASE SET', 'ppt'))
```

**Expected:**
- `base1` for tcgdex
- `Base Set` for ppt

---

### TC05 — Missing mapping raises correct error

**Steps:**
```python
from set_resolver import resolve_identifier, SetIdentifierNotFoundError
try:
    resolve_identifier('Jungle', 'ppt')
except SetIdentifierNotFoundError as e:
    print(str(e))
```

**Expected:** A `SetIdentifierNotFoundError` is raised. The error message contains:
- The search term `Jungle`
- The source `ppt`
- Instructions including the INSERT statement to fix it

---

### TC06 — Error message contains actionable SQL

**Steps:** Same as TC05.

**Expected:** The error message contains a complete `INSERT INTO set_identifiers` statement with placeholders that make it clear exactly what to fill in.

---

### TC07 — TCGdex ingestion uses resolved ID

**Steps:**
1. Add a deliberate typo to the Base Set entry — temporarily update the `tcgdex` `id` identifier to `base1-wrong`:
```sql
UPDATE set_identifiers SET identifier = 'base1-wrong' 
WHERE set_id = 'base1' AND source = 'tcgdex' AND identifier_type = 'id';
```
2. Run the ingestion script:
```bash
python run.py --set-id base1
```
3. Observe the error from the TCGdex API (it should 404 or return empty results)
4. Restore the correct value:
```sql
UPDATE set_identifiers SET identifier = 'base1' 
WHERE set_id = 'base1' AND source = 'tcgdex' AND identifier_type = 'id';
```

**Expected:** The ingestion script uses the value from the table (the wrong one), gets an error from TCGdex, and fails. After restoring the correct value, re-running succeeds.

---

### TC08 — PPT ingestion uses resolved name

**Steps:**
1. Temporarily break the PPT name:
```sql
UPDATE set_identifiers SET identifier = 'Wrong Name'
WHERE set_id = 'base1' AND source = 'ppt' AND identifier_type = 'name';
```
2. Run ingestion and observe that PPT returns no cards (or an error)
3. Restore:
```sql
UPDATE set_identifiers SET identifier = 'Base Set'
WHERE set_id = 'base1' AND source = 'ppt' AND identifier_type = 'name';
```

**Expected:** Same as TC07 — the script uses the table value, fails gracefully with the wrong name, succeeds after restoration.

---

### TC09 — Unique constraint prevents duplicate mappings

**Steps:**
```sql
INSERT INTO set_identifiers (set_id, source, identifier, identifier_type)
VALUES ('base1', 'tcgdex', 'duplicate', 'id');
```

**Expected:** A unique constraint violation error. The second insert is rejected.

---

### TC10 — Foreign key prevents orphaned identifiers

**Steps:**
```sql
INSERT INTO set_identifiers (set_id, source, identifier, identifier_type)
VALUES ('nonexistent-set', 'ppt', 'Some Set', 'name');
```

**Expected:** A foreign key violation error. The insert is rejected because `nonexistent-set` does not exist in `sets`.
