"""
Deterministic lease risk scoring engine.

Design goals:
  1. CONSISTENT  - the score is a pure function of the document text. No LLM, no
                   randomness, no dependence on how many clauses a model returned.
                   The same PDF always produces the same score.
  2. THOROUGH    - ~45 specific provisions drawn from real tenant-law risk factors,
                   each weighted by actual severity rather than a flat per-clause count.
  3. AUDITABLE   - every point of penalty traces back to a named rule, so the score
                   can be explained instead of just asserted.

Scoring model
-------------
  penalty   = sum of weights of DISTINCT matched risk rules (deduped per document,
              so a provision repeated in three clauses is not punished three times)
  credits   = sum of weights of DISTINCT matched tenant-favorable rules (capped)
  effective = max(0, penalty - credits)
  base      = 100 * K / (effective + K)        # smooth hyperbolic decay, never clamps to 0
  score     = min(base, ceiling_for_worst_severity)

The hyperbolic curve keeps resolution across the whole range (no saturation at 0
the way flat subtraction does), and the severity ceiling guarantees a lease with a
critical red flag can never score in the "safe" band just because it also happens
to include some tenant-friendly boilerplate.
"""

import re
from dataclasses import dataclass, field
from typing import List, Tuple, Dict, Optional

# ── Severity weights ────────────────────────────────────────────────────────────
CRITICAL = 14
HIGH = 9
MEDIUM = 5
LOW = 2

# Curve constant. Higher K = gentler curve. Tuned so that a typical US residential
# lease lands in the high 60s/70s, a tenant-friendly one 90+, a predatory one <45.
K = 70

# Credits cannot fully erase real risk.
MAX_CREDITS = 12

# Severity ceilings. A document with serious red flags cannot score in the safe
# band no matter how many favorable terms it also contains. The count-based tier
# matters because short documents (NDAs, offer letters) accumulate far less raw
# penalty than a 30-page lease, yet several compounding HIGH provisions are just
# as damaging.
CEILING_CRITICAL = 45     # any critical provision
CEILING_MANY_HIGH = 55    # three or more high-severity provisions
CEILING_HIGH = 72         # at least one high-severity provision
MANY_HIGH_THRESHOLD = 3

# Even a clean lease is not certified "perfect" - keeps the top of the scale honest.
MAX_SCORE = 97


@dataclass(frozen=True)
class Rule:
    id: str
    label: str
    weight: int
    patterns: Tuple[str, ...]
    exclude: Tuple[str, ...] = ()
    category: str = ""

    def matches(self, text: str) -> bool:
        if not any(re.search(p, text, re.I) for p in self.patterns):
            return False
        return not any(re.search(e, text, re.I) for e in self.exclude)


# ── Risk rules ──────────────────────────────────────────────────────────────────
# Ordered roughly by severity. Patterns are matched against whitespace-normalized
# text, so a provision split across PDF line breaks still matches.

