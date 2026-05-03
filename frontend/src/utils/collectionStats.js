/**
 * Pure aggregation helpers for the Collection Dashboard.
 *
 * Each function takes a list of cards-with-prices (the response shape
 * from ``/collection/cards-with-prices``) and returns a derived
 * summary. The functions are pure -- no DOM, no router, no axios -- so
 * they can be unit-tested in isolation.
 */

/**
 * Total ``quantity * market_price`` summed across all cards. Cards
 * without a market price contribute zero.
 *
 * @param {Array} cards
 * @returns {number}
 */
export function totalCollectionValue(cards) {
  let total = 0;
  for (const c of cards) {
    if (c.market_price == null) continue;
    total += Number(c.market_price) * Number(c.quantity);
  }
  return total;
}

/**
 * Total card count summed across all cards. Each row contributes its
 * own quantity.
 *
 * @param {Array} cards
 * @returns {number}
 */
export function totalCardCount(cards) {
  let total = 0;
  for (const c of cards) total += Number(c.quantity);
  return total;
}

/**
 * Returns ``{ dollarsGain, percentGain }`` across cards that have a
 * purchase price. Cards without one are excluded from both numerator
 * and denominator. Returns ``null`` if no cards have purchase prices.
 *
 * @param {Array} cards
 * @returns {{dollarsGain: number, percentGain: number}|null}
 */
export function lifetimeGain(cards) {
  let costBasis = 0;
  let currentValue = 0;
  let any = false;
  for (const c of cards) {
    if (c.purchase_price == null) continue;
    if (c.market_price == null) continue;
    any = true;
    const qty = Number(c.quantity);
    costBasis += Number(c.purchase_price) * qty;
    currentValue += Number(c.market_price) * qty;
  }
  if (!any || costBasis === 0) return null;
  const dollarsGain = currentValue - costBasis;
  const percentGain = dollarsGain / costBasis;
  return { dollarsGain, percentGain };
}

/**
 * Returns ``true`` when at least one card has a purchase price set.
 * Drives whether the gain KPIs / Top 10 columns appear.
 *
 * @param {Array} cards
 * @returns {boolean}
 */
export function anyPurchasePrices(cards) {
  return cards.some((c) => c.purchase_price != null);
}

/**
 * Returns the single most valuable card by individual ``market_price``
 * (NOT by ``quantity * market_price``). Tie-broken by card_id ascending
 * for determinism. Returns ``null`` if nothing has a market price.
 *
 * @param {Array} cards
 * @returns {object|null}
 */
export function mostValuableCard(cards) {
  let best = null;
  for (const c of cards) {
    if (c.market_price == null) continue;
    if (best === null) {
      best = c;
      continue;
    }
    const bestPrice = Number(best.market_price);
    const candidatePrice = Number(c.market_price);
    if (candidatePrice > bestPrice) {
      best = c;
    } else if (candidatePrice === bestPrice && c.card_id < best.card_id) {
      best = c;
    }
  }
  return best;
}

/**
 * Aggregate cards by ``set_id`` returning ``[{set_id, set_name,
 * total_value, total_quantity, owned_count, printed_total,
 * total_count, percent_of_collection}]``. ``owned_count`` is the count
 * of distinct cards within the set (not summed quantity), which is
 * what the completion progress bar wants.
 *
 * @param {Array} cards
 * @returns {Array}
 */
export function aggregateBySet(cards) {
  const acc = new Map();
  let grand = 0;
  for (const c of cards) {
    const ownedValue =
      c.market_price == null
        ? 0
        : Number(c.market_price) * Number(c.quantity);
    grand += ownedValue;
    let bucket = acc.get(c.set_id);
    if (!bucket) {
      bucket = {
        set_id: c.set_id,
        set_name: c.set_name,
        total_value: 0,
        total_quantity: 0,
        distinct_card_ids: new Set(),
        printed_total: c.printed_total,
        total_count: c.total_count,
      };
      acc.set(c.set_id, bucket);
    }
    bucket.total_value += ownedValue;
    bucket.total_quantity += Number(c.quantity);
    bucket.distinct_card_ids.add(c.card_id);
  }
  const out = [];
  for (const b of acc.values()) {
    out.push({
      set_id: b.set_id,
      set_name: b.set_name,
      total_value: b.total_value,
      total_quantity: b.total_quantity,
      owned_count: b.distinct_card_ids.size,
      printed_total: b.printed_total,
      total_count: b.total_count,
      percent_of_collection: grand > 0 ? b.total_value / grand : 0,
    });
  }
  out.sort((a, b) => b.total_value - a.total_value);
  return out;
}

/**
 * Per-card rows enriched with ``total_value`` (qty * price) and gain
 * fields, sorted by ``total_value`` descending. Used by the Top 10
 * table and treemap sizing.
 *
 * @param {Array} cards
 * @returns {Array}
 */
export function topCardsByValue(cards) {
  const enriched = cards.map((c) => {
    const total =
      c.market_price == null
        ? 0
        : Number(c.market_price) * Number(c.quantity);
    let gainDollars = null;
    let gainPercent = null;
    if (c.purchase_price != null && c.market_price != null) {
      const cost = Number(c.purchase_price) * Number(c.quantity);
      gainDollars = total - cost;
      gainPercent = cost > 0 ? gainDollars / cost : null;
    }
    return {
      ...c,
      total_value: total,
      gain_dollars: gainDollars,
      gain_percent: gainPercent,
    };
  });
  enriched.sort((a, b) => b.total_value - a.total_value);
  return enriched;
}

/**
 * Variant chart bars: aggregate quantities across the variant tokens
 * each card contributes (multi-value variants split by S02's
 * normalizer plus the synthetic ``1st Edition`` token).
 *
 * Cards whose only token is ``"Standard"`` are excluded -- the chart
 * only shows non-standard variants.
 *
 * @param {Array} cards
 * @returns {Array<{variant: string, quantity: number, unique_cards: number}>}
 */
export function variantBars(cards) {
  const counts = new Map();
  for (const c of cards) {
    const tokens = collectVariantTokens(c);
    if (tokens.length === 0) continue;
    for (const token of tokens) {
      let bucket = counts.get(token);
      if (!bucket) {
        bucket = { variant: token, quantity: 0, unique_cards: new Set() };
        counts.set(token, bucket);
      }
      bucket.quantity += Number(c.quantity);
      bucket.unique_cards.add(c.card_id);
    }
  }
  return Array.from(counts.values())
    .map((b) => ({
      variant: b.variant,
      quantity: b.quantity,
      unique_cards: b.unique_cards.size,
    }))
    .sort((a, b) => b.quantity - a.quantity);
}

function collectVariantTokens(card) {
  // Mirrors variantTokensForCard's exclusion rules: "Unlimited" (case
  // -insensitive) is treated as standard print and never gets its own
  // bar on the variant chart.
  const tokens = [];
  if (Array.isArray(card.variant)) {
    for (const v of card.variant) {
      if (!v) continue;
      if (v.trim().toLowerCase() === "unlimited") continue;
      if (!tokens.includes(v)) tokens.push(v);
    }
  }
  if (card.is_first_edition && !tokens.includes("1st Edition")) {
    tokens.push("1st Edition");
  }
  return tokens;
}
