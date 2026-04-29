from pydantic import BaseModel
from typing import List, Optional


class Clause(BaseModel):
    id: str
    clause_type: str
    title: str
    risk_level: str  # "high" | "medium" | "standard" | "favorable"
    risk_score: int  # 1-5
    excerpt: str
    plain_english: str
    verdict: str
    action_label: str
    action_prompt: str


class DocumentMeta(BaseModel):
    filename: str
    page_count: int
    word_count: int
    doc_type: str
    analysis_time_ms: int


class SafetyScore(BaseModel):
    score: int
    high_count: int
    medium_count: int
    standard_count: int
    favorable_count: int


class LeaseSummary(BaseModel):
    landlord: Optional[str] = None
    tenant: Optional[str] = None
    property_address: Optional[str] = None
    lease_start: Optional[str] = None
    lease_end: Optional[str] = None
    lease_term: Optional[str] = None
    monthly_rent: Optional[str] = None
    payment_due_date: Optional[str] = None
    security_deposit: Optional[str] = None
    late_fee: Optional[str] = None
    move_in_notes: Optional[str] = None
    move_out_notes: Optional[str] = None


class AnalysisResponse(BaseModel):
    meta: DocumentMeta
    safety: SafetyScore
    clauses: List[Clause]
    summary: Optional[LeaseSummary] = None


class ErrorResponse(BaseModel):
    error: str
    code: str
