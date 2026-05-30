# M03_S07 — Cold Start Loading Experience

## Summary

Improve the first-load experience when the Render free tier service is waking up from a cold start. Instead of a blank screen or broken-looking spinner, show a full-screen Magikarp-themed loading screen with a Lottie animation while a health check confirms the API is alive. Once the API responds, transition into the app with skeleton loaders filling the content areas before real data arrives.

---

## New API Endpoint

### `GET /health`

A lightweight endpoint that returns immediately with no database interaction. Used exclusively by the frontend to detect when the API has woken up.

```python
@router.get("/health")
def health():
    return {"status": "ok"}
```

Add to `api/routers/` in a new file `health.py` and register it in `main.py`. This endpoint must not require a database connection — if it did, a cold database would block the health check defeating its purpose.

---

## Frontend Changes

### Overview of the loading flow

1. App mounts → immediately show the full-screen Magikarp loading screen
2. Frontend begins polling `GET /health` every 3 seconds
3. Health check succeeds → fade out the loading screen, fade in the app shell
4. App shell appears with skeleton loaders in content areas
5. Data loads → skeleton loaders replaced by real content

---

## Lottie Animation

**Library:** `lottie-web` via the `vue3-lottie` wrapper

Install:
```bash
npm install vue3-lottie lottie-web
```

Register globally in `main.js`:
```javascript
import Vue3Lottie from 'vue3-lottie'
app.use(Vue3Lottie)
```