RISK_RULES: List[Rule] = [
    # ---- CRITICAL: provisions that strip core legal protections -----------------
    Rule("waive_habitability", "Waives the warranty of habitability", CRITICAL, (
        r"waiv\w*[^.]{0,90}(warrant\w+ of habitability|implied warrant\w+)",
        r"(warrant\w+ of habitability)[^.]{0,70}waiv\w*",
        r"accept\w*[^.]{0,40}\bas[- ]is\b[^.]{0,60}waiv\w*[^.]{0,40}repair",
    ), category="Habitability"),

    Rule("confession_of_judgment", "Contains a confession of judgment", CRITICAL, (
        r"confession of judgment", r"confess\w*\s+judgment",
    ), category="Legal process"),

    Rule("waive_eviction_notice", "Waives notice or hearing before eviction", CRITICAL, (
        r"waiv\w*[^.]{0,90}(notice to quit|notice to vacate|right to (a )?(hearing|trial)|service of process)",
        r"waiv\w*[^.]{0,90}notice of (default|termination|eviction)",
    ), category="Legal process"),

    Rule("entry_no_notice", "Landlord may enter without notice", CRITICAL, (
        r"(enter|entry|access)[^.]{0,90}(without (prior |any )?notice|at any time (of the day|without))",
        r"without (prior |any )?notice[^.]{0,70}(enter|entry)",
    ), exclude=(
        r"(emergenc\w+)[^.]{0,40}(without (prior |any )?notice)",
        r"without (prior |any )?notice[^.]{0,40}(in (case|the event) of )?emergenc",
    ), category="Entry rights"),

    Rule("self_help_eviction", "Allows lockout or seizure without a court order", CRITICAL, (
        r"(lock\s?out|change\w*\s+the\s+locks|remove[^.]{0,40}(possessions|belongings|personal property))[^.]{0,80}without[^.]{0,40}(court|legal process|judicial)",
        r"landlord[^.]{0,60}may[^.]{0,40}(seize|take possession of)[^.]{0,40}(tenant'?s?)?[^.]{0,30}(property|belongings)",
    ), category="Legal process"),

    # ---- HIGH: provisions that create serious one-sided exposure -----------------
    Rule("mandatory_arbitration", "Forces arbitration / waives jury trial", HIGH, (
        r"binding arbitration", r"agree\w*[^.]{0,40}to arbitrat",
        r"waiv\w*[^.]{0,60}(jury trial|right to a jury|trial by jury)",
        r"waiv\w*[^.]{0,60}class action",
    ), category="Dispute resolution"),

    Rule("one_way_attorney_fees", "You pay the other side's attorney fees", HIGH, (
        r"tenant[^.]{0,140}(landlord'?s?|lessor'?s?|owner'?s?)[^.]{0,50}attorney'?s?,?\s*(fees|costs)",
        r"attorney'?s?,?\s*fees[^.]{0,90}incurred by[^.]{0,40}(landlord|lessor|owner|discloser|employer|company)",
        # Generic: the weaker party pays the stronger party's fees.
        r"(shall|must|agrees? to|will)\s+(pay|reimburse)[^.]{0,90}(landlord|lessor|owner|discloser|employer|company|seller|licensor)'?s?[^.]{0,60}attorney",
    ), exclude=(
        r"prevailing party", r"either party[^.]{0,60}attorney", r"each party[^.]{0,60}(own|its own)[^.]{0,30}attorney",
    ), category="Legal costs"),

    Rule("broad_indemnity", "Broad indemnification / hold harmless", HIGH, (
        r"indemnif\w+", r"hold[^.]{0,40}(landlord|lessor|owner)[^.]{0,40}harmless",
    ), category="Liability"),

    Rule("joint_several", "Joint and several liability for all tenants", HIGH, (
        r"joint(ly)?\s+and\s+several(ly)?",
    ), category="Liability"),

    Rule("auto_renew_long_notice", "Auto-renews unless you give long advance notice", HIGH, (
        r"(automatic\w*|auto-?)\s*(renew\w+|extend\w+)[^.]{0,160}\b(sixty|60|ninety|90)\b[^.]{0,40}days?",
        r"\b(sixty|60|ninety|90)\b[^.]{0,40}days?[^.]{0,160}(automatic\w*|auto-?)\s*(renew\w+|extend\w+)",
    ), category="Renewal"),

    Rule("no_sublet_absolute", "Subletting or assignment flatly prohibited", HIGH, (
        # "sublet" is unambiguous on its own.
        r"(shall not|may not|must not|is prohibited from|no)[^.]{0,70}(sublet|subleas\w+)",
        r"(sublet\w*|subleas\w+)[^.]{0,40}(not (allowed|permitted)|prohibited)",
        # "assign" is not: it also appears in IP-assignment clauses, so require
        # that it is the lease or premises being assigned.
        r"(shall not|may not|must not|is prohibited from)[^.]{0,60}assign\w*[^.]{0,90}(lease|premises|tenancy|unit|apartment)",
        r"(lease|premises|tenancy)[^.]{0,60}(shall not|may not) be assign\w*",
    ), exclude=(
        r"(sublet|subleas\w+|assign\w*)[^.]{0,90}(prior )?(written )?consent",
        r"(prior )?(written )?consent[^.]{0,90}(sublet|subleas\w+|assign\w*)",
    ), category="Subletting"),

    Rule("tenant_all_repairs", "Tenant made responsible for all repairs", HIGH, (
        r"tenant[^.]{0,70}(responsible|liable)\s+for\s+all[^.]{0,40}(repairs|maintenance)",
        r"tenant[^.]{0,60}shall[^.]{0,40}(maintain|repair)[^.]{0,40}at (tenant'?s?|its) (sole )?(expense|cost)[^.]{0,40}all",
    ), category="Maintenance"),

    Rule("unilateral_rule_change", "Landlord may change the rules unilaterally", MEDIUM, (
        r"(landlord|lessor|owner|management)[^.]{0,70}(may|reserves the right to|shall have the right to)[^.]{0,50}(amend|change|modify|alter|promulgate)[^.]{0,60}(rules|regulations|policies|addend\w+)",
    ), category="Unilateral terms"),

    Rule("nonrefundable_fees", "Non-refundable deposits or fees", HIGH, (
        r"non-?refundable[^.]{0,50}(deposit|fee|charge|payment)",
        r"(deposit|fee)[^.]{0,40}(is|shall be|are)\s+non-?refundable",
    ), category="Deposits"),

    Rule("liquidated_damages", "Liquidated damages / steep early-exit penalty", HIGH, (
        r"liquidated damages",
        r"(two|2|three|3)\s*(\(\d\)\s*)?months?'?\s*rent[^.]{0,90}(terminat\w+|break\w*|early|cancel\w*)",
        r"(terminat\w+|break\w*|early|cancel\w*)[^.]{0,90}(two|2|three|3)\s*(\(\d\)\s*)?months?'?\s*rent",
    ), category="Early termination"),

    Rule("deposit_over_two_months", "Security deposit exceeds two months' rent", HIGH, (
        r"(security )?deposit[^.]{0,90}(three|3|four|4)\s*(\(\d\)\s*)?months?'?\s*rent",
        r"(three|3|four|4)\s*(\(\d\)\s*)?months?'?\s*rent[^.]{0,60}(security )?deposit",
    ), category="Deposits"),

    Rule("rent_acceleration", "Entire remaining rent can be accelerated on default", HIGH, (
        r"acceler\w+[^.]{0,70}(rent|balance|amounts? due)",
        r"(entire|all|total)[^.]{0,40}(remaining|unpaid|balance of)[^.]{0,40}rent[^.]{0,50}(immediately )?(due|payable)",
    ), category="Default"),

    # ---- MEDIUM: common but meaningfully unfavorable ----------------------------
    Rule("late_fee_no_grace", "Late fee with no grace period", MEDIUM, (
        r"late (fee|charge)[^.]{0,90}(immediately|day after|first day|no grace|without grace)",
        r"rent[^.]{0,40}not (received|paid)[^.]{0,40}on the (first|1st)[^.]{0,60}late (fee|charge)",
    ), category="Late fees"),

    Rule("notice_60_plus", "Requires 60+ days notice to move out", MEDIUM, (
        r"\b(sixty|60|ninety|90)\b[^.]{0,20}(\(\d+\)\s*)?days?[^.]{0,90}(written )?notice[^.]{0,60}(vacate|terminat\w+|move out|non-?renew)",
        r"(vacate|terminat\w+|move out|non-?renew)[^.]{0,90}\b(sixty|60|ninety|90)\b[^.]{0,20}(\(\d+\)\s*)?days?[^.]{0,40}notice",
    ), category="Notice"),

    Rule("holdover_penalty", "Holdover rent penalty (often 1.5-2x)", MEDIUM, (
        r"hold(ing)?\s?over[^.]{0,120}(1\.5|one and one-half|150%|double|twice|two times|200%)",
        r"(1\.5|one and one-half|150%|double|twice|200%)[^.]{0,80}hold(ing)?\s?over",
    ), category="Holdover"),

    Rule("entry_short_notice", "Entry allowed on less than 24 hours notice", MEDIUM, (
        r"\b(one|two|three|four|six|eight|twelve|1|2|3|4|6|8|12)\s*(\(\d+\)\s*)?hours?[^.]{0,90}notice[^.]{0,40}(enter|entry|access)",
        r"(enter|entry|access)[^.]{0,90}\b(one|two|three|four|six|eight|twelve|1|2|3|4|6|8|12)\s*(\(\d+\)\s*)?hours?[^.]{0,30}notice",
    ), exclude=(
        # "twenty-four (24) hours" contains a literal "24" - never treat 24h/48h as short
        r"(twenty-?four|forty-?eight|24|48)\s*(\(\d+\)\s*)?hours?",
    ), category="Entry rights"),

    Rule("mandatory_renters_insurance", "Renter's insurance required at your cost", MEDIUM, (
        r"(shall|must|required to|agrees? to)[^.]{0,60}(maintain|obtain|carry|purchase)[^.]{0,60}(renter'?s?|liability|personal)\s+insurance",
    ), category="Insurance"),

    Rule("all_utilities_tenant", "Tenant pays all utilities", LOW, (
        r"tenant[^.]{0,70}(responsible for|shall pay|pays?)[^.]{0,50}all[^.]{0,30}utilit\w+",
    ), category="Utilities"),

    Rule("early_termination_fee", "Early termination fee applies", MEDIUM, (
        r"early terminat\w+[^.]{0,70}(fee|charge|penalty)",
        r"(fee|charge|penalty)[^.]{0,60}early terminat\w+",
    ), category="Early termination"),

    Rule("mandatory_cleaning_fee", "Mandatory cleaning charge regardless of condition", MEDIUM, (
        r"(carpet cleaning|cleaning fee|professional cleaning)[^.]{0,90}(required|shall|must|regardless|non-?refundable|deducted)",
    ), category="Move-out"),

    Rule("guest_restrictions", "Restrictions on guests or occupancy", MEDIUM, (
        r"(guest|visitor)s?[^.]{0,90}(shall not|may not|no more than|limited to|prohibited|consecutive (days|nights))",
        r"overnight guests?[^.]{0,60}(not|limit|prohibit|consent|approv)",
    ), category="Guests"),

    Rule("no_pets", "Pets entirely prohibited", LOW, (
        r"no pets?\b", r"pets?[^.]{0,50}(are )?(not (allowed|permitted)|prohibited)",
    ), exclude=(r"service animal[^.]{0,60}(permitted|allowed|exempt)",), category="Pets"),

    Rule("landlord_not_liable", "Landlord disclaims liability broadly", MEDIUM, (
        r"(landlord|lessor|owner)[^.]{0,50}(shall )?not be liable[^.]{0,80}(any|all)",
    ), category="Liability"),

    Rule("late_fee_present", "Late fee provision", LOW, (
        r"late (fee|charge|payment charge)",
    ), category="Late fees"),

    # ---- LOW: restrictions worth knowing but routine ----------------------------
    Rule("alteration_restriction", "No alterations or decorating without consent", LOW, (
        r"(shall not|may not|no)[^.]{0,60}(alter|paint|redecorat\w+|install|modif\w+)[^.]{0,60}(without|consent)",
    ), category="Alterations"),

    Rule("smoking_ban", "Smoking prohibited", LOW, (
        r"(no smoking|smoking[^.]{0,40}prohibit\w*|smoke-?free)",
    ), category="Smoking"),

    Rule("parking_restriction", "Parking restrictions or fees", LOW, (
        r"parking[^.]{0,80}(fee|charge|assigned|not (guaranteed|included)|tow)",
    ), category="Parking"),

    Rule("quiet_hours", "Noise / quiet-hours rules", LOW, (
        r"(quiet hours|noise[^.]{0,50}(prohibit\w*|restrict\w*)|disturb\w+ (other|neighbor))",
    ), category="Noise"),

    Rule("lock_key_fees", "Lockout or key replacement fees", LOW, (
        r"(lock\s?out|key|fob)[^.]{0,60}(fee|charge|\$\s*\d+)",
    ), category="Fees"),
# ---- General contract, NDA and employment provisions ----------------------
    # Keyed on language that does not appear in residential leases, so these are
    # safe to evaluate against every document type.

    Rule("noncompete_unlimited_geography", "Non-compete with no geographic limit", CRITICAL, (
        r"(non-?compet\w+|not (engage|compete)|shall not[^.]{0,40}competitive)[^.]{0,200}(anywhere in the (united states|world|country)|without (any )?geographic (limit|restriction|scope)|in any (state|country|territory))",
        r"(anywhere in the (united states|world)|without (any )?geographic (limit|restriction))[^.]{0,200}(non-?compet\w+|competitive)",
    ), category="Non-compete"),

    Rule("invention_assignment_offhours", "Claims inventions made on your own time", CRITICAL, (
        r"(invention|idea|improvement|work product|discover\w+)[^.]{0,160}whether or not[^.]{0,80}(on|using|during)[^.]{0,60}(employer|company|its)[^.]{0,30}(time|resources|equipment|premises)",
        r"whether or not[^.]{0,60}(developed|conceived|made)[^.]{0,60}(on|using)[^.]{0,50}(employer|company)[^.]{0,30}(time|resources|equipment)",
    ), category="Intellectual property"),

    Rule("perpetual_obligations", "Obligations never expire (perpetual)", HIGH, (
        r"(in perpetuity|perpetual\w*)",
        r"(confidential\w*|obligation\w*)[^.]{0,90}(shall (not|never) (expire|terminate)|no expiration|survive[^.]{0,30}indefinitel)",
    ), category="Term"),

    Rule("noncompete_present", "Non-compete restricts future work", HIGH, (
        r"non-?compet\w+",
        r"shall not[^.]{0,80}(engage in|be employed by|work for)[^.]{0,80}(business )?competitive",
    ), category="Non-compete"),

    Rule("ip_assignment_broad", "Broad assignment of your intellectual property", HIGH, (
        r"(assign\w*|hereby assigns?)[^.]{0,120}(invention|idea|improvement|work product|intellectual property|copyright|patent)",
        r"(invention|idea|improvement|work product)\w*[^.]{0,90}(?:is|are|shall be|will be)\s+(?:hereby\s+|irrevocably\s+|automatically\s+)*(?:assigned|the (?:sole )?property)\b",
    ), exclude=(
        r"(sublet|subleas\w+|assign\w*)[^.]{0,60}(the )?(lease|premises)",
    ), category="Intellectual property"),

    Rule("no_overtime_exempt", "No overtime regardless of hours worked", HIGH, (
        r"(exempt|no overtime|without overtime)[^.]{0,120}(regardless of[^.]{0,30}hours|no overtime|not[^.]{0,30}entitled[^.]{0,30}overtime)",
        r"no overtime[^.]{0,80}regardless",
    ), category="Compensation"),

    Rule("wage_deduction_unilateral", "Employer may deduct from your wages at will", HIGH, (
        r"(deduct|withhold|offset)\w*[^.]{0,90}(from )?(final |your )?(wages|paycheck|salary|compensation)",
    ), category="Compensation"),

    Rule("nonsolicit_long", "Long non-solicitation restriction", HIGH, (
        r"(non-?solicit\w*|shall not solicit)[^.]{0,160}\b(two|three|four|five|2|3|4|5)\b\s*(\(\d+\)\s*)?years?",
        r"\b(two|three|four|five|2|3|4|5)\b\s*(\(\d+\)\s*)?years?[^.]{0,120}(non-?solicit\w*|not solicit)",
    ), category="Non-solicitation"),

    Rule("unlimited_liability", "Unlimited or uncapped liability", HIGH, (
        r"(unlimited|without limitation|no limit)[^.]{0,60}liab\w+",
        r"liab\w+[^.]{0,60}(shall not be (limited|capped)|without limitation)",
    ), category="Liability"),

    Rule("bonus_clawback", "Signing or relocation bonus must be repaid", MEDIUM, (
        r"(clawback|claw back)",
        r"(repaid?|repay|reimburse|return)[^.]{0,110}(signing |relocation |retention )?bonus",
        r"bonus[^.]{0,90}(must be|shall be)[^.]{0,40}(repaid|returned|reimbursed)",
    ), category="Compensation"),

    Rule("overbroad_confidentiality", "Confidential info defined too broadly", MEDIUM, (
        r"whether or not[^.]{0,60}(marked|designated|identified|labeled)",
        r"(disclosed )?(orally or in writing|in any form)[^.]{0,80}whether or not",
    ), category="Confidentiality"),

    Rule("injunctive_without_bond", "Injunction without bond or proof of damages", MEDIUM, (
        r"injunctive relief[^.]{0,110}without[^.]{0,60}(bond|proving|showing|posting)",
        r"without[^.]{0,40}(posting )?bond[^.]{0,80}injunctive",
    ), category="Remedies"),

    Rule("unilateral_termination_no_notice", "Other side may terminate without cause or notice", MEDIUM, (
        r"(may (be )?terminat\w+|reserves the right to terminate)[^.]{0,90}(at any time|without cause)[^.]{0,60}without[^.]{0,30}notice",
        r"at-?will[^.]{0,90}without (cause or notice|notice)",
    ), category="Termination"),

    Rule("short_return_window", "Very short deadline to return or destroy materials", LOW, (
        r"(within|no later than)[^.]{0,30}(twenty-?four|forty-?eight|24|48)\s*(\(\d+\)\s*)?hours?[^.]{0,90}(return|destro\w+|certif\w+)",
    ), category="Confidentiality"),
# ---- Additional lease provisions a reviewer would flag ---------------------
    Rule("rules_by_reference", "Binds you to rules not attached to the lease", HIGH, (
        r"(rules and regulations|community (policies|guidelines)|handbook|addend\w+)[^.]{0,120}(incorporated[^.]{0,30}by reference|as (may be )?(amended|modified)|posted)",
    ), category="Unilateral terms"),

    Rule("one_strike_eviction", "Single violation can end the tenancy", HIGH, (
        r"(crime-?free|one[- ]strike|zero[- ]tolerance|single violation|any violation)[^.]{0,110}(terminat\w+|evict\w+|immediate)",
    ), category="Default"),

    Rule("guarantor_unlimited", "Guarantor or co-signer liability is unlimited", HIGH, (
        r"(guarantor|co-?signer|surety)[^.]{0,140}(unconditional\w*|absolute\w*|all (obligations|amounts|sums))",
    ), category="Liability"),

    Rule("waive_itemized_deductions", "Waives your right to an itemized deposit statement", HIGH, (
        r"waiv\w*[^.]{0,100}itemi[sz]\w+[^.]{0,50}(statement|list|accounting|breakdown)",
    ), category="Deposits"),

    Rule("waive_tenant_organizing", "Restricts joining a tenant organization", HIGH, (
        r"(shall not|may not|prohibited from)[^.]{0,90}(tenant (union|association|organization)|organiz\w+ (with )?other (tenants|residents))",
    ), category="Tenant rights"),

    Rule("rent_escalation_midterm", "Rent can rise during the term", MEDIUM, (
        r"rent[^.]{0,110}(may be |shall be |subject to )?(increas\w+|adjust\w+|escalat\w+)[^.]{0,80}(during the (initial )?term|upon \d+ days|with \d+ days|annually)",
    ), category="Rent"),

    Rule("consent_sole_discretion", "Approvals left to sole and absolute discretion", MEDIUM, (
        r"(sole|absolute|unfettered)\s+(and absolute\s+)?discretion",
    ), category="Unilateral terms"),

    Rule("notice_by_posting", "Legal notices may be served by posting on your door", MEDIUM, (
        r"notice[^.]{0,100}(post\w+|affix\w+|tap\w+|attach\w+)[^.]{0,60}(door|premises|entrance)",
    ), category="Notice"),

    Rule("abandonment_disposal", "Your belongings can be disposed of if deemed abandoned", MEDIUM, (
        r"abandon\w*[^.]{0,140}(dispose|discard|destroy|sell|remove)",
    ), category="Move-out"),

    Rule("renovation_no_abatement", "Renovation disruption with no rent reduction", MEDIUM, (
        r"(renovat\w+|construct\w+|alterat\w+|repair\w+)[^.]{0,140}(no|without)[^.]{0,40}(rent )?(abatement|reduction|offset|credit)",
    ), category="Maintenance"),

    Rule("mandatory_epay_fee", "Electronic payment required, with a fee", LOW, (
        r"(electronic|online|portal|ach)[^.]{0,70}payment[^.]{0,80}(fee|convenience charge|service charge)",
    ), category="Fees"),

    Rule("deposit_commingled", "Deposit need not be held separately", LOW, (
        r"deposit[^.]{0,100}(commingl\w+|need not be (held|kept)[^.]{0,40}(separate|trust|escrow))",
    ), category="Deposits"),

    Rule("occupancy_strict", "Strict limit on who may live there", LOW, (
        r"occupan\w+[^.]{0,80}(shall not exceed|limited to|no more than)[^.]{0,30}(\w+|\d+)\s*(person|occupant|adult)",
    ), category="Occupancy"),

    # ---- Additional NDA / employment provisions --------------------------------
    Rule("training_repayment", "Must repay training costs if you leave", HIGH, (
        r"(training|education|certification|tuition|licens\w+)[^.]{0,130}(repay|reimburse|refund)[^.]{0,80}(if|upon|should)[^.]{0,50}(depart|resign|terminat|leave|separat)",
    ), category="Compensation"),

    Rule("non_disparagement", "Cannot speak negatively, even truthfully", MEDIUM, (
        r"non-?disparag\w+", r"shall not[^.]{0,50}disparage",
    ), category="Speech"),

    Rule("notify_new_employer", "Must tell future employers about these restrictions", MEDIUM, (
        r"(notify|inform|advise|disclose to)[^.]{0,100}(new|prospective|subsequent|future) employer",
    ), category="Non-compete"),

    Rule("moral_rights_waiver", "Waives moral rights in your work", MEDIUM, (
        r"moral rights",
    ), category="Intellectual property"),

    Rule("exclusive_distant_forum", "Disputes must be heard in a chosen court", MEDIUM, (
        r"exclusive\w*\s+(venue|jurisdiction|forum)",
        r"submit\w*[^.]{0,60}exclusive jurisdiction",
        r"irrevocably (consent|submit)[^.]{0,60}jurisdiction",
    ), category="Dispute resolution"),

    Rule("inevitable_disclosure", "Relies on the inevitable-disclosure theory", MEDIUM, (
        r"inevitab\w+[^.]{0,40}disclos\w+",
    ), category="Confidentiality"),
]


