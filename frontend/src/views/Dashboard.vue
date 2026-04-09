<template>
  <v-container class="py-6">
    <!-- Set selector -->
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

    <template v-if="selectedSetId">
      <!-- Error state -->
      <v-alert v-if="error" type="error" variant="tonal" class="mb-4">
        {{ error }}
      </v-alert>

      <!-- Set summary -->
      <SetSummaryCard :set="selectedSet" />

      <!-- Price chart -->
      <PriceChart :cards="cards" :prices-by-card-id="pricesByCardId" />

      <!-- Card table -->
      <CardTable :cards="cards" :prices-by-card-id="pricesByCardId" :loading="loadingCards" />
    </template>

    <v-alert v-else-if="!loadingSets && sets.length === 0" type="info" variant="tonal">
      No sets found. Run the ingestion script to populate the database:
      <code>docker compose run ingestion python run.py --set-id base1</code>
    </v-alert>
  </v-container>
</template>

<script setup>
import { computed, onMounted, ref, watch } from "vue";
import { getCard, getCardsForSet, getSets } from "../api/index.js";
import CardTable from "../components/CardTable.vue";
import PriceChart from "../components/PriceChart.vue";
import SetSummaryCard from "../components/SetSummaryCard.vue";

const sets = ref([]);
const selectedSetId = ref(null);
const cards = ref([]);
const pricesByCardId = ref({});
const loadingSets = ref(false);
const loadingCards = ref(false);
const error = ref(null);

const setItems = computed(() => sets.value);
const selectedSet = computed(() => sets.value.find((s) => s.id === selectedSetId.value) ?? null);

onMounted(async () => {
  loadingSets.value = true;
  try {
    sets.value = await getSets();
    if (sets.value.length > 0) {
      selectedSetId.value = sets.value[0].id;
    }
  } catch (e) {
    error.value = "Failed to load sets. Is the API running?";
  } finally {
    loadingSets.value = false;
  }
});

watch(selectedSetId, async (setId) => {
  if (!setId) return;
  error.value = null;
  loadingCards.value = true;
  pricesByCardId.value = {};

  try {
    cards.value = await getCardsForSet(setId);

    // Fetch price snapshots for each card in parallel.
    const results = await Promise.allSettled(cards.value.map((c) => getCard(c.id)));
    const prices = {};
    results.forEach((result, i) => {
      if (result.status === "fulfilled") {
        prices[cards.value[i].id] = result.value.latest_prices ?? [];
      }
    });
    pricesByCardId.value = prices;
  } catch (e) {
    error.value = `Failed to load cards for set '${setId}'.`;
  } finally {
    loadingCards.value = false;
  }
});
</script>
