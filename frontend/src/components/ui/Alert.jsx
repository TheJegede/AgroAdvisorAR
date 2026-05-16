import { useState } from 'react'

const VARIANTS = {
  info:    'bg-blue-50 border-blue-300 text-blue-800',
  warning: 'bg-harvest/10 border-harvest text-charcoal',
  error:   'bg-arred/10 border-arred text-arred-dark',
  success: 'bg-field/10 border-field text-field-dark',
}

export default function Alert({ variant = 'info', children, dismissible = false, className = '' }) {
  const [dismissed, setDismissed] = useState(false)
  if (dismissed) return null

  return (
    <div className={`flex items-start gap-3 rounded-lg border px-4 py-3 ${VARIANTS[variant]} ${className}`}>
      <p className="flex-1 text-sm">{children}</p>
      {dismissible && (
        <button
          onClick={() => setDismissed(true)}
          className="text-current opacity-60 hover:opacity-100 text-lg leading-none"
        >
          &times;
        </button>
      )}
    </div>
  )
}