**Animation source:** Use a free Magikarp or water/splash Lottie animation from [LottieFiles](https://lottiefiles.com). Search for `"fish"`, `"splash"`, `"water splash"`, or `"Magikarp"`. Download the `.json` file and place it at:

```
frontend/src/assets/animations/magikarp-splash.json
```

If no suitable animation is found on LottieFiles, fall back to a simple water ripple or splash animation — the exact animation matters less than having something visually engaging. The animation should loop while loading.

---

## New Component — `ColdStartLoader.vue`

**File:** `frontend/src/components/ColdStartLoader.vue`

A full-screen overlay component shown during the health check polling phase.

### Layout

Centered vertically and horizontally. Dark background matching the app theme (`#12121F`). Content stack from top to bottom:

1. **Lottie animation** — 200×200px, looping
2. **App name** — `"Card Market"` in large text, primary text color (`#F5EDD6`)
3. **Status message** — cycles through messages (see below), secondary text color (`#A0A0B8`), small font
4. **Progress dots** — three animated dots (`·  ·  ·`) pulsing in the primary accent color (`#E8412A`)

### Status messages

Cycle through these messages every 4 seconds while waiting. Use a `setInterval` that advances the index:

```javascript
const messages = [
  "Waking up the server...",
  "Magikarp is splashing around...",
  "This takes about 30 seconds on first load...",
  "Almost there...",
  "Hang tight, the server is warming up...",
]
```

### Transition

When the health check succeeds, emit a `loaded` event to the parent. The parent uses a Vue `<Transition>` with a fade effect to smoothly swap out `ColdStartLoader` and reveal the app shell.

```vue
<Transition name="fade">
  <ColdStartLoader v-if="isLoading" @loaded="isLoading = false" />
  <AppLayout v-else>
    <router-view />
  </AppLayout>
</Transition>
```

CSS for the fade transition:
```css
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.6s ease;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
```

---

## Health Check Polling Logic

Place the polling logic inside `ColdStartLoader.vue`. Start polling immediately on mount.

```javascript
const POLL_INTERVAL_MS = 3000
const API_BASE = import.meta.env.VITE_API_BASE_URL

onMounted(() => {
  const interval = setInterval(async () => {
    try {
      const response = await fetch(`${API_BASE}/health`, { method: 'GET' })
      if (response.ok) {
        clearInterval(interval)
        emit('loaded')
      }
    } catch {
      // API not ready yet — continue polling silently
    }
  }, POLL_INTERVAL_MS)

  // Safety valve — stop polling after 3 minutes and show an error state
  setTimeout(() => {
    clearInterval(interval)
    showError.value = true
  }, 180_000)
})
```

### Error state

If the API has not responded after 3 minutes, stop polling and replace the status message and dots with:

```
Unable to reach the server.
Please try refreshing the page.
```

In error color (`#CF6679`). The Lottie animation stops looping and freezes on its last frame.

---

## App.vue Integration

Update `App.vue` to orchestrate the loading flow:

```vue
<template>
  <Transition name="fade">
    <ColdStartLoader v-if="isLoading" @loaded="onLoaded" />
    <AppLayout v-else>
      <router-view />
    </AppLayout>
  </Transition>
</template>

<script setup>
import { ref } from 'vue'
import ColdStartLoader from '@/components/ColdStartLoader.vue'
import AppLayout from '@/layouts/AppLayout.vue'

const isLoading = ref(true)

function onLoaded() {
  isLoading.value = false
}
</script>
```

---

## Skeleton Loaders

The `LoadingSkeleton` component from M03_S03 is used in each view to show skeletons while data loads after the API wakes up. Verify these are in place on:

- `SetListView.vue` — skeleton cards while sets load
- `SetDetailView.vue` — skeleton for chart and table independently
- `CardDetailView.vue` — skeleton for card metadata and price table

No new skeleton work is needed if M03_S03 was implemented correctly — this story just confirms they are wired up and working as part of the overall loading flow.

---

## Test Cases

---

### TC01 — Health endpoint returns 200

**Steps:**
```bash
curl https://card-market-api.onrender.com/health
```

**Expected:**
```json
{"status": "ok"}
```
Response time should be under 500ms when the server is already warm. The endpoint should not make any database calls — verify by checking that no SQL queries appear in the logs when this endpoint is hit.

---

### TC02 — Loading screen appears on cold start

**Steps:**
1. In Render, manually suspend the API service or wait for it to spin down after 15 minutes of inactivity
2. Open the frontend URL in a browser

**Expected:** The full-screen loading overlay appears immediately — dark background, Lottie animation playing, app name visible, status message cycling. The app shell (sidebar, content) is not visible behind it.

---

### TC03 — Status messages cycle

**Steps:** Watch the loading screen for at least 20 seconds.

**Expected:** The status message changes approximately every 4 seconds, cycling through the defined messages. The dots pulse continuously.

---

### TC04 — Loading screen fades out when API responds

**Steps:** Watch the loading screen until the API wakes up.

**Expected:** The loading screen fades out smoothly (approximately 0.6 seconds) and the app shell fades in. No flash of white or unstyled content. No page reload.

---

### TC05 — App shell shows skeleton loaders after cold start fade

**Steps:** Watch what appears immediately after the loading screen fades.

**Expected:** The app shell (sidebar, breadcrumbs) is visible. Content areas show skeleton loaders rather than blank areas. Within a few seconds the skeletons are replaced by real data.

---

### TC06 — No loading screen on warm start

**Steps:**
1. Load the app once (warming up the server)
2. Refresh the page while the server is still warm

**Expected:** The loading screen does not appear. The app shell and skeleton loaders appear immediately and data loads within 1-2 seconds.

---

### TC07 — Error state appears after 3 minute timeout

**Steps:** This is difficult to test in production. To simulate:
1. Temporarily change `VITE_API_BASE_URL` to an invalid URL in a local `.env` file
2. Run the frontend locally
3. Wait 3 minutes

**Expected:** After 3 minutes the status message and progress dots are replaced by the error message in red: `"Unable to reach the server. Please try refreshing the page."` The animation stops. No further polling occurs.

**Restore:** Revert `VITE_API_BASE_URL` to the correct value after testing.

---

### TC08 — Lottie animation plays and loops

**Steps:** Watch the loading screen during a cold start.

**Expected:** The animation plays smoothly and loops continuously until the loading screen fades out. No broken image or empty animation area appears.

---

### TC09 — Health endpoint is in Swagger docs

**Steps:** Open `https://card-market-api.onrender.com/docs`

**Expected:** The `/health` endpoint appears in the Swagger UI and can be executed from the docs page.

---

### TC10 — Loading screen matches app theme

**Steps:** Compare the loading screen to the rest of the app.

**Expected:** Background color matches the app background (`#12121F`). Primary text color matches (`#F5EDD6`). Progress dots use the primary accent color (`#E8412A`). The loading screen feels like part of the app rather than a generic spinner.
