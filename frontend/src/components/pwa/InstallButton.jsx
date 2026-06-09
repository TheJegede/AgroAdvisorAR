import { useInstallPrompt } from '../../hooks/useInstallPrompt'
import { useLang } from '../../contexts/LangContext'
import { LABELS } from '../../constants/i18n'

export default function InstallButton() {
  const { installable, dismissed, promptInstall } = useInstallPrompt()
  const { lang } = useLang()
  const t = LABELS[lang] || LABELS.en
  if (!installable || dismissed) return null
  return (
    <button
      type="button"
      onClick={promptInstall}
      className="min-h-touch rounded-lg bg-forest px-4 py-2 text-parchment"
      title={t.installHint}
    >
      {t.install}
    </button>
  )
}
