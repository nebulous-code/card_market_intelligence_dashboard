/**
 * Turn a failed request into something worth showing a person.
 *
 * Every view used to translate axios errors itself, which produced two
 * problems. Copy drifted — some views wrote friendly sentences, others
 * interpolated the raw axios string and showed users "Request failed
 * with status code 404". And the logic lived in `.vue` files, which sit
 * outside the coverage allow-list, so none of it was ever tested.
 *
 * Putting it here fixes both: one place to change the wording, and the
 * branchy part is measured at 100%.
 *
 * Never format an axios error inline in a component — call these.
 */

/**
 * @typedef {Object} NormalizedError
 * @property {number|null} status HTTP status, or null when the request never landed.
 * @property {'offline'|'timeout'|'notFound'|'rateLimited'|'tooLarge'|'validation'|'server'|'unknown'} kind
 * @property {string} message User-facing sentence, already punctuated.
 * @property {number|null} retryAfter Seconds to wait, from the Retry-After header on a 429.
 */

/**
 * Read `Retry-After` off a 429 response.
 *
 * The header is only readable cross-origin because the API explicitly
 * lists it in `expose_headers`; without that it is invisible to JS even
 * though the browser received it.
 *
 * @param {Object|undefined} response
 * @returns {number|null} Seconds, or null when absent or unparseable.
 */
function parseRetryAfter(response) {
  const raw = response?.headers?.['retry-after']
  if (raw === undefined || raw === null) return null
  const seconds = Number(raw)
  return Number.isFinite(seconds) && seconds > 0 ? Math.ceil(seconds) : null
}

/**
 * Render a wait in units a person thinks in.
 *
 * The API reports `Retry-After` in seconds, which is right for a header
 * and wrong for a sentence -- the default rate-limit window produces
 * 600, and "try again in 600 seconds" makes a reader do arithmetic to
 * find out it means ten minutes.
 *
 * @param {number} seconds
 * @returns {string} e.g. '45 seconds', '2 minutes', '1 minute'
 */
function formatWait(seconds) {
  if (seconds < 60) return `${seconds} seconds`
  const minutes = Math.ceil(seconds / 60)
  return minutes === 1 ? '1 minute' : `${minutes} minutes`
}

/**
 * Use the server's own message when it sent a usable one.
 *
 * The API returns `{"detail": "..."}` for the errors this app raises
 * deliberately — an oversized upload explains the limit, a row-count
 * rejection explains how to fix the sheet. Those are better than
 * anything generic. A 422 upload failure instead returns an object,
 * which drives the annotated-workbook panel and must not be flattened
 * into a string here.
 *
 * @param {Object|undefined} response
 * @returns {string|null}
 */
function serverDetail(response) {
  const detail = response?.data?.detail
  return typeof detail === 'string' && detail.trim() ? detail.trim() : null
}

/**
 * Classify a thrown request error.
 *
 * @param {unknown} err
 * @param {string} [fallback] Message for a failure that matches nothing known.
 * @returns {NormalizedError}
 */
export function normalizeError(err, fallback = 'Something went wrong.') {
  const code = err?.code
  if (code === 'ECONNABORTED' || code === 'ETIMEDOUT') {
    return {
      status: null,
      kind: 'timeout',
      retryAfter: null,
      // The API sleeps on Render's free tier and takes ~30s to wake,
      // while the axios timeout is 15s -- so this is a routine first
      // visit, not a fault. Saying so stops it reading as broken.
      message:
        'The server took too long to respond. It may be waking up — try again in a moment.',
    }
  }

  const response = err?.response
  if (!response) {
    return {
      status: null,
      kind: 'offline',
      retryAfter: null,
      message: 'Could not reach the server. Check your connection and try again.',
    }
  }

  const status = response.status ?? null

  if (status === 404) {
    return { status, kind: 'notFound', retryAfter: null, message: "We couldn't find that." }
  }

  if (status === 413) {
    return {
      status,
      kind: 'tooLarge',
      retryAfter: null,
      message: serverDetail(response) ?? 'That file is too large to process.',
    }
  }

  if (status === 422) {
    return {
      status,
      kind: 'validation',
      retryAfter: null,
      message: serverDetail(response) ?? "That file couldn't be validated.",
    }
  }

  if (status === 429) {
    const retryAfter = parseRetryAfter(response)
    // Header first, then the server's own sentence, then a vague
    // fallback. The header is the most precise source but it is only
    // visible to JS when the API exposes it through CORS, and a
    // misconfiguration there should degrade to the server's wording
    // rather than all the way to "in a moment".
    let message
    if (retryAfter) {
      message = `Too many requests. Try again in ${formatWait(retryAfter)}.`
    } else {
      message = serverDetail(response) ?? 'Too many requests. Try again in a moment.'
    }
    return { status, kind: 'rateLimited', retryAfter, message }
  }

  if (status >= 500) {
    return {
      status,
      kind: 'server',
      retryAfter: null,
      message: 'The server had a problem. Try again in a moment.',
    }
  }

  return { status, kind: 'unknown', retryAfter: null, message: fallback }
}

/**
 * The string form, which is what most call sites want.
 *
 * `lead` preserves the context a view already knows and the error does
 * not — "Could not load sets." reads better than a bare reason, and
 * combining the two gives the user both what failed and why.
 *
 * @param {unknown} err
 * @param {string} [lead] Context sentence placed before the reason.
 * @returns {string}
 */
export function errorMessage(err, lead) {
  const { message } = normalizeError(err, lead ?? 'Something went wrong.')
  if (!lead) return message
  return message === lead ? message : `${lead} ${message}`
}

/**
 * True when the request failed because the thing does not exist.
 *
 * Views use this to show "Set not found" rather than a generic error,
 * and to suppress the rest of the page instead of rendering empty
 * charts and tables around a missing record.
 *
 * @param {unknown} err
 * @returns {boolean}
 */
export function isNotFound(err) {
  return err?.response?.status === 404
}
