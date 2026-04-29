import type { SafetyScore } from '../types'
import { scoreColor } from '../utils/score'

interface Props {
  safety: SafetyScore
}

export default function ScoreStrip({ safety }: Props) {
  const color = scoreColor(safety.score)

  const cells = [
    { label: 'Safety Score', value: `${safety.score}`, color },
    { label: 'High Risk', value: `${safety.high_count}`, color: '#ff4444' },
    { label: 'Medium Risk', value: `${safety.medium_count}`, color: '#e8a020' },
    { label: 'Standard', value: `${safety.standard_count}`, color: '#f0f0f0' },
    { label: 'Favorable', value: `${safety.favorable_count}`, color: '#3ecf8e' },
  ]

  return (
    <div className="score-strip">
      {cells.map((cell, i) => (
        <div key={i} className="score-cell">
          <div className="score-value" style={{ color: cell.color }}>{cell.value}</div>
          <div className="score-label">{cell.label}</div>
        </div>
      ))}
    </div>
  )
}
