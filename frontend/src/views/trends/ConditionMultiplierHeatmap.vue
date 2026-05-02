<template>
  <div>
    <div class="text-h4 font-weight-bold mb-2">Condition Multipliers</div>
    <div class="text-body-2 text-medium-emphasis mb-6">
      Price ratios from real listings, not fixed industry multipliers.
      Each cell shows the cumulative multiplier from Near Mint -- hover
      for the alternate paths (e.g. the LP-based ratio). Calculated from
      the last 6 months of TCGplayer pricing on raw (non-variant) cards.
    </div>

    <!-- Slicers -->
    <div v-if="!loadingSets" class="mb-6">
      <div class="text-caption text-medium-emphasis mb-1">Set</div>
      <v-chip-group
        v-model="selectedSetId"
        mandatory
        column
      >
        <v-chip
          v-for="s in availableSets"
          :key="s.set_id"
          :value="s.set_id"
          size="small"
          variant="outlined"
          filter
        >
          {{ s.set_display_name }}
        </v-chip>
      </v-chip-group>

      <div class="text-caption text-medium-emphasis mt-3 mb-1">Group by</div>
      <v-chip-group
        v-model="groupingType"
        mandatory
      >
        <v-chip value="rarity"    size="small" variant="outlined" filter>Rarity</v-chip>
        <v-chip value="supertype" size="small" variant="outlined" filter>Supertype</v-chip>
      </v-chip-group>
    </div>

    <v-skeleton-loader v-if="loadingSets" type="chip" />

    <!-- Heatmap or empty state -->
    <v-card v-if="!loadingSets" class="mb-6">
      <v-card-text>
        <v-skeleton-loader
          v-if="loadingMultipliers"
          type="image"
          height="240"
        />

        <EmptyState
          v-else-if="cascadeRows.length === 0"
          icon="mdi-chart-box-outline"
          title="Not enough price data yet"
          message="Condition multipliers require at least 30 days of historical pricing. This set will populate once enough data has been collected."
        />

        <div v-else class="heatmap" role="grid" aria-label="Condition multipliers heatmap">
          <!-- Header row -->
          <div class="heatmap__cell heatmap__cell--header"></div>
          <div
            v-for="col in CONDITION_COLUMNS"
            :key="col"
            class="heatmap__cell heatmap__cell--header"
          >
            {{ col }}
          </div>

          <!-- Data rows -->
          <template v-for="row in cascadeRows" :key="row.groupingValue">
            <div class="heatmap__cell heatmap__cell--row-label">
              {{ row.groupingLabel }}
            </div>
            <v-tooltip
              v-for="cell in row.cells"
              :key="`${row.groupingValue}-${cell.condition}`"
              location="top"
              open-delay="100"
              content-class="chartjs-tooltip"
            >
              <template #activator="{ props }">
                <!-- Activator is the entire cell so hover/keyboard focus
                     anywhere on the colored square triggers the tooltip,
                     not just the number text. -->
                <div
                  v-bind="props"
                  class="heatmap__cell heatmap__cell--data"
                  :class="{ 'heatmap__cell--anchor': cell.condition === 'NM' }"
                  :style="{ backgroundColor: cellColor(cell) }"
                >
                  <span
                    class="heatmap__value"
                    :class="{ 'heatmap__value--missing': cell.multiplier == null }"
                  >
                    {{ cell.multiplier == null ? "—" : formatMultiplier(cell.multiplier) }}
                  </span>
                </div>
              </template>
              <!-- Tooltip body. Lines kept terse to match the Chart.js
                   tooltip on the box plot (compact, no extra dividers). -->
              <div class="chartjs-tooltip__title">
                {{ row.groupingLabel }} — {{ cell.condition === "NM" ? "NM (reference)" : `NM → ${cell.condition}` }}
              </div>
              <div v-if="cell.condition === 'NM'" class="chartjs-tooltip__line">
                Anchored at 1.00.
              </div>
              <div v-else-if="cell.multiplier != null" class="chartjs-tooltip__line">
                From NM: {{ formatMultiplier(cell.multiplier) }}
                <span v-if="cell.dataPoints != null">
                  ({{ cell.dataPoints }} pts)
                </span>
              </div>
              <div v-else class="chartjs-tooltip__line">
                No data for this transition.
              </div>
              <div
                v-for="alt in alternatePaths(cell)"
                :key="alt.fromCondition"
                class="chartjs-tooltip__line"
              >
                From {{ alt.fromCondition }}: {{ formatMultiplier(alt.multiplier) }}
                ({{ alt.dataPoints }} pts)
              </div>
            </v-tooltip>
          </template>
        </div>
      </v-card-text>
    </v-card>

    <!-- Summary cards -->
    <v-row v-if="!loadingSets && !loadingMultipliers && cascadeRows.length > 0">
      <v-col cols="12" sm="6" md="3">
        <v-card height="100%">
          <v-card-text>
            <div class="text-caption text-medium-emphasis">Avg LP / NM ratio</div>
            <div class="text-h5 font-weight-bold">
              {{ summary.avgLpRatio != null ? formatMultiplier(summary.avgLpRatio) : "—" }}
            </div>
          </v-card-text>
        </v-card>
      </v-col>
      <v-col cols="12" sm="6" md="3">
        <v-card height="100%">
          <v-card-text>
            <div class="text-caption text-medium-emphasis">Avg MP / NM ratio</div>
            <div class="text-h5 font-weight-bold">
              {{ summary.avgMpRatio != null ? formatMultiplier(summary.avgMpRatio) : "—" }}
            </div>
          </v-card-text>
        </v-card>
      </v-col>
      <v-col cols="12" sm="6" md="3">
        <v-card height="100%">
          <v-card-text>
            <div class="text-caption text-medium-emphasis">Steepest drop (NM → LP)</div>
            <div v-if="summary.steepestDrop" class="text-h6 font-weight-bold">
              {{ summary.steepestDrop.groupingLabel }}
            </div>
            <div v-if="summary.steepestDrop" class="text-body-2 text-medium-emphasis">
              {{ formatMultiplier(summary.steepestDrop.multiplier) }}
            </div>
            <div v-else class="text-h5 font-weight-bold">—</div>
          </v-card-text>
        </v-card>
      </v-col>
      <v-col cols="12" sm="6" md="3">
        <v-card height="100%">
          <v-card-text>
            <div class="text-caption text-medium-emphasis">Total data points</div>
            <div class="text-h5 font-weight-bold">
              {{ formatNumber(summary.totalDataPoints) }}
            </div>
          </v-card-text>
        </v-card>
      </v-col>
    </v-row>

    <div
      v-if="lastRefreshedDisplay"
      class="text-caption text-medium-emphasis mt-4 text-right"
    >
      Last refreshed {{ lastRefreshedDisplay }}
    </div>
  </div>
