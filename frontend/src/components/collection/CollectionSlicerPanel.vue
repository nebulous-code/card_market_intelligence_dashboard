<template>
  <v-navigation-drawer
    location="right"
    permanent
    :rail="collapsed"
    :rail-width="64"
    :width="320"
    color="surface"
  >
    <!-- Top: chevron toggle -->
    <div class="slicer-top d-flex align-center px-2 py-2">
      <v-spacer v-if="!collapsed" />
      <v-btn
        :icon="collapsed ? 'mdi-chevron-left' : 'mdi-chevron-right'"
        variant="text"
        size="small"
        :title="collapsed ? 'Expand filters' : 'Collapse filters'"
        @click="emit('update:collapsed', !collapsed)"
      />
      <div v-if="!collapsed" class="text-subtitle-1 font-weight-bold mr-2">
        Filters
      </div>
    </div>

    <v-divider />

    <!-- Expanded body: stacked slicer regions -->
    <div v-if="!collapsed" class="slicer-body d-flex flex-column">
      <CollectionSlicerRegion
        title="Sets"
        icon="mdi-cards"
        :values="values.sets"
        :filter-set="filterState.sets"
        @toggle="onToggle('sets', $event)"
      />
      <CollectionSlicerRegion
        title="Rarity"
        icon="mdi-diamond-stone"
        :values="values.rarities"
        :filter-set="filterState.rarities"
        @toggle="onToggle('rarities', $event)"
      />
      <CollectionSlicerRegion
        title="Condition"
        icon="mdi-shield-outline"
        :values="values.conditions"
        :filter-set="filterState.conditions"
        @toggle="onToggle('conditions', $event)"
      />
      <CollectionSlicerRegion
        v-if="!hideVariant"
        title="Variant"
        icon="mdi-shimmer"
        :values="values.variants"
        :filter-set="filterState.variants"
        @toggle="onToggle('variants', $event)"
      />
      <div class="slicer-clear pa-3">
        <v-btn
          v-if="anyActive"
          variant="text"
          size="small"
          block
          color="primary"
          @click="onClearAll"
        >
          Clear All Filters
        </v-btn>
      </div>
    </div>

    <!-- Collapsed body: one icon row per slicer + clear icon at bottom -->
    <div v-else class="slicer-rail d-flex flex-column align-center">
      <SlicerRailIcon
        icon="mdi-cards"
        :count="filterState.sets.size"
        title="Sets"
      />
      <SlicerRailIcon
        icon="mdi-diamond-stone"
        :count="filterState.rarities.size"
        title="Rarity"
      />
      <SlicerRailIcon
        icon="mdi-shield-outline"
        :count="filterState.conditions.size"
        title="Condition"
      />
      <SlicerRailIcon
        v-if="!hideVariant"
        icon="mdi-shimmer"
        :count="filterState.variants.size"
        title="Variant"
      />
      <v-spacer />
      <v-btn
        v-if="anyActive"
        icon="mdi-filter-off"
        variant="text"
        size="small"
        title="Clear All Filters"
        class="my-2"
        @click="onClearAll"
      />
    </div>
  </v-navigation-drawer>
</template>

<script setup>
/**
 * Right-side slicer panel for the Collection Dashboard.
 *
 * Reads the unfiltered cards list (so chip universes don't shrink as
 * filters apply) and a reactive ``filterState``. Toggling a chip
 * routes through :func:`toggleChipSelection` and writes the new Set
 * back into the dimension. The collapse state is owned by the parent
 * via ``v-model:collapsed`` so it can be persisted to the URL.
 */

import { computed, h } from 'vue'
import {
  clearAllFilters,
  collectSlicerValues,
  hasAnyActiveFilter,
  shouldHideVariantSlicer,
  toggleChipSelection,
} from '../../utils/slicerState.js'
import CollectionSlicerRegion from './CollectionSlicerRegion.vue'

const props = defineProps({
  cards: { type: Array, required: true },
  filterState: { type: Object, required: true },
  collapsed: { type: Boolean, default: false },
})
const emit = defineEmits(['update:collapsed', 'update:filter-state'])

const values = computed(() => collectSlicerValues(props.cards))
const hideVariant = computed(() => shouldHideVariantSlicer(values.value.variants))
const anyActive = computed(() => hasAnyActiveFilter(props.filterState))

function onToggle(dimension, value) {
  const universe = values.value[dimension].map((entry) => entry.value)
  const next = toggleChipSelection(props.filterState[dimension], value, universe)
  // Reactive Set replacement: writing to the property triggers Vue's
  // reactivity even though the inner Set is mutated. The dashboard's
  // watcher mirrors the change to URL params.
  props.filterState[dimension] = next
  emit('update:filter-state', props.filterState)
}

function onClearAll() {
  clearAllFilters(props.filterState)
  emit('update:filter-state', props.filterState)
}

// Tiny inline component for the rail icons. Defining it here keeps
// the rail layout legible without spawning a third file for what
// amounts to 15 lines of template.
const SlicerRailIcon = {
  props: { icon: String, count: Number, title: String },
  setup(p) {
    return () =>
      h(
        'div',
        { class: 'slicer-rail-icon', title: p.title },
        [
          h('v-icon', {
            color: p.count > 0 ? '#F5C842' : undefined,
            size: 24,
          }, () => p.icon),
          p.count > 0
            ? h(
                'v-chip',
                {
                  size: 'x-small',
                  color: '#F5C842',
                  variant: 'flat',
                  class: 'mt-1 font-weight-bold',
                },
                () => String(p.count),
              )
            : null,
        ],
      )
  },
}
</script>

<style scoped>
.slicer-top {
  min-height: 48px;
}
.slicer-body {
  height: calc(100% - 56px);
  overflow: hidden;
}
.slicer-clear {
  border-top: 1px solid rgba(255, 255, 255, 0.05);
}
.slicer-rail {
  height: calc(100% - 56px);
  padding-top: 12px;
}
.slicer-rail-icon {
  width: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 12px 0;
  border-bottom: 1px solid rgba(255, 255, 255, 0.05);
}
.slicer-rail-icon:last-of-type {
  border-bottom: none;
}
</style>
