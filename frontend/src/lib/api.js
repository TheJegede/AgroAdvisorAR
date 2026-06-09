import axios from 'axios'
import {
  clearAuthStorage,
  getAccessToken,
  redirectToLogin,
  refreshAuthToken,
} from './authTokens'

// Base path is relative; in prod the Vercel rewrite proxies /api/* to the HF backend.
const api = axios.create({
  baseURL: '/api/v1',
})

api.interceptors.request.use((config) => {
  const token = getAccessToken()
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

api.interceptors.response.use(
  (res) => res,
  async (err) => {
    if (err.response?.status === 401) {
      const isAuthEndpoint = err.config?.url?.includes('/auth/')
      if (!isAuthEndpoint && !err.config?._retry) {
        try {
          const accessToken = await refreshAuthToken()
          err.config._retry = true
          err.config.headers = err.config.headers ?? {}
          err.config.headers.Authorization = `Bearer ${accessToken}`
          return api(err.config)
        } catch {
          clearAuthStorage()
          redirectToLogin()
        }
      } else if (!isAuthEndpoint) {
        clearAuthStorage()
        redirectToLogin()
      }
    }
    return Promise.reject(err)
  }
)

export default api
