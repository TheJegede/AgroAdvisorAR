import { useLang } from '../../contexts/LangContext'

export default function RecommendedActions({ actions }) {
  const { t } = useLang()
  if (!actions?.length) return null
  return (
    <div className="my-3">
      <h2 className="text-base font-semibold text-charcoal dark:text-hc-fg mb-2">{t.recommendedActions}</h2>
      <ol className="list-decimal list-outside pl-5 flex flex-col gap-2">
        {actions.map((action, i) => (
          <li key={i} className="text-sm text-gray-700 dark:text-hc-fg leading-relaxed pl-1">{action}</li>
        ))}
      </ol>
    </div>
  )
}
