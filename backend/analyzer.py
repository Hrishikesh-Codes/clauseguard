"""
Clause analysis.

Division of responsibility:
  - scoring.py (deterministic)  decides risk levels and the document score.
  - the LLM (non-deterministic) writes prose only: titles and explanations.

The LLM is TOLD each clause's risk level and which provisions were flagged, so its
wording always agrees with the score. If the LLM is unavailable the analysis still
returns full deterministic results with rule-derived explanations.
"""

import json
import re
from typing import List, Dict, Any, Tuple, Optional

from groq import Groq

from models import Clause, SafetyScore, LeaseSummary, DetectedItem
import scoring

# Groq model IDs. NOTE: llama-3.3-70b-versatile and llama-3.1-8b-instant were
# decommissioned by Groq; these are the current replacements.
MODEL_ANALYSIS = "openai/gpt-oss-120b"
MODEL_SUMMARY = "openai/gpt-oss-20b"

# Fixed decoding params so prose stays as stable as the API allows.
SEED = 7
TEMPERATURE = 0

MAX_CLAUSES = 16
MAX_CLAUSE_CHARS = 500


SYSTEM_PROMPT = """You are a legal document analyzer specializing in residential leases and contracts. You explain clauses clearly to people who have never read a legal document before. You are not a lawyer and do not give legal advice, you explain what things mean in plain English.

Each clause you receive has ALREADY been assigned a risk level and a list of flagged provisions by a legal rule engine. Do not dispute or change them. Write prose that is consistent with the risk level you are given.

For each clause return a JSON object with these exact fields:
- index: the clause number you were given (integer)
- clause_type: short category name (e.g. "Automatic renewal", "Security deposit", "Entry rights", "Pet policy", "Early termination", "Subletting", "Liability", "Utilities", "Maintenance")
- title: a short plain-English title capturing the specific risk or content (e.g. "60-day auto-renewal trap", "Entry without any notice")
- excerpt: the most important 1-2 sentences from the original clause text, quoted exactly
- plain_english: 3-5 sentences stating the actual rules this clause imposes, with specific amounts, timeframes and conditions, and what you can or cannot do. Summarize what the clause actually says. Never say "review carefully".
- verdict: 2-3 sentences explaining why this matters to the reader and one concrete action to take. If flagged provisions were given, reference them specifically. Never say "review carefully", say exactly what to negotiate, ask about, or watch out for.
- action_label: short action text (e.g. "Draft negotiation email", "Check state law", "Move-in checklist")
- action_prompt: the full prompt to send to an AI when the user clicks the action link

Return a JSON object with a single key "clauses" containing an array of these objects, one per clause, in the order given. Return only valid JSON."""


# Keyword tiers used ONLY to decide which clauses are worth sending to the LLM.
# This is selection priority, not risk scoring (see scoring.py for risk).
PRIORITY_KEYWORDS: List[Tuple[int, List[str]]] = [
    (10, ["terminat", "early terminat", "break lease", "lease break"]),
    (10, ["automat", "renew", "holdover", "month-to-month"]),
    (9,  ["entry", "access", "landlord enter", "right to enter", "inspection"]),
    (9,  ["secur", "deposit", "deduct", "withhold"]),
    (8,  ["late fee", "late charge", "grace period", "penalty"]),
    (8,  ["subleas", "sublet", "assign", "transfer"]),
    (7,  ["liabil", "indemnif", "hold harmless", "waiver"]),
    (7,  ["arbitrat", "mediat", "dispute", "governing law", "jurisdiction"]),
    (6,  ["pet", "animal", "dog", "cat"]),
    (6,  ["utilities", "electric", "gas", "water", "trash"]),
    (6,  ["maintenan", "repair", "damage", "condition"]),
    (5,  ["noise", "nuisance", "quiet enjoyment", "disturbance"]),
    (5,  ["insurance", "renter", "renters"]),
    (5,  ["parking", "vehicle", "garage"]),
    (5,  ["guest", "occupant", "visitor"]),
    (4,  ["alteration", "modif", "improvement", "paint"]),
    (4,  ["notice", "written notice", "days notice"]),
]

