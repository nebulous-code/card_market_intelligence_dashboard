<template>
  <AppLayout>
    <router-view />
  </AppLayout>

  <!--
    Cold-start loader. Mounted on top of AppLayout (z-index 9999) only when
    the silent /health probe in onMounted didn't return in time. Vue's
    <Transition> handles the fade-out when the API responds.
  -->
  <Transition name="fade">
    <ColdStartLoader v-if="showLoader" @loaded="onLoaded" />
  </Transition>
</template>

<script setup>
import { onMounted, provide, ref } from 'vue'
import AppLayout from './layouts/AppLayout.vue'
import ColdStartLoader from './components/ColdStartLoader.vue'
import { getHealth } from './api/index.js'

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

// --- Cold-start loader orchestration ---
//
// Render's free tier spins the API down after ~15 minutes of inactivity. We
// fire a single /health probe with an 800ms cap. If it succeeds in time the
// loader never paints (warm refresh). If it doesn't, we surface ColdStartLoader
// which polls every 3s and emits 'loaded' once /health responds; the overlay
// then fades and the underlying AppLayout is already mounted so the in-view
// skeletons handle the data-arriving phase.
const GRACE_MS = 800
const showLoader = ref(false)

function onLoaded() {
  showLoader.value = false
}

onMounted(async () => {
  try {
    await Promise.race([
      getHealth(),
      new Promise((_, reject) =>
        setTimeout(() => reject(new Error('grace-period-elapsed')), GRACE_MS)
      ),
    ])
    // Resolved in time → warm start, leave the loader hidden.
  } catch {
    showLoader.value = true
  }
})
</script>

<style>
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.6s ease;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
