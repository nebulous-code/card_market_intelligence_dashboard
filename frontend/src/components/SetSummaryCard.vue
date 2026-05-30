<template>
  <!-- Only render the card if set data has been passed in. -->
  <v-card v-if="set" class="mb-6">
    <v-card-text>
      <v-row align="center">

        <!-- Set logo image. Only rendered if a logo URL is available. -->
        <v-col cols="auto">
          <v-img
            v-if="set.logo_url"
            :src="set.logo_url"
            :alt="set.name"
            max-height="60"
            max-width="160"
            contain
          />
        </v-col>

        <!-- Set name and series. -->
        <v-col>
          <div class="text-h5 font-weight-bold">{{ set.name }}</div>
          <div class="text-subtitle-1 text-medium-emphasis">{{ set.series }}</div>
        </v-col>

        <!-- Total card count. -->
        <v-col cols="auto" class="text-right">
          <div class="text-body-2 text-medium-emphasis">Cards</div>
          <div class="text-h6">{{ formatNumber(set.printed_total) }}</div>
        </v-col>

        <!-- Release date, formatted for readability. -->
        <v-col cols="auto" class="text-right">
          <div class="text-body-2 text-medium-emphasis">Released</div>
          <div class="text-h6">{{ formatDate(set.release_date) }}</div>
        </v-col>

      </v-row>
    </v-card-text>
  </v-card>
</template>

<script setup>
/**
 * SetSummaryCard component.
 *
 * Displays a summary banner for the currently selected Pokemon card set.
 * Shows the set logo, name, series, total card count, and release date.
 *
 * Props:
 *   set - The set object from the API. Can be null while data is loading,
 *         in which case nothing is rendered.
 */

import { formatDate, formatNumber } from "../utils/formatters.js";

const props = defineProps({
  /**
   * The set object to display. Expected to have: name, series,
   * printed_total, release_date, and optionally logo_url.
   */
  set: {
    type: Object,
    default: null,
  },
});
</script>
