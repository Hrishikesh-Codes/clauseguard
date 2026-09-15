"""
Regression suite for the deterministic scoring engine.

Run:  python test_scoring.py
Exits non-zero if any check fails.

Guarantees locked in here:
  1. DETERMINISM  - the same text always produces the same score AND the same
                    findings, across many runs. This is the property that was
                    originally broken when the score came from the LLM.
  2. CALIBRATION  - each archetype lands in its expected band, and a fair
                    document always outranks a predatory one of the same type.
  3. SAFETY       - unreadable text is never reported as low risk.
  4. PRECISION    - protective and standard clauses do not trigger risk rules.
"""

import hashlib
import json
import re
import sys

import scoring
from scoring import score_document, classify_clause, match_rules, numeric_findings

failures: list = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  [{detail}]" if detail and not ok else ""))
    if not ok:
        failures.append(name)


# ── Fixtures ───────────────────────────────────────────────────────────────────

LEASE_FRIENDLY = """
RENT. Tenant shall pay $2,000 per month due on the first day of each month. A grace
period of five (5) days shall apply before any late charge is assessed.
SECURITY DEPOSIT. The security deposit equals one month's rent and shall be returned
within 21 days of move-out. The deposit shall bear interest at the statutory rate.
ENTRY. Landlord shall provide twenty-four (24) hours written notice before entering
the premises, except in case of emergency.
MAINTENANCE. Landlord shall maintain the premises and make all necessary repairs and
keep the dwelling in good repair at Landlord's expense.
SUBLETTING. Tenant may sublet the premises with Landlord's prior written consent.
MOVE-IN. The parties shall complete a move-in inspection checklist documenting condition.
TERMINATION. Either party may terminate with thirty (30) days written notice.
ATTORNEY FEES. The prevailing party shall be awarded reasonable attorney's fees.
PRORATION. Rent shall be prorated for any partial month.
TERM. The term begins August 1, 2025 and ends July 31, 2026.
"""

LEASE_TYPICAL = """
RENT. Rent of $2,400 is due on the 1st. A late fee of $75 applies if rent is unpaid.
SECURITY DEPOSIT. Deposit of one month's rent is required.
TERM AND RENEWAL. This Lease shall automatically renew for successive twelve month
terms unless Tenant provides sixty (60) days written notice of intent to vacate.
INSURANCE. Tenant shall maintain renter's insurance throughout the term.
UTILITIES. Tenant is responsible for all utilities serving the premises.
HOLDING OVER. Any holding over shall be at 150% of the then-current monthly rent.
SUBLETTING. Tenant may sublet only with Landlord's prior written consent.
ENTRY. Landlord may enter upon twenty-four (24) hours notice.
MAINTENANCE. Landlord shall keep the dwelling in good repair.
PETS. No pets are allowed without written authorization.
SMOKING. No smoking is permitted anywhere on the premises.
ALTERATIONS. Tenant shall not paint or alter the premises without consent.
RULES. Landlord reserves the right to amend the community rules and regulations.
PARKING. Parking is assigned and a monthly parking fee applies.
"""

LEASE_PREDATORY = """
ENTRY. Landlord may enter the premises at any time without notice for any purpose.
HABITABILITY. Tenant accepts the premises as-is and waives the implied warranty of
habitability and waives all claims for repairs.
DISPUTES. Tenant agrees to binding arbitration and waives any right to a jury trial
and waives participation in any class action.
LEGAL FEES. Tenant shall pay all of Landlord's attorney's fees and costs incurred in
any action arising from this Lease.
INDEMNITY. Tenant shall indemnify and hold Landlord harmless from any and all claims.
LIABILITY. All tenants are jointly and severally liable for all obligations.
RENEWAL. This Lease automatically renews unless ninety (90) days written notice is given.
SUBLETTING. Tenant shall not sublet or assign the premises under any circumstance.
FEES. The administrative fee and cleaning fee are non-refundable.
TERMINATION. Early termination requires payment of three (3) months rent as liquidated damages.
DEPOSIT. Tenant shall pay a security deposit equal to three months rent.
DEFAULT. Upon default the entire remaining balance of rent shall be immediately due.
REPAIRS. Tenant is responsible for all repairs and maintenance of the premises.
RULES. Landlord may modify any rules or policies at its sole discretion.
LATE FEE. A late charge is assessed immediately with no grace period.
RENT. Rent of $2,400 per month is due on the first.
"""

