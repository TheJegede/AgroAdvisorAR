import { createContext, useContext, useState, useEffect } from 'react'
import { clearAuthStorage, getAccessToken, setAuthTokens } from '../lib/authTokens'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [token, setToken] = useState(null)
  const [isLoading, setIsLoading] = useState(true)

  useEffect(() => {
    const stored = getAccessToken()
    if (stored) setToken(stored)
    setIsLoading(false)
  }, [])

  function login(accessToken, refreshToken) {
    setAuthTokens(accessToken, refreshToken)
    setToken(accessToken)
  }

  function logout() {
    clearAuthStorage()
    setToken(null)
  }

  return (
    <AuthContext.Provider value={{ token, isLoading, login, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  return useContext(AuthContext)
}
