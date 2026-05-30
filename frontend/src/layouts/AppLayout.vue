<template>
  <v-app>
    <!-- Persistent left sidebar -->
    <v-navigation-drawer
      permanent
      :rail="appSidebarCollapsed"
      :rail-width="64"
      :width="240"
      color="surface"
    >
      <!-- Header row: chevron toggle + (when expanded) brand text -->
      <div class="sidebar-top d-flex align-center px-2 py-3">
        <v-btn
          :icon="appSidebarCollapsed ? 'mdi-chevron-right' : 'mdi-chevron-left'"
          variant="text"
          size="small"
          :title="appSidebarCollapsed ? 'Expand sidebar' : 'Collapse sidebar'"
          @click="toggleSidebar"
        />
        <div v-if="!appSidebarCollapsed" class="ml-2">
          <div class="text-subtitle-1 font-weight-bold">Card Market</div>
          <div class="text-caption text-medium-emphasis">
            Intelligence Dashboard
          </div>
        </div>
      </div>
      <v-divider />
      <v-list nav>
        <v-list-item
          v-for="item in navItems"
          :key="item.route"
          :to="item.disabled ? undefined : item.route"
          :prepend-icon="item.icon"
          :title="item.label"
          :disabled="item.disabled"
          active-color="primary"
          rounded="lg"
        />
      </v-list>
    </v-navigation-drawer>

    <!-- Top bar with breadcrumbs -->
    <v-app-bar flat color="surface" border="b">
      <v-app-bar-title>
        <AppBreadcrumbs :dynamic-crumbs="dynamicCrumbs" />
      </v-app-bar-title>
    </v-app-bar>

    <!-- Main scrollable content area -->
    <v-main>
      <v-container fluid class="pa-6">
        <slot />
      </v-container>
    </v-main>
  </v-app>
</template>

<script setup>
/**
 * AppLayout component.
 *
 * The persistent application shell. Every view is rendered inside this layout
 * via the default slot. It provides:
 *   - A fixed left sidebar with navigation links (collapsible to a 64px rail)
 *   - A top bar with breadcrumb navigation
 *   - A scrollable main content area
 *
 * The sidebar's collapsed state is a global UI preference (it should
 * apply to every page the user visits in this browser), so it
 * persists to localStorage rather than the URL. The dashboard's
 * filter / slicer panel collapse is dashboard-specific and uses URL
 * params instead -- two different mechanisms by design.
 */
import { onMounted, ref, inject } from 'vue'
import AppBreadcrumbs from '../components/AppBreadcrumbs.vue'

const STORAGE_KEY = 'appSidebarCollapsed'

const dynamicCrumbs = inject('dynamicCrumbs', { value: {} })

const appSidebarCollapsed = ref(false)

onMounted(() => {
  try {
    appSidebarCollapsed.value =
      window.localStorage.getItem(STORAGE_KEY) === 'true'
  } catch {
    // localStorage unavailable (private mode / disabled storage) --
    // silently fall back to the expanded default.
  }
})

function toggleSidebar() {
  appSidebarCollapsed.value = !appSidebarCollapsed.value
  try {
    window.localStorage.setItem(
      STORAGE_KEY,
      appSidebarCollapsed.value ? 'true' : 'false',
    )
  } catch {
    // Same fallback as above -- preference is per-tab if storage fails.
  }
}

const navItems = [
  { label: 'Sets', icon: 'mdi-cards', route: '/sets', disabled: false },
  { label: 'Market Trends', icon: 'mdi-chart-line', route: '/trends', disabled: false },
  { label: 'Analyze Your Collection', icon: 'mdi-book-search', route: '/collection', disabled: false },
]
</script>

<style scoped>
.sidebar-top {
  min-height: 56px;
}
</style>
