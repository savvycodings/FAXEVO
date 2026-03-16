'use client'

import { useEffect, useState } from 'react'
import { useParams, useRouter } from 'next/navigation'
import { supabase } from '@/lib/supabase'
import { motion } from 'framer-motion'
import {
  CheckCircle2,
  XCircle,
  Loader2,
  ArrowLeft,
  Activity,
  Target,
  TrendingUp,
  AlertTriangle,
  Lightbulb,
  Eye,
  Dumbbell
} from 'lucide-react'
import { useLanguage } from '@/lib/language-context'
import { t } from '@/lib/translations'
import LanguageToggle from '@/components/LanguageToggle'

type AnalysisStatus = 'uploading' | 'processing' | 'completed' | 'failed'

interface AIAnalysisContent {
  diagnosis: string
  observations: string[]
  recommendations: string[]
}

interface AIAnalysis {
  score?: number
  rating: string
  // New bilingual structure
  en?: AIAnalysisContent
  es?: AIAnalysisContent
  // Legacy flat structure (old records)
  diagnosis?: string
  observations?: string[]
  recommendations?: string[]
}

interface AnalysisMetrics {
  total_frames: number
  analyzed_frames: number
  pose_data: any[]
  ai_analysis?: AIAnalysis
}

interface AnalysisData {
  id: string
  video_url: string
  status: AnalysisStatus
  metrics?: AnalysisMetrics
  feedback_text?: string
  created_at: string
}

function getAnalysisContent(aiAnalysis: AIAnalysis, lang: 'en' | 'es'): AIAnalysisContent {
  // New bilingual record
  if (aiAnalysis.en || aiAnalysis.es) {
    const content = aiAnalysis[lang] ?? aiAnalysis.en ?? aiAnalysis.es
    return content ?? { diagnosis: '', observations: [], recommendations: [] }
  }
  // Legacy flat record
  return {
    diagnosis: aiAnalysis.diagnosis ?? '',
    observations: aiAnalysis.observations ?? [],
    recommendations: aiAnalysis.recommendations ?? []
  }
}

function ScoreCircle({ score, colorClass }: { score: number; colorClass: string }) {
  const radius = 28
  const circumference = 2 * Math.PI * radius
  const fill = (score / 10) * circumference

  return (
    <div className="relative w-16 h-16 flex items-center justify-center">
      <svg className="absolute" width="64" height="64" viewBox="0 0 64 64">
        <circle
          cx="32" cy="32" r={radius}
          fill="none" stroke="currentColor"
          strokeWidth="4" className="text-[#333333]"
        />
        <circle
          cx="32" cy="32" r={radius}
          fill="none" stroke="currentColor"
          strokeWidth="4" className={colorClass}
          strokeDasharray={`${fill} ${circumference}`}
          strokeLinecap="round"
          transform="rotate(-90 32 32)"
        />
      </svg>
      <span className="text-xl font-bold">{score}</span>
    </div>
  )
}

