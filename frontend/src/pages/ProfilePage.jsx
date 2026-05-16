import { Link } from 'react-router-dom'
import { useLang } from '../contexts/LangContext'
import ProfileForm from '../components/profile/ProfileForm'

export default function ProfilePage() {
  const { t } = useLang()
  return (
    <div className="flex-1 overflow-y-auto px-4 py-6">
      <div className="max-w-sm mx-auto">
        <div className="flex items-center gap-3 mb-6">
          <Link to="/" aria-label={t.back} className="text-field dark:text-hc-fg">
            <svg width="20" height="20" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2} aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 19.5L8.25 12l7.5-7.5" />
            </svg>
          </Link>
          <h1 className="text-xl font-bold text-charcoal dark:text-hc-fg">{t.profile}</h1>
        </div>
        <div className="bg-white dark:bg-hc-surface rounded-card shadow-sm dark:shadow-none border border-gray-100 dark:border-2 dark:border-hc-border p-6">
          <ProfileForm />
        </div>
      </div>
    </div>
  )
}
