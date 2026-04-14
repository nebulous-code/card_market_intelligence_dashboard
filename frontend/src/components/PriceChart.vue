<template>
  <v-card class="mb-6">
    <v-card-title class="text-subtitle-1 font-weight-bold pa-4">
      Average Market Price by Rarity
    </v-card-title>
    <v-card-text>
      <!-- Render the bar chart if there is price data to show. -->
      <Bar v-if="chartData" :data="chartData" :options="chartOptions" style="max-height: 320px" />

      <!-- Fallback message when no price data exists for this set. -->
      <v-alert v-else type="info" variant="tonal" density="compact">
        No price data available for this set.
      </v-alert>
    </v-card-text>
  </v-card>
</template>

<script setup>
/**
 * PriceChart component.
 *
 * Displays a bar chart showing the average market price per rarity group
 * for all cards in the selected set. For example, "Rare Holo" cards might
 * average $10 while "Common" cards average $0.50.
 *
 * The chart uses Chart.js via the vue-chartjs wrapper. Chart.js components
 * must be explicitly registered before they can be used -- that is what the
 * ChartJS.register() call below does.
 *
 * Props:
 *   cards          - Array of card objects for the selected set.
 *   pricesByCardId - Map of card ID to that card's latest prices array.
 *                    Pre-fetched by the Dashboard to avoid redundant requests.
 */

import {
  BarElement,
  CategoryScale,
  Chart as ChartJS,
  Legend,
  LinearScale,
  Title,
  Tooltip,
} from "chart.js";
import { computed } from "vue";
import { Bar } from "vue-chartjs";
import { formatCurrency } from "../utils/formatters.js";

// Register all the Chart.js components this chart needs.
// Chart.js uses tree-shaking so only the pieces you explicitly register
// are included in the final bundle.
ChartJS.register(Title, Tooltip, Legend, BarElement, CategoryScale, LinearScale);

const props = defineProps({
  /**
   * Array of card objects from GET /sets/{id}/cards.
   */
  cards: {
    type: Array,
    default: () => [],
  },
  /**
   * Map of card_id to latest_prices array.
   * Keys are card IDs (e.g. "base1-4"), values are arrays of price snapshot
   * objects as returned by GET /cards/{id}.
   */
  pricesByCardId: {
    type: Object,
    default: () => ({}),
  },
});

/**
 * Build the chart data object from the cards and prices props.
 *
 * Groups cards by rarity, finds the best available price for each card
 * (preferring normal condition, falling back to holofoil), and calculates
 * the average price per rarity group.
 *
 * Returns null if no price data is available, which causes the empty state
 * message to be shown instead of an empty chart.
 */
const chartData = computed(() => {
  // Accumulators for computing averages per rarity group.
  const totals = {};
  const counts = {};

  for (const card of props.cards) {
    const rarity = card.rarity ?? "Unknown";
    const prices = props.pricesByCardId[card.id] ?? [];

    // Use NM (Near Mint) — the condition label used by PokemonPriceTracker
    // for standard ungraded TCGPlayer prices.
    const snap = prices.find((p) => p.condition === "NM");
    if (!snap?.market_price) continue; // Skip cards with no price data.

    // Add this card's price to the running total for its rarity group.
    totals[rarity] = (totals[rarity] ?? 0) + Number(snap.market_price);
    counts[rarity] = (counts[rarity] ?? 0) + 1;
  }

  const labels = Object.keys(totals);

  // Return null if there is no data to display.
  if (labels.length === 0) return null;

  return {
    labels,
    datasets: [
      {
        label: "Avg Market Price (USD)",
        // Compute the average for each rarity group.
        data: labels.map((r) => (totals[r] / counts[r]).toFixed(2)),
        backgroundColor: "rgba(99, 102, 241, 0.7)",
        borderColor: "rgba(99, 102, 241, 1)",
        borderWidth: 1,
        borderRadius: 4,
      },
    ],
  };
});

// Chart display options. These control axis formatting and tooltip content.
const chartOptions = {
  responsive: true,
  plugins: {
    legend: { display: false }, // The single dataset label is redundant.
    tooltip: {
      callbacks: {
        label: (ctx) => ` ${formatCurrency(ctx.parsed.y)}`,
      },
    },
  },
  scales: {
    y: {
      ticks: {
        callback: (val) => formatCurrency(val),
      },
    },
  },
};
</script>
