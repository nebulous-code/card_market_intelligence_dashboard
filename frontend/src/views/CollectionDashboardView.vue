<template>
  <div>
    <!-- Page header: title + Download Excel button. -->
    <div class="d-flex align-center mb-4 flex-wrap ga-2">
      <div class="text-h4 font-weight-bold">Collection Dashboard</div>
      <v-spacer />
      <v-btn
        color="primary"
        prepend-icon="mdi-file-excel-outline"
        :loading="downloadingExcel"
        @click="onDownloadExcel"
      >
        Download Excel
      </v-btn>
    </div>

    <v-skeleton-loader v-if="loading" type="article" />

    <v-alert
      v-else-if="error"
      type="error"
      variant="tonal"
      class="mb-4"
    >
      {{ error }}
    </v-alert>

    <template v-else-if="cards.length > 0">
      <CollectionKpis :cards="filteredCards" />

      <CollectionTreemap :cards="filteredCards" :palette="palette" />

      <v-row class="mb-6">
        <v-col cols="12" :md="hasNonStandardVariants ? 6 : 12">
          <CollectionValuePie
            :cards="filteredCards"
            :palette="palette"
          />
        </v-col>
        <v-col v-if="hasNonStandardVariants" cols="12" md="6">
          <CollectionVariantBars :cards="filteredCards" />
        </v-col>
      </v-row>

      <CollectionPriceOverTime v-model="timeWindow" />
      <CollectionMoversChart :window="timeWindow" />

      <CollectionTopCardsTable
        :cards="filteredCards"
        :collapsed="topCardsCollapsed"
        @update:collapsed="onTopCardsCollapsedChange"
      />

      <CollectionSetsTable
        :cards="filteredCards"
        :collapsed="setsCollapsed"
        :has-set-filter="filterState.sets.size > 0"
        @update:collapsed="onSetsCollapsedChange"
        @select-set="onSelectSet"
        @clear-set-filter="onClearSetFilter"
        @reset-collection="onResetCollection"
      />
    </template>

    <CollectionSlicerPanel
      v-if="!loading && !error && cards.length > 0"
      :cards="cards"
      :filter-state="filterState"
      :collapsed="slicersCollapsed"
      @update:collapsed="onSlicersCollapsedChange"
    />

    <v-snackbar
      v-model="excelToast"
      color="error"
      :timeout="4000"
      location="bottom right"
    >
      {{ excelToastMessage }}
    </v-snackbar>
  </div>
</template>

<script setup>
/**
 * Collection Dashboard.
 *
 * Loads the parsed session collection on mount, redirects to the upload
 * page (with an ``empty=1`` banner marker) if no session exists, and
 * holds the shared filter state that every chart and table consumes.
 *
 * The filter state and ``filteredCards`` computed read by every widget
 * mean the slicer panel built in M04_S04 only needs to write into
 * ``filterState`` -- charts pick up the change reactively without any
 * per-chart wiring. URL params on mount hydrate the filters; user
 * changes write back to the URL so the dashboard is shareable and
 * survives reloads.
 */

import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import CollectionKpis from '../components/collection/CollectionKpis.vue'
import CollectionMoversChart from '../components/collection/CollectionMoversChart.vue'
import CollectionPriceOverTime from '../components/collection/CollectionPriceOverTime.vue'
import CollectionSetsTable from '../components/collection/CollectionSetsTable.vue'
import CollectionSlicerPanel from '../components/collection/CollectionSlicerPanel.vue'
import CollectionTopCardsTable from '../components/collection/CollectionTopCardsTable.vue'
import CollectionTreemap from '../components/collection/CollectionTreemap.vue'
import CollectionValuePie from '../components/collection/CollectionValuePie.vue'
import CollectionVariantBars from '../components/collection/CollectionVariantBars.vue'
import {
  deleteCollectionSession,
  downloadCollectionExcel,
  getCollectionCardsWithPrices,
  getPalette,
} from '../api/index.js'
import { variantBars } from '../utils/collectionStats.js'
import {
  createEmptyFilterState,
  filterCards,
  filterStateFromQuery,
  filterStateToQuery,
} from '../utils/collectionFilters.js'

const route = useRoute()
const router = useRouter()

const cards = ref([])
const palette = ref([])
const loading = ref(true)
const error = ref('')

const downloadingExcel = ref(false)
const excelToast = ref(false)
const excelToastMessage = ref('')

// Time window shared by the price-over-time and gainers/losers
// components. Defaults to 30D per the spec.
const timeWindow = ref('30d')

