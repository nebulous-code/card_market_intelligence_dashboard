import { describe, it, expect } from "vitest";

import {
  createEmptyFilterState,
  filterCards,
  filterStateFromQuery,
  filterStateToQuery,
  variantTokensForCard,
} from "../../src/utils/collectionFilters.js";


function card(overrides = {}) {
  return {
    card_id: "base1-4",
    set_id: "base1",
    rarity: "Rare Holo",
    condition: "NM",
    variant: [],
    is_first_edition: false,
    quantity: 1,
    ...overrides,
  };
}


describe("createEmptyFilterState", () => {
  it("returns four empty Sets", () => {
    const state = createEmptyFilterState();
    expect(state.sets).toBeInstanceOf(Set);
    expect(state.sets.size).toBe(0);
    expect(state.rarities.size).toBe(0);
    expect(state.conditions.size).toBe(0);
    expect(state.variants.size).toBe(0);
  });
});


describe("filterCards", () => {
  it("returns [] for empty input", () => {
    expect(filterCards([], createEmptyFilterState())).toEqual([]);
  });

  it("returns [] for undefined input", () => {
    expect(filterCards(undefined, createEmptyFilterState())).toEqual([]);
  });

  it("returns every card when state is empty", () => {
    const cards = [card({ card_id: "a" }), card({ card_id: "b" })];
    expect(filterCards(cards, createEmptyFilterState())).toHaveLength(2);
  });

  it("filters by set_id", () => {
    const state = createEmptyFilterState();
    state.sets.add("base1");
    const cards = [card({ set_id: "base1" }), card({ set_id: "base2" })];
    const out = filterCards(cards, state);
    expect(out.map((c) => c.set_id)).toEqual(["base1"]);
  });

  it("filters by rarity (treating null as empty string)", () => {
    const state = createEmptyFilterState();
    state.rarities.add("");
    const cards = [card({ rarity: null }), card({ rarity: "Rare Holo" })];
    const out = filterCards(cards, state);
    expect(out).toHaveLength(1);
    expect(out[0].rarity).toBe(null);
  });

  it("filters by condition", () => {
    const state = createEmptyFilterState();
    state.conditions.add("NM");
    const cards = [card({ condition: "NM" }), card({ condition: "LP" })];
    expect(filterCards(cards, state)).toHaveLength(1);
  });

  it("filters by variant intersection (any-match)", () => {
    const state = createEmptyFilterState();
    state.variants.add("Reverse Holo");
    const cards = [
      card({ variant: ["Reverse Holo", "Misprint"] }),
      card({ variant: ["Holo"] }),
    ];
    expect(filterCards(cards, state)).toHaveLength(1);
  });

  it("treats is_first_edition as the synthetic '1st Edition' variant token", () => {
    const state = createEmptyFilterState();
    state.variants.add("1st Edition");
    const cards = [
      card({ is_first_edition: true }),
      card({ is_first_edition: false }),
    ];
    expect(filterCards(cards, state)).toHaveLength(1);
  });

  it("treats blank-variant non-1st-Ed cards as 'Standard'", () => {
    const state = createEmptyFilterState();
    state.variants.add("Standard");
    const cards = [
      card({ variant: [], is_first_edition: false }),
      card({ variant: ["Reverse Holo"] }),
    ];
    expect(filterCards(cards, state)).toHaveLength(1);
  });

  it("ANDs across dimensions", () => {
    const state = createEmptyFilterState();
    state.sets.add("base1");
    state.conditions.add("NM");
    const cards = [
      card({ set_id: "base1", condition: "NM" }),
      card({ set_id: "base1", condition: "LP" }),
      card({ set_id: "base2", condition: "NM" }),
    ];
    expect(filterCards(cards, state)).toHaveLength(1);
  });
});


describe("variantTokensForCard", () => {
  it("returns ['Standard'] for a blank-variant non-1st-Ed card", () => {
    expect(variantTokensForCard(card())).toEqual(["Standard"]);
  });

  it("dedupes repeated variant entries", () => {
    expect(
      variantTokensForCard(card({ variant: ["Reverse Holo", "Reverse Holo"] })),
    ).toEqual(["Reverse Holo"]);
  });

  it("appends '1st Edition' when is_first_edition is true", () => {
    const tokens = variantTokensForCard(
      card({ variant: ["Reverse Holo"], is_first_edition: true }),
    );
    expect(tokens).toContain("Reverse Holo");
    expect(tokens).toContain("1st Edition");
  });

  it("ignores empty-string entries in the variant list", () => {
    expect(
      variantTokensForCard(card({ variant: ["", "Reverse Holo"] })),
    ).toEqual(["Reverse Holo"]);
  });

  it("handles a missing variant array", () => {
    expect(variantTokensForCard({ is_first_edition: false })).toEqual([
      "Standard",
    ]);
  });
});


describe("filterStateToQuery", () => {
  it("emits comma-separated lists per dimension", () => {
    const state = createEmptyFilterState();
    state.sets.add("base1");
    state.sets.add("jungle");
    state.conditions.add("NM");
    expect(filterStateToQuery(state)).toEqual({
      sets: "base1,jungle",
      conditions: "NM",
    });
  });

  it("omits dimensions with no values", () => {
    expect(filterStateToQuery(createEmptyFilterState())).toEqual({});
  });
});


describe("filterStateFromQuery", () => {
  it("parses comma-separated values into Sets", () => {
    const state = filterStateFromQuery({
      sets: "base1,base2",
      rarities: "Rare,Common",
    });
    expect(Array.from(state.sets).sort()).toEqual(["base1", "base2"]);
    expect(state.rarities.has("Rare")).toBe(true);
    expect(state.conditions.size).toBe(0);
  });

  it("trims whitespace and drops empty fragments", () => {
    const state = filterStateFromQuery({ sets: " base1 , ,base2 " });
    expect(Array.from(state.sets).sort()).toEqual(["base1", "base2"]);
  });

  it("uses the first value when a key arrives as an array", () => {
    const state = filterStateFromQuery({ sets: ["base1", "ignored"] });
    expect(Array.from(state.sets)).toEqual(["base1"]);
  });

  it("returns empty state for an empty query", () => {
    const state = filterStateFromQuery({});
    expect(state.sets.size).toBe(0);
  });

  it("ignores keys outside the known dimensions", () => {
    const state = filterStateFromQuery({ unknown: "foo" });
    expect(state.sets.size).toBe(0);
  });
});