RISK_RANK = {"high": 0, "medium": 1, "standard": 2, "favorable": 3}


def selection_priority(text: str) -> int:
    """How important a clause is to send to the LLM. Higher = more important."""
    lower = text.lower()
    score = 0
    for points, keywords in PRIORITY_KEYWORDS:
        if any(kw in lower for kw in keywords):
            score += points
    # Clauses the rule engine actually flagged are the most valuable to explain.
    risks, _ = scoring.match_rules(text)
    score += sum(r.weight for r in risks)
    return score


def select_top_clauses(clauses: List[str]) -> List[str]:
    """Deterministically pick the most important clauses, keeping document order."""
    if len(clauses) <= MAX_CLAUSES:
        return clauses
    # Tie-break on index so selection is stable, never arbitrary.
    ranked = sorted(
        enumerate(clauses),
        key=lambda pair: (-selection_priority(pair[1]), pair[0]),
    )
    top = sorted(i for i, _ in ranked[:MAX_CLAUSES])
    return [clauses[i] for i in top]


def build_user_prompt(
    clauses: List[str],
    classifications: List[Tuple[str, int, List[str]]],
    doc_type: str,
    jurisdiction: str,
) -> str:
    parts = [
        f"Document type: {doc_type}",
        f"State/jurisdiction: {jurisdiction}",
        "",
        "Clauses to explain. Each shows the risk level and flagged provisions "
        "already determined by the rule engine.",
        "",
    ]
    for i, (clause, (level, _score, flags)) in enumerate(zip(clauses, classifications), 1):
        parts.append(f"[CLAUSE {i}] risk_level={level}")
        if flags:
            parts.append("flagged: " + "; ".join(flags))
        parts.append(clause[:MAX_CLAUSE_CHARS])
        parts.append("")
    parts.append("Return the JSON as specified, one object per clause.")
    return "\n".join(parts)


def detect_jurisdiction(text: str) -> str:
    """Try to find state/jurisdiction from document text."""
    states = [
        "Alabama", "Alaska", "Arizona", "Arkansas", "California", "Colorado",
        "Connecticut", "Delaware", "Florida", "Georgia", "Hawaii", "Idaho",
        "Illinois", "Indiana", "Iowa", "Kansas", "Kentucky", "Louisiana",
        "Maine", "Maryland", "Massachusetts", "Michigan", "Minnesota",
        "Mississippi", "Missouri", "Montana", "Nebraska", "Nevada",
        "New Hampshire", "New Jersey", "New Mexico", "New York", "North Carolina",
        "North Dakota", "Ohio", "Oklahoma", "Oregon", "Pennsylvania",
        "Rhode Island", "South Carolina", "South Dakota", "Tennessee", "Texas",
        "Utah", "Vermont", "Virginia", "Washington", "West Virginia",
        "Wisconsin", "Wyoming", "District of Columbia"
    ]
    for state in states:
        if state in text:
            return state
    return "Unknown"


def _strip_fences(raw: str) -> str:
    raw = re.sub(r"^```(?:json)?\s*", "", raw.strip())
    return re.sub(r"\s*```$", "", raw)


def _parse_json(raw: str) -> Dict[str, Any]:
    raw = _strip_fences(raw)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            return json.loads(match.group(0))
        raise ValueError(f"Invalid JSON from LLM: {raw[:300]}")


def call_groq(
    clauses: List[str],
    classifications: List[Tuple[str, int, List[str]]],
    doc_type: str,
    full_text: str,
) -> Dict[str, Any]:
    """One batched, deterministic-as-possible call for clause prose."""
    client = Groq()
    user_prompt = build_user_prompt(
        clauses, classifications, doc_type, detect_jurisdiction(full_text)
    )
    response = client.chat.completions.create(
        model=MODEL_ANALYSIS,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        temperature=TEMPERATURE,
        top_p=1,
        seed=SEED,
        max_tokens=8000,
        response_format={"type": "json_object"},
    )
    return _parse_json(response.choices[0].message.content)


