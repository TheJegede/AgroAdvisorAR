import { createContext, useContext, useState } from 'react'
import { LABELS } from '../constants/i18n'

const LangContext = createContext(null)
const STORAGE_KEY = 'agro_lang'
const DEFAULT_LANG = 'en'

function getStoredLang() {
  const stored = localStorage.getItem(STORAGE_KEY)
  return LABELS[stored] ? stored : DEFAULT_LANG
}

export function LangProvider({ children }) {
  const [lang, setLangState] = useState(getStoredLang)

  function setLang(l) {
    const nextLang = LABELS[l] ? l : DEFAULT_LANG
    localStorage.setItem(STORAGE_KEY, nextLang)
    setLangState(nextLang)
  }

  function resetLang() {
    localStorage.removeItem(STORAGE_KEY)
    setLangState(DEFAULT_LANG)
  }

  const t = LABELS[lang]

  return (
    <LangContext.Provider value={{ lang, setLang, resetLang, t }}>
      {children}
    </LangContext.Provider>
  )
}

export function useLang() {
  return useContext(LangContext)
}
