"""Dynamic system prompt assembly per PRD Section 10.1."""
import json
from langchain_core.documents import Document

ROLE_BLOCK = """You are AgroAdvisor AR, an expert agricultural advisory system specialized in
rice, soybean, and poultry production in Arkansas, United States. You respond
ONLY based on the provided document context. You do not generate information
not present in the retrieved documents."""

OUTPUT_INSTRUCTIONS_DIAG = """Respond in {language}. Return ONLY valid JSON matching the AdvisoryResponse schema.
Ensure response_type is "diagnostic".
Every claim must cite a specific retrieved document by its exact title (shown in [brackets]) and section. Do not invent or use numbered-document labels — cite the bracketed title text verbatim.
If context is insufficient to answer, set confidence to "Low" and explain why.
Never recommend products not mentioned in the retrieved documents.
Always include a warnings array — use an empty array if no warnings apply.
citations must contain at least one entry from the retrieved documents."""

OUTPUT_INSTRUCTIONS_INFO = """Respond in {language}. Return ONLY valid JSON matching the AdvisoryResponse schema.
Ensure response_type is "informational".
Provide a summary of the topic in problem_summary.
Provide a clear, detailed, educational explanation of the concepts in detailed_explanation (since this is an informational query, not a crop-health issue diagnosis).
Provide a list of key educational points or guidelines in key_points.
Since this query is informational/educational and not a crop-health diagnosis, leave likely_causes and products_rates empty ([]).
Every claim must cite a specific retrieved document by its exact title (shown in [brackets]) and section. Do not invent or use numbered-document labels — cite the bracketed title text verbatim.
If context is insufficient to answer, set confidence to "Low" and explain why.
Always include a warnings array — use an empty array if no warnings apply.
citations must contain at least one entry from the retrieved documents."""

OUTPUT_INSTRUCTIONS = OUTPUT_INSTRUCTIONS_DIAG

SAFETY_OVERRIDE = """SAFETY OVERRIDE — ALWAYS APPLY:
If the query involves pesticide mixing, chemical safety, overdose, or regulatory
compliance, prepend a safety warning to the warnings array regardless of other content:
"WARNING: Chemical handling errors can cause serious injury. Consult product label and
your county extension agent before mixing or applying any pesticide." """

OUT_OF_SCOPE_MESSAGE = (
    "AgroAdvisor AR is specialized for rice, soybean, and poultry questions in Arkansas. "
    "For general questions, please use a general-purpose assistant."
)

OUT_OF_SCOPE_MESSAGE_ES = (
    "AgroAdvisor AR está especializado en preguntas sobre arroz, soya y aves de "
    "corral en Arkansas. Para preguntas generales, utilice un asistente de "
    "propósito general."
)


def out_of_scope_message(language: str) -> str:
    """Out-of-scope reply in the user's language (static — no LLM call)."""
    return OUT_OF_SCOPE_MESSAGE_ES if language == "es" else OUT_OF_SCOPE_MESSAGE


def build_system_prompt(
    *,
    soil_context: dict,
    weather_context: dict,
    retrieved_docs: list[Document],
    session_history: list[dict],
    language: str,
    is_safety_critical: bool,
    county_name: str,
    awd_context: str | None = None,
    intent: str = "diagnostic",
) -> str:
    parts = [ROLE_BLOCK, ""]

    # Local conditions block
    if soil_context.get("available") or weather_context.get("available"):
        parts.append(f"[LOCAL CONDITIONS — {county_name.upper()}, ARKANSAS]")
        if soil_context.get("available"):
            parts.append("SOIL: " + json.dumps(soil_context, indent=None))
        if weather_context.get("available"):
            parts.append("WEATHER: " + json.dumps(weather_context, indent=None))
        parts.append("")

    # AWD irrigation context (rice queries only)
    if awd_context:
        parts.append(awd_context)
        parts.append("")

    # Retrieved document context. The header is intentionally NOT wrapped in [brackets]
    # so the model can't mistake it for a citable title.
    if retrieved_docs:
        parts.append("=== RETRIEVED CONTEXT (cite each passage by its [bracketed] title) ===")
        for i, doc in enumerate(retrieved_docs, 1):
            meta = doc.metadata
            title = meta.get("document_title") or ""
            section = meta.get("section_heading", "")
            label = f"{title} — {section}".strip(" —")
            if not label:
                # Titleless gte index stores only {text, namespace}. Give a stable,
                # citable handle rather than "[Unknown]", which the model echoes verbatim.
                label = f"Arkansas Extension source {i}"
            parts.append(f"[{label}] {doc.page_content}")
        parts.append("")

    # Conversation history
    if session_history:
        parts.append("[CONVERSATION HISTORY]")
        for exchange in session_history[-10:]:
            role = exchange.get("role", "user")
            content = exchange.get("content", "")
            parts.append(f"{role.upper()}: {content}")
        parts.append("")

    # Output instructions
    parts.append("[OUTPUT INSTRUCTIONS]")
    if intent == "informational":
        parts.append(OUTPUT_INSTRUCTIONS_INFO.format(language=language))
    else:
        parts.append(OUTPUT_INSTRUCTIONS_DIAG.format(language=language))

    if is_safety_critical:
        parts.append("")
        parts.append(SAFETY_OVERRIDE)

    return "\n".join(parts)
