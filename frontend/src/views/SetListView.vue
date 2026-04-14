<template>
  <div>
    <!-- Page title -->
    <div class="mb-6">
      <div class="text-h4 font-weight-bold">Sets</div>
      <div v-if="!loadingSets" class="text-subtitle-1 text-medium-emphasis">
        {{ sets.length }} {{ sets.length === 1 ? 'set' : 'sets' }}
      </div>
    </div>

    <!-- Loading state -->
    <v-row v-if="loadingSets">
      <v-col v-for="n in 4" :key="n" cols="6" sm="4" md="3">
        <v-skeleton-loader type="card" height="320" />
      </v-col>
    </v-row>

    <!-- Empty state -->
    <EmptyState
      v-else-if="sets.length === 0"
      icon="mdi-cards-outline"
      title="No sets found"
      message="Run the ingestion script to populate the database."
    />

    <!-- Set grid -->
    <v-row v-else>
      <v-col
        v-for="set in sets"
        :key="set.id"
        cols="6"
        sm="4"
        md="3"
      >
        <v-card
          :to="`/sets/${set.id}`"
          class="set-card"
          height="320"
          :ripple="true"
        >
          <!-- Image area -->
          <div class="set-card__image-area d-flex align-center justify-center">
            <v-img
              v-if="set.logo_url"
              :src="set.logo_url"
              :alt="set.name"
              max-height="80"
              contain
            />
            <div v-else class="text-h5 font-weight-bold text-medium-emphasis">
              {{ setInitials(set.name) }}
            </div>
          </div>

          <!-- Accent divider -->
          <div class="set-card__divider" />

          <!-- Set name -->
          <v-card-text class="pa-3 pb-0">
            <div class="text-subtitle-2 font-weight-bold text-truncate">{{ set.name }}</div>

            <!-- Meta row -->
            <div class="d-flex justify-space-between mt-1">
              <span class="text-caption text-medium-emphasis">{{ set.printed_total }} cards</span>
              <span class="text-caption text-medium-emphasis">{{ formatMonthYear(set.release_date) }}</span>
            </div>
          </v-card-text>

          <!-- Price mini-table -->
          <v-card-text class="pa-3 pt-2">
            <template v-if="set.min_price != null">
              <div class="d-flex justify-space-between text-caption text-medium-emphasis mb-1">
                <span>Min</span>
                <span>Avg</span>
                <span>Max</span>
              </div>
              <div class="d-flex justify-space-between text-caption font-weight-bold text-primary">
                <span>{{ formatCompactCurrency(set.min_price) }}</span>
                <span>{{ formatCompactCurrency(set.avg_price) }}</span>
                <span>{{ formatCompactCurrency(set.max_price) }}</span>
              </div>
            </template>
            <template v-else>
              <div class="d-flex justify-space-between text-caption text-medium-emphasis mb-1">
                <span>Min</span>
                <span>Avg</span>
                <span>Max</span>
              </div>
              <div class="d-flex justify-space-between text-caption text-medium-emphasis">
                <span>—</span>
                <span>—</span>
                <span>—</span>
              </div>
              <div class="text-caption text-medium-emphasis mt-1 text-center">No pricing data yet</div>
            </template>
          </v-card-text>
        </v-card>
      </v-col>
    </v-row>
  </div>
</template>

<script setup>
import { onMounted, ref } from "vue";
import { getSets } from "../api/index.js";
import EmptyState from "../components/EmptyState.vue";
import { formatCompactCurrency, formatMonthYear } from "../utils/formatters.js";

const sets = ref([]);
const loadingSets = ref(true);

onMounted(async () => {
  try {
    sets.value = await getSets();
  } finally {
    loadingSets.value = false;
  }
});

function setInitials(name) {
  return name
    .split(" ")
    .map((w) => w[0])
    .join("")
    .toUpperCase()
    .slice(0, 3);
}
</script>

<style scoped>
.set-card {
  cursor: pointer;
  transition: border 0.15s ease, box-shadow 0.15s ease;
  border: 1px solid transparent;
}

.set-card:hover {
  border-color: #E8412A;
  box-shadow: 0 4px 16px rgba(232, 65, 42, 0.2) !important;
}

.set-card__image-area {
  height: 128px;
  background-color: #12121F;
  padding: 16px;
}

.set-card__divider {
  height: 2px;
  background-color: #E8412A;
}
</style>
