"""Core RAG chain: retrieve → inject context → Gemini structured output."""
import asyncio
import logging
import re
import time
from datetime import date as _date
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_pinecone import PineconeVectorStore
from pinecone import Pinecone
from models.advisory import AdvisoryDraft, AdvisoryResponse
from services.embedding import MiniLMEmbeddings
from services.context import get_context
from services.classifier import CATEGORY_TO_NAMESPACE
from utils.crops import CROP_NAMESPACES
from services import citation_guard_v2
from utils.prompt import build_system_prompt
from utils.counties import get_county_info
from utils.llm import _is_quota_error
import config

logger = logging.getLogger(__name__)

# Minimum spacing between partial-draft SSE frames. JsonOutputParser re-emits the
# FULL cumulative draft dict on every update, so an unthrottled stream re-sends
# hundreds of KB and forces a React re-render per token. One frame per quarter
# second keeps the progressive-typing UX without the O(n²) payload (F7).
PARTIAL_STREAM_THROTTLE_SECONDS = 0.25


async def _emit(progress, stage, **data):
    """Put a progress stage dict onto the queue when one is provided; no-op
    otherwise. Lets run_rag_query report stage transitions to the SSE stream
    without coupling to the router."""
    if progress is not None:
        await progress.put({"stage": stage, **data})


async def _astream_draft(
    llm,
    messages: list,
    run_config: dict | None,
    on_partial,
    prepend_format_instructions: bool = False,
) -> dict | None:
    """Stream partial JSON dicts from an LLM via JsonOutputParser.

    Pipes ``llm | JsonOutputParser()`` and iterates over partial dicts as
    LangChain incrementally assembles JSON tokens into objects.  For each
    non-empty partial dict, ``await on_partial(partial_dict)`` is called so
    the caller can forward progressive updates to the SSE stream.

    Args:
        llm: Any LangChain chat model that supports ``.astream()``.
        messages: The message list to send.
        run_config: Optional LangChain run config (tracing, callbacks, …).
        on_partial: Async callable invoked with each non-empty partial dict.
        prepend_format_instructions: When True (DeepInfra / json_mode
            providers), prepend ``PydanticOutputParser`` format instructions
            to the first ``SystemMessage`` so the model knows the expected
            JSON schema.

    Returns:
        The last (most complete) dict yielded, or ``None`` if the stream
        produced no valid JSON.
    """
    from langchain_core.output_parsers import JsonOutputParser
    from langchain_core.output_parsers import PydanticOutputParser
    from langchain_core.messages import SystemMessage as _SystemMessage

    effective_messages = messages
    if prepend_format_instructions:
        fmt = PydanticOutputParser(pydantic_object=AdvisoryDraft).get_format_instructions()
        effective_messages = []
        prepended = False
        for msg in messages:
            if not prepended and isinstance(msg, _SystemMessage):
                effective_messages.append(_SystemMessage(content=fmt + "\n\n" + msg.content))
                prepended = True
            else:
                effective_messages.append(msg)
        if not prepended:
            # No system message found — prepend a new one
            effective_messages = [_SystemMessage(content=fmt)] + effective_messages

    chain = llm | JsonOutputParser()
    last: dict | None = None
    async for partial in chain.astream(effective_messages, config=run_config):
        if not partial:
            continue
        last = partial
        await on_partial(partial)
    return last


# The prompt numbers retrieved chunks as "Document N: <title> | ...". The LLM
# echoes that scaffolding into citation titles and prose, which (a) broke exact
# title-matching so confidence was forced Low even for grounded answers, and
# (b) spawned un-entailable meta-claims ("Document 2 is related to ...") during
# NLI decomposition. Strip it before matching/verifying.
_DOC_PREFIX_RE = re.compile(r"\bDocument\s+\d+\s*:?\s*", re.IGNORECASE)


def _strip_doc_prefix(text: str) -> str:
    """Remove "Document N:" scaffolding the LLM copies from the prompt context."""
    return _DOC_PREFIX_RE.sub("", text or "").strip()


