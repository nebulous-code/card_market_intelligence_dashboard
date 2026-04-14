<template>
  <v-app>
    <!-- Persistent left sidebar -->
    <v-navigation-drawer permanent width="240" color="surface">
      <v-list-item
        title="Card Market"
        subtitle="Intelligence Dashboard"
        prepend-icon="mdi-cards"
        class="py-4"
      />
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
 *   - A fixed left sidebar with navigation links
 *   - A top bar with breadcrumb navigation
 *   - A scrollable main content area
 *
 * Props:
 *   dynamicCrumbs - Passed through to AppBreadcrumbs so individual views can
 *                   override breadcrumb titles with runtime-loaded names.
 */
import AppBreadcrumbs from '../components/AppBreadcrumbs.vue'

defineProps({
  dynamicCrumbs: {
    type: Object,
    default: () => ({}),
  },
})

const navItems = [
  { label: 'Sets', icon: 'mdi-cards', route: '/sets', disabled: false },
  { label: 'Market Trends', icon: 'mdi-chart-line', route: '/trends', disabled: true },
]
</script>
