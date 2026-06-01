# Phase 3 UX — Audit Closeout

## Context

Phase 1 fixed hierarchy, touch targets, and badge contrast. Phase 2 added resilient state,
offline detection, stream retry, and data clarity. Both shipped 2026-05-31.

Three categories of work remain from the original design audit
(`docs/superpowers/plans/2026-05-31-ux-design-audit.md`):

1. **i18n gaps** — Phase 2 hardcoded four UI strings in English only
   (`SyncStatusBar`, `Sidebar` retry/error messages, `ChatPage` retry button).
   These break the ES translate-bridge UX for Spanish-speaking farmers.

2. **AlertBanner resilience** — the Phase 2 context block explicitly called out
   AlertBanner's `.catch(() => {})` on both API calls, but the implementation only
   fixed Sidebar. Dismiss failure currently silently drops an alert the farmer can
   never get back.

3. **Visual polish** — three remaining design-audit items: `rounded-2xl` outlier in
   ChatInput container (inconsistent with `rounded-card` 12px system), two emoji
   icons (`📞` in EscalationCard, `🌾` in OutOfScopeCard) that should be SVG to
   match the rest of the icon system, and citation link contrast (`text-field` 3.59:1
   on white → `text-field-dark` for legibility).

All three sub-phases are independent and can run in parallel.

---

## Sub-phase A — i18n completeness

**Files:** `frontend/src/constants/i18n.js`, `frontend/src/components/ui/SyncStatusBar.jsx`,
`frontend/src/components/layout/Sidebar.jsx`, `frontend/src/pages/ChatPage.jsx`

### i18n.js — add 4 missing keys (EN + ES)

Add to both `en` and `es` label maps:

```js
// EN
offline: 'Offline — some features unavailable',
retry: 'Retry',
sessionsLoadError: "Couldn't load conversations. Tap to retry.",
profileUnavailable: 'Profile unavailable',

// ES
offline: 'Sin conexión — algunas funciones no están disponibles',
retry: 'Reintentar',
sessionsLoadError: 'No se pudieron cargar las conversaciones. Toca para reintentar.',
profileUnavailable: 'Perfil no disponible',
```

### SyncStatusBar.jsx — use i18n

Import `useLang` and replace the hardcoded string:
```jsx
import { useLang } from '../../contexts/LangContext'

export default function SyncStatusBar({ online }) {
  const { t } = useLang()
  if (online) return null
  return (
    <div className="flex-shrink-0 h-7 bg-harvest/10 border-b border-harvest/30 flex items-center px-4 gap-2 text-xs text-harvest-dark">
      <span className="w-2 h-2 rounded-full bg-harvest inline-block" />
      {t.offline}
    </div>
  )
}
```

### Sidebar.jsx — use i18n keys

Replace the two hardcoded strings in the error/profile blocks:
- `"Couldn't load conversations. Tap to retry."` → `{t.sessionsLoadError}`
- `"Profile unavailable"` → `{t.profileUnavailable}`

Remove the `|| "..."` fallback from `t.sessionsLoadError` usage.

### ChatPage.jsx — use i18n key

Replace `{t.retry || 'Retry'}` → `{t.retry}`.

---

## Sub-phase B — AlertBanner resilience

**File:** `frontend/src/components/AlertBanner.jsx`

Current code does optimistic dismiss (remove from state, then PATCH silently fails):
```js
function dismiss(id) {
  api.patch(`/alerts/${id}/dismiss`).catch(() => {})
  setAlerts(prev => prev.filter(a => a.id !== id))
}
```

Fix: remove optimistically, restore on failure:
```js
function dismiss(id) {
  setAlerts(prev => prev.filter(a => a.id !== id))
  api.patch(`/alerts/${id}/dismiss`).catch(() => {
    // Restore: re-fetch alerts the server didn't accept
    api.get('/alerts').then(res => setAlerts(res.data)).catch(() => {})
  })
}
```

GET /alerts failure already returns `null` (no banner shown) — correct behavior,
leave the `useEffect` `.catch(() => {})` as-is.

---

## Sub-phase C — Visual polish

**Files:** `frontend/src/components/chat/ChatInput.jsx`,
`frontend/src/components/advisory/EscalationCard.jsx`,
`frontend/src/components/chat/OutOfScopeCard.jsx`,
`frontend/src/components/advisory/CitationsSection.jsx`

### ChatInput.jsx — radius consistency

Container `div` uses `rounded-2xl`. Change to `rounded-card` (custom token = 12px,
same as AdvisoryCard and OutOfScopeCard):

```jsx
// before
<div className="flex items-end gap-2 rounded-2xl border ...">
// after
<div className="flex items-end gap-2 rounded-card border ...">
```

### EscalationCard.jsx — 📞 emoji → SVG

Replace the `📞` emoji span with an inline SVG phone icon (Heroicons stroke style):

```jsx
<svg width="18" height="18" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2} aria-hidden="true">
  <path strokeLinecap="round" strokeLinejoin="round"
    d="M2.25 6.75c0 8.284 6.716 15 15 15h2.25a2.25 2.25 0 002.25-2.25v-1.372c0-.516-.351-.966-.852-1.091l-4.423-1.106c-.44-.11-.902.055-1.173.417l-.97 1.293c-.282.376-.769.542-1.21.38a12.035 12.035 0 01-7.143-7.143c-.162-.441.004-.928.38-1.21l1.293-.97c.363-.271.527-.734.417-1.173L6.963 3.102a1.125 1.125 0 00-1.091-.852H4.5A2.25 2.25 0 002.25 4.5v2.25z" />
</svg>
```

### OutOfScopeCard.jsx — 🌾 emoji → SVG

Replace the `🌾` emoji span with an inline SVG plant icon:

```jsx
<svg width="32" height="32" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5} aria-hidden="true">
  <path strokeLinecap="round" strokeLinejoin="round"
    d="M12 18.75a6 6 0 006-6v-1.5m-6 7.5a6 6 0 01-6-6v-1.5m6 7.5v3.75m-3.75 0h7.5M12 15c-2.485 0-4.5-2.015-4.5-4.5V4.875C7.5 3.839 8.34 3 9.375 3h5.25c1.035 0 1.875.84 1.875 1.875V10.5c0 2.485-2.015 4.5-4.5 4.5z" />
</svg>
```

### CitationsSection.jsx — citation link contrast

Inline citation links use `text-field` (3.59:1 on white — below 4.5:1 AA for normal text).
Change to `text-field-dark`:

```jsx
// before
<a href={c.url} ... className="text-field dark:text-hc-accent underline font-bold">
// after
<a href={c.url} ... className="text-field-dark dark:text-hc-accent underline font-bold">
```

---

## Verification

1. `cd frontend && npm run lint` — clean
2. `npm run test` — 26/26 pass
3. Manual checks:
   - Toggle `navigator.onLine` off in DevTools → offline bar shows Spanish text when lang=ES
   - Switch lang to ES → Sidebar retry link + profile unavailable text in Spanish
   - Retry button label in ES → "Reintentar"
   - Dismiss an alert with network blocked → alert reappears (not silently lost)
   - Advisory card with EscalationCard → SVG phone icon, no emoji
   - OOS reply → SVG plant icon, no emoji
   - ChatInput container corners → 12px (matches advisory card)
   - Citations with links → darker green (`text-field-dark`)
