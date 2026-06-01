---
version: anydesign-1
name: AgroAdvisor AR
source: frontend/src — React 19 + Vite + Tailwind codebase audit
captured_at: 2026-05-31
description: |
  AgroAdvisor operates in the functional register of an agricultural extension tool: earthy
  low-reflectivity palette, high-contrast text, field-operative layout. The design believes
  the farmer's time in the field is finite. Every choice answers a single question: "does
  this help someone wearing work gloves make a decision in the next 60 seconds?" The palette
  (forest green, harvest amber, warm parchment) is not decoration — it is optical camouflage
  for bright outdoor screens.

colors:
  primary: "#2D6A4F"
  primary-dark: "#1B4332"
  primary-light: "#40916C"
  secondary: "#E9A228"
  secondary-dark: "#B57D1A"
  danger: "#CC2936"
  danger-dark: "#9B1E29"
  neutral-warm: "#8B6B5E"
  canvas: "#F7F4EF"
  surface: "#FFFFFF"
  text-primary: "#1C1917"
  text-body: "#374151"
  text-muted: "#4B5563"
  border-default: "#E5E7EB"
  border-subtle: "#F3F4F6"
  sidebar-bg: "#1B4332"
  hc-bg: "#FFFFFF"
  hc-fg: "#000000"
  hc-accent: "#0033A0"
  hc-danger: "#B00020"
  hc-focus: "#FFD700"
  hc-sidebar-bg: "#000000"

typography:
  display:
    fontFamily: "Inter, system-ui, sans-serif"
    fontSize: "20px"
    fontWeight: 700
    lineHeight: 1.3
    letterSpacing: "0"
  section-heading:
    fontFamily: "Inter, system-ui, sans-serif"
    fontSize: "16px"
    fontWeight: 600
    lineHeight: 1.4
    letterSpacing: "0"
  body:
    fontFamily: "Inter, system-ui, sans-serif"
    fontSize: "16px"
    fontWeight: 400
    lineHeight: 1.625
  body-sm:
    fontFamily: "Inter, system-ui, sans-serif"
    fontSize: "14px"
    fontWeight: 400
    lineHeight: 1.5
  caption:
    fontFamily: "Inter, system-ui, sans-serif"
    fontSize: "12px"
    fontWeight: 400
    lineHeight: 1.4
  label:
    fontFamily: "Inter, system-ui, sans-serif"
    fontSize: "11px"
    fontWeight: 600
    lineHeight: 1
    letterSpacing: "0.06em"
  data-mono:
    fontFamily: "ui-monospace, 'Geist Mono', monospace"
    fontSize: "14px"
    fontWeight: 500
    lineHeight: 1.4

spacing:
  base: 4px
  scale: [4, 8, 12, 16, 20, 24, 32, 48, 64]

rounded:
  control: "8px"
  card: "12px"
  pill: "9999px"

elevation:
  L0: "flat — no shadow, no border"
  L1: "1px solid {colors.border-subtle} + box-shadow: 0 1px 3px rgba(0,0,0,0.06)"
  L2: "1px solid {colors.border-default} + box-shadow: 0 2px 6px rgba(0,0,0,0.08)"

components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.surface}"
    rounded: "{rounded.control}"
    minHeight: "44px"
    padding: "10px 16px"
  button-secondary:
    backgroundColor: "{colors.secondary}"
    textColor: "{colors.text-primary}"
    rounded: "{rounded.control}"
    minHeight: "44px"
  button-ghost:
    backgroundColor: "transparent"
    border: "1px solid {colors.primary}"
    textColor: "{colors.primary}"
    rounded: "{rounded.control}"
    minHeight: "44px"
  button-danger:
    backgroundColor: "{colors.danger}"
    textColor: "{colors.surface}"
    rounded: "{rounded.control}"
    minHeight: "44px"
  advisory-card:
    backgroundColor: "{colors.surface}"
    border: "1px solid {colors.border-subtle}"
    rounded: "{rounded.card}"
    shadow: "{elevation.L1}"
    maxWidth: "672px"
    padding: "16px"
  smart-card:
    backgroundColor: "{colors.surface}"
    border: "1px solid {colors.border-default}"
    rounded: "{rounded.card}"
    shadow: "{elevation.L1}"
    padding: "16px"
  confidence-badge:
    rounded: "{rounded.pill}"
    padding: "4px 12px"
  chat-input:
    backgroundColor: "{colors.surface}"
    border: "1px solid {colors.border-default}"
    rounded: "16px"
    focusBorder: "{colors.primary}"
  suggestion-chip:
    backgroundColor: "{colors.surface}"
    border: "1px solid {colors.border-default}"
    rounded: "{rounded.pill}"
    minHeight: "44px"
    padding: "8px 16px"
  sync-status-bar:
    height: "28px"
    backgroundColor: "{colors.canvas}"
    borderBottom: "1px solid {colors.border-subtle}"
  offline-badge:
    rounded: "{rounded.pill}"
    padding: "2px 8px"
---

# Design Analysis — AgroAdvisor AR

> Analysis generated with the `anydesign` skill.
> Date: 2026-05-31
> Analysis emphasis: Reconstruction + Design system + Field-UX audit
> Source type: Codebase (React/Tailwind) — full component tree read

---

## Source

- **Source type**: Local codebase — JSX + Tailwind config
- **Path**: `frontend/src/`
- **Capture method**: Full component tree read (tailwind.config.js, index.css, AppShell, ChatPage, ChatInput, ChatHistory, AdvisoryCard + all sub-components, Sidebar, Header, Button, layout primitives)
- **Detected limitations**: No runtime screenshot — layout and rendering inferred from class analysis. No tablet/desktop viewport capture.

---

## TL;DR

