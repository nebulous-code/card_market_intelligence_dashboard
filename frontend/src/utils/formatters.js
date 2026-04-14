/**
 * Global formatting utilities.
 *
 * Import these functions anywhere a price, date, or number is displayed.
 * Never format these values inline in a component — use these instead so
 * formatting is consistent and easy to change in one place.
 */

/**
 * Format a number as USD currency.
 * Returns '—' for null, undefined, or non-numeric values.
 * @param {number|null|undefined} value
 * @returns {string} e.g. '$399.99' or '—'
 */
export function formatCurrency(value) {
  if (value === null || value === undefined || isNaN(Number(value))) return '—'
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value)
}

/**
 * Format an ISO date string to a readable date.
 * @param {string|null|undefined} value
 * @returns {string} e.g. 'Apr 13, 2026' or '—'
 */
export function formatDate(value) {
  if (!value) return '—'
  return new Date(value).toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  })
}

/**
 * Format a plain number with comma separators.
 * @param {number|null|undefined} value
 * @returns {string} e.g. '1,234' or '—'
 */
export function formatNumber(value) {
  if (value === null || value === undefined || isNaN(Number(value))) return '—'
  return new Intl.NumberFormat('en-US').format(value)
}

/**
 * Format a decimal as a percentage.
 * @param {number|null|undefined} value
 * @returns {string} e.g. '12.34%' or '—'
 */
export function formatPercent(value) {
  if (value === null || value === undefined || isNaN(Number(value))) return '—'
  return new Intl.NumberFormat('en-US', {
    style: 'percent',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value)
}
