"""Persian/English argument normalization for tool execution."""

from __future__ import annotations

import re
import unicodedata
from typing import Any

# Arabic presentation forms / Yeh-Kaf variants commonly seen in FA ASR output.
_FA_CHAR_MAP = str.maketrans(
    {
        "ي": "ی",
        "ك": "ک",
        "ة": "ه",
        "ؤ": "و",
        "إ": "ا",
        "أ": "ا",
        "ٱ": "ا",
        "ۀ": "ه",
        "‌": " ",  # ZWNJ -> space for matching
    }
)

_ARABIC_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def contains_farsi(text: str) -> bool:
    return bool(re.search(r"[\u0600-\u06FF]", text or ""))


def detect_lang(text: str) -> str:
    if contains_farsi(text):
        # Mixed if also has substantial Latin letters.
        latin = len(re.findall(r"[A-Za-z]", text or ""))
        return "mixed" if latin >= 3 else "fa"
    return "en"


def normalize_farsi_text(text: str) -> str:
    """NFC + Yeh/Kaf unification + digit fold for FA entities."""
    if not text:
        return ""
    out = unicodedata.normalize("NFC", text)
    out = out.translate(_FA_CHAR_MAP)
    out = out.translate(_ARABIC_DIGITS)
    out = re.sub(r"\s+", " ", out).strip()
    return out


def normalize_tool_arguments(arguments: dict[str, Any], source_lang: str) -> dict[str, Any]:
    """Normalize string args; apply FA token cleanup when source is fa/mixed."""
    cleaned: dict[str, Any] = {}
    for key, value in arguments.items():
        if isinstance(value, str):
            s = value.strip()
            if source_lang in ("fa", "mixed") or contains_farsi(s):
                s = normalize_farsi_text(s)
            # Canonical enums stay lowercase ASCII where applicable.
            if re.fullmatch(r"[A-Za-z_]+", s):
                s = s.lower()
            cleaned[str(key)] = s
        else:
            cleaned[str(key)] = value
    return cleaned
