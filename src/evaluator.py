from groq import Groq
from dotenv import load_dotenv
import os
import json
from retriever import search_by_category, list_risk_categories

load_dotenv()
client = Groq(api_key=os.getenv("GROQ_API_KEY"))

MODEL_NAME = "openai/gpt-oss-120b"


def _get_language_instruction(language):
    return "in Arabic" if language == "Arabic" else "in English"


def _parse_json_response(raw_text):
    try:
        return json.loads(raw_text)
    except json.JSONDecodeError:
        start = raw_text.find("{")
        end = raw_text.rfind("}") + 1
        return json.loads(raw_text[start:end])


def _call_llm(prompt):
    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[{"role": "user", "content": prompt}],
        temperature=0
    )
    return response.choices[0].message.content


# ============================================================
# RISK ENGINE — مستقل تمامًا عن الـ Compliance Engine (Invariant 4)
# ============================================================

def _severity_from_score(likelihood, impact):
    score = likelihood * impact
    if score <= 4:
        return "Low"
    elif score <= 9:
        return "Medium"
    elif score <= 19:
        return "High"
    else:
        return "Critical"


# ============================================================
# COMPLIANCE ENGINE — مستقل تمامًا عن الـ Risk Engine (Invariant 1)
# ============================================================

_COMPLIANCE_PRIORITY = {"Non-Compliant": 2, "Evidence Required": 1, "Compliant": 0}


def _compliance_from_evidence(entry):
    """
    Evidence Status (3 حالات فقط) → Compliance Status.
    Invariant 2: REQUIRED (بما فيها غياب الدليل) لا يساوي Non-Compliant أبدًا.
    Invariant 3: CONTRADICTED دايمًا Non-Compliant.
    """
    status = entry.get("evidence_status")
    if status == "Contradicted":
        return "Non-Compliant"
    if status == "Confirmed":
        outcome = entry.get("confirmed_outcome")
        return "Non-Compliant" if outcome == "Non-Compliant" else "Compliant"
    return "Evidence Required"


def _aggregate_compliance(compliance_statuses):
    """
    Invariant 5: كل Finding ياخد Compliance Status واحد بس، عن طريق
    worst-case aggregation صريح (مش average ولا أول عنصر).
    """
    if not compliance_statuses:
        return "Compliant"
    return max(compliance_statuses, key=lambda s: _COMPLIANCE_PRIORITY.get(s, 0))


def _identify_risks(input_text):
    categories = list_risk_categories()
    prompt = f"""You are a risk classifier for an AI Governance audit system.

Available risk categories (choose ONLY from this exact list, do not invent new ones):
{json.dumps(categories, indent=2)}

Text to analyze:
\"\"\"{input_text}\"\"\"

Identify which of the above risk categories are ACTUALLY present in the text,
based only on evidence in the text itself. If none apply, return an empty list.

CRITICAL RULE: Do not select "sensitive_data_exposure" merely because personal or
sensitive data is mentioned as being processed. That alone belongs under
"privacy_data_protection" or "data_governance_minimization" instead.
Only select "sensitive_data_exposure" if the text gives explicit evidence of actual
leakage, unauthorized disclosure/access, insecure transmission/storage, or excessive
exposure to a third party/model/tool - not merely that sensitive data exists.

Respond ONLY with a valid JSON object in this exact format:
{{
  "risk_categories": ["category_1", "category_2"]
}}

Do not include any text before or after the JSON object.
"""
    raw = _call_llm(prompt)
    parsed = _parse_json_response(raw)
    found = parsed.get("risk_categories", [])
    return [c for c in found if c in categories]


