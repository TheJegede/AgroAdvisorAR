import { useLang } from '../contexts/LangContext'
import LoginForm from '../components/auth/LoginForm'

export default function LoginPage() {
  const { t } = useLang()
  return (
    <div className="min-h-[100dvh] bg-parchment flex flex-col items-center justify-center px-4">
      <div className="w-full max-w-sm">
        <div className="text-center mb-8">
          <h1 className="text-2xl font-bold text-field">{t.appName}</h1>
          <p className="text-sm text-gray-500 mt-1">Arkansas Agricultural Advisor</p>
        </div>
        <div className="bg-white rounded-card shadow-sm border border-gray-100 p-6">
          <LoginForm />
        </div>
      </div>
    </div>
  )
}
