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

export interface LeaseSummary {
  landlord: string | null
  tenant: string | null
  property_address: string | null
  lease_start: string | null
  lease_end: string | null
  lease_term: string | null
  monthly_rent: string | null
  payment_due_date: string | null
  security_deposit: string | null
  late_fee: string | null
  move_in_notes: string | null
  move_out_notes: string | null
}

export interface AnalysisResult {
  meta: DocumentMeta
  safety: SafetyScore
  clauses: Clause[]
  summary: LeaseSummary | null
  analyzedAt: string // ISO timestamp
}

export type FilterTab = 'all' | 'high' | 'medium' | 'standard' | 'favorable'
export type RiskLevel = 'high' | 'medium' | 'standard' | 'favorable'
