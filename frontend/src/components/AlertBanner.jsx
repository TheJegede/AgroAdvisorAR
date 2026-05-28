// frontend/src/components/AlertBanner.jsx
import { useState, useEffect } from 'react'
import api from '../lib/api'

export function selectMessage(alert) {
  return alert?.message ?? ''
}

export default function AlertBanner({ onPrefill }) {
  const [alerts, setAlerts] = useState([])

  useEffect(() => {
    api.get('/alerts')
      .then(res => setAlerts(res.data))
      .catch(() => {})
  }, [])

  function dismiss(id) {
    api.patch(`/alerts/${id}/dismiss`).catch(() => {})
    setAlerts(prev => prev.filter(a => a.id !== id))
  }

  if (alerts.length === 0) return null

  return (
    <div className="flex flex-col gap-2 px-4 pt-3 flex-shrink-0">
      {alerts.map(alert => (
        <div
          key={alert.id}
          role="alert"
          className="flex items-start gap-3 bg-amber-50 border border-amber-300 rounded-xl px-4 py-3
            dark:bg-amber-900/20 dark:border-amber-600"
        >
          {/* Warning icon */}
          <svg className="flex-shrink-0 mt-0.5 text-amber-600 dark:text-amber-400" width="18" height="18"
            fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2} aria-hidden>
            <path strokeLinecap="round" strokeLinejoin="round"
              d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z" />
          </svg>

          <p className="flex-1 text-sm text-amber-900 dark:text-amber-200 leading-snug">
            {selectMessage(alert)}
          </p>

          <div className="flex items-center gap-2 flex-shrink-0">
            {onPrefill && (
              <button
                onClick={() => onPrefill(selectMessage(alert))}
                className="text-xs font-medium text-amber-700 dark:text-amber-300
                  hover:text-amber-900 dark:hover:text-amber-100 underline underline-offset-2"
              >
                Ask
              </button>
            )}
            <button
              onClick={() => dismiss(alert.id)}
              aria-label="Dismiss alert"
              className="text-amber-500 hover:text-amber-700 dark:text-amber-400 dark:hover:text-amber-200"
            >
              <svg width="16" height="16" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        </div>
      ))}
    </div>
  )
}