NDA_FAIR = """
MUTUAL NON-DISCLOSURE AGREEMENT
This Agreement is made between Acme Corp ("Discloser") and Jane Roe ("Recipient")
effective March 1, 2026.
1. Each party shall hold the other's Confidential Information in confidence and use it
only to evaluate a potential partnership.
2. Confidentiality obligations expire three (3) years after disclosure.
3. Obligations do not apply to information that is publicly available, in the public
domain, independently developed, or already known to the receiving party.
4. Nothing in this Agreement shall prohibit either party from reporting possible
violations of law to any government agency or commission.
5. Either party may terminate this agreement with thirty (30) days notice.
6. Liability for any breach shall not exceed the fees paid under the partnership.
"""

NDA_PREDATORY = """
MUTUAL NON-DISCLOSURE AGREEMENT
Between Acme Holdings, Inc. ("Discloser") and Sam Roe ("Recipient"), March 3, 2026.
1. Recipient shall hold all Confidential Information in strict confidence in
perpetuity, with no expiration of these obligations.
2. Confidential Information includes any information disclosed orally or in writing,
whether or not marked confidential.
3. For five (5) years Recipient shall not solicit or hire any employee, contractor,
customer or supplier of Discloser.
4. Any improvement, idea or invention conceived by Recipient is hereby irrevocably
assigned to Discloser without additional compensation.
5. Discloser may obtain injunctive relief without posting bond and without proving
actual damages.
6. Any breach shall result in liquidated damages of $250,000 per occurrence.
7. Recipient shall certify destruction of all materials within 24 hours of request.
8. Recipient shall indemnify and hold Discloser harmless from any and all claims.
9. Recipient shall pay all of Discloser's attorney's fees incurred in enforcement.
"""

EMPLOY_FAIR = """
EMPLOYMENT AGREEMENT between Initech LLC ("Employer") and Sam Lee ("Employee"),
position Analyst, start date February 2, 2026.
1. Salary shall be $95,000 per year, paid semi-monthly, with standard benefits and
paid time off.
2. Either party may terminate this agreement with thirty (30) days notice.
3. Employee is classified as non-exempt and shall receive overtime at time and
one-half for hours over 40.
4. Prior inventions listed on Schedule A are excluded and shall not be assigned.
5. Nothing in this Agreement shall prohibit Employee from reporting possible
violations of law to any government agency.
6. The prevailing party in any dispute shall be awarded reasonable attorney's fees.
7. Employer's liability shall not exceed amounts paid under this Agreement.
"""

EMPLOY_PREDATORY = """
EMPLOYMENT AGREEMENT between Globex Inc ("Employer") and John Doe ("Employee"),
position Senior Engineer, start date January 5, 2026.
1. Employment is at-will and may be terminated at any time without cause or notice.
2. For twenty-four (24) months after separation, Employee shall not engage in any
business competitive with Employer anywhere in the United States.
3. Employee assigns to Employer all inventions conceived during employment, whether
or not developed on Employer time or using Employer resources.
4. Employee is classified as exempt and shall receive no overtime compensation
regardless of hours worked.
5. Salary shall be $150,000 per year. Any signing bonus must be repaid in full if
Employee departs within 24 months.
6. Employee waives any right to a jury trial and agrees to binding arbitration,
waiving class action participation.
7. Employer may deduct from final wages any amounts it determines are owed.
8. Employee shall notify any prospective employer of these restrictions.
"""

