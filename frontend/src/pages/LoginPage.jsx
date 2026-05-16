import { useLang } from '../contexts/LangContext'
import LoginForm from '../components/auth/LoginForm'

export default function LoginPage() {
  const { t } = useLang()
  return (
    <main className="min-h-[100dvh] bg-parchment dark:bg-hc-bg flex flex-col items-center justify-center px-4">
      <div className="w-full max-w-sm">
        <div className="text-center mb-8">
          <h1 className="text-2xl font-bold text-field dark:text-hc-fg">{t.appName}</h1>
          <p className="text-sm text-gray-700 dark:text-hc-fg mt-1">Arkansas Agricultural Advisor</p>
        </div>
        <div className="bg-white dark:bg-hc-surface rounded-card shadow-sm dark:shadow-none border border-gray-100 dark:border-2 dark:border-hc-border p-6">
          <LoginForm />
        </div>
      </div>
    </main>
  )
}
