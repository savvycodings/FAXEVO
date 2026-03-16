'use client'

import { useLanguage } from '@/lib/language-context'

export default function LanguageToggle() {
  const { lang, setLang } = useLanguage()

  return (
    <div className="flex items-center gap-1 text-sm font-medium bg-[#333333] border border-[#333333] rounded-full px-3 py-1.5">
      <button
        onClick={() => setLang('en')}
        className={`transition-colors ${lang === 'en' ? 'text-[#FF8C66]' : 'text-[#8C8C8C] hover:text-[#E0E0E0]'}`}
      >
        EN
      </button>
      <span className="text-[#8C8C8C]">|</span>
      <button
        onClick={() => setLang('es')}
        className={`transition-colors ${lang === 'es' ? 'text-[#FF8C66]' : 'text-[#8C8C8C] hover:text-[#E0E0E0]'}`}
      >
        ES
      </button>
    </div>
  )
}
