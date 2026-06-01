import { useLang } from '../../contexts/LangContext'
import FeedbackWidget from '../advisory/FeedbackWidget'

export default function OutOfScopeCard({ message, messageId }) {
  const { t } = useLang()
  return (
    <div className="bg-harvest/10 dark:bg-hc-surface border border-harvest dark:border-2 dark:border-hc-border rounded-card p-4 my-2 max-w-lg">
      <div className="flex items-start gap-3">
        <svg width="32" height="32" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5} aria-hidden="true" className="flex-shrink-0 text-field-dark">
          <path strokeLinecap="round" strokeLinejoin="round"
            d="M12 18.75a6 6 0 006-6v-1.5m-6 7.5a6 6 0 01-6-6v-1.5m6 7.5v3.75m-3.75 0h7.5M12 15c-2.485 0-4.5-2.015-4.5-4.5V4.875C7.5 3.839 8.34 3 9.375 3h5.25c1.035 0 1.875.84 1.875 1.875V10.5c0 2.485-2.015 4.5-4.5 4.5z" />
        </svg>
        <div className="flex-1">
          <p className="font-semibold text-charcoal dark:text-hc-fg mb-1">{t.outOfScopeTitle}</p>
          <p className="text-sm text-gray-700 dark:text-hc-fg leading-relaxed">{message}</p>
          <FeedbackWidget messageId={messageId} />
        </div>
      </div>
    </div>
  )
}
