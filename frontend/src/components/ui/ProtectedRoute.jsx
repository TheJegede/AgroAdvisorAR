import { Navigate } from 'react-router-dom'
import { useAuth } from '../../contexts/AuthContext'
import Spinner from './Spinner'

export default function ProtectedRoute({ children }) {
  const { token, isLoading } = useAuth()

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-[100dvh] bg-parchment">
        <Spinner />
      </div>
    )
  }

  if (!token) return <Navigate to="/login" replace />

  return children
}
