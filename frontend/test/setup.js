/**
 * Global test setup.
 *
 * Runs before each test file in the suite. Use this for cross-cutting
 * concerns: stubbing browser APIs jsdom doesn't ship with, providing
 * import.meta.env defaults, etc.
 *
 * Today this file is intentionally minimal -- the api/ tests mock axios
 * directly, and utils/ tests don't touch the DOM. Add helpers here as
 * the suite grows (e.g. when component tests start arriving).
 */

// import.meta.env.VITE_API_BASE_URL is read at module load by api/index.js.
// In jsdom it's undefined by default which makes the axios baseURL fall
// through to the localhost fallback -- fine for tests, no setup needed.
