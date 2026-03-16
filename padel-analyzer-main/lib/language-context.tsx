'use client'

import { createContext, useContext, useState, useEffect, ReactNode } from 'react'

export type Language = 'en' | 'es'

interface LanguageContextValue {
  lang: Language
  setLang: (l: Language) => void
}

const LanguageContext = createContext<LanguageContextValue>({
  lang: 'en',
  setLang: () => {}
})

export function LanguageProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Language>('en')

  // Read from localStorage after mount to avoid SSR mismatch
  useEffect(() => {
    const stored = localStorage.getItem('padel-lang')
    if (stored === 'es' || stored === 'en') {
      setLangState(stored)
    }
  }, [])

  const setLang = (l: Language) => {
    setLangState(l)
    localStorage.setItem('padel-lang', l)
  }

  return (
    <LanguageContext.Provider value={{ lang, setLang }}>
      {children}
    </LanguageContext.Provider>
  )
}

export function useLanguage() {
  return useContext(LanguageContext)
}
