# PokemonPriceTracker API — Milestone 2 Reference

## Overview

PokemonPriceTracker aggregates Pokémon card pricing from TCGPlayer, eBay, and CardMarket and exposes it via a REST API. It is the sole pricing data source for Milestone 2.

- **Base URL:** `https://www.pokemonpricetracker.com/api/v2`
- **Authentication:** `Authorization: Bearer YOUR_API_KEY`
- **Response format:** JSON
- **Update cadence:** Daily

---

## Tiers

| Tier | Cost | Credits/day | History window | eBay/PSA data |
|---|---|---|---|---|
| Free | $0 | 100 | 3 days | No |
| API | $9.99/mo | 20,000 | 6 months | Yes |

The free tier is sufficient for development and testing against Base Set. The API tier is the target for active data accumulation — run it for 2-3 months to build up meaningful history in Neon, then cancel. Daily snapshots on the free tier can continue indefinitely after that.

---

## Credit System

Credits are consumed per card per data type:

| Data requested | Cost per card |
|---|---|
| Basic card data + current price | 1 credit |
| + price history | +1 credit |
| + eBay/PSA graded data | +1 credit |

Every API response includes headers showing current consumption:

```
X-API-Calls-Consumed: 102
X-RateLimit-Daily-Remaining: 19898
```

The ingestion script must read and log these headers on every call and stop gracefully if the daily limit is approached.

**Free tier capacity for Base Set (102 cards):**
Pulling all 102 cards at 1 credit each requires 102 credits — just over the 100/day limit. On the free tier, pull 100 cards one day and the remaining 2 the next. Once multiple sets are in the database, prioritize by set and rotate across days.

**API tier capacity:**
20,000 credits/day comfortably covers daily snapshots across many sets. A full Base Set pull with history costs 204 credits, leaving 19,796 for other sets.

---

## Endpoint — `GET /api/v2/cards`

The only endpoint used in the Milestone 2 ingestion loop. Fetches card data and prices, optionally including history and eBay graded prices.

### Parameters

| Parameter | Type | Free | API | Notes |
|---|---|---|---|---|
| `set` | string | ✓ | ✓ | Set name or ID — e.g. `base1` |
| `tcgPlayerId` | string | ✓ | ✓ | Exact card ID — e.g. `base1-4` |
| `fetchAllInSet` | boolean | ✓ | ✓ | Fetch all cards in a set in one call |
| `limit` | int | ✓ | ✓ | Results per page, default 50 |
| `offset` | int | ✓ | ✓ | Pagination offset |
| `includeHistory` | boolean | ✓ (3 days) | ✓ (6 months) | Include price history in response |
| `days` | int | ✓ (max 3) | ✓ (max 180) | History window — defaults to 7 |
| `includeEbay` | boolean | ✗ | ✓ | eBay/PSA graded prices — API tier only |

### Free Tier Call

Fetches all Base Set cards with current prices only:

```
GET /api/v2/cards?set=base1&fetchAllInSet=true
Authorization: Bearer YOUR_API_KEY
```

Cost: 1 credit per card returned.

### API Tier Call — Initial Backfill

Run once per set when first upgrading to the API tier. Fetches all cards with 6 months of price history and eBay graded data:

```
GET /api/v2/cards?set=base1&fetchAllInSet=true&includeHistory=true&days=180&includeEbay=true
Authorization: Bearer YOUR_API_KEY
```

Cost: 3 credits per card returned (base + history + eBay).

### API Tier Call — Daily Snapshot

Run nightly after the initial backfill. Fetches current prices only — history accumulates in Neon over time:

```
GET /api/v2/cards?set=base1&fetchAllInSet=true
Authorization: Bearer YOUR_API_KEY
```

Cost: 1 credit per card returned.

### Response Shape

