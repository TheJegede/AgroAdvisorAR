# Implementation Plan — Cartoonish Tractor Loader Animation

This plan implements a cartoonish, theme-adaptive tractor loader animation to replace the default bouncing dots when RAG retrieval and response generation are streaming.

## Context

The current streaming phase is represented by a generic three-dot bouncing loader in **[TypingIndicator.jsx](file:///c:/Users/jeged/Downloads/AgroAdvisor/frontend/src/components/chat/TypingIndicator.jsx)**. To make the interface feel premium, modern, and aligned with the agricultural theme (Arkansas farming), we will replace this indicator with a custom CSS-animated SVG tractor driving past crops.

### Theme & Contrast Strategy

The codebase **does not have a separate dark mode**. Instead, **[tailwind.config.js](file:///c:/Users/jeged/Downloads/AgroAdvisor/frontend/tailwind.config.js)** configures Tailwind's `dark:` selector to target High Contrast mode:
```javascript
darkMode: ['selector', '[data-theme="hc"] &']
```
Therefore, any CSS class prefixed with `dark:` applies **specifically when High Contrast (hc) mode is enabled** (when `<html data-theme="hc">` is set). The blueprint is calibrated to map:
- **Light Mode**: Emerald tractor body (`text-field`), green crops (`text-emerald-500`), brown ground line, and slate wheels.
- **High Contrast Mode (`dark:`)**: Accent-blue tractor body (`dark:text-hc-accent`), black crops (`dark:text-hc-fg`), black ground line (`dark:text-hc-border`), and black wheels (`dark:text-hc-fg`).

---

## Proposed Changes

### Frontend Component

#### [MODIFY] [TypingIndicator.jsx](file:///c:/Users/jeged/Downloads/AgroAdvisor/frontend/src/components/chat/TypingIndicator.jsx)

- Replace the entire content of `TypingIndicator.jsx` with the custom SVG tractor.
- Keep the exported component name as `TypingIndicator` (default export) so we do **not** need to touch the import statements in **[ChatHistory.jsx](file:///c:/Users/jeged/Downloads/AgroAdvisor/frontend/src/components/chat/ChatHistory.jsx)**.
- Embed the animation CSS keyframes inside a `<style>` block in the SVG to keep the component fully self-contained.
- Ensure the colors dynamically map to light mode and high-contrast mode (`dark:bg-hc-surface`, `dark:border-hc-border`, `dark:text-hc-accent`) using Tailwind CSS.

---

## Code Blueprint for `TypingIndicator.jsx`

```jsx
export default function TypingIndicator() {
  return (
    <div 
      className="flex items-center justify-center p-3 bg-white dark:bg-hc-surface rounded-card shadow-sm border border-gray-100 dark:border-2 dark:border-hc-border w-48 my-2"
      role="status" 
      aria-label="Tractor driving, loading response"
    >
      <svg 
        viewBox="0 0 120 60" 
        width="96" 
        height="48" 
        className="text-field dark:text-hc-accent" 
        fill="currentColor"
      >
        <defs>
          <style>{`
            .tractor-body {
              animation: tractor-bounce 0.45s ease-in-out infinite;
            }
            @keyframes tractor-bounce {
              0%, 100% { transform: translateY(0); }
              50% { transform: translateY(-1.5px); }
            }

            .wheel-back {
              animation: spin 0.8s linear infinite;
              transform-origin: 32px 38px;
            }
            .wheel-front {
              animation: spin 0.8s linear infinite;
              transform-origin: 64px 42px;
            }
            @keyframes spin {
              from { transform: rotate(0deg); }
              to { transform: rotate(360deg); }
            }

            .smoke-puff-1 {
              animation: smoke 1.2s ease-out infinite;
              transform-origin: 62px 12px;
            }
            .smoke-puff-2 {
              animation: smoke 1.2s ease-out infinite 0.6s;
              transform-origin: 62px 12px;
            }
            @keyframes smoke {
              0% { transform: translate(0, 0) scale(0.3); opacity: 0; }
              20% { opacity: 0.8; }
              80% { opacity: 0.2; }
              100% { transform: translate(-8px, -16px) scale(1.8); opacity: 0; }
            }

            .crop-row {
              animation: scroll-crops 1.2s linear infinite;
            }
            @keyframes scroll-crops {
              0% { transform: translateX(0); }
              100% { transform: translateX(-20px); }
            }
          `}</style>
        </defs>

        {/* Background Crops (Scrolling right-to-left) */}
        <g className="crop-row text-emerald-500 dark:text-hc-fg">
          {[-20, 0, 20, 40, 60, 80, 100, 120, 140].map((x) => (
            <path 
              key={x} 
              d={`M ${x} 48 Q ${x+2} 42 ${x+5} 44 M ${x} 48 Q ${x-2} 43 ${x-4} 45`} 
              stroke="currentColor" 
              strokeWidth="1.5" 
              strokeLinecap="round" 
              fill="none" 
            />
          ))}
        </g>

        {/* Ground Line */}
        <line 
          x1="0" 
          y1="48" 
          x2="120" 
          y2="48" 
          stroke="#78350F" 
          strokeWidth="2" 
          strokeLinecap="round" 
          className="text-amber-800 dark:text-hc-border" 
        />

        {/* Exhaust Smoke Puffs */}
        <circle cx="62" cy="10" r="2.5" className="smoke-puff-1 fill-gray-300 dark:fill-hc-fg" />
        <circle cx="62" cy="10" r="2.5" className="smoke-puff-2 fill-gray-300 dark:fill-hc-fg" />

        {/* Tractor Body */}
        <g className="tractor-body">
          <line x1="62" y1="24" x2="62" y2="12" stroke="currentColor" strokeWidth="2" />
          <path d="M 46 24 H 68 V 38 H 46 Z" fill="currentColor" />
          <path d="M 24 38 V 20 H 42 L 46 24 V 38 Z" fill="none" stroke="currentColor" strokeWidth="2" strokeLinejoin="round" />
          <rect x="28" y="24" width="10" height="10" className="fill-sky-100 dark:fill-hc-bg stroke-current" strokeWidth="1.5" />
          <line x1="42" y1="27" x2="45" y2="24" stroke="currentColor" stroke-width="1.5" />
        </g>

        {/* Wheels (Separated from jiggling body so they spin steadily) */}
        <g className="wheel-back text-gray-800 dark:text-hc-fg">
          <circle cx="32" cy="38" r="10" fill="currentColor" />
          <circle cx="32" cy="38" r="4" className="fill-white dark:fill-hc-surface" />
          <line x1="32" y1="28" x2="32" y2="48" stroke="currentColor" stroke-width="1.5" />
          <line x1="22" y1="38" x2="42" y2="38" stroke="currentColor" stroke-width="1.5" />
        </g>

        <g className="wheel-front text-gray-800 dark:text-hc-fg">
          <circle cx="64" cy="42" r="6" fill="currentColor" />
          <circle cx="64" cy="42" r="2.5" className="fill-white dark:fill-hc-surface" />
          <line x1="64" y1="36" x2="64" y2="48" stroke="currentColor" stroke-width="1" />
          <line x1="58" y1="42" x2="70" y2="42" stroke="currentColor" stroke-width="1" />
        </g>
      </svg>
    </div>
  )
}
`````

---

## Verification Plan

### Automated Tests
- Run `cd frontend && npm run test` to verify Vitest component tests pass.
- Run `cd frontend && npm run lint` to verify ESLint passes with 0 errors.

### Manual Verification
- Start the Vite dev server (`npm run dev`) and post a query to the chatbot.
- Verify the tractor animation renders in the message list while streaming the response.
- Toggle between **Light**, **Dark**, and **High Contrast** modes in the sidebar and verify that the tractor colors change appropriately to match the UI themes.
