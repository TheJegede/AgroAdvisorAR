import { useLang } from '../../contexts/LangContext'

export default function SyncStatusBar({ online }) {
  const { t } = useLang()
  if (online) return null
  return (
    <div className="flex-shrink-0 h-7 bg-harvest/10 border-b border-harvest/30 flex items-center px-4 gap-2 text-xs text-harvest-dark">
      <span className="w-2 h-2 rounded-full bg-harvest inline-block" />
      {t.offline}
    </div>
  )
}