export default function AnalysisResult() {
  const params = useParams()
  const router = useRouter()
  const { lang } = useLanguage()
  const [analysis, setAnalysis] = useState<AnalysisData | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    console.log('[ANALYSIS PAGE] Mounted with ID:', params.id)

    if (!params.id) {
      console.error('[ANALYSIS PAGE] No ID provided')
      setLoading(false)
      return
    }

    const fetchAnalysis = async () => {
      console.log('[ANALYSIS PAGE] Fetching analysis data...')
      const { data, error } = await supabase
        .from('analyses')
        .select('*')
        .eq('id', params.id)
        .single()

      if (error) {
        console.error('[ANALYSIS PAGE] Fetch error:', error)
        setLoading(false)
        return
      }

      if (data) {
        console.log('[ANALYSIS PAGE] Data fetched:', data)
        setAnalysis(data)
      }
      setLoading(false)
    }

    fetchAnalysis()

    // Poll for updates if not completed/failed
    const interval = setInterval(async () => {
      const { data } = await supabase
        .from('analyses')
        .select('status, metrics, feedback_text')
        .eq('id', params.id)
        .single()

      if (data && (data.status === 'completed' || data.status === 'failed')) {
        clearInterval(interval)
        setAnalysis(prev => prev ? { ...prev, ...data } : data as AnalysisData)
      } else if (data) {
        setAnalysis(prev => prev ? { ...prev, ...data } : data as AnalysisData)
      }
    }, 3000)

    return () => clearInterval(interval)
  }, [params.id])

  const getRatingColor = (rating: string) => {
    switch (rating) {
      case 'excellent': return 'text-green-400 bg-green-900/20 border-green-900/30'
      case 'good': return 'text-[#FF8C66] bg-[#FF8C66]/10 border-[#FF8C66]/20'
      case 'needs_improvement': return 'text-yellow-400 bg-yellow-900/20 border-yellow-900/30'
      case 'poor': return 'text-red-400 bg-red-900/20 border-red-900/30'
      default: return 'text-[#8C8C8C] bg-[#333333]/20 border-[#333333]/30'
    }
  }

  const getRatingIcon = (rating: string) => {
    switch (rating) {
      case 'excellent': return '🌟'
      case 'good': return '✅'
      case 'needs_improvement': return '💪'
      case 'poor': return '⚠️'
      default: return '❓'
    }
  }

  const getScoreColor = (rating: string) => {
    switch (rating) {
      case 'excellent': return 'text-green-400'
      case 'good': return 'text-[#FF8C66]'
      case 'needs_improvement': return 'text-yellow-400'
      case 'poor': return 'text-red-400'
      default: return 'text-[#8C8C8C]'
    }
  }

  const getStatusText = () => {
    switch (analysis?.status) {
      case 'uploading': return t[lang].statusUploading
      case 'processing': return t[lang].statusProcessing
      case 'completed': return t[lang].statusComplete
      case 'failed': return t[lang].statusFailed
    }
  }

  if (loading) {
    return (
      <div className="min-h-screen bg-black flex items-center justify-center">
        <Loader2 className="w-8 h-8 text-[#FF8C66] animate-spin" />
      </div>
    )
  }

  if (!analysis) {
    return (
      <div className="min-h-screen bg-black flex items-center justify-center">
        <p className="text-[#8C8C8C]">{t[lang].analysisNotFound}</p>
      </div>
    )
  }

  const getStatusIcon = () => {
    switch (analysis.status) {
      case 'completed':
        return <CheckCircle2 className="w-16 h-16 text-green-500" />
      case 'failed':
        return <XCircle className="w-16 h-16 text-red-500" />
      default:
        return <Loader2 className="w-16 h-16 text-[#FF8C66] animate-spin" />
    }
  }

  const aiAnalysis = analysis.metrics?.ai_analysis

  return (
    <div className="min-h-screen bg-black p-4">
      <div className="max-w-4xl mx-auto">
        <div className="flex items-center justify-between mt-4">
          <button
            onClick={() => router.push('/')}
            className="text-[#8C8C8C] hover:text-[#E0E0E0] flex items-center gap-2"
          >
            <ArrowLeft className="w-4 h-4" />
            {t[lang].back}
          </button>
          <LanguageToggle />
        </div>

        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className="mt-8 bg-[#333333]/50 rounded-2xl p-8 border border-[#333333]"
        >
          {/* Status Header */}
          <div className="flex flex-col items-center text-center mb-8">
            {getStatusIcon()}
            <h1 className="mt-4 text-3xl font-bold text-[#E0E0E0]">{getStatusText()}</h1>
          </div>

          {/* Video Preview */}
          <div className="aspect-video bg-black rounded-xl overflow-hidden mb-8">
            <video
              src={analysis.video_url}
              controls
              className="w-full h-full object-contain"
            />
          </div>

          {/* AI Analysis Results */}
          {analysis.status === 'completed' && aiAnalysis && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ delay: 0.2 }}
              className="space-y-6"
            >
              {/* Rating Badge + Score */}
              <div className={`rounded-xl p-6 border ${getRatingColor(aiAnalysis.rating)}`}>
                <div className="flex items-center justify-between mb-3">
                  <div className="flex items-center gap-3">
                    <span className="text-3xl">{getRatingIcon(aiAnalysis.rating)}</span>
                    <div>
                      <p className="text-sm text-[#8C8C8C]">{t[lang].techniqueRating}</p>
                      <p className="text-2xl font-bold capitalize">
                        {aiAnalysis.rating?.replace('_', ' ') || 'Unknown'}
                      </p>
                    </div>
                  </div>
                  {aiAnalysis.score !== undefined && (
                    <div className="flex flex-col items-center">
                      <p className="text-sm text-[#8C8C8C] mb-1">{t[lang].score}</p>
                      <ScoreCircle
                        score={aiAnalysis.score}
                        colorClass={getScoreColor(aiAnalysis.rating)}
                      />
                    </div>
                  )}
                </div>
                <p className="text-[#E0E0E0]">{getAnalysisContent(aiAnalysis, lang).diagnosis}</p>
              </div>

              {/* Observations */}
              {(() => {
                const content = getAnalysisContent(aiAnalysis, lang)
                return content.observations.length > 0 && (
                  <div className="bg-purple-900/20 rounded-xl p-6 border border-purple-900/30">
                    <div className="flex items-center gap-2 mb-4">
                      <Eye className="w-5 h-5 text-purple-400" />
                      <h3 className="text-lg font-semibold text-[#E0E0E0]">{t[lang].observations}</h3>
                    </div>
                    <ul className="space-y-2">
                      {content.observations.map((obs, idx) => (
                        <li key={idx} className="flex items-start gap-2 text-[#E0E0E0]">
                          <span className="text-purple-400 mt-1">•</span>
                          {obs}
                        </li>
                      ))}
                    </ul>
                  </div>
                )
              })()}

              {/* Recommendations */}
              {(() => {
                const content = getAnalysisContent(aiAnalysis, lang)
                return content.recommendations.length > 0 && (
                  <div className="bg-green-900/20 rounded-xl p-6 border border-green-900/30">
                    <div className="flex items-center gap-2 mb-4">
                      <Dumbbell className="w-5 h-5 text-green-400" />
                      <h3 className="text-lg font-semibold text-[#E0E0E0]">{t[lang].trainingRecs}</h3>
                    </div>
                    <ul className="space-y-3">
                      {content.recommendations.map((rec, idx) => (
                        <li key={idx} className="flex items-start gap-3 text-[#E0E0E0] bg-green-900/10 rounded-lg p-3">
                          <Lightbulb className="w-5 h-5 text-green-400 mt-0.5 flex-shrink-0" />
                          {rec}
                        </li>
                      ))}
                    </ul>
                  </div>
                )
              })()}
            </motion.div>
          )}

          {/* Frame Metrics */}
          {analysis.status === 'completed' && analysis.metrics && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ delay: 0.4 }}
              className="grid grid-cols-1 md:grid-cols-3 gap-4 mt-6"
            >
              <div className="bg-[#FF8C66]/10 rounded-xl p-4 border border-[#FF8C66]/20">
                <div className="flex items-center gap-2 mb-2">
                  <Activity className="w-5 h-5 text-[#FF8C66]" />
                  <span className="text-[#8C8C8C] text-sm">{t[lang].totalFrames}</span>
                </div>
                <p className="text-2xl font-bold text-[#E0E0E0]">{analysis.metrics.total_frames}</p>
              </div>

              <div className="bg-purple-900/20 rounded-xl p-4 border border-purple-900/30">
                <div className="flex items-center gap-2 mb-2">
                  <Target className="w-5 h-5 text-purple-400" />
                  <span className="text-[#8C8C8C] text-sm">{t[lang].analyzed}</span>
                </div>
                <p className="text-2xl font-bold text-[#E0E0E0]">{analysis.metrics.analyzed_frames}</p>
              </div>

              <div className="bg-green-900/20 rounded-xl p-4 border border-green-900/30">
                <div className="flex items-center gap-2 mb-2">
                  <TrendingUp className="w-5 h-5 text-green-400" />
                  <span className="text-[#8C8C8C] text-sm">{t[lang].dataPoints}</span>
                </div>
                <p className="text-2xl font-bold text-[#E0E0E0]">{analysis.metrics.pose_data?.length || 0}</p>
              </div>
            </motion.div>
          )}

          {/* Fallback for old feedback_text format */}
          {analysis.status === 'completed' && !aiAnalysis && analysis.feedback_text && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              className="mt-6 bg-[#333333]/30 rounded-xl p-4"
            >
              <p className="text-[#E0E0E0] whitespace-pre-line">{analysis.feedback_text}</p>
            </motion.div>
          )}

          {analysis.status === 'failed' && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              className="mt-8 bg-red-900/20 rounded-xl p-4 border border-red-900/30 flex items-start gap-3"
            >
              <AlertTriangle className="w-5 h-5 text-red-400 mt-0.5" />
              <div>
                <p className="font-medium text-red-400">{t[lang].statusFailed}</p>
                <p className="text-sm text-[#8C8C8C] mt-1">{analysis.feedback_text}</p>
              </div>
            </motion.div>
          )}
        </motion.div>
      </div>
    </div>
  )
}
