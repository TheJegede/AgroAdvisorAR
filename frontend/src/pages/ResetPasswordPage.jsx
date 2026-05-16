import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useLang } from '../contexts/LangContext'
import api from '../lib/api'
import Input from '../components/ui/Input'
import Button from '../components/ui/Button'
import Alert from '../components/ui/Alert'

function parseHashParams(hash) {
  const out = {}
  if (!hash) return out
  const clean = hash.startsWith('#') ? hash.slice(1) : hash
  for (const part of clean.split('&')) {
    const [k, v] = part.split('=')
    if (k) out[decodeURIComponent(k)] = decodeURIComponent(v || '')
  }
  return out
}

export default function ResetPasswordPage() {
  const { t } = useLang()
  const navigate = useNavigate()

  const [tokens, setTokens] = useState(null)
  const [tokenError, setTokenError] = useState(false)
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState(false)

  useEffect(() => {
    const params = parseHashParams(window.location.hash)
    if (params.type === 'recovery' && params.access_token && params.refresh_token) {
      setTokens({ access_token: params.access_token, refresh_token: params.refresh_token })
    } else {
      setTokenError(true)
    }
  }, [])

  async function handleSubmit(e) {
    e.preventDefault()
    if (!tokens) return
    if (password.length < 8) {
      setError(t.errPasswordShort)
      return
    }
    setError('')
    setLoading(true)
    try {
      await api.post('/auth/reset-password', {
        access_token: tokens.access_token,
        refresh_token: tokens.refresh_token,
        new_password: password,
      })
      setSuccess(true)
      setTimeout(() => navigate('/login'), 2500)
    } catch (err) {
      setError(err.response?.data?.detail || t.resetPasswordInvalid)
    } finally {
      setLoading(false)
    }
  }

  return (
    <main className="min-h-[100dvh] bg-parchment dark:bg-hc-bg flex flex-col items-center justify-center px-4">
      <div className="w-full max-w-sm">
        <div className="text-center mb-8">
          <h1 className="text-2xl font-bold text-field dark:text-hc-fg">{t.appName}</h1>
          <p className="text-sm text-gray-700 dark:text-hc-fg mt-1">{t.resetPasswordHeading}</p>
        </div>
        <div className="bg-white dark:bg-hc-surface rounded-card shadow-sm dark:shadow-none border border-gray-100 dark:border-2 dark:border-hc-border p-6">
          {tokenError ? (
            <div className="flex flex-col gap-4">
              <Alert variant="error">{t.resetPasswordInvalid}</Alert>
              <Link to="/forgot-password" className="text-center text-sm text-field dark:text-hc-accent font-bold hover:underline">
                {t.forgotPassword}
              </Link>
            </div>
          ) : success ? (
            <Alert variant="success">{t.resetPasswordSuccess}</Alert>
          ) : (
            <form onSubmit={handleSubmit} className="flex flex-col gap-4">
              {error && <Alert variant="error" dismissible>{error}</Alert>}
              <Input
                id="new_password"
                label={t.newPassword}
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                autoComplete="new-password"
              />
              <Button type="submit" loading={loading} disabled={!tokens} className="w-full mt-2">
                {t.resetPasswordSubmit}
              </Button>
              <Link to="/login" className="text-center text-sm text-field dark:text-hc-accent font-bold hover:underline">
                ← {t.backToLogin}
              </Link>
            </form>
          )}
        </div>
      </div>
    </main>
  )
}
