<template>
  <v-card color="surface" variant="tonal" class="pa-8 text-center">
    <v-icon :icon="icon" size="64" color="secondary-text" class="mb-4" />
    <div class="text-h6 font-weight-bold mb-2">{{ title }}</div>
    <div v-if="message" class="text-body-2 text-medium-emphasis">{{ message }}</div>
  </v-card>
</template>

<script setup>
/**
 * EmptyState component.
 *
 * Shown when a table, chart, or content area has no data to display.
 * Replaces blank areas with a consistent icon + message treatment.
 */
defineProps({
  icon: { type: String, default: 'mdi-magnify-off' },
  title: { type: String, default: 'No data found' },
  message: { type: String, default: '' },
})
</script>
