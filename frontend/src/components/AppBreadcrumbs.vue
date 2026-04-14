<template>
  <v-breadcrumbs v-if="crumbs.length" :items="crumbs" divider="›" class="pa-0">
    <template #item="{ item, index }">
      <v-breadcrumbs-item
        :to="item.to"
        :disabled="!item.to"
        :class="index === crumbs.length - 1 ? 'text-on-surface' : 'text-medium-emphasis'"
      >
        {{ item.title }}
      </v-breadcrumbs-item>
    </template>
  </v-breadcrumbs>
</template>

<script setup>
/**
 * AppBreadcrumbs component.
 *
 * Reads breadcrumb data from the current route's meta.breadcrumbs array and
 * renders a Vuetify v-breadcrumbs component. Accepts a dynamicCrumbs prop
 * that allows parent views to override specific breadcrumb titles with values
 * resolved at runtime (e.g. the loaded set name or card name).
 *
 * Props:
 *   dynamicCrumbs - Optional map of breadcrumb index to override title.
 *                   e.g. { 1: 'Base Set', 2: 'Charizard' }
 */
import { computed } from 'vue'
import { useRoute } from 'vue-router'

const props = defineProps({
  dynamicCrumbs: {
    type: Object,
    default: () => ({}),
  },
})

const route = useRoute()

const crumbs = computed(() => {
  const base = route.meta?.breadcrumbs ?? []
  return base.map((crumb, i) => ({
    ...crumb,
    title: props.dynamicCrumbs[i] ?? crumb.title,
  }))
})
</script>
