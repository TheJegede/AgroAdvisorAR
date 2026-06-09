# evals/diagnostic/pipeline_flags.py
"""Read abstention state off an advisory dict (model_dump of AdvisoryResponse)."""


def is_abstention(advisory: dict) -> bool:
    if advisory.get("suppressed"):
        return True
    if advisory.get("escalation"):
        return True
    return False
