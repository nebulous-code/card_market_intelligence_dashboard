import { describe, it, expect } from "vitest";

import {
  formatCurrency,
  formatDate,
  formatNumber,
  formatPercent,
  formatCompactCurrency,
  formatMonthYear,
} from "../../src/utils/formatters.js";

describe("formatCurrency", () => {
  it("formats a number as USD with two decimals", () => {
    expect(formatCurrency(399.99)).toBe("$399.99");
  });

  it("rounds to two decimal places", () => {
    expect(formatCurrency(1.234)).toBe("$1.23");
    expect(formatCurrency(1.235)).toMatch(/^\$1\.2[34]$/);
  });

  it("formats sub-dollar values with two decimals", () => {
    expect(formatCurrency(0.04)).toBe("$0.04");
    expect(formatCurrency(0.1)).toBe("$0.10");
  });

  it("returns the em-dash placeholder for null/undefined/NaN", () => {
    expect(formatCurrency(null)).toBe("—");
    expect(formatCurrency(undefined)).toBe("—");
    expect(formatCurrency("not-a-number")).toBe("—");
  });
});

describe("formatDate", () => {
  it("formats an ISO date string as 'Mon DD, YYYY'", () => {
    // Pin to a stable, timezone-resistant date by using midday UTC.
    const out = formatDate("2026-04-13T12:00:00Z");
    expect(out).toMatch(/Apr 13, 2026/);
  });

  it("returns the em-dash placeholder for null/empty input", () => {
    expect(formatDate(null)).toBe("—");
    expect(formatDate(undefined)).toBe("—");
    expect(formatDate("")).toBe("—");
  });
});

describe("formatNumber", () => {
  it("inserts comma separators for large numbers", () => {
    expect(formatNumber(1234)).toBe("1,234");
    expect(formatNumber(1_000_000)).toBe("1,000,000");
  });

  it("returns the em-dash placeholder for null/undefined/NaN", () => {
    expect(formatNumber(null)).toBe("—");
    expect(formatNumber(undefined)).toBe("—");
    expect(formatNumber("nope")).toBe("—");
  });
});

describe("formatPercent", () => {
  it("formats a decimal as a percent with two decimals", () => {
    expect(formatPercent(0.1234)).toBe("12.34%");
  });

  it("returns the em-dash placeholder for null/undefined/NaN", () => {
    expect(formatPercent(null)).toBe("—");
    expect(formatPercent(undefined)).toBe("—");
    expect(formatPercent("x")).toBe("—");
  });
});

describe("formatCompactCurrency", () => {
  it("uses compact notation for large amounts", () => {
    expect(formatCompactCurrency(1500)).toMatch(/\$1\.5K/);
    expect(formatCompactCurrency(15_000)).toMatch(/\$15K/);
  });

  it("renders sub-1K amounts as plain dollars", () => {
    expect(formatCompactCurrency(400)).toBe("$400");
  });

  it("returns the em-dash placeholder for null/undefined/NaN", () => {
    expect(formatCompactCurrency(null)).toBe("—");
    expect(formatCompactCurrency(undefined)).toBe("—");
    expect(formatCompactCurrency("nope")).toBe("—");
  });
});

describe("formatMonthYear", () => {
  it("renders an ISO date as 'Mon YYYY'", () => {
    const out = formatMonthYear("1999-01-09T12:00:00Z");
    expect(out).toMatch(/Jan 1999/);
  });

  it("returns the em-dash placeholder for null/empty input", () => {
    expect(formatMonthYear(null)).toBe("—");
    expect(formatMonthYear(undefined)).toBe("—");
    expect(formatMonthYear("")).toBe("—");
  });
});