# ── Tenant-favorable rules (credits) ───────────────────────────────────────────
CREDIT_RULES: List[Rule] = [
    Rule("grace_period", "Rent grace period of 5+ days", 4, (
        r"grace period[^.]{0,60}\b(five|5|six|6|seven|7|ten|10)\b",
        r"\b(five|5|six|6|seven|7|ten|10)\b[^.]{0,20}(\(\d+\)\s*)?days?[^.]{0,40}grace",
    ), category="Late fees"),

    Rule("entry_24h_notice", "Entry requires 24+ hours written notice", 4, (
        r"(twenty-?four|forty-?eight|24|48)\s*(\(\d+\)\s*)?hours?[^.]{0,70}(written )?notice[^.]{0,50}(enter|entry|access)",
        r"(enter|entry|access)[^.]{0,80}(twenty-?four|forty-?eight|24|48)\s*(\(\d+\)\s*)?hours?[^.]{0,40}notice",
        r"\b(one|two|1|2)\s*(\(\d+\)\s*)?days?[^.]{0,60}(written )?notice[^.]{0,50}(enter|entry|access)",
    ), category="Entry rights"),

    Rule("sublet_with_consent", "Subletting permitted with consent", 3, (
        r"(sublet|subleas\w+|assign\w*)[^.]{0,90}(prior )?(written )?consent",
    ), category="Subletting"),

    Rule("landlord_repairs", "Landlord responsible for repairs and maintenance", 3, (
        r"(landlord|lessor|owner)[^.]{0,70}(shall|will|is responsible for|agrees to)[^.]{0,50}(maintain|repair|keep[^.]{0,30}(good )?repair)",
    ), category="Maintenance"),

    Rule("deposit_return_window", "States a deadline for returning the deposit", 3, (
        r"deposit[^.]{0,120}(returned|refunded|remitted)[^.]{0,60}within[^.]{0,30}\d+\s*(\(\d+\)\s*)?days?",
        r"within[^.]{0,20}\d+\s*(\(\d+\)\s*)?days?[^.]{0,80}(return|refund)[^.]{0,40}deposit",
    ), category="Deposits"),

    Rule("prorated_rent", "Rent is prorated", 3, (
        r"pro-?rat\w+[^.]{0,40}rent", r"rent[^.]{0,40}pro-?rat\w+",
    ), category="Rent"),

    Rule("deposit_interest", "Interest paid on the security deposit", 3, (
        r"interest[^.]{0,60}(on|accru\w+)[^.]{0,40}deposit", r"deposit[^.]{0,50}bear[^.]{0,30}interest",
    ), category="Deposits"),

    Rule("mutual_attorney_fees", "Attorney fees awarded to the prevailing party", 3, (
        r"prevailing party[^.]{0,80}attorney'?s?,?\s*fees",
    ), category="Legal costs"),

    Rule("written_move_in_inspection", "Move-in inspection / condition checklist", 3, (
        r"(move-?in|inspection)[^.]{0,70}(checklist|statement of condition|inventory|condition (report|form))",
    ), category="Move-in"),

    Rule("early_term_reasonable", "Reasonable early-termination path", 3, (
        r"(one|1)\s*(\(\d\)\s*)?month'?s?\s*rent[^.]{0,80}(early )?terminat\w+",
        r"(thirty|30)\s*(\(\d+\)\s*)?days?[^.]{0,60}notice[^.]{0,60}terminat\w+",
    ), category="Early termination"),
Rule("mutual_obligations", "Obligations are mutual, not one-sided", 3, (
        r"mutual (non-?disclosure|confidentiality|agreement)",
        r"each party[^.]{0,80}(shall|agrees to)[^.]{0,60}(hold|protect|maintain)",
    ), category="Fairness"),

    Rule("confidentiality_time_limited", "Confidentiality obligations expire", 3, (
        r"(confidential\w*)[^.]{0,110}(expire|terminate|end)[^.]{0,60}\b(one|two|three|five|1|2|3|5)\b\s*(\(\d+\)\s*)?years?",
        r"\b(one|two|three|five|1|2|3|5)\b\s*(\(\d+\)\s*)?years?[^.]{0,80}(confidential\w*)[^.]{0,50}(expire|terminate|end)",
    ), category="Confidentiality"),

    Rule("standard_carveouts", "Standard carve-outs for public or independent info", 3, (
        r"(publicly available|public domain|independently developed|already known|rightfully (received|obtained))",
    ), category="Confidentiality"),
Rule("whistleblower_carveout", "Protects your right to report to regulators", 4, (
        r"(nothing in this|nothing herein)[^.]{0,140}(prohibit|prevent|restrict|limit)[^.]{0,110}(report|disclos|communicat)\w*[^.]{0,90}(government|agency|law enforcement|securities and exchange|commission|eeoc|nlrb|regulator)",
        r"defend trade secrets act", r"18 u\.?\s?s\.?\s?c\.?[^.]{0,20}1833",
    ), category="Tenant rights"),

    Rule("cure_period", "You get a chance to fix a problem before penalty", 4, (
        r"(right to cure|opportunity to cure|cure (the |such )?(default|breach|violation))",
        r"(cure|remedy)[^.]{0,60}within[^.]{0,30}\d+\s*(\(\d+\)\s*)?days?",
    ), category="Default"),

    Rule("rent_fixed_for_term", "Rent is fixed for the whole term", 3, (
        r"rent[^.]{0,110}(shall not (be )?(increase|change|be raised)|remain\w*\s+(fixed|unchanged|the same))[^.]{0,50}(during|for)[^.]{0,40}term",
    ), category="Rent"),

    Rule("liability_capped", "Liability is capped", 3, (
        r"(liability|damages)[^.]{0,110}(shall not exceed|is limited to|are limited to|capped at)",
    ), category="Liability"),

    Rule("mutual_termination_right", "Either side can end the agreement", 3, (
        r"either party may terminate",
    ), category="Termination"),

    Rule("prior_inventions_excluded", "Your existing work is carved out", 3, (
        r"(prior|pre-?existing|previously conceived)[^.]{0,60}(invention|work|intellectual property)[^.]{0,90}(exclud\w+|not (be )?assign\w+|listed|schedule)",
    ), category="Intellectual property"),
]


