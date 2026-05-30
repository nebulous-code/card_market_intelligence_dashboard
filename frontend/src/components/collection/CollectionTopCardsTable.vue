<template>
  <v-card class="mb-6">
    <v-card-title
      class="d-flex align-center pa-4"
      style="cursor: pointer;"
      @click="emit('update:collapsed', !collapsed)"
    >
      <v-icon class="mr-2">
        {{ collapsed ? 'mdi-chevron-right' : 'mdi-chevron-down' }}
      </v-icon>
      <div class="text-h6 font-weight-bold">Top Cards by Value</div>
    </v-card-title>
    <v-data-table
      v-if="!collapsed"
      :headers="headers"
      :items="rows"
      :items-per-page="10"
      :sort-by="[{ key: 'total_value', order: 'desc' }]"
      density="compact"
      hover
      @click:row="onRowClick"
    >
      <template #item.image_url="{ item }">
        <v-img
          v-if="item.image_url"
          :src="item.image_url"
          width="40"
          contain
          class="my-1"
        />
      </template>
      <template #item.condition="{ item }">
        <span>{{ item.condition }}</span>
        <v-chip
          v-if="item.is_first_edition"
          color="warning"
          variant="tonal"
          size="x-small"
          class="ml-1"
        >
          1st Ed
        </v-chip>
      </template>
      <template #item.variant="{ item }">
        <span v-if="item.variant.length === 0" class="text-medium-emphasis">—</span>
        <span v-else>{{ item.variant.join(', ') }}</span>
      </template>
      <template #item.market_price="{ item }">
        {{ formatCurrency(item.market_price) }}
      </template>
      <template #item.total_value="{ item }">
        {{ formatCurrency(item.total_value) }}
      </template>
      <template #item.gain_dollars="{ item }">
        <span v-if="item.gain_dollars == null" class="text-medium-emphasis">—</span>
        <span v-else :class="gainClass(item.gain_dollars)">
          {{ formatSignedCurrency(item.gain_dollars) }}
        </span>
      </template>
      <template #item.gain_percent="{ item }">
        <span v-if="item.gain_percent == null" class="text-medium-emphasis">—</span>
        <span v-else :class="gainClass(item.gain_percent)">
          {{ formatSignedPercent(item.gain_percent) }}
        </span>
      </template>
    </v-data-table>
  </v-card>
</template>

<script setup>
/**
 * Top 10 cards by ``quantity * market_price``. Gain columns are
 * conditional -- they only appear when at least one card in the
 * filtered collection has a purchase price set, matching the spec's
 * KPI behavior.
 */

import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { anyPurchasePrices, topCardsByValue } from '../../utils/collectionStats.js'
import { formatCurrency } from '../../utils/formatters.js'

const props = defineProps({
  cards: { type: Array, required: true },
  collapsed: { type: Boolean, default: false },
})
const emit = defineEmits(['update:collapsed'])

const router = useRouter()

const collapsed = computed(() => props.collapsed)

const allRanked = computed(() => topCardsByValue(props.cards))
const rows = computed(() => allRanked.value.slice(0, 10))

const showGains = computed(() => anyPurchasePrices(props.cards))

const headers = computed(() => {
  const base = [
    { title: '', key: 'image_url', sortable: false, width: 56 },
    { title: 'Card', key: 'card_name' },
    { title: 'Set', key: 'set_name' },
    { title: 'Condition', key: 'condition' },
    { title: 'Variant', key: 'variant', sortable: false },
    { title: 'Qty', key: 'quantity', align: 'end' },
    { title: 'Market', key: 'market_price', align: 'end' },
    { title: 'Total', key: 'total_value', align: 'end' },
  ]
  if (showGains.value) {
    base.push(
      { title: 'Gained $', key: 'gain_dollars', align: 'end' },
      { title: 'Gained %', key: 'gain_percent', align: 'end' },
    )
  }
  return base
})

function onRowClick(_event, { item }) {
  router.push(`/cards/${item.card_id}?from=collection`)
}

function gainClass(value) {
  if (value == null || value === 0) return ''
  return value > 0 ? 'text-success' : 'text-error'
}

function formatSignedCurrency(value) {
  if (value == null) return '—'
  const sign = value > 0 ? '+' : value < 0 ? '−' : ''
  return `${sign}${formatCurrency(Math.abs(value))}`
}

function formatSignedPercent(value) {
  if (value == null) return '—'
  const sign = value > 0 ? '+' : value < 0 ? '−' : ''
  return `${sign}${(Math.abs(value) * 100).toFixed(1)}%`
}
</script>
