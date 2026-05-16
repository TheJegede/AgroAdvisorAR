import { useLang } from '../../contexts/LangContext'

function relativeDate(isoString, t) {
  const date = new Date(isoString)
  const now = new Date()
  const diffDays = Math.floor((now - date) / (1000 * 60 * 60 * 24))
  if (diffDays === 0) return t.today
  if (diffDays === 1) return t.yesterday
  return date.toLocaleDateString()
}

export default function SessionListItem({ session, onSelect }) {
  const { t } = useLang()
  return (
    <button
      onClick={() => onSelect(session.id)}
      className="w-full text-left bg-white border border-gray-100 rounded-card px-4 py-3
        min-h-touch hover:border-field hover:bg-field/5 transition-colors flex flex-col gap-0.5
        dark:bg-hc-bg dark:border-2 dark:border-hc-border dark:hover:bg-hc-muted dark:hover:text-hc-bg"
    >
      <p className="text-sm text-charcoal dark:text-hc-fg line-clamp-2 leading-snug">
        {session.preview || '...'}
      </p>
      <p className="text-xs text-gray-600 dark:text-hc-fg">
        {relativeDate(session.last_message_at, t)}
      </p>
    </button>
  )
}
