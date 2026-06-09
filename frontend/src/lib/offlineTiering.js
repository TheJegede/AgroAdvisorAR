// Decide whether an advisory may be cached and shown OFFLINE as reference.
// Offline = abstention: time-sensitive safety content must never be served
// frozen. Default to FALSE (do not cache) whenever unsure.

const TIME_SENSITIVE_RE =
  /\b(spray|spraying|dicamba|engenia|xtendimax|tavium|application window|apply|rate|oz\/a|pt\/a|inversion|burndown|pre-?harvest|window|today|forecast|wind)\b/i

function textBlob(advisory) {
  const parts = [
    advisory.problem_summary || '',
    advisory.detailed_explanation || '',
    ...(advisory.recommended_actions || []),
    ...(advisory.key_points || []),
  ]
  return parts.join(' ')
}

export function isCacheableAsReference(advisory) {
  if (!advisory || typeof advisory !== 'object') return false
  if (advisory.response_type !== 'informational') return false
  if ((advisory.products_rates || []).length > 0) return false
  if ((advisory.warnings || []).length > 0) return false
  if (TIME_SENSITIVE_RE.test(textBlob(advisory))) return false
  return true
}
