import { useLang } from '../contexts/LangContext'
import LoginForm from '../components/auth/LoginForm'
import AuthLanguageSwitcher from '../components/auth/AuthLanguageSwitcher'
import farmBg from '../assets/farm-bg.png'

export default function LoginPage() {
  const { t } = useLang()
  return (
    <main className="relative flex min-h-[100dvh] flex-col items-center justify-center overflow-hidden bg-[#06130e] px-4 py-8 dark:bg-hc-bg">
      <div
        className="absolute inset-0 scale-105 bg-cover bg-center bg-no-repeat blur-[1px] dark:hidden"
        style={{ backgroundImage: `url(${farmBg})` }}
        aria-hidden="true"
      />
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_50%_10%,rgba(64,145,108,0.34),transparent_36%),linear-gradient(115deg,rgba(3,11,8,0.88),rgba(8,31,24,0.56)_46%,rgba(3,9,8,0.88))] dark:hidden" aria-hidden="true" />
      <div className="absolute inset-0 bg-black/20 backdrop-blur-[2px] dark:hidden" aria-hidden="true" />

      <div className="relative z-10 flex w-full flex-1 items-center justify-center">
        <div className="relative w-full max-w-[28rem] overflow-hidden rounded-[1.35rem] border border-white/25 bg-slate-950/30 p-7 shadow-[0_30px_90px_rgba(0,0,0,0.42),inset_0_1px_0_rgba(255,255,255,0.25)] backdrop-blur-2xl dark:border-2 dark:border-hc-border dark:bg-hc-surface dark:shadow-none sm:p-8">
          <div className="pointer-events-none absolute inset-0 bg-[linear-gradient(108deg,transparent_4%,rgba(255,255,255,0.12)_43%,rgba(255,255,255,0.045)_49%,transparent_60%)] dark:hidden" aria-hidden="true" />
          <div className="pointer-events-none absolute inset-x-0 top-0 h-28 bg-gradient-to-b from-white/15 to-transparent dark:hidden" aria-hidden="true" />
          <div className="pointer-events-none absolute inset-x-8 top-0 h-px bg-gradient-to-r from-transparent via-white/60 to-transparent dark:hidden" aria-hidden="true" />
          <AuthLanguageSwitcher />
          <div className="relative mb-8 text-center">
            <p className="mb-3 text-xs font-semibold uppercase tracking-[0.28em] text-emerald-100/70 dark:text-hc-fg">
              {t.authEyebrow}
            </p>
            <h1 className="text-3xl font-bold text-white drop-shadow-lg dark:text-hc-fg">{t.appName}</h1>
            <p className="mt-3 text-sm font-medium text-white/80 dark:text-hc-fg">
              {t.loginSubtitle}
            </p>
            <p className="mt-1 text-xs text-white/50 dark:text-hc-fg">
              {t.loginCrops}
            </p>
          </div>
          <div className="relative">
            <LoginForm />
          </div>
        </div>
      </div>
      <p className="relative z-10 mt-6 text-xs text-white/50 drop-shadow dark:text-hc-fg">
        {t.copyright}
      </p>
    </main>
  )
}
