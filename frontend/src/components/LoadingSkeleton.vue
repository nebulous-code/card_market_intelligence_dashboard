<template>
  <v-skeleton-loader v-if="loading" :type="type" />
  <slot v-else />
</template>

<script setup>
/**
 * LoadingSkeleton component.
 *
 * A thin wrapper around v-skeleton-loader that provides consistent loading
 * states across the app. When loading=true the skeleton is shown; when
 * false the default slot content is rendered.
 *
 * Usage:
 *   <LoadingSkeleton :loading="isLoading" type="table">
 *     <CardTable :cards="cards" />
 *   </LoadingSkeleton>
 */
defineProps({
  loading: { type: Boolean, default: true },
  type: { type: String, default: 'table' },
})
</script>
