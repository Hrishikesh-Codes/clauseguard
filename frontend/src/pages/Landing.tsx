import { useState, useCallback, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import Nav from '../components/Nav'
import UploadZone from '../components/UploadZone'
import LoadingState from '../components/LoadingState'
import { useAnalysis } from '../context/AnalysisContext'
import type { AnalysisResult } from '../types'

const API_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

const EXAMPLE_PILLS = ['Automatic renewal', 'Entry rights', 'Liability', 'Security deposit', 'Early termination']

export default function Landing() {
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [progress, setProgress] = useState(0)
  const { setCurrent } = useAnalysis()
  const navigate = useNavigate()
  const progressRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const startTimeRef = useRef<number>(0)

  const startProgress = useCallback(() => {
    setProgress(0)
    progressRef.current = setInterval(() => {
      setProgress(p => {
        if (p >= 90) return p
        return p + (90 - p) * 0.04
      })
    }, 100)
  }, [])

  const stopProgress = useCallback(() => {
    if (progressRef.current) clearInterval(progressRef.current)
    setProgress(100)
  }, [])

  useEffect(() => () => { if (progressRef.current) clearInterval(progressRef.current) }, [])

  const handleFile = useCallback(async (file: File) => {
    setError(null)

    if (file.size > 10 * 1024 * 1024) {
      setError('This file is too large. Please upload a PDF under 10MB.')
      return
    }

    if (!file.name.toLowerCase().endsWith('.pdf') && file.type !== 'application/pdf') {
      setError('Please upload a PDF file.')
      return
    }

    setLoading(true)
    startTimeRef.current = Date.now()
    startProgress()

    const formData = new FormData()
    formData.append('file', file)

    try {
      const res = await fetch(`${API_URL}/api/analyze`, {
        method: 'POST',
        body: formData,
      })

      const data = await res.json()

      if (!res.ok) {
        const errMsg = data?.detail?.error ?? data?.detail ?? 'Analysis failed. Please try again in a moment.'
        throw new Error(errMsg)
      }

      stopProgress()

      // Ensure minimum 1.5s loading time
      const elapsed = Date.now() - startTimeRef.current
      const remaining = Math.max(0, 1500 - elapsed)

      await new Promise(r => setTimeout(r, remaining))

      const result: AnalysisResult = {
        ...data,
        analyzedAt: new Date().toISOString(),
      }
      setCurrent(result)
      setLoading(false)
      navigate('/results')
    } catch (err) {
      stopProgress()
      await new Promise(r => setTimeout(r, 300))
      setLoading(false)
      setError(err instanceof Error ? err.message : 'Analysis failed. Please try again in a moment.')
    }
  }, [startProgress, stopProgress, setCurrent, navigate])

  if (loading) {
    return <LoadingState progress={progress} />
  }

  return (
    <div className="landing">
      <Nav />
      <div className="landing-content">
        <h1 className="landing-heading">Read your lease.<br />Understand it.</h1>
        <p className="landing-subheading">
          Upload any lease or contract. We'll flag every risk in plain English.
        </p>
        <UploadZone onFile={handleFile} error={error} />
        <div className="landing-pills">
          {EXAMPLE_PILLS.map(pill => (
            <span key={pill} className="landing-pill">{pill}</span>
          ))}
        </div>
        <p className="landing-footer">No account needed. Your document is never stored.</p>
      </div>
    </div>
  )
}
