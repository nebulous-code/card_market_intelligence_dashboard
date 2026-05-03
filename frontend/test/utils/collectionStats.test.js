import { describe, it, expect } from "vitest";

import {
  aggregateBySet,
  anyPurchasePrices,
  lifetimeGain,
  mostValuableCard,
  topCardsByValue,
  totalCardCount,
  totalCollectionValue,
  variantBars,
} from "../../src/utils/collectionStats.js";


function card(overrides = {}) {
  return {
    card_id: "base1-4",
    card_name: "Charizard",
    set_id: "base1",
    set_name: "Base Set",
    printed_total: 102,
    total_count: 102,
    rarity: "Rare Holo",
    supertype: "Pokemon",
    condition: "NM",
    variant: [],
    is_first_edition: false,
    quantity: 1,
    market_price: "100.00",
    purchase_price: null,
    image_url: null,
    ...overrides,
  };
}


describe("totalCollectionValue", () => {
  it("sums quantity * market_price", () => {
    expect(
      totalCollectionValue([
        card({ quantity: 2, market_price: "10.00" }),
        card({ quantity: 1, market_price: "5.00" }),
      ]),
    ).toBe(25);
  });

  it("skips cards without a market price", () => {
    expect(
      totalCollectionValue([
        card({ quantity: 2, market_price: "10.00" }),
        card({ market_price: null }),
      ]),
    ).toBe(20);
  });

  it("returns 0 for an empty collection", () => {
    expect(totalCollectionValue([])).toBe(0);
  });
});


describe("totalCardCount", () => {
  it("sums quantities across cards", () => {
    expect(totalCardCount([card({ quantity: 3 }), card({ quantity: 2 })])).toBe(5);
  });
});


describe("anyPurchasePrices", () => {
  it("returns true when any card has one", () => {
    expect(
      anyPurchasePrices([card(), card({ purchase_price: "12.00" })]),
    ).toBe(true);
  });

  it("returns false when none do", () => {
    expect(anyPurchasePrices([card(), card()])).toBe(false);
  });
});


describe("lifetimeGain", () => {
  it("returns null when no cards have purchase prices", () => {
    expect(lifetimeGain([card(), card()])).toBe(null);
  });

  it("ignores cards without market prices", () => {
    const out = lifetimeGain([
      card({ purchase_price: "5.00", market_price: null }),
    ]);
    expect(out).toBe(null);
  });

  it("computes percent gain across cards with purchase prices", () => {
    const out = lifetimeGain([
      card({ purchase_price: "100.00", market_price: "150.00", quantity: 2 }),
      card({ purchase_price: "50.00", market_price: "60.00", quantity: 1 }),
    ]);
    // cost: 200 + 50 = 250; current: 300 + 60 = 360; gain: 110; pct: 0.44
    expect(out.dollarsGain).toBe(110);
    expect(out.percentGain).toBeCloseTo(0.44);
  });

  it("returns null when costBasis is zero", () => {
    expect(
      lifetimeGain([
        card({ purchase_price: "0", market_price: "10.00" }),
      ]),
    ).toBe(null);
  });
});


describe("mostValuableCard", () => {
  it("picks the highest individual market price (not total value)", () => {
    const result = mostValuableCard([
      card({ card_id: "a", quantity: 3, market_price: "20.00" }), // total $60
      card({ card_id: "b", quantity: 1, market_price: "59.00" }), // total $59
    ]);
    expect(result.card_id).toBe("b");
  });

  it("breaks ties by card_id ascending for determinism", () => {
    const result = mostValuableCard([
      card({ card_id: "z", market_price: "100.00" }),
      card({ card_id: "a", market_price: "100.00" }),
    ]);
    expect(result.card_id).toBe("a");
  });

  it("returns null when nothing has a market price", () => {
    expect(
      mostValuableCard([card({ market_price: null })]),
    ).toBe(null);
  });
});


