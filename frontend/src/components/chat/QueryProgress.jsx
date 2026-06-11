import { useLang } from '../../contexts/LangContext'

// Inline "thinking" indicator — animated text + bouncing dots, rendered like an
// assistant message (left-aligned, no card). Updates in place as staged progress
// frames arrive (searching -> sources_found -> writing -> verifying), then is
// replaced by the advisory. Mirrors the conversational AI pattern (Claude/ChatGPT)
// rather than a boxed status card.
export default function QueryProgress({ stage }) {
  const { t } = useLang()
  const name = stage?.stage ?? 'searching'

  let caption = t.progressSearching
  if (name === 'sources_found') {
    caption = t.progressFoundSources.replace('{n}', String(stage?.count ?? 0))
  } else if (name === 'writing') {
    caption = t.progressWriting
  } else if (name === 'verifying') {
    caption = t.progressVerifying
  }

  return (
    <div
      className="flex flex-col my-2 px-1 self-start gap-1"
      role="status"
      aria-live="polite"
      aria-label={caption}
    >
      <div className="flex items-center gap-2">
        <span className="inline-flex gap-1" aria-hidden="true">
          <span className="w-1.5 h-1.5 rounded-full bg-field dark:bg-hc-accent animate-bounce" style={{ animationDelay: '0ms' }} />
          <span className="w-1.5 h-1.5 rounded-full bg-field dark:bg-hc-accent animate-bounce" style={{ animationDelay: '150ms' }} />
          <span className="w-1.5 h-1.5 rounded-full bg-field dark:bg-hc-accent animate-bounce" style={{ animationDelay: '300ms' }} />
        </span>
        <span className="text-sm font-medium text-charcoal-light dark:text-hc-fg animate-pulse">
          {caption}
        </span>
      </div>
      {name === 'sources_found' && stage?.titles?.length > 0 && (
        <ul className="ml-4 text-xs text-gray-500 dark:text-hc-fg/70 space-y-0.5 list-none">
          {stage.titles.map((title, i) => (
            <li key={i}>{title}</li>
          ))}
        </ul>
      )}
    </div>
  )
}
