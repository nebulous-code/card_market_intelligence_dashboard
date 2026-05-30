<template>
  <v-card class="pa-4 mb-6">
    <div class="text-h6 font-weight-bold mb-3">Collection Treemap</div>
    <div v-if="entries.length === 0" class="text-medium-emphasis">
      No priced cards to chart yet.
    </div>
    <div v-else style="position: relative; min-height: 480px;">
      <Chart type="treemap" :data="chartData" :options="chartOptions" />
    </div>
  </v-card>
</template>

<script setup>
/**
 * Set -> Card treemap. Each card rectangle is sized by quantity *
 * market price; cards within a set share the set's palette color, and
 * the cheapest cards (bottom 10% of set value) collapse into an
 * "Other" rectangle so a long tail of pennies doesn't dominate the
 * canvas.
 */

import { Chart as ChartJS } from 'chart.js'
import { TreemapController, TreemapElement } from 'chartjs-chart-treemap'
import { computed } from 'vue'
import { Chart } from 'vue-chartjs'
import { useRouter } from 'vue-router'
import { buildTreemapData } from '../../utils/treemap.js'
import { formatCurrency } from '../../utils/formatters.js'

ChartJS.register(TreemapController, TreemapElement)

const props = defineProps({
  cards: { type: Array, required: true },
  palette: { type: Array, default: () => [] },
})

const router = useRouter()

const entries = computed(() => buildTreemapData(props.cards))

const setColors = computed(() => {
  const fallback = ['#E8412A', '#F5C842', '#A0A0B8', '#4CAF82', '#FFA726', '#CF6679']
  const source = props.palette.length > 0 ? props.palette : fallback
  const map = new Map()
  let idx = 0
  for (const e of entries.value) {
    if (!map.has(e.set_id)) {
      map.set(e.set_id, source[idx % source.length])
      idx += 1
    }
  }
  return map
})

const chartData = computed(() => ({
  datasets: [
    {
      tree: entries.value,
      key: 'value',
      groups: ['set_name', 'card_name'],
      borderColor: '#12121F',
      borderWidth: 1,
      spacing: 1,
      // Color cards by set; "Other" rectangles get a muted variant.
      backgroundColor: (ctx) => {
        const item = ctx.raw?._data
        if (!item) return '#12121F'
        const base = setColors.value.get(item.set_id) ?? '#A0A0B8'
        if (item.is_other) return hexAlpha(base, 0.45)
        return hexAlpha(base, 0.78)
      },
      labels: {
        display: true,
        color: '#0B0B14',
        font: { size: 11, weight: '500' },
        formatter: (ctx) => {
          const item = ctx.raw?._data
          if (!item) return ''
          return item.card_name ?? ''
        },
      },
      captions: {
        display: true,
        color: '#F5EDD6',
        font: { weight: '700', size: 13 },
      },
    },
  ],
}))

const chartOptions = {
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
        title: (ctxs) => {
          const item = ctxs[0]?.raw?._data
          if (!item) return ''
          return item.card_name ?? item.set_name
        },
        label: (ctx) => {
          const item = ctx.raw?._data
          if (!item) return ''
          if (item.is_other) {
            const top = item.top_card_name ? ` (top: ${item.top_card_name})` : ''
            return `${item.count} cards • ${formatCurrency(item.value)}${top}`
          }
          return `${item.set_name} • ${formatCurrency(item.value)} • qty ${item.count}`
        },
      },
    },
  },
  onClick: (_evt, elements) => {
    if (!elements.length) return
    const item = elements[0].element?.$context?.raw?._data
    if (item?.card_id && !item.is_other) {
      router.push(`/cards/${item.card_id}?from=collection`)
    }
  },
}

function hexAlpha(hex, alpha) {
  const clean = hex.replace('#', '')
  const r = parseInt(clean.slice(0, 2), 16)
  const g = parseInt(clean.slice(2, 4), 16)
  const b = parseInt(clean.slice(4, 6), 16)
  return `rgba(${r}, ${g}, ${b}, ${alpha})`
}
</script>