# ── Confidence / coverage ───────────────────────────────────────────────────────
# A score is only meaningful if the text was actually readable. Without this, a
# garbled or failed extraction matches no rules and scores as "Low risk", which is
# the most dangerous possible failure: telling someone an unreadable document is
# safe. Instead we check that the document's own core topics are present.

DOC_FAMILY: Dict[str, str] = {
    "Residential Lease": "lease",
    "Commercial Lease": "lease",
    "NDA": "nda",
    "Employment Contract": "employment",
    "Service Agreement": "generic",
    "Purchase Agreement": "generic",
    "Legal Document": "generic",
}

TOPIC_PROBES: Dict[str, List[Tuple[str, str]]] = {
    "lease": [
        ("parties",  r"\b(landlord|lessor|tenant|lessee|resident)\b"),
        ("rent",     r"\brent\b|\bmonthly (payment|installment)"),
        ("term",     r"\bterm\b|\bcommenc\w+|\blease (start|begin|end)|\bexpir\w+"),
        ("premises", r"\bpremises\b|\bapartment\b|\bdwelling\b|\bunit\b|\bproperty\b"),
        ("money",    r"\bdeposit\b|\bfee\b|\$\s*\d"),
    ],
    "nda": [
        ("parties",      r"\b(discloser|recipient|receiving party|disclosing party|parties)\b"),
        ("confidential", r"\bconfidential\w*\b|\bproprietary\b|\btrade secret"),
        ("obligation",   r"\bshall\b|\bagrees?\b|\bmust\b"),
        ("term",         r"\bterm\b|\bperiod\b|\bexpir\w+|\byears?\b"),
    ],
    "employment": [
        ("parties",      r"\b(employer|employee|company)\b"),
        ("role",         r"\bposition\b|\btitle\b|\bduties\b|\bemploym\w+"),
        ("compensation", r"\bsalary\b|\bwage\b|\bcompensation\b|\bpay\b"),
        ("term",         r"\bstart date\b|\bat-?will\b|\bterm\b|\bterminat\w+"),
    ],
    "generic": [
        ("parties",    r"\bpart(y|ies)\b|\bbetween\b"),
        ("obligation", r"\bshall\b|\bagrees?\b|\bmust\b"),
        ("term",       r"\bterm\b|\bdate\b|\beffective\b"),
        ("exchange",   r"\bpayment\b|\bfee\b|\bcompensation\b|\bconsideration\b"),
    ],
}

