import { describe, it, expect, vi, beforeEach } from "vitest";

// Mock axios at the module boundary so we never make real HTTP calls.
// The factory needs the spies at hoisted scope because vi.mock() executes
// before any top-level `const`. vi.hoisted() lets us share the spies with
// both the factory and the per-test assertions.
const { httpGet, httpPost, httpDelete } = vi.hoisted(() => ({
  httpGet: vi.fn(),
  httpPost: vi.fn(),
  httpDelete: vi.fn(),
}));
vi.mock("axios", () => ({
  default: {
    create: vi.fn(() => ({ get: httpGet, post: httpPost, delete: httpDelete })),
  },
}));

import {
  getSets,
  getSet,
  getCardsForSet,
  getCard,
  getSetCardPrices,
  getPriceHistory,
  getReferenceConditions,
  getReferenceVariants,
  getReferenceRarities,
  getSetsWithMultipliers,
  getConditionMultipliers,
  getHealth,
  downloadCollectionTemplate,
  uploadCollection,
  downloadAnnotatedWorkbook,
  useMockCollection,
  getCollectionSession,
  deleteCollectionSession,
} from "../../src/api/index.js";

beforeEach(() => {
  httpGet.mockReset();
  httpPost.mockReset();
  httpDelete.mockReset();
});

describe("getSets", () => {
  it("GETs /sets and unwraps the data field", async () => {
    httpGet.mockResolvedValue({ data: [{ id: "base1" }] });
    const result = await getSets();
    expect(httpGet).toHaveBeenCalledWith("/sets");
    expect(result).toEqual([{ id: "base1" }]);
  });
});

describe("getSet", () => {
  it("GETs /sets/{id}", async () => {
    httpGet.mockResolvedValue({ data: { id: "base1" } });
    const result = await getSet("base1");
    expect(httpGet).toHaveBeenCalledWith("/sets/base1");
    expect(result).toEqual({ id: "base1" });
  });
});

describe("getCardsForSet", () => {
  it("GETs /sets/{id}/cards", async () => {
    httpGet.mockResolvedValue({ data: [{ id: "base1-1" }] });
    await getCardsForSet("base1");
    expect(httpGet).toHaveBeenCalledWith("/sets/base1/cards");
  });
});

describe("getCard", () => {
  it("GETs /cards/{id}", async () => {
    httpGet.mockResolvedValue({ data: { id: "base1-4" } });
    const result = await getCard("base1-4");
    expect(httpGet).toHaveBeenCalledWith("/cards/base1-4");
    expect(result).toEqual({ id: "base1-4" });
  });
});

describe("getSetCardPrices", () => {
  it("returns the inner `prices` map, not the whole envelope", async () => {
    httpGet.mockResolvedValue({ data: { prices: { "base1-4": [] } } });
    const result = await getSetCardPrices("base1");
    expect(httpGet).toHaveBeenCalledWith("/sets/base1/cards/prices");
    expect(result).toEqual({ "base1-4": [] });
  });
});

describe("getPriceHistory", () => {
  it("GETs the price-history endpoint with no params by default", async () => {
    httpGet.mockResolvedValue({ data: { card_id: "base1-4", snapshots: [] } });
    await getPriceHistory("base1-4");
    expect(httpGet).toHaveBeenCalledWith(
      "/cards/base1-4/price-history",
      { params: {} },
    );
  });

  it("forwards filters as query params", async () => {
    httpGet.mockResolvedValue({ data: { card_id: "base1-4", snapshots: [] } });
    await getPriceHistory("base1-4", { source: "tcgplayer", condition: "NM" });
    expect(httpGet).toHaveBeenCalledWith(
      "/cards/base1-4/price-history",
      { params: { source: "tcgplayer", condition: "NM" } },
    );
  });
});

describe("reference list helpers", () => {
  it("getReferenceConditions GETs /reference/conditions", async () => {
    httpGet.mockResolvedValue({ data: [{ value: "NM" }] });
    await getReferenceConditions();
    expect(httpGet).toHaveBeenCalledWith("/reference/conditions");
  });

  it("getReferenceVariants GETs /reference/variants", async () => {
    httpGet.mockResolvedValue({ data: [{ value: null }] });
    await getReferenceVariants();
    expect(httpGet).toHaveBeenCalledWith("/reference/variants");
  });

  it("getReferenceRarities GETs /reference/rarities", async () => {
    httpGet.mockResolvedValue({ data: [{ value: "common" }] });
    await getReferenceRarities();
    expect(httpGet).toHaveBeenCalledWith("/reference/rarities");
  });
});

