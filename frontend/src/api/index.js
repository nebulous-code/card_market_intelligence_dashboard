/**
 * API service layer.
 *
 * This module is the only place in the frontend that makes HTTP requests.
 * Components never import Axios directly -- they call the functions
 * exported from this file instead. This keeps all API communication
 * in one place so that if the base URL, headers, or error handling
 * ever need to change, there is only one file to update.
 *
 * The base URL is read from the VITE_API_BASE_URL environment variable
 * defined in the .env file at the project root. If the variable is not
 * set, it falls back to http://localhost:8000.
 */

import axios from "axios";

// Create a pre-configured Axios instance with the API base URL and a
// 15-second timeout. All requests made through this instance will
// automatically include the base URL as a prefix, so functions only
// need to specify the path (e.g. "/sets" instead of the full URL).
//
// Both arms of the `??` are exercised by the test suite (with and
// without VITE_API_BASE_URL), but v8 coverage cannot merge branch hits
// across the dynamic re-import the second case requires. The directive
// below opts the line out of branch counting; line coverage is still
// enforced.
/* c8 ignore next */
const baseURL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

const http = axios.create({
  baseURL,
  timeout: 15000,
  // Required so the browser sends and stores the HttpOnly session cookie
  // returned by /collection/upload. Without this every request to a
  // cross-origin API would silently strip the cookie.
  withCredentials: true,
});

/**
 * Fetch all sets stored in the database.
 *
 * Used by the Dashboard to populate the set selector dropdown. Sets are
 * returned in descending release date order (newest first) by the API.
 *
 * @returns {Promise<Array>} Array of set objects.
 */
export async function getSets() {
  const { data } = await http.get("/sets");
  return data;
}

/**
 * Fetch a single set by its TCGdex ID.
 *
 * @param {string} setId - The TCGdex set identifier (e.g. "base1").
 * @returns {Promise<Object>} The set object.
 */
export async function getSet(setId) {
  const { data } = await http.get(`/sets/${setId}`);
  return data;
}

/**
 * Fetch all cards belonging to a given set.
 *
 * Cards are returned ordered by card number within the set. This data
 * is used to populate the CardTable and PriceChart components.
 *
 * @param {string} setId - The TCGdex set identifier (e.g. "base1").
 * @returns {Promise<Array>} Array of card objects for the set.
 */
export async function getCardsForSet(setId) {
  const { data } = await http.get(`/sets/${setId}/cards`);
  return data;
}

/**
 * Fetch a single card with its latest price snapshots.
 *
 * Returns the card's metadata along with the most recent price for each
 * available condition (normal, holofoil, reverseHolofoil). Used by the
 * Dashboard to populate the price chart and card table price column.
 *
 * @param {string} cardId - The TCGdex card identifier (e.g. "base1-4").
 * @returns {Promise<Object>} The card object with a latest_prices array.
 */
export async function getCard(cardId) {
  const { data } = await http.get(`/cards/${cardId}`);
  return data;
}

/**
 * Fetch the latest prices for all cards in a set in a single request.
 *
 * Returns a map of card ID to that card's latest price snapshots. Used by
 * the Dashboard instead of calling getCard() once per card, which would
 * fire 100+ parallel requests and exhaust the database connection pool.
 *
 * @param {string} setId - The TCGdex set identifier (e.g. "base1").
 * @returns {Promise<Object>} Object with a prices map: { [cardId]: snapshot[] }
 */
export async function getSetCardPrices(setId) {
  const { data } = await http.get(`/sets/${setId}/cards/prices`);
  return data.prices;
}

/**
 * Fetch the full price history for a single card.
 *
 * Returns all price snapshots for the card in chronological order (oldest
 * first), ready to pass directly to a chart. Optionally filtered by source
 * and/or condition to reduce the response to a single chart series.
 *
 * @param {string} cardId - The TCGdex card identifier (e.g. "base1-4").
 * @param {Object} [filters={}] - Optional filters.
 * @param {string} [filters.source] - Price source to filter by (e.g. "tcgplayer", "psa").
 * @param {string} [filters.condition] - Condition to filter by (e.g. "NM", "PSA-10").
 * @returns {Promise<Object>} Object with card_id and snapshots array.
 */
export async function getPriceHistory(cardId, filters = {}) {
  const { data } = await http.get(`/cards/${cardId}/price-history`, { params: filters });
  return data;
}

/**
 * Fetch the canonical condition list (NM, LP, ..., PSA-10, ...) with display
 * labels and sort order. Used to populate filter dropdowns without hardcoding
 * the labels in the frontend.
 *
 * @returns {Promise<Array<{value: string, label: string, display_order: number}>>}
 */
export async function getReferenceConditions() {
  const { data } = await http.get("/reference/conditions");
  return data;
}

/**
 * Fetch the canonical variant list (Standard, Holofoil, 1st Ed. Holo, ...).
 * The Standard row has value=null.
 *
 * @returns {Promise<Array<{value: string|null, label: string, display_order: number}>>}
 */
export async function getReferenceVariants() {
  const { data } = await http.get("/reference/variants");
  return data;
}

/**
 * Fetch the canonical rarity list (hyper_rare, ..., common) with display
 * labels and sort order. Ordered rarest-first.
 *
 * @returns {Promise<Array<{value: string, label: string, display_order: number}>>}
 */
export async function getReferenceRarities() {
  const { data } = await http.get("/reference/rarities");
  return data;
}

/**
 * Fetch the list of sets that have at least one row in condition_multipliers.
 * Used by the Market Trends → Condition Multipliers heatmap to populate the
 * set selector chips. Sets with no multiplier data are omitted.
 *
 * @returns {Promise<{sets: Array<{set_id: string, set_display_name: string}>}>}
 */
