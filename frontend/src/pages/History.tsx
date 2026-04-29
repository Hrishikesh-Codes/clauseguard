import { useNavigate } from 'react-router-dom'
import Nav from '../components/Nav'
import { useAnalysis } from '../context/AnalysisContext'
import { formatFilename, formatDate } from '../utils/format'
import { scoreColor } from '../utils/score'

export default function History() {
  const { history, loadFromHistory } = useAnalysis()
  const navigate = useNavigate()

  const handleLoad = (result: Parameters<typeof loadFromHistory>[0]) => {
    loadFromHistory(result)
    navigate('/results')
  }

  return (
    <div className="history-page">
      <Nav />
      <div className="history-content">
        <h1 className="history-heading">History</h1>
        <p className="history-subheading">Documents analyzed this session.</p>

        {history.length === 0 ? (
          <div className="history-empty">
            <p className="history-empty-text">No documents analyzed yet.</p>
            <button className="btn-try-again" onClick={() => navigate('/')}>Analyze a document</button>
          </div>
        ) : (
          <div className="history-list">
            {history.map((result, i) => (
              <div
                key={i}
                className="history-row"
                onClick={() => handleLoad(result)}
              >
                <div className="history-row-left">
                  <div className="history-filename">{formatFilename(result.meta.filename)}</div>
                  <div className="history-row-meta">
                    {result.meta.doc_type}
                    <span className="meta-dot">·</span>
                    {result.clauses.length} clauses
                    <span className="meta-dot">·</span>
                    {formatDate(result.analyzedAt)}
                  </div>
                </div>
                <div className="history-row-right">
                  <div
                    className="history-score"
                    style={{ color: scoreColor(result.safety.score) }}
                  >
                    {result.safety.score}
                  </div>
                  <div className="history-score-label">score</div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
