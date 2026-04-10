/**
 * Vite build tool configuration for the Vue frontend.
 *
 * Vite is the tool that serves the frontend during development and bundles
 * it for production. This file controls where it looks for environment
 * variables, which plugins it uses, and how the development server behaves.
 */

import vue from "@vitejs/plugin-vue";
import { defineConfig } from "vite";
import vuetify from "vite-plugin-vuetify";

export default defineConfig({
  // Load environment variables (VITE_* prefixed) from the project root
  // rather than the frontend/ directory. This allows a single .env file
  // at the root to serve all three services: api, ingestion, and frontend.
  envDir: "..",

  plugins: [
    // Enables Vue single-file component support (.vue files).
    vue(),

    // Integrates Vuetify with Vite. autoImport: true means Vuetify components
    // are automatically imported on demand, so only the components actually
    // used in the app are included in the final bundle (tree-shaking).
    vuetify({ autoImport: true }),
  ],

  server: {
    // Bind to 127.0.0.1 (localhost only) rather than 0.0.0.0 (all network
    // interfaces). Binding to 0.0.0.0 triggers a Windows firewall permission
    // prompt. Since this is a local development server that does not need to
    // be accessible from other machines on the network, localhost is correct.
    host: "127.0.0.1",

    port: 5173,

    // Proxy requests to /api through to the backend API server.
    // This means a request from the frontend to /api/sets is forwarded to
    // http://localhost:8000/api/sets, which avoids cross-origin request
    // issues during development. Note: the API routes do not currently use
    // an /api prefix, so this proxy is a placeholder for future use.
    proxy: {
      "/api": "http://localhost:8000",
    },
  },
});
