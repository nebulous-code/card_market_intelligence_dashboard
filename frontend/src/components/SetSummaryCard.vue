<template>
  <v-card v-if="set" class="mb-6">
    <v-card-text>
      <v-row align="center">
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
        <v-col>
          <div class="text-h5 font-weight-bold">{{ set.name }}</div>
          <div class="text-subtitle-1 text-medium-emphasis">{{ set.series }}</div>
        </v-col>
        <v-col cols="auto" class="text-right">
          <div class="text-body-2 text-medium-emphasis">Cards</div>
          <div class="text-h6">{{ set.printed_total }}</div>
        </v-col>
        <v-col cols="auto" class="text-right">
          <div class="text-body-2 text-medium-emphasis">Released</div>
          <div class="text-h6">{{ formatDate(set.release_date) }}</div>
        </v-col>
      </v-row>
    </v-card-text>
  </v-card>
</template>

<script setup>
const props = defineProps({
  set: {
    type: Object,
    default: null,
  },
});

function formatDate(dateStr) {
  if (!dateStr) return "—";
  return new Date(dateStr).toLocaleDateString("en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}
</script>
