import { useLang } from '../../contexts/LangContext'

const STYLES = {
  High:   'bg-field text-white dark:bg-hc-accent dark:text-hc-accent-fg dark:border-2 dark:border-hc-border',
  Medium: 'bg-harvest text-charcoal dark:bg-hc-bg dark:text-hc-fg dark:border-2 dark:border-hc-border',
  Low:    'bg-arred/10 border border-arred/30 text-arred-dark dark:bg-hc-danger dark:text-hc-danger-fg dark:border-2 dark:border-hc-border',
}

export default function ConfidenceBadge({ confidence }) {
  const { t } = useLang()
  const label = { High: t.confidenceHigh, Medium: t.confidenceMedium, Low: t.confidenceLow }
  return (
    <span className={`inline-flex items-center rounded-full px-3 py-1 text-sm font-semibold ${STYLES[confidence]}`}>
      {t.confidence}: {label[confidence]}
    </span>
  )
}
