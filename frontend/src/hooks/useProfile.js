import { useState, useEffect } from 'react'
import api from '../lib/api'

export function useProfile() {
  const [profile, setProfile] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    api.get('/profile')
      .then(({ data }) => setProfile(data))
      .catch((err) => setError(err.response?.data?.detail || 'Failed to load profile'))
      .finally(() => setLoading(false))
  }, [])

  async function updateProfile(fields) {
    const { data } = await api.patch('/profile', fields)
    setProfile(data)
    return data
  }

  return { profile, loading, error, updateProfile }
}
