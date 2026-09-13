import type { SafetyScore } from '../types'
import { scoreColor, scoreLabel } from '../utils/score'

interface Props {
  safety: SafetyScore
}

export default function ScoreStrip({ safety }: Props) {
  const color = scoreColor(safety.score)
  const grade = safety.grade || scoreLabel(safety.score)

  const cells: { label: string; value: string; color: string; sub?: string }[] = [
    { label: 'Safety Score', value: `${safety.score}`, color, sub: grade },
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
          {cell.sub && <div className="score-sub" style={{ color: cell.color }}>{cell.sub}</div>}
        </div>
      ))}
    </div>
  )
}
