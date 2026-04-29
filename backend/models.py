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


class AnalysisResponse(BaseModel):
    meta: DocumentMeta
    safety: SafetyScore
    clauses: List[Clause]


class ErrorResponse(BaseModel):
    error: str
    code: str