AgroAdvisor has a thoughtful earthy palette (`{colors.primary}` forest green, `{colors.secondary}` harvest amber, `{colors.canvas}` warm parchment) that already does 70% of the outdoor-readiness job. The two critical problems are: (1) the advisory card buries actionable content — farmers scroll past four confidence-metadata sections before seeing what to do; (2) five touch-target violations exist on frequently-used controls. Fixing those two issues — plus adding offline-first status signals — turns a functionally-sound app into a genuinely field-ready tool.

---

## 1. Visual Identity

### 1.1 Surface Description

**Personality**: Practical, grounded, mission-operative, utilitarian-warm, non-decorative.

**Mood**: Trustworthy. The absence of gradient meshes, hero animations, or marketing flourishes signals "tool, not product." A farmer picking this up mid-field should feel like they picked up a reference manual, not a startup's landing page.

**Detectable stylistic references**: Closer to healthcare reference apps (UpToDate, clinical dashboards) than consumer chat (ChatGPT, Claude). The advisory card's multi-section structure with collapsible causes echoes clinical decision-support UI. Not derivative — this is the right reference class for the use case.

**Information density**: Medium-dense overall; spikes to very dense inside advisory cards. The welcome state is appropriately minimal.

**Implicit positioning**: Field-operative end-users (farmers, farm managers) and potentially extension agents reviewing recommendations on mobile. Not developer-facing.

**Confidence**: ✅ high

### 1.2 Brand Voice / Atmosphere

