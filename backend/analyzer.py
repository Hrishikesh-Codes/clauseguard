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

from models import Clause, SafetyScore, DocumentSummary, SummaryField, DetectedItem
import scoring

# Groq model IDs. NOTE: llama-3.3-70b-versatile and llama-3.1-8b-instant were
# decommissioned by Groq; these are the current replacements.
MODEL_ANALYSIS = "openai/gpt-oss-120b"
MODEL_SUMMARY = "openai/gpt-oss-20b"

# Fixed decoding params so prose stays as stable as the API allows.
SEED = 7
TEMPERATURE = 0

# ── Token budgeting ─────────────────────────────────────────────────────────────
# Groq enforces a tokens-per-minute ceiling and rejects an oversized request with
# HTTP 413. Rather than a fixed clause cap that can exceed it on a dense lease, we
# estimate cost per clause and send as many as safely fit. Sparse documents get
# more coverage; dense ones automatically get less instead of failing.
TPM_LIMIT = 8000
BUDGET_SAFETY = 0.85          # headroom for reasoning-token variance
SYSTEM_PROMPT_TOKENS = 430    # measured
EST_OUTPUT_PER_CLAUSE = 160   # measured with reasoning_effort=low (143 actual + margin)
EST_INPUT_OVERHEAD = 30       # per-clause header and flags line
CHARS_PER_TOKEN = 4

MAX_CLAUSES = 30              # hard ceiling even when budget allows more
MIN_CLAUSES = 6               # always explain at least this many
MAX_CLAUSE_CHARS = 420


SYSTEM_PROMPT = """You are a legal document analyzer specializing in leases and contracts. You explain clauses clearly to people who have never read a legal document before. You are not a lawyer and do not give legal advice, you explain what things mean in plain English.

Each clause you receive has ALREADY been assigned a risk level and a list of flagged provisions by a legal rule engine. Do not dispute or change them. Write prose that is consistent with the risk level you are given.

For each clause return a JSON object with these exact fields:
- index: the clause number you were given (integer)
- clause_type: short category name (e.g. "Automatic renewal", "Security deposit", "Entry rights", "Non-compete", "Confidentiality", "Liability", "Compensation")
- title: a short plain-English title capturing the specific risk or content (e.g. "60-day auto-renewal trap", "Entry without any notice")
- excerpt: the most important 1-2 sentences from the original clause text, quoted exactly
- plain_english: 3-4 sentences stating the actual rules this clause imposes, with specific amounts, timeframes and conditions, and what you can or cannot do. Summarize what the clause actually says. Never say "review carefully".
- verdict: 2 sentences explaining why this matters to the reader and one concrete action to take. If flagged provisions were given, reference them specifically. Never say "review carefully", say exactly what to negotiate, ask about, or watch out for.

Return a JSON object with a single key "clauses" containing an array of these objects, one per clause, in the order given. Return only valid JSON."""


# Keyword tiers used ONLY to decide which clauses are worth sending to the LLM.
# This is selection priority, not risk scoring (see scoring.py for risk).
PRIORITY_KEYWORDS: List[Tuple[int, List[str]]] = [
    (10, ["terminat", "early terminat", "break lease", "lease break"]),
    (10, ["automat", "renew", "holdover", "month-to-month"]),
    (9,  ["entry", "access", "landlord enter", "right to enter", "inspection"]),
    (9,  ["secur", "deposit", "deduct", "withhold"]),
    (9,  ["non-compet", "noncompet", "non-solicit", "confidential"]),
    (8,  ["late fee", "late charge", "grace period", "penalty"]),
    (8,  ["subleas", "sublet", "assign", "transfer"]),
    (8,  ["salary", "wage", "compensation", "overtime", "bonus"]),
    (7,  ["liabil", "indemnif", "hold harmless", "waiver"]),
    (7,  ["arbitrat", "mediat", "dispute", "governing law", "jurisdiction"]),
    (7,  ["invention", "intellectual property", "work product"]),
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


def _est_input_tokens(text: str) -> int:
    return len(text[:MAX_CLAUSE_CHARS]) // CHARS_PER_TOKEN + EST_INPUT_OVERHEAD


def plan_selection(clauses: List[str]) -> Tuple[List[str], int]:
    """
    Choose as many clauses as fit the per-request token budget, most important
    first, then restore document order so the output reads naturally.

    Returns (selected clauses, completion-token budget for the call).
    """
    usable = int(TPM_LIMIT * BUDGET_SAFETY) - SYSTEM_PROMPT_TOKENS

    ranked = sorted(
        range(len(clauses)),
        key=lambda i: (-selection_priority(clauses[i]), i),  # stable tie-break
    )

    picked: List[int] = []
    spent = 0
    for i in ranked:
        if len(picked) >= MAX_CLAUSES:
            break
        cost = _est_input_tokens(clauses[i]) + EST_OUTPUT_PER_CLAUSE
        if spent + cost > usable and len(picked) >= MIN_CLAUSES:
            break
        picked.append(i)
        spent += cost

    picked.sort()
    selected = [clauses[i] for i in picked]

    input_tokens = sum(_est_input_tokens(c) for c in selected)
    completion_budget = max(1024, usable - input_tokens)
    return selected, completion_budget


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
    raw = re.sub(r"^```(?:json)?\s*", "", (raw or "").strip())
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
    completion_budget: int,
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
        max_tokens=completion_budget,
        # Critical: gpt-oss reasoning tokens are billed against completion_tokens,
        # and at default effort they consumed the entire budget, silently
        # truncating the clause array (18 of 22 returned). Capping reasoning cut
        # output from 227 to 143 tokens per clause and returned all of them.
        extra_body={"reasoning_effort": "low"},
        response_format={"type": "json_object"},
    )
    return _parse_json(response.choices[0].message.content)


