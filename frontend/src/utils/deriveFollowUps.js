const TRUNCATE_AT = 60

function truncate(str) {
  if (!str || str.length <= TRUNCATE_AT) return str
  return str.slice(0, TRUNCATE_AT - 1).trimEnd() + '…'
}

function pickRandom(arr) {
  return arr[Math.floor(Math.random() * arr.length)]
}

/**
 * Derives 2–3 contextual follow-up chip strings from the last advisory.
 * Pure function — no React deps, safe to call outside components.
 */
export function deriveFollowUps(advisory, category, t) {
  const chips = []
  const templates = t.followUpTemplates
  if (!templates) return []

  const firstCause = advisory?.likely_causes?.[0]?.cause
  if (firstCause) {
    chips.push(truncate(templates.howToTreat.replace('{cause}', firstCause)))
  }

  const firstAction = advisory?.recommended_actions?.[0]
  if (firstAction) {
    chips.push(truncate(templates.tellMeMore.replace('{action}', firstAction)))
  }

  const pool = templates.categoryPool?.[category]
  if (pool?.length) chips.push(pickRandom(pool))

  return [...new Set(chips)].slice(0, 3)
}
