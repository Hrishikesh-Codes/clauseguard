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


class DocumentMeta(BaseModel):
    filename: str
    page_count: int
    word_count: int
    doc_type: str
    analysis_time_ms: int
    clauses_found: int = 0     # total clauses the parser extracted
    clauses_analyzed: int = 0  # how many fit in the token budget


class DetectedItem(BaseModel):
    """A provision the deterministic rule engine matched."""
    label: str
    category: str = ""
    severity: str = ""  # critical | high | medium | low | favorable


class SafetyScore(BaseModel):
    score: int
    high_count: int
    medium_count: int
    standard_count: int
    favorable_count: int
    # Added by the deterministic scoring engine. Optional for backward compatibility.
    grade: str = ""
    # How much the text supported a score: high | medium | low. When not high the
    # reader is told, rather than being shown a confident-looking number.
    confidence: str = "high"
    confidence_note: str = ""
    # State law context. Informational only, never folded into the score.
    jurisdiction: str = "Unknown"
    jurisdiction_notes: List[str] = []
    risks: List[DetectedItem] = []
    benefits: List[DetectedItem] = []


class SummaryField(BaseModel):
    label: str
    value: str


class DocumentSummary(BaseModel):
    """
    Key facts, shaped per document type. Leases get landlord/rent/dates, NDAs get
    disclosing party/confidentiality term, employment contracts get salary/
    non-compete, and so on. Rendered generically as label/value rows.
    """
    doc_type: str = ""
    fields: List[SummaryField] = []


class AnalysisResponse(BaseModel):
    meta: DocumentMeta
    safety: SafetyScore
    clauses: List[Clause]
    summary: Optional[DocumentSummary] = None


class ErrorResponse(BaseModel):
    error: str
    code: str
