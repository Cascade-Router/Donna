"""Plugin: farsi_naming_fix — offline post-STT Farsi name repair.

Stdlib only. No shell, network, or filesystem side effects.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any

TOOL_ID = "farsi_naming_fix"
_MAX_INPUT_CHARS = 4_000

# Known Persian / mangled forms → canonical English spelling used by Donna profile keys.
# Ordered longest-first so multi-token patterns win.
_NAME_RULES: tuple[tuple[re.Pattern[str], str], ...] = (
    # Amirhosein (with optional space / ZWNJ / Arabic Yeh)
    (
        re.compile(
            r"(?:"
            r"امیر[\s\u200c]*حسین|"
            r"امیر[\s\u200c]*حسینی|"
            r"\bAmir\s*[- ]?\s*Hosein\b|"
            r"\bAmir\s*[- ]?\s*Hossein\b|"
            r"\bAmirhos(?:e|ei|i)n\b|"
            r"\bAMIRHOSEN\b|"
            r"\bAmir\s+Hoss?ein\b"
            r")",
            re.I,
        ),
        "Amirhosein",
    ),
    # Narges
    (
        re.compile(
            r"(?:"
            r"نرگس|"
            r"نارگس|"
            r"نارگِس|"
            r"\bNarius\b|"
            r"\bNarjis\b|"
            r"\bAR[- ]?GES\b|"
            r"\bNarg(?:es|is|ez|ess)\b"
            r")",
            re.I,
        ),
        "Narges",
    ),
)

# Collapse duplicated repairs: "Amirhosein Amirhosein" / "Narges, and Narges"
_DEDUP_RULES: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(
            r"\b(Amirhosein)(?:\s*,\s*(?:and\s+)?|\s+and\s+|\s+)\1\b",
            re.I,
        ),
        r"\1",
    ),
    (
        re.compile(
            r"\b(Narges)(?:\s*,\s*(?:and\s+)?|\s+and\s+|\s+)\1\b",
            re.I,
        ),
        r"\1",
    ),
)


def sanitize_transcript(text: str) -> str:
    """Strict input sanitization: NFC, length cap, strip C0 controls (keep whitespace)."""
    raw = unicodedata.normalize("NFC", str(text or ""))
    if len(raw) > _MAX_INPUT_CHARS:
        raw = raw[:_MAX_INPUT_CHARS]
    cleaned = "".join(
        ch
        for ch in raw
        if ch in "\t\n\r" or unicodedata.category(ch)[0] != "C"
    )
    return cleaned.strip()


def farsi_naming_fix(text: str) -> dict[str, Any]:
    """Apply household-name dictionary + regex repairs to an STT transcript.

    Returns a structured result for tests / observation formatting.
    """
    original = sanitize_transcript(text)
    if not original:
        return {
            "ok": True,
            "text": "",
            "changed": False,
            "replacements": [],
            "error": None,
        }

    out = original
    replacements: list[dict[str, str]] = []
    for pattern, repl in _NAME_RULES:
        def _sub(m: re.Match[str], *, _repl: str = repl) -> str:
            hit = m.group(0)
            if hit != _repl:
                replacements.append({"from": hit, "to": _repl})
            return _repl

        out = pattern.sub(_sub, out)

    for pattern, repl in _DEDUP_RULES:
        out = pattern.sub(repl, out)

    # Normalize whitespace after Farsi → Latin swaps.
    out = re.sub(r"[ \t]{2,}", " ", out).strip()
    return {
        "ok": True,
        "text": out,
        "changed": out != original,
        "replacements": replacements,
        "error": None,
    }


def handle_tool_call(call: Any) -> str:
    """Broker-compatible handler: ToolCall → Observation string."""
    args = getattr(call, "arguments", None) or {}
    if not isinstance(args, dict):
        args = {}
    text = args.get("text")
    if text is None:
        return "ERROR: missing text"
    result = farsi_naming_fix(str(text))
    if not result.get("ok"):
        return f"ERROR: farsi_naming_fix failed: {result.get('error')}"
    n = len(result.get("replacements") or [])
    flag = "changed=true" if result.get("changed") else "changed=false"
    return f"OK: farsi_naming_fix {flag} replacements={n} text={result['text']!r}"
