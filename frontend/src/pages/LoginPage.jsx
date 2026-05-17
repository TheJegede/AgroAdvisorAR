import { useLang } from '../contexts/LangContext'
import LoginForm from '../components/auth/LoginForm'
import farmBg from '../assets/farm-bg.png'

export default function LoginPage() {
  const { t } = useLang()
  return (
    <main className="min-h-[100dvh] dark:bg-hc-bg flex flex-col items-center justify-center px-4 relative overflow-hidden">
      {/* Farm background image — suppressed in HC mode */}
      <div
        className="absolute inset-0 bg-cover bg-center bg-no-repeat dark:hidden"
        style={{ backgroundImage: `url(${farmBg})` }}
        aria-hidden="true"
      />
      {/* Warm amber overlay — suppressed in HC mode */}
      <div className="absolute inset-0 bg-[#E9A228]/40 dark:hidden" aria-hidden="true" />

      {/* Content */}
      <div className="relative z-10 w-full max-w-sm">
        {/* Branding above card */}
        <div className="text-center mb-8">
          <h1 className="text-3xl font-bold text-white dark:text-hc-fg drop-shadow-lg">{t.appName}</h1>
          <p className="text-sm text-white/90 dark:text-hc-fg mt-1 drop-shadow">Arkansas Agricultural Advisor</p>
        </div>

        {/* Frosted glass card */}
        <div className="bg-white/75 dark:bg-hc-surface backdrop-blur-md rounded-card shadow-lg dark:shadow-none border border-white/50 dark:border-2 dark:border-hc-border p-6">
          <LoginForm />
        </div>
      </div>
    </main>
  )
}
