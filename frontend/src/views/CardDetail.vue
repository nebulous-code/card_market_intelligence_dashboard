<template>
  <v-container class="py-6">

    <!-- Back button -->
    <v-btn
      :to="'/sets'"
      variant="text"
      prepend-icon="mdi-arrow-left"
      class="mb-4"
    >
      Back to Sets
    </v-btn>

    <!-- Loading state -->
    <div v-if="loading" class="d-flex justify-center py-12">
      <v-progress-circular indeterminate color="primary" size="48" />
    </div>

    <!-- Error state -->
    <v-alert v-else-if="error" type="error" variant="tonal" class="mb-4">
      {{ error }}
    </v-alert>

    <!-- Card content -->
    <template v-else-if="card">

      <!-- Card header: image + metadata -->
      <v-row class="mb-6" align="start">
        <v-col cols="auto">
          <v-img
            v-if="card.image_url"
            :src="card.image_url"
            width="180"
            contain
            class="rounded"
          />
        </v-col>
        <v-col>
          <div class="text-h4 font-weight-bold mb-1">{{ card.name }}</div>
          <div class="text-subtitle-1 text-medium-emphasis mb-4">
            {{ card.set_display_name ?? card.set_id }} &bull; #{{ card.number }}/{{ card.set_printed_total ?? '?' }}
          </div>
          <v-chip v-if="card.supertype" class="mr-2" color="primary" variant="tonal">
            {{ card.supertype }}
          </v-chip>
          <v-chip v-if="card.rarity" variant="tonal">
            {{ card.rarity }}
          </v-chip>
        </v-col>
      </v-row>

      <!-- Source / condition filters -->
      <v-row class="mb-4" dense>
        <v-col cols="12" sm="4">
          <v-select
            v-model="selectedSource"
            :items="availableSources"
            label="Source"
            clearable
            density="compact"
            hide-details
            @update:modelValue="fetchHistory"
          />
        </v-col>
        <v-col cols="12" sm="4">
          <v-select
            v-model="selectedCondition"
            :items="availableConditions"
            label="Condition"
            clearable
            density="compact"
            hide-details
            @update:modelValue="fetchHistory"
          />
        </v-col>
      </v-row>

      <!-- Price history line chart -->
      <v-card class="mb-6">
        <v-card-title class="text-subtitle-1 font-weight-bold pa-4">
          Price History
        </v-card-title>
        <v-card-text>
          <Line
            v-if="chartData"
            :data="chartData"
            :options="chartOptions"
            style="max-height: 360px"
          />
          <v-alert v-else type="info" variant="tonal" density="compact">
            No price history available for this card with the current filters.
          </v-alert>
        </v-card-text>
      </v-card>

      <!-- Snapshot data table -->
      <v-card>
        <v-card-title class="text-subtitle-1 font-weight-bold pa-4">
          Price Snapshots
        </v-card-title>
        <v-data-table
          :headers="snapshotHeaders"
          :items="snapshots"
          :loading="historyLoading"
          :items-per-page="25"
          :sort-by="[{ key: 'captured_at', order: 'desc' }]"
          density="compact"
        >
          <template #item.market_price="{ item }">
            <span :class="item.market_price == null ? 'text-medium-emphasis' : ''">
              {{ formatCurrency(item.market_price) }}
            </span>
          </template>
          <template #item.captured_date="{ item }">
            {{ formatDate(item.captured_date) }}
          </template>
        </v-data-table>
      </v-card>

    </template>

  </v-container>
</template>

<script setup>
/**
 * CardDetail view.
 *
 * Displays a single card's metadata, a filterable price history line chart,
 * and a full table of all price snapshots. Accessible via /cards/:cardId.
 *
 * The view fetches card metadata from GET /cards/{id} on mount, then fetches
 * price history from GET /cards/{id}/price-history. When the source or
 * condition filter dropdowns change, the price history is re-fetched with
 * the updated filters applied server-side.
 */

