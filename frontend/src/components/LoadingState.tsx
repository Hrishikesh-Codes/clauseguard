import { useState, useEffect } from 'react'

const MESSAGES = [
  'Extracting clauses...',
  'Identifying risk patterns...',
  'Translating legal language...',
  'Scoring each clause...',
  'Building your report...',
]

interface Props {
  progress: number // 0-100
}

export default function LoadingState({ progress }: Props) {
  const [msgIndex, setMsgIndex] = useState(0)

  useEffect(() => {
    const interval = setInterval(() => {
      setMsgIndex(i => (i + 1) % MESSAGES.length)
    }, 1500)
    return () => clearInterval(interval)
  }, [])

  return (
    <div className="loading-screen">
      <div className="loading-progress-bar">
        <div className="loading-progress-fill" style={{ width: `${progress}%` }} />
      </div>
      <div className="loading-content">
        <h1 className="loading-heading">Analyzing your document.</h1>
        <p className="loading-message">{MESSAGES[msgIndex]}</p>
      </div>
    </div>
  )
}
