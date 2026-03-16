import { NextResponse } from 'next/server'

export async function POST(request: Request) {
  try {
    console.log('[API] Received analyze request')

    const body = await request.json()
    console.log('[API] Request body:', { hasVideoUrl: !!body.video_url, hasAnalysisId: !!body.analysis_id })

    const { video_url, analysis_id } = body

    if (!video_url || !analysis_id) {
      console.error('[API] Missing required fields')
      return NextResponse.json({ error: 'Missing required fields' }, { status: 400 })
    }

    const modalUrl = process.env.MODAL_WEBHOOK_URL
    console.log('[API] Modal webhook URL:', modalUrl ? 'SET' : 'NOT SET')

    if (!modalUrl) {
      console.error('[API] MODAL_WEBHOOK_URL not configured')
      return NextResponse.json({ error: 'Server configuration error: MODAL_WEBHOOK_URL missing' }, { status: 500 })
    }

    // Call Modal
    console.log('[API] Calling Modal webhook...')
    const response = await fetch(modalUrl, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        video_url,
        analysis_id,
        supabase_url: process.env.NEXT_PUBLIC_SUPABASE_URL,
        supabase_key: process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY,
        anthropic_api_key: process.env.ANTHROPIC_API_KEY || ''
      })
    })

    console.log('[API] Modal response status:', response.status)

    if (!response.ok) {
      const error = await response.text()
      console.error('[API] Modal error:', error)
      throw new Error(`Modal error: ${error}`)
    }

    const data = await response.json()
    console.log('[API] Modal response data:', data)

    return NextResponse.json(data)

  } catch (error: any) {
    console.error('[API] Fatal error:', error)
    return NextResponse.json({ error: error.message }, { status: 500 })
  }
}
