import { useLang } from '../../contexts/LangContext'

export default function EscalationCard({ escalation }) {
  const { t } = useLang()
  if (!escalation) return null
  return (
    <div className="bg-harvest/20 dark:bg-hc-bg border border-harvest dark:border-2 dark:border-hc-border rounded-lg px-4 py-3 flex items-start gap-3 my-2">
      <span className="text-xl" role="img" aria-label="phone">📞</span>
      <div>
        <p className="text-sm font-semibold text-charcoal dark:text-hc-fg">{t.escalationContact}</p>
        <p className="text-sm text-charcoal dark:text-hc-fg mt-1">{escalation}</p>
      </div>
    </div>
  )
}