// Collapsible-table state. Persisted in URL params so a refresh keeps
// the user's chosen layout.
const topCardsCollapsed = ref(route.query.topCollapsed === '1')
const setsCollapsed = ref(route.query.setsCollapsed === '1')
const slicersCollapsed = ref(route.query.slicersCollapsed === 'true')

function onSlicersCollapsedChange(value) {
  slicersCollapsed.value = value
  patchQuery({ slicersCollapsed: value ? 'true' : undefined })
}

function onTopCardsCollapsedChange(value) {
  topCardsCollapsed.value = value
  patchQuery({ topCollapsed: value ? '1' : undefined })
}

function onSetsCollapsedChange(value) {
  setsCollapsed.value = value
  patchQuery({ setsCollapsed: value ? '1' : undefined })
}

function patchQuery(patch) {
  const next = { ...route.query, ...patch }
  for (const k of Object.keys(patch)) {
    if (patch[k] === undefined) delete next[k]
  }
  router.replace({ query: next })
}

function onSelectSet(setId) {
  filterState.sets = new Set([setId])
}

function onClearSetFilter() {
  filterState.sets = new Set()
}

async function onResetCollection() {
  try {
    await deleteCollectionSession()
  } catch {
    // Already gone -- nothing to do.
  }
  router.push('/collection')
}

async function onDownloadExcel() {
  // Fetch via the shared http instance so the session cookie + CORS
  // config behave identically to every other dashboard request. Errors
  // are surfaced as toasts rather than a broken Save dialog.
  downloadingExcel.value = true
  try {
    const blob = await downloadCollectionExcel()
    triggerBlobDownload(blob, 'collection.xlsx')
  } catch (err) {
    excelToastMessage.value =
      err?.response?.status === 404
        ? 'Please load a collection before downloading.'
        : 'Excel export is not available yet.'
    excelToast.value = true
  } finally {
    downloadingExcel.value = false
  }
}

function triggerBlobDownload(blob, fallbackName) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = fallbackName
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}

// Filter state. A reactive() wrapper around four Sets means every change
// flows to filteredCards via Vue's standard reactivity.
const filterState = reactive(createEmptyFilterState())

const filteredCards = computed(() => filterCards(cards.value, filterState))

const totalCardCount = computed(() =>
  cards.value.reduce((acc, c) => acc + Number(c.quantity), 0),
)
const totalSetCount = computed(
  () => new Set(cards.value.map((c) => c.set_id)).size,
)

// Variant chart hides itself when no non-standard variants exist (i.e.
// every card has an empty variant list and is not 1st edition). The
// pie chart takes the full row width in that case per the spec.
const hasNonStandardVariants = computed(
  () => variantBars(filteredCards.value).length > 0,
)

// Hydrate filter state from URL on first load. Done as a function so we
// can also call it on browser-back navigation if needed.
function hydrateFromQuery() {
  const next = filterStateFromQuery(route.query)
  filterState.sets = next.sets
  filterState.rarities = next.rarities
  filterState.conditions = next.conditions
  filterState.variants = next.variants
}

// Watch every filter change and mirror it back into the URL so the
// dashboard is reload-safe and shareable. Strip our own keys before
// re-merging so removing a filter actually drops the param.
watch(
  () => [
    Array.from(filterState.sets),
    Array.from(filterState.rarities),
    Array.from(filterState.conditions),
    Array.from(filterState.variants),
  ],
  () => {
    const ours = filterStateToQuery(filterState)
    const {
      sets: _s,
      rarities: _r,
      conditions: _c,
      variants: _v,
      ...rest
    } = route.query
    router.replace({ query: { ...rest, ...ours } })
  },
  { deep: true },
)

onMounted(async () => {
  hydrateFromQuery()
  try {
    const [collectionResponse, paletteResponse] = await Promise.all([
      getCollectionCardsWithPrices(),
      getPalette().catch(() => ({ colors: [] })),
    ])
    cards.value = collectionResponse.cards
    palette.value = paletteResponse.colors ?? []
  } catch (err) {
    if (err?.response?.status === 404) {
      router.replace({ path: '/collection', query: { empty: '1' } })
      return
    }
    error.value = 'Could not load your collection.'
  } finally {
    loading.value = false
  }
})

// Expose to the runtime for the Phase 3+ components that will be
// imported here later. Defined as a no-op so Vue doesn't warn on the
// unused identifier; will be referenced by KPI / chart imports.
defineExpose({ filterState, filteredCards })
</script>
