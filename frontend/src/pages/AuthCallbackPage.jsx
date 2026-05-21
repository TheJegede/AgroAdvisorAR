import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../contexts/AuthContext'
import { supabase } from '../lib/supabase'
import api from '../lib/api'

export default function AuthCallbackPage() {
  const { login } = useAuth()
  const navigate = useNavigate()
  const [failed, setFailed] = useState(false)
  const handled = useRef(false)

  useEffect(() => {
    if (handled.current) return
    handled.current = true

    async function handleCallback() {
      const { data: { session }, error } = await supabase.auth.getSession()
      if (error || !session) {
        setFailed(true)
        return
      }
      login(session.access_token, session.refresh_token)
      try {
        await api.get('/profile')
        navigate('/', { replace: true })
      } catch (err) {
        if (err.response?.status === 404) {
          navigate('/profile?setup=1', { replace: true })
        } else {
          navigate('/', { replace: true })
        }
      }
    }

    handleCallback()
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  if (failed) {
    return (
      <div className="flex min-h-[100dvh] items-center justify-center bg-[#06130e]">
        <div className="text-center px-4">
          <p className="text-white/80 text-sm mb-4">Sign-in failed. Please try again.</p>
          <a href="/login" className="text-emerald-300 underline text-sm">Back to login</a>
        </div>
      </div>
    )
  }

  return (
    <div className="flex min-h-[100dvh] items-center justify-center bg-[#06130e]">
      <div className="text-center">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-emerald-400/30 border-t-emerald-400 mx-auto mb-4" aria-hidden="true" />
        <p className="text-white/60 text-sm">Signing you in...</p>
      </div>
    </div>
  )
}
