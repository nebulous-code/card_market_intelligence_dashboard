<template>
  <v-card>
    <v-card-title class="text-subtitle-1 font-weight-bold pa-4">
      Cards
      <v-spacer />
    </v-card-title>

    <!--
      Vuetify data table. Sorting and pagination are handled natively. Filters
      are rendered in column-header slots so the controls live in the same row
      as the column label, matching the Excel pattern. Filtering itself is done
      by the parent (SetDetailView) so the chart can subscribe to the same
      filtered list — this component only edits filter state via v-model.
    -->
    <v-data-table
      :headers="headers"
      :items="cards"
      :loading="loading"
      :items-per-page="25"
      :sort-by="[{ key: 'number', order: 'asc' }]"
      density="compact"
      hover
    >
      <!-- Name column header: label/sort + text-field filter -->
      <template #header.name="{ column, getSortIcon, toggleSort }">
        <div class="d-flex flex-column py-1" style="min-width: 180px;">
          <div
            class="d-flex align-center cursor-pointer"
            @click="toggleSort(column)"
          >
            <span>{{ column.title }}</span>
            <v-icon size="small" :icon="getSortIcon(column)" />
          </div>
          <v-text-field
            :model-value="filters.name"
            density="compact"
            placeholder="Search..."
            clearable
            hide-details
            prepend-inner-icon="mdi-magnify"
            @update:model-value="updateFilter('name', $event ?? '')"
            @click.stop
          />
        </div>
      </template>

      <!-- Supertype column header: label/sort + multi-select -->
      <template #header.supertype="{ column, getSortIcon, toggleSort }">
        <div class="d-flex flex-column py-1" style="min-width: 160px;">
          <div
            class="d-flex align-center cursor-pointer"
            @click="toggleSort(column)"
          >
            <span>{{ column.title }}</span>
            <v-icon size="small" :icon="getSortIcon(column)" />
          </div>
          <v-select
            :model-value="filters.supertype"
            :items="SUPERTYPE_OPTIONS"
            multiple
            chips
            density="compact"
            clearable
            hide-details
            placeholder="All"
            @update:model-value="updateFilter('supertype', $event ?? [])"
            @click.stop
          />
        </div>
      </template>

      <!-- Rarity column header: label/sort + multi-select (dynamic items) -->
      <template #header.rarity="{ column, getSortIcon, toggleSort }">
        <div class="d-flex flex-column py-1" style="min-width: 180px;">
          <div
            class="d-flex align-center cursor-pointer"
            @click="toggleSort(column)"
          >
            <span>{{ column.title }}</span>
            <v-icon size="small" :icon="getSortIcon(column)" />
          </div>
          <v-select
            :model-value="filters.rarity"
            :items="availableRarities"
            multiple
            chips
            density="compact"
            clearable
            hide-details
            placeholder="All"
            @update:model-value="updateFilter('rarity', $event ?? [])"
            @click.stop
          />
        </div>
      </template>

      <!-- Market Price column header: label/sort + min/max range inputs -->
      <template #header.market_price="{ column, getSortIcon, toggleSort }">
        <div class="d-flex flex-column align-end py-1" style="min-width: 180px;">
          <div
            class="d-flex align-center cursor-pointer"
            @click="toggleSort(column)"
          >
            <span>{{ column.title }}</span>
            <v-icon size="small" :icon="getSortIcon(column)" />
          </div>
          <div class="text-caption text-medium-emphasis mt-1">Price Range</div>
          <div class="d-flex" style="gap: 4px;" @click.stop>
            <v-text-field
              :model-value="filters.minPrice"
              type="number"
              density="compact"
              placeholder="Min $"
              hide-details
              style="max-width: 86px;"
              @update:model-value="updateFilter('minPrice', toNumberOrNull($event))"
            />
            <v-text-field
              :model-value="filters.maxPrice"
              type="number"
              density="compact"
              placeholder="Max $"
              hide-details
              style="max-width: 86px;"
              @update:model-value="updateFilter('maxPrice', toNumberOrNull($event))"
            />
          </div>
        </div>
      </template>

      <!-- Custom rendering for the image column: show the card image thumbnail. -->
      <template #item.image_url="{ item }">
        <v-img
          v-if="item.image_url"
          :src="item.image_url"
          width="36"
          height="50"
          contain
          class="my-1"
        />
      </template>

      <!-- Render the human-readable rarity label rather than the canonical
           snake_case value stored on the row. The dropdown filter still
           operates on the canonical key. -->
      <template #item.rarity="{ item }">
        {{ item.rarity_label ?? item.rarity ?? "" }}
      </template>

      <!-- Custom rendering for the price column: format as a dollar amount. -->
      <template #item.market_price="{ item }">
        <span :class="item.market_price == null ? 'text-medium-emphasis' : ''">
          {{ formatCurrency(item.market_price) }}
        </span>
      </template>

      <!-- Details button navigates to the card detail page. -->
      <template #item.actions="{ item }">
        <v-btn
          :to="`/cards/${item.id}`"
          size="small"
          variant="tonal"
          color="primary"
        >
          Details
        </v-btn>
      </template>

    </v-data-table>
  </v-card>
</template>

<script setup>
/**
 * CardTable component.
 *
 * Presentational table for the Set Detail page. Rendering only — the parent
 * (SetDetailView) merges price data into each card and applies filters before
 * passing the rows in via the `cards` prop. The chart on the same page reads
 * the same filtered list, so filter logic must live in the parent.
 *
 * Filter state is shared via v-model:filters. The four column-header slots
 * render the filter inputs that bind back to that state. AvailableRarities is
 * passed in (computed by the parent from the unfiltered list) so the rarity
 * dropdown options stay stable while other filters narrow the visible rows.
 *
 * Props:
 *   cards             - Array of merged card+price objects to render.
 *   filters           - Current filter state (v-model:filters from the parent).
 *   availableRarities - Sorted distinct rarities present in the full set.
 *   loading           - When true, the table shows a loading indicator.
 */

import { formatCurrency } from "../utils/formatters.js";

const props = defineProps({
  cards: {
    type: Array,
    default: () => [],
  },
  filters: {
    type: Object,
    required: true,
  },
  availableRarities: {
    type: Array,
    default: () => [],
  },
  loading: {
    type: Boolean,
    default: false,
  },
});

const emit = defineEmits(["update:filters"]);

// Hardcoded supertype options. Values match the cards.supertype column
// (no accent on "Pokemon") so substring/equality filtering works directly.
const SUPERTYPE_OPTIONS = ["Pokemon", "Trainer", "Energy"];

/**
 * Emit a single-key change to the parent's filter object. Vuetify's
 * v-text-field / v-select emit `null` when cleared; coerce to the empty-state
 * value the parent expects so its watcher serializes a clean URL query.
 */
function updateFilter(key, value) {
  emit("update:filters", { ...props.filters, [key]: value });
}

/**
 * Coerce a v-text-field number input into either a number or null.
 * `type="number"` still emits a string; an empty input emits "".
 */
function toNumberOrNull(value) {
  if (value === "" || value == null) return null;
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}

const headers = [
  { title: "", key: "image_url", sortable: false, width: "56px" },
  { title: "#", key: "number", width: "72px" },
  { title: "Name", key: "name" },
  { title: "Supertype", key: "supertype" },
  { title: "Rarity", key: "rarity" },
  { title: "Market Price", key: "market_price", align: "end" },
  { title: "", key: "actions", sortable: false, align: "end", width: "100px" },
];
</script>

<style scoped>
.cursor-pointer {
  cursor: pointer;
  user-select: none;
}
</style>
