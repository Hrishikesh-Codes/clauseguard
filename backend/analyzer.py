import json
import uuid
import re
from typing import List, Dict, Any

from groq import Groq

from models import Clause, SafetyScore, LeaseSummary


SYSTEM_PROMPT = """You are a legal document analyzer specializing in residential leases and contracts. Your job is to analyze clauses and explain them clearly to people who have never read a legal document before. You are not a lawyer and do not give legal advice — you explain what things mean in plain English.

For each clause you receive, return a JSON object with these exact fields:
- clause_type: short category name (e.g. "Automatic renewal", "Security deposit", "Entry rights", "Pet policy", "Early termination", "Subletting", "Liability", "Utilities", "Maintenance", "Noise policy")
- title: a short plain-English title that captures the risk or content (e.g. "60-day auto-renewal trap", "Entry without any notice")
- risk_level: exactly one of "high", "medium", "standard", "favorable"
- risk_score: integer 1-5 (how many risk bar segments to fill)
- excerpt: the most important 1-2 sentences from the original clause text, quoted exactly
- plain_english: 3-5 sentences that state the actual rules this clause imposes — specific amounts, timeframes, conditions, and what you can or cannot do. Do not say "review carefully" — instead summarize what the clause actually says. Example: "You must give 60 days written notice before moving out. If you don't, you'll be charged rent for the full 60 days even after you leave. The landlord can enter your unit with only 12 hours notice for inspections."
- verdict: 2-3 sentences starting with "This is [good/bad/standard/favorable] because..." that explain why this matters to the reader and give one concrete action they should take. Never say "review carefully" — instead say what specifically to negotiate, ask about, or watch out for.
- action_label: short action text (e.g. "Draft negotiation email", "Check state law", "Draft roommate agreement", "Move-in checklist")
- action_prompt: the full prompt to send to an AI when the user clicks the action link

Return a JSON object with a single key "clauses" containing an array of these objects. Return only valid JSON, no markdown, no preamble."""


MAX_CLAUSES = 12
MAX_CLAUSE_CHARS = 500


def build_user_prompt(clauses: List[str], doc_type: str, jurisdiction: str = "Unknown") -> str:
    # Cap clause count and truncate long clauses to stay within TPM limits
    clauses = clauses[:MAX_CLAUSES]
    parts = [
        f"Document type: {doc_type}",
        f"State/jurisdiction: {jurisdiction}",
        "",
        "Here are the clauses extracted from the document:",
        "",
    ]

    for i, clause in enumerate(clauses, 1):
        parts.append(f"[CLAUSE {i}]")
        parts.append(clause[:MAX_CLAUSE_CHARS])
        parts.append("")

    parts.append("Analyze each clause and return the JSON as specified.")
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


def call_groq(clauses: List[str], doc_type: str, full_text: str) -> Dict[str, Any]:
    """Send all clauses to Groq in one batched call. Returns parsed JSON dict."""
    client = Groq()

    jurisdiction = detect_jurisdiction(full_text)
    user_prompt = build_user_prompt(clauses, doc_type, jurisdiction)

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.2,
        max_tokens=8192,
    )

    raw = response.choices[0].message.content.strip()

    # Strip markdown code fences if present
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        # Try to extract JSON substring
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        if match:
            data = json.loads(match.group(0))
        else:
            raise ValueError(f"Invalid JSON from LLM: {str(e)}\nRaw: {raw[:500]}")

    return data


def parse_clauses(data: Dict[str, Any]) -> List[Clause]:
    """Convert raw LLM JSON into Clause models."""
    raw_clauses = data.get("clauses", [])
    result: List[Clause] = []

    valid_risk_levels = {"high", "medium", "standard", "favorable"}

    for item in raw_clauses:
        try:
            risk_level = item.get("risk_level", "standard").lower()
            if risk_level not in valid_risk_levels:
                risk_level = "standard"

            risk_score = int(item.get("risk_score", 3))
            risk_score = max(1, min(5, risk_score))

            clause = Clause(
                id=str(uuid.uuid4()),
                clause_type=str(item.get("clause_type", "General")),
                title=str(item.get("title", "Untitled clause")),
                risk_level=risk_level,
                risk_score=risk_score,
                excerpt=str(item.get("excerpt", "")),
                plain_english=str(item.get("plain_english", "")),
                verdict=str(item.get("verdict", "")),
                action_label=str(item.get("action_label", "Learn more")),
                action_prompt=str(item.get("action_prompt", "")),
            )
            result.append(clause)
        except Exception:
            continue

    return result


def compute_safety(clauses: List[Clause]) -> SafetyScore:
    high = sum(1 for c in clauses if c.risk_level == "high")
    medium = sum(1 for c in clauses if c.risk_level == "medium")
    standard = sum(1 for c in clauses if c.risk_level == "standard")
    favorable = sum(1 for c in clauses if c.risk_level == "favorable")

    score = 100
    score -= high * 15
    score -= medium * 5
    score += favorable * 5
    score = max(0, min(100, score))

    return SafetyScore(
        score=score,
        high_count=high,
        medium_count=medium,
        standard_count=standard,
        favorable_count=favorable,
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


def extract_summary(full_text: str) -> LeaseSummary:
    """Extract key lease facts using a fast small model. Returns LeaseSummary."""
    client = Groq()
    # Use first 4000 chars — enough to capture the main terms
    snippet = full_text[:4000]

    try:
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {"role": "system", "content": SUMMARY_SYSTEM_PROMPT},
                {"role": "user", "content": f"Extract the key facts from this document:\n\n{snippet}"},
            ],
            temperature=0.1,
            max_tokens=1024,
        )
        raw = response.choices[0].message.content.strip()
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
        data = json.loads(raw)
        return LeaseSummary(
            landlord=data.get("landlord"),
            tenant=data.get("tenant"),
            property_address=data.get("property_address"),
            lease_start=data.get("lease_start"),
            lease_end=data.get("lease_end"),
            lease_term=data.get("lease_term"),
            monthly_rent=data.get("monthly_rent"),
            payment_due_date=data.get("payment_due_date"),
            security_deposit=data.get("security_deposit"),
            late_fee=data.get("late_fee"),
            move_in_notes=data.get("move_in_notes"),
            move_out_notes=data.get("move_out_notes"),
        )
    except Exception:
        return LeaseSummary()


def analyze_document(clauses: List[str], doc_type: str, full_text: str) -> tuple[List[Clause], SafetyScore, LeaseSummary]:
    """Main entry point: analyze all clauses, return (clauses, safety_score, summary)."""
    raw = call_groq(clauses, doc_type, full_text)
    parsed = parse_clauses(raw)
    safety = compute_safety(parsed)
    summary = extract_summary(full_text)
    return parsed, safety, summary
