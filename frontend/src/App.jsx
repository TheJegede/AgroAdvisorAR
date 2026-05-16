import { BrowserRouter, Routes, Route, Navigate, useLocation } from 'react-router-dom'
import { AuthProvider } from './contexts/AuthContext'
import { LangProvider } from './contexts/LangContext'
import { ThemeProvider } from './contexts/ThemeContext'
import AppShell from './components/layout/AppShell'
import ProtectedRoute from './components/ui/ProtectedRoute'
import AdminRoute from './components/ui/AdminRoute'
import LoginPage from './pages/LoginPage'
import RegisterPage from './pages/RegisterPage'
import ForgotPasswordPage from './pages/ForgotPasswordPage'
import ResetPasswordPage from './pages/ResetPasswordPage'
import ChatPage from './pages/ChatPage'
import ProfilePage from './pages/ProfilePage'
import SessionsPage from './pages/SessionsPage'
import AdminDashboardPage from './pages/AdminDashboardPage'
import EvalQueuePage from './pages/EvalQueuePage'

// Remounts ChatPage when ?session param changes so session state fully resets
function ChatPageWrapper() {
  const location = useLocation()
  const sessionParam = new URLSearchParams(location.search).get('session') ?? 'new'
  return <ChatPage key={sessionParam} />
}

export default function App() {
  return (
    <AuthProvider>
      <LangProvider>
        <ThemeProvider>
        <BrowserRouter>
          <Routes>
            <Route path="/login" element={<LoginPage />} />
            <Route path="/register" element={<RegisterPage />} />
            <Route path="/forgot-password" element={<ForgotPasswordPage />} />
            <Route path="/reset-password" element={<ResetPasswordPage />} />
            <Route
              element={
                <ProtectedRoute>
                  <AppShell />
                </ProtectedRoute>
              }
            >
              <Route path="/" element={<ChatPageWrapper />} />
              <Route path="/profile" element={<ProfilePage />} />
              <Route path="/sessions" element={<SessionsPage />} />
              <Route
                path="/admin"
                element={<AdminRoute><AdminDashboardPage /></AdminRoute>}
              />
              <Route
                path="/admin/queue"
                element={<AdminRoute><EvalQueuePage /></AdminRoute>}
              />
            </Route>
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </BrowserRouter>
        </ThemeProvider>
      </LangProvider>
    </AuthProvider>
  )
}
