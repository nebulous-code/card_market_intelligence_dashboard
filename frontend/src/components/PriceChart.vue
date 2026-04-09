<template>
  <v-card class="mb-6">
    <v-card-title class="text-subtitle-1 font-weight-bold pa-4">
      Average Market Price by Rarity
    </v-card-title>
    <v-card-text>
      <Bar v-if="chartData" :data="chartData" :options="chartOptions" style="max-height: 320px" />
      <v-alert v-else type="info" variant="tonal" density="compact">
        No price data available for this set.
      </v-alert>
    </v-card-text>
  </v-card>
</template>

<script setup>
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

ChartJS.register(Title, Tooltip, Legend, BarElement, CategoryScale, LinearScale);

const props = defineProps({
  /**
   * Array of card objects from GET /sets/{id}/cards.
   * Each card should have a `rarity` field and will be cross-referenced
   * with latestPrices.
   */
  cards: {
    type: Array,
    default: () => [],
  },
  /**
   * Map of card_id → latest_prices array (from GET /cards/{id}).
   * Pre-fetched by the parent to avoid N+1 requests per chart render.
   */
  pricesByCardId: {
    type: Object,
    default: () => ({}),
  },
});

const chartData = computed(() => {
  // Aggregate average normal-condition market price per rarity.
  const totals = {};
  const counts = {};

  for (const card of props.cards) {
    const rarity = card.rarity ?? "Unknown";
    const prices = props.pricesByCardId[card.id] ?? [];
    const normalSnap = prices.find((p) => p.condition === "normal" || p.condition === "holofoil");
    if (!normalSnap?.market_price) continue;

    totals[rarity] = (totals[rarity] ?? 0) + Number(normalSnap.market_price);
    counts[rarity] = (counts[rarity] ?? 0) + 1;
  }

  const labels = Object.keys(totals);
  if (labels.length === 0) return null;

  return {
    labels,
    datasets: [
      {
        label: "Avg Market Price (USD)",
        data: labels.map((r) => (totals[r] / counts[r]).toFixed(2)),
        backgroundColor: "rgba(99, 102, 241, 0.7)",
        borderColor: "rgba(99, 102, 241, 1)",
        borderWidth: 1,
        borderRadius: 4,
      },
    ],
  };
});

const chartOptions = {
  responsive: true,
  plugins: {
    legend: { display: false },
    tooltip: {
      callbacks: {
        label: (ctx) => ` $${ctx.parsed.y}`,
      },
    },
  },
  scales: {
    y: {
      ticks: {
        callback: (val) => `$${val}`,
      },
    },
  },
};
</script>
