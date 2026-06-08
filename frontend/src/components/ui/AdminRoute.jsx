import { Navigate } from 'react-router-dom'
import { useProfile } from '../../hooks/useProfile'
import { useLang } from '../../contexts/LangContext'
import Skeleton from './Skeleton'

export default function AdminRoute({ children }) {
  const { profile, loading } = useProfile()
  const { t } = useLang()

  if (loading) {
    return (
      <div className="flex-1 p-4 md:p-6 space-y-6">
        <Skeleton variant="text" className="w-48 h-8" />
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="bg-white border border-gray-100 rounded-card p-4 flex flex-col gap-2 dark:bg-hc-surface dark:border-2 dark:border-hc-border">
              <Skeleton variant="text" className="w-1/2 h-3" />
              <Skeleton variant="text" className="w-3/4 h-8" />
            </div>
          ))}
        </div>
      </div>
    )
  }

  if (!profile?.is_admin) {
    return (
      <div className="flex-1 flex items-center justify-center p-6">
        <div className="bg-arred/10 border border-arred rounded-card p-6 text-arred-dark max-w-md text-center">
          {t.accessDenied}
          <div className="mt-3">
            <Navigate to="/" replace />
          </div>
        </div>
      </div>
    )
  }

  return children
}