</template>

<script setup>
/**
 * ConditionMultiplierHeatmap view.
 *
 * Displays the cumulative NM->X multiplier for every (rarity OR supertype)
 * grouping in a set as a color-graded grid. Uses two simple slicers:
 * a single-select set chip group and a Rarity/Supertype toggle. The four
 * summary cards below the grid are computed from the same cascade rows
 * shown above.
 *
 * Data pipeline:
 *   /trends/sets-with-multipliers     -> available set chips
 *   /trends/condition-multipliers     -> grouping rows + transition data
 *   buildCascadeRow / summarizeCascade (utils/heatmap.js) -> view shape
 *   colorForMultiplier (utils/heatmapColors.js)           -> cell color
 */

import { computed, onMounted, ref, watch } from "vue";
import EmptyState from "../../components/EmptyState.vue";
import {
  getConditionMultipliers,
  getSetsWithMultipliers,
} from "../../api/index.js";
import {
  CONDITION_COLUMNS,
  buildCascadeRow,
  summarizeCascade,
} from "../../utils/heatmap.js";
import { colorForMultiplier, MUTED_BACKGROUND } from "../../utils/heatmapColors.js";
import { formatNumber } from "../../utils/formatters.js";

const availableSets = ref([]);
const loadingSets = ref(true);

