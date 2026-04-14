<template>
  <div>
    <!-- Loading state for header -->
    <v-skeleton-loader v-if="loadingSet" type="list-item-two-line" class="mb-6" />

    <!-- Set header -->
    <v-card v-else-if="set" class="mb-6">
      <v-card-text>
        <v-row align="center">
          <v-col cols="auto">
            <v-img
              v-if="set.logo_url"
              :src="set.logo_url"
              :alt="set.name"
              max-height="80"
              max-width="160"
              contain
            />
          </v-col>
          <v-col>
            <div class="text-h5 font-weight-bold">{{ set.name }}</div>
            <div class="text-subtitle-1 text-medium-emphasis">{{ set.series }}</div>
          </v-col>
          <v-col cols="auto" class="text-right">
            <div class="text-body-2 text-medium-emphasis">Cards</div>
            <div class="text-h6">{{ formatNumber(set.printed_total) }}</div>
          </v-col>
          <v-col cols="auto" class="text-right">
            <div class="text-body-2 text-medium-emphasis">Released</div>
            <div class="text-h6">{{ formatDate(set.release_date) }}</div>
          </v-col>
        </v-row>
      </v-card-text>
    </v-card>

    <!-- Price distribution chart -->
    <v-card class="mb-6">
      <v-card-title class="text-subtitle-1 font-weight-bold pa-4">
        Price Distribution by Rarity
      </v-card-title>
      <v-card-text>
        <v-skeleton-loader v-if="loadingCards" type="image" />
        <EmptyState
          v-else-if="!chartData"
          icon="mdi-chart-box-outline"
          title="No price data"
          message="Price data has not been ingested for this set yet."
        />
        <BoxPlot
          v-else
          :data="chartData"
          :options="chartOptions"
          style="max-height: 360px"
        />
      </v-card-text>
    </v-card>

    <!-- Card table -->
    <CardTable
      :cards="cards"
      :prices-by-card-id="pricesByCardId"
      :loading="loadingCards"
    />
  </div>
</template>

<script setup>
import {
  BoxAndWiskers,
  BoxPlotController,
} from "@sgratzl/chartjs-chart-boxplot";
import {
  CategoryScale,
  Chart,
  LinearScale,
  LogarithmicScale,
  Tooltip,
} from "chart.js";
import { computed, inject, onMounted, onUnmounted, ref, watch } from "vue";
import { useRoute } from "vue-router";
import { getCardsForSet, getSet, getSetCardPrices } from "../api/index.js";
import CardTable from "../components/CardTable.vue";
import EmptyState from "../components/EmptyState.vue";
import { formatCompactCurrency, formatCurrency, formatDate, formatNumber } from "../utils/formatters.js";

// Register Chart.js + box plot plugin
Chart.register(BoxPlotController, BoxAndWiskers, CategoryScale, LinearScale, LogarithmicScale, Tooltip);

// Custom chart component wrapping the boxplot type
import { defineComponent, h } from "vue";
const BoxPlot = defineComponent({
  name: "BoxPlot",
  props: { data: Object, options: Object },
  setup(props) {
    const { ref: canvasRef, onMounted: onMountedInner } = { ref: null, onMounted: null };
    return () =>
      h("canvas", {
        ref: "canvas",
        style: "max-height: 360px; width: 100%;",
      });
  },
  mounted() {
    this._chart = new Chart(this.$el, {
      type: "boxplot",
      data: this.data,
      options: this.options,
    });
  },
  watch: {
    data: {
      deep: true,
      handler(val) {
        if (this._chart) {
          this._chart.data = val;
          this._chart.update();
        }
      },
    },
  },
  beforeUnmount() {
    if (this._chart) {
      this._chart.destroy();
    }
  },
});

const route = useRoute();
const setId = computed(() => route.params.setId);

const setCrumb = inject('setCrumb', () => {})
const clearCrumbs = inject('clearCrumbs', () => {})

const set = ref(null);
const cards = ref([]);
const pricesByCardId = ref({});
const loadingSet = ref(true);
const loadingCards = ref(true);

// Rarity sort order
const RARITY_ORDER = ["Common", "Uncommon", "Rare", "Rare Holo"];

const chartData = computed(() => {
  if (!cards.value.length) return null;

  // Group market prices by rarity
  const groups = {};
  for (const card of cards.value) {
    const rarity = card.rarity ?? "Unknown";
    const prices = pricesByCardId.value[card.id] ?? [];
    const snap = prices.find((p) => p.condition === "NM") ?? prices[0];
    if (!snap?.market_price) continue;
    if (!groups[rarity]) groups[rarity] = [];
    groups[rarity].push(Number(snap.market_price));
  }

  if (Object.keys(groups).length === 0) return null;

  // Sort rarities: standard order first, then alphabetical
  const labels = Object.keys(groups).sort((a, b) => {
    const ai = RARITY_ORDER.indexOf(a);
    const bi = RARITY_ORDER.indexOf(b);
    if (ai !== -1 && bi !== -1) return ai - bi;
    if (ai !== -1) return -1;
    if (bi !== -1) return 1;
    return a.localeCompare(b);
  });

  return {
    labels,
    datasets: [
      {
        label: "Market Price",
        data: labels.map((r) => groups[r]),
        backgroundColor: "rgba(232, 65, 42, 0.3)",
        borderColor: "#E8412A",
        borderWidth: 1,
        medianColor: "#F5C842",
        outlierColor: "rgba(245, 200, 66, 0.7)",
        whiskerColor: "#E8412A",
        padding: 8,
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
        label(ctx) {
          const { min, q1, median, q3, max } = ctx.raw ?? {};
          const count = ctx.raw?.items?.length ?? (Array.isArray(ctx.raw) ? ctx.raw.length : "?");
          return [
            `Cards: ${count}`,
            `Min: ${formatCurrency(min)}`,
            `Q1: ${formatCurrency(q1)}`,
            `Median: ${formatCurrency(median)}`,
            `Q3: ${formatCurrency(q3)}`,
            `Max: ${formatCurrency(max)}`,
          ];
        },
      },
    },
  },
  scales: {
    y: {
      type: "logarithmic",
      title: { display: true, text: "Market Price (USD)" },
      ticks: {
        callback: (val) => formatCompactCurrency(val),
      },
    },
  },
};

async function loadSet() {
  loadingSet.value = true;
  try {
    set.value = await getSet(setId.value);
    setCrumb(1, set.value.name, null);
  } finally {
    loadingSet.value = false;
  }
}

async function loadCards() {
  loadingCards.value = true;
  cards.value = [];
  pricesByCardId.value = {};
  try {
    cards.value = await getCardsForSet(setId.value);
  } finally {
    loadingCards.value = false;
  }
  // Load prices independently so card table shows even if prices fail
  try {
    pricesByCardId.value = await getSetCardPrices(setId.value);
  } catch {
    pricesByCardId.value = {};
  }
}

onMounted(() => {
  loadSet();
  loadCards();
});

onUnmounted(() => {
  clearCrumbs();
});

watch(setId, () => {
  clearCrumbs();
  loadSet();
  loadCards();
});
</script>
