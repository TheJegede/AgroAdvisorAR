import { lazy, Suspense } from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { AuthProvider } from './contexts/AuthContext'
import { LangProvider } from './contexts/LangContext'
import { ThemeProvider } from './contexts/ThemeContext'
import AppShell from './components/layout/AppShell'
import ProtectedRoute from './components/ui/ProtectedRoute'
import AdminRoute from './components/ui/AdminRoute'

const LoginPage = lazy(() => import('./pages/LoginPage'))
const AuthCallbackPage = lazy(() => import('./pages/AuthCallbackPage'))
const RegisterPage = lazy(() => import('./pages/RegisterPage'))
const ForgotPasswordPage = lazy(() => import('./pages/ForgotPasswordPage'))
const ResetPasswordPage = lazy(() => import('./pages/ResetPasswordPage'))
const ChatPage = lazy(() => import('./pages/ChatPage'))
const ProfilePage = lazy(() => import('./pages/ProfilePage'))
const SessionsPage = lazy(() => import('./pages/SessionsPage'))
const AdminDashboardPage = lazy(() => import('./pages/AdminDashboardPage'))
const EvalQueuePage = lazy(() => import('./pages/EvalQueuePage'))
const DriftReportPage = lazy(() => import('./pages/DriftReportPage'))
const SprayCheckPage = lazy(() => import('./pages/SprayCheckPage'))

// ChatPage wrapper component. State is reset internally inside ChatPage
// based on changes to the session query parameter.
function ChatPageWrapper() {
  return <ChatPage />
}

export default function App() {
  return (
    <AuthProvider>
      <LangProvider>
        <ThemeProvider>
        <BrowserRouter>
          <Suspense fallback={<div className="min-h-screen bg-cream dark:bg-hc-bg" />}>
            <Routes>
              <Route path="/login" element={<LoginPage />} />
              <Route path="/register" element={<RegisterPage />} />
              <Route path="/forgot-password" element={<ForgotPasswordPage />} />
              <Route path="/reset-password" element={<ResetPasswordPage />} />
              <Route path="/auth/callback" element={<AuthCallbackPage />} />
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
                <Route path="/drift-report" element={<DriftReportPage />} />
                <Route path="/spray-check" element={<SprayCheckPage />} />
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
          </Suspense>
        </BrowserRouter>
        </ThemeProvider>
      </LangProvider>
    </AuthProvider>
  )
}
