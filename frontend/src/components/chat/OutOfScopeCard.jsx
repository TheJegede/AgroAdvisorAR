import { useLang } from '../../contexts/LangContext'
import FeedbackWidget from '../advisory/FeedbackWidget'

export default function OutOfScopeCard({ message, messageId }) {
  const { t } = useLang()
  return (
    <div className="bg-harvest/10 border border-harvest rounded-card p-4 my-2 max-w-lg">
      <div className="flex items-start gap-3">
        <span className="text-2xl" role="img" aria-label="wheat">🌾</span>
        <div className="flex-1">
          <p className="font-semibold text-charcoal mb-1">{t.outOfScopeTitle}</p>
          <p className="text-sm text-gray-700 leading-relaxed">{message}</p>
          <FeedbackWidget messageId={messageId} />
        </div>
      </div>
    </div>
  )
}
