<template>
  <v-card class="pa-4 h-100">
    <div class="text-h6 font-weight-bold mb-3">Variant Counts</div>
    <div v-if="bars.length === 0" class="text-medium-emphasis">
      No non-standard variants in this collection.
    </div>
    <div v-else style="position: relative; min-height: 320px;">
      <Bar :data="chartData" :options="chartOptions" />
    </div>
  </v-card>
</template>

<script setup>
/**
 * Horizontal bar chart of total quantity per variant token.
 *
 * Multi-value variants split across bars (each card contributes its
 * quantity to every variant it carries). ``is_first_edition=true``
 * adds a synthetic ``"1st Edition"`` token so the flag has a place on
 * the chart even when no variant string is set.
 */

import {
  BarElement,
  CategoryScale,
  Chart as ChartJS,
  Legend,
  LinearScale,
  LogarithmicScale,
  Tooltip,
} from 'chart.js'
import { computed } from 'vue'
import { Bar } from 'vue-chartjs'
import { variantBars } from '../../utils/collectionStats.js'

ChartJS.register(BarElement, CategoryScale, LinearScale, LogarithmicScale, Tooltip, Legend)

const props = defineProps({
  cards: { type: Array, required: true },
})

const bars = computed(() => variantBars(props.cards))

const chartData = computed(() => ({
  labels: bars.value.map((b) => b.variant),
  datasets: [
    {
      label: 'Quantity',
      data: bars.value.map((b) => b.quantity),
      backgroundColor: '#F5C842',
      borderColor: '#F5C842',
      borderRadius: 4,
    },
  ],
}))

const chartOptions = {
  indexAxis: 'y',
  responsive: true,
  maintainAspectRatio: false,
  plugins: {
    legend: { display: false },
    tooltip: {
      backgroundColor: 'rgba(0, 0, 0, 0.85)',
      titleColor: '#F5EDD6',
      bodyColor: '#F5EDD6',
      borderRadius: 4,
      padding: 8,
      callbacks: {
        label: (ctx) => {
          const bar = bars.value[ctx.dataIndex]
          const cards = bar.unique_cards === 1 ? 'card' : 'cards'
          return `${bar.quantity} owned across ${bar.unique_cards} ${cards}`
        },
      },
    },
  },
  scales: {
    x: {
      type: 'logarithmic',
      ticks: { color: '#A0A0B8' },
      grid: { color: 'rgba(160, 160, 184, 0.08)' },
    },
    y: {
      ticks: { color: '#F5EDD6' },
      grid: { color: 'rgba(160, 160, 184, 0.08)' },
    },
  },
}
</script>
