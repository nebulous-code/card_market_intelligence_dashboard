<template>
  <v-alert type="error" variant="tonal" :icon="icon">
    <div class="text-subtitle-1 font-weight-bold">{{ title }}</div>
    <div v-if="message" class="text-body-2 mt-1">{{ message }}</div>
    <v-btn
      v-if="retryLabel"
      class="mt-3"
      color="error"
      variant="tonal"
      size="small"
      @click="$emit('retry')"
    >
      {{ retryLabel }}
    </v-btn>
  </v-alert>
</template>

<script setup>
/**
 * ErrorState component.
 *
 * The sibling of EmptyState, for when a request failed rather than
 * returned nothing. Keeping the two distinct matters: several views
 * used to render "No sets found" when the API was unreachable, which
 * tells the user their data is empty when in fact we never got an
 * answer.
 *
 * Rendered as a v-alert because that was already the copy-pasted
 * treatment in four views -- this consolidates them rather than
 * introducing another style.
 *
 * Takes strings and emits an event; it holds no logic of its own,
 * because components sit outside the coverage allow-list and untested
 * branching is worth avoiding there. Message text comes from
 * utils/errorMessage.js, which is tested.
 */
defineProps({
  title: { type: String, default: 'Something went wrong' },
  message: { type: String, default: '' },
  icon: { type: String, default: 'mdi-alert-circle-outline' },
  // A button appears only when a label is given, so a caller with
  // nothing useful to retry simply omits it.
  retryLabel: { type: String, default: '' },
})

defineEmits(['retry'])
</script>
