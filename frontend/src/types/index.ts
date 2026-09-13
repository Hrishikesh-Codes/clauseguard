export interface Clause {
  id: string
  clause_type: string
  title: string
  risk_level: 'high' | 'medium' | 'standard' | 'favorable'
  risk_score: number // 1-5
  excerpt: string
  plain_english: string
  verdict: string
}

export interface DocumentMeta {
  filename: string
  page_count: number
  word_count: number
  doc_type: string
  analysis_time_ms: number
  clauses_found?: number
  clauses_analyzed?: number
}

export interface DetectedItem {
  label: string
  category: string
  severity: string // critical | high | medium | low | favorable
}

export interface SafetyScore {
  score: number
  high_count: number
  medium_count: number
  standard_count: number
  favorable_count: number
  // From the deterministic scoring engine. Optional so older cached
  // history entries still render.
  grade?: string
  confidence?: 'high' | 'medium' | 'low'
  confidence_note?: string
  risks?: DetectedItem[]
  benefits?: DetectedItem[]
}

export interface SummaryField {
  label: string
  value: string
}

export interface DocumentSummary {
  doc_type: string
  fields: SummaryField[]
}

export interface AnalysisResult {
  meta: DocumentMeta
  safety: SafetyScore
  clauses: Clause[]
  summary: DocumentSummary | null
  analyzedAt: string // ISO timestamp
}

export type FilterTab = 'all' | 'high' | 'medium' | 'standard' | 'favorable'
export type RiskLevel = 'high' | 'medium' | 'standard' | 'favorable'
