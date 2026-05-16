import { Navigate } from 'react-router-dom'
import { useProfile } from '../../hooks/useProfile'
import { useLang } from '../../contexts/LangContext'
import Spinner from './Spinner'

export default function AdminRoute({ children }) {
  const { profile, loading } = useProfile()
  const { t } = useLang()

  if (loading) {
    return (
      <div className="flex items-center justify-center flex-1">
        <Spinner />
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