const selectedSetId = ref(null);
const groupingType = ref("rarity");

const multiplierData = ref(null);
const loadingMultipliers = ref(false);

async function loadAvailableSets() {
  loadingSets.value = true;
  try {
    const response = await getSetsWithMultipliers();
    availableSets.value = response.sets;
    if (availableSets.value.length > 0 && selectedSetId.value == null) {
      selectedSetId.value = availableSets.value[0].set_id;
    }
  } finally {
    loadingSets.value = false;
  }
}

async function loadMultipliers() {
  if (!selectedSetId.value) return;
  loadingMultipliers.value = true;
  try {
    multiplierData.value = await getConditionMultipliers(
      selectedSetId.value,
      groupingType.value,
    );
  } catch {
    // Failure leaves multiplierData null; the empty-state path handles it.
    multiplierData.value = null;
  } finally {
    loadingMultipliers.value = false;
  }
}

const cascadeRows = computed(() => {
  if (!multiplierData.value) return [];
  return multiplierData.value.groupings.map(buildCascadeRow);
});

const summary = computed(() => summarizeCascade(cascadeRows.value));

const lastRefreshedDisplay = computed(() => {
  const ts = multiplierData.value?.last_refreshed;
  if (!ts) return null;
  return new Date(ts).toLocaleString();
});

function cellColor(cell) {
  if (cell.condition === "NM") return MUTED_BACKGROUND;
  return colorForMultiplier(cell.multiplier);
}

function formatMultiplier(value) {
  return value == null ? "—" : value.toFixed(2);
}

function alternatePaths(cell) {
  // The "from NM" entry is already shown in the main tooltip body; the
  // tooltip's secondary list is everything ELSE that lands at this column.
  return cell.incomingTransitions.filter((t) => t.fromCondition !== "NM");
}

watch([selectedSetId, groupingType], loadMultipliers);

onMounted(loadAvailableSets);
</script>

<style scoped>
.heatmap {
  display: grid;
  grid-template-columns: minmax(140px, max-content) repeat(5, 1fr);
  gap: 4px;
}

.heatmap__cell {
  padding: 12px 8px;
  text-align: center;
  border-radius: 4px;
  min-height: 48px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.heatmap__cell--header {
  font-weight: 600;
  color: rgba(255, 255, 255, 0.7);
  text-transform: uppercase;
  letter-spacing: 0.04em;
  font-size: 12px;
  background: transparent;
}

.heatmap__cell--row-label {
  justify-content: flex-start;
  text-align: left;
  padding-left: 0;
  font-weight: 500;
}

.heatmap__cell--data {
  font-variant-numeric: tabular-nums;
  font-weight: 600;
}

.heatmap__cell--anchor {
  border: 1px dashed rgba(255, 255, 255, 0.2);
  font-weight: 400;
  color: rgba(255, 255, 255, 0.6);
}

.heatmap__value {
  cursor: default;
}

.heatmap__value--missing {
  color: rgba(255, 255, 255, 0.3);
}
</style>

<!--
  Tooltip styling lives in an unscoped block because Vuetify teleports
  v-tooltip content out of this component's DOM tree, so scoped selectors
  don't reach it. The look matches the Chart.js default tooltip on the
  box-and-whiskers plot: solid dark background, white sans-serif body,
  small corner radius, tight padding, no border.
-->
<style>
.chartjs-tooltip.v-overlay__content {
  background: rgba(0, 0, 0, 0.85);
  color: #fff;
  border-radius: 4px;
  padding: 8px 10px;
  font-size: 12px;
  line-height: 1.45;
  max-width: 280px;
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.3);
}

.chartjs-tooltip__title {
  font-weight: 700;
  margin-bottom: 4px;
}

.chartjs-tooltip__line {
  font-weight: 400;
}
</style>
