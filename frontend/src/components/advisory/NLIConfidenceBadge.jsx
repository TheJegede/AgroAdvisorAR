import { useLang } from '../../contexts/LangContext'

const STYLES = {
  green: 'bg-field text-white dark:bg-hc-accent dark:text-hc-accent-fg dark:border-2 dark:border-hc-border',
  amber: 'bg-harvest text-charcoal dark:bg-hc-bg dark:text-hc-fg dark:border-2 dark:border-hc-border',
  red:   'bg-arred text-white dark:bg-hc-danger dark:text-hc-danger-fg dark:border-2 dark:border-hc-border',
}

function scoreColor(score) {
  if (score >= 0.7) return 'green'
  if (score >= 0.4) return 'amber'
  return 'red'
}

export default function NLIConfidenceBadge({ confidence_score }) {
  const { t } = useLang()
  if (confidence_score == null) return null
  const color = scoreColor(confidence_score)
  return (
    <span
      className={`inline-flex items-center rounded-full px-3 py-1 text-sm font-semibold ${STYLES[color]}`}
      aria-label={`${t.nliScore}: ${confidence_score.toFixed(2)}`}
    >
      {t.nliScore}: {confidence_score.toFixed(2)}
    </span>
  )
}