# Confidence must depend only on signals that are invariant to repetition,
# otherwise duplicated text changes the score. Raw word count is NOT invariant,
# so unique vocabulary is used instead, alongside topic coverage. Brevity alone
# is not a failed extraction: a short, fair NDA is still fully assessable.
MIN_UNIQUE_WORDS = 20
CAP_LOW_CONFIDENCE = 50    # cannot look safe when we could not read it
CAP_MEDIUM_CONFIDENCE = 85 # cannot claim the top band on thin coverage


def _family(doc_type: Optional[str]) -> str:
    return DOC_FAMILY.get(doc_type or "", "generic")


def assess_confidence(text: str, doc_type: Optional[str]) -> Tuple[str, str, int, int]:
    """
    How much to trust a score for this text.
    Returns (level, human reason, topics_found, topics_expected).
    """
    norm = normalize(text)
    unique_words = len({w.lower() for w in re.findall(r"[a-zA-Z]{2,}", norm)})
    probes = TOPIC_PROBES[_family(doc_type)]
    found = sum(1 for _name, pat in probes if re.search(pat, norm, re.I))
    total = len(probes)

    if unique_words < MIN_UNIQUE_WORDS or found <= 1:
        return (
            "low",
            "The text extracted from this document was too sparse to assess. "
            "It may be a scanned image or a PDF that did not read correctly.",
            found, total,
        )
    if found < (total + 1) // 2:
        return (
            "medium",
            f"Only {found} of the {total} sections normally found in this kind of "
            "document were detected, so the score may be incomplete.",
            found, total,
        )
    return ("high", "", found, total)


