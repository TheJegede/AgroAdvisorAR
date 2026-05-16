import { useState, useEffect } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useLang } from '../contexts/LangContext'
import { useSessions } from '../hooks/useSessions'
import SessionListItem from '../components/sessions/SessionListItem'
import Spinner from '../components/ui/Spinner'
import Button from '../components/ui/Button'
import Alert from '../components/ui/Alert'

export default function SessionsPage() {
  const { t } = useLang()
  const { listSessions } = useSessions()
  const navigate = useNavigate()
  const [sessions, setSessions] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    listSessions()
      .then(setSessions)
      .catch(() => setError(t.errorGeneric))
      .finally(() => setLoading(false))
  }, [listSessions, t.errorGeneric])

  return (
    <div className="flex-1 overflow-y-auto px-4 py-6">
      <div className="max-w-sm mx-auto">
        <div className="flex items-center gap-3 mb-6">
          <Link to="/" className="text-field dark:text-hc-fg">
            <svg width="20" height="20" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 19.5L8.25 12l7.5-7.5" />
            </svg>
          </Link>
          <h1 className="text-xl font-bold text-charcoal dark:text-hc-fg">{t.pastSessions}</h1>
        </div>

        <Button className="w-full mb-4" onClick={() => navigate('/')}>
          + {t.newChat}
        </Button>

        {error && <Alert variant="error">{error}</Alert>}
        {loading && <div className="flex justify-center py-8"><Spinner /></div>}
        {!loading && !error && sessions.length === 0 && (
          <p className="text-sm text-gray-600 dark:text-hc-fg text-center py-8">{t.noSessions}</p>
        )}
        {!loading && (
          <div className="flex flex-col gap-2">
            {sessions.map((s) => (
              <SessionListItem
                key={s.id}
                session={s}
                onSelect={(id) => navigate(`/?session=${id}`)}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
