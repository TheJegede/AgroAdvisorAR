import { useLang } from '../../contexts/LangContext'

function Tractor() {
  return (
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
        <line x1="42" y1="27" x2="45" y2="24" stroke="currentColor" strokeWidth="1.5" />
      </g>

      {/* Wheels (Separated from jiggling body so they spin steadily) */}
      <g className="wheel-back text-gray-800 dark:text-hc-fg">
        <circle cx="32" cy="38" r="10" fill="currentColor" />
        <circle cx="32" cy="38" r="4" className="fill-white dark:fill-hc-surface" />
        <line x1="32" y1="28" x2="32" y2="48" stroke="currentColor" strokeWidth="1.5" />
        <line x1="22" y1="38" x2="42" y2="38" stroke="currentColor" strokeWidth="1.5" />
      </g>

      <g className="wheel-front text-gray-800 dark:text-hc-fg">
        <circle cx="64" cy="42" r="6" fill="currentColor" />
        <circle cx="64" cy="42" r="2.5" className="fill-white dark:fill-hc-surface" />
        <line x1="64" y1="36" x2="64" y2="48" stroke="currentColor" strokeWidth="1" />
        <line x1="58" y1="42" x2="70" y2="42" stroke="currentColor" strokeWidth="1" />
      </g>
    </svg>
  )
}

export default function QueryProgress({ stage }) {
  const { t } = useLang()
  const name = stage?.stage ?? 'searching'

  let caption = t.progressSearching
  if (name === 'sources_found') {
    caption = t.progressFoundSources.replace('{n}', String(stage?.count ?? 0))
  } else if (name === 'writing') {
    caption = t.progressWriting
  } else if (name === 'verifying') {
    caption = t.progressVerifying
  }

  const titles = name === 'sources_found' ? (stage?.titles ?? []) : []

  return (
    <div
      className="flex flex-col items-center gap-2 p-3 bg-white dark:bg-hc-surface rounded-card shadow-sm border border-gray-100 dark:border-2 dark:border-hc-border w-64 my-2"
      role="status"
      aria-label="Loading response"
    >
      <Tractor />
      <p className="text-sm text-gray-600 dark:text-hc-fg font-medium text-center" aria-live="polite">{caption}</p>
      {titles.length > 0 && (
        <ul className="text-xs text-gray-500 dark:text-hc-fg self-stretch list-disc pl-5 mt-1 border-t border-gray-50 dark:border-hc-border pt-2">
          {titles.map((title, i) => (
            <li key={i} className="truncate" title={title}>
              {title}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
