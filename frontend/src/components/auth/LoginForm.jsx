import { useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { useAuth } from '../../contexts/AuthContext'
import { useLang } from '../../contexts/LangContext'
import api from '../../lib/api'
import { supabase } from '../../lib/supabase'
import Alert from '../ui/Alert'

function MailIcon() {
  return (
    <svg aria-hidden="true" viewBox="0 0 24 24" className="h-5 w-5">
      <path d="M4 6.75h16v10.5H4V6.75Z" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round" />
      <path d="m4.5 7.25 7.5 6 7.5-6" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

function LockIcon() {
  return (
    <svg aria-hidden="true" viewBox="0 0 24 24" className="h-5 w-5">
      <path d="M7 10.5h10v8H7v-8Z" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round" />
      <path d="M9 10.5V8a3 3 0 0 1 6 0v2.5" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  )
}

function EyeIcon() {
  return (
    <svg aria-hidden="true" viewBox="0 0 24 24" className="h-5 w-5">
      <path d="M3.5 12s3-5 8.5-5 8.5 5 8.5 5-3 5-8.5 5-8.5-5-8.5-5Z" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round" />
      <circle cx="12" cy="12" r="2.2" fill="none" stroke="currentColor" strokeWidth="1.8" />
    </svg>
  )
}

function GoogleIcon() {
  return (
    <svg aria-hidden="true" viewBox="0 0 24 24" className="h-5 w-5">
      <path fill="#4285F4" d="M21.6 12.23c0-.74-.07-1.45-.19-2.13H12v4.03h5.38a4.6 4.6 0 0 1-1.99 3.02v2.52h3.23c1.89-1.74 2.98-4.3 2.98-7.44Z" />
      <path fill="#34A853" d="M12 22c2.7 0 4.96-.89 6.62-2.33l-3.23-2.52c-.9.6-2.04.95-3.39.95-2.6 0-4.8-1.75-5.59-4.11H3.07v2.6A10 10 0 0 0 12 22Z" />
      <path fill="#FBBC05" d="M6.41 13.99a6.02 6.02 0 0 1 0-3.98v-2.6H3.07a10 10 0 0 0 0 9.18l3.34-2.6Z" />
      <path fill="#EA4335" d="M12 5.9c1.47 0 2.78.51 3.82 1.5l2.87-2.87A9.62 9.62 0 0 0 12 2a10 10 0 0 0-8.93 5.41l3.34 2.6C7.2 7.65 9.4 5.9 12 5.9Z" />
    </svg>
  )
}

export default function LoginForm() {
  const { login } = useAuth()
  const { t } = useLang()
  const navigate = useNavigate()

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [remember, setRemember] = useState(false)
  const [showPassword, setShowPassword] = useState(false)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  async function handleGoogleSignIn() {
    setError('')
    await supabase.auth.signInWithOAuth({
      provider: 'google',
      options: { redirectTo: `${window.location.origin}/auth/callback` },
    })
  }

  async function handleSubmit(e) {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      const { data } = await api.post('/auth/login', { email, password })
      login(data.access_token, data.refresh_token)
      navigate('/')
    } catch (err) {
      setError(err.response?.data?.detail || t.errorGeneric)
    } finally {
      setLoading(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-4">
      {error && <Alert variant="error" dismissible>{error}</Alert>}
      <div className="group relative">
        <label htmlFor="email" className="sr-only">{t.email}</label>
        <span className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-white/60 transition-colors group-focus-within:text-emerald-200 dark:text-hc-fg">
          <MailIcon />
        </span>
        <input
          id="email"
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          required
          autoComplete="email"
          placeholder={t.email}
          className="min-h-touch w-full rounded-xl border border-white/20 bg-white/[0.075] px-12 py-3 text-base text-white shadow-[inset_0_1px_0_rgba(255,255,255,0.12)] outline-none transition placeholder:text-white/60 focus:border-emerald-200/70 focus:bg-white/[0.11] focus:ring-2 focus:ring-emerald-200/25 dark:border-2 dark:border-hc-border dark:bg-hc-bg dark:text-hc-fg"
        />
      </div>

      <div className="group relative">
        <label htmlFor="password" className="sr-only">{t.password}</label>
        <span className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-white/60 transition-colors group-focus-within:text-emerald-200 dark:text-hc-fg">
          <LockIcon />
        </span>
        <input
          id="password"
          type={showPassword ? 'text' : 'password'}
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
          autoComplete="current-password"
          placeholder={t.password}
          className="min-h-touch w-full rounded-xl border border-white/20 bg-white/[0.075] py-3 pl-12 pr-12 text-base text-white shadow-[inset_0_1px_0_rgba(255,255,255,0.12)] outline-none transition placeholder:text-white/60 focus:border-emerald-200/70 focus:bg-white/[0.11] focus:ring-2 focus:ring-emerald-200/25 dark:border-2 dark:border-hc-border dark:bg-hc-bg dark:text-hc-fg"
        />
        <button
          type="button"
          onClick={() => setShowPassword((value) => !value)}
          className="absolute right-3 top-1/2 flex h-9 w-9 -translate-y-1/2 items-center justify-center rounded-full text-white/60 transition hover:bg-white/10 hover:text-white focus:outline-none focus:ring-2 focus:ring-emerald-200/50 dark:text-hc-fg"
          aria-label={showPassword ? 'Hide password' : 'Show password'}
        >
          <EyeIcon />
        </button>
      </div>

      <div className="-mt-1 flex items-center justify-between gap-4 text-sm">
        <label htmlFor="remember" className="flex cursor-pointer items-center gap-2 text-white/75 dark:text-hc-fg">
          <input
            id="remember"
            type="checkbox"
            checked={remember}
            onChange={(e) => setRemember(e.target.checked)}
            className="peer sr-only"
          />
          <span className="relative h-5 w-10 rounded-full border border-white/20 bg-white/20 shadow-inner transition after:absolute after:left-0.5 after:top-0.5 after:h-4 after:w-4 after:rounded-full after:bg-white after:shadow after:transition peer-checked:bg-emerald-300/80 peer-checked:after:translate-x-5 peer-focus-visible:ring-2 peer-focus-visible:ring-emerald-200/60 dark:border-hc-border dark:bg-hc-bg" />
          <span>{t.rememberMe}</span>
        </label>
        <Link to="/forgot-password" className="font-medium text-white/80 transition hover:text-white hover:underline dark:text-hc-accent">
          {t.forgotPassword}
        </Link>
      </div>

      <button
        type="submit"
        disabled={loading}
        className="mt-3 min-h-touch w-full rounded-xl bg-gradient-to-r from-emerald-400 via-lime-300 to-harvest px-5 py-3 font-bold text-[#092014] shadow-[0_16px_36px_rgba(45,106,79,0.34),inset_0_1px_0_rgba(255,255,255,0.42)] transition hover:brightness-110 focus:outline-none focus:ring-2 focus:ring-emerald-100/70 disabled:cursor-not-allowed disabled:opacity-60 dark:border-2 dark:border-hc-border dark:bg-hc-accent dark:bg-none dark:text-hc-accent-fg"
      >
        {loading ? t.sending : t.enterApp}
      </button>

      <div className="my-4 flex items-center gap-3 text-xs text-white/50 dark:text-hc-fg">
        <span className="h-px flex-1 bg-white/20 dark:bg-hc-border" />
        <span>{t.quickAccessVia}</span>
        <span className="h-px flex-1 bg-white/20 dark:bg-hc-border" />
      </div>

      <button
        type="button"
        onClick={handleGoogleSignIn}
        className="flex min-h-touch w-full items-center justify-center gap-3 rounded-xl border border-white/20 bg-black/20 px-4 py-2.5 text-sm font-semibold text-white/90 shadow-[inset_0_1px_0_rgba(255,255,255,0.1)] transition hover:bg-white/10 focus:outline-none focus:ring-2 focus:ring-emerald-200/50 dark:border-2 dark:border-hc-border dark:bg-hc-bg dark:text-hc-fg"
      >
        <GoogleIcon />
        <span>{t.continueWithGoogle}</span>
      </button>

      <p className="pt-2 text-center text-sm text-white/70 dark:text-hc-fg">
        {t.noAccount}{' '}
        <Link to="/register" className="font-bold text-white transition hover:text-emerald-100 hover:underline dark:text-hc-accent">
          {t.createAccount}
        </Link>
      </p>
    </form>
  )
}
