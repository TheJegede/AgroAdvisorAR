import { useState, useEffect } from 'react'
import { Link, useNavigate, useLocation } from 'react-router-dom'
import { useAuth } from '../../contexts/AuthContext'
import { useLang } from '../../contexts/LangContext'
import { useTheme } from '../../contexts/ThemeContext'
import { useSessions } from '../../hooks/useSessions'
import { useProfile } from '../../hooks/useProfile'

function SidebarNavItem({ to, onClick, children, ariaPressed, ariaLabel, disabled }) {
  const baseCls = 'flex items-center gap-3 px-3 py-3 rounded-lg text-sm transition-colors'
  const stateCls = disabled
    ? 'text-white/40 cursor-not-allowed w-full text-left'
    : 'text-white/70 hover:bg-white/10 hover:text-white cursor-pointer'
  const cls = `${baseCls} ${stateCls}`

  if (to && !disabled) {
    return (
      <Link to={to} onClick={onClick} className={cls} aria-label={ariaLabel}>
        {children}
      </Link>
    )
  }
  return (
    <button
      type="button"
      onClick={disabled ? undefined : onClick}
      disabled={disabled}
      className={cls}
      aria-pressed={ariaPressed}
      aria-label={ariaLabel}
    >
      {children}
    </button>
  )
}

function SessionsList({ sessions, currentSessionId, onNavigate, onDelete, loading, error, onRetry, t }) {
  if (loading) {
    return (
      <div className="flex-1 overflow-y-auto flex flex-col gap-0.5 min-h-0 pb-2 px-3">
        {[0, 1, 2].map((i) => (
          <div key={i} className="h-8 bg-white/10 rounded animate-pulse my-0.5" />
        ))}
      </div>
    )
  }
  if (error) {
    return (
      <div className="flex-1 overflow-y-auto flex flex-col gap-0.5 min-h-0 pb-2">
        <button
          type="button"
          onClick={onRetry}
          className="text-xs text-white/60 hover:text-white px-3 py-1.5 text-left underline"
        >
          {t.sessionsLoadError}
        </button>
      </div>
    )
  }
  return (
    <div className="flex-1 overflow-y-auto flex flex-col gap-0.5 min-h-0 pb-2">
      {sessions.length === 0 ? (
        <p className="text-xs text-white/60 px-3 py-1.5">{t.noSessions}</p>
      ) : (
        sessions.slice(0, 12).map((s) => (
          <div
            key={s.id}
            className={[
              'group flex items-center justify-between px-3 py-2 rounded-lg text-sm transition-colors ml-1 mr-2',
              currentSessionId === s.id
                ? 'bg-white/15 text-white'
                : 'text-white/60 hover:bg-white/10 hover:text-white/90',
            ].join(' ')}
          >
            <button
              type="button"
              onClick={() => onNavigate(s.id)}
              className="flex-1 text-left truncate min-w-0"
            >
              {s.preview || t.newChat}
            </button>
            <button
              type="button"
              onClick={(e) => { e.stopPropagation(); onDelete(s.id) }}
              className="opacity-0 group-hover:opacity-100 focus:opacity-100 text-white/40 hover:text-white transition-opacity p-2 ml-1 flex-shrink-0"
              aria-label="Delete conversation"
            >
              <svg width="14" height="14" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
              </svg>
            </button>
          </div>
        ))
      )}
    </div>
  )
}

function SidebarFooter({ initials, fullName, profileLoading, profileError, onClick, t }) {
  return (
    <Link
      to="/profile"
      onClick={onClick}
      className="px-4 py-3 flex items-center gap-3 flex-shrink-0 hover:bg-white/10 transition-colors cursor-pointer w-full text-left no-underline"
    >
      <div className="w-9 h-9 rounded-full bg-white dark:bg-hc-fg flex items-center justify-center text-field-dark dark:text-hc-bg text-xs font-bold flex-shrink-0">
        {initials}
      </div>
      <div className="min-w-0 flex-1">
        {profileError ? (
          <p className="text-white/50 text-sm truncate">{t.profileUnavailable}</p>
        ) : profileLoading && !fullName ? (
          <div className="w-24 h-3 bg-white/10 rounded animate-pulse" />
        ) : (
          <p className="text-white text-sm font-medium truncate">
            {fullName || 'Farmer'}
          </p>
        )}
        <p className="text-white/70 text-xs">{t.farmer}</p>
      </div>
    </Link>
  )
}

