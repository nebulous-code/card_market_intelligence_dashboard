/**
 * Pure helpers backing the Collection Dashboard slicer panel.
 *
 * The slicer panel is the only writer of ``filterState``; charts and
 * tables read through ``filteredCollection`` (set up in M04_S03). All
 * logic that decides which chips show up, the order they appear in,
 * and how clicking one updates the filter state lives here so the
 * panel component can stay a thin renderer.
 */

import { variantTokensForCard } from "./collectionFilters.js";

/**
 * Canonical order for the Rarity slicer. Anything not in this list
 * sorts after the canonical entries, alphabetically. The empty string
 * (representing a card with no rarity) sorts to the bottom and is
 * displayed via :func:`displayLabelForRarity`.
 */
const RARITY_ORDER = [
  "Common",
  "Uncommon",
  "Rare",
  "Rare Holo",
  "Rare Holo EX",
  "Rare Holo GX",
  "Rare Holo V",
  "Rare Holo VMAX",
  "Rare Holo VSTAR",
  "Rare Ultra",
  "Rare Secret",
  "Secret Rare",
  "Hyper Rare",
];

const CONDITION_ORDER = ["NM", "LP", "MP", "HP", "DMG"];

/**
 * Display label for an empty / null rarity bucket. Stored value in the
 * filter Set is ``""`` so :mod:`collectionFilters` can compare against
 * ``card.rarity ?? ""`` without translation.
 */
export const UNRATED_LABEL = "Unrated";

/**
 * Build the chip universes for each slicer dimension from the
 * dashboard's full (unfiltered) cards list. Slicer values do **not**
 * cascade -- selecting a set does not shrink the rarity options --
 * because that would let the user paint themselves into an
 * impossible-to-undo corner.
 *
 * @param {Array} cards
 * @returns {{
 *   sets: Array<{value: string, label: string}>,
 *   rarities: Array<{value: string, label: string}>,
 *   conditions: Array<{value: string, label: string}>,
 *   variants: Array<{value: string, label: string}>,
 * }}
 */
export function collectSlicerValues(cards) {
  return {
    sets: collectSets(cards),
    rarities: collectRarities(cards),
    conditions: collectConditions(cards),
    variants: collectVariants(cards),
  };
}

function collectSets(cards) {
  const seen = new Map();
  for (const c of cards) {
    if (!seen.has(c.set_id)) {
      seen.set(c.set_id, c.set_name ?? c.set_id);
    }
  }
  return Array.from(seen.entries())
    .map(([value, label]) => ({ value, label }))
    .sort((a, b) => a.label.localeCompare(b.label));
}

function collectRarities(cards) {
  const seen = new Set();
  for (const c of cards) {
    seen.add(c.rarity ?? "");
  }
  const values = Array.from(seen);
  values.sort((a, b) => rarityOrderKey(a) - rarityOrderKey(b) || a.localeCompare(b));
  return values.map((value) => ({
    value,
    label: value === "" ? UNRATED_LABEL : value,
  }));
}

function rarityOrderKey(value) {
  if (value === "") return 1e6; // Unrated sinks to the bottom.
  const idx = RARITY_ORDER.indexOf(value);
  return idx === -1 ? 1e5 : idx;
}

function collectConditions(cards) {
  const seen = new Set();
  for (const c of cards) {
    if (c.condition) seen.add(c.condition);
  }
  const values = Array.from(seen);
  values.sort((a, b) => conditionOrderKey(a) - conditionOrderKey(b) || a.localeCompare(b));
  return values.map((value) => ({ value, label: value }));
}

function conditionOrderKey(value) {
  const idx = CONDITION_ORDER.indexOf(value);
  return idx === -1 ? 1e5 : idx;
}

function collectVariants(cards) {
  const seen = new Set();
  for (const c of cards) {
    for (const token of variantTokensForCard(c)) {
      seen.add(token);
    }
  }
  // Standard first, then alphabetical for variant strings, then
  // "1st Edition" pinned to the bottom as a synthetic token.
  const values = Array.from(seen);
  values.sort((a, b) => variantOrderKey(a) - variantOrderKey(b) || a.localeCompare(b));
  return values.map((value) => ({ value, label: value }));
}

function variantOrderKey(value) {
  if (value === "Standard") return 0;
  if (value === "1st Edition") return 100;
  return 50;
}

/**
 * Returns ``true`` when the variant slicer should be hidden -- i.e.
 * every card in the collection is Standard with no other variants.
 *
 * @param {Array<{value: string}>} variantValues
 * @returns {boolean}
 */
export function shouldHideVariantSlicer(variantValues) {
  if (variantValues.length === 0) return true;
  return variantValues.every((v) => v.value === "Standard");
}

/**
 * Apply the Excel-style chip toggle rule and return the new Set.
 *
 * - When ``current`` is empty (the "all selected" sentinel), clicking
 *   any chip isolates that chip: the new Set is ``{value}``.
 * - When the chip is already in the Set and is the only one, the
 *   click is a no-op (we never reach the zero-selection state).
 * - When the chip is in the Set and there are others, remove it.
 * - When the chip is not in the Set, add it.
 * - If the resulting Set ends up containing every value in
 *   ``universe``, canonicalize back to the empty Set so the URL stays
 *   compact and a reload with no params produces identical filtering.
 *
 * @param {Set<string>} current
 * @param {string} value
 * @param {Iterable<string>} universe -- every distinct value the slicer offers
 * @returns {Set<string>}
 */
export function toggleChipSelection(current, value, universe) {
  const universeArr = Array.from(universe);
  if (current.size === 0) {
    return new Set([value]);
  }
  const next = new Set(current);
  if (next.has(value)) {
    if (next.size === 1) {
      return next; // No-op -- can't reach zero selections.
    }
    next.delete(value);
  } else {
    next.add(value);
  }
  if (next.size === universeArr.length && universeArr.every((v) => next.has(v))) {
    return new Set();
  }
  return next;
}

/**
 * Mutating helper that resets every dimension of ``filterState`` to
 * an empty Set. Used by the panel's "Clear All Filters" button.
 *
 * @param {{sets: Set, rarities: Set, conditions: Set, variants: Set}} filterState
 */
export function clearAllFilters(filterState) {
  filterState.sets = new Set();
  filterState.rarities = new Set();
  filterState.conditions = new Set();
  filterState.variants = new Set();
}

/**
 * Returns ``true`` when at least one filter dimension is non-empty.
 * Drives visibility of the "Clear All Filters" button and the
 * Magikarp-gold accent on per-region count badges.
 *
 * @param {{sets: Set, rarities: Set, conditions: Set, variants: Set}} filterState
 */
export function hasAnyActiveFilter(filterState) {
  return (
    filterState.sets.size > 0 ||
    filterState.rarities.size > 0 ||
    filterState.conditions.size > 0 ||
    filterState.variants.size > 0
  );
}

/**
 * Returns ``true`` when ``value`` is "active" in the filter Set --
 * either explicitly present or implicitly present because the Set is
 * empty (the "all selected" sentinel).
 *
 * @param {Set<string>} set
 * @param {string} value
 */
export function isChipSelected(set, value) {
  if (set.size === 0) return true;
  return set.has(value);
}
