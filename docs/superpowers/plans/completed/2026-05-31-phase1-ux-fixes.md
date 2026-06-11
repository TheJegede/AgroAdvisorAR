# Phase 1 UX Fixes — Advisory Card Reorder + Touch Targets + Badge Contrast

## Context

Design audit (`docs/superpowers/plans/2026-05-31-ux-design-audit.md`) identified the advisory card's #1 UX problem: confidence metadata renders *before* actionable content — a farmer scrolls past 4 metadata sections before seeing "what to do." Five touch targets fail the 44px field-use standard. Low confidence badge fails WCAG AA contrast (3.94:1 on `bg-arred text-white`).

**All three phases are fully independent — no shared files, run in parallel.**

---

## Phase A — AdvisoryCard hierarchy reorder

**File:** `frontend/src/components/advisory/AdvisoryCard.jsx`  
**Dependency:** none

Rewrite `AdvisoryCardInner` JSX body. New render order for the **default (advisory)** branch:

```
1. Crop chip + ContextMetaBar      ← orientation row (unchanged, stays at top)
2. ProblemSummary                  ← first visible content
3. RecommendedActions              ← priority-1 action
4. ProductsRates                   ← products / rates
5. LikelyCauses                    ← collapsible accordion (already defaultOpen: false)
6. EscalationCard                  ← gated: !response.suppressed  ← gate travels with it
7. WarningsBanner
8. ConfidenceBadge + NLIConfidenceBadge   ← trust signal row, now secondary
9. ConfidenceExplainer
10. LowConfidenceBanner
11. CitationsSection               ← collapsible
12. FeedbackWidget
```

**Informational branch** (`response_type === 'informational'`):
```
ProblemSummary → detailed_explanation → key_points → RecommendedActions →
EscalationCard (!suppressed) → WarningsBanner →
[ConfidenceBadge + NLIConfidenceBadge] → ConfidenceExplainer → LowConfidenceBanner →
CitationsSection → FeedbackWidget
```

**Suppressed branch:** `SuppressedNotice` unchanged.

**Constraint:** `!response.suppressed && <EscalationCard>` guard must travel with `EscalationCard` — do not detach.

---

## Phase B — Touch target fixes

**Files:** `ChatInput.jsx`, `Header.jsx`, `ChatPage.jsx`, `Sidebar.jsx`  
**Dependency:** none (4 files, all independent — can split further if needed)

### `frontend/src/components/chat/ChatInput.jsx`
- Line 108: send button `w-9 h-9` → `w-11 h-11`

### `frontend/src/components/layout/Header.jsx`
- Line 11: hamburger button `w-9 h-9` → `w-11 h-11`
- Line 24: profile `<Link>` `w-9 h-9` → `w-11 h-11`

### `frontend/src/pages/ChatPage.jsx`
- Line 181: mid-chat chip buttons — add `min-h-touch` to className  
  (welcome chips line 158 already have it — match that pattern)

### `frontend/src/components/layout/Sidebar.jsx`
- Line 10: `SidebarNavItem` base class `py-2.5` → `py-3`
- Line 51: session delete button `p-1` → `p-2`

---

## Phase C — ConfidenceBadge contrast fix

**File:** `frontend/src/components/advisory/ConfidenceBadge.jsx`  
**Dependency:** none

Change `Low` entry in `STYLES` from solid red to outlined pill:

```js
// before
Low: 'bg-arred text-white dark:bg-hc-danger dark:text-hc-danger-fg dark:border-2 dark:border-hc-border',

// after
Low: 'bg-arred/10 border border-arred/30 text-arred-dark dark:bg-hc-danger dark:text-hc-danger-fg dark:border-2 dark:border-hc-border',
```

`text-arred-dark` (#9B1E29) on white = 8.02:1 — AAA ✅. Dark mode classes unchanged.

---

## Verification (after all phases done)

1. `cd frontend && npm run lint` — no new errors
2. `npm run test` — vitest suite passes
3. Dev server visual check:
   - Advisory response: `ProblemSummary` is first visible section; confidence badges near bottom
   - Send button, hamburger, profile icon all 44×44px
   - Low badge is outlined red-on-white, not filled
