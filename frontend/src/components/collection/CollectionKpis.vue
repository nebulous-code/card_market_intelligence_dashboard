<template>
  <div>
    <!-- Primary KPI row: 2 tiles (always) or 4 tiles (when any card has a purchase price). -->
    <v-row class="mb-3">
      <v-col cols="12" :md="showGains ? 3 : 6">
        <v-card class="kpi-tile h-100" variant="flat">
          <v-card-text>
            <div class="text-caption text-medium-emphasis">Total Collection Value</div>
            <div class="text-h5 font-weight-bold">{{ formatCurrency(totalValue) }}</div>
          </v-card-text>
        </v-card>
      </v-col>
      <v-col cols="12" :md="showGains ? 3 : 6">
        <v-card class="kpi-tile h-100" variant="flat">
          <v-card-text>
            <div class="text-caption text-medium-emphasis">Total Card Count</div>
            <div class="text-h5 font-weight-bold">
              {{ formatNumber(totalCount) }}
              <span class="text-body-2 text-medium-emphasis">cards</span>
            </div>
          </v-card-text>
        </v-card>
      </v-col>
      <template v-if="showGains">
        <v-col cols="12" md="3">
          <v-card class="kpi-tile h-100" variant="flat">
            <v-card-text>
              <div class="text-caption text-medium-emphasis">Lifetime Gain ($)</div>
              <div
                class="text-h5 font-weight-bold"
                :class="gainColorClass(gain?.dollarsGain)"
              >
                {{ formatSignedCurrency(gain?.dollarsGain) }}
              </div>
            </v-card-text>
          </v-card>
        </v-col>
        <v-col cols="12" md="3">
          <v-card class="kpi-tile h-100" variant="flat">
            <v-card-text>
              <div class="text-caption text-medium-emphasis">Lifetime Gain (%)</div>
              <div
                class="text-h5 font-weight-bold"
                :class="gainColorClass(gain?.percentGain)"
              >
                {{ formatSignedPercent(gain?.percentGain) }}
              </div>
            </v-card-text>
          </v-card>
        </v-col>
      </template>
    </v-row>

    <!-- Secondary row: most valuable card. -->
    <v-card v-if="topCard" class="kpi-tile mb-6" variant="flat">
      <v-card-text class="d-flex align-center flex-wrap ga-2">
        <strong>Most Valuable Card:</strong>
        <router-link
          :to="`/cards/${topCard.card_id}?from=collection`"
          class="text-decoration-none top-card-link"
        >
          {{ topCard.card_name }}
        </router-link>
        <span class="text-medium-emphasis">
          ({{ topCard.set_name }} {{ topCard.condition }})
        </span>
        <span class="ml-auto font-weight-bold">
          {{ formatCurrency(topCard.market_price) }}
        </span>
      </v-card-text>
    </v-card>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import {
  anyPurchasePrices,
  lifetimeGain,
  mostValuableCard,
  totalCardCount,
  totalCollectionValue,
} from '../../utils/collectionStats.js'
import { formatCurrency, formatNumber } from '../../utils/formatters.js'

const props = defineProps({
  cards: { type: Array, required: true },
})

const totalValue = computed(() => totalCollectionValue(props.cards))
const totalCount = computed(() => totalCardCount(props.cards))
const showGains = computed(() => anyPurchasePrices(props.cards))
const gain = computed(() => lifetimeGain(props.cards))
const topCard = computed(() => mostValuableCard(props.cards))

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

function gainColorClass(value) {
  if (value == null || value === 0) return ''
  return value > 0 ? 'text-success' : 'text-error'
}
</script>

<style scoped>
.kpi-tile {
  background-color: #1e1e30;
  border: 1px solid rgba(255, 255, 255, 0.05);
}
.top-card-link {
  color: #f5edd6;
  border-bottom: 1px dashed rgba(245, 237, 214, 0.4);
}
.top-card-link:hover {
  color: #e8412a;
  border-bottom-color: #e8412a;
}
</style>
