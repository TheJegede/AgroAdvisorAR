# Phase 2 UX — Resilient State & Data Clarity

## Context

Phase 1 fixed hierarchy, touch targets, and badge contrast. Phase 2 addresses two compounding problems in the live app:

1. **Resilient State**: Sidebar session list, AlertBanner, and session creation all `.catch(() => {})` silently — user sees a blank list or stale data with zero explanation. Stream failure has no retry button (user must re-type). No offline detection.

2. **Data Clarity**: `NLIConfidenceBadge` shows raw `0.00` with no context when the score is zero or unknown. Advisory body text uses `text-gray-600` (6.35:1 contrast) — fails 7:1 outdoor threshold. Rate/dosage values in `ProductsRates.jsx` render in proportional Inter instead of monospaced font.

All sub-phases are independent — run in parallel.

---

## Phase A — Session + Profile error/loading feedback

**Files:** `frontend/src/components/layout/Sidebar.jsx`, `frontend/src/hooks/useSessions.js`

### useSessions.js — expose loading + error per operation

Add `loading` and `error` state to the `listSessions` call. The hook currently returns only the operation functions with no status; callers get nothing to render.

Add to hook return:
```js
const [sessionsLoading, setSessionsLoading] = useState(false)
const [sessionsError, setSessionsError] = useState(null)
```

In `listSessions()`:
```js
setSessionsLoading(true)
setSessionsError(null)
try {
  const data = await api.get('/sessions').then(r => r.data)
  setSessions(data)
} catch (e) {
  setSessionsError(true)
} finally {
  setSessionsLoading(false)
}
```

Return `{ ..., sessionsLoading, sessionsError }` from the hook.

### Sidebar.jsx — consume loading/error, surface profile error

Line 88 currently: `const { profile } = useProfile()` — ignores `loading` and `error`.
Change to: `const { profile, loading: profileLoading, error: profileError } = useProfile()`

**SessionsList component** — add loading and error states:
- While `sessionsLoading`: show 3 skeleton rows (`h-8 bg-white/10 rounded animate-pulse`)
- If `sessionsError`: show `"Couldn't load conversations. Tap to retry."` link that calls `listSessions()` again (no `.catch(() => {})`)

**Sidebar footer** — if `profileError`: show `"Profile unavailable"` in place of user name (already muted text, so just substitute text). If `profileLoading` and no profile yet: show a `w-24 h-3 bg-white/10 rounded animate-pulse` skeleton inline.

---

## Phase B — Stream retry button

**Files:** `frontend/src/pages/ChatPage.jsx`, `frontend/src/hooks/useSSEQuery.js`

### useSSEQuery.js

Add `retryable` flag to the error state: set it true on any error that is NOT an AbortError (i.e., real network failures). Return `{ ..., retryable }`.

Keep last submitted query in a ref so it can be replayed:
```js
const lastQueryRef = useRef(null)
// In submit(): lastQueryRef.current = { query, language, sessionId }
```

Expose `retry` function:
```js
const retry = () => {
  if (lastQueryRef.current) submit(lastQueryRef.current)
}
return { ..., retry, retryable }
```

### ChatPage.jsx

After the error message bubble in chat (the `onError` path, around line 111-117), if `retryable` is true, render below the error bubble:

```jsx
{retryable && (
  <div className="flex justify-center mt-2">
    <Button variant="ghost" size="sm" onClick={retry}>
      Retry
    </Button>
  </div>
)}
```

Clear `retryable` on any new user submission.

---

## Phase C — Offline status bar

**Files:** New `frontend/src/hooks/useSyncStatus.js`, new `frontend/src/components/ui/SyncStatusBar.jsx`, `frontend/src/components/layout/AppShell.jsx`

### useSyncStatus.js (new file)

```js
import { useState, useEffect } from 'react'

export function useSyncStatus() {
  const [online, setOnline] = useState(navigator.onLine)
  useEffect(() => {
    const on = () => setOnline(true)
    const off = () => setOnline(false)
    window.addEventListener('online', on)
    window.addEventListener('offline', off)
    return () => { window.removeEventListener('online', on); window.removeEventListener('offline', off) }
  }, [])
  return { online }
}
```

### SyncStatusBar.jsx (new file)

Renders nothing when `online`. When offline:
```jsx
<div className="flex-shrink-0 h-7 bg-harvest/10 border-b border-harvest/30 flex items-center px-4 gap-2 text-xs text-harvest-dark">
  <span className="w-2 h-2 rounded-full bg-harvest inline-block" />
  Offline — some features unavailable
</div>
```

### AppShell.jsx

Import `useSyncStatus` and `SyncStatusBar`. Insert `<SyncStatusBar online={online} />` between `<Header>` and the main content flex container. The bar adds 28px height only when offline — no layout shift when online.

---

## Phase D — Data clarity: NLI badge, contrast, mono rates

**Files:** `frontend/src/components/advisory/NLIConfidenceBadge.jsx`, `frontend/src/components/advisory/ProductsRates.jsx`, `frontend/src/components/advisory/LikelyCauses.jsx`, `frontend/src/components/advisory/CitationsSection.jsx`, `frontend/src/components/advisory/RecommendedActions.jsx`, `frontend/src/components/advisory/ProblemSummary.jsx`

### NLIConfidenceBadge.jsx — handle zero/unknown score

Currently renders `0.00` (red badge) when score is zero — farmer sees a red number with no explanation. Zero could mean "not computed" or "genuinely zero."

Change:
```jsx
// Current
if (confidence_score == null) return null

// New — also hide or reframe zero
if (confidence_score == null || confidence_score === 0) return null
```

If design wants to keep 0.00 visible (it is meaningful data): add a tooltip/title instead:
```jsx
<span title="Groundedness score: how well the answer is supported by retrieved sources">
  {t.nliScore}: {confidence_score.toFixed(2)}
</span>
```
Pick one: hide zero OR add title attribute. Hide zero is safer for farmer audience.

### ProductsRates.jsx — mono font for rates/dosages

Rate values (dosage numbers, units like "lb/acre", "qt/acre", PHI days) should use monospaced font for column alignment. Find the table `<td>` and list item elements that render rate values.

Add `font-mono` Tailwind class to numeric rate cells/spans. Example:
- Table rate cells: add `font-mono` to the `<td>` or inner `<span>` rendering the numeric value
- Card-style rate values: add `font-mono` to the value span

`font-mono` in Tailwind maps to `ui-monospace, SFMono-Regular, Menlo, Monaco, monospace` — no config change needed.

### Advisory body text contrast (6 files)

Replace `text-gray-600` → `text-gray-700` in advisory sub-components. This bumps from 6.35:1 to 10.27:1 on white — clears the 7:1 outdoor threshold.

Files to sweep (use replace_all):
- `ProblemSummary.jsx`
- `LikelyCauses.jsx`  
- `RecommendedActions.jsx`
- `CitationsSection.jsx`
- `AdvisoryCard.jsx` (DetailSection prose)

Don't change `text-gray-600` in non-advisory UI (sidebar, header, ChatPage chips) — the outdoor threshold applies specifically to advisory body content.

---

## Verification

1. `cd frontend && npm run lint` — clean
2. `npm run test` — 26/26 pass
3. Dev server manual checks:
   - Kill network mid-stream → error bubble + Retry button appears; press Retry → resubmits
   - Toggle `navigator.onLine` via DevTools → orange bar appears/disappears instantly
   - Simulate slow session fetch → skeleton rows in sidebar, not blank; if fetch fails → error + retry link
   - Advisory card with `confidence_score=0` → NLI badge hidden (or has title tooltip)
   - ProductsRates → rate values render in monospace
