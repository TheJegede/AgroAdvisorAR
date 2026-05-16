import { useState } from 'react'
import { useLang } from '../../contexts/LangContext'

export default function LikelyCauses({ causes }) {
  const { t } = useLang()
  const [open, setOpen] = useState(new Set())

  function toggle(i) {
    setOpen((prev) => {
      const next = new Set(prev)
      next.has(i) ? next.delete(i) : next.add(i)
      return next
    })
  }

  if (!causes?.length) return null
  return (
    <div className="my-3">
      <h2 className="text-base font-semibold text-charcoal mb-2">{t.likelyCauses}</h2>
      <div className="flex flex-col gap-1">
        {causes.map((c, i) => (
          <div key={i} className="rounded-lg border border-gray-200 overflow-hidden">
            <button
              onClick={() => toggle(i)}
              className="w-full flex items-center justify-between px-4 py-3 text-left text-sm font-medium text-charcoal hover:bg-gray-50 min-h-touch transition-colors"
            >
              <span>{c.cause}</span>
              <svg
                className={`w-4 h-4 text-gray-400 transition-transform ${open.has(i) ? 'rotate-180' : ''}`}
                fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}
              >
                <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
              </svg>
            </button>
            {open.has(i) && (
              <div className="px-4 pb-3 bg-gray-50 text-sm text-gray-700 leading-relaxed border-t border-gray-200">
                {c.explanation}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}
