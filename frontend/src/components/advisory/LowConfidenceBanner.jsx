import { useLang } from '../../contexts/LangContext'

export default function LowConfidenceBanner() {
  const { t } = useLang()
  return (
    <div className="bg-harvest/20 dark:bg-hc-bg border border-harvest dark:border-2 dark:border-hc-border rounded-lg px-4 py-3 flex items-start gap-3 my-2">
      <span className="text-xl" role="img" aria-label="phone">📞</span>
      <div>
        <p className="text-sm font-semibold text-charcoal dark:text-hc-fg">{t.lowConfidenceCallout}</p>
        <a
          href="tel:18002645237"
          className="text-sm text-field dark:text-hc-accent underline font-bold"
        >
          {t.extensionPhone}
        </a>
      </div>
    </div>
  )
}
