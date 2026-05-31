import { useLang } from '../../contexts/LangContext'

export default function SuppressedNotice({ escalation }) {
  const { t } = useLang()
  return (
    <div className="bg-arred/10 dark:bg-hc-surface border border-arred dark:border-2 dark:border-hc-danger rounded-card p-4 my-2">
      <p className="text-sm font-semibold text-arred-dark dark:text-hc-danger">{t.suppressedTitle}</p>
      <p className="text-sm text-charcoal dark:text-hc-fg mt-1 leading-relaxed">{t.suppressedBody}</p>
      {escalation && <p className="text-sm font-medium text-charcoal dark:text-hc-fg mt-2">{escalation}</p>}
    </div>
  )
}
