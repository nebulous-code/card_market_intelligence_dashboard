/**
 * Color mapping for Condition Multiplier heatmap cells.
 *
 * Pulled out of the component so it can be unit-tested at 100% without
 * mounting Vue. The palette follows the Magikarp theme: gold for "no
 * discount" (multiplier near 1) shifting through orange to deep red for
 * steep discounts (multiplier near 0).
 *
 * The boundaries below are the exact ones from the M04_S01 spec.
 */

const BANDS = [
  { min: 0.9,  color: "rgba(245, 200,  66, 0.85)" },
  { min: 0.8,  color: "rgba(238, 175,  48, 0.80)" },
  { min: 0.7,  color: "rgba(224, 140,  36, 0.75)" },
  { min: 0.6,  color: "rgba(220, 100,  30, 0.70)" },
  { min: 0.5,  color: "rgba(220,  70,  28, 0.65)" },
  { min: 0.4,  color: "rgba(210,  50,  25, 0.60)" },
  { min: 0.3,  color: "rgba(200,  38,  22, 0.55)" },
  { min: 0,    color: "rgba(180,  28,  18, 0.50)" },
];

/** Background color reserved for the NM column or empty cells. */
export const MUTED_BACKGROUND = "rgba(255, 255, 255, 0.04)";

/**
 * Pick the heatmap cell color for a given multiplier.
 *
 * Multipliers above 1.0 (which can happen on noisy low-value commons --
 * see the comment on the migration) clamp to the topmost band; null falls
 * back to the muted background.
 *
 * @param {number|null} multiplier
 * @returns {string} An rgba() color string.
 */
export function colorForMultiplier(multiplier) {
  if (multiplier == null) return MUTED_BACKGROUND;
  for (const band of BANDS) {
    if (multiplier >= band.min) return band.color;
  }
  // Negative or NaN -- shouldn't happen with valid data but keeps the
  // function total rather than throwing.
  return MUTED_BACKGROUND;
}
