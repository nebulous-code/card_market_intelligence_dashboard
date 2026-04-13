<template>
  <v-container class="py-6">

    <!-- Set selector dropdown. Lets the user choose which ingested set to view.
         The dropdown is populated from the sets fetched on page load. -->
    <v-row class="mb-4">
      <v-col cols="12" md="4">
        <v-select
          v-model="selectedSetId"
          :items="setItems"
          item-title="name"
          item-value="id"
          label="Select a Set"
          variant="outlined"
          density="comfortable"
          hide-details
          :loading="loadingSets"
          prepend-inner-icon="mdi-cards"
        />
      </v-col>
    </v-row>

    <!-- Content area. Only shown after a set has been selected. -->
    <template v-if="selectedSetId">

      <!-- Error banner. Shown if any API request fails. -->
      <v-alert v-if="error" type="error" variant="tonal" class="mb-4">
        {{ error }}
      </v-alert>

      <!-- Set summary card: name, series, card count, release date, logo. -->
      <SetSummaryCard :set="selectedSet" />

      <!-- Bar chart showing average card price grouped by rarity. -->
      <PriceChart :cards="cards" :prices-by-card-id="pricesByCardId" />

      <!-- Paginated, sortable table of all cards with prices. -->
      <CardTable :cards="cards" :prices-by-card-id="pricesByCardId" :loading="loadingCards" />

    </template>

    <!-- Empty state shown when sets have loaded but none exist in the database. -->
    <v-alert v-else-if="!loadingSets && sets.length === 0" type="info" variant="tonal">
      No sets found. Run the ingestion script to populate the database:
      <code>docker compose run ingestion python run.py --set-id base1</code>
    </v-alert>

  </v-container>
</template>

<script setup>
/**
 * Dashboard view.
 *
 * This is the main page of the application. It manages loading state for
 * both sets and cards, coordinates the three display components, and handles
 * errors from the API in a way that shows the user a clear message.
 *
 * Data flow:
 *   1. On page load, fetch all sets and select the first one automatically.
 *   2. When a set is selected, fetch its card list.
 *   3. For each card, fetch its latest prices in parallel.
 *   4. Pass the cards and price data down to the child components as props.
 */

import { computed, onMounted, ref, watch } from "vue";
import { getCardsForSet, getSetCardPrices, getSets } from "../api/index.js";
import CardTable from "../components/CardTable.vue";
import PriceChart from "../components/PriceChart.vue";
import SetSummaryCard from "../components/SetSummaryCard.vue";

// Reactive state. Vue tracks these and re-renders the template whenever
// any of them change.
const sets = ref([]);           // all sets available in the dropdown
const selectedSetId = ref(null); // the ID of the currently selected set
const cards = ref([]);           // cards for the selected set
const pricesByCardId = ref({});  // map of card ID to its latest prices array
const loadingSets = ref(false);  // true while the sets request is in flight
const loadingCards = ref(false); // true while card/price requests are in flight
const error = ref(null);         // error message to show the user, or null

// Computed values derived from state. Vue recalculates these automatically
// when the values they depend on change.
const setItems = computed(() => sets.value);
const selectedSet = computed(
  () => sets.value.find((s) => s.id === selectedSetId.value) ?? null
);

// On page load: fetch the list of all sets and auto-select the first one.
onMounted(async () => {
  loadingSets.value = true;
  try {
    sets.value = await getSets();

    // Automatically select the first set so the dashboard is not empty
    // when it loads. The watch below will fire and load that set's cards.
    if (sets.value.length > 0) {
      selectedSetId.value = sets.value[0].id;
    }
  } catch (e) {
    error.value = "Failed to load sets. Is the API running?";
  } finally {
    // Always turn off the loading state, even if an error occurred.
    loadingSets.value = false;
  }
});

// Watch for set selection changes. When the user picks a different set,
// fetch the cards and prices for that set.
watch(selectedSetId, async (setId) => {
  if (!setId) return;

  // Reset state before loading so stale data from the previous set
  // does not briefly appear while the new data is loading.
  error.value = null;
  loadingCards.value = true;
  pricesByCardId.value = {};

  try {
    // Step 1: Fetch the card list for this set.
    cards.value = await getCardsForSet(setId);
  } catch (e) {
    error.value = `Failed to load cards for set '${setId}'.`;
    return;
  } finally {
    loadingCards.value = false;
  }

  // Step 2: Fetch latest prices for all cards in one request.
  // This is kept separate from the card fetch so a price failure does not
  // prevent the card table from rendering -- cards show with empty prices
  // rather than the whole view failing.
  try {
    pricesByCardId.value = await getSetCardPrices(setId);
  } catch (e) {
    console.warn("Failed to load prices for set:", setId, e);
    pricesByCardId.value = {};
  } finally {
    loadingCards.value = false;
  }
});
</script>