def _evaluate_single_risk(category, input_text, language_instruction, policy_name=None):
    chunks_with_pages, matched_policy_source = search_by_category(category, n_results=3, policy_name=policy_name)

    if chunks_with_pages:
        context = "\n\n---\n\n".join(
            f"[Source: {c.get('policy', 'Unknown')}, page {c.get('page', '?')}]\n{c['text']}"
            for c in chunks_with_pages
        )
        available_sources = sorted(set(c.get("policy") for c in chunks_with_pages if c.get("policy")))
    else:
        context = "No relevant policy excerpts were retrieved."
        available_sources = []

    prompt = f"""You are a Responsible AI policy auditor. You are evaluating ONE specific
risk category: "{category}".

Policy excerpts retrieved for this category, each labeled with its source policy and page:
{context}

Available source policies in the excerpts above: {available_sources if available_sources else "none"}

Text under review:
\"\"\"{input_text}\"\"\"

=== TWO COMPLETELY INDEPENDENT ASSESSMENTS ===

You must produce TWO SEPARATE assessments for the category overall, and they must
NEVER influence each other:

A) RISK ASSESSMENT (likelihood/impact) - answers "how bad would this be if it happened?"
B) COMPLIANCE ASSESSMENT (per policy_violations entry) - answers "does the evidence
   actually confirm a requirement was met or violated?"

A high risk score does NOT mean the category is non-compliant, and a low risk score
does NOT mean it is compliant. These are answered by completely different questions
and must never be conflated.

=== RULES FOR policy_violations ENTRIES (Compliance Assessment) ===

1. Identify each DISTINCT policy consideration as its own entry (different source
   policies, or genuinely different specific obligations within the same source).

2. Each entry has exactly ONE source policy that specifically supports it.

3. For each entry, set "evidence_status" to exactly ONE of these three values:
   - "Confirmed": the text EXPLICITLY states whether the specific control/requirement
     is met or not met (e.g. "Human oversight on decisions: No" explicitly confirms
     the control is ABSENT; "Human oversight: reviews every decision" explicitly
     confirms it IS present). When "Confirmed", you MUST also set "confirmed_outcome"
     to "Compliant" (requirement is met) or "Non-Compliant" (requirement is violated).
   - "Required": the text does not explicitly confirm either way - including when the
     text simply never mentions this control at all, or only mentions a generic
     adjacent fact (e.g. "contains personal data" does not confirm whether consent
     or purpose limitation specifically was handled). This is the correct status for
     genuine uncertainty - it is NOT a violation.
   - "Contradicted": the text explicitly describes behavior that directly conflicts
     with or undermines the requirement in a way that goes beyond simple absence
     (use sparingly - most "absent control" cases are "Confirmed"+"Non-Compliant",
     not "Contradicted"; reserve "Contradicted" for cases where the text describes
     an active practice that directly defeats the requirement's purpose).

4. CRITICAL - ABSENCE OF INFORMATION IS "Required", NEVER "Confirmed"/"Non-Compliant":
   if the text simply doesn't mention a safeguard, that is unknown, not proof it is
   missing - unless the input explicitly says "No" or similar for that specific
   control (which makes it "Confirmed"/"Non-Compliant" per rule 3).

5. CRITICAL - EVIDENCE MUST BE SEMANTICALLY SPECIFIC TO THE NAMED OBLIGATION:
   - "Data source: In-house" is NOT evidence about leakage, encryption, or access
     control.
   - "Contains sensitive data: Yes" or "Contains personal data: Yes" alone is NOT
     evidence that any specific safeguard (consent, minimization, transparency) is
     present or absent - it only confirms the data category exists.
   - If your only "evidence" for an entry is such a generic fact, either mark it
     "Required" (not Confirmed) or, if it does not specifically speak to a named
     obligation at all, do not create that entry.

6. Do NOT duplicate the same generic fact across multiple entries to inflate the
   violation count. If two considerations would only be supported by the exact same
   generic fact, merge them into ONE broader entry instead.
   
6b. A DERIVED or SECONDARY field (e.g. a "type" or "category" sub-field that is
    automatically empty/N/A whenever a related primary field is "No") is NOT
    independent evidence on its own. If your evidence for an entry is only such
    a secondary field (e.g. "Human oversight type: N/A"), do not create a separate
    "Confirmed" entry for it - it does not add new information beyond the primary
    field it derives from. Only the primary field (e.g. "Human oversight on
    decisions: No") counts as standalone Confirmed evidence.

6c. When the SAME primary fact (e.g. "Human oversight on decisions: No") would
    support a "Confirmed" entry under more than one framework, mark AT MOST the
    ONE most directly applicable source as "Confirmed"/"Non-Compliant". Mark the
    same fact under any additional frameworks as "Required" instead, noting in
    the recommendation that formal applicability assessment is needed for those
    frameworks specifically.
7. Only include an entry if it is supported by a specific excerpt above. If no
   excerpt supports any entry, return an empty "policy_violations" list.

8. Each entry's "evidence" must be exact short phrase(s) copied VERBATIM from the
   TEXT UNDER REVIEW. Do not translate, do not invent evidence not in the text.

9. If you name a specific source policy in "justification", that policy MUST also
   appear as its own entry in "policy_violations".

10. SPECIFIC GUIDANCE for commonly-misapplied areas:
    - Human oversight (GDPR Article 22 / EU AI Act): a solely-automated decision with
      NO described human involvement at all ("Human oversight on decisions: No") is
      "Confirmed"/"Non-Compliant". But if the text describes SOME human involvement
      (e.g. "escalation-only review", "sample review"), the adequacy is NOT
      determinable from this alone (can the human actually intervene? at what
      stage?) - mark this "Required", not "Confirmed".
    - Consent/lawful basis (GDPR): never assume consent is the only valid lawful
      basis. Frame around "lawful basis not documented" rather than "consent
      missing" unless the text specifically discusses consent.

=== RULES FOR RISK ASSESSMENT (independent of compliance) ===

11. Rate "likelihood" and "impact" each from 1 (lowest) to 5 (highest), based purely
    on how likely/severe the described situation is - regardless of how many entries
    are "Confirmed" vs "Required". A category can be high-risk in principle even
    while specific evidence remains uncertain, and can be lower-risk even with a
    confirmed gap, if the described consequences are minor. Do NOT mechanically tie
    these numbers to the compliance entries above - assess them on their own terms
    based on the real-world stakes described in the text.
    Do NOT output a severity label yourself - only output the two numeric ratings.

12. Set "has_controls" to true if the text explicitly describes safeguards already
    in place for this category, regardless of the compliance entries above.

=== JUSTIFICATION AND RECOMMENDATION ===

13. "justification" must be a SHORT (2-4 sentences) explanation of the overall risk
    picture for this category. Do not restate every policy_violations entry in prose.

14. "recommendation" must be 2-5 short, separate action items (one per line), never
    assuming a single legal mechanism (like consent) is the only valid path.

15. Language rules: "category", "policy", "source", "evidence_status",
    "confirmed_outcome" stay as-is (do not translate). "evidence" is verbatim from
    the text under review (do not translate). "justification" and "recommendation"
    ONLY are written {language_instruction}, in formal gender-neutral professional
    tone when Arabic (no colloquial dialect, no gender-specific imperatives).

Respond ONLY with a valid JSON object in this exact format:
{{
  "category": "{category}",
  "policy_violations": [
    {{
      "policy": "short policy/principle name reflecting the SPECIFIC obligation",
      "source": "single source label from the available list",
      "page": 1,
      "evidence_status": "Confirmed or Required or Contradicted",
      "confirmed_outcome": "Compliant or Non-Compliant (ONLY when evidence_status is Confirmed, otherwise null)",
      "evidence": ["exact phrase from text under review"]
    }}
  ],
  "likelihood": 1,
  "impact": 1,
  "has_controls": false,
  "justification": "short overall risk summary (2-4 sentences)",
  "recommendation": "2-5 short action items, one per line"
}}

Do not include any text before or after the JSON object.
"""
    raw = _call_llm(prompt)
    result = _parse_json_response(raw)

    likelihood = int(result.get("likelihood", 1))
    impact = int(result.get("impact", 1))
    likelihood = max(1, min(5, likelihood))
    impact = max(1, min(5, impact))

    violations = result.get("policy_violations", [])
    if not isinstance(violations, list):
        violations = []

    for v in violations:
        if v.get("evidence_status") not in ("Confirmed", "Required", "Contradicted"):
            v["evidence_status"] = "Required"
        if v.get("evidence_status") != "Confirmed":
            v["confirmed_outcome"] = None
        elif v.get("confirmed_outcome") not in ("Compliant", "Non-Compliant"):
            v["confirmed_outcome"] = "Non-Compliant"
        # الـ Compliance Status لكل Violation محسوبة بالكود، مش رأي الموديل
        v["compliance_status"] = _compliance_from_evidence(v)

    result["category"] = category
    result["policy_violations"] = violations
    result["likelihood"] = likelihood
    result["impact"] = impact
    result["risk_score"] = likelihood * impact
    result["severity"] = _severity_from_score(likelihood, impact)
    result["has_controls"] = bool(result.get("has_controls", False))

    # Finding-level Compliance Status: worst-case aggregation من كل الـ violations
    # (Invariant 5) - مستقل تمامًا عن الـ severity/risk_score (Invariant 1 و4)
    result["compliance_status"] = _aggregate_compliance(
        [v["compliance_status"] for v in violations]
    )
    return result


