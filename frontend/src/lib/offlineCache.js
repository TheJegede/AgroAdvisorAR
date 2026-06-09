// Cache the last-N REFERENCE (non-time-sensitive) advisories for offline
// reading. Time-sensitive content is rejected at the door (see offlineTiering).
import { isCacheableAsReference } from './offlineTiering'

export const MAX_CACHED = 10
const KEY = 'agroar.offline.reference.v1'

function read(store) {
  try {
    return JSON.parse(store.getItem(KEY) || '[]')
  } catch {
    return []
  }
}

export function cacheReferenceAdvisory(advisory, { store = window.localStorage, now = Date.now } = {}) {
  if (!isCacheableAsReference(advisory)) return
  const entries = read(store)
  entries.unshift({ cachedAt: now(), advisory })
  store.setItem(KEY, JSON.stringify(entries.slice(0, MAX_CACHED)))
}

export function getCachedAdvisories({ store = window.localStorage } = {}) {
  return read(store)
}
