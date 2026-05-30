<template>
  <div>
    <div class="text-h4 font-weight-bold mb-2">Market Trends</div>
    <div class="text-body-2 text-medium-emphasis mb-6">
      Cross-set analyses of how prices move with rarity, condition, and
      printing. Each card on this page links to a dedicated trend view.
    </div>

    <v-row>
      <v-col cols="12" sm="6" md="4">
        <v-card
          to="/trends/condition-multipliers"
          class="trend-card"
          height="200"
          :ripple="true"
        >
          <v-card-text class="d-flex flex-column h-100">
            <v-icon size="40" class="mb-3" color="primary">
              mdi-table-large
            </v-icon>
            <div class="text-h6 font-weight-bold mb-1">
              Condition Multipliers
            </div>
            <div class="text-body-2 text-medium-emphasis">
              How much value a card loses as it degrades along the
              NM → LP → MP → HP → DMG ladder, broken down by rarity and
              supertype within each set.
            </div>
          </v-card-text>
        </v-card>
      </v-col>
    </v-row>
  </div>
</template>

<script setup>
/**
 * Market Trends landing page.
 *
 * One v-card per analysis. New trend stories drop a card alongside the
 * Condition Multipliers one. Kept dead simple -- no slicers, no shared
 * data fetch -- because each child view owns its own state.
 */
</script>

<style scoped>
.trend-card {
  cursor: pointer;
  transition: border 0.15s ease, box-shadow 0.15s ease;
  border: 1px solid transparent;
}

.trend-card:hover {
  border-color: #e8412a;
  box-shadow: 0 4px 16px rgba(232, 65, 42, 0.2) !important;
}
</style>
