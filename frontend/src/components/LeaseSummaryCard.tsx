import type { LeaseSummary } from '../types'

interface Props {
  summary: LeaseSummary
}

const ROWS: { label: string; key: keyof LeaseSummary }[] = [
  { label: 'Landlord', key: 'landlord' },
  { label: 'Tenant', key: 'tenant' },
  { label: 'Property', key: 'property_address' },
  { label: 'Lease start', key: 'lease_start' },
  { label: 'Lease end', key: 'lease_end' },
  { label: 'Term', key: 'lease_term' },
  { label: 'Monthly rent', key: 'monthly_rent' },
  { label: 'Payment due', key: 'payment_due_date' },
  { label: 'Security deposit', key: 'security_deposit' },
  { label: 'Late fee', key: 'late_fee' },
  { label: 'Move-in', key: 'move_in_notes' },
  { label: 'Move-out', key: 'move_out_notes' },
]

export default function LeaseSummaryCard({ summary }: Props) {
  const hasAnyValue = ROWS.some(r => summary[r.key])
  if (!hasAnyValue) return null

  return (
    <div className="summary-card">
      <div className="summary-header">Lease summary</div>
      <div className="summary-grid">
        {ROWS.map(({ label, key }) => {
          const value = summary[key]
          if (!value) return null
          return (
            <div key={key} className="summary-row">
              <div className="summary-label">{label}</div>
              <div className="summary-value">{value}</div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
