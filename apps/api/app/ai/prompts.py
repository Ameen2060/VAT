"""Prompts for extraction, VAT advisory, and chat.

The advisory/chat persona is the senior UAE VAT consultant. Guardrails are explicit:
cite legislation, defer to the deterministic rule engine for verdicts, and never
fabricate a citation or a Public Clarification number.
"""

from __future__ import annotations

# System persona shared by advisory + chat.
VAT_CONSULTANT_SYSTEM = """\
You are a Senior UAE VAT Compliance Consultant with 10+ years of experience in UAE \
VAT legislation and FTA compliance.

Authoritative sources, in priority order:
1. Federal Decree-Law No. 8 of 2017 (VAT) and amendments
2. Executive Regulation (Cabinet Decision No. 52 of 2017, as amended)
3. Cabinet Decisions
4. Ministerial Decisions
5. FTA Public Clarifications
6. Official FTA Guides
7. Other FTA publications

Hard rules:
- The deterministic rule engine's findings are authoritative for compliance \
verdicts. Explain and contextualise them; do not contradict them.
- Always cite the specific article when you assert a legal position.
- NEVER invent a citation, article number, or Public Clarification reference. If you \
are not certain a source exists, say so explicitly.
- If information needed for a conclusion is missing, state what is missing and ask \
for it rather than assuming.
- Be practical: give the accountant/auditor the corrective action, not just theory.
"""

# Extraction prompt. The model must return ONLY JSON matching the Invoice schema.
EXTRACTION_INSTRUCTION = """\
Extract the invoice into the provided JSON schema. Rules:
- Read all text, including scanned/handwritten content if this is an image or scan.
- Amounts are numbers (no currency symbols or thousands separators).
- vat_rate is a decimal fraction (5% -> 0.05, 0% -> 0).
- Set has_tax_invoice_label true only if the words "Tax Invoice" appear.
- Set has_reverse_charge_statement true only if a reverse-charge statement appears.
- Classify invoice_type, transaction_type and treatment when evident; otherwise use \
"unknown"/null. Do NOT guess a TRN — copy exactly what is printed, or null.
- If a field is not present on the document, use null. Do not fabricate values.
Return ONLY the JSON object, no prose.
"""


_GROUNDING = """\
Grounding rules (strict):
- Base your analysis ONLY on the DATA below (extracted fields, rule verdict, and the \
raw document text). Do not use outside facts about these specific parties or amounts.
- When you state a fact about the document, reference the actual extracted value \
(e.g. the invoice number, a TRN, or a total) so the reader can trace it.
- NEVER invent values, parties, dates, amounts, citations or clarification numbers. \
If something needed for a conclusion is absent from the DATA, say so explicitly and \
label it as missing/insufficient rather than guessing.
- Do not override the rule engine's status or risk; explain them.
"""


def advisory_user_prompt(invoice_json: str, review_json: str, source_text: str | None = None) -> str:
    src = (source_text or "").strip()
    src_block = (
        f"\nRAW DOCUMENT TEXT (OCR/extracted — the primary source):\n\"\"\"\n{src[:6000]}\n\"\"\"\n"
        if src
        else "\n(No raw document text was captured for this item.)\n"
    )
    return f"""\
{_GROUNDING}

DATA
====
STRUCTURED INVOICE (parsed fields):
{invoice_json}

RULE ENGINE REVIEW (authoritative verdict + findings):
{review_json}
{src_block}

TASK
====
Write a senior-consultant advisory, grounded strictly in the DATA above:
1. A short plain-English summary of the compliance position (reflect the engine's \
status and risk exactly — do not override them), naming the document by its actual \
invoice number and parties.
2. An explanation of each material finding and WHY it matters under UAE VAT law, \
with the specific article citation, referencing the actual value that triggered it.
3. Anomalies, inconsistencies or missing information you can see in the DATA \
(e.g. totals that don't reconcile, an invalid TRN, absent mandatory fields).
4. Practical corrective actions, ordered by priority.
5. Input VAT recoverability comment where relevant (supplier vs recipient).
6. Supporting documents the business should retain for an FTA audit.
If the DATA is insufficient to judge something, state that plainly.

Return ONLY JSON with keys: narrative (string), recommendations (string array), \
citations (string array of the legal references you actually relied on), \
confidence ("low"|"medium"|"high").
"""


def combined_analysis_prompt(documents_block: str) -> str:
    return f"""\
{_GROUNDING}
- Additionally: compare the documents against each other and surface cross-document \
issues (duplicate invoice numbers, inconsistent TRNs for the same party, VAT totals \
that don't add up across the set, mismatched currencies, etc.).

DATA — MULTIPLE DOCUMENTS
=========================
{documents_block}

TASK
====
Produce a portfolio-level VAT analysis grounded strictly in the DATA above:
1. An overview of the set (how many documents, types, total net/VAT/gross where \
determinable, currencies).
2. The most material compliance risks across the set, each tied to the specific \
document(s) and value(s) that raise it.
3. Cross-document inconsistencies or anomalies (name the documents involved).
4. Missing information that prevents a firm conclusion.
5. Prioritised recommended actions.

Return ONLY JSON with keys: narrative (string), recommendations (string array), \
citations (string array), confidence ("low"|"medium"|"high").
"""
