import type { FilterTab } from '../types'

const TABS: { id: FilterTab; label: string }[] = [
  { id: 'all', label: 'All clauses' },
  { id: 'high', label: 'High risk' },
  { id: 'medium', label: 'Medium risk' },
  { id: 'standard', label: 'Standard' },
  { id: 'favorable', label: 'Favorable' },
]

interface Props {
  active: FilterTab
  onChange: (tab: FilterTab) => void
  counts: Record<FilterTab, number>
}

export default function FilterTabs({ active, onChange, counts }: Props) {
  return (
    <div className="filter-tabs">
      {TABS.map((tab, i) => (
        <button
          key={tab.id}
          className={`filter-tab${active === tab.id ? ' filter-tab--active' : ''}`}
          onClick={() => onChange(tab.id)}
          style={{ borderRight: i < TABS.length - 1 ? '0.5px solid #222' : 'none' }}
        >
          {tab.label}
          {counts[tab.id] > 0 && tab.id !== 'all' && (
            <span className="filter-tab-count">{counts[tab.id]}</span>
          )}
        </button>
      ))}
    </div>
  )
}
