import type { AnalysisResult } from '../types'
import { buildClaudeUrl } from '../utils/format'

interface Props {
  result: AnalysisResult
}

export default function BottomBar({ result }: Props) {
  const docName = result.meta.filename

  const actions = [
    {
      label: 'Draft appeal letter',
      prompt: `I have a lease for "${docName}" with several concerning clauses. Please help me draft a professional appeal letter to my landlord requesting modifications to the high-risk clauses in my lease. Here is a summary of the issues:\n\n${result.clauses.filter(c => c.risk_level === 'high').map(c => `- ${c.title}: ${c.plain_english}`).join('\n')}\n\nPlease write a polite but firm letter requesting fair modifications.`,
    },
    {
      label: 'Questions to ask',
      prompt: `I'm about to sign a lease for "${docName}". Based on the following concerning clauses, what specific questions should I ask my landlord before signing?\n\n${result.clauses.filter(c => ['high', 'medium'].includes(c.risk_level)).map(c => `- ${c.title}: ${c.plain_english}`).join('\n')}\n\nProvide a numbered list of clear, direct questions I should ask.`,
    },
    {
      label: 'Compare to standard',
      prompt: `I have a lease for "${docName}". Please compare the following clauses to standard residential lease terms in the US. For each one, tell me if it is more or less tenant-friendly than typical leases, and what the standard practice is:\n\n${result.clauses.map(c => `- ${c.title} (${c.risk_level}): ${c.excerpt}`).join('\n')}\n\nProvide a clear comparison for each clause.`,
    },
    {
      label: 'Explain simply',
      prompt: `Please explain my lease "${docName}" in the simplest possible language, as if I am signing a lease for the very first time and have never dealt with legal documents before. Focus on what I actually need to know and do:\n\n${result.clauses.map(c => `- ${c.title}: ${c.excerpt}`).join('\n')}\n\nUse plain everyday language, no legal jargon.`,
    },
  ]

  return (
    <div className="bottom-bar">
      {actions.map((action, i) => (
        <a
          key={i}
          className={`bottom-bar-btn${i === 0 ? ' bottom-bar-btn--primary' : ''}`}
          href={buildClaudeUrl(action.prompt)}
          target="_blank"
          rel="noopener noreferrer"
          style={{ borderRight: i < actions.length - 1 ? '0.5px solid #222' : 'none' }}
        >
          {action.label}
        </a>
      ))}
    </div>
  )
}
