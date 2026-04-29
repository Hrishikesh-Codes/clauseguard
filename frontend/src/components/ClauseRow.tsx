import { useState } from 'react'
import type { Clause, RiskLevel } from '../types'
import RiskBar from './RiskBar'
import VerdictBlock from './VerdictBlock'

const RISK_LABEL_COLORS: Record<RiskLevel, string> = {
  high: '#ff4444',
  medium: '#e8a020',
  standard: '#555',
  favorable: '#3ecf8e',
}

const RISK_LABEL_TEXT: Record<RiskLevel, string> = {
  high: 'High risk',
  medium: 'Medium risk',
  standard: 'Standard',
  favorable: 'Favorable',
}

interface Props {
  clause: Clause
}

export default function ClauseRow({ clause }: Props) {
  const [selected, setSelected] = useState(false)
  const labelColor = RISK_LABEL_COLORS[clause.risk_level as RiskLevel]
  const labelText = RISK_LABEL_TEXT[clause.risk_level as RiskLevel]

  return (
    <div
      className={`clause-row${selected ? ' clause-row--selected' : ''}`}
      onClick={() => setSelected(s => !s)}
    >
      {/* Left column */}
      <div className="clause-left">
        <div className="clause-meta" style={{ color: labelColor }}>
          — {labelText} · {clause.clause_type}
        </div>
        <div className="clause-title">{clause.title}</div>
        <div className="clause-excerpt">"{clause.excerpt}"</div>
        <RiskBar score={clause.risk_score} riskLevel={clause.risk_level as RiskLevel} />
      </div>

      {/* Right column */}
      <div className="clause-right">
        <p className="clause-explanation">{clause.plain_english}</p>
        <VerdictBlock verdict={clause.verdict} riskLevel={clause.risk_level as RiskLevel} />
      </div>
    </div>
  )
}
