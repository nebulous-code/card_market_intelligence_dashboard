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

    <!-- Filter status row: "Showing N of M" note + Clear Filters button -->
    <div
      v-if="hasActiveFilters"
      class="d-flex align-center mb-3"
    >
      <div
        v-if="filteredCards.length !== cardsWithPrices.length"
        class="text-caption text-medium-emphasis"
      >
        Showing {{ filteredCards.length }} of {{ cardsWithPrices.length }} cards
      </div>
      <v-spacer />
      <v-btn
        variant="text"
        prepend-icon="mdi-filter-off"
        size="small"
        @click="clearFilters"
      >
        Clear Filters
      </v-btn>
    </div>

    <!-- Card table -->
    <CardTable
      :filters="filters"
      :cards="filteredCards"
      :available-rarities="availableRarities"
      :loading="loadingCards"
      @update:filters="onFiltersUpdate"
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
import { computed, inject, onMounted, onUnmounted, reactive, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import {
  getCardsForSet,
  getReferenceRarities,
  getSet,
  getSetCardPrices,
} from "../api/index.js";
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
const router = useRouter();
const setId = computed(() => route.params.setId);

const setCrumb = inject('setCrumb', () => {})
const clearCrumbs = inject('clearCrumbs', () => {})

const set = ref(null);
const cards = ref([]);
const pricesByCardId = ref({});
const loadingSet = ref(true);
const loadingCards = ref(true);

// Canonical rarity reference list (rarest-first by display_order). Drives the
// rarity dropdown options and the box-and-whisker column ordering. Fetched
// once on mount; the list is small and changes only on a migration.
const rarityRef = ref([]);

// --- Filter state ---
//
// Single reactive object covering every column-header filter. CardTable is the
// only place these are read/written from the user's side (via v-model:filters).
// The chart, table, and "Showing N of M" note all consume `filteredCards`.
//
// State is mirrored to the URL (so views are bookmarkable / shareable) and to
// sessionStorage keyed by setId (so filters survive a breadcrumb round-trip
// through a card detail page; URL is authoritative when both are present).
const EMPTY_FILTERS = () => ({
  name: "",
  supertype: [],
  rarity: [],
  minPrice: null,
  maxPrice: null,
});
const filters = reactive(EMPTY_FILTERS());

const STORAGE_KEY = (id) => `setDetail:filters:${id}`;

const hasActiveFilters = computed(
  () =>
    !!filters.name ||
    filters.supertype.length > 0 ||
    filters.rarity.length > 0 ||
    filters.minPrice !== null ||
    filters.maxPrice !== null
);

/**
 * Build the URL-query object from the current filter state. Empty values are
 * omitted so the URL stays clean. Multi-selects join with commas; numbers are
 * stringified so router.replace receives a uniform string-only object.
 */
function buildQuery(f) {
  const q = {};
  if (f.name) q.name = f.name;
  if (f.supertype?.length) q.supertype = f.supertype.join(",");
  if (f.rarity?.length) q.rarity = f.rarity.join(",");
  if (f.minPrice !== null && f.minPrice !== "") q.minPrice = String(f.minPrice);
  if (f.maxPrice !== null && f.maxPrice !== "") q.maxPrice = String(f.maxPrice);
  return q;
}

/**
 * Mutate the `filters` reactive object in-place from a query-shaped source
 * (route.query or a sessionStorage stash). Unknown keys are ignored; missing
 * keys revert to their empty-state values so partial query strings work too.
 */
function applyFromQuery(src) {
  filters.name = typeof src.name === "string" ? src.name : "";
  filters.supertype = src.supertype ? String(src.supertype).split(",").filter(Boolean) : [];
  filters.rarity = src.rarity ? String(src.rarity).split(",").filter(Boolean) : [];
  filters.minPrice = src.minPrice != null && src.minPrice !== "" ? Number(src.minPrice) : null;
  filters.maxPrice = src.maxPrice != null && src.maxPrice !== "" ? Number(src.maxPrice) : null;
}

function clearFilters() {
  Object.assign(filters, EMPTY_FILTERS());
  // The deep watcher will clear the URL and sessionStorage automatically.
}

/**
 * Apply a filter-shape update from CardTable. Mutates the existing reactive
 * object in-place rather than replacing it; the deep watcher then writes the
 * URL and sessionStorage. Using Object.assign preserves the reactive proxy
 * identity (a plain `filters = newVal` would break the watcher).
 */
function onFiltersUpdate(newFilters) {
  Object.assign(filters, newFilters);
}

/**
 * Merge each card with its NM market price (with legacy condition fallbacks).
 * This used to live inside CardTable but is lifted here so the chart, the
 * price-range filter, and the table all see the same shape.
 */
const cardsWithPrices = computed(() =>
  cards.value.map((card) => {
    const prices = pricesByCardId.value[card.id] ?? [];
    const snap =
      prices.find((p) => p.condition === "NM") ??
      prices.find((p) => p.condition === "normal") ??
      prices.find((p) => p.condition === "holofoil") ??
      null;
    return {
      ...card,
      market_price: snap?.market_price != null ? Number(snap.market_price) : null,
    };
  })
);

/**
 * Distinct rarities present in the unfiltered list, returned as
 * [{value, title}] objects rarest-first. The `value` is the canonical key
 * stored on cards.rarity (e.g. "common") and the `title` is the display
 * label from canonical_rarities ("Common"). Computed from `cardsWithPrices`
 * (not `filteredCards`) so the option list stays stable as filters narrow
 * the table.
 */
const availableRarities = computed(() => {
  const presentValues = new Set(
    cardsWithPrices.value.map((c) => c.rarity).filter(Boolean)
  );
  return rarityRef.value
    .filter((r) => presentValues.has(r.value))
    .map((r) => ({ value: r.value, title: r.label }));
});

/** Lookup tables built from the reference list. */
const rarityLabelByValue = computed(() => {
  const m = {};
  for (const r of rarityRef.value) m[r.value] = r.label;
  return m;
});
const rarityOrderByValue = computed(() => {
  const m = {};
  for (const r of rarityRef.value) m[r.value] = r.display_order;
  return m;
});

/**
 * Apply the active filters to the merged-with-prices list. AND across filter
 * keys, OR within each multi-select. Null prices are excluded only when a
 * price bound is explicitly set.
 */
const filteredCards = computed(() => {
  return cardsWithPrices.value.filter((card) => {
    if (filters.name) {
      const needle = filters.name.toLowerCase();
      if (!card.name?.toLowerCase().includes(needle)) return false;
    }
    if (filters.supertype.length > 0 && !filters.supertype.includes(card.supertype)) {
      return false;
    }
    if (filters.rarity.length > 0 && !filters.rarity.includes(card.rarity)) {
      return false;
    }
    if (filters.minPrice !== null || filters.maxPrice !== null) {
      if (card.market_price == null) return false;
      if (filters.minPrice !== null && card.market_price < filters.minPrice) return false;
      if (filters.maxPrice !== null && card.market_price > filters.maxPrice) return false;
    }
    return true;
  });
});

const chartData = computed(() => {
  if (!filteredCards.value.length) return null;

  // Group market prices by canonical rarity value, sourced from the filtered
  // list so the chart visually agrees with the table. Cards with no rarity
  // get a synthetic "unknown" bucket sorted to the far right.
  const groups = {};
  for (const card of filteredCards.value) {
    const rarity = card.rarity ?? "__unknown__";
    if (card.market_price == null) continue;
    if (!groups[rarity]) groups[rarity] = [];
    groups[rarity].push(card.market_price);
  }

  if (Object.keys(groups).length === 0) return null;

  // Sort by canonical display_order ascending so the rarest column is on the
  // left. Anything not in rarityRef (e.g. the unknown bucket) sorts after
  // everything in the reference list.
  const orderMap = rarityOrderByValue.value;
  const FALLBACK = Number.POSITIVE_INFINITY;
  const sortedValues = Object.keys(groups).sort((a, b) => {
    const ai = orderMap[a] ?? FALLBACK;
    const bi = orderMap[b] ?? FALLBACK;
    if (ai !== bi) return ai - bi;
    return a.localeCompare(b);
  });

  // Render display labels along the X axis but keep the canonical value as
  // the lookup key for the data array.
  const labelMap = rarityLabelByValue.value;
  const labels = sortedValues.map((v) => labelMap[v] ?? v);

  return {
    labels,
    datasets: [
      {
        label: "Market Price",
        data: sortedValues.map((r) => groups[r]),
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
          // chartjs-chart-boxplot puts computed stats on ctx.parsed; ctx.raw is the input array
          const { min, q1, median, q3, max } = ctx.parsed ?? {};
          const count = Array.isArray(ctx.raw) ? ctx.raw.length : "?";
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
      min: 0.1,
      title: { display: true, text: "Market Price (USD)" },
      ticks: {
        callback: (val) => formatCompactCurrency(val),
        padding: 10,
      },
      grid: {
        drawTicks: true,
        tickLength: 8,
      },
      // Force ticks at every power-of-10 and the midpoint (5×) between each decade.
      // Chart.js log scale auto-ticks are unpredictable, so we replace them entirely.
      afterBuildTicks(scale) {
        const TICK_SEQUENCE = [
          0.1, 0.5, 1, 5, 10, 50, 100, 500, 1_000, 5_000, 10_000, 50_000, 100_000,
        ];
        scale.ticks = TICK_SEQUENCE
          .filter((v) => v <= (scale.max ?? Infinity) * 1.5)
          .map((v) => ({ value: v }));
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

/**
 * Initialize filter state for the current setId. URL query is authoritative;
 * if the URL has no filter params, fall back to whatever was last stashed in
 * sessionStorage so a breadcrumb round-trip from a card detail page doesn't
 * lose the user's filters.
 */
function initFiltersForCurrentSet() {
  const q = route.query;
  const urlHasFilters =
    !!(q.name || q.supertype || q.rarity || q.minPrice || q.maxPrice);
  if (urlHasFilters) {
    applyFromQuery(q);
    return;
  }
  const stashed = sessionStorage.getItem(STORAGE_KEY(setId.value));
  if (stashed) {
    try {
      applyFromQuery(JSON.parse(stashed));
      // Reflect restored filters in the URL so it stays the canonical source.
      router.replace({ query: buildQuery(filters) });
    } catch {
      // Corrupt stash — ignore and fall through to empty state.
    }
  }
}

async function loadRarityReference() {
  try {
    rarityRef.value = await getReferenceRarities();
  } catch {
    // Reference fetch failure is non-fatal — the dropdown just shows
    // canonical values without nice labels until the next refresh.
    rarityRef.value = [];
  }
}

onMounted(() => {
  initFiltersForCurrentSet();
  loadRarityReference();
  loadSet();
  loadCards();
});

onUnmounted(() => {
  clearCrumbs();
});

watch(setId, (newId, oldId) => {
  clearCrumbs();
  // Filters are scoped to a set: changing sets resets the active state and
  // re-initializes from the new URL/storage rather than carrying old values.
  Object.assign(filters, EMPTY_FILTERS());
  initFiltersForCurrentSet();
  loadSet();
  loadCards();
});

/**
 * Mirror filter changes into the URL (replace, not push, so each keystroke
 * does not flood the browser history) and into sessionStorage. The watcher
 * fires after `clearFilters()` too, which is how we wipe both stores.
 */
watch(
  filters,
  (newFilters) => {
    const query = buildQuery(newFilters);
    router.replace({ query });
    if (Object.keys(query).length === 0) {
      sessionStorage.removeItem(STORAGE_KEY(setId.value));
    } else {
      sessionStorage.setItem(STORAGE_KEY(setId.value), JSON.stringify(query));
    }
  },
  { deep: true }
);
</script>
