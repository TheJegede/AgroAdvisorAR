import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))
sys.path.insert(0, str(Path(__file__).parent))

import config
import services.rag as rag
from answer_eval_full import _apply_gen_model_override


def test_gen_model_override_repoints_config_and_clears_cache():
    # Stale cached client + the default 70B model in config.
    rag._deepinfra_llm = "STALE_CLIENT"
    config.DEEPINFRA_MODEL = "meta-llama/Llama-3.3-70B-Instruct"

    out = _apply_gen_model_override("openai/gpt-oss-120b")

    # Phase C swaps ONLY the generation model id...
    assert out == "openai/gpt-oss-120b"
    assert config.DEEPINFRA_MODEL == "openai/gpt-oss-120b"
    # ...and clears rag's cached client so run_rag_query rebuilds generation
    # with the new model (retrieval + judge untouched).
    assert rag._deepinfra_llm is None


def test_gen_model_override_accepts_qwen():
    rag._deepinfra_llm = None
    _apply_gen_model_override("Qwen/Qwen3-32B")
    assert config.DEEPINFRA_MODEL == "Qwen/Qwen3-32B"
