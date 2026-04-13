/**
 * Frontend application entry point.
 *
 * This file boots the Vue application. It imports the root component,
 * sets up the two main libraries (Vuetify for UI components and Vue Router
 * for page navigation), and mounts everything onto the HTML page.
 *
 * The "mount" step is what makes the application visible in the browser.
 * It replaces the empty <div id="app"> in index.html with the full
 * rendered application.
 */

// Import the Material Design Icons font. This gives access to the icon set
// used throughout the UI (e.g. mdi-cards, mdi-magnify).
import "@mdi/font/css/materialdesignicons.css";

// Import Vuetify's base stylesheet. This must be imported before any
// Vuetify components are used.
import "vuetify/styles";

import { createApp } from "vue";
import { createVuetify } from "vuetify";

import App from "./App.vue";
import router from "./router/index.js";

// Configure the Vuetify UI component library.
// Vuetify provides ready-made components like buttons, tables, cards, and
// form inputs that follow Material Design guidelines.
const vuetify = createVuetify({
  theme: {
    defaultTheme: "light",
  },
  icons: {
    // Use the Material Design Icons set imported above.
    defaultSet: "mdi",
  },
});

// Create the Vue application, register the plugins, and mount it.
// .use(router)  -- enables navigation between pages
// .use(vuetify) -- enables all Vuetify UI components
// .mount("#app") -- attaches the app to the <div id="app"> in index.html
createApp(App).use(router).use(vuetify).mount("#app");