# name, text, doc_type, expected band (inclusive)
ARCHETYPES = [
    ("lease / tenant-friendly", LEASE_FRIENDLY,   "Residential Lease",   (88, 100)),
    ("lease / market-typical",  LEASE_TYPICAL,    "Residential Lease",   (62, 80)),
    ("lease / predatory",       LEASE_PREDATORY,  "Residential Lease",   (1, 40)),
    ("nda / fair",              NDA_FAIR,         "NDA",                 (88, 100)),
    ("nda / predatory",         NDA_PREDATORY,    "NDA",                 (1, 50)),
    ("employment / fair",       EMPLOY_FAIR,      "Employment Contract", (85, 100)),
    ("employment / predatory",  EMPLOY_PREDATORY, "Employment Contract", (1, 50)),
]


def fingerprint(text: str, doc_type: str) -> str:
    """Hash the whole result, not just the score, so finding drift is caught too."""
    r = score_document(text, doc_type)
    payload = json.dumps({
        "score": r.score, "grade": r.grade, "penalty": r.penalty,
        "credits": r.credits, "confidence": r.confidence,
        "risks": [(x.id, x.weight) for x in r.risks],
        "benefits": [(x.id, x.weight) for x in r.benefits],
    })
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


# ── 1. Determinism ─────────────────────────────────────────────────────────────
print("\n1. DETERMINISM (same text -> same score and same findings)")
for name, text, doc_type, _band in ARCHETYPES:
    hashes = {fingerprint(text, doc_type) for _ in range(200)}
    check(f"{name}: identical over 200 runs", len(hashes) == 1, f"{len(hashes)} variants")

print("\n   repetition immunity (duplicated text must not change the score)")
for name, text, doc_type, _band in ARCHETYPES:
    once = score_document(text, doc_type).score
    thrice = score_document(text + "\n" + text + "\n" + text, doc_type).score
    check(f"{name}: dedupe holds", once == thrice, f"{once} vs {thrice}")


# ── 2. Calibration ─────────────────────────────────────────────────────────────
print("\n2. CALIBRATION (expected band per archetype)")
scores = {}
for name, text, doc_type, (lo, hi) in ARCHETYPES:
    r = score_document(text, doc_type)
    scores[name] = r.score
    check(f"{name}: {r.score} in [{lo},{hi}] ({r.grade})", lo <= r.score <= hi, f"got {r.score}")

print("\n   relative ordering (fair must outrank predatory)")
for fair, bad in [("lease / tenant-friendly", "lease / predatory"),
                  ("lease / market-typical", "lease / predatory"),
                  ("nda / fair", "nda / predatory"),
                  ("employment / fair", "employment / predatory")]:
    check(f"{fair} > {bad}", scores[fair] > scores[bad], f"{scores[fair]} vs {scores[bad]}")


# ── 3. Safety: never call an unreadable document safe ──────────────────────────
print("\n3. SAFETY (unreadable input must not read as low risk)")
for label, text in [("empty", ""), ("whitespace", "   \n\t "),
                    ("garbled ocr", "l1 0f th3 pr3m1s3s h3r3by 4gr33s t0 th3 t3rms"),
                    ("title only", "RESIDENTIAL LEASE AGREEMENT"),
                    ("one sentence", "This document could not be read properly.")]:
    r = score_document(text, "Residential Lease")
    check(f"{label}: not low risk (score {r.score}, {r.confidence})",
          r.confidence == "low" and r.score <= scoring.CAP_LOW_CONFIDENCE)

print("\n   real documents must stay high confidence")
for name, text, doc_type, _band in ARCHETYPES:
    r = score_document(text, doc_type)
    check(f"{name}: confidence high", r.confidence == "high", r.confidence)


