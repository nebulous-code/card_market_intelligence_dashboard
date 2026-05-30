import { describe, it, expect } from "vitest";

import {
  MUTED_BACKGROUND,
  colorForMultiplier,
} from "../../src/utils/heatmapColors.js";

describe("colorForMultiplier", () => {
  it("returns the muted background for null", () => {
    expect(colorForMultiplier(null)).toBe(MUTED_BACKGROUND);
  });

  it("returns the muted background for undefined", () => {
    expect(colorForMultiplier(undefined)).toBe(MUTED_BACKGROUND);
  });

  it("returns the gold band for 1.0 (or above)", () => {
    expect(colorForMultiplier(1.0)).toContain("245, 200,  66");
    expect(colorForMultiplier(1.5)).toContain("245, 200,  66"); // clamps high
  });

  it("returns the right band at each boundary", () => {
    expect(colorForMultiplier(0.95)).toContain("245, 200,  66"); // top band
    expect(colorForMultiplier(0.85)).toContain("238, 175,  48");
    expect(colorForMultiplier(0.75)).toContain("224, 140,  36");
    expect(colorForMultiplier(0.65)).toContain("220, 100,  30");
    expect(colorForMultiplier(0.55)).toContain("220,  70,  28");
    expect(colorForMultiplier(0.45)).toContain("210,  50,  25");
    expect(colorForMultiplier(0.35)).toContain("200,  38,  22");
    expect(colorForMultiplier(0.10)).toContain("180,  28,  18"); // bottom band
  });

  it("treats exact boundary values as the higher band", () => {
    expect(colorForMultiplier(0.9)).toContain("245, 200,  66");
    expect(colorForMultiplier(0.8)).toContain("238, 175,  48");
    expect(colorForMultiplier(0.5)).toContain("220,  70,  28");
  });

  it("returns muted background for negative or NaN", () => {
    // Defensive paths -- shouldn't happen with well-formed data.
    expect(colorForMultiplier(-0.1)).toBe(MUTED_BACKGROUND);
    expect(colorForMultiplier(Number.NaN)).toBe(MUTED_BACKGROUND);
  });
});
