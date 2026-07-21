"""Donna runtime feature flags loaded from settings.json."""

from __future__ import annotations

import json
import os
from typing import Any

from donna.paths import DONNA_WORKSPACE, PROJECT_ROOT, SETTINGS_PATH as _SETTINGS_PATH

_ROOT = str(PROJECT_ROOT)
SETTINGS_PATH = str(_SETTINGS_PATH)

# Production defaults — Tool Forge unlocked; English-first until Persian is re-enabled.
DEFAULT_FLAGS: dict[str, Any] = {
    "enable_dynamic_tool_synthesis": True,
    # Cascade Router: escalate high-complexity turns to an external LLM when available.
    "enable_cascade_router": False,
    # en = English-only STT/reply/TTS | fa = Persian-first | auto = detect from transcript
    "assistant_language": "en",
    # HF Whisper.generate language id: "english" | "persian"
    "whisper_language": "english",
    # IANA timezone (e.g. America/Los_Angeles) for local clock + kickoff conversion.
    "timezone": "America/Los_Angeles",
    # Human place label spoken in answers (city / region).
    "home_city": "",
    "home_region": "",
}


def get_assistant_language() -> str:
    """Return en | fa | auto from settings (default en for production English-first)."""
    raw = str(load_donna_settings().get("assistant_language") or "en").strip().lower()
    if raw in ("en", "english"):
        return "en"
    if raw in ("fa", "farsi", "persian"):
        return "fa"
    if raw in ("auto", "detect", "mixed"):
        return "auto"
    return "en"


def get_whisper_language() -> str:
    """HF transformers Whisper language id."""
    cfg = load_donna_settings()
    raw = str(cfg.get("whisper_language") or "").strip().lower()
    if raw in ("english", "en"):
        return "english"
    if raw in ("persian", "farsi", "fa"):
        return "persian"
    # Derive from assistant_language when whisper_language omitted.
    mode = get_assistant_language()
    if mode == "fa":
        return "persian"
    return "english"


def resolve_reply_lang(user_text: str = "") -> str:
    """Language lock for ReAct FINAL / TTS routing."""
    mode = get_assistant_language()
    if mode == "en":
        return "en"
    if mode == "fa":
        return "fa"
    from donna.tools.normalize import detect_lang

    return detect_lang(user_text) if user_text else "en"


def get_timezone() -> str:
    """IANA timezone id from settings (default America/Los_Angeles)."""
    raw = str(load_donna_settings().get("timezone") or "America/Los_Angeles").strip()
    return raw or "America/Los_Angeles"


def get_home_place() -> dict[str, str]:
    """User place labels for prompt injection."""
    cfg = load_donna_settings()
    city = str(cfg.get("home_city") or "").strip()
    region = str(cfg.get("home_region") or "").strip()
    return {"city": city, "region": region}


def local_now_context(
    *,
    timezone: str | None = None,
    home_city: str | None = None,
    home_region: str | None = None,
) -> dict[str, str]:
    """Local clock + place strings for the system prompt and sports answers."""
    from datetime import datetime
    from zoneinfo import ZoneInfo

    tz_name = (timezone or get_timezone()).strip() or "America/Los_Angeles"
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        # Windows often needs the `tzdata` package; fall back to system local TZ.
        try:
            tz_name = "America/Los_Angeles"
            tz = ZoneInfo(tz_name)
        except Exception:
            now = datetime.now().astimezone()
            place_cfg = get_home_place()
            city = (home_city if home_city is not None else place_cfg["city"]).strip()
            region = (home_region if home_region is not None else place_cfg["region"]).strip()
            if city and region:
                place_s = f"{city}, {region}"
            elif city:
                place_s = city
            elif region:
                place_s = region
            else:
                place_s = ""
            abbr = now.tzname() or "local"
            hour12 = now.strftime("%I").lstrip("0") or "12"
            local_now = (
                f"{now.strftime('%A, %B')} {now.day}, {now.year}, "
                f"{hour12}:{now.strftime('%M')} {now.strftime('%p')} {abbr}"
            )
            return {
                "timezone": str(now.tzinfo or "local"),
                "tz_abbr": abbr,
                "local_now": local_now,
                "local_date": f"{now.strftime('%A, %B')} {now.day}, {now.year}",
                "place": place_s,
            }
    now = datetime.now(tz)
    place_cfg = get_home_place()
    city = (home_city if home_city is not None else place_cfg["city"]).strip()
    region = (home_region if home_region is not None else place_cfg["region"]).strip()
    if city and region:
        place_s = f"{city}, {region}"
    elif city:
        place_s = city
    elif region:
        place_s = region
    else:
        place_s = ""
    # Friendly TZ abbreviation when available (PDT/PST etc.).
    abbr = now.tzname() or tz_name
    hour12 = now.strftime("%I").lstrip("0") or "12"
    local_now = (
        f"{now.strftime('%A, %B')} {now.day}, {now.year}, "
        f"{hour12}:{now.strftime('%M')} {now.strftime('%p')} {abbr}"
    )
    return {
        "timezone": tz_name,
        "tz_abbr": abbr,
        "local_now": local_now,
        "local_date": f"{now.strftime('%A, %B')} {now.day}, {now.year}",
        "place": place_s,
    }