# ── 4. Precision: protective and routine clauses must not be flagged ──────────
print("\n4. PRECISION (no false positives on protective or routine clauses)")
NEGATIVE = [
    ("emergency-only entry",      "Landlord may enter without notice only in the event of an emergency.", "entry_no_notice"),
    ("sublet with consent",       "Tenant shall not sublet without Landlord's prior written consent.",    "no_sublet_absolute"),
    ("prevailing-party fees",     "The prevailing party shall recover attorney's fees.",                  "one_way_attorney_fees"),
    ("each party bears own fees", "Each party shall bear its own attorney's fees.",                       "one_way_attorney_fees"),
    ("24h entry notice",          "Landlord shall provide twenty-four (24) hours written notice before entry.", "entry_short_notice"),
    ("prior-invention carve-out", "Prior inventions listed on Schedule A are excluded and shall not be assigned.", "ip_assignment_broad"),
    ("carve-out not a sublet ban","Prior inventions are excluded and shall not be assigned to Employer.",  "no_sublet_absolute"),
    ("routine occupancy",         "The premises shall be occupied by Tenant and immediate family.",        "occupancy_strict"),
    ("right to cure",             "Landlord shall give Tenant the right to cure any default within 10 days.", "one_strike_eviction"),
    ("plain governing law",       "This Agreement is governed by the laws of Delaware.",                   "exclusive_distant_forum"),
]
for label, text, must_not_fire in NEGATIVE:
    fired = {r.id for r in match_rules(text)[0]}
    check(f"{label}: {must_not_fire} not fired", must_not_fire not in fired, str(sorted(fired)))

print("\n   genuine red flags must still fire")
POSITIVE = [
    ("no-notice entry",     "Landlord may enter the premises at any time without notice.",       "entry_no_notice"),
    ("habitability waiver", "Tenant waives the implied warranty of habitability.",               "waive_habitability"),
    ("active IP grab",      "Employee assigns to Employer all inventions conceived.",            "ip_assignment_broad"),
    ("passive IP grab",     "Any invention is hereby irrevocably assigned to Discloser.",        "ip_assignment_broad"),
    ("absolute sublet ban", "Tenant shall not sublet or assign the premises under any circumstance.", "no_sublet_absolute"),
    ("arbitration waiver",  "Employee waives any right to a jury trial and agrees to arbitration.", "mandatory_arbitration"),
    ("perpetual terms",     "Recipient shall hold information in confidence in perpetuity.",     "perpetual_obligations"),
]
for label, text, must_fire in POSITIVE:
    fired = {r.id for r in match_rules(text)[0]}
    check(f"{label}: {must_fire} fired", must_fire in fired, str(sorted(fired)))


# ── 5. Quantitative grading ────────────────────────────────────────────────────
print("\n5. MAGNITUDE (amounts graded, not just detected)")
NUMERIC = [
    ("$2,400 rent / $75 late fee is not steep", "Rent of $2,400 is due monthly. A late fee of $75 applies.", None),
    ("deposit 3x rent",        "Tenant shall pay $1,800 per month. A security deposit of $5,400 is required.", "deposit_ratio_high"),
    ("late fee 12.5% of rent", "Rent of $2,000 per month. Late charge of $250.",                                "late_fee_steep"),
    ("$250k penalty",          "Any breach results in liquidated damages of $250,000 per occurrence.",          "penalty_very_large"),
    ("24-month non-compete",   "The non-compete restriction lasts 24 months after separation.",                 "noncompete_very_long"),
]
for label, text, expected in NUMERIC:
    ids = {i for i, _l, _w, _c in numeric_findings(text, set())}
    check(f"{label}", (expected in ids) if expected else not ids, str(sorted(ids)))


# ── 6. Clause classification ───────────────────────────────────────────────────
print("\n6. CLAUSE CLASSIFICATION")
CLAUSES = [
    ("Landlord may enter the premises at any time without notice.", "high"),
    ("Tenant shall indemnify and hold Landlord harmless from all claims.", "high"),
    ("Landlord shall provide twenty-four (24) hours written notice before entry.", "favorable"),
    ("The premises are located at 123 Main Street, Unit 4.", "standard"),
]
for text, expected in CLAUSES:
    level, score = classify_clause(text)
    check(f"{expected:9} <- {text[:52]}", level == expected, f"got {level}")

print("\n   classification is deterministic")
for text, _expected in CLAUSES:
    results = {classify_clause(text) for _ in range(200)}
    check(f"stable <- {text[:52]}", len(results) == 1)


