import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAnalysis } from '../context/AnalysisContext'
import Nav from '../components/Nav'
import ScoreStrip from '../components/ScoreStrip'
import SummaryCard from '../components/SummaryCard'
import RiskBreakdown from '../components/RiskBreakdown'
import FilterTabs from '../components/FilterTabs'
import ClauseRow from '../components/ClauseRow'
import BottomBar from '../components/BottomBar'
import type { FilterTab, Clause } from '../types'
import { formatFilename, formatWordCount, formatAnalysisTime } from '../utils/format'

export default function Results() {
  const { current } = useAnalysis()
  const navigate = useNavigate()
  const [activeTab, setActiveTab] = useState<FilterTab>('all')

  if (!current) {
    return (
      <div className="no-results">
        <Nav />
        <div className="no-results-content">
          <p className="no-results-text">No analysis yet.</p>
          <button className="btn-try-again" onClick={() => navigate('/')}>Upload a document</button>
        </div>
      </div>
    )
  }

  const { meta, safety, clauses } = current

  const filtered: Clause[] = activeTab === 'all'
    ? clauses
    : clauses.filter(c => c.risk_level === activeTab)

  const counts: Record<FilterTab, number> = {
    all: clauses.length,
    high: clauses.filter(c => c.risk_level === 'high').length,
    medium: clauses.filter(c => c.risk_level === 'medium').length,
    standard: clauses.filter(c => c.risk_level === 'standard').length,
    favorable: clauses.filter(c => c.risk_level === 'favorable').length,
  }

  return (
    <div className="results-page">
      <Nav />

      <div className="results-hero">
        <h1 className="results-filename">{formatFilename(meta.filename)}</h1>
        <p className="results-meta">
          {meta.page_count} pages
          <span className="meta-dot">·</span>
          {formatWordCount(meta.word_count)}
          <span className="meta-dot">·</span>
          {meta.doc_type}
          <span className="meta-dot">·</span>
          Analyzed in {formatAnalysisTime(meta.analysis_time_ms)}
          {!!meta.clauses_found && (
            <>
              <span className="meta-dot">·</span>
              {meta.clauses_analyzed === meta.clauses_found
                ? `All ${meta.clauses_found} clauses explained`
                : `${meta.clauses_analyzed} of ${meta.clauses_found} clauses explained`}
            </>
          )}
        </p>
      </div>

      <ScoreStrip safety={safety} />
      {safety.confidence && safety.confidence !== 'high' && safety.confidence_note && (
        <div className={`score-notice score-notice--${safety.confidence}`}>
          <span className="score-notice-tag">
            {safety.confidence === 'low' ? 'Cannot score reliably' : 'Partial read'}
          </span>
          <span className="score-notice-text">{safety.confidence_note}</span>
        </div>
      )}
      <RiskBreakdown safety={safety} />
      {current.summary && <SummaryCard summary={current.summary} />}
      <FilterTabs active={activeTab} onChange={setActiveTab} counts={counts} />

      <div className="clause-list">
        {filtered.length === 0 ? (
          <div className="no-clauses">No clauses in this category.</div>
        ) : (
          filtered.map(clause => <ClauseRow key={clause.id} clause={clause} />)
        )}
      </div>

      <BottomBar result={current} />
    </div>
  )
}