_SEVERITY_ORDER = {"None": 0, "Low": 1, "Medium": 2, "High": 3, "Critical": 4}


def _run_full_evaluation(input_text, language="Arabic"):
    language_instruction = _get_language_instruction(language)

    risk_categories = _identify_risks(input_text)

    if not risk_categories:
        return {
            "decision": "Compliant",
            "risk_level": "Low",
            "findings": [],
            "summary_justification": (
                "لم يتم رصد أي فئة خطر واضحة في المحتوى المُدخل بناءً على التصنيفات المتاحة."
                if language == "Arabic" else
                "No clear risk category was detected in the provided content based on the available taxonomy."
            ),
            "summary_recommendation": (
                "لا يوجد إجراء مطلوب حاليًا. يُنصح بالمراجعة الدورية العادية."
                if language == "Arabic" else
                "No action required at this time. Routine periodic review is recommended."
            ),
        }

    HIGH_STAKES_CATEGORIES = {"violence_harmful_content", "self_harm_content"}

    findings = []
    dismissed_high_stakes = []
    for category in risk_categories:
        finding = _evaluate_single_risk(category, input_text, language_instruction)
        if finding.get("severity", "None") != "None" and finding.get("risk_score", 0) > 1:
            findings.append(finding)
        elif category in HIGH_STAKES_CATEGORIES:
            dismissed_high_stakes.append(category)

    if not findings and dismissed_high_stakes:
        overall_decision = "Needs Review"
        overall_risk = "Low"
    elif not findings:
        overall_decision = "Compliant"
        overall_risk = "Low"
    else:
        # Decision (Compliance Engine) - worst-case aggregation عبر كل الـ Findings،
        # مستقل تمامًا عن الـ Risk Level (Invariant 1)
        overall_compliance = _aggregate_compliance([f["compliance_status"] for f in findings])
        decision_map = {
            "Non-Compliant": "Violation",
            "Evidence Required": "Needs Review",
            "Compliant": "Compliant",
        }
        overall_decision = decision_map[overall_compliance]

        # Risk Level (Risk Engine) - محسوب بشكل مستقل تمامًا (Invariant 4)
        max_finding = max(findings, key=lambda f: _SEVERITY_ORDER.get(f.get("severity", "None"), 0))
        overall_risk = max_finding.get("severity", "Medium")

    total_violations = sum(len(f.get("policy_violations", [])) for f in findings)
    total_confirmed_noncompliant = sum(
        1 for f in findings for v in f.get("policy_violations", [])
        if v.get("compliance_status") == "Non-Compliant"
    )

    return {
        "decision": overall_decision,
        "risk_level": overall_risk,
        "findings": findings,
        "summary_justification": (
            f"تم رصد {len(findings)} نتيجة (finding) بإجمالي {total_violations} ملاحظة سياسة ({total_confirmed_noncompliant} مخالفة مؤكدة)، عبر الفئات التالية: "
            + ", ".join(f['category'] for f in findings)
            if language == "Arabic" else
            f"{len(findings)} finding(s) identified with {total_violations} policy assessments ({total_confirmed_noncompliant} confirmed non-compliant), across categories: "
            + ", ".join(f['category'] for f in findings)
        ) if findings else "",
        "summary_recommendation": (
            "راجعي كل finding على حدة واتخذي قرارًا بشريًا موثقًا (قبول/رفض/تصعيد) لكل واحد."
            if language == "Arabic" else
            "Review each finding individually and record a documented human decision (accept/reject/escalate) for each."
        ) if findings else "",
    }


def evaluate_content(content, content_type="AI Response", reason="Routine review", policy_name=None, language="Arabic"):
    input_text = f"[Content type: {content_type}] [Reason: {reason}]\n{content}"
    return _run_full_evaluation(input_text, language=language)


def evaluate_system(system_name, use_case, data_used, automated_decision, human_oversight, policy_name=None, language="Arabic"):
    description = f"""System Name: {system_name}
Use Case: {use_case}
Data Used: {data_used}
Makes automated decisions affecting users: {automated_decision}
Human oversight on decisions: {human_oversight}"""
    return _run_full_evaluation(description, language=language)


if __name__ == "__main__":
    loan_scenario = """System Name: Automated Loan Approval System
Use Case: Approves or rejects loan applications automatically based on income, credit history, and employment status
Data Used: Income, credit history, employment status
Makes automated decisions affecting users: Yes
Human oversight on decisions: No"""

    result = evaluate_content(
        content=loan_scenario,
        content_type="System Description",
        reason="Diagnostic test",
        language="English"
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))