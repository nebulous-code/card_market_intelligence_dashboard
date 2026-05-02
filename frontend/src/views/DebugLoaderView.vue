<template>
  <!--
    Debug harness for the cold-start loader. Mounts ColdStartLoader in
    debug mode (no /health polling, no 3-minute error timeout) so the
    animation and error state can be iterated on without lagging the
    API server. Reachable via /debug/loader -- not linked from the nav.
  -->
  <div class="debug-shell">
    <div class="control-panel">
      <h2 class="text-h6 mb-2">Loader Debug</h2>
      <p class="text-caption text-medium-emphasis mb-4">
        ColdStartLoader is mounted with polling disabled. Toggle states below
        to preview the animation and error UI.
      </p>

      <div class="d-flex flex-column" style="gap: 8px;">
        <v-btn
          :color="loaderVisible ? 'secondary' : 'primary'"
          @click="loaderVisible = !loaderVisible"
        >
          {{ loaderVisible ? "Hide loader" : "Show loader" }}
        </v-btn>

        <v-btn
          :disabled="!loaderVisible"
          :color="forceError ? 'error' : undefined"
          @click="forceError = !forceError"
        >
          {{ forceError ? "Clear error state" : "Force error state" }}
        </v-btn>

        <v-btn variant="text" @click="reload">Reload page</v-btn>
      </div>

      <v-divider class="my-4" />

      <div class="text-caption text-medium-emphasis">
        State:
        <ul class="mt-1">
          <li>visible: {{ loaderVisible }}</li>
          <li>forceError: {{ forceError }}</li>
        </ul>
      </div>
    </div>

    <ColdStartLoader
      v-if="loaderVisible"
      debug
      :force-error="forceError"
    />
  </div>
</template>

<script setup>
/**
 * Debug harness route for ColdStartLoader.
 *
 * Renders the loader in `debug` mode so polling and the 3-minute timeout
 * are suppressed -- the animation runs indefinitely. Buttons toggle visibility
 * and the error state so the designer / reviewer can preview both UIs without
 * having to take down the API server.
 */
import { ref } from "vue";
import ColdStartLoader from "../components/ColdStartLoader.vue";

const loaderVisible = ref(true);
const forceError = ref(false);

function reload() {
  window.location.reload();
}
</script>

<style scoped>
.debug-shell {
  /* Sit beneath the loader. Visible only when loaderVisible is false, but
     always rendered so toggling back on is instant. */
  padding: 16px;
}
.control-panel {
  position: relative;
  z-index: 1; /* below the loader's z-index of 9999 */
  max-width: 360px;
}
</style>