describe("trends helpers", () => {
  it("getSetsWithMultipliers GETs /trends/sets-with-multipliers", async () => {
    httpGet.mockResolvedValue({ data: { sets: [] } });
    await getSetsWithMultipliers();
    expect(httpGet).toHaveBeenCalledWith("/trends/sets-with-multipliers");
  });

  it("getConditionMultipliers forwards set_id and grouping_type", async () => {
    httpGet.mockResolvedValue({ data: { groupings: [] } });
    await getConditionMultipliers("base1", "rarity");
    expect(httpGet).toHaveBeenCalledWith(
      "/trends/condition-multipliers",
      { params: { set_id: "base1", grouping_type: "rarity" } },
    );
  });
});

describe("getHealth", () => {
  it("GETs /health", async () => {
    httpGet.mockResolvedValue({ data: { status: "ok" } });
    const result = await getHealth();
    expect(httpGet).toHaveBeenCalledWith("/health");
    expect(result).toEqual({ status: "ok" });
  });
});

describe("downloadCollectionTemplate", () => {
  it("GETs /collection/template as a blob and unwraps data", async () => {
    const blob = new Blob(["xlsx-bytes"]);
    httpGet.mockResolvedValue({ data: blob });
    const result = await downloadCollectionTemplate();
    expect(httpGet).toHaveBeenCalledWith(
      "/collection/template",
      { responseType: "blob" },
    );
    expect(result).toBe(blob);
  });
});

describe("uploadCollection", () => {
  it("POSTs the file as multipart and returns the JSON body", async () => {
    httpPost.mockResolvedValue({
      data: { session_id: "abc", card_count: 3, set_count: 1 },
    });
    const file = new File(["xlsx"], "collection.xlsx");
    const result = await uploadCollection(file);

    expect(httpPost).toHaveBeenCalledTimes(1);
    const [path, form] = httpPost.mock.calls[0];
    expect(path).toBe("/collection/upload");
    expect(form).toBeInstanceOf(FormData);
    expect(form.get("file")).toBe(file);
    expect(result).toEqual({ session_id: "abc", card_count: 3, set_count: 1 });
  });
});

describe("downloadAnnotatedWorkbook", () => {
  it("POSTs the file and returns the blob", async () => {
    const blob = new Blob(["annotated"]);
    httpPost.mockResolvedValue({ data: blob });
    const file = new File(["xlsx"], "errors.xlsx");
    const result = await downloadAnnotatedWorkbook(file);

    expect(httpPost).toHaveBeenCalledTimes(1);
    const [path, form, opts] = httpPost.mock.calls[0];
    expect(path).toBe("/collection/upload/annotated");
    expect(form).toBeInstanceOf(FormData);
    expect(form.get("file")).toBe(file);
    expect(opts).toEqual({ responseType: "blob" });
    expect(result).toBe(blob);
  });
});

describe("useMockCollection", () => {
  it("POSTs /collection/mock with no body", async () => {
    httpPost.mockResolvedValue({
      data: { session_id: "abc", card_count: 20, set_count: 4 },
    });
    const result = await useMockCollection();
    expect(httpPost).toHaveBeenCalledWith("/collection/mock");
    expect(result).toEqual({ session_id: "abc", card_count: 20, set_count: 4 });
  });
});

describe("getCollectionSession", () => {
  it("GETs /collection/session", async () => {
    httpGet.mockResolvedValue({
      data: { session_id: "abc", rows: [], card_count: 0, set_count: 0 },
    });
    const result = await getCollectionSession();
    expect(httpGet).toHaveBeenCalledWith("/collection/session");
    expect(result.session_id).toBe("abc");
  });
});

describe("deleteCollectionSession", () => {
  it("DELETEs /collection/session and resolves to undefined", async () => {
    httpDelete.mockResolvedValue({ status: 204 });
    const result = await deleteCollectionSession();
    expect(httpDelete).toHaveBeenCalledWith("/collection/session");
    expect(result).toBeUndefined();
  });
});

describe("axios baseURL configuration", () => {
  it("uses VITE_API_BASE_URL when it is set", async () => {
    // The branch is /* v8 ignore */d in the source because v8 can't merge
    // hits across dynamic re-imports, but the behavior is still asserted
    // here -- a regression in baseURL resolution would be caught by this
    // test even though the branch counter doesn't reflect it.
    import.meta.env.VITE_API_BASE_URL = "https://api.example.com";
    vi.resetModules();

    const axios = (await import("axios")).default;
    await import("../../src/api/index.js");

    expect(axios.create).toHaveBeenCalledWith(
      expect.objectContaining({ baseURL: "https://api.example.com" }),
    );
    delete import.meta.env.VITE_API_BASE_URL;
  });
});
