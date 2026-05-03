/**
 * Pure filter helpers for the Collection Dashboard.
 *
 * The dashboard uses a single reactive filter state object whose four
 * dimensions (sets, rarities, conditions, variants) are each represented
 * as JavaScript ``Set`` instances. Empty Set means "no filter applied":
 * every card passes that dimension.
 *
 * The slicer panel (M04_S04) writes to those Sets; charts and tables
 * read through ``filterCards`` so adding the slicer in a later story is
 * a no-op for chart components.
 */

/**
 * Build an empty filter state with the right shape for ``filterCards``.
 *
 * @returns {{sets: Set, rarities: Set, conditions: Set, variants: Set}}
 */
export function createEmptyFilterState() {
  return {
    sets: new Set(),
    rarities: new Set(),
    conditions: new Set(),
    variants: new Set(),
  };
}

/**
 * Return the cards that pass the active filter state.
 *
 * Variant matching is multi-value: a card with ``variant=["Reverse
 * Holo", "Misprint"]`` passes if EITHER label is in the variants
 * filter. ``is_first_edition`` contributes the synthetic
 * ``"1st Edition"`` token to the variant comparison so a single
 * filter value can target either the spec'd variant string or the
 * 1st-edition flag.
 *
 * @param {Array} cards
 * @param {{sets: Set, rarities: Set, conditions: Set, variants: Set}} state
 * @returns {Array}
 */
export function filterCards(cards, state) {
  if (!cards || cards.length === 0) return [];
  const { sets, rarities, conditions, variants } = state;
  return cards.filter((card) => {
    if (sets.size > 0 && !sets.has(card.set_id)) return false;
    if (rarities.size > 0 && !rarities.has(card.rarity ?? "")) return false;
    if (conditions.size > 0 && !conditions.has(card.condition)) return false;
    if (variants.size > 0) {
      const tokens = variantTokensForCard(card);
      const intersects = tokens.some((t) => variants.has(t));
      if (!intersects) return false;
    }
    return true;
  });
}

/**
 * Return the variant tokens that represent a card for filtering and
 * for the variant chart. A card with no variants and not 1st edition
 * contributes a single ``"Standard"`` token so it can still appear in
 * filter dropdowns built from the collection's distinct values.
 *
 * @param {{variant?: string[], is_first_edition?: boolean}} card
 * @returns {string[]}
 */
export function variantTokensForCard(card) {
  const tokens = [];
  if (Array.isArray(card.variant)) {
    for (const v of card.variant) {
      if (v && !tokens.includes(v)) tokens.push(v);
    }
  }
  if (card.is_first_edition && !tokens.includes("1st Edition")) {
    tokens.push("1st Edition");
  }
  if (tokens.length === 0) tokens.push("Standard");
  return tokens;
}

/**
 * Round-trip the filter state to/from URL query params.
 *
 * Each dimension serializes as a comma-separated list:
 *
 *     ?sets=base1,base2&rarities=Rare%20Holo&conditions=NM,LP
 *
 * Empty Sets are dropped from the query so the URL stays compact when
 * no filters are active. Values are URI-encoded by the router.
 */

const QUERY_KEYS = ["sets", "rarities", "conditions", "variants"];

/**
 * Convert filter state to a flat object suitable for ``router.replace({ query })``.
 *
 * @param {{sets: Set, rarities: Set, conditions: Set, variants: Set}} state
 * @returns {Record<string, string>}
 */
export function filterStateToQuery(state) {
  const out = {};
  for (const key of QUERY_KEYS) {
    const values = state[key];
    if (values && values.size > 0) {
      out[key] = Array.from(values).join(",");
    }
  }
  return out;
}

/**
 * Hydrate a filter state object from a router ``query`` dict.
 *
 * @param {Record<string, string|string[]>} query
 * @returns {{sets: Set, rarities: Set, conditions: Set, variants: Set}}
 */
export function filterStateFromQuery(query) {
  const out = createEmptyFilterState();
  for (const key of QUERY_KEYS) {
    const raw = query[key];
    if (!raw) continue;
    const text = Array.isArray(raw) ? raw[0] : raw;
    for (const part of text.split(",")) {
      const trimmed = part.trim();
      if (trimmed) out[key].add(trimmed);
    }
  }
  return out;
}
