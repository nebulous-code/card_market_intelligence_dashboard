import vue from "@vitejs/plugin-vue";
import { defineConfig } from "vite";
import vuetify from "vite-plugin-vuetify";

export default defineConfig({
  envDir: "..", // Load .env from the project root
  plugins: [
    vue(),
    // Treeshakes Vuetify components automatically.
    vuetify({ autoImport: true }),
  ],
  server: {
    host: "127.0.0.1",
    port: 5173,
    proxy: {
      "/api": "http://localhost:8000",
    },
  },
});
