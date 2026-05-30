<template>
  <v-card class="pa-4 h-100">
    <div class="text-h6 font-weight-bold mb-3">Value by Set</div>
    <div v-if="!hasData" class="text-medium-emphasis">
      No priced cards to chart yet.
    </div>
    <div v-else style="position: relative; min-height: 320px;">
      <Doughnut :data="chartData" :options="chartOptions" />
    </div>
  </v-card>
</template>

<script setup>
/**
 * Doughnut chart of total collection value broken down by set.
 *
 * Slices are sized by ``sum(quantity * market_price)`` per set. Colors
 * come from the palette prop -- the dashboard fetches it once and
 * passes the same array to every chart so a set keeps the same color
 * everywhere on the page.
 */

import {
  ArcElement,
  Chart as ChartJS,
  Legend,
  Tooltip,
} from 'chart.js'
import { computed } from 'vue'
import { Doughnut } from 'vue-chartjs'
import { aggregateBySet, totalCollectionValue } from '../../utils/collectionStats.js'
import { formatCurrency } from '../../utils/formatters.js'

ChartJS.register(ArcElement, Tooltip, Legend)

const props = defineProps({
  cards: { type: Array, required: true },
  palette: { type: Array, default: () => [] },
})

const sets = computed(() => aggregateBySet(props.cards))
const grandTotal = computed(() => totalCollectionValue(props.cards))
const hasData = computed(() => sets.value.length > 0 && grandTotal.value > 0)

const chartData = computed(() => ({
  labels: sets.value.map((s) => s.set_name),
  datasets: [
    {
      data: sets.value.map((s) => Number(s.total_value.toFixed(2))),
      backgroundColor: sets.value.map((_, idx) => paletteColor(idx)),
      borderColor: '#12121F',
      borderWidth: 2,
    },
  ],
}))

const chartOptions = {
  responsive: true,
  maintainAspectRatio: false,
  cutout: '55%',
  plugins: {
    legend: {
      position: 'right',
      labels: { color: '#F5EDD6', boxWidth: 14, padding: 12 },
    },
    tooltip: {
      backgroundColor: 'rgba(0, 0, 0, 0.85)',
      titleColor: '#F5EDD6',
      bodyColor: '#F5EDD6',
      borderRadius: 4,
      padding: 8,
      callbacks: {
        label: (ctx) => {
          const set = sets.value[ctx.dataIndex]
          const value = formatCurrency(set.total_value)
          const pct = (set.percent_of_collection * 100).toFixed(1)
          return `${set.set_name}: ${value} (${pct}% • ${set.total_quantity} cards)`
        },
      },
    },
  },
}

function paletteColor(idx) {
  const fallback = ['#E8412A', '#F5C842', '#A0A0B8', '#4CAF82', '#FFA726', '#CF6679']
  const source = props.palette.length > 0 ? props.palette : fallback
  return source[idx % source.length]
}
</script>
