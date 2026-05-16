import { useState } from 'react'
import { useLang } from '../../contexts/LangContext'

export default function ConfidenceExplainer({ explanation }) {
  const { t } = useLang()
  const [open, setOpen] = useState(false)
  if (!explanation) return null

  return (
    <div className="mt-1">
      <button
        onClick={() => setOpen((v) => !v)}
        className="text-xs text-gray-500 dark:text-hc-fg underline min-h-touch flex items-center"
      >
        {t.whyConfidence}
      </button>
      {open && (
        <p className="text-xs text-gray-600 dark:text-hc-fg italic mt-1 leading-relaxed">{explanation}</p>
      )}
    </div>
  )
}
