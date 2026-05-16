import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useLang } from '../contexts/LangContext'
import api from '../lib/api'
import Input from '../components/ui/Input'
import Button from '../components/ui/Button'
import Alert from '../components/ui/Alert'

export default function ForgotPasswordPage() {
  const { t } = useLang()
  const [email, setEmail] = useState('')
  const [submitted, setSubmitted] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  async function handleSubmit(e) {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      await api.post('/auth/forgot', { email })
      setSubmitted(true)
    } catch (err) {
      setError(err.response?.data?.detail || t.errorGeneric)
    } finally {
      setLoading(false)
    }
  }

  return (
    <main className="min-h-[100dvh] bg-parchment dark:bg-hc-bg flex flex-col items-center justify-center px-4">
      <div className="w-full max-w-sm">
        <div className="text-center mb-8">
          <h1 className="text-2xl font-bold text-field dark:text-hc-fg">{t.appName}</h1>
          <p className="text-sm text-gray-700 dark:text-hc-fg mt-1">{t.forgotPasswordHeading}</p>
        </div>
        <div className="bg-white dark:bg-hc-surface rounded-card shadow-sm dark:shadow-none border border-gray-100 dark:border-2 dark:border-hc-border p-6">
          {submitted ? (
            <div className="flex flex-col gap-4">
              <Alert variant="success">{t.forgotPasswordSent}</Alert>
              <Link
                to="/login"
                className="text-center text-sm text-field dark:text-hc-accent font-bold hover:underline"
              >
                ← {t.backToLogin}
              </Link>
            </div>
          ) : (
            <form onSubmit={handleSubmit} className="flex flex-col gap-4">
              <p className="text-sm text-gray-700 dark:text-hc-fg">{t.forgotPasswordHelp}</p>
              {error && <Alert variant="error" dismissible>{error}</Alert>}
              <Input
                id="email"
                label={t.email}
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                autoComplete="email"
              />
              <Button type="submit" loading={loading} className="w-full mt-2">
                {t.forgotPasswordSubmit}
              </Button>
              <Link
                to="/login"
                className="text-center text-sm text-field dark:text-hc-accent font-bold hover:underline"
              >
                ← {t.backToLogin}
              </Link>
            </form>
          )}
        </div>
      </div>
    </main>
  )
}
