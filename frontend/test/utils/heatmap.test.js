import { describe, it, expect } from "vitest";

import {
  CONDITION_COLUMNS,
  buildCascadeRow,
  summarizeCascade,
} from "../../src/utils/heatmap.js";

describe("CONDITION_COLUMNS", () => {
  it("lists the five conditions left-to-right", () => {
    expect(CONDITION_COLUMNS).toEqual(["NM", "LP", "MP", "HP", "DMG"]);
  });
});

describe("buildCascadeRow", () => {
  it("emits a cell per condition column", () => {
    const row = buildCascadeRow({
      grouping_value: "rare",
      grouping_label: "Rare",
      transitions: [],
    });
    expect(row.cells.map((c) => c.condition)).toEqual(CONDITION_COLUMNS);
    expect(row.groupingValue).toBe("rare");
    expect(row.groupingLabel).toBe("Rare");
  });

  it("anchors NM at multiplier=1 with no data points", () => {
    const row = buildCascadeRow({
      grouping_value: "rare",
      grouping_label: "Rare",
      transitions: [],
    });
    const nm = row.cells.find((c) => c.condition === "NM");
    expect(nm.multiplier).toBe(1);
    expect(nm.dataPoints).toBeNull();
    expect(nm.incomingTransitions).toEqual([]);
  });

  it("uses the NM->X transition for each non-NM cell's multiplier", () => {
    const row = buildCascadeRow({
      grouping_value: "rare",
      grouping_label: "Rare",
      transitions: [
        { from_condition: "NM", to_condition: "LP",  multiplier: "0.6", data_points: 50 },
        { from_condition: "NM", to_condition: "MP",  multiplier: "0.4", data_points: 40 },
        { from_condition: "NM", to_condition: "HP",  multiplier: "0.3", data_points: 30 },
        { from_condition: "NM", to_condition: "DMG", multiplier: "0.2", data_points: 20 },
      ],
    });
    const byCondition = Object.fromEntries(
      row.cells.map((c) => [c.condition, c]),
    );
    expect(byCondition.LP.multiplier).toBeCloseTo(0.6);
    expect(byCondition.LP.dataPoints).toBe(50);
    expect(byCondition.MP.multiplier).toBeCloseTo(0.4);
    expect(byCondition.DMG.multiplier).toBeCloseTo(0.2);
  });

  it("returns null multiplier when no NM->X transition is present", () => {
    const row = buildCascadeRow({
      grouping_value: "common",
      grouping_label: "Common",
      transitions: [
        // No NM->LP transition -- only an LP->MP one.
        { from_condition: "LP", to_condition: "MP", multiplier: "0.7", data_points: 8 },
      ],
    });
    const lp = row.cells.find((c) => c.condition === "LP");
    expect(lp.multiplier).toBeNull();
    expect(lp.dataPoints).toBeNull();
  });

  it("captures every transition ending at a column for tooltip use", () => {
    const row = buildCascadeRow({
      grouping_value: "rare",
      grouping_label: "Rare",
      transitions: [
        { from_condition: "NM", to_condition: "MP", multiplier: "0.4", data_points: 40 },
        { from_condition: "LP", to_condition: "MP", multiplier: "0.7", data_points: 35 },
      ],
    });
    const mp = row.cells.find((c) => c.condition === "MP");
    expect(mp.incomingTransitions).toHaveLength(2);
    const fromLabels = mp.incomingTransitions.map((t) => t.fromCondition).sort();
    expect(fromLabels).toEqual(["LP", "NM"]);
  });

  it("treats missing transitions field as an empty list", () => {
    const row = buildCascadeRow({
      grouping_value: "x",
      grouping_label: "X",
      // no transitions field at all
    });
    expect(row.cells.every((c) => c.condition === "NM" || c.multiplier === null)).toBe(true);
  });
});

describe("summarizeCascade", () => {
  function rowOf(label, lp, mp, dataPoints) {
    return buildCascadeRow({
      grouping_value: label.toLowerCase(),
      grouping_label: label,
      transitions: [
        ...(lp != null
          ? [{ from_condition: "NM", to_condition: "LP", multiplier: String(lp), data_points: dataPoints }]
          : []),
        ...(mp != null
          ? [{ from_condition: "NM", to_condition: "MP", multiplier: String(mp), data_points: dataPoints }]
          : []),
      ],
    });
  }

  it("averages LP and MP ratios across rows", () => {
    const summary = summarizeCascade([
      rowOf("Rare", 0.6, 0.4, 50),
      rowOf("Uncommon", 0.7, 0.5, 30),
    ]);
    expect(summary.avgLpRatio).toBeCloseTo(0.65);
    expect(summary.avgMpRatio).toBeCloseTo(0.45);
  });

  it("identifies the row with the steepest NM->LP drop", () => {
    const summary = summarizeCascade([
      rowOf("Rare",     0.5, 0.3, 50),
      rowOf("Uncommon", 0.7, 0.5, 30),
      rowOf("Common",   0.6, 0.4, 100),
    ]);
    expect(summary.steepestDrop.groupingLabel).toBe("Rare");
    expect(summary.steepestDrop.multiplier).toBeCloseTo(0.5);
  });

  it("sums data points across every cell that has them", () => {
    const summary = summarizeCascade([
      rowOf("Rare", 0.5, 0.3, 10),
      rowOf("Uncommon", 0.6, 0.4, 20),
    ]);
    // Each rowOf row has 2 cells (LP, MP) with the same dataPoints -- so 10+10+20+20.
    expect(summary.totalDataPoints).toBe(60);
  });

  it("returns null averages and steepestDrop when no rows have LP/MP data", () => {
    const summary = summarizeCascade([]);
    expect(summary.avgLpRatio).toBeNull();
    expect(summary.avgMpRatio).toBeNull();
    expect(summary.steepestDrop).toBeNull();
    expect(summary.totalDataPoints).toBe(0);
  });

  it("handles rows with only LP data (no MP)", () => {
    const summary = summarizeCascade([rowOf("Rare", 0.6, null, 50)]);
    expect(summary.avgLpRatio).toBeCloseTo(0.6);
    expect(summary.avgMpRatio).toBeNull();
  });
});
