import type { SafetyScore } from '../types'

export function scoreColor(score: number): string {
  if (score < 50) return '#ff4444'
  if (score < 75) return '#e8a020'
  return '#3ecf8e'
}

export function scoreLabel(score: number): string {
  if (score < 50) return 'High risk'
  if (score < 75) return 'Moderate'
  return 'Safe'
}

export function computeSafety(clauses: { risk_level: string }[]): SafetyScore {
  const high = clauses.filter(c => c.risk_level === 'high').length
  const medium = clauses.filter(c => c.risk_level === 'medium').length
  const standard = clauses.filter(c => c.risk_level === 'standard').length
  const favorable = clauses.filter(c => c.risk_level === 'favorable').length

  let score = 100
  score -= high * 20
  score -= medium * 8
  score += favorable * 5
  score = Math.max(0, Math.min(100, score))

  return { score, high_count: high, medium_count: medium, standard_count: standard, favorable_count: favorable }
}
