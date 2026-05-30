import { describe, it, expect } from "vitest";

import {
  UNRATED_LABEL,
  clearAllFilters,
  collectSlicerValues,
  hasAnyActiveFilter,
  isChipSelected,
  shouldHideVariantSlicer,
  toggleChipSelection,
} from "../../src/utils/slicerState.js";


function card(overrides = {}) {
  return {
    card_id: "base1-4",
    set_id: "base1",
    set_name: "Base Set",
    rarity: "Rare Holo",
    condition: "NM",
    variant: [],
    is_first_edition: false,
    quantity: 1,
    market_price: "100.00",
    purchase_price: null,
    ...overrides,
  };
}


describe("collectSlicerValues — sets", () => {
  it("dedupes by set_id and sorts by set_name alphabetically", () => {
    const cards = [
      card({ set_id: "jungle", set_name: "Jungle" }),
      card({ set_id: "base1", set_name: "Base Set" }),
      card({ set_id: "jungle", set_name: "Jungle" }),
    ];
    const { sets } = collectSlicerValues(cards);
    expect(sets.map((s) => s.value)).toEqual(["base1", "jungle"]);
    expect(sets.map((s) => s.label)).toEqual(["Base Set", "Jungle"]);
  });

  it("falls back to set_id when set_name is missing", () => {
    const { sets } = collectSlicerValues([
      card({ set_id: "weird", set_name: undefined }),
    ]);
    expect(sets[0].label).toBe("weird");
  });
});


describe("collectSlicerValues — rarities", () => {
  it("sorts canonical rarities by spec order", () => {
    const cards = [
      card({ rarity: "Rare Holo" }),
      card({ rarity: "Common" }),
      card({ rarity: "Uncommon" }),
    ];
    const { rarities } = collectSlicerValues(cards);
    expect(rarities.map((r) => r.value)).toEqual([
      "Common",
      "Uncommon",
      "Rare Holo",
    ]);
  });

  it("sinks unknown rarities below canonical ones, alphabetically", () => {
    const cards = [
      card({ rarity: "Rare" }),
      card({ rarity: "Mystery" }),
      card({ rarity: "Banana" }),
    ];
    const { rarities } = collectSlicerValues(cards);
    expect(rarities.map((r) => r.value)).toEqual([
      "Rare",
      "Banana",
      "Mystery",
    ]);
  });

  it("represents null rarity as the empty-string sentinel labeled 'Unrated'", () => {
    const { rarities } = collectSlicerValues([
      card({ rarity: null }),
      card({ rarity: "Rare" }),
    ]);
    const unrated = rarities.find((r) => r.value === "");
    expect(unrated?.label).toBe(UNRATED_LABEL);
    // Sinks to the bottom regardless of original order.
    expect(rarities[rarities.length - 1].value).toBe("");
  });
});


describe("collectSlicerValues — conditions", () => {
  it("orders by NM/LP/MP/HP/DMG canonical sequence", () => {
    const cards = [
      card({ condition: "DMG" }),
      card({ condition: "NM" }),
      card({ condition: "MP" }),
    ];
    const { conditions } = collectSlicerValues(cards);
    expect(conditions.map((c) => c.value)).toEqual(["NM", "MP", "DMG"]);
  });

  it("appends graded conditions alphabetically after the canonical five", () => {
    const cards = [
      card({ condition: "PSA-10" }),
      card({ condition: "BGS-9.5" }),
      card({ condition: "NM" }),
    ];
    const { conditions } = collectSlicerValues(cards);
    expect(conditions.map((c) => c.value)).toEqual([
      "NM",
      "BGS-9.5",
      "PSA-10",
    ]);
  });

  it("ignores cards with falsy condition values", () => {
    const cards = [card({ condition: null }), card({ condition: "NM" })];
    const { conditions } = collectSlicerValues(cards);
    expect(conditions.map((c) => c.value)).toEqual(["NM"]);
  });
});


describe("collectSlicerValues — variants", () => {
  it("builds chip universe from variantTokensForCard output", () => {
    const cards = [
      card({ variant: ["Reverse Holo"], is_first_edition: false }),
      card({ variant: [], is_first_edition: true }), // 1st Edition synthetic
      card({ variant: [], is_first_edition: false }), // Standard
    ];
    const { variants } = collectSlicerValues(cards);
    const labels = variants.map((v) => v.value);
    expect(labels).toContain("Standard");
    expect(labels).toContain("Reverse Holo");
    expect(labels).toContain("1st Edition");
  });

  it("orders Standard first, variants alphabetical, 1st Edition last", () => {
    const cards = [
      card({ variant: ["Misprint"] }),
      card({ variant: ["Reverse Holo"] }),
      card({ variant: [], is_first_edition: true }),
      card({ variant: [], is_first_edition: false }),
    ];
    const { variants } = collectSlicerValues(cards);
    expect(variants.map((v) => v.value)).toEqual([
      "Standard",
      "Misprint",
      "Reverse Holo",
      "1st Edition",
    ]);
  });

  it("skips Unlimited entirely (treated as Standard)", () => {
    const cards = [
      card({ variant: ["Unlimited"], is_first_edition: false }),
    ];
    const { variants } = collectSlicerValues(cards);
    expect(variants.map((v) => v.value)).toEqual(["Standard"]);
  });
});