# ── Missing protections ─────────────────────────────────────────────────────────
# A reviewer notices what a document leaves out, not only what it says. These fire
# when an expected protection is absent. `requires` keeps them relevant: there is
# no missing deposit deadline if the document never mentions a deposit. They are
# only evaluated at high confidence, since otherwise "absent" just means unread.

@dataclass(frozen=True)
class AbsenceRule:
    id: str
    label: str
    weight: int
    families: Tuple[str, ...]
    protections: Tuple[str, ...]           # if none match, protection is missing
    requires: Tuple[str, ...] = ()         # only relevant if one of these matches
    category: str = ""

    def fires(self, text: str) -> bool:
        if self.requires and not any(re.search(p, text, re.I) for p in self.requires):
            return False
        return not any(re.search(p, text, re.I) for p in self.protections)


ABSENCE_RULES: List[AbsenceRule] = [
    AbsenceRule("missing_entry_notice", "No notice required before the landlord enters", HIGH,
        ("lease",),
        protections=(r"(hours?|days?)[^.]{0,70}notice[^.]{0,60}(enter|entry|access)",
                     r"(enter|entry|access)[^.]{0,80}(hours?|days?)[^.]{0,30}notice",),
        requires=(r"\benter\b|\bentry\b|\baccess\b",),
        category="Entry rights"),

    AbsenceRule("missing_deposit_deadline", "No deadline for returning your deposit", MEDIUM,
        ("lease",),
        protections=(r"deposit[^.]{0,140}(return|refund|remit)\w*[^.]{0,70}(within|by|no later)",
                     r"(within|no later than)[^.]{0,40}days?[^.]{0,90}deposit",),
        requires=(r"security deposit|\bdeposit\b",),
        category="Deposits"),

    AbsenceRule("missing_landlord_repairs", "Landlord never promises to make repairs", MEDIUM,
        ("lease",),
        protections=(r"(landlord|lessor|owner|management)[^.]{0,90}(shall|will|must|agrees to|is responsible)[^.]{0,60}(maintain|repair|habitable|good (repair|condition))",),
        requires=(r"\brepair\w*|\bmaintenan\w+|\bcondition\b",),
        category="Maintenance"),

    AbsenceRule("missing_nda_carveouts", "No carve-outs for public or independently known information", HIGH,
        ("nda",),
        protections=(r"(publicly available|public domain|independently developed|already known|rightfully (received|obtained)|becomes public)",),
        requires=(r"confidential\w*",),
        category="Confidentiality"),

    AbsenceRule("missing_confidentiality_term", "No time limit on confidentiality obligations", MEDIUM,
        ("nda",),
        protections=(r"confidential\w*[^.]{0,120}(expire|terminate|end|for a period|years?|months?)",
                     r"(years?|months?)[^.]{0,90}confidential\w*",),
        requires=(r"confidential\w*",),
        category="Confidentiality"),

    AbsenceRule("missing_whistleblower_carveout", "No protection for reporting to regulators", MEDIUM,
        ("nda", "employment"),
        protections=(r"(nothing in this|nothing herein)[^.]{0,140}(report|disclos|communicat)",
                     r"defend trade secrets act", r"(government|agency|law enforcement|regulator|commission)[^.]{0,80}(report|disclos)",),
        requires=(r"confidential\w*|non-?disclos\w+",),
        category="Tenant rights"),

    AbsenceRule("missing_prior_invention_carveout", "No carve-out for work you already owned", MEDIUM,
        ("employment", "nda"),
        protections=(r"(prior|pre-?existing|previously conceived)[^.]{0,70}(invention|work|intellectual property)",),
        requires=(r"assign\w*[^.]{0,120}(invention|intellectual property|work product)",),
        category="Intellectual property"),
]


