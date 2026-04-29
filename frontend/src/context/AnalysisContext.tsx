import { createContext, useContext, useState, useCallback, type ReactNode } from 'react'
import type { AnalysisResult } from '../types'

interface AnalysisContextValue {
  current: AnalysisResult | null
  history: AnalysisResult[]
  setCurrent: (result: AnalysisResult) => void
  loadFromHistory: (result: AnalysisResult) => void
  clearCurrent: () => void
}

const AnalysisContext = createContext<AnalysisContextValue | null>(null)

export function AnalysisProvider({ children }: { children: ReactNode }) {
  const [current, setCurrent_] = useState<AnalysisResult | null>(null)
  const [history, setHistory] = useState<AnalysisResult[]>([])

  const setCurrent = useCallback((result: AnalysisResult) => {
    setCurrent_(result)
    setHistory(prev => {
      const without = prev.filter(r => r.meta.filename !== result.meta.filename)
      return [result, ...without].slice(0, 20)
    })
  }, [])

  const loadFromHistory = useCallback((result: AnalysisResult) => {
    setCurrent_(result)
  }, [])

  const clearCurrent = useCallback(() => {
    setCurrent_(null)
  }, [])

  return (
    <AnalysisContext.Provider value={{ current, history, setCurrent, loadFromHistory, clearCurrent }}>
      {children}
    </AnalysisContext.Provider>
  )
}

export function useAnalysis(): AnalysisContextValue {
  const ctx = useContext(AnalysisContext)
  if (!ctx) throw new Error('useAnalysis must be used inside AnalysisProvider')
  return ctx
}