describe("aggregateBySet", () => {
  it("buckets cards by set with totals and percent share", () => {
    const out = aggregateBySet([
      card({ card_id: "base1-4", set_id: "base1", set_name: "Base Set", market_price: "100", quantity: 1 }),
      card({ card_id: "base1-58", set_id: "base1", set_name: "Base Set", market_price: "50", quantity: 2 }),
      card({ card_id: "j-1", set_id: "jungle", set_name: "Jungle", market_price: "10", quantity: 1 }),
    ]);
    // base1: 100 + 100 = 200; jungle: 10
    expect(out[0].set_id).toBe("base1");
    expect(out[0].total_value).toBe(200);
    expect(out[0].owned_count).toBe(2);
    expect(out[0].total_quantity).toBe(3);
    expect(out[0].percent_of_collection).toBeCloseTo(200 / 210);
    expect(out[1].set_id).toBe("jungle");
  });

  it("treats null market prices as zero contribution", () => {
    const out = aggregateBySet([
      card({ market_price: null, quantity: 5 }),
    ]);
    expect(out[0].total_value).toBe(0);
    expect(out[0].percent_of_collection).toBe(0);
  });
});


describe("topCardsByValue", () => {
  it("sorts by total_value descending", () => {
    const out = topCardsByValue([
      card({ card_id: "a", market_price: "10", quantity: 1 }),
      card({ card_id: "b", market_price: "10", quantity: 5 }),
    ]);
    expect(out[0].card_id).toBe("b");
    expect(out[0].total_value).toBe(50);
  });

  it("computes gain dollars and percent when purchase_price exists", () => {
    const [out] = topCardsByValue([
      card({
        market_price: "150",
        purchase_price: "100",
        quantity: 2,
      }),
    ]);
    expect(out.gain_dollars).toBe(100); // (150 - 100) * 2
    expect(out.gain_percent).toBeCloseTo(0.5);
  });

  it("leaves gain fields null when no purchase price", () => {
    const [out] = topCardsByValue([card({ purchase_price: null })]);
    expect(out.gain_dollars).toBe(null);
    expect(out.gain_percent).toBe(null);
  });

  it("zeros total_value when market_price is null", () => {
    const [out] = topCardsByValue([card({ market_price: null, quantity: 5 })]);
    expect(out.total_value).toBe(0);
  });

  it("returns null gain_percent when purchase basis is zero", () => {
    const [out] = topCardsByValue([
      card({ market_price: "10", purchase_price: "0", quantity: 1 }),
    ]);
    expect(out.gain_percent).toBe(null);
  });
});


describe("variantBars", () => {
  it("excludes Standard-only cards", () => {
    expect(
      variantBars([card({ variant: [], is_first_edition: false })]),
    ).toEqual([]);
  });

  it("aggregates quantities across variant tokens", () => {
    const out = variantBars([
      card({
        card_id: "a",
        variant: ["Reverse Holo", "Misprint"],
        quantity: 2,
      }),
      card({ card_id: "b", variant: ["Reverse Holo"], quantity: 3 }),
    ]);
    const reverse = out.find((b) => b.variant === "Reverse Holo");
    expect(reverse.quantity).toBe(5);
    expect(reverse.unique_cards).toBe(2);
    const misprint = out.find((b) => b.variant === "Misprint");
    expect(misprint.quantity).toBe(2);
    expect(misprint.unique_cards).toBe(1);
  });

  it("counts is_first_edition as a synthetic '1st Edition' bar", () => {
    const out = variantBars([
      card({ is_first_edition: true, quantity: 4 }),
    ]);
    expect(out).toEqual([
      { variant: "1st Edition", quantity: 4, unique_cards: 1 },
    ]);
  });

  it("dedupes repeated variant entries on a single card", () => {
    const out = variantBars([
      card({ variant: ["Reverse Holo", "Reverse Holo"], quantity: 1 }),
    ]);
    expect(out).toEqual([
      { variant: "Reverse Holo", quantity: 1, unique_cards: 1 },
    ]);
  });

  it("ignores blank entries in the variant list", () => {
    const out = variantBars([
      card({ variant: ["", "Holo"], quantity: 2 }),
    ]);
    expect(out).toEqual([
      { variant: "Holo", quantity: 2, unique_cards: 1 },
    ]);
  });

  it("sorts bars by quantity descending", () => {
    const out = variantBars([
      card({ card_id: "a", variant: ["Holo"], quantity: 1 }),
      card({ card_id: "b", variant: ["Reverse Holo"], quantity: 5 }),
    ]);
    expect(out.map((b) => b.variant)).toEqual(["Reverse Holo", "Holo"]);
  });
});