# ── Compounding combinations ────────────────────────────────────────────────────
# Individually survivable terms can combine into a trap. A reviewer reads the
# interaction, not just the list.

@dataclass(frozen=True)
class ComboRule:
    id: str
    label: str
    weight: int
    requires: Tuple[str, ...]   # every one of these rule ids must have fired
    category: str = ""


COMBO_RULES: List[ComboRule] = [
    ComboRule("combo_renewal_trap", "Auto-renewal plus a long notice window is hard to escape",
              HIGH, ("auto_renew_long_notice", "notice_60_plus"), "Renewal"),
    ComboRule("combo_roommate_trap", "You owe the full rent but cannot replace a roommate",
              HIGH, ("joint_several", "no_sublet_absolute"), "Liability"),
    ComboRule("combo_no_recourse", "Forced arbitration plus paying their legal fees leaves no practical recourse",
              HIGH, ("mandatory_arbitration", "one_way_attorney_fees"), "Dispute resolution"),
    ComboRule("combo_locked_in", "Steep exit penalty with no way to sublet",
              HIGH, ("liquidated_damages", "no_sublet_absolute"), "Early termination"),
    ComboRule("combo_employment_asymmetry", "They can fire you at will while you stay bound by a non-compete",
              HIGH, ("noncompete_present", "unilateral_termination_no_notice"), "Non-compete"),
    ComboRule("combo_nda_overreach", "Perpetual confidentiality combined with broad IP assignment",
              HIGH, ("perpetual_obligations", "ip_assignment_broad"), "Confidentiality"),
    ComboRule("combo_deposit_squeeze", "Non-refundable fees on top of an oversized deposit",
              MEDIUM, ("nonrefundable_fees", "deposit_over_two_months"), "Deposits"),
]


# ── Quantitative severity ───────────────────────────────────────────────────────
# Magnitude matters. A $75 late fee and a $250,000 liquidated-damages clause are
# not the same risk, and a rule that only checks for the phrase cannot tell them
# apart.

_MONEY = r"\$\s*([\d,]+(?:\.\d{1,2})?)"

# Plausibility bounds. A figure outside these is almost certainly something else
# on the page (a purchase price, a phone number, an address) and is ignored
# rather than allowed to produce a nonsense ratio.
_BOUNDS = {
    "rent":     (100, 50_000),
    "deposit":  (50, 200_000),
    "late_fee": (5, 2_000),
}

# Directional and tightly bound: the amount must sit immediately beside its
# label. An earlier version scanned a +/-90 character window, which let the
# "$75" in "late fee of $75 applies if rent is unpaid" be read as the rent.
_AMOUNT_PATTERNS = {
    "rent": (
        r"(?:monthly rent|rent)\s*(?:of|is|shall be|will be|:|in the amount of)?\s*" + _MONEY,
        _MONEY + r"\s*(?:per|/|a)\s*month",
    ),
    "deposit": (
        r"(?:security deposit|deposit)\s*(?:of|is|shall be|equal to|:|in the amount of)?\s*" + _MONEY,
    ),
    "late_fee": (
        r"late\s*(?:fee|charge)\s*(?:of|is|shall be|:)?\s*" + _MONEY,
        _MONEY + r"\s*late\s*(?:fee|charge)",
    ),
}


def _amounts(text: str, kind: str) -> List[float]:
    """Plausible dollar amounts for one labelled quantity."""
    low, high = _BOUNDS[kind]
    found: List[float] = []
    for pattern in _AMOUNT_PATTERNS[kind]:
        for raw in re.findall(pattern, text, re.I):
            value = raw if isinstance(raw, str) else raw[0]
            try:
                amount = float(value.replace(",", ""))
            except ValueError:
                continue
            if low <= amount <= high:
                found.append(amount)
    return found


def _penalty_amounts(text: str) -> List[float]:
    """Fixed penalty sums, which must be stated near penalty language."""
    found: List[float] = []
    for pattern in (
        r"liquidated damages[^.]{0,60}?" + _MONEY,
        _MONEY + r"[^.]{0,40}?(?:liquidated damages|per occurrence)",
        r"penalty[^.]{0,40}?" + _MONEY,
    ):
        for raw in re.findall(pattern, text, re.I):
            value = raw if isinstance(raw, str) else raw[0]
            try:
                amount = float(value.replace(",", ""))
            except ValueError:
                continue
            if 100 <= amount <= 100_000_000:
                found.append(amount)
    return found


def numeric_findings(text: str, already: set) -> List[Tuple[str, str, int, str]]:
    """
    Graded findings derived from actual amounts. Magnitude matters: a $75 late fee
    and a $250,000 liquidated-damages clause are not the same risk, and a rule
    that only checks for the phrase cannot tell them apart.

    `already` holds the rule ids that fired, so a numeric check does not
    double-count what a phrase rule caught.
    """
    norm = normalize(text)
    out: List[Tuple[str, str, int, str]] = []

    rents = _amounts(norm, "rent")
    rent = max(rents) if rents else None

    # A deposit far above one month's rent ties up a lot of cash.
    deposits = _amounts(norm, "deposit")
    if rent and deposits and "deposit_over_two_months" not in already:
        ratio = max(deposits) / rent
        if ratio >= 2.5:
            out.append(("deposit_ratio_high", f"Deposit is about {ratio:.1f}x the monthly rent", HIGH, "Deposits"))
        elif ratio >= 1.6:
            out.append(("deposit_ratio_elevated", f"Deposit is about {ratio:.1f}x the monthly rent", MEDIUM, "Deposits"))

    # Late fees above roughly 5% of rent are challenged as punitive in many states.
    late = _amounts(norm, "late_fee")
    if rent and late:
        pct = max(late) / rent * 100
        if pct >= 10:
            out.append(("late_fee_steep", f"Late fee is about {pct:.0f}% of the monthly rent", MEDIUM, "Late fees"))
        elif pct >= 5:
            out.append(("late_fee_notable", f"Late fee is about {pct:.0f}% of the monthly rent", LOW, "Late fees"))

    # A large fixed penalty is a different order of risk from a nominal one.
    penalties = _penalty_amounts(norm)
    if penalties:
        biggest = max(penalties)
        if biggest >= 50_000:
            out.append(("penalty_very_large", f"Fixed penalty of ${biggest:,.0f}", CRITICAL, "Remedies"))
        elif biggest >= 10_000:
            out.append(("penalty_large", f"Fixed penalty of ${biggest:,.0f}", HIGH, "Remedies"))

    # Non-compete length drives both enforceability and real-world harm.
    match = re.search(r"non-?compet\w+[^.]{0,200}?(\d{1,2})\s*(month|year)", norm, re.I) or \
            re.search(r"(\d{1,2})\s*(month|year)s?[^.]{0,200}?non-?compet\w+", norm, re.I)
    if match:
        n = int(match.group(1))
        months = n * 12 if match.group(2).lower().startswith("year") else n
        if months >= 24:
            out.append(("noncompete_very_long", f"Non-compete runs {months} months", CRITICAL, "Non-compete"))
        elif months >= 12:
            out.append(("noncompete_long", f"Non-compete runs {months} months", HIGH, "Non-compete"))
    return out



