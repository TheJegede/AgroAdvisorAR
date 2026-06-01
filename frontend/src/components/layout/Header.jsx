import { Link } from 'react-router-dom'
import { useLang } from '../../contexts/LangContext'

export default function Header({ onMenuClick }) {
  const { t } = useLang()

  return (
    <header className="h-14 bg-white dark:bg-hc-bg border-b border-gray-200 dark:border-hc-border dark:border-b-2 flex items-center px-4 gap-3 flex-shrink-0">
      {/* Hamburger — mobile only */}
      <button
        className="md:hidden flex items-center justify-center w-11 h-11 rounded-lg hover:bg-gray-100 dark:hover:bg-hc-muted dark:hover:text-hc-bg transition-colors text-charcoal dark:text-hc-fg"
        onClick={onMenuClick}
        aria-label="Open menu"
      >
        <svg width="20" height="20" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 6.75h16.5M3.75 12h16.5m-16.5 5.25h16.5" />
        </svg>
      </button>

      <h1 className="font-bold text-lg text-charcoal dark:text-hc-fg flex-1">{t.appName}</h1>

      <Link
        to="/profile"
        className="flex items-center justify-center w-11 h-11 rounded-lg hover:bg-gray-100 dark:hover:bg-hc-muted dark:hover:text-hc-bg transition-colors text-gray-500 dark:text-hc-fg"
        aria-label={t.profile}
      >
        <svg width="20" height="20" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round"
            d="M15.75 6a3.75 3.75 0 11-7.5 0 3.75 3.75 0 017.5 0zM4.501 20.118a7.5 7.5 0 0114.998 0A17.933 17.933 0 0112 21.75c-2.676 0-5.216-.584-7.499-1.632z" />
        </svg>
      </Link>
    </header>
  )
}
