import { createContext, useContext, useState } from 'react'
import { LABELS } from '../constants/i18n'

const LangContext = createContext(null)

export function LangProvider({ children }) {
  const [lang, setLangState] = useState(
    () => localStorage.getItem('agro_lang') || 'en'
  )

  function setLang(l) {
    localStorage.setItem('agro_lang', l)
    setLangState(l)
  }

  const t = LABELS[lang]

  return (
    <LangContext.Provider value={{ lang, setLang, t }}>
      {children}
    </LangContext.Provider>
  )
}

export function useLang() {
  return useContext(LangContext)
}
