/**
 * Heatmap data transforms for the Condition Multiplier view.
 *
 * The API returns the full pairwise transition list (up to 10 entries per
 * grouping). The visible heatmap shows only the cascade from NM -- one cell
 * per condition column, displaying the cumulative NM->X multiplier. The full
 * transition list is still exposed on the cell so tooltips can show the
 * alternate paths (e.g. LP->X).
 *
 * Splitting these transforms out of the component keeps them unit-testable
 * without mounting Vue, which is consistent with the project's "100% on
 * src/utils" coverage policy.
 */

/** Condition columns rendered in the heatmap, left-to-right. */
export const CONDITION_COLUMNS = ["NM", "LP", "MP", "HP", "DMG"];

/**
 * Build one heatmap row from a grouping's flat transition list.
 *
 * The returned cells line up with CONDITION_COLUMNS. The NM cell is the
 * anchor (multiplier=1, no data points); subsequent cells carry the
 * NM->that-condition multiplier when present, plus every pairwise
 * transition ending at that condition (for tooltips).
 *
 * @param {Object} grouping - GroupingResponse from the API.
 * @param {Array<{from_condition: string, to_condition: string,
 *                multiplier: number|string, data_points: number}>}
 *        grouping.transitions
 * @param {string} grouping.grouping_value
 * @param {string} grouping.grouping_label
 * @returns {{
 *   groupingValue: string,
 *   groupingLabel: string,
 *   cells: Array<{
 *     condition: string,
 *     multiplier: number|null,
 *     dataPoints: number|null,
 *     incomingTransitions: Array<{
 *       fromCondition: string,
 *       multiplier: number,
 *       dataPoints: number
 *     }>
 *   }>
 * }}
 */
export function buildCascadeRow(grouping) {
  const transitions = grouping.transitions ?? [];

  // Index every transition by its destination condition so we can quickly
  // pull "all paths ending at LP", "all paths ending at MP", etc.
  const byDestination = new Map();
  for (const t of transitions) {
    if (!byDestination.has(t.to_condition)) {
      byDestination.set(t.to_condition, []);
    }
    byDestination.get(t.to_condition).push({
      fromCondition: t.from_condition,
      multiplier: Number(t.multiplier),
      dataPoints: t.data_points,
    });
  }

  const cells = CONDITION_COLUMNS.map((condition) => {
    if (condition === "NM") {
      // The NM column is the reference point. Always rendered as 1.0 with
      // no underlying data; the muted styling is handled in the component.
      return {
        condition,
        multiplier: 1,
        dataPoints: null,
        incomingTransitions: [],
      };
    }

    const incoming = byDestination.get(condition) ?? [];
    const fromNM = incoming.find((t) => t.fromCondition === "NM");
    return {
      condition,
      multiplier: fromNM ? fromNM.multiplier : null,
      dataPoints: fromNM ? fromNM.dataPoints : null,
      incomingTransitions: incoming,
    };
  });

  return {
    groupingValue: grouping.grouping_value,
    groupingLabel: grouping.grouping_label,
    cells,
  };
}

/**
 * Compute summary metrics for the four cards under the heatmap.
 *
 * @param {Array<ReturnType<typeof buildCascadeRow>>} rows - Cascade rows.
 * @returns {{
 *   avgLpRatio: number|null,
 *   avgMpRatio: number|null,
 *   steepestDrop: { groupingLabel: string, multiplier: number } | null,
 *   totalDataPoints: number
 * }}
 */
export function summarizeCascade(rows) {
  const lpValues = [];
  const mpValues = [];
  let steepest = null;
  let totalDataPoints = 0;

  for (const row of rows) {
    const lpCell = row.cells.find((c) => c.condition === "LP");
    const mpCell = row.cells.find((c) => c.condition === "MP");

    if (lpCell?.multiplier != null) {
      lpValues.push(lpCell.multiplier);
      // "Steepest drop" is the grouping with the lowest NM->LP -- that's
      // the cliff users care about most ("which cards lose value fastest
      // when they leave NM?").
      if (steepest === null || lpCell.multiplier < steepest.multiplier) {
        steepest = {
          groupingLabel: row.groupingLabel,
          multiplier: lpCell.multiplier,
        };
      }
    }
    if (mpCell?.multiplier != null) {
      mpValues.push(mpCell.multiplier);
    }

    for (const cell of row.cells) {
      if (cell.dataPoints != null) {
        totalDataPoints += cell.dataPoints;
      }
    }
  }

  const avg = (values) =>
    values.length === 0
      ? null
      : values.reduce((a, b) => a + b, 0) / values.length;

  return {
    avgLpRatio: avg(lpValues),
    avgMpRatio: avg(mpValues),
    steepestDrop: steepest,
    totalDataPoints,
  };
}
