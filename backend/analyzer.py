import json
import uuid
import re
from typing import List, Dict, Any

from groq import Groq

from models import Clause, SafetyScore


SYSTEM_PROMPT = """You are a legal document analyzer specializing in residential leases and contracts. Your job is to analyze clauses and explain them clearly to people who have never read a legal document before. You are not a lawyer and do not give legal advice — you explain what things mean in plain English.

For each clause you receive, return a JSON object with these exact fields:
- clause_type: short category name (e.g. "Automatic renewal", "Security deposit", "Entry rights", "Pet policy", "Early termination", "Subletting", "Liability", "Utilities", "Maintenance", "Noise policy")
- title: a short plain-English title that captures the risk or content (e.g. "60-day auto-renewal trap", "Entry without any notice")
- risk_level: exactly one of "high", "medium", "standard", "favorable"
- risk_score: integer 1-5 (how many risk bar segments to fill)
- excerpt: the most important 1-2 sentences from the original clause text, quoted exactly
- plain_english: 3-5 sentences explaining what this clause means in practice using everyday scenarios. Write as if explaining to a first-time renter who has never signed a lease.
- verdict: 3-5 sentences starting with "This is [good/bad/standard/favorable] because..." explaining: (a) why it is good or bad, (b) how it compares to what is standard or legally typical, (c) exactly what the reader should do
- action_label: short action text for the action link (e.g. "Draft negotiation email", "Check state law", "Draft roommate agreement", "Move-in checklist")
- action_prompt: the full prompt to send to an AI when the user clicks the action link

Return a JSON object with a single key "clauses" containing an array of these objects. Return only valid JSON, no markdown, no preamble."""


def build_user_prompt(clauses: List[str], doc_type: str, jurisdiction: str = "Unknown") -> str:
    parts = [
        f"Document type: {doc_type}",
        f"State/jurisdiction: {jurisdiction}",
        "",
        "Here are the clauses extracted from the document:",
        "",
    ]

    for i, clause in enumerate(clauses, 1):
        parts.append(f"[CLAUSE {i}]")
        parts.append(clause)
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
        model="llama-3.1-70b-versatile",
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
    score -= high * 20
    score -= medium * 8
    score += favorable * 5
    score = max(0, min(100, score))

    return SafetyScore(
        score=score,
        high_count=high,
        medium_count=medium,
        standard_count=standard,
        favorable_count=favorable,
    )


def analyze_document(clauses: List[str], doc_type: str, full_text: str) -> tuple[List[Clause], SafetyScore]:
    """Main entry point: analyze all clauses, return (clauses, safety_score)."""
    raw = call_groq(clauses, doc_type, full_text)
    parsed = parse_clauses(raw)
    safety = compute_safety(parsed)
    return parsed, safety