def format_kickoff_in_local_tz(
    hour: int,
    minute: int,
    *,
    source_tz: str = "America/New_York",
) -> str | None:
    """Convert a source-timezone kickoff clock into the user's local spoken time."""
    from datetime import datetime
    from zoneinfo import ZoneInfo

    try:
        src = ZoneInfo(source_tz)
        dst_name = get_timezone()
        dst = ZoneInfo(dst_name)
    except Exception:
        return None
    # Use today's date in source TZ as anchor (fixture date handled by caller).
    now_src = datetime.now(src)
    anchored = now_src.replace(hour=hour, minute=minute, second=0, microsecond=0)
    local = anchored.astimezone(dst)
    h12 = local.strftime("%I").lstrip("0") or "12"
    ampm = local.strftime("%p")
    abbr = local.tzname() or dst_name
    return f"{h12}:{local.strftime('%M')} {ampm} {abbr}"


def update_place_settings(
    *,
    timezone: str | None = None,
    home_city: str | None = None,
    home_region: str | None = None,
) -> None:
    """Persist place/timezone overrides into settings.json and refresh cache."""
    global _CACHE
    cfg = load_donna_settings(force_reload=True)
    if timezone is not None and str(timezone).strip():
        cfg["timezone"] = str(timezone).strip()
    if home_city is not None:
        cfg["home_city"] = str(home_city).strip()
    if home_region is not None:
        cfg["home_region"] = str(home_region).strip()
    try:
        with open(SETTINGS_PATH, "w", encoding="utf-8") as fh:
            json.dump(cfg, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
    except OSError:
        return
    _CACHE = dict(cfg)


_CACHE: dict[str, Any] | None = None


def load_donna_settings(*, force_reload: bool = False) -> dict[str, Any]:
    """Load settings.json merged over production defaults."""
    global _CACHE
    if _CACHE is not None and not force_reload:
        return dict(_CACHE)
    cfg: dict[str, Any] = dict(DEFAULT_FLAGS)
    if os.path.isfile(SETTINGS_PATH):
        try:
            with open(SETTINGS_PATH, encoding="utf-8") as fh:
                raw = json.load(fh)
            if isinstance(raw, dict):
                cfg.update(raw)
        except (OSError, json.JSONDecodeError):
            pass
    _CACHE = dict(cfg)
    return dict(cfg)


def is_dynamic_tool_synthesis_enabled() -> bool:
    """True only when settings explicitly enable architect_new_tool / sandbox writes."""
    cfg = load_donna_settings()
    return bool(cfg.get("enable_dynamic_tool_synthesis", False))


def synthesis_locked_message(lang: str = "en") -> str:
    """Bilingual graceful-degradation copy when synthesis is production-locked."""
    if lang in ("fa", "mixed"):
        return (
            "قابلیت ساخت پویای ابزار الان برای ایمنی محیط تولید قفل است "
            "و نمی‌توانم کد جدید تولید یا تست کنم. "
            "برای فعال‌سازی موقت، enable_dynamic_tool_synthesis را در settings.json روی true بگذارید."
        )
    return (
        "My dynamic tool synthesis capabilities are currently locked for production safety, "
        "and I cannot generate or test new code at this time. "
        "To re-enable temporarily, set enable_dynamic_tool_synthesis to true in settings.json."
    )