_PLACEHOLDER_RE = re.compile(r"\[?\s*RETRIEVED DOCUMENT CONTEXT\s*\]?", re.IGNORECASE)


def _strip_scaffolding(text: str) -> str:
    """Remove prompt scaffolding the LLM copies verbatim: 'Document N:' prefixes and
    the '[RETRIEVED DOCUMENT CONTEXT]' context header."""
    return _PLACEHOLDER_RE.sub("", _DOC_PREFIX_RE.sub("", text or "")).strip()


_vectorstore: PineconeVectorStore | None = None
_llm: ChatGoogleGenerativeAI | None = None
_groq_llm = None
_groq_fast_llm = None
_deepinfra_llm = None


def _get_groq_llm():
    global _groq_llm
    if _groq_llm is None and config.GROQ_API_KEY:
        from langchain_groq import ChatGroq
        _groq_llm = ChatGroq(
            model=config.GROQ_PRIMARY_MODEL,
            api_key=config.GROQ_API_KEY,
            temperature=0.1,
        )
    return _groq_llm


def _get_groq_fast_llm():
    """8b-instant — far higher free tokens-per-day than 70b. Generation fallback
    when 70b hits its TPD cap, so the free tier survives pilot load."""
    global _groq_fast_llm
    if _groq_fast_llm is None and config.GROQ_API_KEY:
        from langchain_groq import ChatGroq
        _groq_fast_llm = ChatGroq(
            model=config.GROQ_FAST_MODEL,
            api_key=config.GROQ_API_KEY,
            temperature=0.1,
        )
    return _groq_fast_llm


def _get_deepinfra_llm():
    global _deepinfra_llm
    if _deepinfra_llm is None and config.DEEPINFRA_API_KEY:
        from langchain_openai import ChatOpenAI
        _deepinfra_llm = ChatOpenAI(
            model=config.DEEPINFRA_MODEL,
            openai_api_key=config.DEEPINFRA_API_KEY,
            openai_api_base="https://api.deepinfra.com/v1",
            temperature=0.1,
        )
    return _deepinfra_llm


def _get_vectorstore() -> PineconeVectorStore:
    global _vectorstore
    if _vectorstore is None:
        pc = Pinecone(api_key=config.PINECONE_API_KEY)
        index = pc.Index(config.PINECONE_INDEX_NAME)
        _vectorstore = PineconeVectorStore(
            index=index,
            embedding=MiniLMEmbeddings(),
            text_key="text",
        )
    return _vectorstore


def _get_llm() -> ChatGoogleGenerativeAI:
    global _llm
    if _llm is None:
        _llm = ChatGoogleGenerativeAI(
            model=config.GEMINI_PRIMARY_MODEL,
            google_api_key=config.GOOGLE_API_KEY,
            temperature=0.1,
        )
    return _llm


def _namespaces_for(category: str) -> list[str]:
    """Pinecone namespaces to search for a classifier category.

    A specific crop → its single namespace. IN_SCOPE_GENERAL_AG maps to None in
    CATEGORY_TO_NAMESPACE; the corpus has no `general`/default namespace (all
    20k vectors live under rice/soybeans/poultry), so a general-ag query must
    fan out across every crop namespace. Previously None meant "pass no namespace",
    which made Pinecone search the empty default namespace → zero docs → every
    general-ag answer suppressed.
    """
    # Support categories with or without DIAG/INFO suffix
    clean_cat = category.split(":", 1)[0] if ":" in category else category
    ns = CATEGORY_TO_NAMESPACE.get(category) or CATEGORY_TO_NAMESPACE.get(clean_cat + ":DIAG")
    return [ns] if ns else list(CROP_NAMESPACES.values())


def _fanout_search(vectorstore, query: str, k: int, namespaces: list[str]) -> list:
    """Retrieve top-k across one or more namespaces, merged by similarity score.

    Pinecone queries a single namespace per call, so multi-namespace retrieval
    means querying each, then merging by descending cosine score and trimming to k.
    """
    scored: list = []
    for ns in namespaces:
        scored.extend(vectorstore.similarity_search_with_score(query, k=k, namespace=ns))
    scored.sort(key=lambda doc_score: doc_score[1], reverse=True)
    return [doc for doc, _ in scored[:k]]


