import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useLang } from '../contexts/LangContext'
import api from '../lib/api'
import Alert from '../components/ui/Alert'
import AuthLanguageSwitcher from '../components/auth/AuthLanguageSwitcher'
import farmBg from '../assets/farm-bg.png'

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
              {t.forgotPasswordHeading}
            </p>
          </div>

          <div className="relative flex flex-col gap-4">
            {submitted ? (
              <>
                <Alert variant="success">{t.forgotPasswordSent}</Alert>
                <Link
                  to="/login"
                  className="text-center text-sm font-bold text-white/80 transition hover:text-white hover:underline dark:text-hc-accent"
                >
                  ← {t.backToLogin}
                </Link>
              </>
            ) : (
              <form onSubmit={handleSubmit} className="flex flex-col gap-4">
                <p className="text-sm text-white/75 dark:text-hc-fg">{t.forgotPasswordHelp}</p>
                {error && <Alert variant="error" dismissible>{error}</Alert>}

                <div>
                  <label htmlFor="email" className="sr-only">{t.email}</label>
                  <input
                    id="email"
                    type="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    required
                    autoComplete="email"
                    placeholder={t.email}
                    className="min-h-touch w-full rounded-xl border border-white/20 bg-white/[0.075] px-4 py-3 text-base text-white shadow-[inset_0_1px_0_rgba(255,255,255,0.12)] outline-none transition placeholder:text-white/60 focus:border-emerald-200/70 focus:bg-white/[0.11] focus:ring-2 focus:ring-emerald-200/25 dark:border-2 dark:border-hc-border dark:bg-hc-bg dark:text-hc-fg"
                  />
                </div>

                <button
                  type="submit"
                  disabled={loading}
                  className="mt-1 min-h-touch w-full rounded-xl bg-gradient-to-r from-emerald-400 via-lime-300 to-harvest px-5 py-3 font-bold text-[#092014] shadow-[0_16px_36px_rgba(45,106,79,0.34),inset_0_1px_0_rgba(255,255,255,0.42)] transition hover:brightness-110 focus:outline-none focus:ring-2 focus:ring-emerald-100/70 disabled:cursor-not-allowed disabled:opacity-60 dark:border-2 dark:border-hc-border dark:bg-hc-accent dark:bg-none dark:text-hc-accent-fg"
                >
                  {loading ? t.sending : t.forgotPasswordSubmit}
                </button>

                <Link
                  to="/login"
                  className="text-center text-sm font-bold text-white/70 transition hover:text-white hover:underline dark:text-hc-accent"
                >
                  ← {t.backToLogin}
                </Link>
              </form>
            )}
          </div>
        </div>
      </div>
      <p className="relative z-10 mt-6 text-xs text-white/50 drop-shadow dark:text-hc-fg">
        {t.copyright}
      </p>
    </main>
  )
}
