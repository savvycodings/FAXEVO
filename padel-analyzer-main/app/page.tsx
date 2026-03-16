'use client'

import Image from 'next/image'
import VideoUpload from '@/components/VideoUpload'
import LanguageToggle from '@/components/LanguageToggle'
import { useLanguage } from '@/lib/language-context'
import { t } from '@/lib/translations'

export default function Home() {
  const { lang } = useLanguage()

  return (
    <main className="flex min-h-screen flex-col items-center justify-center p-4 bg-black text-[#E0E0E0]">
      <div className="z-10 max-w-5xl w-full items-center justify-between font-mono text-sm lg:flex mb-12">
        <div className="fixed left-0 top-0 flex w-full justify-center border-b border-[#333333] bg-black pb-6 pt-8 backdrop-blur-2xl lg:static lg:w-auto lg:rounded-xl lg:border lg:p-4 lg:bg-[#333333]/50">
          <div className="flex items-center gap-2">
            <Image src="/logo.jpg" alt="Padel AInalyzer logo" height={40} width={65} className="object-contain" />
            <span>Padel<span className="text-[#FF8C66] font-bold mx-1">AI</span>nalyzer</span>
          </div>
        </div>
        <div className="fixed top-6 right-4 z-50 lg:static lg:z-auto">
          <LanguageToggle />
        </div>
        <div className="fixed bottom-0 left-0 flex h-48 w-full items-end justify-center bg-gradient-to-t from-black via-black lg:static lg:h-auto lg:w-auto lg:bg-none">
          <a
            className="pointer-events-none flex place-items-center gap-2 p-8 lg:pointer-events-auto lg:p-0 text-[#8C8C8C] hover:text-[#E0E0E0]"
            href="https://modal.com"
            target="_blank"
            rel="noopener noreferrer"
          >
            {t[lang].poweredBy}
          </a>
        </div>
      </div>

      <div className="relative flex flex-col items-center place-items-center before:absolute before:h-[300px] before:w-[480px] before:-translate-x-1/2 before:rounded-full before:bg-gradient-to-br before:from-[#FF8C66] before:to-[#FF4444] before:opacity-10 before:blur-3xl before:content-[''] after:absolute after:-z-20 after:h-[180px] after:w-[240px] after:translate-x-1/3 after:bg-gradient-to-t after:from-[#FF8C66] after:via-[#FF6644] after:blur-3xl after:content-[''] z-0">
        <h1 className="text-4xl md:text-6xl font-bold text-center mb-6 tracking-tight">
          {t[lang].taglinePrefix}{' '}
          <span className="text-transparent bg-clip-text bg-gradient-to-r from-[#FF8C66] to-[#FFB347]">
            {t[lang].taglineHighlight}
          </span>
        </h1>
        <p className="text-[#8C8C8C] text-center max-w-xl mb-12 text-lg">
          {t[lang].subtitle}
        </p>

        <VideoUpload />
      </div>

      <div className="mb-32 grid text-center lg:max-w-5xl lg:w-full lg:mb-0 lg:grid-cols-3 lg:text-left mt-24 gap-8">
        <div className="group rounded-lg border border-transparent px-5 py-4 transition-colors hover:border-[#333333] hover:bg-[#333333]/30">
          <h2 className="mb-3 text-2xl font-semibold text-[#E0E0E0]">
            {t[lang].uploadStep}{' '}
            <span className="inline-block transition-transform group-hover:translate-x-1 motion-reduce:transform-none">
              -&gt;
            </span>
          </h2>
          <p className="m-0 max-w-[30ch] text-sm text-[#8C8C8C]">
            {t[lang].uploadDesc}
          </p>
        </div>

        <div className="group rounded-lg border border-transparent px-5 py-4 transition-colors hover:border-[#333333] hover:bg-[#333333]/30">
          <h2 className="mb-3 text-2xl font-semibold text-[#E0E0E0]">
            {t[lang].analyzeStep}{' '}
            <span className="inline-block transition-transform group-hover:translate-x-1 motion-reduce:transform-none">
              -&gt;
            </span>
          </h2>
          <p className="m-0 max-w-[30ch] text-sm text-[#8C8C8C]">
            {t[lang].analyzeDesc}
          </p>
        </div>

        <div className="group rounded-lg border border-transparent px-5 py-4 transition-colors hover:border-[#333333] hover:bg-[#333333]/30">
          <h2 className="mb-3 text-2xl font-semibold text-[#E0E0E0]">
            {t[lang].improveStep}{' '}
            <span className="inline-block transition-transform group-hover:translate-x-1 motion-reduce:transform-none">
              -&gt;
            </span>
          </h2>
          <p className="m-0 max-w-[30ch] text-sm text-[#8C8C8C]">
            {t[lang].improveDesc}
          </p>
        </div>
      </div>
    </main>
  )
}
