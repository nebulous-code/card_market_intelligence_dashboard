<template>
  <v-card class="mb-6">
    <v-card-title class="d-flex align-center pa-4">
      <v-icon class="mr-2" style="cursor: pointer;" @click="toggleCollapsed">
        {{ collapsed ? 'mdi-chevron-right' : 'mdi-chevron-down' }}
      </v-icon>
      <div
        class="text-h6 font-weight-bold"
        style="cursor: pointer;"
        @click="toggleCollapsed"
      >
        Sets Ranked by Value
      </div>
      <v-spacer />
      <v-btn
        v-if="hasSetFilter"
        variant="text"
        size="small"
        prepend-icon="mdi-filter-off"
        class="mr-2"
        @click="emit('clear-set-filter')"
      >
        Clear Filter
      </v-btn>
      <v-btn
        variant="text"
        size="small"
        color="error"
        prepend-icon="mdi-restart"
        @click="emit('reset-collection')"
      >
        Reset Collection
      </v-btn>
    </v-card-title>
    <v-data-table
      v-if="!collapsed"
      :headers="headers"
      :items="rows"
      :items-per-page="-1"
      density="compact"
      hover
      @click:row="onRowClick"
    >
      <template #item.rank="{ index }">{{ index + 1 }}</template>
      <template #item.completion="{ item }">
        <div class="d-flex align-center">
          <v-progress-linear
            :model-value="completionPercent(item)"
            :color="completionColor(item)"
            height="8"
            rounded
            style="min-width: 100px;"
          />
          <span class="ml-2 text-caption text-medium-emphasis">
            {{ item.owned_count }} / {{ item.total_count }}
          </span>
        </div>
      </template>
      <template #item.total_value="{ item }">
        {{ formatCurrency(item.total_value) }}
      </template>
      <template #item.percent_of_collection="{ item }">
        {{ (item.percent_of_collection * 100).toFixed(1) }}%
      </template>
    </v-data-table>
  </v-card>
</template>

<script setup>
/**
 * Sets ranked by total value. Click a row to apply that set as a
 * filter; the dashboard pushes it into ``filterState.sets`` and every
 * other widget refreshes.
 *
 * The completion progress bar uses ``total_count`` as the denominator
 * (which already includes secret rares -- see the
 * ``total_count`` rollout in M03_S07). When the user owns every card
 * the bar flips to Magikarp gold to celebrate the 100%.
 */

import { computed } from 'vue'
import { aggregateBySet } from '../../utils/collectionStats.js'
import { formatCurrency } from '../../utils/formatters.js'

const props = defineProps({
  cards: { type: Array, required: true },
  collapsed: { type: Boolean, default: false },
  hasSetFilter: { type: Boolean, default: false },
})
const emit = defineEmits([
  'update:collapsed',
  'select-set',
  'clear-set-filter',
  'reset-collection',
])

const collapsed = computed(() => props.collapsed)

function toggleCollapsed() {
  emit('update:collapsed', !collapsed.value)
}

const rows = computed(() => aggregateBySet(props.cards))

const headers = [
  { title: '#', key: 'rank', sortable: false, width: 48 },
  { title: 'Set', key: 'set_name' },
  { title: 'Cards', key: 'owned_count', align: 'end' },
  { title: 'Set Total', key: 'total_count', align: 'end' },
  { title: 'Completion', key: 'completion', sortable: false },
  { title: 'Value', key: 'total_value', align: 'end' },
  { title: '%', key: 'percent_of_collection', align: 'end' },
]

function completionPercent(row) {
  if (!row.total_count || row.total_count === 0) return 0
  return Math.min(100, (row.owned_count / row.total_count) * 100)
}

function completionColor(row) {
  return completionPercent(row) >= 100 ? '#F5C842' : '#5B8DEF'
}

function onRowClick(_event, { item }) {
  emit('select-set', item.set_id)
}
</script>
