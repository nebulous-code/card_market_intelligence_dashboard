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
 * renders a Vuetify v-breadcrumbs component. Injects dynamicCrumbs from
 * App.vue so views can override titles and links at runtime without prop
 * drilling. Each dynamicCrumbs entry is { title, to? } or just a string.
 */
import { computed, inject } from 'vue'
import { useRoute } from 'vue-router'

const dynamicCrumbs = inject('dynamicCrumbs', { value: {} })

const route = useRoute()

const crumbs = computed(() => {
  const base = route.meta?.breadcrumbs ?? []
  return base.map((crumb, i) => {
    const override = dynamicCrumbs.value?.[i]
    if (!override) return crumb
    if (typeof override === 'string') return { ...crumb, title: override }
    return { ...crumb, ...override }
  })
})
</script>