export async function getSetsWithMultipliers() {
  const { data } = await http.get("/trends/sets-with-multipliers");
  return data;
}

/**
 * Fetch the condition multiplier matrix for one set, grouped by either rarity
 * or supertype. Each grouping carries all 10 forward condition transitions
 * that have data; transitions with no data are simply absent from the array.
 *
 * @param {string} setId - The canonical set ID (e.g. "base1").
 * @param {"rarity" | "supertype"} groupingType - Which `cards.*` column to bucket by.
 * @returns {Promise<Object>} ConditionMultiplierResponse.
 */
export async function getConditionMultipliers(setId, groupingType) {
  const { data } = await http.get("/trends/condition-multipliers", {
    params: { set_id: setId, grouping_type: groupingType },
  });
  return data;
}

/**
 * Lightweight liveness probe. Hits /wake, which is intentionally DB-free
 * so a cold database does not block detection. Used by the cold-start loader
 * to know when the API service has woken up.
 *
 * The path is /wake (not /health) because ad-blocker filter lists routinely
 * block well-known liveness paths on shared hosts -- uBlock Origin's default
 * lists block /health on *.onrender.com, which made cold-start detection
 * fail silently for users with ad blockers.
 *
 * @returns {Promise<{status: string}>}
 */
export async function getHealth() {
  const { data } = await http.get("/wake");
  return data;
}

/**
 * Download the upload template as a Blob suitable for triggering a save
 * dialog via a temporary anchor click. The filename is set by the server
 * via Content-Disposition; callers can fall back to a generic name.
 *
 * @returns {Promise<Blob>}
 */
export async function downloadCollectionTemplate() {
  const response = await http.get("/collection/template", { responseType: "blob" });
  return response.data;
}

/**
 * Download the active session's collection as a populated workbook. The
 * server fills the four agent-populated tables in the template with the
 * user's data and streams the result. Throws on 404 if no session is
 * active so the caller can surface a "load a collection first" toast.
 *
 * @returns {Promise<Blob>}
 */
export async function downloadCollectionExcel() {
  const response = await http.get("/collection/excel", { responseType: "blob" });
  return response.data;
}

/**
 * Upload a filled-out collection workbook. On success the API sets a
 * session cookie and returns a summary; the caller redirects to the
 * collection dashboard. On row-level validation failure axios throws
 * with a 422 -- callers should inspect ``error.response.data.detail``
 * for the structured ``UploadValidationFailure`` payload.
 *
 * @param {File} file
 * @returns {Promise<{session_id: string, card_count: number, set_count: number}>}
 */
export async function uploadCollection(file) {
  const form = new FormData();
  form.append("file", file);
  const { data } = await http.post("/collection/upload", form);
  return data;
}

/**
 * Re-submit a workbook that previously failed validation and get back
 * the annotated copy with an Error column added.
 *
 * @param {File} file
 * @returns {Promise<Blob>}
 */
export async function downloadAnnotatedWorkbook(file) {
  const form = new FormData();
  form.append("file", file);
  const response = await http.post("/collection/upload/annotated", form, {
    responseType: "blob",
  });
  return response.data;
}

/**
 * Run the bundled mock collection through the upload pipeline. Same
 * response shape as ``uploadCollection``.
 *
 * @returns {Promise<{session_id: string, card_count: number, set_count: number}>}
 */
export async function useMockCollection() {
  const { data } = await http.post("/collection/mock");
  return data;
}

/**
 * Fetch the parsed collection tied to the caller's session cookie.
 * Throws on 404 if the session is missing or expired.
 *
 * @returns {Promise<{session_id: string, rows: Array, card_count: number, set_count: number}>}
 */
export async function getCollectionSession() {
  const { data } = await http.get("/collection/session");
  return data;
}

/**
 * Clear the session cookie and the row backing it. Resolves to
 * ``undefined`` since the API returns 204.
 *
 * @returns {Promise<void>}
 */
export async function deleteCollectionSession() {
  await http.delete("/collection/session");
}

/**
 * Fetch the dashboard's full card list -- one row per session line item
 * joined to the latest market price + card metadata.
 *
 * @returns {Promise<{cards: Array}>}
 */
export async function getCollectionCardsWithPrices() {
  const { data } = await http.get("/collection/cards-with-prices");
  return data;
}

/**
 * Daily total collection value across the chosen window. Server-side
 * Last Observation Carried Forward fills missing days.
 *
 * @param {"7d"|"30d"|"90d"|"6m"|"all"} window
 * @returns {Promise<{points: Array, earliest_snapshot: string|null}>}
 */
export async function getCollectionTimeseries(window) {
  const { data } = await http.get("/collection/timeseries", {
    params: { window },
  });
  return data;
}

/**
 * Top gainers and losers in the chosen window, capped at ``count`` each
 * after applying the ``min_pct`` threshold (default 5%).
 *
 * @param {"7d"|"30d"|"90d"|"6m"|"all"} window
 * @param {number} [count=5]
 * @param {number} [minPct=0.05]
 * @returns {Promise<{gainers: Array, losers: Array}>}
 */
export async function getCollectionMovers(window, count = 5, minPct = 0.05) {
  const { data } = await http.get("/collection/movers", {
    params: { window, count, min_pct: minPct },
  });
  return data;
}

/**
 * Fetch the configured chart palette in display order.
 *
 * @returns {Promise<{colors: string[]}>}
 */
export async function getPalette() {
  const { data } = await http.get("/palette");
  return data;
}