export default function Sidebar({ open, onClose }) {
  const { logout } = useAuth()
  const { lang, setLang, resetLang, t } = useLang()
  const { theme, toggleTheme } = useTheme()
  const navigate = useNavigate()
  const location = useLocation()
  const { listSessions, deleteSession, sessionsLoading, sessionsError } = useSessions()
  const { profile, loading: profileLoading, error: profileError } = useProfile()
  const [sessions, setSessions] = useState([])

  async function loadSessions() {
    const data = await listSessions()
    setSessions(data)
  }

  // Reload sessions on every navigation so new sessions appear
  useEffect(() => {
    loadSessions()
  }, [listSessions, location.key]) // eslint-disable-line react-hooks/exhaustive-deps

  function handleLogout() {
    logout()
    resetLang()
    navigate('/login')
  }

  async function handleDeleteSession(sessionId) {
    if (!window.confirm(t.deleteSessionConfirm || 'Are you sure you want to delete this conversation?')) {
      return
    }
    try {
      await deleteSession(sessionId)
      setSessions((prev) => prev.filter((s) => s.id !== sessionId))
      // Read active session from location at delete time to avoid stale closure.
      const activeSessionId = new URLSearchParams(location.search).get('session')
      if (activeSessionId === sessionId) {
        navigate('/')
      }
    } catch (err) {
      console.error('Failed to delete session:', err)
    }
  }

  const initials = profile?.full_name
    ? profile.full_name.split(' ').map((n) => n[0]).join('').slice(0, 2).toUpperCase()
    : 'F'

  const currentSessionId = new URLSearchParams(location.search).get('session')

  return (
    <>
      {/* Mobile overlay */}
      {open && (
        <div
          className="fixed inset-0 bg-black/50 z-20 md:hidden"
          onClick={onClose}
        />
      )}

      <aside
        aria-label={t.siteNavLabel}
        className={[
          'flex flex-col w-64 flex-shrink-0 bg-field-dark dark:bg-hc-sidebar-bg dark:border-r-2 dark:border-hc-border',
          'fixed inset-y-0 left-0 z-30 transition-transform duration-200 ease-in-out',
          open ? 'translate-x-0' : '-translate-x-full',
          'md:static md:translate-x-0',
        ].join(' ')}
      >
        {/* Brand */}
        <div className="px-5 pt-6 pb-4 flex-shrink-0">
          <p className="text-xl font-bold text-white tracking-tight">{t.appName}</p>
          <p className="text-xs text-emerald-200 mt-0.5">Arkansas Farming</p>
        </div>

        {/* New Chat button */}
        <div className="px-4 pb-4 flex-shrink-0">
          <button
            onClick={() => { navigate('/'); onClose?.() }}
            className="w-full border border-white/30 text-white rounded-lg py-2.5 text-sm font-medium
              hover:bg-white/10 transition-colors flex items-center justify-center gap-2 min-h-touch"
          >
            <svg width="16" height="16" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
            </svg>
            {t.newChat}
          </button>
        </div>

        {/* Nav + sessions */}
        <nav className="px-2 flex-1 flex flex-col overflow-hidden min-h-0">
          {/* Recent conversations header */}
          <div className="flex items-center gap-2 px-3 py-2 mt-2 flex-shrink-0">
            <svg width="14" height="14" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2} className="text-white/50">
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 6v6h4.5m4.5 0a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            <span className="text-[11px] font-semibold text-white/75 uppercase tracking-wider">
              {t.recentConversations}
            </span>
          </div>

          <SessionsList
            sessions={sessions}
            currentSessionId={currentSessionId}
            onNavigate={(id) => { navigate(`/?session=${id}`); onClose?.() }}
            onDelete={handleDeleteSession}
            loading={sessionsLoading}
            error={sessionsError}
            onRetry={loadSessions}
            t={t}
          />
        </nav>

        {/* Bottom navigation items */}
        <div className="px-2 pt-2 border-t border-white/10 flex-shrink-0">
          {profile?.is_admin && (
            <SidebarNavItem to="/admin" onClick={onClose}>
              <svg width="18" height="18" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2} aria-hidden="true">
                <path strokeLinecap="round" strokeLinejoin="round"
                  d="M10.5 6h9.75M10.5 6a1.5 1.5 0 11-3 0m3 0a1.5 1.5 0 10-3 0M3.75 6H7.5m3 12h9.75m-9.75 0a1.5 1.5 0 01-3 0m3 0a1.5 1.5 0 00-3 0m-3.75 0H7.5m9-6h3.75m-3.75 0a1.5 1.5 0 01-3 0m3 0a1.5 1.5 0 00-3 0m-9.75 0h9.75" />
              </svg>
              {t.admin}
            </SidebarNavItem>
          )}

          <SidebarNavItem to="/drift-report" onClick={onClose}>
            <svg width="18" height="18" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2} aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round"
                d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z" />
            </svg>
            {t.driftReport}
          </SidebarNavItem>

          <SidebarNavItem disabled ariaLabel="Settings (Coming soon)">
            <svg width="18" height="18" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2} aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round"
                d="M9.594 3.94c.09-.542.56-.94 1.11-.94h2.593c.55 0 1.02.398 1.11.94l.213 1.281c.063.374.313.686.645.87.074.04.147.083.22.127.324.196.72.257 1.075.124l1.217-.456a1.125 1.125 0 011.37.49l1.296 2.247a1.125 1.125 0 01-.26 1.431l-1.003.827c-.293.24-.438.613-.431.992a6.759 6.759 0 010 .255c-.007.378.138.75.43.99l1.005.828c.424.35.534.954.26 1.43l-1.298 2.247a1.125 1.125 0 01-1.369.491l-1.217-.456c-.355-.133-.75-.072-1.076.124a6.57 6.57 0 01-.22.128c-.331.183-.581.495-.644.869l-.213 1.28c-.09.543-.56.941-1.11.941h-2.594c-.55 0-1.019-.398-1.11-.94l-.213-1.281c-.062-.374-.312-.686-.644-.87a6.52 6.52 0 01-.22-.127c-.325-.196-.72-.257-1.076-.124l-1.217.456a1.125 1.125 0 01-1.369-.49l-1.297-2.247a1.125 1.125 0 01.26-1.431l1.004-.827c.292-.24.437-.613.43-.992a6.932 6.932 0 010-.255c.007-.378-.138-.75-.43-.99l-1.004-.828a1.125 1.125 0 01-.26-1.43l1.297-2.247a1.125 1.125 0 011.37-.491l1.216.456c.356.133.751.072 1.076-.124.072-.044.146-.087.22-.128.332-.183.582-.495.644-.869l.214-1.281z" />
              <path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
            </svg>
            {t.settings}
          </SidebarNavItem>

          <SidebarNavItem onClick={() => setLang(lang === 'en' ? 'es' : 'en')}>
            <svg width="18" height="18" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2} aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round"
                d="M12 21a9.004 9.004 0 008.716-6.747M12 21a9.004 9.004 0 01-8.716-6.747M12 21c2.485 0 4.5-4.03 4.5-9S14.485 3 12 3m0 18c-2.485 0-4.5-4.03-4.5-9S9.515 3 12 3m0 0a8.997 8.997 0 017.843 4.582M12 3a8.997 8.997 0 00-7.843 4.582m15.686 0A11.953 11.953 0 0112 10.5c-2.998 0-5.74-1.1-7.843-2.918m15.686 0A8.959 8.959 0 0121 12c0 .778-.099 1.533-.284 2.253M3 12a8.959 8.959 0 01.284-2.253" />
            </svg>
            {t.languages} ({lang.toUpperCase()})
          </SidebarNavItem>

          <SidebarNavItem
            onClick={toggleTheme}
            ariaPressed={theme === 'hc'}
            ariaLabel={theme === 'hc' ? t.highContrastOn : t.highContrastOff}
          >
            <svg width="18" height="18" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2} aria-hidden="true">
              <circle cx="12" cy="12" r="9" />
              <path d="M12 3a9 9 0 010 18z" fill="currentColor" />
            </svg>
            {t.highContrast} ({theme === 'hc' ? 'ON' : 'OFF'})
          </SidebarNavItem>

          <SidebarNavItem onClick={handleLogout}>
            <svg width="18" height="18" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2} aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round"
                d="M15.75 9V5.25A2.25 2.25 0 0013.5 3h-6a2.25 2.25 0 00-2.25 2.25v13.5A2.25 2.25 0 007.5 21h6a2.25 2.25 0 002.25-2.25V15M12 9l-3 3m0 0l3 3m-3-3h12.75" />
            </svg>
            {t.logout}
          </SidebarNavItem>
        </div>

        <SidebarFooter
          initials={initials}
          fullName={profile?.full_name}
          profileLoading={profileLoading}
          profileError={profileError}
          onClick={onClose}
          t={t}
        />
      </aside>
    </>
  )
}
