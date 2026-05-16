import { useLang } from '../../contexts/LangContext'

const STYLES = {
  High:   'bg-field text-white',
  Medium: 'bg-harvest text-charcoal',
  Low:    'bg-arred text-white',
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
