import { createContext, useContext, useState, useCallback, useEffect, type ReactNode } from 'react'
import type { AnalysisResult } from '../types'

// Bump when the stored shape changes, so old entries are discarded rather than
// rendered against a newer component.
const STORAGE_KEY = 'clauseguard.history.v1'
const MAX_HISTORY = 10

interface AnalysisContextValue {
  current: AnalysisResult | null
  history: AnalysisResult[]
  setCurrent: (result: AnalysisResult) => void
  loadFromHistory: (result: AnalysisResult) => void
  clearCurrent: () => void
  clearHistory: () => void
}

const AnalysisContext = createContext<AnalysisContextValue | null>(null)

// History lives only in this browser. Reading or writing it can throw in a
// private window or when site data is blocked, so every access is guarded and
// the app renders correctly when storage is unavailable.
function readStored(): AnalysisResult[] {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw)
    return Array.isArray(parsed) ? parsed.slice(0, MAX_HISTORY) : []
  } catch {
    return []
  }
}

function writeStored(entries: AnalysisResult[]): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(entries.slice(0, MAX_HISTORY)))
  } catch {
    // Storage full or blocked. History simply does not persist this session.
  }
}

export function AnalysisProvider({ children }: { children: ReactNode }) {
  const [current, setCurrent_] = useState<AnalysisResult | null>(null)
  const [history, setHistory] = useState<AnalysisResult[]>(readStored)

  useEffect(() => { writeStored(history) }, [history])

  const setCurrent = useCallback((result: AnalysisResult) => {
    setCurrent_(result)
    setHistory(prev => {
      const without = prev.filter(r => r.meta.filename !== result.meta.filename)
      return [result, ...without].slice(0, MAX_HISTORY)
    })
  }, [])

  const loadFromHistory = useCallback((result: AnalysisResult) => setCurrent_(result), [])
  const clearCurrent = useCallback(() => setCurrent_(null), [])
  const clearHistory = useCallback(() => {
    setHistory([])
    try { window.localStorage.removeItem(STORAGE_KEY) } catch { /* nothing to clear */ }
  }, [])

  return (
    <AnalysisContext.Provider
      value={{ current, history, setCurrent, loadFromHistory, clearCurrent, clearHistory }}
    >
      {children}
    </AnalysisContext.Provider>
  )
}

export function useAnalysis(): AnalysisContextValue {
  const ctx = useContext(AnalysisContext)
  if (!ctx) throw new Error('useAnalysis must be used inside AnalysisProvider')
  return ctx
}