AgroAdvisor operates under a constraint that shapes every design decision: the primary user is holding a phone in bright Arkansas sunlight, possibly with dirty hands, possibly under time pressure from an active pest event. The design knows this. The warm parchment canvas (`{colors.canvas}` #F7F4EF) is not a stylistic choice — it is a deliberate reduction of screen luminance compared to a pure-white (`{colors.surface}`) background. The forest green sidebar (`{colors.sidebar-bg}` #1B4332) grounds the spatial hierarchy without the glare penalty of a light sidebar.

The palette says "we work with land." The three semantic brand colors map to the three crops: `{colors.primary}` (forest green) → rice and soybeans, `{colors.secondary}` (harvest amber) → medium-confidence advice / caution state, `{colors.danger}` (Arkansas red) → danger / Low confidence. This isn't arbitrary color assignment — it is a visual language a farmer can learn once and read instantly. That instinctive legibility is the brand's functional promise.

What the design deliberately does NOT do is also part of its voice: no gradient overlays, no decorative illustrations, no product-hero animations. These would be noise at 500 nits of sunlight. The restraint is a stance — "we are not trying to impress you; we are trying to help you" — and it should be protected as a design rule, not relaxed as the product matures.

### 1.3 The "ONE Brand Thing"

**The thing**: `{colors.primary}` (#2D6A4F) — field green, used in the sidebar background (via `{colors.sidebar-bg}`), primary buttons, send button, High-confidence badge, focus rings, and hover states across the app.

**Why it carries the brand**: Remove this green and the UI becomes a generic gray-white chat interface indistinguishable from any LLM wrapper. The green is the visual anchor that signals "agriculture" without an illustration.

**How everything else supports it**: `{colors.canvas}` (warm cream) and `{colors.text-primary}` (near-black charcoal) are deliberately neutral. `{colors.secondary}` (amber) and `{colors.danger}` (red) are semantically scoped, not decorative. The green is the only color used for primary spatial orientation — if you look at the sidebar, you know where you are.

**Where it appears / where it deliberately doesn't**: Appears in sidebar, primary CTA, send button, High-confidence badge, focus rings, hover tints (`field/10`, `field/5`). Notably absent from body text, card backgrounds, mid-card section dividers — it stays functional, never decorative.

*Confidence*: ✅ high

---

## 2. Design System (Tokens)

### 2.1 Colors

| Token | Hex | Role | Where it appears | Contrast on canvas | Outdoor 7:1? |
|---|---|---|---|---|---|
| `primary` | `#2D6A4F` | Brand, CTA, High-confidence | Sidebar bg (via primary-dark), buttons, badges | 5.82:1 | ❌ AA only |
| `primary-dark` | `#1B4332` | Sidebar bg, dark hover | Sidebar, dark button hover | 10.17:1 | ✅ AAA |
| `primary-light` | `#40916C` | Hover states | Button/link hover | — | — |
| `secondary` | `#E9A228` | Medium-confidence, secondary btn | Confidence badge bg, button bg | 2.16:1 (bg) | ❌ use as bg only with dark text |
| `secondary-dark` | `#B57D1A` | Avatar, dark harvest hover | Avatar bg, button hover | — | — |
| `danger` | `#CC2936` | Low-confidence bg, error, AR Red | Badge bg, alert, error text | 5.33:1 | ⚠️ AA text only |
| `danger-dark` | `#9B1E29` | Danger text on light bg | Error text, border accent | 8.02:1 | ✅ AAA |
| `neutral-warm` | `#8B6B5E` | Poultry crop chip | Poultry category indicator | — | — |
| `canvas` | `#F7F4EF` | App background | AppShell bg, page canvas | — | — |
| `surface` | `#FFFFFF` | Raised surfaces | Cards, header, input | — | — |
| `text-primary` | `#1C1917` | All headings, labels | Charcoal text everywhere | 16.03:1 (on canvas) | ✅ AAA |
| `text-body` | `#374151` | Body prose in advisory | Gray-700, advisory body | 10.27:1 (on surface) | ✅ AAA |
| `text-muted` | `#4B5563` | Captions, secondary labels | Muted text | 6.93:1 (on canvas) | ⚠️ just below 7:1 |
| `border-default` | `#E5E7EB` | Input borders, table dividers | Interactive elements | — | — |
| `border-subtle` | `#F3F4F6` | Card borders, section dividers | Advisory card chrome | — | — |
| `sidebar-bg` | `#1B4332` | Sidebar background | Sidebar only | — | — |

**Critical outdoor contrast finding**: `{colors.primary}` (#2D6A4F) as text on `{colors.surface}` achieves 6.35:1 — AA but NOT AAA (7:1). For any `{colors.primary}`-colored text used as body content (citations, hover labels), switch to `{colors.primary-dark}` (#1B4332) which achieves 10.17:1 on canvas and 11.08:1 on surface.

**Current badge contrast failure**: `bg-arred text-white` (Low-confidence badge) achieves only 3.94:1 at `text-sm` size — fails WCAG AA for normal text. Fix: use `bg-danger/10 border border-danger/30 text-danger-dark` pill pattern instead. `{colors.danger-dark}` (#9B1E29) on surface = 8.02:1 (AAA ✅).

**`{colors.secondary}` (#E9A228)** cannot carry white text — 2.16:1. Current implementation correctly uses `text-charcoal` — preserve this.

**`{colors.text-muted}` (#4B5563)** on `{colors.canvas}` = 6.93:1 — 1% short of the 7:1 outdoor target. Bump muted captions to `{colors.text-body}` (#374151) in field-facing UI.

### 2.2 Typography

- **Detected family**: `Inter` (defined in tailwind.config.js)
- **Suggested fallback**: `system-ui, sans-serif`
- **Mono face**: MISSING — no `font-mono` defined in config. Needed for numerical data (NPK rates, application rates, weather values). Add `ui-monospace, 'Geist Mono', monospace` as `data-mono` family.

**Observed scale:**

| Token | Size | Weight | Line-height | Use |
|---|---|---|---|---|
| `display` | 20px / `text-xl` | 700 | 1.3 | Welcome h1, header app name |
| `section-heading` | 16px / `text-base` | 600 | 1.4 | Advisory section headings (h2) |
| `body` | 16px / `text-base` | 400 | 1.625 | ProblemSummary prose |
| `body-sm` | 14px / `text-sm` | 400 | 1.5 | Advisory lists, sidebar nav |
| `caption` | 12px / `text-xs` | 400 | 1.4 | Citations, char counter |
| `label` | 11px / `text-[11px]` | 600 | 1 | Section label ("RECENT CONVERSATIONS") |
| `data-mono` | 14px | 500 | 1.4 | **Proposed**: rates, NPK values, weather numbers |

**Notable tracking**: 0.06em uppercase tracking on sidebar section labels (`tracking-wider`) — the one typographic sophistication in the system. Should be extracted as a rule.

**Missing**: No negative tracking on headings. Adding `-0.01em` tracking on `section-heading` would improve scannability on outdoor screens. Currently Inter renders at default tracking throughout.

### 2.3 Spacing

- **Inferred base unit**: 4px (Tailwind default scale)
- **Common values**: `p-4` (16px), `px-4 py-3` (16/12px), `gap-2` (8px), `gap-3` (12px), `py-2.5` (10px), `pb-4` (16px)
- **Card internal rhythm**: sections separated by `my-3` (12px) — consistent ✅
- **Overall consistency**: ✅ high — systematically Tailwind multiples throughout

### 2.4 Radii — CURRENT PROBLEM

Four distinct radius values currently in simultaneous use on the same screens:

| Current value | Used on |
|---|---|
| `rounded-full` / `9999px` | Confidence badges, suggestion chips, avatar, send button |
| `rounded-2xl` / `16px` | Chat input container, welcome icon |
| `rounded-card` / `12px` | Advisory cards, product cards |
| `rounded-lg` / `8px` | Buttons, nav items, LikelyCauses accordion, EscalationCard |

**This is too many.** 4 radius values on one screen fractures the visual system. Proposed consolidation to 3:

| Token | Value | Rule |
|---|---|---|
| `{rounded.pill}` | `9999px` | Badges, chips, avatars, send button — semantic indicators only |
| `{rounded.card}` | `12px` | Content containers (advisory, product cards, smart cards, input container) |
| `{rounded.control}` | `8px` | Interactive controls (buttons, nav items, accordions) |

This eliminates the `rounded-2xl` (16px) outlier — chat input container moves to `{rounded.card}` (12px).

### 2.5 Elevation System

**Level 0 — Flat**: sidebar, full-bleed chat canvas, suggestion chip row. No shadow.

**Level 1 — Card** (`advisory-card`, `smart-card`): `border border-gray-100` + `shadow-sm`. The actual elevation model is surface-tone lift (white card on parchment canvas) — the shadow is a secondary reinforcement. This parchment→surface elevation is the system's primary depth mechanism.

**Level 2 — Input focus**: `border-field + ring-1 ring-field/20` on ChatInput. No shadow added — focus is communicated through border color change only.

**Level 3 — Modal overlay**: `bg-black/50` mobile sidebar overlay. Full-screen.

**Elevation philosophy**: Flat-first. Depth through surface-tone (canvas→surface), not shadow stacking. This is correct for outdoor readability — heavy shadows reduce legibility on bright screens. Preserve this discipline.

#### Decorative depth

None present. No gradient meshes, no atmospheric washes, no background patterns. **This is signal, not absence**: the design earns its mood through surface tone and color identity alone. Introducing decorative depth (e.g., a hero gradient) would violate the brand's functional stance.

### 2.6 Borders

- Default: `1px solid #F3F4F6` (`border-gray-100`) on cards — very subtle, almost invisible in bright light
- Interactive: `1px solid #E5E7EB` (`border-gray-200`) on inputs
- Focus: `border-field` (#2D6A4F) + `ring-1 ring-field/20`
- HC mode: `2px solid #000000` (all borders reinforced)

**Outdoor concern**: `border-gray-100` (#F3F4F6) card borders may disappear in high glare. Recommend upgrading to `border-gray-200` (#E5E7EB) minimum for advisory cards in field conditions.

### 2.7 Accessibility Quick-Check

**Key contrast pairs (computed):**

| Pair | Ratio | WCAG | Outdoor 7:1 |
|---|---|---|---|
| `text-primary` (#1C1917) on `canvas` (#F7F4EF) | 16.03:1 | AAA ✅ | ✅ |
| `text-primary` on `surface` (#FFFFFF) | 17.47:1 | AAA ✅ | ✅ |
| `text-body` (#374151) on `surface` | 10.27:1 | AAA ✅ | ✅ |
| `text-muted` (#4B5563) on `canvas` | 6.93:1 | AA ✅ | ❌ (0.1 short) |
| `primary` (#2D6A4F) on `surface` (text use) | 6.35:1 | AA ✅ | ❌ |
| `primary-dark` (#1B4332) on `surface` (text use) | 11.08:1 | AAA ✅ | ✅ |
| `danger` (#CC2936) bg + white text (current badge) | 3.94:1 | ❌ FAIL | ❌ |
| `danger-dark` (#9B1E29) text on `surface` | 8.02:1 | AAA ✅ | ✅ |
| `secondary` (#E9A228) bg + `text-primary` text | 8.09:1 | AAA ✅ | ✅ |
| White text on `sidebar-bg` (#1B4332) | 11.08:1 | AAA ✅ | ✅ |

**Three required fixes** based on outdoor 7:1 target:
1. `bg-arred text-white` → `bg-danger/10 border-danger/30 text-danger-dark` (Low badge)
2. `text-gray-600` → `text-gray-700` for all advisory body labels
3. `{colors.primary}` as inline text → switch to `{colors.primary-dark}`

---

## 3. Components Inventory

### 3.1 Generic Components

#### Button
- **Variants**: primary (bg-field), secondary (bg-harvest + text-charcoal), danger (bg-arred), ghost (transparent + border-field)
- **Sizes**: sm (`px-3 py-1.5`), md (`px-4 py-2.5`), lg (`px-6 py-3`)
- **States**: default, loading (with Spinner), disabled (opacity-50)
- **Touch target**: ✅ `min-h-touch` (44px) applied
- **Radius**: `{rounded.control}` (8px) — `rounded-lg`
- **Confidence**: ✅ high (well-implemented primitive)

#### Chat Input
- **Behavior**: Auto-resizing textarea (scrollHeight capped at 120px), Enter = submit, Shift+Enter = newline
- **States**: idle, focused (border-field + ring), disabled (opacity-50), error (empty-submit pulse)
- **Container radius**: currently `rounded-2xl` (16px) → should move to `{rounded.card}` (12px) per consolidation
- **Send button**: `w-9 h-9` (36px) — ❌ FAILS 44px touch target. Fix: `w-11 h-11` (44px)
- **Decorative icons** (paperclip, mic): non-interactive `<span>` with `aria-hidden` — correct
- **Confidence**: ✅ high

#### Suggestion Chips
- **Welcome chips**: `min-h-touch` applied ✅ — 44px
- **Mid-chat chips**: `py-1.5 px-3 text-xs` — effective height ~32px ❌ FAILS 44px. Add `min-h-touch`
- **Radius**: `rounded-full` (pill) — appropriate for chips
- **Confidence**: ✅ high (welcome) / ❌ (mid-chat touch target)

#### Sidebar Nav Item
- **Height**: `py-2.5` + text = ~40px ⚠️ borderline (fails strict 44px)
- **Fix**: bump to `py-3` (12px top + 12px bottom = ~44px with 18px icon)
- **Confidence**: ✅ high (pattern is correct, measurement is tight)

#### Hamburger (mobile menu)
- **Size**: `w-9 h-9` = 36×36px ❌ FAILS 44px
- **Fix**: `w-11 h-11` = 44×44px
- **Confidence**: ✅ high (simple fix)

#### Session Delete Button (sidebar)
- **Size**: `p-1` icon-only = ~24×24px ❌ FAILS 44px critically
- **Fix**: `p-2.5` minimum, or use `w-8 h-8` (32px) with `hover:bg-white/15` as acceptable minimum for icon-only secondary action
- **Confidence**: ✅ high

#### Alert / AlertBanner
- Seen: error alert (dismissible), AlertBanner for pre-fills. Standard pattern.
- **Confidence**: ⚠️ medium (not fully traced)

#### Spinner
- Used as full-screen loading for session loads. Should be replaced by skeleton states for chat history loading.
- **Confidence**: ✅ high (identified usage)

### 3.2 Signature Components

#### AdvisoryCard (PRIMARY SIGNATURE)
The defining UI element of the product. No equivalent in generic chat UIs.

- **What it is**: A structured multi-section card delivering a pest/disease advisory. Sections: ConfidenceBadge, NLIConfidenceBadge, crop chip, ContextMetaBar, ConfidenceExplainer, EscalationCard, LowConfidenceBanner, WarningsBanner, ProblemSummary, LikelyCauses (accordion), RecommendedActions (numbered list), ProductsRates (cards/table), CitationsSection (collapsible), FeedbackWidget.
- **Why it's signature**: This is the product's primary value delivery. The structured breakdown (causes → actions → products) is the RAG advisory engine's output made readable.
- **Critical problem — hierarchy inversion**: The card currently renders DIAGNOSTIC METADATA (confidence badges, NLI score, confidence explanation) BEFORE the ACTIONABLE CONTENT (ProblemSummary, RecommendedActions). A farmer on a tractor stop scrolls past 4 metadata sections before seeing "what to do." This is the #1 UX issue.

**Proposed new render order (Actions First):**
```
1. [Crop chip] + [Context meta] — quick orientation (1 line, flex-wrap)
2. ProblemSummary — what's happening (VISIBLE IMMEDIATELY)
3. RecommendedActions — what to do NOW (PRIORITY 1 CONTENT)
4. ProductsRates — what products / rates to apply
5. LikelyCauses — collapsible accordion, defaultOpen: false
6. EscalationCard — if escalation present (safety-critical)
7. WarningsBanner — if warnings present
8. ConfidenceBadge + NLIConfidenceBadge — trust signal row (now secondary)
9. ConfidenceExplainer — collapsible or small muted text
10. LowConfidenceBanner — deemphasized at bottom
11. CitationsSection — collapsible
12. FeedbackWidget
```

- **Composition**: white surface on canvas, `{rounded.card}` (12px), `{elevation.L1}`, `max-w-2xl`, `p-4`
- **Where it appears**: Chat history, replacing assistant text bubble for in-scope queries
- **Confidence**: ✅ high

#### LikelyCauses Accordion
- Collapsible per-cause with `min-h-touch` triggers. Good pattern.
- Currently positioned ABOVE RecommendedActions — needs to move below.

#### ARCountyMap (admin-only)
- D3/react-simple-maps choropleth for drift reports
- Signature admin component, not farmer-facing
- **Confidence**: ⚠️ medium (not fully audited)

---

## 4. Layout & Composition

### 4.1 Grid & Containers

- **App shell**: `flex h-[100dvh] overflow-hidden` — correctly handles iOS viewport units
- **Sidebar**: fixed 256px (`w-64`) on desktop, full-height drawer on mobile. Field-dark bg.
- **Header**: `h-14` (56px), white, `border-b`. App name + hamburger (mobile) + profile icon.
- **Main**: `flex-col flex-1 overflow-hidden` — full remaining height
- **ChatHistory**: `flex-1 overflow-y-auto px-4 py-3` — scrollable, advisory cards render at `max-w-2xl`
- **ChatInput**: `flex-shrink-0` — pinned bottom. Correctly uses `safe-area-inset-bottom` for iOS notch.
- **Advisory cards**: `max-w-2xl` — 672px max. Left-aligned within the scroll column.
- **Advisory card content**: currently left-aligned list without visual section separation — needs vertical breathing room per section.

### 4.2 Composition Patterns

- **Full-height column**: Chat interface (`flex-col h-full`)
- **Welcome state**: Centered column with icon + h1 + suggestion chips
- **Mid-chat**: Scrollable message list + pinned chip row + pinned input
- **Sidebar drawer**: Mobile: overlay with `bg-black/50` + slide-in. Desktop: static left column.
- No hero pattern — this is a tool, not a marketing surface.

### 4.3 Responsive Behavior

#### Breakpoints

| Name | Width | Key changes |
|---|---|---|
| Mobile | < 768px (`md` breakpoint) | Sidebar hides (drawer), hamburger visible, ProductsRates shows card stack |
| Desktop | ≥ 768px | Sidebar static 256px, ProductsRates shows table, hamburger hidden |

*Only two breakpoints defined in the codebase: mobile (<md) and desktop (≥md). No tablet-specific layout.*

#### Touch Targets Audit

| Element | Current size | Meets 44px? | Fix |
|---|---|---|---|
| Button (all variants) | `min-h-touch` = 44px | ✅ | — |
| Welcome chips | `min-h-touch py-2` | ✅ | — |
| Mid-chat chips | `py-1.5 px-3` (~32px) | ❌ | Add `min-h-touch` |
| Send button | `w-9 h-9` = 36px | ❌ | Change to `w-11 h-11` |
| Hamburger button | `w-9 h-9` = 36px | ❌ | Change to `w-11 h-11` |
| Sidebar nav items | `py-2.5` (~40px) | ⚠️ | Bump to `py-3` |
| Session delete btn | `p-1` (~24px) | ❌ | Change to `min-w-[44px] min-h-touch` |
| Header profile icon | `w-9 h-9` = 36px | ❌ | Change to `w-11 h-11` |
| LikelyCauses trigger | `py-3 px-4` + `min-h-touch` | ✅ | — |
| CitationsSection toggle | `min-h-touch` | ✅ | — |

**5 failures**. Highest priority: send button (used every interaction), hamburger (entry point on mobile).

#### Collapsing Strategy

- **Sidebar**: hamburger → `translate-x-full`/`translate-x-0` slide-in on mobile. ✅
- **ProductsRates**: card stack on mobile, table on desktop. ✅ Good responsive split.
- **Advisory card**: no structural change across breakpoints — `max-w-2xl` works on both.
- **Suggestion chips**: `overflow-x-auto` horizontal scroll on mobile. Acceptable.

### 4.4 Image Behavior

- **No photography** in the application. Pure UI.
- **Icons**: Custom SVG stroke-only style (consistent with Heroicons Outline). Stroke width: 2px standard, 2.5px on CTA (send button). ✅ Consistent convention.
- **App icon** (welcome state): 56px square `rounded-2xl`, `bg-field`, inline SVG (sparkle/star). The product's only branded "logomark." Functional, not illustrative.
- **Emoji**: One emoji used — `📞` in EscalationCard. Should be replaced with an SVG icon for consistent rendering across platforms.

---

## 5. Reconstruction Notes

### Suggested Stack

**React 19 + Vite + Tailwind CSS** (confirmed — existing stack)

Justification: Classes like `flex-1`, `min-h-touch`, `bg-field/10`, `rounded-card`, `text-charcoal`, `dark:bg-hc-sidebar-bg` confirm Tailwind with custom theme extensions. No shadcn/ui — custom primitive components (`Button.jsx`, `Input.jsx`, `Select.jsx`).

### Quick Wins

- Palette and typography already correct — 70% of outdoor-readiness is done.
- `min-h-touch: 44px` already in Tailwind config — it's just not applied to all touch targets.
- HC (high-contrast) mode is thoughtfully implemented — needs no overhaul.
- `safe-area-inset-bottom` in ChatInput already handles iOS notch.
- ProductsRates mobile/desktop split already done well.

### Tricky Bits

- **AdvisoryCard reorder**: The section restructuring requires changing the render order in `AdvisoryCardInner` without breaking the SuppressedNotice gating logic (currently `!response.suppressed && <EscalationCard>`).
- **Confidence badge contrast**: The `bg-arred text-white` pattern is in `ConfidenceBadge.jsx` AND repeated in `NLIConfidenceBadge.jsx` and `EscalationCard.jsx` — fix all three.
- **Offline state**: Requires new infrastructure (service worker or cache API) — not just a UI pattern.
- **Smart Card numbers**: Needs `font-mono` added to Tailwind config before the `data-mono` token can be used.
- **Emoji → SVG**: `EscalationCard.jsx` uses 📞 — platform rendering varies.

### Implicit States to Define

- Advisory card **loading/streaming state** — currently just TypingIndicator. A skeleton that pre-renders the card structure would reduce perceived latency.
- **Offline state** for the whole app — no current handling.
- **Session cache state** — "loaded from cache" vs. "live" session.
- Input **empty-submit** — currently a transient text message. Consider a shake animation.
- **Empty sessions list** — currently shows `t.noSessions` text. Could show a prompt.

### Confidence Map

| Layer | Confidence | Why |
|---|---|---|
| Identity | ✅ high | Clear codebase + naming conventions |
| Colors | ✅ high | Exact hex values from tailwind.config.js |
| Typography | ✅ high | Font family from config; scale inferred from class names |
| Spacing | ✅ high | Systematic Tailwind multiples throughout |
| Components | ✅ high | All components read directly |
| Layout | ⚠️ medium | No runtime screenshot; responsive inferred from class analysis |

---

## 6. Do's and Don'ts

### Do

1. **Reserve `{colors.primary}` (#2D6A4F) for interactive CTA surfaces** (button bg, send button bg, focus rings, High-confidence badge bg). For `{colors.primary}`-colored TEXT (citations, links), use `{colors.primary-dark}` (#1B4332) to clear the 7:1 outdoor threshold.

2. **Use `{colors.canvas}` (#F7F4EF) as the app background; use `{colors.surface}` (#FFFFFF) only for elevated surfaces** (advisory cards, header, input containers). The parchment→white surface lift IS the elevation model. Don't introduce `{colors.surface}` at the canvas layer.

3. **Apply `min-h-touch` (44px) to every tappable element without exception**. The token exists in the Tailwind config — use it. Field use with dirty/gloved hands makes sub-44px targets functionally unusable.

4. **Render advisory sections Actions-First**: ProblemSummary → RecommendedActions → ProductsRates → (collapsed) LikelyCauses → Confidence signals. Farmers read top-down under time pressure. The current order (confidence metadata first) is inverted.

5. **Use uppercase `tracking-wider` labels** (the `{typography.label}` token: 11px, 600 weight, 0.06em) for section group headers (e.g., "RECENT CONVERSATIONS", "SOURCES"). This is the one typographic sophistication in the system — extend it consistently to advisory section group headers.

6. **Use `{colors.secondary}` (#E9A228) with `{colors.text-primary}` (#1C1917)** — never with white text. The amber fails white-text contrast at 2.16:1. Current `ConfidenceBadge Medium` correctly uses `text-charcoal` — maintain this everywhere.

7. **Set numerical agricultural data** (application rates, NPK values, PHI, weather metrics) in `{typography.data-mono}` (ui-monospace). Numbers in proportional fonts misalign in multi-row comparisons; mono guarantees column alignment without a table wrapper.

### Don't

1. **Don't render confidence metadata (ConfidenceBadge, NLIConfidenceBadge, ConfidenceExplainer) above the advisory's actionable body content**. The farmer's first scroll should reach RecommendedActions, not a numerical NLI score they may not understand.

2. **Don't use `bg-danger text-white` on small (`text-sm` or `text-xs`) elements**. `{colors.danger}` (#CC2936) with white text achieves only 3.94:1 — fails AA. Use `bg-danger/10 border-danger/30 text-danger-dark` instead for the Low confidence badge.

3. **Don't add a fourth accent color to the palette**. The system semantics are: green = primary/success, amber = caution/secondary, red = danger/Low confidence, terracotta = poultry/neutral-warm. New accent colors break the crop-category color coding. If you need a new semantic color, map it to an existing scale stop (e.g., use `field-light` for informational states rather than blue).

4. **Don't introduce heavy drop shadows** (`shadow-lg`, `shadow-xl`). The elevation system is flat-first: parchment→white surface lift + `shadow-sm` max. Heavy shadows reduce contrast and look incorrect at outdoor luminance levels.

5. **Don't mix `{rounded.pill}` and `{rounded.control}` on the same component**. Pill radius belongs exclusively to semantic chips (confidence badges, crop chips, suggestion chips, avatar). Structural containers (cards, input container, buttons, accordions) use `{rounded.card}` or `{rounded.control}`. Never use `rounded-2xl` (16px) — it sits between `{rounded.card}` (12px) and pill and belongs to neither scale.

6. **Don't add loading spinners for cached content**. Full-screen `<Spinner />` for session loading should be replaced by skeleton frames. Intrusive spinners block the user's orientation; skeletons communicate structure while data loads.

7. **Don't use emoji in advisory UI** (e.g., `📞` in EscalationCard). Cross-platform emoji rendering is inconsistent. Replace with the Heroicons `phone` SVG in the same stroke style used throughout the app.

---

## 7. Design Proposals

### 7.1 Smart Card — NPK / Weather Trend Component

A new reusable component for structured agricultural data (NPK soil levels, weather data from NOAA/Open-Meteo). Used in ContextMetaBar and future drift reports.

```
┌─────────────────────────────────────────┐  ← {rounded.card}, border-default, shadow-L1
│ 🌱 Soil Nutrient Snapshot  · 2h ago ↻  │  ← header: label (mono), timestamp (caption), sync icon
│  ─────────────────────────────────────  │  ← border-subtle divider
│  [N]    [P]    [K]    [pH]             │  ← metric chips row
│  142    38     97     6.4             │  ← data-mono, text-primary, large (18px)
│  ppm    ppm    ppm                    │  ← caption below each value
│  🟢     🟡     🔴                      │  ← threshold indicator dots (field/secondary/danger)
│  ─────────────────────────────────────  │  ← border-subtle divider
│  ▼ Trend (7-day)           [Collapse]  │  ← collapsible detail toggle, min-h-touch
│    [sparkline or data table here]      │
└─────────────────────────────────────────┘

States:
  - Live: normal render
  - Cached: amber "From cache · 3h ago" badge top-right  ← {colors.secondary-dark} on secondary/10
  - Offline: gray "Offline" badge, data still shown
  - Loading: skeleton (gray-100 animated pulse replacing values)
  - Error: "Data unavailable" with retry button (ghost, field color)
```

**Implementation spec:**
```jsx
// Tailwind classes
<div className="bg-white border border-gray-200 rounded-card shadow-sm p-4">
  <div className="flex items-center justify-between mb-3">
    <span className="text-[11px] font-semibold text-gray-500 uppercase tracking-wider">
      {title}
    </span>
    <CacheBadge status={cacheStatus} timestamp={timestamp} />
  </div>
  <div className="grid grid-cols-4 gap-3">
    {metrics.map(m => (
      <MetricChip key={m.key} label={m.label} value={m.value}
        unit={m.unit} threshold={m.threshold} />
    ))}
  </div>
  {expanded && <TrendDetail data={trendData} />}
</div>
```

**MetricChip**: `text-lg font-mono font-medium text-charcoal` for value; `text-xs text-gray-500` for label/unit; threshold dot `w-2 h-2 rounded-full` in field/secondary/danger color.

### 7.2 Offline-First UI Patterns

**Principle**: Never block the UI for network state. Show data from cache immediately; indicate sync status non-intrusively.

#### Pattern A — Sync Status Bar (top of app, below header)

```
┌─────────────────────────────────────────────────────────┐
│ ● Offline — showing cached data   [Retry] ↺             │  ← 28px tall
│                                                          │
└─────────────────────────────────────────────────────────┘
```

- Height: 28px (`h-7`)
- Background: `{colors.canvas}` with `border-b border-gray-100`
- Offline: amber left dot + `text-xs text-gray-600` message + ghost `[Retry]` button
- Syncing: animated green spinner + "Syncing…"
- Synced: hidden (don't show "connected" — absence of bar = connected)
- Implementation: `useSyncStatus` hook reading `navigator.onLine` + last-fetch timestamp

#### Pattern B — Cache Availability Badge on Sessions

Sessions list items show a small dot indicator:
- `●` green (`{colors.primary-light}`) = "Available offline"  
- `●` gray (`border-gray-300`) = "Online only"

Small `text-[10px]` badge beside session preview text. Does NOT replace session title — overlaid.

#### Pattern C — Advisory Card Streaming Skeleton

Replace `<TypingIndicator />` with a skeleton frame matching the AdvisoryCard structure:

```
┌─────────────────────────────────────────┐
│ [████████] [████] [███]                 │  ← badge row skeleton
│                                          │
│ [████████████████████████]              │  ← heading skeleton
│ [████████████████████]                  │  ← body skeleton 1
│ [██████████████████████████]            │  ← body skeleton 2
│                                          │
│ ① [████████████████████]               │  ← action item skeleton
│ ② [████████████]                       │
└─────────────────────────────────────────┘
```

Skeleton uses `bg-gray-100 animate-pulse rounded` blocks. Matches real AdvisoryCard proportions so the layout doesn't jump when content arrives.

#### Pattern D — Offline Input State

When `navigator.onLine === false`, show a non-blocking amber banner above ChatInput:

```
📶 You're offline. Your question will be sent when connection is restored.
```

- Do NOT disable the input — let the user type
- Queue the message (store in `sessionStorage`), send on reconnect
- Remove the banner immediately on reconnect

### 7.3 Advisory Card Visual Hierarchy Redesign

Current vs. Proposed layout:

```
CURRENT (metadata-first):          PROPOSED (actions-first):
────────────────────────           ────────────────────────
[High] [0.82] [🌾 Rice]            [🌾 Rice] · Concordia, AR
Context: Concordia, AR             ──────────────────────────
"Confidence: The NLI model…"       PROBLEM SUMMARY
⚠️ Escalation: Call ext…           [what's happening]
⚠️ Low Confidence Banner           ──────────────────────────
─────────────────────              RECOMMENDED ACTIONS ← ABOVE FOLD
PROBLEM SUMMARY ← too far down     ① Do this
[what's happening]                 ② Do this
─────────────────────              ③ Do this
CAUSES (accordion)                 ──────────────────────────
ACTIONS                            PRODUCTS & RATES
PRODUCTS                           [cards / table]
CITATIONS (collapsed)              ──────────────────────────
FEEDBACK                           ▼ Likely Causes (collapsed)
                                   ──────────────────────────
                                   ⚠️ Escalation (if present)
                                   ──────────────────────────
                                   [High] [0.82]  ← trust signal, secondary
                                   ──────────────────────────
                                   ▼ Sources (collapsed)
                                   👍 👎
```

The confidence signals move to the BOTTOM of the card — still present for transparency, but not the first thing a farmer reads.

---

## 8. Implementation Roadmap

Prioritized refactor sequence for the React/Tailwind codebase. Chat interface is addressed first per the user's constraint.

### Phase 1 — Chat & Advisory UX (2–3 days)
**Files**: `AdvisoryCard.jsx`, `ChatInput.jsx`, `ChatPage.jsx`, `Header.jsx`, `Sidebar.jsx`

1. **AdvisoryCardInner render reorder** — move ProblemSummary and RecommendedActions to top; move confidence metadata to bottom. The suppressed-state gating (`!response.suppressed && <EscalationCard>`) must move with EscalationCard to its new position.
2. **Fix 5 touch targets**:
   - `ChatInput.jsx` send button: `w-9 h-9` → `w-11 h-11` (44px)
   - `Header.jsx` hamburger + profile icon: `w-9 h-9` → `w-11 h-11`
   - `ChatPage.jsx` mid-chat chips: add `min-h-touch`
   - `Sidebar.jsx` nav items: `py-2.5` → `py-3`
   - `Sidebar.jsx` session delete: `p-1` → `p-2` + `min-w-[36px] min-h-[36px]` (acceptable for secondary icon-only action)
3. **Fix Low confidence badge contrast**: `ConfidenceBadge.jsx` — change Low style to `bg-arred/10 text-arred-dark border border-arred/30`

### Phase 2 — Design Token Cleanup (1 day)
**Files**: `tailwind.config.js`

1. Add `fontFamily.mono` → `['ui-monospace', 'Geist Mono', 'monospace']`
2. Remove `rounded-2xl` usage (chat input container → `rounded-card`)
3. Upgrade `emerald-200` in Sidebar to a config token (use `primary-light` #40916C instead)
4. Add `fontSize['label']` = 11px for the section label scale

### Phase 3 — Color Outdoor Audit (1 day)
**Files**: `AdvisoryCard.jsx`, `ProductsRates.jsx`, `ProblemSummary.jsx`, `LikelyCauses.jsx`, `CitationsSection.jsx`

1. Replace `text-gray-600` with `text-gray-700` throughout advisory components (bumps to 10.27:1 on surface)
2. Replace inline `text-field` link/citation text with `text-field-dark` (from 6.35:1 → 11.08:1)
3. Replace card `border-gray-100` with `border-gray-200` for legibility in bright light
4. Bump advisory card `p-4` section headings to `-tracking-[0.01em]` for tighter outdoor legibility

### Phase 4 — Offline-First Patterns (2–3 days)
**Files**: New `hooks/useSyncStatus.js`, `components/ui/SyncStatusBar.jsx`, `components/ui/OfflineBadge.jsx`, `TypingIndicator.jsx` → `AdvisoryCardSkeleton.jsx`

1. `useSyncStatus` hook: wraps `navigator.onLine` + `online`/`offline` events
2. `SyncStatusBar` component: 28px bar below Header, hidden when online, amber+retry when offline
3. Replace `<TypingIndicator />` with `<AdvisoryCardSkeleton />` in ChatHistory
4. Add offline badge logic to `SessionListItem`
5. Add offline queue to `useSSEQuery` (store pending messages in sessionStorage)

### Phase 5 — Smart Card + Data Components (2 days)
**Files**: New `components/ui/SmartCard.jsx`, `components/ui/MetricChip.jsx`, update `ContextMetaBar.jsx`, update `ProductsRates.jsx`

1. Build `SmartCard` + `MetricChip` with the spec in Section 7.1
2. Apply `font-mono` to all rate/dosage values in `ProductsRates.jsx` (td values)
3. Update `ContextMetaBar` to use SmartCard wrapper for weather/soil data when available
4. Replace `📞` emoji in `EscalationCard.jsx` with `PhoneIcon` SVG (Heroicons outline)

---

## 9. Open Questions

1. **Service worker / cache infrastructure**: Offline patterns in Section 7.2 require a service worker (Workbox) or explicit IndexedDB cache. Does the project have a planned approach, or should this be scoped as a future milestone?
2. **Advisory card streaming**: Does the SSE stream arrive as a complete advisory object at once, or section-by-section? The skeleton design in Section 7.2 assumes complete-on-arrival. If streaming is section-by-section, the skeleton should progressively reveal.
3. **ContextMetaBar weather data**: Does this component ever receive live NPK/weather values from the NOAA/SSURGO integration, or only metadata (county, crop)? The SmartCard spec depends on what data is actually available.
4. **AdvisoryCard on desktop**: The `max-w-2xl` (672px) constraint on a wide desktop produces a narrow advisory column with large empty gutters. Is this intentional (readability over width) or a layout gap?
5. **NLIConfidenceBadge**: The `NLIConfidenceBadge` exposes a 0–1 numeric score alongside the categorical `ConfidenceBadge`. For a farmer audience, does a raw 0.82 score add value, or should this be gated behind an expandable "why?" toggle?
6. **grayscale functional test**: The user requested grayscale baseline. In grayscale, the three confidence levels (High/Medium/Low) map to: mid-gray/light-gray/dark-gray — the green badge becomes indistinguishable from the amber badge. Recommend testing and confirming textual label + shape/icon differentiation as the primary distinguisher (not color alone).

---

## 10. Companion Files

- [x] `design-tokens.json` — DTCG-format token file (see root directory)
- [ ] `design-a11y.md` — WCAG contrast table is inline in Section 2.7 of this document
- [ ] `design-screenshot.png` — not generated (codebase audit, no Playwright capture)

---

*Next logical step: run Phase 1 of the implementation roadmap — the advisory card reorder and touch target fixes are the highest ROI changes and require no new infrastructure. Estimated 1 day of focused frontend work.*