GRADE_BANDS = [
    (85, "Low risk"),
    (70, "Moderate risk"),
    (55, "Elevated risk"),
    (45, "High risk"),
    (0,  "Severe risk"),
]


@dataclass
class DetectedRule:
    id: str
    label: str
    weight: int
    category: str
    severity: str


@dataclass
class ScoreResult:
    score: int
    grade: str
    penalty: int
    credits: int
    confidence: str = "high"       # high | medium | low
    confidence_note: str = ""      # shown to the reader when not high
    risks: List[DetectedRule] = field(default_factory=list)
    benefits: List[DetectedRule] = field(default_factory=list)


def normalize(text: str) -> str:
    """Collapse whitespace so provisions split across PDF line breaks still match."""
    return re.sub(r"\s+", " ", text or "")


def _dehyphenate(text: str) -> str:
    """Rejoin words broken by a hyphen at a line break, common in real PDFs."""
    return re.sub(r"(\w)-[ \t]*\r?\n[ \t]*(\w)", r"\1\2", text or "")


def _variants(text: str) -> Tuple[str, ...]:
    """
    Both normalizations of the text. Rejoining hyphenated line breaks recovers
    words like "indemnifi-\ncation", but blindly joining could break a genuine
    compound such as "month-to-month", so both forms are matched and unioned.
    """
    plain = normalize(text)
    joined = normalize(_dehyphenate(text))
    return (plain,) if plain == joined else (plain, joined)


def _ceiling(weights: List[int]) -> int:
    """Highest score a document with these findings is allowed to reach."""
    if any(w >= CRITICAL for w in weights):
        return CEILING_CRITICAL
    highs = sum(1 for w in weights if w >= HIGH)
    if highs >= MANY_HIGH_THRESHOLD:
        return CEILING_MANY_HIGH
    if highs >= 1:
        return CEILING_HIGH
    return 100


def _severity_name(weight: int) -> str:
    if weight >= CRITICAL:
        return "critical"
    if weight >= HIGH:
        return "high"
    if weight >= MEDIUM:
        return "medium"
    return "low"


def match_rules(text: str) -> Tuple[List[Rule], List[Rule]]:
    """Return (matched risk rules, matched credit rules) for a block of text."""
    forms = _variants(text)
    risks = [r for r in RISK_RULES if any(r.matches(f) for f in forms)]
    credits = [r for r in CREDIT_RULES if any(r.matches(f) for f in forms)]
    return risks, credits


def _grade_for(score: int) -> str:
    return next(label for cutoff, label in GRADE_BANDS if score >= cutoff)


def score_document(full_text: str, doc_type: Optional[str] = None) -> ScoreResult:
    """
    Compute the deterministic safety score for a whole document.

    Combines four signals, all derived only from the text:
      1. provisions present      (RISK_RULES / CREDIT_RULES)
      2. protections absent      (ABSENCE_RULES, only when confidence is high)
      3. magnitude of amounts    (numeric_findings)
      4. compounding combinations (COMBO_RULES)

    Scans the entire text, not just the clauses sent to the LLM, so risks buried
    in later sections still count. Findings are deduped by id, so a provision
    repeated in several clauses cannot move the score.
    """
    confidence, note, _found, _total = assess_confidence(full_text, doc_type)
    norm = normalize(full_text)

    risk_rules, credit_rules = match_rules(full_text)
    fired = {r.id for r in risk_rules}

    # (id, label, weight, category)
    findings: List[Tuple[str, str, int, str]] = [
        (r.id, r.label, r.weight, r.category) for r in risk_rules
    ]

    # Missing protections only count when we are confident we read the document.
    # Otherwise "absent" would really mean "not extracted".
    if confidence == "high":
        family = _family(doc_type)
        for rule in ABSENCE_RULES:
            if family in rule.families and rule.fires(norm):
                findings.append((rule.id, rule.label, rule.weight, rule.category))
                fired.add(rule.id)

    for nid, nlabel, nweight, ncat in numeric_findings(full_text, fired):
        findings.append((nid, nlabel, nweight, ncat))
        fired.add(nid)

    for combo in COMBO_RULES:
        if all(req in fired for req in combo.requires):
            findings.append((combo.id, combo.label, combo.weight, combo.category))

    penalty = sum(weight for _i, _l, weight, _c in findings)
    credits_applied = min(sum(r.weight for r in credit_rules), MAX_CREDITS)

    effective = max(0, penalty - credits_applied)
    base = 100.0 * K / (effective + K)
    ceiling = _ceiling([weight for _i, _l, weight, _c in findings])

    score = int(round(min(base, ceiling, MAX_SCORE)))
    score = max(1, min(100, score))

    # A score cannot claim safety we did not actually verify.
    if confidence == "low":
        score = min(score, CAP_LOW_CONFIDENCE)
        grade = "Not enough detail to score"
    else:
        if confidence == "medium":
            score = min(score, CAP_MEDIUM_CONFIDENCE)
        grade = _grade_for(score)

    risks = [
        DetectedRule(i, label, weight, cat, _severity_name(weight))
        for i, label, weight, cat in sorted(findings, key=lambda f: -f[2])
    ]
    benefits = [
        DetectedRule(r.id, r.label, r.weight, r.category, "favorable")
        for r in sorted(credit_rules, key=lambda r: -r.weight)
    ]

    return ScoreResult(
        score=score,
        grade=grade,
        penalty=penalty,
        credits=credits_applied,
        confidence=confidence,
        confidence_note=note,
        risks=risks,
        benefits=benefits,
    )


def classify_clause(text: str) -> Tuple[str, int]:
    """
    Deterministically classify a single clause.

    Returns (risk_level, risk_score) where risk_level is one of
    high / medium / standard / favorable and risk_score is 1-5.
    """
    risks, credits = match_rules(text)

    if not risks:
        return ("favorable", 1) if credits else ("standard", 2)

    worst = max(r.weight for r in risks)
    if worst >= CRITICAL:
        return "high", 5
    if worst >= HIGH:
        return "high", 4
    if worst >= MEDIUM:
        return "medium", 3
    return "standard", 2
