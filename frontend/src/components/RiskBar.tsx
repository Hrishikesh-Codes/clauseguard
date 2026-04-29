import type { RiskLevel } from '../types'

const RISK_COLORS: Record<RiskLevel, string> = {
  high: '#ff4444',
  medium: '#e8a020',
  standard: '#555',
  favorable: '#3ecf8e',
}

interface Props {
  score: number // 1-5
  riskLevel: RiskLevel
}

export default function RiskBar({ score, riskLevel }: Props) {
  const color = RISK_COLORS[riskLevel]
  return (
    <div className="risk-bar">
      {Array.from({ length: 5 }, (_, i) => (
        <div
          key={i}
          className="risk-bar-segment"
          style={{ background: i < score ? color : '#1e1e1e' }}
        />
      ))}
    </div>
  )
}