def _advisory_to_verifiable_text(result: AdvisoryResponse) -> str:
    """Concatenate the SUBSTANTIVE factual claims for NLI grounding.

    Excludes `warnings` on purpose: they are generic safety boilerplate ("consult
    a professional", "follow label directions") that rarely entails from an
    extension passage. Including them (added during F1) tanked the grounding
    score and caused good answers to be suppressed.
    """
    parts: list[str] = [result.problem_summary]
    if result.detailed_explanation:
        parts.append(result.detailed_explanation)
    if result.key_points:
        parts.extend(result.key_points)
    parts.extend(
        f"{cause.cause}: {cause.explanation}" for cause in result.likely_causes
    )
    parts.extend(result.recommended_actions)
    parts.extend(
        " ".join(filter(None, [
            product.product,
            product.rate,
            product.application_method,
            product.pre_harvest_interval,
        ]))
        for product in result.products_rates
    )
    # Strip prompt scaffolding so decomposition verifies real content,
    # not meta-claims about document numbering or context headers.
    return _strip_scaffolding(" ".join(p for p in parts if p))


async def _postprocess_async(
    result: AdvisoryDraft | AdvisoryResponse,
    docs: list,
    soil: dict,
    weather: dict,
    county_fips: str,
    run_config: dict | None = None,
    category: str | None = None,
) -> AdvisoryResponse:
    """Apply citation guard (title-match + NLI) and stamp context_meta.

    Accepts the LLM-authored AdvisoryDraft and promotes it to a full
    AdvisoryResponse (guard fields default None until filled below)."""
    if not isinstance(result, AdvisoryResponse):
        result = AdvisoryResponse(**result.model_dump())
    # B1: the analysis scratchpad is internal reasoning workspace — strip it
    # before the guard scores prose and before anything is stored or streamed.
    if result.analysis is not None:
        result = result.model_copy(update={"analysis": None})
    # Step 1: title-match citation guard.
    # Only meaningful when retrieval carries `document_title` metadata. Legacy
    # gte indexes stored only {text, namespace}, so this guard would validate no
    # citation there and force every grounded answer to Low. When no retrieved
    # doc carries a title, skip the title guard entirely and let the NLI
    # confidence_score (Step 3) govern.
    # Run the title-match guard only when the retrieval set RELIABLY carries
    # titles (every doc), not when a single stray titled doc appears among
    # titleless gte results — `any()` there forced a false "Low" on answers
    # actually grounded by the titleless docs (F12). `all()` defers to the NLI
    # score in mixed/titleless cases and activates once gte is re-ingested with
    # titles on every chunk.
    titles_present = bool(docs) and all(doc.metadata.get("document_title") for doc in docs)
    if titles_present:
        retrieved_titles = {
            doc.metadata.get("document_title", "").lower() for doc in docs
        }
        # Strip the "Document N:" prefix the LLM copies from the prompt so a
        # grounded citation actually matches the retrieved title. Store the
        # normalized title back on the kept citation.
        valid_citations = []
        for c in result.citations:
            clean_title = _strip_doc_prefix(c.document_title)
            if clean_title.lower() in retrieved_titles:
                valid_citations.append(c.model_copy(update={"document_title": clean_title}))
        if not valid_citations:
            result = result.model_copy(update={"confidence": "Low"})
        else:
            result = result.model_copy(update={"citations": valid_citations})

    # Step 2: stamp context_meta
    result = result.model_copy(update={
        "context_meta": result.context_meta.model_copy(update={
            "soil_data_available": soil.get("available", False),
            "weather_data_available": weather.get("available", False),
            "county_fips": county_fips,
        })
    })

    # Step 2b: scrub residual "Document N:" from user-facing fields. The LLM
    # echoes the prompt's chunk scaffolding into citation titles and prose even
    # after the Phase 5 prompt fix; the title-match branch above only normalizes
    # titles when `titles_present`. Run this ALWAYS (titleless gte index too) so
    # users never see "Document N:" in the returned advisory.
    result = result.model_copy(update={
        "problem_summary": _strip_scaffolding(result.problem_summary),
        "detailed_explanation": _strip_scaffolding(result.detailed_explanation) if result.detailed_explanation else None,
        "key_points": [_strip_scaffolding(kp) for kp in result.key_points] if result.key_points else [],
        "recommended_actions": [_strip_scaffolding(a) for a in result.recommended_actions],
        "likely_causes": [
            c.model_copy(update={
                "cause": _strip_scaffolding(c.cause),
                "explanation": _strip_scaffolding(c.explanation),
            })
            for c in result.likely_causes
        ],
        "citations": [
            c.model_copy(update={"document_title": _strip_scaffolding(c.document_title)})
            for c in result.citations
        ],
    })

    # SAFETY_CRITICAL queries (pesticide overdose, toxic exposure) must ALWAYS
    # carry an escalation next-step, regardless of guard score — these are the
    # highest-stakes class. Fall back to the statewide contact when the county
    # is not in county_agents.json (F3/F4).
    safety_escalation = None
    if category and category.split(":", 1)[0] == "SAFETY_CRITICAL":
        safety_escalation = (
            citation_guard_v2.escalation_cue(county_fips)
            or citation_guard_v2.GENERIC_ESCALATION
        )

    # Step 3: NLI claim verification. This can be disabled for constrained
    # runtimes, but defaults on so confidence scoring remains active.
    if not config.NLI_CITATION_GUARD_ENABLED:
        if safety_escalation:
            result = result.model_copy(update={"escalation": safety_escalation})
        return result

    answer_prose = _advisory_to_verifiable_text(result)
    retrieved_chunks = [
        {
            "snippet": (doc.page_content or "")[:500] if hasattr(doc, "page_content")
                       else doc.get("snippet", ""),
        }
        for doc in docs
    ]

    nli_result = await citation_guard_v2.verify_answer(answer_prose, retrieved_chunks, run_config=run_config)
    confidence_score: float = nli_result["confidence_score"]
    claim_verification = nli_result["claim_verification"]

    escalation = None
    if confidence_score < citation_guard_v2.ESCALATION_THRESHOLD:
        # Generic statewide contact when the county is missing from
        # county_agents.json — a suppressed body must still carry a next step (F3).
        escalation = (
            citation_guard_v2.escalation_cue(county_fips)
            or citation_guard_v2.GENERIC_ESCALATION
        )
    if safety_escalation and not escalation:
        escalation = safety_escalation

    update: dict = {
        "confidence_score": confidence_score,
        "claim_verification": claim_verification,
        "escalation": escalation,
    }

    # Reconcile the user-facing confidence label with the guard score. The
    # LLM-authored `confidence` is advisory; the guard score is authoritative.
    # Downgrade only — never upgrade an LLM "Low".
    if confidence_score < citation_guard_v2.SUPPRESSION_THRESHOLD:
        update["confidence"] = "Low"
    elif confidence_score < citation_guard_v2.ESCALATION_THRESHOLD:
        if result.confidence == "High":
            update["confidence"] = "Medium"

    if confidence_score < citation_guard_v2.SUPPRESSION_THRESHOLD:
        # Blank the unverified body. The escalation is carried by `escalation`
        # (rendered as its own card) — do NOT also duplicate it into warnings.
        update.update({
            "suppressed": True,
            "problem_summary": "",
            "likely_causes": [],
            "recommended_actions": [],
            "products_rates": [],
            "warnings": [],
        })

    return result.model_copy(update=update)


