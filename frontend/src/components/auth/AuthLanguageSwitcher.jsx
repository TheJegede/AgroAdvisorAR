import { useLang } from '../../contexts/LangContext'

const OPTIONS = [
  { value: 'en', label: 'English' },
  { value: 'es', label: 'Español' },
]

export default function AuthLanguageSwitcher() {
  const { lang, setLang, t } = useLang()

  return (
    <div className="relative z-10 mb-5 flex justify-center">
      <div
        className="inline-flex rounded-full border border-white/20 bg-black/20 p-1 shadow-[inset_0_1px_0_rgba(255,255,255,0.12)] dark:border-hc-border dark:bg-hc-bg"
        role="group"
        aria-label={t.languagePref}
      >
        {OPTIONS.map((option) => {
          const isActive = option.value === lang
          return (
            <button
              key={option.value}
              type="button"
              onClick={() => setLang(option.value)}
              className={[
                'min-h-9 rounded-full px-3 text-xs font-bold transition focus:outline-none focus:ring-2 focus:ring-emerald-200/60',
                isActive
                  ? 'bg-white text-[#092014] shadow-sm dark:bg-hc-accent dark:text-hc-accent-fg'
                  : 'text-white/70 hover:bg-white/10 hover:text-white dark:text-hc-fg',
              ].join(' ')}
              aria-pressed={isActive}
            >
              {option.label}
            </button>
          )
        })}
      </div>
    </div>
  )
}