def _fallback_prose(clause: str, level: str, flags: List[str]) -> Dict[str, str]:
    """Used when the LLM is unavailable so results stay useful instead of failing."""
    if flags:
        issues = "; ".join(flags)
        plain = (
            f"This clause was flagged for: {issues}. "
            f"The text reads: {clause[:220].strip()}"
        )
        verdict = (
            f"This is rated {level} risk because of: {issues}. "
            "Ask the landlord to strike or soften these terms before you sign."
        )
        title = flags[0]
    else:
        plain = clause[:260].strip()
        verdict = f"This is rated {level} risk. No specific red-flag provisions were detected."
        title = "Standard provision"
    return {"title": title, "plain_english": plain, "verdict": verdict}


def build_clauses(
    selected: List[str],
    classifications: List[Tuple[str, int, List[str]]],
    llm_data: Optional[Dict[str, Any]],
) -> List[Clause]:
    """
    Build Clause objects. Risk level and score always come from the rule engine;
    only prose comes from the LLM (with a deterministic fallback).
    """
    items_by_index: Dict[int, Dict[str, Any]] = {}
    if llm_data:
        raw_items = llm_data.get("clauses") or []
        for pos, item in enumerate(raw_items):
            if not isinstance(item, dict):
                continue
            try:
                idx = int(item.get("index", pos + 1)) - 1
            except (TypeError, ValueError):
                idx = pos
            if 0 <= idx < len(selected):
                items_by_index.setdefault(idx, item)

    result: List[Clause] = []
    for i, (clause_text, (level, risk_score, flags)) in enumerate(
        zip(selected, classifications)
    ):
        item = items_by_index.get(i, {})
        fb = _fallback_prose(clause_text, level, flags)

        def pick(key: str, default: str) -> str:
            val = item.get(key)
            return str(val).strip() if isinstance(val, str) and val.strip() else default

        result.append(
            Clause(
                # Stable id derived from position, so repeated runs match up.
                id=f"clause-{i + 1}",
                clause_type=pick("clause_type", flags[0] if flags else "General"),
                title=pick("title", fb["title"]),
                risk_level=level,       # rule engine is authoritative
                risk_score=risk_score,  # rule engine is authoritative
                excerpt=pick("excerpt", clause_text[:240].strip()),
                plain_english=pick("plain_english", fb["plain_english"]),
                verdict=pick("verdict", fb["verdict"]),
                action_label=pick("action_label", "Check state law"),
                action_prompt=pick("action_prompt", ""),
            )
        )
    return result


def compute_safety(clauses: List[Clause], full_text: str) -> SafetyScore:
    """
    Document score from the deterministic engine over the FULL text, so risks in
    sections that were never sent to the LLM still count.
    """
    result = scoring.score_document(full_text)
    return SafetyScore(
        score=result.score,
        grade=result.grade,
        high_count=sum(1 for c in clauses if c.risk_level == "high"),
        medium_count=sum(1 for c in clauses if c.risk_level == "medium"),
        standard_count=sum(1 for c in clauses if c.risk_level == "standard"),
        favorable_count=sum(1 for c in clauses if c.risk_level == "favorable"),
        risks=[
            DetectedItem(label=r.label, category=r.category, severity=r.severity)
            for r in result.risks
        ],
        benefits=[
            DetectedItem(label=b.label, category=b.category, severity="favorable")
            for b in result.benefits
        ],
    )