def _fallback_prose(
    clause: str, level: str, flags: List[str], credits: Optional[List[str]] = None
) -> Dict[str, str]:
    """Used when the LLM is unavailable so results stay useful instead of failing."""
    credits = credits or []
    snippet = clause[:220].strip()

    if flags:
        issues = "; ".join(flags)
        return {
            "title": flags[0],
            "plain_english": f"This clause was flagged for: {issues}. The text reads: {snippet}",
            "verdict": (
                f"This is rated {level} risk because of: {issues}. "
                "Ask the other party to strike or soften these terms before you sign."
            ),
        }
    if credits:
        wins = "; ".join(credits)
        return {
            "title": credits[0],
            "plain_english": f"This clause works in your favor: {wins}. The text reads: {snippet}",
            "verdict": (
                f"This is favorable because it gives you: {wins}. "
                "Keep this term in the agreement and make sure it is not edited out."
            ),
        }
    return {
        "title": "Standard provision",
        "plain_english": clause[:260].strip(),
        "verdict": "This is a standard provision. No specific red-flag provisions were detected.",
    }


def build_clauses(
    selected: List[str],
    classifications: List[Tuple[str, int, List[str]]],
    llm_data: Optional[Dict[str, Any]],
    meta: Optional[List[Tuple[str, List[str]]]] = None,
) -> List[Clause]:
    """
    Build Clause objects. Risk level and score always come from the rule engine;
    only prose comes from the LLM (with a deterministic fallback).
    """
    items_by_index: Dict[int, Dict[str, Any]] = {}
    if llm_data:
        for pos, item in enumerate(llm_data.get("clauses") or []):
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
        category, credit_labels = meta[i] if meta and i < len(meta) else ("General", [])
        fb = _fallback_prose(clause_text, level, flags, credit_labels)

        def pick(key: str, default: str) -> str:
            val = item.get(key)
            return str(val).strip() if isinstance(val, str) and val.strip() else default

        result.append(
            Clause(
                # Stable id derived from position, so repeated runs match up.
                id=f"clause-{i + 1}",
                clause_type=pick("clause_type", category),
                title=pick("title", fb["title"]),
                risk_level=level,       # rule engine is authoritative
                risk_score=risk_score,  # rule engine is authoritative
                excerpt=pick("excerpt", clause_text[:240].strip()),
                plain_english=pick("plain_english", fb["plain_english"]),
                verdict=pick("verdict", fb["verdict"]),
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


# ── Document summary ────────────────────────────────────────────────────────────
# Key facts differ completely by document type: a lease has rent and a landlord,
# an NDA has a disclosing party and a confidentiality term. Each spec is an
# ordered list of (json_key, display_label, extraction_hint).

_LEASE_SPEC = [
    ("landlord",         "Landlord",         "full name or company of the landlord/lessor"),
    ("tenant",           "Tenant",           "full name(s) of the tenant(s)/lessee(s)"),
    ("property_address", "Property",         "full property address or description"),
    ("lease_start",      "Lease start",      "start date, e.g. August 1, 2025"),
    ("lease_end",        "Lease end",        "end date, e.g. July 31, 2026"),
    ("lease_term",       "Term",             "duration, e.g. 12 months"),
    ("monthly_rent",     "Monthly rent",     "rent per month, e.g. $2,450/month"),
    ("payment_due_date", "Payment due",      "when rent is due, e.g. 1st of each month"),
    ("security_deposit", "Security deposit", "deposit amount"),
    ("late_fee",         "Late fee",         "late fee amount and when it applies"),
    ("move_in_notes",    "Move-in",          "key move-in conditions or fees, 1-2 sentences"),
    ("move_out_notes",   "Move-out",         "notice required and key move-out conditions, 1-2 sentences"),
]

_NDA_SPEC = [
    ("disclosing_party",          "Discloser",      "party sharing the confidential information"),
    ("receiving_party",           "Recipient",       "party receiving the confidential information"),
    ("mutual_or_oneway",          "Direction",             "whether obligations are mutual or one-way"),
    ("effective_date",            "Effective date",        "date the agreement starts"),
    ("purpose",                   "Purpose",               "why information is being shared, 1 sentence"),
    ("confidentiality_duration",  "Confidentiality", "how long confidentiality obligations last"),
    ("non_solicit",               "Non-solicitation",      "any non-solicit or no-hire restriction and its length"),
    ("exclusions",                "Exclusions",            "what is NOT confidential, e.g. public information"),
    ("return_obligation",         "Return of info",   "what must be returned or destroyed and by when"),
    ("remedies",                  "Remedies",              "penalties, liquidated damages or injunctive relief"),
    ("governing_law",             "Governing law",         "governing law or jurisdiction"),
]

_EMPLOYMENT_SPEC = [
    ("employer",        "Employer",        "employer name"),
    ("employee",        "Employee",        "employee name"),
    ("job_title",       "Position",        "job title or role"),
    ("start_date",      "Start date",      "employment start date"),
    ("employment_type", "Type",            "at-will, fixed term, full-time or part-time"),
    ("compensation",    "Compensation",    "salary or hourly rate"),
    ("bonus",           "Bonus",           "bonus, commission or equity terms"),
    ("benefits",        "Benefits",        "benefits and paid time off"),
    ("hours",           "Hours",           "expected hours and overtime or exempt status"),
    ("non_compete",     "Non-compete",     "non-compete scope, duration and geography"),
    ("ip_terms",        "IP assignment",   "who owns inventions and work product"),
    ("notice_period",   "Notice period",   "notice either side must give"),
    ("termination",     "Termination",     "how employment can end and any severance"),
]

_SERVICE_SPEC = [
    ("provider",       "Provider",       "party providing the services"),
    ("client",         "Client",         "party receiving the services"),
    ("effective_date", "Effective date", "date the agreement starts"),
    ("services",       "Services",       "what is being delivered, 1-2 sentences"),
    ("fees",           "Fees",           "price or rate"),
    ("payment_terms",  "Payment terms",  "invoicing schedule and due dates"),
    ("term",           "Term",           "how long the agreement runs"),
    ("termination",    "Termination",    "how either side can end it and any notice"),
    ("ip_ownership",   "IP ownership",   "who owns the work product"),
    ("liability_cap",  "Liability cap",  "any limit on liability"),
    ("governing_law",  "Governing law",  "governing law or jurisdiction"),
]

_PURCHASE_SPEC = [
    ("buyer",             "Buyer",             "buyer name"),
    ("seller",            "Seller",            "seller name"),
    ("item",              "Property / item",   "what is being sold"),
    ("purchase_price",    "Purchase price",    "total price"),
    ("deposit",           "Deposit",           "earnest money or deposit amount"),
    ("payment_terms",     "Payment terms",     "how and when payment is made"),
    ("closing_date",      "Closing date",      "closing or delivery date"),
    ("contingencies",     "Contingencies",     "financing, inspection or other conditions"),
    ("inspection_period", "Inspection", "how long the buyer has to inspect"),
    ("as_is",             "Condition",         "whether sold as-is or with warranties"),
    ("governing_law",     "Governing law",     "governing law or jurisdiction"),
]

_GENERIC_SPEC = [
    ("parties",         "Parties",         "who the agreement is between"),
    ("effective_date",  "Effective date",  "date the agreement starts"),
    ("purpose",         "Purpose",         "what the agreement covers, 1-2 sentences"),
    ("term",            "Term",            "how long it lasts"),
    ("payment_terms",   "Payment terms",   "any money owed and when"),
    ("key_obligations", "Key obligations", "the main duties imposed on you, 1-2 sentences"),
    ("termination",     "Termination",     "how it can be ended"),
    ("governing_law",   "Governing law",   "governing law or jurisdiction"),
]

SUMMARY_SPECS: Dict[str, List[Tuple[str, str, str]]] = {
    "Residential Lease":   _LEASE_SPEC,
    "Commercial Lease":    _LEASE_SPEC,
    "NDA":                 _NDA_SPEC,
    "Employment Contract": _EMPLOYMENT_SPEC,
    "Service Agreement":   _SERVICE_SPEC,
    "Purchase Agreement":  _PURCHASE_SPEC,
}


def _spec_for(doc_type: str) -> List[Tuple[str, str, str]]:
    return SUMMARY_SPECS.get(doc_type, _GENERIC_SPEC)


def _summary_prompt(spec: List[Tuple[str, str, str]], doc_type: str) -> str:
    body = ",\n".join(f'  "{key}": "{hint}"' for key, _label, hint in spec)
    return (
        f"You are a document parser. Extract key facts from this {doc_type} and return "
        "them as a JSON object. If a field cannot be found in the text, use null. Never "
        "guess. Return only valid JSON, no markdown, no preamble.\n\n"
        "Return exactly this structure:\n{\n" + body + "\n}"
    )


def _clean_field(value: Any) -> Optional[str]:
    """Normalize one summary field. Numbers are coerced, not dropped."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, (list, tuple)):
        parts = [p for p in (_clean_field(v) for v in value) if p]
        return "; ".join(parts) or None
    if not isinstance(value, str):
        return None
    text = " ".join(value.split())
    return text if text and text.lower() not in ("null", "none", "n/a", "na", "unknown", "not specified", "not found") else None


def extract_summary(full_text: str, doc_type: str) -> DocumentSummary:
    """Extract key facts, shaped for the detected document type."""
    spec = _spec_for(doc_type)
    try:
        client = Groq()
        response = client.chat.completions.create(
            model=MODEL_SUMMARY,
            messages=[
                {"role": "system", "content": _summary_prompt(spec, doc_type)},
                {"role": "user", "content": f"Extract the key facts from this document:\n\n{full_text[:4500]}"},
            ],
            temperature=TEMPERATURE,
            top_p=1,
            seed=SEED,
            # gpt-oss reasoning tokens count against max_tokens; 1024 ran out
            # before valid JSON could be emitted.
            max_tokens=4096,
            # groq 0.13.0 has no reasoning_effort kwarg; pass it through raw.
            # Cuts completion tokens ~3.5x with identical output.
            extra_body={"reasoning_effort": "low"},
            response_format={"type": "json_object"},
        )
        data = _parse_json(response.choices[0].message.content)
        fields = [
            SummaryField(label=label, value=cleaned)
            for key, label, _hint in spec
            if (cleaned := _clean_field(data.get(key)))
        ]
        return DocumentSummary(doc_type=doc_type, fields=fields)
    except Exception as e:
        print(f"SUMMARY ERROR ({MODEL_SUMMARY}, {doc_type}): {e}")
        return DocumentSummary(doc_type=doc_type, fields=[])


def analyze_document(
    clauses: List[str], doc_type: str, full_text: str
) -> Tuple[List[Clause], SafetyScore, DocumentSummary, int]:
    """Main entry point. Returns (clauses, safety, summary, clauses_analyzed)."""
    selected, completion_budget = plan_selection(clauses)

    # Deterministic classification drives everything downstream.
    classifications: List[Tuple[str, int, List[str]]] = []
    meta: List[Tuple[str, List[str]]] = []
    for text in selected:
        level, risk_score = scoring.classify_clause(text)
        risks, credits = scoring.match_rules(text)
        ranked = sorted(risks, key=lambda r: -r.weight)
        ranked_credits = sorted(credits, key=lambda r: -r.weight)
        classifications.append((level, risk_score, [r.label for r in ranked]))
        # Category makes a better clause_type than the rule label, which would
        # otherwise duplicate the title when the LLM omits a clause.
        source = ranked or ranked_credits
        meta.append((
            source[0].category if source and source[0].category else "General",
            [c.label for c in ranked_credits],
        ))

    # Prose is best-effort: a model outage must not lose the analysis.
    llm_data = None
    try:
        llm_data = call_groq(selected, classifications, doc_type, full_text, completion_budget)
    except Exception as e:
        print(f"GROQ ERROR ({MODEL_ANALYSIS}): {e}")

    analyzed = build_clauses(selected, classifications, llm_data, meta)
    # Show the riskiest clauses first; stable tie-break keeps ordering reproducible.
    analyzed.sort(key=lambda c: (RISK_RANK.get(c.risk_level, 9), -c.risk_score))

    return (
        analyzed,
        compute_safety(analyzed, full_text),
        extract_summary(full_text, doc_type),
        len(selected),
    )