> **Note (verified April 2026):** The actual API response format differs from older documentation. `prices.market` is a flat scalar, `prices.variants` contains per-printing/condition breakdowns, and `priceHistory` is **not returned** even when `includeHistory=true` is sent. History accumulates from daily snapshot runs rather than a bulk backfill.

```json
{
  "data": [
    {
      "tcgPlayerId": "base1-4",
      "name": "Charizard",
      "setName": "Base Set",
      "cardNumber": "4",
      "totalSetNumber": "102",
      "rarity": "Holo Rare",
      "prices": {
        "market": 399.99,
        "low": 275.00,
        "sellers": 382,
        "listings": 0,
        "primaryPrinting": "Unlimited",
        "lastUpdated": "2026-04-15T00:00:00.000Z",
        "variants": {
          "1st Edition": {
            "Near Mint 1st Edition": {
              "price": 17.11,
              "listings": null,
              "priceString": "$17.11",
              "lastUpdated": "2026-04-15T00:00:00.000Z"
            }
          },
          "Unlimited": {
            "Near Mint Unlimited": {
              "price": 1.20,
              "listings": null,
              "priceString": "$1.20",
              "lastUpdated": "2026-04-15T00:00:00.000Z"
            }
          }
        }
      },
      "ebay": {
        "psa10": { "avg": 15750.00 },
        "psa9": { "avg": 1850.00 },
        "bgs95": { "avg": 12000.00 }
      }
    }
  ],
  "metadata": {
    "total": 102,
    "count": 102,
    "limit": 200,
    "offset": 0,
    "hasMore": false
  }
}
```

Fields present in the response depend on the parameters sent. `ebay` is only present when `includeEbay=true` and the account is on the API tier or above. `priceHistory` is not returned by the current API — historical data builds up from daily snapshot runs.

---

## Environment Variables

The ingestion script controls tier-specific behavior via environment variables. Switching from free to API tier requires only updating the key and flags — no code changes:

```ini
# .env

POKEMON_PRICE_TRACKER_API_KEY=your_key_here

# Set to true on API tier, false on free tier
PPT_INCLUDE_HISTORY=false
PPT_HISTORY_DAYS=180

# Set to true on API tier only — ignored on free tier
PPT_INCLUDE_EBAY=false
```

---

## Schema Mapping

How the API response maps to the `price_snapshots` table:

| Database column | API field | Notes |
|---|---|---|
| `card_id` | `tcgPlayerId` | Direct match to `cards.id` |
| `source` | — | Hardcoded as `tcgplayer` for raw prices |
| `market_price` | `prices.market` | |
| `low_price` | `prices.low` | |
| `high_price` | `prices.high` | |
| `captured_at` | — | Timestamp set at ingest time |

When `includeEbay=true`, graded prices (PSA, BGS) are stored as additional rows with `source` set to `psa`, `bgs`, etc. and `condition` set to the grade (e.g. `PSA-10`).

---

## Ingestion Strategy by Tier

### Free Tier (development and ongoing after cancelling paid)

1. Query the database for all sets
2. For each set, call `GET /api/v2/cards?set={set_id}&fetchAllInSet=true`
3. Read `X-RateLimit-Daily-Remaining` from the response header
4. Stop gracefully and update the watermark if the remaining limit drops below a safe threshold (e.g. 10 credits)
5. Continue the remaining sets on the next run

### API Tier (active accumulation phase)

1. On first run per set: call with `includeHistory=true&days=180&includeEbay=true` to backfill
2. Mark set as backfilled in the `ingestion_watermarks` table
3. On subsequent runs: call with current prices only — history accumulates from daily snapshots
4. Track remaining credits and stop gracefully as above

---

## Rate Limiting Notes

- 60 requests per minute on all tiers
- `fetchAllInSet=true` counts as `ceil(cards / 10)` minute-rate calls, capped at 30 — so fetching a 102-card set counts as roughly 11 minute-rate calls, not 102
- The daily credit limit resets at midnight UTC
- If a 429 response is received, back off and retry after 60 seconds before stopping the run
