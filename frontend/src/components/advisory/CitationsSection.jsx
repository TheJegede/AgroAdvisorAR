import { useState } from 'react'
import { useLang } from '../../contexts/LangContext'

export default function CitationsSection({ citations }) {
  const { t } = useLang()
  const [open, setOpen] = useState(false)
  if (!citations?.length) return null

  return (
    <div className="mt-3 border-t border-gray-100 dark:border-t-2 dark:border-hc-border pt-3">
      <button
        onClick={() => setOpen((v) => !v)}
        className="text-sm text-field dark:text-hc-accent font-bold flex items-center gap-1 min-h-touch hover:underline"
      >
        {open ? t.hideSources : `${t.showSources} (${citations.length})`}
        <svg className={`w-3 h-3 transition-transform ${open ? 'rotate-180' : ''}`}
          fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
        </svg>
      </button>
      {open && (
        <ul className="mt-2 flex flex-col gap-1.5">
          {citations.map((c, i) => (
            <li key={i} className="text-xs text-gray-700 dark:text-hc-fg leading-relaxed">
              {c.url ? (
                <a href={c.url} target="_blank" rel="noopener noreferrer"
                  className="text-field-dark dark:text-hc-accent underline font-bold">
                  {c.document_title}
                </a>
              ) : (
                <span className="font-medium">{c.document_title}</span>
              )}
              {c.section && <span className="text-gray-700 dark:text-hc-fg"> — {c.section}</span>}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
