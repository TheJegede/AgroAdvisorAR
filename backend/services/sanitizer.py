"""Prompt-injection mitigation. Runs on /query input before classifier.

Two-stage:
  1. Reject (raise InjectionDetected) on high-confidence override attempts.
  2. Strip silently on lower-risk patterns (role tokens, control chars,
     HTML role tags). Stripped text continues through the pipeline.

This is defense-in-depth. The RAG system prompt already instructs the LLM
to ignore user-supplied role framing, and structured-output validation
catches most leakage. The sanitizer is a cheap first line."""
import re
import unicodedata


MAX_MESSAGE_LENGTH = 800


class InjectionDetected(ValueError):
    """User input contained a high-confidence prompt-injection attempt."""


class MessageTooLong(ValueError):
    """Message exceeds the length cap after Unicode normalization."""


# High-confidence override patterns — reject with 400.
# Case-insensitive. Word boundaries to limit false positives on natural phrases
# like "I want to ignore weeds in my field".
_REJECT_PATTERNS = [
    # Ignore / disregard / forget previous instructions
    r"\b(ignore|disregard|forget)\s+(all\s+|the\s+|your\s+|prior\s+|previous\s+|above\s+|earlier\s+)+(instructions?|prompts?|rules?|context|system|directives?)\b",
    r"\b(ignore|disregard|forget)\s+(everything\s+)?(above|prior|previously?|before)\b",
    # Role override
    r"\byou\s+are\s+(now|no\s+longer|actually)\b",
    r"\b(pretend|act|behave|respond|roleplay)\s+(to\s+be|as\s+(a|an|if))\b",
    r"\bfrom\s+now\s+on(\s*,)?\s+(you|respond|act|answer)\b",
    # Prompt-leak attempts
    r"\b(reveal|show|print|output|repeat|display)\s+(your|the)\s+(system\s+)?(prompt|instructions?|rules?)\b",
    r"\bwhat\s+(are|is)\s+your\s+(system\s+)?(prompt|instructions?|rules?)\b",
    # Instruction header injection
    r"^\s*(new\s+instructions?|system|assistant|user)\s*:",
    # Literal role tokens (model-specific)
    r"<\|(im_start|im_end|system|assistant|user|endoftext)\|>",
    r"\[/?(INST|SYS|SYSTEM|ASSISTANT|USER)\]",
    # XML/HTML role wrappers
    r"</?(system|assistant)>",
]
_REJECT_RE = re.compile("|".join(_REJECT_PATTERNS), re.IGNORECASE | re.MULTILINE)


# Lower-risk patterns — strip silently, do not block the query.
_STRIP_PATTERNS = [
    # Strip leftover XML role tags that survived REJECT (e.g. case the
    # reject regex missed). Belt-and-suspenders.
    (re.compile(r"</?(system|assistant|user)>", re.IGNORECASE), ""),
    # Zero-width and bidi control characters that hide injected tokens.
    (re.compile(r"[​-‏‪-‮⁠﻿]"), ""),
]


def sanitize(message: str, max_length: int = MAX_MESSAGE_LENGTH) -> str:
    """Sanitize user input. Raises InjectionDetected on hard-block patterns and
    MessageTooLong when the normalized text exceeds the cap. Returns a cleaned
    string otherwise."""
    if not isinstance(message, str):
        raise InjectionDetected("Message must be a string.")

    # Normalize Unicode (combine compatibility characters, strip lookalike tricks).
    normalized = unicodedata.normalize("NFKC", message)

    # Enforce the length cap AFTER normalization: NFKC can expand compatibility
    # characters (e.g. a single ligature → many chars), so checking the raw
    # string would let amplified input slip past the cap (F13).
    if len(normalized) > max_length:
        raise MessageTooLong(f"message exceeds {max_length} character limit")

    if _REJECT_RE.search(normalized):
        raise InjectionDetected(
            "Your message looks like a prompt-injection attempt. "
            "Please rephrase as a normal agricultural question."
        )

    cleaned = normalized
    for pattern, replacement in _STRIP_PATTERNS:
        cleaned = pattern.sub(replacement, cleaned)

    return cleaned.strip()
