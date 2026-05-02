<template>
  <!--
    Full-screen overlay shown while the API is waking up from a Render cold
    start. Position-fixed at z-index 9999 so it sits over the AppLayout that
    is mounted underneath. When /health responds the parent fades it out via
    a Vue <Transition>, which is why this component does not animate its own
    opacity on unmount.
  -->
  <div class="cold-start-overlay" :class="{ 'is-error': showError }">
    <div class="splash-stack">
      <Vue3Lottie
        ref="lottieRef"
        class="splash-anim"
        :animation-data="animationData"
        :height="200"
        :width="200"
        :loop="true"
        :autoplay="true"
      />

      <h1 class="app-name">Card Market</h1>

      <p v-if="!showError" class="status-message">
        {{ messages[messageIndex] }}
      </p>
      <p v-else class="error-message">
        Unable to reach the server.<br />
        Please try refreshing the page.
      </p>

      <div v-if="!showError" class="dots" aria-hidden="true">
        <span class="dot dot-1">·</span>
        <span class="dot dot-2">·</span>
        <span class="dot dot-3">·</span>
      </div>
    </div>
  </div>
</template>

<script setup>
/**
 * ColdStartLoader.
 *
 * Renders a themed full-screen loading overlay while the API is being woken
 * up from a Render free-tier cold start. Polls GET /health every 3 seconds;
 * emits 'loaded' on the first successful response. After 3 minutes without
 * a response the component switches to an error state and stops polling.
 *
 * The component owns:
 *   - polling interval (3s)
 *   - status-message rotation interval (4s)
 *   - error-state timeout (3min)
 *
 * All three are cleared on unmount.
 *
 * Emits:
 *   loaded — fired once when /health returns a 2xx response.
 */

import { onMounted, onUnmounted, ref, watch } from "vue";
import { Vue3Lottie } from "vue3-lottie";
import animationData from "../assets/animations/fish-loader.json";
import { getHealth } from "../api/index.js";

const props = defineProps({
  /**
   * When true, suppress the /health polling and the 3-minute error timeout.
   * The loader simply renders its visual state. Used by the /debug/loader
   * page so the animation and error state can be inspected without needing
   * to lag the API server.
   */
  debug: {
    type: Boolean,
    default: false,
  },
  /**
   * When true, render the error state immediately. Useful for debug, and for
   * the parent to short-circuit into the error UI without waiting 3 minutes.
   */
  forceError: {
    type: Boolean,
    default: false,
  },
});

const emit = defineEmits(["loaded"]);

const POLL_INTERVAL_MS = 3000;
const MESSAGE_INTERVAL_MS = 4000;
const ERROR_TIMEOUT_MS = 180_000; // 3 minutes

const messages = [
  "Waking up the server...",
  "Magikarp is splashing around...",
  "This takes about 30 seconds on first load...",
  "Almost there...",
  "Hang tight, the server is warming up...",
];

const messageIndex = ref(0);
const showError = ref(false);
const lottieRef = ref(null);

let pollInterval = null;
let messageInterval = null;
let errorTimeout = null;

function stopAllTimers() {
  if (pollInterval) {
    clearInterval(pollInterval);
    pollInterval = null;
  }
  if (messageInterval) {
    clearInterval(messageInterval);
    messageInterval = null;
  }
  if (errorTimeout) {
    clearTimeout(errorTimeout);
    errorTimeout = null;
  }
}

async function pollOnce() {
  try {
    await getHealth();
    stopAllTimers();
    emit("loaded");
  } catch {
    // API not ready yet — keep polling silently.
  }
}

// Pause Lottie playback when entering the error state so it visually freezes
// on its current frame, matching the spec's "animation stops" behavior.
function applyErrorPlayback(isError) {
  const inst = lottieRef.value;
  if (!inst) return;
  if (isError && typeof inst.pause === "function") inst.pause();
  if (!isError && typeof inst.play === "function") inst.play();
}

// Mirror the forceError prop into the local error state so the UI updates
// reactively when the debug page toggles it. Also stop the message rotation
// once we're in error state (it has no use beyond that point) and pause
// the Lottie animation.
watch(
  () => props.forceError,
  (val) => {
    showError.value = val;
    if (val && messageInterval) {
      clearInterval(messageInterval);
      messageInterval = null;
    }
    applyErrorPlayback(val);
  },
  { immediate: true }
);

watch(showError, applyErrorPlayback);

onMounted(() => {
  // Always rotate status messages so the loader doesn't look frozen, even
  // in debug mode. Stops once the error state is reached.
  messageInterval = setInterval(() => {
    if (showError.value) return;
    messageIndex.value = (messageIndex.value + 1) % messages.length;
  }, MESSAGE_INTERVAL_MS);

  // Skip polling and the error timeout when running in debug mode -- the
  // /debug/loader page wants to see the animation indefinitely.
  if (props.debug) return;

  // Fire one probe immediately so we don't wait the full interval before the
  // first attempt. (App.vue already did one, but the API may have woken up
  // between then and now, so probing again is fine and cheap.)
  pollOnce();
  pollInterval = setInterval(pollOnce, POLL_INTERVAL_MS);

  errorTimeout = setTimeout(() => {
    showError.value = true;
    if (pollInterval) {
      clearInterval(pollInterval);
      pollInterval = null;
    }
    if (messageInterval) {
      clearInterval(messageInterval);
      messageInterval = null;
    }
  }, ERROR_TIMEOUT_MS);
});

onUnmounted(stopAllTimers);
</script>

<style scoped>
.cold-start-overlay {
  position: fixed;
  inset: 0;
  z-index: 9999;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #12121f;
  color: #f5edd6;
}

.splash-stack {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 16px;
}

.splash-anim {
  /* vue3-lottie injects its own wrapper; keep its sizing predictable. */
  pointer-events: none;
}

.app-name {
  font-size: 32px;
  font-weight: 600;
  letter-spacing: 0.02em;
  color: #f5edd6;
  margin: 0;
}

.status-message {
  font-size: 14px;
  color: #a0a0b8;
  margin: 0;
  min-height: 1.2em;
}

.error-message {
  font-size: 14px;
  color: #cf6679;
  text-align: center;
  margin: 0;
  line-height: 1.4;
}

.dots {
  display: flex;
  gap: 6px;
  font-size: 32px;
  line-height: 0.5;
  color: #e8412a;
}
.dot {
  animation: dot-pulse 1.2s ease-in-out infinite;
}
.dot-2 { animation-delay: 0.2s; }
.dot-3 { animation-delay: 0.4s; }
@keyframes dot-pulse {
  0%, 100% { opacity: 0.3; transform: translateY(0); }
  50%      { opacity: 1;   transform: translateY(-4px); }
}
</style>
