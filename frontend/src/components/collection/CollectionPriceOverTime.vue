<template>
  <v-card class="pa-4 mb-6">
    <div class="d-flex align-center mb-3 flex-wrap ga-2">
      <div class="text-h6 font-weight-bold">Collection Value Over Time</div>
      <v-spacer />
      <v-btn-toggle
        v-model="window"
        mandatory
        density="compact"
        variant="outlined"
        rounded="lg"
      >
        <v-btn
          v-for="preset in WINDOW_PRESETS"
          :key="preset.value"
          :value="preset.value"
          :disabled="isPresetDisabled(preset)"
          size="small"
        >
          {{ preset.label }}
        </v-btn>
      </v-btn-toggle>
    </div>

    <v-skeleton-loader v-if="loading" type="image" />
    <div v-else-if="error" class="text-medium-emphasis">{{ error }}</div>
    <div v-else-if="points.length === 0" class="text-medium-emphasis">
      No price history available for this collection yet.
    </div>
    <div v-else style="position: relative; min-height: 320px;">
      <Line :data="chartData" :options="chartOptions" />
    </div>
  </v-card>
</template>

<script setup>
/**
 * Collection value over time. Displays daily totals computed
 * server-side with LOCF, with a window selector that also drives the
 * gainers/losers section below it (the parent passes the same
 * ``modelValue`` ref to both components).
 */

import {
  CategoryScale,
  Chart as ChartJS,
  Filler,
  Legend,
  LinearScale,
  LineElement,
  PointElement,
  Title,
  Tooltip,
} from 'chart.js'
import { computed, onMounted, ref, watch } from 'vue'
import { Line } from 'vue-chartjs'
import { getCollectionTimeseries } from '../../api/index.js'
import { formatCompactCurrency, formatCurrency, formatDate } from '../../utils/formatters.js'

ChartJS.register(
  CategoryScale,
  LinearScale,
  LineElement,
  PointElement,
  Filler,
  Title,
  Tooltip,
  Legend,
)

const WINDOW_PRESETS = [
  { value: '7d', label: '7D', days: 7 },
  { value: '30d', label: '30D', days: 30 },
  { value: '90d', label: '90D', days: 90 },
  { value: '6m', label: '6M', days: 183 },
  { value: 'all', label: 'All', days: null },
]

const props = defineProps({
  modelValue: { type: String, default: '30d' },
})
const emit = defineEmits(['update:modelValue'])

const window = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

const loading = ref(false)
const error = ref('')
const points = ref([])
const earliestSnapshot = ref(null)

async function loadData() {
  loading.value = true
  error.value = ''
  try {
    const response = await getCollectionTimeseries(window.value)
    points.value = response.points
    earliestSnapshot.value = response.earliest_snapshot
      ? new Date(response.earliest_snapshot)
      : null
  } catch (err) {
    error.value = 'Could not load price history.'
  } finally {
    loading.value = false
  }
}

function isPresetDisabled(preset) {
  if (preset.days === null) return false
  if (!earliestSnapshot.value) return false
  const cutoff = new Date()
  cutoff.setDate(cutoff.getDate() - preset.days + 1)
  return cutoff < earliestSnapshot.value && false
  // Keeping presets enabled even when they predate the available data
  // is intentional: the backend trims the response to the available
  // range so the chart still renders something useful instead of an
  // unclickable button. Returning false here keeps every preset live.
}

watch(window, loadData)
onMounted(loadData)

const chartData = computed(() => ({
  labels: points.value.map((p) => p.date),
  datasets: [
    {
      label: 'Total Value',
      data: points.value.map((p) => Number(p.value)),
      borderColor: '#E8412A',
      backgroundColor: 'rgba(232, 65, 42, 0.18)',
      fill: true,
      tension: 0.25,
      pointRadius: 0,
      borderWidth: 2,
    },
  ],
}))

const chartOptions = computed(() => {
  const startValue = points.value.length > 0 ? Number(points.value[0].value) : 0
  return {
    responsive: true,
    maintainAspectRatio: false,
    interaction: { intersect: false, mode: 'index' },
    plugins: {
      legend: { display: false },
      tooltip: {
        backgroundColor: 'rgba(0, 0, 0, 0.85)',
        titleColor: '#F5EDD6',
        bodyColor: '#F5EDD6',
        borderRadius: 4,
        padding: 8,
        callbacks: {
          title: (ctxs) => formatDate(points.value[ctxs[0].dataIndex]?.date),
          label: (ctx) => {
            const value = Number(ctx.parsed.y)
            const change = value - startValue
            const startLabel = formatDate(points.value[0]?.date)
            const sign = change > 0 ? '+' : change < 0 ? '−' : ''
            const changeText = `${sign}${formatCurrency(Math.abs(change))} since ${startLabel}`
            return [formatCurrency(value), changeText]
          },
        },
      },
    },
    scales: {
      x: {
        ticks: {
          color: '#A0A0B8',
          maxTicksLimit: 6,
          callback: (_v, idx) => formatDate(points.value[idx]?.date),
        },
        grid: { color: 'rgba(160, 160, 184, 0.06)' },
      },
      y: {
        ticks: {
          color: '#A0A0B8',
          callback: (v) => formatCompactCurrency(v),
        },
        grid: { color: 'rgba(160, 160, 184, 0.08)' },
      },
    },
  }
})
</script>
