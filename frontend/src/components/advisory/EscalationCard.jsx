import { useLang } from '../../contexts/LangContext'

export default function EscalationCard({ escalation }) {
  const { t } = useLang()
  if (!escalation) return null
  return (
    <div className="bg-harvest/20 dark:bg-hc-bg border border-harvest dark:border-2 dark:border-hc-border rounded-lg px-4 py-3 flex items-start gap-3 my-2">
      <svg width="18" height="18" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2} aria-hidden="true" className="flex-shrink-0 mt-0.5 text-harvest-dark">
        <path strokeLinecap="round" strokeLinejoin="round"
          d="M2.25 6.75c0 8.284 6.716 15 15 15h2.25a2.25 2.25 0 002.25-2.25v-1.372c0-.516-.351-.966-.852-1.091l-4.423-1.106c-.44-.11-.902.055-1.173.417l-.97 1.293c-.282.376-.769.542-1.21.38a12.035 12.035 0 01-7.143-7.143c-.162-.441.004-.928.38-1.21l1.293-.97c.363-.271.527-.734.417-1.173L6.963 3.102a1.125 1.125 0 00-1.091-.852H4.5A2.25 2.25 0 002.25 4.5v2.25z" />
      </svg>
      <div>
        <p className="text-sm font-semibold text-charcoal dark:text-hc-fg">{t.escalationContact}</p>
        <p className="text-sm text-charcoal dark:text-hc-fg mt-1">{escalation}</p>
      </div>
    </div>
  )
}
