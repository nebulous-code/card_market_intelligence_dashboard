<template>
  <v-card class="pa-4 mb-6">
    <div class="d-flex align-center mb-3 flex-wrap ga-2">
      <div class="text-h6 font-weight-bold">Top Gainers and Losers</div>
      <v-spacer />
      <v-btn-toggle
        v-model="count"
        mandatory
        density="compact"
        variant="outlined"
        rounded="lg"
      >
        <v-btn v-for="opt in COUNT_OPTIONS" :key="opt" :value="opt" size="small">
          {{ opt }}
        </v-btn>
      </v-btn-toggle>
    </div>

    <v-skeleton-loader v-if="loading" type="image" />
    <div v-else-if="error" class="text-medium-emphasis">{{ error }}</div>
    <div v-else-if="gainers.length === 0 && losers.length === 0" class="text-medium-emphasis">
      No cards moving more than {{ thresholdPercent }}% in this window.
    </div>
    <template v-else>
      <v-row>
        <v-col cols="12" md="6">
          <div class="text-subtitle-2 mb-2 text-medium-emphasis">Gainers</div>
          <div style="position: relative; min-height: 240px;">
            <Bar :data="gainersData" :options="chartOptions(true)" />
          </div>
        </v-col>
        <v-col cols="12" md="6">
          <div class="text-subtitle-2 mb-2 text-medium-emphasis">Losers</div>
          <div style="position: relative; min-height: 240px;">
            <Bar :data="losersData" :options="chartOptions(false)" />
          </div>
        </v-col>
      </v-row>
      <div class="text-caption text-medium-emphasis mt-2">
        Time window controlled by the selector above.
      </div>
      <div v-if="insufficientNote" class="text-caption mt-1">
        {{ insufficientNote }}
      </div>
    </template>
  </v-card>
</template>

<script setup>
/**
 * Twin bar charts of the top gainers and losers in the active time
 * window. Both share the same y-axis range so visual heights are
 * directly comparable. The 5% movement threshold is a constant; cards
 * below it are filtered out server-side.
 */

import {
  BarElement,
  CategoryScale,
  Chart as ChartJS,
  Legend,
  LinearScale,
  Tooltip,
} from 'chart.js'
import { computed, ref, watch } from 'vue'
import { Bar } from 'vue-chartjs'
import { useRouter } from 'vue-router'
import { getCollectionMovers } from '../../api/index.js'
import { formatCurrency } from '../../utils/formatters.js'

ChartJS.register(BarElement, CategoryScale, LinearScale, Tooltip, Legend)

const COUNT_OPTIONS = [3, 5, 10, 20]
const MIN_PCT = 0.05

const props = defineProps({
  window: { type: String, default: '30d' },
})

const router = useRouter()

const count = ref(5)
const loading = ref(false)
const error = ref('')
const gainers = ref([])
const losers = ref([])

const thresholdPercent = computed(() => Math.round(MIN_PCT * 100))

async function loadData() {
  loading.value = true
  error.value = ''
  try {
    const response = await getCollectionMovers(props.window, count.value, MIN_PCT)
    gainers.value = response.gainers
    losers.value = response.losers
  } catch (err) {
    error.value = 'Could not load gainers/losers.'
  } finally {
    loading.value = false
  }
}

watch(() => props.window, loadData, { immediate: true })
watch(count, loadData)

const sharedYRange = computed(() => {
  const all = [...gainers.value, ...losers.value].map((m) =>
    Math.abs(Number(m.change_pct)),
  )
  if (all.length === 0) return { min: -0.1, max: 0.1 }
  const peak = Math.max(...all) * 1.1 || 0.1
  return { min: -peak, max: peak }
})

const gainersData = computed(() => ({
  labels: gainers.value.map((m) => m.card_name),
  datasets: [
    {
      label: 'Gain %',
      data: gainers.value.map((m) => Number(m.change_pct)),
      backgroundColor: '#4CAF82',
      borderColor: '#4CAF82',
      borderRadius: 4,
    },
  ],
}))

const losersData = computed(() => ({
  labels: losers.value.map((m) => m.card_name),
  datasets: [
    {
      label: 'Loss %',
      data: losers.value.map((m) => Number(m.change_pct)),
      backgroundColor: '#CF6679',
      borderColor: '#CF6679',
      borderRadius: 4,
    },
  ],
}))

function chartOptions(isGainers) {
  return {
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
            const m = (isGainers ? gainers.value : losers.value)[ctx.dataIndex]
            const pct = (Number(m.change_pct) * 100).toFixed(1)
            const sign = Number(m.change_pct) > 0 ? '+' : '−'
            return [
              `${sign}${Math.abs(pct)}% (${formatCurrency(Number(m.change_dollars))})`,
              `${formatCurrency(Number(m.start_price))} → ${formatCurrency(Number(m.current_price))}`,
              `${m.set_name} • ${m.condition}`,
            ]
          },
        },
      },
    },
    scales: {
      x: {
        ticks: {
          color: '#F5EDD6',
          autoSkip: false,
          maxRotation: 30,
          minRotation: 0,
        },
        grid: { color: 'rgba(160, 160, 184, 0.05)' },
      },
      y: {
        min: sharedYRange.value.min,
        max: sharedYRange.value.max,
        ticks: {
          color: '#A0A0B8',
          callback: (v) => `${(v * 100).toFixed(0)}%`,
        },
        grid: { color: 'rgba(160, 160, 184, 0.08)' },
      },
    },
    onClick: (_evt, elements) => {
      if (!elements.length) return
      const m = (isGainers ? gainers.value : losers.value)[elements[0].index]
      if (m?.card_id) {
        router.push(`/cards/${m.card_id}?from=collection`)
      }
    },
  }
}

const insufficientNote = computed(() => {
  const want = count.value
  const gShort = gainers.value.length < want
  const lShort = losers.value.length < want
  if (!gShort && !lShort) return ''
  const pct = thresholdPercent.value
  if (gShort && lShort) {
    return `Showing ${gainers.value.length} gainers and ${losers.value.length} losers. Your collection has fewer cards moving more than ${pct}% in this window.`
  }
  if (gShort) {
    return `Showing ${gainers.value.length} gainers. Your collection has fewer than ${want} cards gaining more than ${pct}% in this window.`
  }
  return `Showing ${losers.value.length} losers. Your collection has fewer than ${want} cards losing more than ${pct}% in this window.`
})
</script>