async def run_rag_query(
    *,
    message: str,
    county_fips: str,
    language: str,
    category: str,
    session_history: list[dict],
    rice_fields: list[dict] | None = None,
    user_id: str | None = None,
    progress: "asyncio.Queue | None" = None,
    stream: bool = False,
) -> tuple[AdvisoryResponse, list[dict]]:
    """Returns (advisory, retrieved_chunks)."""
    await _emit(progress, "searching")
    run_config = {
        "metadata": {
            "user_id": user_id,
            "county_fips": county_fips,
            "language": language,
            "category": category,
        }
    }
    context_task = asyncio.create_task(get_context(county_fips))

    vectorstore = _get_vectorstore()
    namespaces = _namespaces_for(category)

    # When reranking, pull a wider candidate set then trim to TOP_K_RETRIEVAL.
    fetch_k = config.RERANK_CANDIDATES if config.RERANK_ENABLED else config.TOP_K_RETRIEVAL

    docs = await asyncio.to_thread(
        _fanout_search, vectorstore, message, fetch_k, namespaces,
    )

    if config.RERANK_ENABLED and docs:
        from services import reranker
        docs = await asyncio.to_thread(
            reranker.rerank, message, docs, config.TOP_K_RETRIEVAL
        )

    await _emit(
        progress, "sources_found",
        count=len(docs),
        titles=[
            (d.metadata.get("document_title") or f"Source {i+1}")
            for i, d in enumerate(docs)
        ],
    )

    ctx = await context_task
    soil = ctx["soil"]
    weather = ctx["weather"]

    # Parse intent and base category
    intent = "diagnostic"
    base_category = category
    if ":" in category:
        base_category, intent_suffix = category.split(":", 1)
        if intent_suffix.lower() == "info":
            intent = "informational"

    # AWD context injection for rice queries with registered fields
    awd_context: str | None = None
    if rice_fields and base_category == "IN_SCOPE_RICE":
        try:
            from services import awd_scheduler
            from services.context import fetch_usgs_well
            usgs = await fetch_usgs_well(county_fips)
            stress = (usgs or {}).get("stress_level", "normal")
            well_m = (usgs or {}).get("current_depth_m")
            drainage = soil.get("drainage_class") or "default"

            awd_results = []
            for f in rice_fields[:3]:
                if not f.get("field_name") or not f.get("last_flood_date"):
                    continue
                try:
                    flood_date = _date.fromisoformat(f["last_flood_date"])
                except ValueError:
                    continue
                awd_results.append(
                    awd_scheduler.compute_awd_stage(
                        field_name=f["field_name"],
                        last_flood_date=flood_date,
                        drainage_class=drainage,
                        current_well_m=well_m,
                        aquifer_stress_level=stress,
                    )
                )
            if awd_results:
                awd_context = awd_scheduler.format_awd_context(awd_results)
        except Exception:
            logger.warning("AWD context injection failed", exc_info=True)

    county_info = get_county_info(county_fips)
    county_name = county_info["county_name"] if county_info else county_fips

    system_prompt = build_system_prompt(
        soil_context=soil,
        weather_context=weather,
        retrieved_docs=docs,
        session_history=session_history,
        language=language,
        is_safety_critical=(base_category == "SAFETY_CRITICAL"),
        county_name=county_name,
        awd_context=awd_context,
        intent=intent,
    )

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=message),
    ]

    # Provider order from config (default Groq primary — Gemini free is 20/day).
    # Chain 70b -> 8b-instant -> Gemini: when 70b hits its free tokens-per-day cap,
    # 8b (far higher TPD) keeps the pilot serving instead of failing.
    deepinfra = None  # default; overridden below when not using local LLM
    if config.LLM_PRIMARY == "local":
        from services.local_llm import get_local_chat
        ordered = [get_local_chat()]
    else:
        groq = _get_groq_llm()
        deepinfra = _get_deepinfra_llm()
        groq_fast = _get_groq_fast_llm()
        gemini = _get_llm()
        
        if config.LLM_PRIMARY == "deepinfra":
            ordered = [deepinfra, groq, groq_fast, gemini]
        elif config.LLM_PRIMARY == "gemini":
            ordered = [gemini, groq, deepinfra, groq_fast]
        else:  # groq
            ordered = [groq, deepinfra, groq_fast, gemini]

    # Partial-update callback: pushes {"kind": "partial", "draft": ...} onto the
    # progress queue so the SSE router can forward incremental advisory content.
    # Throttled to one frame per PARTIAL_STREAM_THROTTLE_SECONDS (F7). The final
    # complete advisory ships separately, so dropping intermediate frames is safe.
    last_partial_at = 0.0

    async def _on_partial_cb(d: dict) -> None:
        nonlocal last_partial_at
        if progress is None:
            return
        now = time.monotonic()
        if now - last_partial_at < PARTIAL_STREAM_THROTTLE_SECONDS:
            return
        last_partial_at = now
        await progress.put({"kind": "partial", "draft": d})

    await _emit(progress, "writing")
    result = None
    last_err = None
    for llm in ordered:
        if llm is None:
            continue
        try:
            # Identity check — value-equality on pydantic models is fragile and
            # can misclassify a non-DeepInfra provider as DeepInfra.
            is_deepinfra = deepinfra is not None and llm is deepinfra

            if is_deepinfra:
                from langchain_core.output_parsers import PydanticOutputParser
                parser = PydanticOutputParser(pydantic_object=AdvisoryDraft)
                format_instructions = parser.get_format_instructions()

                di_messages = []
                for msg in messages:
                    if msg.type == "system":
                        di_messages.append(SystemMessage(content=f"{msg.content}\n\n{format_instructions}"))
                    else:
                        di_messages.append(msg)

            if stream:
                # --- Streaming path ---
                try:
                    if is_deepinfra:
                        final_dict = await _astream_draft(
                            llm, di_messages, run_config, _on_partial_cb,
                            prepend_format_instructions=True,
                        )
                    else:
                        final_dict = await _astream_draft(
                            llm, messages, run_config, _on_partial_cb,
                        )

                    if final_dict is None:
                        # Stream produced no valid JSON — fall back to ainvoke
                        # silently (zero partial items already pushed).
                        logger.debug("_astream_draft returned None; falling back to ainvoke for this provider")
                        if is_deepinfra:
                            runnable = llm.with_structured_output(AdvisoryDraft, method="json_mode")
                            result = await runnable.ainvoke(di_messages, config=run_config)
                        else:
                            result = await llm.with_structured_output(AdvisoryDraft).ainvoke(messages, config=run_config)
                    else:
                        # Validate the streamed dict against AdvisoryDraft.
                        # Raises ValidationError on bad generation → provider fallback.
                        result = AdvisoryDraft(**final_dict)
                except Exception as stream_exc:
                    # Any error during streaming (astream, validation, etc.) falls
                    # back to ainvoke for this provider.  Quota errors on the ainvoke
                    # fallback still bubble up and trigger the outer provider loop.
                    logger.debug("Streaming failed (%s); falling back to ainvoke", stream_exc)
                    if is_deepinfra:
                        runnable = llm.with_structured_output(AdvisoryDraft, method="json_mode")
                        result = await runnable.ainvoke(di_messages, config=run_config)
                    else:
                        result = await llm.with_structured_output(AdvisoryDraft).ainvoke(messages, config=run_config)
            else:
                # --- Non-streaming path (unchanged) ---
                if is_deepinfra:
                    runnable = llm.with_structured_output(AdvisoryDraft, method="json_mode")
                    result = await runnable.ainvoke(di_messages, config=run_config)
                else:
                    result = await llm.with_structured_output(AdvisoryDraft).ainvoke(messages, config=run_config)

            break
        except Exception as e:
            last_err = e
            # Only fall back on quota/rate-limit. Real errors (auth, schema, bug)
            # must surface, not be masked by trying every provider in turn.
            if not _is_quota_error(e):
                raise
            logger.warning("Generation provider quota-exhausted, trying next: %s", str(e)[:200])

    if result is None:
        raise RuntimeError(f"RAG generation failed (all providers): {last_err}") from last_err

    await _emit(progress, "verifying")
    advisory = await _postprocess_async(result, docs, soil, weather, county_fips, run_config=run_config, category=category)
    retrieved_chunks = [
        {
            "document_title": d.metadata.get("document_title", ""),
            "section_heading": d.metadata.get("section_heading", ""),
            "snippet": (d.page_content or "")[:500],
        }
        for d in docs
    ]
    return advisory, retrieved_chunks
