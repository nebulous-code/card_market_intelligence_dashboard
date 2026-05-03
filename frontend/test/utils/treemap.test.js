import { describe, it, expect } from "vitest";

import { buildTreemapData } from "../../src/utils/treemap.js";


function card(overrides = {}) {
  return {
    card_id: "base1-1",
    card_name: "Card 1",
    set_id: "base1",
    set_name: "Base Set",
    market_price: "10.00",
    quantity: 1,
    condition: "NM",
    ...overrides,
  };
}


describe("buildTreemapData", () => {
  it("returns one entry per card when set has fewer than 5 cards", () => {
    const out = buildTreemapData([
      card({ card_id: "a", market_price: "100" }),
      card({ card_id: "b", market_price: "20" }),
      card({ card_id: "c", market_price: "10" }),
    ]);
    expect(out.map((e) => e.card_id)).toEqual(["a", "b", "c"]);
    expect(out.every((e) => !e.is_other)).toBe(true);
  });

  it("collapses bottom 10% into 'Other' when 3+ cards qualify", () => {
    // Set total = 100; bottom-10% threshold = 10. Five cards with values
    // [50, 40, 4, 3, 3]. Walking from cheapest: 3+3+4=10, next would
    // exceed -> three-card group. Group qualifies (>= MIN_GROUP_SIZE).
    const out = buildTreemapData([
      card({ card_id: "a", market_price: "50", card_name: "A" }),
      card({ card_id: "b", market_price: "40", card_name: "B" }),
      card({ card_id: "c", market_price: "4", card_name: "C" }),
      card({ card_id: "d", market_price: "3", card_name: "D" }),
      card({ card_id: "e", market_price: "3", card_name: "E" }),
    ]);
    expect(out).toHaveLength(3); // A, B, Other
    const other = out.find((e) => e.is_other);
    expect(other.count).toBe(3);
    expect(other.value).toBe(10);
    expect(other.card_name).toMatch(/Other \(3 cards\)/);
    expect(other.top_card_name).toBe("C"); // largest in the tail
  });

  it("does not collapse when fewer than 3 cards would group", () => {
    // Five cards, but the bottom 10% only consolidates 2 of them.
    const out = buildTreemapData([
      card({ card_id: "a", market_price: "100" }),
      card({ card_id: "b", market_price: "100" }),
      card({ card_id: "c", market_price: "100" }),
      card({ card_id: "d", market_price: "100" }),
      card({ card_id: "e", market_price: "1" }),
    ]);
    expect(out).toHaveLength(5);
    expect(out.every((e) => !e.is_other)).toBe(true);
  });

  it("handles cards with null market_price as zero value", () => {
    const out = buildTreemapData([
      card({ card_id: "a", market_price: null }),
    ]);
    expect(out[0].value).toBe(0);
  });

  it("multiplies value by quantity", () => {
    const out = buildTreemapData([
      card({ card_id: "a", market_price: "10", quantity: 5 }),
    ]);
    expect(out[0].value).toBe(50);
  });

  it("does not consolidate when set total is zero", () => {
    const out = buildTreemapData([
      card({ card_id: "a", market_price: null }),
      card({ card_id: "b", market_price: null }),
      card({ card_id: "c", market_price: null }),
      card({ card_id: "d", market_price: null }),
      card({ card_id: "e", market_price: null }),
    ]);
    expect(out).toHaveLength(5);
    expect(out.every((e) => !e.is_other)).toBe(true);
  });

  it("groups cards by set", () => {
    const out = buildTreemapData([
      card({ card_id: "x", set_id: "base1" }),
      card({ card_id: "y", set_id: "jungle" }),
    ]);
    const sets = new Set(out.map((e) => e.set_id));
    expect(sets).toEqual(new Set(["base1", "jungle"]));
  });
});