# ── 7. Sensitivity ─────────────────────────────────────────────────────────────
# The weights are considered legal judgment, not measured constants. This checks
# that the CONCLUSIONS do not depend on the exact numbers: perturb every severity
# weight by +/-20% and the bands and ordering must still hold. It is not a
# substitute for calibrating against documents rated by a real attorney, which
# remains the main outstanding gap.
print("\n7. SENSITIVITY (conclusions must survive +/-20% weight perturbation)")

from dataclasses import replace as _dc_replace

_ORIG_CONSTS = (scoring.CRITICAL, scoring.HIGH, scoring.MEDIUM, scoring.LOW, scoring.K)
_ORIG_RULES = {
    "risk": list(scoring.RISK_RULES),
    "absence": list(scoring.ABSENCE_RULES),
    "combo": list(scoring.COMBO_RULES),
    "credit": list(scoring.CREDIT_RULES),
}


def _perturb(factor: float) -> None:
    """Scale every severity weight, the credits and the curve constant."""
    scoring.CRITICAL = max(1, round(_ORIG_CONSTS[0] * factor))
    scoring.HIGH = max(1, round(_ORIG_CONSTS[1] * factor))
    scoring.MEDIUM = max(1, round(_ORIG_CONSTS[2] * factor))
    scoring.LOW = max(1, round(_ORIG_CONSTS[3] * factor))
    scoring.K = max(1, round(_ORIG_CONSTS[4] * factor))
    # Rules captured their weight at definition time, so rebuild each one.
    for key, bucket in (("risk", scoring.RISK_RULES), ("absence", scoring.ABSENCE_RULES),
                        ("combo", scoring.COMBO_RULES), ("credit", scoring.CREDIT_RULES)):
        bucket[:] = [_dc_replace(r, weight=max(1, round(r.weight * factor)))
                     for r in _ORIG_RULES[key]]


def _restore() -> None:
    (scoring.CRITICAL, scoring.HIGH, scoring.MEDIUM,
     scoring.LOW, scoring.K) = _ORIG_CONSTS
    scoring.RISK_RULES[:] = _ORIG_RULES["risk"]
    scoring.ABSENCE_RULES[:] = _ORIG_RULES["absence"]
    scoring.COMBO_RULES[:] = _ORIG_RULES["combo"]
    scoring.CREDIT_RULES[:] = _ORIG_RULES["credit"]


try:
    for factor in (0.8, 1.2):
        _perturb(factor)
        results = {name: score_document(text, dt).score for name, text, dt, _b in ARCHETYPES}
        weights_changed = scoring.RISK_RULES[0].weight != _ORIG_RULES["risk"][0].weight
        _restore()
        check(f"x{factor}: weights actually changed", weights_changed)
        check(f"x{factor}: ordering preserved",
              results["lease / tenant-friendly"] > results["lease / market-typical"] >
              results["lease / predatory"] and
              results["nda / fair"] > results["nda / predatory"] and
              results["employment / fair"] > results["employment / predatory"],
              str(results))
        check(f"x{factor}: predatory stays below 60",
              all(results[n] < 60 for n in ("lease / predatory", "nda / predatory",
                                            "employment / predatory")), str(results))
        check(f"x{factor}: fair stays at or above 80",
              all(results[n] >= 80 for n in ("lease / tenant-friendly", "nda / fair",
                                             "employment / fair")), str(results))
finally:
    _restore()

_after = {name: score_document(text, dt).score for name, text, dt, _b in ARCHETYPES}
check("baseline restored after perturbation",
      _after == scores, f"{_after} vs {scores}")


# ── Summary ────────────────────────────────────────────────────────────────────
print("\n" + "=" * 70)
print(f"rules: {len(scoring.RISK_RULES)} risk, {len(scoring.CREDIT_RULES)} credit, "
      f"{len(scoring.ABSENCE_RULES)} absence, {len(scoring.COMBO_RULES)} combination")
if failures:
    print(f"FAILED: {len(failures)} check(s)")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
print("ALL CHECKS PASSED")
