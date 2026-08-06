<template>
  <div>
    <div class="text-h4 font-weight-bold mb-4">Page not found</div>
    <EmptyState
      icon="mdi-map-marker-question-outline"
      title="There's nothing at this address"
      message="The page may have moved, or the link may be mistyped."
    />
    <div class="mt-4 d-flex ga-2 justify-center">
      <v-btn color="primary" to="/sets">Browse sets</v-btn>
      <v-btn variant="tonal" to="/collection">Analyze your collection</v-btn>
    </div>
  </div>
</template>

<script setup>
/**
 * Catch-all view for unmatched routes.
 *
 * The deployment rewrites every path to index.html so client-side
 * routing survives a refresh (see render.yaml). Without a catch-all
 * route that rewrite means a typo'd URL renders the nav bar and an
 * empty body -- the app looks broken rather than saying the address is
 * wrong.
 *
 * Offers two ways onward rather than just a back link, since someone
 * arriving from a stale external link has no history to go back to.
 */
import EmptyState from '../components/EmptyState.vue'
</script>
