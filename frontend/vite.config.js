import vue from "@vitejs/plugin-vue";
import { defineConfig } from "vite";
import vuetify from "vite-plugin-vuetify";

export default defineConfig({
  plugins: [
    vue(),
    // Treeshakes Vuetify components automatically.
    vuetify({ autoImport: true }),
  ],
  server: {
    host: "0.0.0.0", // Required for Docker to expose the port.
    port: 5173,
    proxy: {
      "/api": "http://localhost:8000",
    },
  },
});
