'use client'

import { useState, useCallback } from 'react'
import { useRouter } from 'next/navigation'
import { motion, AnimatePresence } from 'framer-motion'
import { UploadCloud, FileVideo, X, CheckCircle2, AlertCircle, Loader2 } from 'lucide-react'
import { supabase } from '@/lib/supabase'
import { clsx } from 'clsx'
import { twMerge } from 'tailwind-merge'
import { useLanguage } from '@/lib/language-context'
import { t } from '@/lib/translations'

export default function VideoUpload() {
  const router = useRouter()
  const { lang } = useLanguage()
  const [dragActive, setDragActive] = useState(false)
  const [file, setFile] = useState<File | null>(null)
  const [uploading, setUploading] = useState(false)
  const [analyzing, setAnalyzing] = useState(false)
  const [progress, setProgress] = useState(0)
  const [status, setStatus] = useState<'idle' | 'uploading' | 'analyzing' | 'success' | 'error'>('idle')
  const [message, setMessage] = useState('')
  const [analysisId, setAnalysisId] = useState<string | null>(null)

  const handleDrag = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    if (e.type === 'dragenter' || e.type === 'dragover') {
      setDragActive(true)
    } else if (e.type === 'dragleave') {
      setDragActive(false)
    }
  }, [])

  const validateFile = (file: File) => {
    if (!file.type.startsWith('video/')) {
      setMessage(t[lang].errorVideoOnly)
      setStatus('error')
      return false
    }
    if (file.size > 50 * 1024 * 1024) {
      setMessage(t[lang].errorFileSize)
      setStatus('error')
      return false
    }
    return true
  }

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    setDragActive(false)
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      const droppedFile = e.dataTransfer.files[0]
      if (validateFile(droppedFile)) {
        setFile(droppedFile)
        setStatus('idle')
        setMessage('')
      }
    }
  }, [])

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    e.preventDefault()
    if (e.target.files && e.target.files[0]) {
      const selectedFile = e.target.files[0]
      if (validateFile(selectedFile)) {
        setFile(selectedFile)
        setStatus('idle')
        setMessage('')
      }
    }
  }

  const uploadVideo = async () => {
    if (!file) return

    try {
      setUploading(true)
      setStatus('uploading')
      setProgress(0)
      setMessage('')

      console.log('[UPLOAD] Starting upload...', { fileName: file.name, size: file.size })

      const fileExt = file.name.split('.').pop()
      const fileName = `${Math.random().toString(36).substring(2, 15)}_${Date.now()}.${fileExt}`
      const filePath = `${fileName}`

      console.log('[UPLOAD] Uploading to Supabase Storage...', { bucket: 'videos', path: filePath })

      // 1. Upload to Storage
      const { error: uploadError, data: uploadData } = await supabase.storage
        .from('videos')
        .upload(filePath, file, {
          cacheControl: '3600',
          upsert: false
        })

      if (uploadError) {
        console.error('[UPLOAD] Storage error:', uploadError)
        throw new Error(`Storage upload failed: ${uploadError.message}`)
      }

      console.log('[UPLOAD] Storage upload complete:', uploadData)

      setProgress(50)

      // 2. Get Public URL
      const { data: { publicUrl } } = supabase.storage
        .from('videos')
        .getPublicUrl(filePath)

      console.log('[UPLOAD] Public URL:', publicUrl)

      // 3. Create DB Record
      console.log('[UPLOAD] Creating database record...')
      const { data: analysisData, error: dbError } = await supabase
        .from('analyses')
        .insert({
          video_url: publicUrl,
          status: 'uploading'
        })
        .select()
        .single()

      if (dbError) {
        console.error('[UPLOAD] Database error:', dbError)
        throw new Error(`Database insert failed: ${dbError.message}`)
      }

      console.log('[UPLOAD] Database record created:', analysisData)
      setAnalysisId(analysisData.id)  // Store ID for navigation

      setProgress(100)
      setUploading(false)
      setAnalyzing(true)
      setStatus('analyzing')
      setMessage(t[lang].analyzingMovement)

      // 4. Trigger Analysis via Next.js API -> Modal
      console.log('[UPLOAD] Triggering analysis API...')
      const response = await fetch('/api/analyze', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          video_url: publicUrl,
          analysis_id: analysisData.id
        })
      })

      if (!response.ok) {
        const err = await response.json()
        console.error('[UPLOAD] API error:', err)
        throw new Error(err.error || 'Analysis failed to start')
      }

      const responseData = await response.json()
      console.log('[UPLOAD] API response:', responseData)

      setAnalysisId(analysisData.id)  // Store ID for manual navigation

      setProgress(100)
      setUploading(false)
      setAnalyzing(true)
      setStatus('analyzing')
      setMessage(t[lang].analyzingMovement)

      // Redirect to results page - use analysisData.id directly (already in scope)
      console.log('[UPLOAD] Redirecting to results...')
      console.log('[UPLOAD] Analysis ID:', analysisData.id)
      console.log('[UPLOAD] Redirect URL:', `/analysis/${analysisData.id}`)
      
      setTimeout(() => {
        console.log('[UPLOAD] Executing forced navigation...')
        window.location.href = `/analysis/${analysisData.id}`
      }, 500)

    } catch (error: any) {
      console.error('[UPLOAD] Fatal error:', error)
      setStatus('error')
      setMessage(error.message || 'Upload failed')
      setUploading(false)
      setAnalyzing(false)
    }
  }

  return (
    <div className="w-full max-w-xl mx-auto p-4">
      <div
        className={twMerge(
          "relative border-2 border-dashed rounded-xl p-8 transition-all duration-200 flex flex-col items-center justify-center min-h-[300px]",
          dragActive ? "border-[#FF8C66] bg-[#FF8C66]/5" : "border-[#333333] bg-[#333333]/30",
          status === 'success' ? "border-green-500 bg-green-500/10" : ""
        )}
        onDragEnter={handleDrag}
        onDragLeave={handleDrag}
        onDragOver={handleDrag}
        onDrop={handleDrop}
      >
        <AnimatePresence mode="wait">
          {!file ? (
            <motion.div
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -10 }}
              className="flex flex-col items-center text-center"
            >
              <div className="w-16 h-16 bg-[#333333]/50 rounded-full flex items-center justify-center mb-4">
                <UploadCloud className="w-8 h-8 text-[#8C8C8C]" />
              </div>
              <p className="text-lg font-medium text-[#E0E0E0] mb-2">{t[lang].dragDrop}</p>
              <p className="text-sm text-[#8C8C8C] mb-6">{t[lang].fileTypes}</p>
              <label className="btn-primary cursor-pointer px-6 py-2 bg-[#FF8C66] hover:bg-[#FF6644] text-[#E0E0E0] rounded-full font-medium transition-colors">
                <span>{t[lang].selectFile}</span>
                <input type="file" className="hidden" accept="video/*" onChange={handleChange} />
              </label>
            </motion.div>
          ) : status === 'analyzing' ? (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              className="w-full"
            >
              <div className="text-center py-8">
                <Loader2 className="w-12 h-12 text-[#FF8C66] animate-spin mx-auto mb-4" />
                <p className="text-lg font-medium text-white mb-2">{t[lang].analyzingMovement}</p>
                <p className="text-sm text-[#8C8C8C]">{t[lang].analyzingSubtext}</p>
                <p className="text-xs text-gray-500 mt-4">{t[lang].redirecting}</p>
              </div>
            </motion.div>
          ) : status === 'success' ? (
            <motion.div
              initial={{ opacity: 0, scale: 0.9 }}
              animate={{ opacity: 1, scale: 1 }}
              className="flex flex-col items-center"
            >
              <div className="w-16 h-16 bg-green-500/20 rounded-full flex items-center justify-center mb-4">
                <CheckCircle2 className="w-10 h-10 text-green-500" />
              </div>
              <p className="text-xl font-bold text-[#E0E0E0] mb-2">{t[lang].analysisStarted}</p>
              <p className="text-[#8C8C8C]">{t[lang].videoProcessing}</p>
              <button
                onClick={() => router.push(`/analysis/${analysisId || ''}`)}
                className="mt-4 px-4 py-2 bg-[#FF8C66] hover:bg-[#FF6644] text-[#E0E0E0] rounded-lg font-medium transition-all"
              >
                {t[lang].viewResults}
              </button>
              <button
                onClick={() => { setFile(null); setStatus('idle'); }}
                className="mt-2 text-sm text-[#8C8C8C] hover:text-[#E0E0E0] underline"
              >
                {t[lang].analyzeAnother}
              </button>
            </motion.div>
          ) : (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              className="w-full"
            >
              <div className="flex items-center justify-between mb-4 bg-[#333333]/30 p-3 rounded-lg">
                <div className="flex items-center space-x-3">
                  <div className="w-10 h-10 bg-[#FF8C66]/20 rounded-lg flex items-center justify-center">
                    <FileVideo className="w-5 h-5 text-[#FF8C66]" />
                  </div>
                  <div className="text-left">
                    <p className="text-sm font-medium text-[#E0E0E0] truncate max-w-[200px]">{file.name}</p>
                    <p className="text-xs text-[#8C8C8C]">{(file.size / (1024 * 1024)).toFixed(1)} MB</p>
                  </div>
                </div>
                {!uploading && !analyzing && (
                  <button onClick={() => setFile(null)} className="p-1 hover:bg-[#333333] rounded-full transition-colors">
                    <X className="w-5 h-5 text-[#8C8C8C]" />
                  </button>
                )}
              </div>

              {uploading || analyzing ? (
                <div className="space-y-2">
                  <div className="flex justify-between text-xs text-[#8C8C8C]">
                    <span>{analyzing ? t[lang].analyzing : t[lang].uploading}</span>
                    <span>{analyzing ? '' : `${progress}%`}</span>
                  </div>
                  <div className="w-full bg-[#333333] rounded-full h-2 overflow-hidden">
                    <motion.div
                      className={twMerge("h-full", "bg-[#FF8C66]")}
                      initial={{ width: 0 }}
                      animate={{ width: analyzing ? "100%" : `${progress}%` }}
                      transition={analyzing ? { repeat: Infinity, duration: 1.5 } : {}}
                    />
                  </div>
                </div>
              ) : (
                <button 
                  onClick={uploadVideo}
                  className="w-full py-3 bg-[#FF8C66] hover:bg-[#FF6644] text-[#E0E0E0] rounded-lg font-bold transition-all shadow-lg shadow-[#FF8C66]/20"
                >
                  {t[lang].analyzeBtn}
                </button>
              )}
              
              {status === 'error' && (
                <div className="mt-4 p-3 bg-red-500/10 border border-red-500/20 rounded-lg flex items-center gap-2 text-red-400 text-sm">
                  <AlertCircle className="w-4 h-4" />
                  <span>{message}</span>
                </div>
              )}
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  )
}
