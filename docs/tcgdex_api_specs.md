# TCGdex API Reference

Internal reference for the TCGdex REST API. This document covers the endpoints, response shapes, and query capabilities used by the ingestion layer. The official documentation is at [tcgdex.dev](https://tcgdex.dev).

---

## Overview

| Property | Value |
| --- | --- |
| Base URL | `https://api.tcgdex.net/v2/{language}` |
| Language (default) | `en` |
| Authentication | None — all endpoints are public |
| Methods | GET only |
| Response format | JSON |
| Protocol | HTTPS only (HTTP redirects automatically) |

---

## Endpoints

### Get a set

``` api
GET /sets/{setId}
```

Returns the full set object including embedded card list (brief).

**Example:** `https://api.tcgdex.net/v2/en/sets/base1`

**Response:** [Set object](#set-object)

---

### List all sets

``` api
GET /sets
```

Returns an array of `SetBrief` objects. Supports [filtering, sorting, and pagination](#filtering-sorting-and-pagination).

---

### Get a card

``` api
GET /cards/{cardId}
```

Returns the full card object for a given card ID. Card IDs are formatted as `{setId}-{localId}` (e.g., `base1-4`).

**Example:** `https://api.tcgdex.net/v2/en/cards/base1-4`

**Response:** [Card object](#card-object)

**404 response:**
``` json
{ "error": "Endpoint or id not found" }
```

---

### List all cards

``` api
GET /cards
```

Returns an array of `CardBrief` objects across all sets. Supports [filtering, sorting, and pagination](#filtering-sorting-and-pagination).

**CardBrief shape:**
``` json
{
  "id": "base1-4",
  "localId": "4",
  "name": "Charizard",
  "image": "https://assets.tcgdex.net/en/base/base1/4"
}
```

---

## Set Object

| Field | Type | Nullable | Description |
| --- | --- | --- | --- |
| `id` | string | No | Unique set identifier (e.g., `base1`) |
| `name` | string | No | Set display name |
| `serie` | object | No | Parent series — has `id` and `name` fields |
| `releaseDate` | string | No | Format: `YYYY-MM-DD` |
| `cardCount` | object | No | See below |
| `cardCount.total` | number | No | All cards including hidden |
| `cardCount.official` | number | No | Count printed on physical cards |
| `cardCount.reverse` | number | No | Reverse holo variants |
| `cardCount.holo` | number | No | Holo variants |
| `cardCount.firstEd` | number | No | First edition variants |
| `cards` | CardBrief[] | No | Brief list of all cards in the set |
| `logo` | string | Yes | Logo asset base URL |
| `symbol` | string | Yes | Symbol asset base URL |
| `legal` | object | No | `{ standard: boolean, expanded: boolean }` |
| `tcgOnline` | string | Yes | TCG Online set code |
| `boosters` | array | Yes | Booster product entries |

**Image URLs** — append a format extension to asset base URLs:
``` urls
{logo}.png
{logo}.webp
{symbol}.png
```

---

## Card Object

### Core fields (all card types)

| Field | Type | Nullable | Description |
| --- | --- | --- | --- |
| `id` | string | No | Globally unique card ID (e.g., `base1-4`) |
| `localId` | string | No | Card number within its set |
| `name` | string | No | Official card name |
| `category` | string | No | `"Pokemon"`, `"Trainer"`, or `"Energy"` |
| `set` | SetBrief | No | Parent set — has `id`, `name`, `cardCount`, `logo`, `symbol` |
| `variants` | object | No | `{ normal, reverse, holo, firstEdition }` — all boolean |
| `image` | string | Yes | Asset base URL — append `/high.png` or `/low.png` |
| `rarity` | string | Yes | Rarity string (e.g., `"Rare Holo"`) |
| `illustrator` | string | Yes | Card artist name |
| `updated` | string | No | ISO 8601 timestamp of last data update |
| `boosters` | array | Yes | Booster packs containing this card |
| `pricing` | object | Yes | See [Pricing](#pricing) |

### Pokémon-specific fields

| Field | Type | Nullable |
| --- | --- | --- |
| `hp` | number | Yes |
| `types` | string[] | Yes |
| `stage` | string | Yes |
| `evolveFrom` | string | Yes |
| `description` | string | Yes |
| `level` | string | Yes |
| `attacks` | array | Yes |
| `weaknesses` | array | Yes |
| `retreat` | number | Yes |
| `dexId` | number[] | Yes |
| `suffix` | string | Yes |
| `item` | object | Yes |
| `regulationMark` | string | Yes |

### Trainer-specific fields

| Field | Type | Nullable |
| --- | --- | --- |
| `effect` | string | No |
| `trainerType` | string | No |

### Energy-specific fields

| Field | Type | Nullable |
| --- | --- | --- |
| `effect` | string | No |
| `energyType` | string | No |

### Pricing

The `pricing` field, when present, contains data from two sources:

**TCGPlayer** — `pricing.tcgplayer`

- Per-variant pricing objects (`normal`, `holofoil`, `reverseHolofoil`, `1stEdition`)
- Each variant: `low`, `mid`, `high`, `market` (all numeric, USD)
- `updated`: timestamp of last price update

**Cardmarket** — `pricing.cardmarket`

- `averageSellPrice`, `lowPrice`, `trendPrice`
- Time-period averages: `avg1` (24h), `avg7` (7d), `avg30` (30d)
- `updated`: timestamp of last price update

---

## Filtering, Sorting, and Pagination

All list endpoints (`/cards`, `/sets`, etc.) support these query parameters.

### Filtering

Filters use the format `field=value` or `field=prefix:value`.

| Operator | Syntax | Description |
| --- | --- | --- |
| Lax equality (default) | `name=furret` | Case-insensitive partial match |
| Lax negation | `name=not:furret` | Excludes partial matches |
| Strict equality | `name=eq:Furret` | Exact match |
| Strict negation | `name=neq:Furret` | Excludes exact match |
| Greater than | `hp=gt:100` | Numeric |
| Greater or equal | `hp=gte:100` | Numeric |
| Less than | `hp=lt:100` | Numeric |
| Less or equal | `hp=lte:100` | Numeric |
| Is null | `effect=null:` | Field is absent or null |
| Is not null | `effect=notnull:` | Field is present |

Multiple values (OR logic) use pipe separation: `name=eq:Furret|Pikachu`

Wildcard matching: `name=*chu` (suffix), `name=fu*` (prefix)

### Sorting

| Parameter | Default | Description |
| --- | --- | --- |
| `sort:field` | `releaseDate > localId > id` | Field to sort by |
| `sort:order` | `ASC` | `ASC` or `DESC` |

**Example:** `?sort:field=name&sort:order=DESC`

### Pagination

| Parameter | Default | Description |
| --- | --- | --- |
| `pagination:page` | `1` | Page number |
| `pagination:itemsPerPage` | `100` | Results per page |

**Example:** `?pagination:page=2&pagination:itemsPerPage=50`

---

## Python SDK

A first-party SDK is available if direct HTTP calls become cumbersome.

**Installation:**

```bash
pip install tcgdex-sdk
```

**Basic usage:**

```python
from tcgdexsdk import TCGdex, Language

tcgdex = TCGdex(Language.EN)

# Async
card = await tcgdex.card.get("base1-4")
set_data = await tcgdex.set.get("base1")

# Sync
card = tcgdex.card.getSync("base1-4")
```

**Querying:**

``` python
from tcgdexsdk import Query

# Filter cards with HP > 200, sorted descending
cards = await tcgdex.card.list(
    Query().greaterThan("hp", 200).sort("hp", "desc")
)

# Pagination
page = await tcgdex.card.list(Query().paginate(page=2, itemsPerPage=20))
```

**Image URLs via SDK:**
``` python
from tcgdexsdk.enums import Quality, Extension

image_url = card.get_image_url(quality="high", extension="png")
logo_url = set_data.get_logo_url(Extension.PNG)
```

The ingestion layer currently uses direct `requests` calls rather than the SDK to avoid the extra dependency and keep the async/sync boundary explicit.

---

## Notes

- The `cards` array embedded in a set response contains `CardBrief` objects only. Full card detail (rarity, category, attacks, etc.) requires individual `GET /cards/{cardId}` requests.
- There is no bulk card detail endpoint. Fetching full detail for an entire set requires N requests where N is the card count.
- Price data (`pricing` field) is present on full card objects but absent from `CardBrief`. Pricing via the TCGdex API is planned for use in Milestone 2 if eBay data is unavailable or incomplete.
