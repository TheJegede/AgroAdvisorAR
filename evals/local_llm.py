"""Local Qwen-7B (4-bit) for FREE, quota-free eval — generation + judging on the
RTX 4070. Provides:
  - LocalChat: a minimal langchain-shaped chat model with .with_structured_output()
    so it drops into the production RAG chain in place of Groq/Gemini.
  - judge_correctness / judge_faithfulness: local LLM-as-judge.
One 7B-4bit model is loaded once and reused for both.
"""
import asyncio
import json
import re

_model = None
_tok = None
MODEL = "Qwen/Qwen2.5-7B-Instruct"


def _load():
    global _model, _tok
    if _model is None:
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
        print(f"Loading {MODEL} (4-bit)...")
        bnb = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4",
                                 bnb_4bit_compute_dtype=torch.float16)
        _tok = AutoTokenizer.from_pretrained(MODEL)
        _model = AutoModelForCausalLM.from_pretrained(MODEL, quantization_config=bnb,
                                                      device_map="cuda")
        _model.eval()
    return _model, _tok


def _gen(system: str, user: str, max_new_tokens: int = 512) -> str:
    import torch
    model, tok = _load()
    msgs = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    prompt = tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
    enc = tok(prompt, return_tensors="pt", truncation=True, max_length=4096).to("cuda")
    with torch.no_grad():
        out = model.generate(**enc, max_new_tokens=max_new_tokens, do_sample=False,
                             pad_token_id=tok.eos_token_id)
    return tok.decode(out[0, enc["input_ids"].shape[1]:], skip_special_tokens=True)


def _extract_json(raw: str):
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:
        return None


# --- structured-generation adapter for the production chain ---
_SCHEMA_INSTR = (
    "\n\nRespond with ONLY a single JSON object, no prose, with exactly these keys:\n"
    '{"problem_summary": str, "likely_causes": [{"cause": str, "explanation": str}], '
    '"recommended_actions": [str], "products_rates": [{"product": str, "rate": str, '
    '"application_method": str}], "warnings": [str], "citations": [{"document_title": '
    'str, "section": str}], "confidence": "High"|"Medium"|"Low", '
    '"confidence_explanation": str}'
)


class _Structured:
    def __init__(self, schema):
        self.schema = schema

    async def ainvoke(self, messages):
        system = "\n".join(getattr(m, "content", "") for m in messages
                           if m.__class__.__name__ == "SystemMessage")
        user = "\n".join(getattr(m, "content", "") for m in messages
                         if m.__class__.__name__ == "HumanMessage")
        raw = await asyncio.to_thread(_gen, system + _SCHEMA_INSTR, user, 700)
        data = _extract_json(raw) or {}
        # Fill scaffolding the chain/postprocess expects; postprocess overwrites context_meta.
        payload = {
            "problem_summary": data.get("problem_summary", ""),
            "likely_causes": data.get("likely_causes", []) or [],
            "recommended_actions": data.get("recommended_actions", []) or [],
            "products_rates": [
                {"product": p.get("product", ""), "rate": p.get("rate", ""),
                 "application_method": p.get("application_method", "")}
                for p in (data.get("products_rates", []) or []) if isinstance(p, dict)
            ],
            "warnings": data.get("warnings", []) or [],
            "citations": [
                {"document_title": c.get("document_title", ""), "section": c.get("section", "")}
                for c in (data.get("citations", []) or []) if isinstance(c, dict)
            ],
            "confidence": data.get("confidence", "Medium") if data.get("confidence") in
                          {"High", "Medium", "Low"} else "Medium",
            "confidence_explanation": data.get("confidence_explanation", ""),
            "language": "en",
            "context_meta": {"soil_data_available": False, "weather_data_available": False,
                             "county_fips": ""},
        }
        return self.schema.model_validate(payload)


class LocalChat:
    """Drop-in for ChatGroq/ChatGoogleGenerativeAI in the generation chain."""
    def with_structured_output(self, schema):
        return _Structured(schema)

    async def ainvoke(self, messages):
        """Plain text call (used by the translation bridge in eval)."""
        import asyncio
        from types import SimpleNamespace
        system = "\n".join(getattr(m, "content", "") for m in messages
                           if m.__class__.__name__ == "SystemMessage")
        user = "\n".join(getattr(m, "content", "") for m in messages
                         if m.__class__.__name__ != "SystemMessage")
        text = await asyncio.to_thread(_gen, system, user, 256)
        return SimpleNamespace(content=text)


# --- local LLM-as-judge ---
def _summarize(advisory: dict) -> str:
    parts = [f"Problem summary: {advisory.get('problem_summary','')}"]
    if advisory.get("likely_causes"):
        parts.append("Likely causes: " + "; ".join(
            f"{c.get('cause','')} — {c.get('explanation','')}" for c in advisory["likely_causes"]))
    if advisory.get("recommended_actions"):
        parts.append("Recommended actions: " + "; ".join(advisory["recommended_actions"]))
    if advisory.get("products_rates"):
        parts.append("Products: " + "; ".join(
            f"{p.get('product','')} @ {p.get('rate','')}" for p in advisory["products_rates"]))
    return "\n".join(parts)


def _score(system: str, user: str):
    raw = _gen(system, user, 120)
    d = _extract_json(raw) or {}
    try:
        s = max(0.0, min(1.0, float(d.get("score", 0.0))))
    except Exception:
        s = 0.0
    return s, str(d.get("rationale", ""))[:80]


def judge_correctness(query: str, advisory: dict, gold: str):
    sys = ("You grade an agricultural advisory against a reference passage. Be strict; "
           "penalize hallucinations and contradictions.")
    user = (f"QUERY: {query}\n\nADVISORY:\n{_summarize(advisory)}\n\nREFERENCE (gold):\n{gold[:2000]}\n\n"
            'Return ONLY JSON: {"score": 1.0|0.5|0.0, "rationale": "<short>"}\n'
            "1.0 correct use of reference; 0.5 partial; 0.0 wrong/hallucinated/off-topic.")
    return _score(sys, user)


def judge_faithfulness(advisory: dict, chunks: list):
    ctx = "\n\n".join(f"[{c.get('document_title','')}] {c.get('snippet','')}" for c in chunks) or "(none)"
    sys = ("You audit a RAG advisory for faithfulness: are its specific claims (causes, "
           "actions, products, rates) supported by the retrieved passages? Penalize invented specifics.")
    user = (f"ADVISORY:\n{_summarize(advisory)}\n\nRETRIEVED PASSAGES (only context):\n{ctx[:6000]}\n\n"
            'Return ONLY JSON: {"score": 1.0|0.5|0.0, "rationale": "<short>"}\n'
            "1.0 all claims supported; 0.5 minor unsupported; 0.0 key claims unsupported.")
    return _score(sys, user)
