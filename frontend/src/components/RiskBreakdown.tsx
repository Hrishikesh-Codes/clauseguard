import type { SafetyScore, DetectedItem } from '../types'

interface Props {
  safety: SafetyScore
}

const SEVERITY_COLOR: Record<string, string> = {
  critical: '#ff4444',
  high: '#ff6b6b',
  medium: '#e8a020',
  low: '#aaa',
  favorable: '#3ecf8e',
}

const SEVERITY_LABEL: Record<string, string> = {
  critical: 'Critical',
  high: 'High',
  medium: 'Medium',
  low: 'Minor',
  favorable: 'In your favor',
}

function Row({ item }: { item: DetectedItem }) {
  const color = SEVERITY_COLOR[item.severity] ?? '#888'
  return (
    <div className="breakdown-row">
      <span className="breakdown-sev" style={{ color, borderColor: color }}>
        {SEVERITY_LABEL[item.severity] ?? item.severity}
      </span>
      <span className="breakdown-label">{item.label}</span>
      {item.category && <span className="breakdown-cat">{item.category}</span>}
    </div>
  )
}

export default function RiskBreakdown({ safety }: Props) {
  const risks = safety.risks ?? []
  const benefits = safety.benefits ?? []
  if (risks.length === 0 && benefits.length === 0) return null

  return (
    <div className="breakdown">
      <div className="breakdown-header">
        Why this score
        <span className="breakdown-note">
          {risks.length} risk{risks.length === 1 ? '' : 's'} detected
          {benefits.length > 0 && ` · ${benefits.length} in your favor`}
        </span>
      </div>

      {risks.length > 0 && (
        <div className="breakdown-group">
          <div className="breakdown-group-title">Risks found</div>
          {risks.map(r => <Row key={r.label} item={r} />)}
        </div>
      )}

      {benefits.length > 0 && (
        <div className="breakdown-group">
          <div className="breakdown-group-title">Terms in your favor</div>
          {benefits.map(b => <Row key={b.label} item={b} />)}
        </div>
      )}
    </div>
  )
}