import {
  CategoryScale,
  Chart as ChartJS,
  Legend,
  LinearScale,
  LineElement,
  PointElement,
  Title,
  Tooltip,
} from "chart.js";
import { computed, inject, onMounted, onUnmounted, ref } from "vue";
import { Line } from "vue-chartjs";
import { useRoute } from "vue-router";
import { getCard, getPriceHistory } from "../api/index.js";
import { formatCurrency, formatDate } from "../utils/formatters.js";

// Register Chart.js components needed for a line chart.
ChartJS.register(Title, Tooltip, Legend, LineElement, PointElement, CategoryScale, LinearScale);

const route = useRoute();
const cardId = route.params.cardId;

const setCrumb = inject('setCrumb', () => {})
const clearCrumbs = inject('clearCrumbs', () => {})

// --- State ---
const card = ref(null);
const snapshots = ref([]);
const loading = ref(true);     // true while the initial card metadata is loading
const historyLoading = ref(false); // true while price history is loading
const error = ref(null);

// Filter state — bound to the dropdowns.
const selectedSource = ref(null);
const selectedCondition = ref(null);

// --- Derived filter options ---
// Build the source/condition dropdown options from whatever the API returns,
// rather than hardcoding them, so new sources/conditions appear automatically.

const availableSources = computed(() => {
  const sources = new Set(snapshots.value.map((s) => s.source));
  return Array.from(sources).sort();
});

const availableConditions = computed(() => {
  const conditions = new Set(snapshots.value.map((s) => s.condition));
  return Array.from(conditions).sort();
});

// --- Data fetching ---

async function fetchHistory() {
  historyLoading.value = true;
  try {
    const filters = {};
    if (selectedSource.value) filters.source = selectedSource.value;
    if (selectedCondition.value) filters.condition = selectedCondition.value;

    const result = await getPriceHistory(cardId, filters);
    snapshots.value = result.snapshots ?? [];
  } catch (e) {
    console.error("Failed to fetch price history:", e);
    // Don't overwrite the card-level error -- just leave the chart empty.
    snapshots.value = [];
  } finally {
    historyLoading.value = false;
  }
}

onMounted(async () => {
  try {
    const [cardData] = await Promise.all([
      getCard(cardId),
      fetchHistory(),
    ]);
    card.value = cardData;
    // Set breadcrumbs: Sets > {Set Name} (linked) > {Card Name} {num}/{total} (plain)
    const setId = cardData.set_id;
    const setName = cardData.set_display_name ?? setId;
    const cardLabel = `${cardData.name} ${cardData.number}/${cardData.set_printed_total ?? '?'}`;
    setCrumb(1, setName, `/sets/${setId}`);
    setCrumb(2, cardLabel, null);
  } catch (e) {
    error.value = `Failed to load card: ${e.message}`;
  } finally {
    loading.value = false;
  }
});

onUnmounted(() => {
  clearCrumbs();
});

// --- Chart ---

/**
 * Build the Chart.js line chart data from the snapshots array.
 * Returns null when there are no snapshots (shows the empty state message).
 */
const chartData = computed(() => {
  if (!snapshots.value.length) return null;

  // Sort oldest-first for the chart (the API already returns them this way,
  // but enforce it here in case filters changed the order).
  const sorted = [...snapshots.value].sort(
    (a, b) => new Date(a.captured_date) - new Date(b.captured_date)
  );

  return {
    labels: sorted.map((s) => s.captured_date),
    datasets: [
      {
        label: "Market Price (USD)",
        data: sorted.map((s) => s.market_price),
        borderColor: "rgba(99, 102, 241, 1)",
        backgroundColor: "rgba(99, 102, 241, 0.1)",
        borderWidth: 2,
        pointRadius: 3,
        tension: 0.3, // slight curve to make the line easier to read
        fill: true,
        spanGaps: true, // connect across null values (historical points may have gaps)
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
    x: {
      // Thin out the x-axis labels when there are many data points to avoid overlap.
      ticks: {
        maxTicksLimit: 12,
      },
    },
  },
};

// --- Snapshot table columns ---

const snapshotHeaders = [
  { title: "Date", key: "captured_date" },
  { title: "Source", key: "source" },
  { title: "Condition", key: "condition" },
  { title: "Market Price", key: "market_price", align: "end" },
];
</script>
