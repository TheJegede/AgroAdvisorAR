import { Navigate } from 'react-router-dom'
import { useAuth } from '../../contexts/AuthContext'
import Skeleton from './Skeleton'

export default function ProtectedRoute({ children }) {
  const { token, isLoading } = useAuth()

  if (isLoading) {
    return (
      <div className="flex flex-col gap-4 p-4 min-h-[100dvh] bg-parchment dark:bg-hc-bg">
        <Skeleton count={3} />
      </div>
    )
  }

  if (!token) return <Navigate to="/login" replace />

  return children
}
