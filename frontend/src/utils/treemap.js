/**
 * Pure helpers for the Collection Treemap.
 *
 * Builds the data array Chart.js's ``treemap`` controller wants from the
 * cards-with-prices response. Two transforms live here:
 *
 * 1. ``buildTreemapData(cards)`` -- one entry per card OR per
 *    consolidated "Other" group. Each entry has ``{set_id, set_name,
 *    card_id?, card_name, value, count, top_card_name?}``.
 *
 * 2. The bottom-10% rule: within a set, the cheapest cards whose
 *    cumulative value sums to <= 10% of the set's total are merged
 *    into a single "Other (N cards)" entry. The merge runs only when
 *    the set has 5+ cards and the merge would consolidate at least 3
 *    of them; otherwise every card stays on its own.
 */

const OTHER_THRESHOLD = 0.1
const MIN_SET_SIZE_FOR_OTHER = 5
const MIN_GROUP_SIZE = 3

/**
 * @param {Array} cards
 * @returns {Array<{
 *   set_id: string,
 *   set_name: string,
 *   card_id?: string,
 *   card_name: string,
 *   value: number,
 *   count: number,
 *   top_card_name?: string,
 *   is_other?: boolean,
 * }>}
 */
export function buildTreemapData(cards) {
  // Group rows by set; each row's value is qty * market_price (zero
  // when no market price is known so the row still slots in but
  // doesn't take up area in the treemap).
  const bySet = new Map()
  for (const c of cards) {
    const value =
      c.market_price == null ? 0 : Number(c.market_price) * Number(c.quantity)
    let bucket = bySet.get(c.set_id)
    if (!bucket) {
      bucket = { set_id: c.set_id, set_name: c.set_name, rows: [] }
      bySet.set(c.set_id, bucket)
    }
    bucket.rows.push({
      card_id: c.card_id,
      card_name: c.card_name,
      condition: c.condition,
      quantity: Number(c.quantity),
      value,
    })
  }

  const out = []
  for (const bucket of bySet.values()) {
    bucket.rows.sort((a, b) => b.value - a.value)
    const setTotal = bucket.rows.reduce((acc, r) => acc + r.value, 0)
    const grouped = consolidateOthers(bucket.rows, setTotal)
    for (const entry of grouped) {
      out.push({
        set_id: bucket.set_id,
        set_name: bucket.set_name,
        ...entry,
      })
    }
  }
  return out
}

function consolidateOthers(rows, setTotal) {
  if (rows.length < MIN_SET_SIZE_FOR_OTHER || setTotal <= 0) {
    return rows.map((r) => rowEntry(r))
  }
  // Walk from cheapest upward, accumulating until we'd cross the 10%
  // threshold. Whatever we accumulated is the "Other" bucket -- but
  // only if it consolidates at least MIN_GROUP_SIZE rows.
  const cutoff = setTotal * OTHER_THRESHOLD
  let runningTotal = 0
  let cutIndex = rows.length // default: nothing grouped
  for (let i = rows.length - 1; i >= 0; i--) {
    const next = runningTotal + rows[i].value
    if (next > cutoff) break
    runningTotal = next
    cutIndex = i
  }
  const groupedCount = rows.length - cutIndex
  if (groupedCount < MIN_GROUP_SIZE) {
    return rows.map((r) => rowEntry(r))
  }
  const head = rows.slice(0, cutIndex).map((r) => rowEntry(r))
  const tail = rows.slice(cutIndex)
  const tailValue = tail.reduce((acc, r) => acc + r.value, 0)
  const topCardInTail = tail.reduce(
    (best, r) => (best === null || r.value > best.value ? r : best),
    null,
  )
  head.push({
    card_name: `Other (${tail.length} cards)`,
    value: tailValue,
    count: tail.length,
    top_card_name: topCardInTail?.card_name ?? null,
    is_other: true,
  })
  return head
}

function rowEntry(r) {
  return {
    card_id: r.card_id,
    card_name: r.card_name,
    condition: r.condition,
    value: r.value,
    count: r.quantity,
  }
}
