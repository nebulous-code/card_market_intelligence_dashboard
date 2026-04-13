<template>
  <v-card>
    <v-card-title class="text-subtitle-1 font-weight-bold pa-4">
      Cards
      <v-spacer />
    </v-card-title>

    <!--
      Vuetify data table. Handles pagination, sorting, and rendering automatically.
      :sort-by sets the default sort to card number ascending so cards appear
      in set order when the page first loads.
    -->
    <v-data-table
      :headers="headers"
      :items="rows"
      :loading="loading"
      :items-per-page="25"
      :sort-by="[{ key: 'number', order: 'asc' }]"
      density="compact"
      hover
    >
      <!-- Custom rendering for the image column: show the card image thumbnail. -->
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

      <!-- Custom rendering for the price column: format as a dollar amount. -->
      <template #item.market_price="{ item }">
        <span v-if="item.market_price != null">${{ Number(item.market_price).toFixed(2) }}</span>
        <!-- Show a dash for cards with no price data rather than null or 0. -->
        <span v-else class="text-medium-emphasis">---</span>
      </template>

    </v-data-table>
  </v-card>
</template>

<script setup>
/**
 * CardTable component.
 *
 * Displays all cards for the selected set in a paginated, sortable table.
 * Columns: card image thumbnail, card number, name, supertype, rarity,
 * and market price.
 *
 * The market price shown is the normal condition price if available,
 * falling back to holofoil. Cards with no price data show "---".
 *
 * Props:
 *   cards          - Array of card objects from the API.
 *   pricesByCardId - Map of card ID to latest prices array.
 *   loading        - Whether card data is still being fetched. Shows a
 *                    loading overlay on the table when true.
 */

import { computed } from "vue";

const props = defineProps({
  /**
   * Array of card objects from GET /sets/{id}/cards.
   */
  cards: {
    type: Array,
    default: () => [],
  },
  /**
   * Map of card_id to latest_prices array, pre-fetched by the Dashboard.
   */
  pricesByCardId: {
    type: Object,
    default: () => ({}),
  },
  /**
   * When true, the table shows a loading indicator.
   * Should be true while the Dashboard is fetching card data.
   */
  loading: {
    type: Boolean,
    default: false,
  },
});

// Column definitions for the Vuetify data table.
// Each header defines the column label, the data key it maps to, and
// optional settings like whether the column is sortable.
const headers = [
  { title: "", key: "image_url", sortable: false, width: "56px" }, // thumbnail column
  { title: "#", key: "number", width: "72px" },
  { title: "Name", key: "name" },
  { title: "Supertype", key: "supertype" },
  { title: "Rarity", key: "rarity" },
  { title: "Market Price", key: "market_price", align: "end" },
];

/**
 * Computed rows array with price data merged into each card object.
 *
 * The Vuetify data table expects a flat array of objects, but price data
 * arrives separately in pricesByCardId. This computed property merges them
 * so each row has a market_price field alongside the card fields.
 */
const rows = computed(() =>
  props.cards.map((card) => {
    const prices = props.pricesByCardId[card.id] ?? [];

    // Prefer the normal condition price; fall back to holofoil.
    // Most Base Set cards have one or the other but not always both.
    const snap =
      prices.find((p) => p.condition === "normal") ??
      prices.find((p) => p.condition === "holofoil") ??
      null;

    // Spread the card fields and add the resolved price.
    // market_price will be null if no snapshot was found.
    return {
      ...card,
      market_price: snap?.market_price ?? null,
    };
  })
);
</script>
