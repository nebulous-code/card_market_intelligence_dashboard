<template>
  <AppLayout>
    <router-view />
  </AppLayout>
</template>

<script setup>
import { provide, ref } from 'vue'
import AppLayout from './layouts/AppLayout.vue'

// Reactive map that any view can write to override breadcrumb titles.
// Keyed by breadcrumb index. e.g. { 1: 'Base Set', 2: 'Charizard 4/102' }
// Views inject 'dynamicCrumbs' and call setCrumb(index, title) to set values.
// AppLayout injects 'dynamicCrumbs' and passes it to AppBreadcrumbs.
const dynamicCrumbs = ref({})

provide('dynamicCrumbs', dynamicCrumbs)
provide('setCrumb', (index, title, to) => {
  dynamicCrumbs.value = { ...dynamicCrumbs.value, [index]: { title, to } }
})
provide('clearCrumbs', () => {
  dynamicCrumbs.value = {}
})
</script>