SUMMARY_SYSTEM_PROMPT = """You are a document parser. Extract key facts from a lease or contract and return them as a JSON object. If a field cannot be found in the text, use null. Return only valid JSON, no markdown, no preamble.

Return exactly this structure:
{
  "landlord": "full name or company of the landlord/lessor",
  "tenant": "full name(s) of the tenant(s)/lessee(s)",
  "property_address": "full property address or description",
  "lease_start": "lease start date (e.g. April 9, 2025)",
  "lease_end": "lease end date (e.g. April 8, 2026)",
  "lease_term": "duration (e.g. 12 months, 1 year)",
  "monthly_rent": "rent amount per month (e.g. $1,200/month)",
  "payment_due_date": "when rent is due (e.g. 1st of each month)",
  "security_deposit": "security deposit amount",
  "late_fee": "late fee amount and when it applies",
  "move_in_notes": "key move-in conditions, fees, or checklist requirements (1-2 sentences)",
  "move_out_notes": "notice required and key move-out conditions (1-2 sentences)"
}"""

SUMMARY_FIELDS = [
    "landlord", "tenant", "property_address", "lease_start", "lease_end",
    "lease_term", "monthly_rent", "payment_due_date", "security_deposit",
    "late_fee", "move_in_notes", "move_out_notes",
]


def _clean_field(value: Any) -> Optional[str]:
    """Normalize one summary field. Numbers are coerced, not dropped."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return str(value)
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text if text and text.lower() not in ("null", "none", "n/a", "unknown", "") else None


def extract_summary(full_text: str) -> LeaseSummary:
    """Extract key lease facts. Returns an empty summary if the model is unavailable."""
    try:
        client = Groq()
        response = client.chat.completions.create(
            model=MODEL_SUMMARY,
            messages=[
                {"role": "system", "content": SUMMARY_SYSTEM_PROMPT},
                {"role": "user", "content": f"Extract the key facts from this document:\n\n{full_text[:4000]}"},
            ],
            temperature=TEMPERATURE,
            top_p=1,
            seed=SEED,
            # gpt-oss reasoning tokens count against max_tokens; 1024 ran out
            # before valid JSON could be emitted. Extraction needs no deep
            # reasoning, so cap it and leave room for the document.
            max_tokens=4096,
            # groq 0.13.0 has no reasoning_effort kwarg; pass it through raw.
            # Cuts completion tokens ~3.5x (1031 -> 294) with identical output.
            extra_body={"reasoning_effort": "low"},
            response_format={"type": "json_object"},
        )
        data = _parse_json(response.choices[0].message.content)
        return LeaseSummary(**{f: _clean_field(data.get(f)) for f in SUMMARY_FIELDS})
    except Exception as e:
        print(f"SUMMARY ERROR ({MODEL_SUMMARY}): {e}")
        return LeaseSummary()


def analyze_document(
    clauses: List[str], doc_type: str, full_text: str
) -> Tuple[List[Clause], SafetyScore, LeaseSummary]:
    """Main entry point. Returns (clauses, safety_score, summary)."""
    selected = select_top_clauses(clauses)

    # Deterministic classification drives everything downstream.
    classifications: List[Tuple[str, int, List[str]]] = []
    for text in selected:
        level, risk_score = scoring.classify_clause(text)
        risks, _ = scoring.match_rules(text)
        flags = [r.label for r in sorted(risks, key=lambda r: -r.weight)]
        classifications.append((level, risk_score, flags))

    # Prose is best-effort: a model outage must not lose the analysis.
    llm_data = None
    try:
        llm_data = call_groq(selected, classifications, doc_type, full_text)
    except Exception as e:
        print(f"GROQ ERROR ({MODEL_ANALYSIS}): {e}")

    analyzed = build_clauses(selected, classifications, llm_data)
    # Show the riskiest clauses first; stable tie-break keeps ordering reproducible.
    analyzed.sort(key=lambda c: (RISK_RANK.get(c.risk_level, 9), -c.risk_score))

    return analyzed, compute_safety(analyzed, full_text), extract_summary(full_text)
