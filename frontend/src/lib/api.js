import axios from 'axios'

const api = axios.create({
  baseURL: '/api/v1',
})

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

api.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.response?.status === 401) {
      const isAuthEndpoint = err.config?.url?.includes('/auth/')
      if (!isAuthEndpoint) {
        localStorage.removeItem('access_token')
        localStorage.removeItem('refresh_token')
        localStorage.removeItem('agro_lang')
        window.location.href = '/login'
      }
    }
    return Promise.reject(err)
  }
)

export default api
