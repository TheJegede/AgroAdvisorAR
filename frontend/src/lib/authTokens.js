const ACCESS_TOKEN_KEY = 'access_token'
const REFRESH_TOKEN_KEY = 'refresh_token'

let refreshPromise = null

function storage() {
  return typeof localStorage === 'undefined' ? null : localStorage
}

export function getAccessToken() {
  return storage()?.getItem(ACCESS_TOKEN_KEY) ?? null
}

export function getRefreshToken() {
  return storage()?.getItem(REFRESH_TOKEN_KEY) ?? null
}

export function setAuthTokens(accessToken, refreshToken) {
  const store = storage()
  if (!store) return
  store.setItem(ACCESS_TOKEN_KEY, accessToken)
  store.setItem(REFRESH_TOKEN_KEY, refreshToken)
}

export function clearAuthStorage() {
  const store = storage()
  if (!store) return
  store.removeItem(ACCESS_TOKEN_KEY)
  store.removeItem(REFRESH_TOKEN_KEY)
}

export function redirectToLogin() {
  if (typeof window !== 'undefined') {
    window.location.href = '/login'
  }
}

export async function refreshAuthToken() {
  const refreshToken = getRefreshToken()
  if (!refreshToken) {
    throw new Error('Missing refresh token')
  }

  if (!refreshPromise) {
    refreshPromise = fetch('/api/v1/auth/refresh', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: refreshToken }),
    })
      .then(async (response) => {
        if (!response.ok) {
          throw new Error(`Refresh failed: ${response.status}`)
        }
        const data = await response.json()
        setAuthTokens(data.access_token, data.refresh_token)
        return data.access_token
      })
      .finally(() => {
        refreshPromise = null
      })
  }

  return refreshPromise
}
