<template>
  <v-card>
    <v-card-title class="text-subtitle-1 font-weight-bold pa-4">
      Cards
      <v-spacer />
    </v-card-title>
    <v-data-table
      :headers="headers"
      :items="rows"
      :loading="loading"
      :items-per-page="25"
      density="compact"
      hover
    >
      <template #item.image_url="{ item }">
        <v-img
          v-if="item.image_url"
          :src="item.image_url"
          width="36"
          height="50"
          contain
          class="my-1"
        />
      </template>

      <template #item.market_price="{ item }">
        <span v-if="item.market_price != null">${{ Number(item.market_price).toFixed(2) }}</span>
        <span v-else class="text-medium-emphasis">—</span>
      </template>
    </v-data-table>
  </v-card>
</template>

<script setup>
import { computed } from "vue";

const props = defineProps({
  cards: {
    type: Array,
    default: () => [],
  },
  /**
   * Map of card_id → latest_prices array, pre-fetched by the parent.
   */
  pricesByCardId: {
    type: Object,
    default: () => ({}),
  },
  loading: {
    type: Boolean,
    default: false,
  },
});

const headers = [
  { title: "", key: "image_url", sortable: false, width: "56px" },
  { title: "#", key: "number", width: "72px" },
  { title: "Name", key: "name" },
  { title: "Supertype", key: "supertype" },
  { title: "Rarity", key: "rarity" },
  { title: "Market Price", key: "market_price", align: "end" },
];

const rows = computed(() =>
  props.cards.map((card) => {
    const prices = props.pricesByCardId[card.id] ?? [];
    // Prefer normal price; fall back to holofoil.
    const snap =
      prices.find((p) => p.condition === "normal") ??
      prices.find((p) => p.condition === "holofoil") ??
      null;
    return {
      ...card,
      market_price: snap?.market_price ?? null,
    };
  })
);
</script>
