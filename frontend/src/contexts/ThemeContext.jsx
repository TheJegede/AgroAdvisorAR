import { createContext, useContext, useEffect, useState } from 'react'

const ThemeContext = createContext(null)

const STORAGE_KEY = 'agroar:theme'
const VALID = ['light', 'hc']

export function ThemeProvider({ children }) {
  const [theme, setThemeState] = useState(() => {
    const stored = localStorage.getItem(STORAGE_KEY)
    return VALID.includes(stored) ? stored : 'light'
  })

  useEffect(() => {
    const root = document.documentElement
    if (theme === 'hc') {
      root.setAttribute('data-theme', 'hc')
    } else {
      root.removeAttribute('data-theme')
    }
  }, [theme])

  function setTheme(t) {
    if (!VALID.includes(t)) return
    localStorage.setItem(STORAGE_KEY, t)
    setThemeState(t)
  }

  function toggleTheme() {
    setTheme(theme === 'hc' ? 'light' : 'hc')
  }

  return (
    <ThemeContext.Provider value={{ theme, setTheme, toggleTheme }}>
      {children}
    </ThemeContext.Provider>
  )
}

export function useTheme() {
  return useContext(ThemeContext)
}
