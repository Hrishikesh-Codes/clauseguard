export interface Clause {
  id: string
  clause_type: string
  title: string
  risk_level: 'high' | 'medium' | 'standard' | 'favorable'
  risk_score: number // 1-5
  excerpt: string
  plain_english: string
  verdict: string
  action_label: string
  action_prompt: string
}

export interface DocumentMeta {
  filename: string
  page_count: number
  word_count: number
  doc_type: string
  analysis_time_ms: number
}

export interface SafetyScore {
  score: number
  high_count: number
  medium_count: number
  standard_count: number
  favorable_count: number
}

export interface AnalysisResult {
  meta: DocumentMeta
  safety: SafetyScore
  clauses: Clause[]
  analyzedAt: string // ISO timestamp
}

export type FilterTab = 'all' | 'high' | 'medium' | 'standard' | 'favorable'
export type RiskLevel = 'high' | 'medium' | 'standard' | 'favorable'
