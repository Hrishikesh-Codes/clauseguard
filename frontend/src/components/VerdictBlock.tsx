import type { RiskLevel } from '../types'

const VERDICT_STYLES: Record<RiskLevel, { bg: string; border: string; color: string }> = {
  high: { bg: '#1a0a0a', border: '#ff6b6b', color: '#ff6b6b' },
  medium: { bg: '#1a1200', border: '#e8b84b', color: '#e8b84b' },
  standard: { bg: '#111', border: '#555', color: '#aaa' },
  favorable: { bg: '#071a10', border: '#3ecf8e', color: '#3ecf8e' },
}

interface Props {
  verdict: string
  riskLevel: RiskLevel
}

export default function VerdictBlock({ verdict, riskLevel }: Props) {
  const style = VERDICT_STYLES[riskLevel]
  return (
    <div
      className="verdict-block"
      style={{
        background: style.bg,
        borderLeft: `2px solid ${style.border}`,
        color: style.color,
      }}
    >
      {verdict}
    </div>
  )
}