describe("shouldHideVariantSlicer", () => {
  it("hides when no values exist", () => {
    expect(shouldHideVariantSlicer([])).toBe(true);
  });

  it("hides when only Standard is present", () => {
    expect(shouldHideVariantSlicer([{ value: "Standard", label: "Standard" }])).toBe(
      true,
    );
  });

  it("shows when any non-Standard variant exists", () => {
    expect(
      shouldHideVariantSlicer([
        { value: "Standard", label: "Standard" },
        { value: "Reverse Holo", label: "Reverse Holo" },
      ]),
    ).toBe(false);
  });

  it("shows when only 1st Edition exists", () => {
    expect(
      shouldHideVariantSlicer([{ value: "1st Edition", label: "1st Edition" }]),
    ).toBe(false);
  });
});


describe("toggleChipSelection", () => {
  it("isolates the clicked chip when the Set is empty (all-selected sentinel)", () => {
    const next = toggleChipSelection(new Set(), "base1", ["base1", "jungle"]);
    expect(Array.from(next)).toEqual(["base1"]);
  });

  it("adds an unselected chip to an existing partial selection", () => {
    const next = toggleChipSelection(
      new Set(["base1"]),
      "jungle",
      ["base1", "jungle", "fossil"],
    );
    expect(Array.from(next).sort()).toEqual(["base1", "jungle"]);
  });

  it("removes a selected chip when more than one is selected", () => {
    const next = toggleChipSelection(
      new Set(["base1", "jungle"]),
      "base1",
      ["base1", "jungle", "fossil"],
    );
    expect(Array.from(next)).toEqual(["jungle"]);
  });

  it("is a no-op on the only-selected chip", () => {
    const current = new Set(["base1"]);
    const next = toggleChipSelection(current, "base1", ["base1", "jungle"]);
    expect(Array.from(next)).toEqual(["base1"]);
  });

  it("canonicalizes a fully-populated Set back to empty", () => {
    const universe = ["base1", "jungle", "fossil"];
    const current = new Set(["base1", "jungle"]);
    const next = toggleChipSelection(current, "fossil", universe);
    expect(next.size).toBe(0);
  });

  it("does not mutate the original Set", () => {
    const current = new Set(["base1"]);
    toggleChipSelection(current, "jungle", ["base1", "jungle"]);
    expect(Array.from(current)).toEqual(["base1"]);
  });
});


describe("clearAllFilters", () => {
  it("resets every dimension to an empty Set", () => {
    const state = {
      sets: new Set(["base1"]),
      rarities: new Set(["Rare"]),
      conditions: new Set(["NM"]),
      variants: new Set(["Reverse Holo"]),
    };
    clearAllFilters(state);
    expect(state.sets.size).toBe(0);
    expect(state.rarities.size).toBe(0);
    expect(state.conditions.size).toBe(0);
    expect(state.variants.size).toBe(0);
  });
});


describe("hasAnyActiveFilter", () => {
  it("returns false when every dimension is empty", () => {
    expect(
      hasAnyActiveFilter({
        sets: new Set(),
        rarities: new Set(),
        conditions: new Set(),
        variants: new Set(),
      }),
    ).toBe(false);
  });

  it("returns true when any single dimension has a value", () => {
    expect(
      hasAnyActiveFilter({
        sets: new Set(["base1"]),
        rarities: new Set(),
        conditions: new Set(),
        variants: new Set(),
      }),
    ).toBe(true);
    expect(
      hasAnyActiveFilter({
        sets: new Set(),
        rarities: new Set(),
        conditions: new Set(),
        variants: new Set(["Reverse Holo"]),
      }),
    ).toBe(true);
  });

  it("detects active rarity and condition dimensions", () => {
    expect(
      hasAnyActiveFilter({
        sets: new Set(),
        rarities: new Set(["Rare"]),
        conditions: new Set(),
        variants: new Set(),
      }),
    ).toBe(true);
    expect(
      hasAnyActiveFilter({
        sets: new Set(),
        rarities: new Set(),
        conditions: new Set(["NM"]),
        variants: new Set(),
      }),
    ).toBe(true);
  });
});


describe("isChipSelected", () => {
  it("treats empty Set as 'all selected'", () => {
    expect(isChipSelected(new Set(), "base1")).toBe(true);
  });

  it("returns true when the value is in the Set", () => {
    expect(isChipSelected(new Set(["base1"]), "base1")).toBe(true);
  });

  it("returns false when the value is not in a non-empty Set", () => {
    expect(isChipSelected(new Set(["base1"]), "jungle")).toBe(false);
  });
});
