import type { DocumentSummary } from '../types'

interface Props {
  summary: DocumentSummary
}

export default function SummaryCard({ summary }: Props) {
  if (!summary.fields || summary.fields.length === 0) return null

  // Long prose values read better on their own full-width row.
  const isWide = (value: string) => value.length > 60

  return (
    <div className="summary-card">
      <div className="summary-header">
        {summary.doc_type ? `${summary.doc_type} summary` : 'Document summary'}
      </div>
      <div className="summary-grid">
        {summary.fields.map(f => (
          <div
            key={f.label}
            className={`summary-row${isWide(f.value) ? ' summary-row--wide' : ''}`}
          >
            <div className="summary-label">{f.label}</div>
            <div className="summary-value">{f.value}</div>
          </div>
        ))}
      </div>
    </div>
  )
}
