import type { SafetyScore } from '../types'

// Bands mirror GRADE_BANDS in backend/scoring.py. The backend is the single
// source of truth for the score itself; this only picks a display colour.
export function scoreColor(score: number): string {
  if (score >= 85) return '#3ecf8e' // Low risk
  if (score >= 70) return '#e8b84b' // Moderate risk
  if (score >= 55) return '#e8a020' // Elevated risk
  return '#ff4444'                  // High / Severe risk
}

// Fallback only. The backend sends `grade`; prefer that when present.
export function scoreLabel(score: number): string {
  if (score >= 85) return 'Low risk'
  if (score >= 70) return 'Moderate risk'
  if (score >= 55) return 'Elevated risk'
  if (score >= 45) return 'High risk'
  return 'Severe risk'
}

export type { SafetyScore }
