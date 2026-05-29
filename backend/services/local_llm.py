"""Local GPU LLM (Qwen2.5-7B 4-bit) as a drop-in for the cloud chat models.

For LOCAL development/testing only (`LLM_PRIMARY=local`) — lets the full RAG
chain run with zero API quota on a CUDA GPU. NOT for the deployed backend
(Koyeb has no GPU). Exposes a langchain-shaped interface: `.ainvoke(messages)`
for plain calls (classifier, claim decomposition) and `.with_structured_output()`
for the advisory generation.
"""
import asyncio
import json
import re
from types import SimpleNamespace

import config

_model = None
_tok = None
MODEL = config.LOCAL_LLM_MODEL


def _load():
    global _model, _tok
    if _model is None:
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
        bnb = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4",
                                 bnb_4bit_compute_dtype=torch.float16)
        _tok = AutoTokenizer.from_pretrained(MODEL)
        _model = AutoModelForCausalLM.from_pretrained(MODEL, quantization_config=bnb,
                                                      device_map="cuda")
        _model.eval()
    return _model, _tok


def _generate(system: str, user: str, max_new_tokens: int) -> str:
    import torch
    model, tok = _load()
    msgs = []
    if system:
        msgs.append({"role": "system", "content": system})
    msgs.append({"role": "user", "content": user})
    prompt = tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
    enc = tok(prompt, return_tensors="pt", truncation=True, max_length=4096).to("cuda")
    with torch.no_grad():
        out = model.generate(**enc, max_new_tokens=max_new_tokens, do_sample=False,
                             pad_token_id=tok.eos_token_id)
    return tok.decode(out[0, enc["input_ids"].shape[1]:], skip_special_tokens=True)


def _split_messages(messages):
    system = "\n".join(getattr(m, "content", "") for m in messages
                       if m.__class__.__name__ == "SystemMessage")
    user = "\n".join(getattr(m, "content", "") for m in messages
                     if m.__class__.__name__ != "SystemMessage")
    return system, user


_SCHEMA_INSTR = (
    "\n\nRespond with ONLY a single JSON object, no prose, with exactly these keys:\n"
    '{"problem_summary": str, "likely_causes": [{"cause": str, "explanation": str}], '
    '"recommended_actions": [str], "products_rates": [{"product": str, "rate": str, '
    '"application_method": str}], "warnings": [str], "citations": [{"document_title": '
    'str, "section": str}], "confidence": "High"|"Medium"|"Low", '
    '"confidence_explanation": str}'
)


def _extract_json(raw: str):
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if not m:
        return {}
    try:
        return json.loads(m.group(0))
    except Exception:
        return {}


class _Structured:
    def __init__(self, schema):
        self.schema = schema

    async def ainvoke(self, messages):
        system, user = _split_messages(messages)
        raw = await asyncio.to_thread(_generate, system + _SCHEMA_INSTR, user, 700)
        d = _extract_json(raw)
        payload = {
            "problem_summary": d.get("problem_summary", ""),
            "likely_causes": [c for c in (d.get("likely_causes") or []) if isinstance(c, dict)],
            "recommended_actions": d.get("recommended_actions") or [],
            "products_rates": [
                {"product": p.get("product", ""), "rate": p.get("rate", ""),
                 "application_method": p.get("application_method", "")}
                for p in (d.get("products_rates") or []) if isinstance(p, dict)
            ],
            "warnings": d.get("warnings") or [],
            "citations": [
                {"document_title": c.get("document_title", ""), "section": c.get("section", "")}
                for c in (d.get("citations") or []) if isinstance(c, dict)
            ],
            "confidence": d.get("confidence") if d.get("confidence") in {"High", "Medium", "Low"} else "Medium",
            "confidence_explanation": d.get("confidence_explanation", ""),
            "language": "en",
            "context_meta": {"soil_data_available": False, "weather_data_available": False,
                             "county_fips": ""},
        }
        return self.schema.model_validate(payload)


class LocalChat:
    """Drop-in for ChatGroq / ChatGoogleGenerativeAI on a local GPU."""

    async def ainvoke(self, messages):
        system, user = _split_messages(messages)
        text = await asyncio.to_thread(_generate, system, user, 256)
        return SimpleNamespace(content=text)

    def with_structured_output(self, schema):
        return _Structured(schema)


_local = None


def get_local_chat():
    global _local
    if _local is None:
        _local = LocalChat()
    return _local
