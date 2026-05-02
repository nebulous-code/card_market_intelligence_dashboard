/**
 * Vitest configuration.
 *
 * Reuses the existing vite.config.js plugin set so test code resolves the
 * same way the app does (Vue SFCs, Vuetify auto-import, etc.). The only
 * extra wiring is here:
 *
 *   - environment: "jsdom"   so component tests can mount and query DOM
 *   - setupFiles              global mocks shared across tests
 *   - coverage                100% gate on src/utils and src/api only;
 *                             everything else is excluded from measurement
 *                             (we trust Vuetify -- see project test plan)
 */

import { mergeConfig, defineConfig } from "vite";
import viteConfig from "./vite.config.js";

export default mergeConfig(
  viteConfig,
  defineConfig({
    test: {
      environment: "jsdom",
      globals: true,
      setupFiles: ["./test/setup.js"],
      include: ["test/**/*.{test,spec}.{js,ts}"],

      coverage: {
        provider: "v8",
        reporter: ["text", "html"],

        // Only utils/ and api/ are gated. Components/views are intentionally
        // out of scope: we trust Vuetify and the chart libraries, and
        // 100%-covering Vue SFCs forces a lot of test scaffolding for
        // marginal value.
        include: ["src/utils/**/*.js", "src/api/**/*.js"],
        thresholds: {
          lines: 100,
          functions: 100,
          branches: 100,
          statements: 100,
        },
      },
    },
  }),
);
