"""Unit tests for Phase-2 production features + multi-forge routing."""

from __future__ import annotations

from donna.swarm.multi_forge import looks_like_multi_forge, split_forge_goals
from donna.tools.broker import _TOOL_FORGE_HINT_RE, get_broker
from donna.telemetry import note_tool_event, write_dashboard
from donna.paths import DASHBOARD_PATH
from donna.core_agent import ACOUSTIC_SHADOW_FLOOR, adaptive_vad_speech_rms


MASS = (
    "Donna, build three different tools back-to-back: one that tells me the time, "
    "one that generates a random number, and one that lists files in the sandbox."
)


def test_forge_hint_matches_batch() -> None:
    assert _TOOL_FORGE_HINT_RE.search(MASS)
    call = get_broker().parse_utterance(MASS)
    assert call is not None
    assert call.tool_id == "architect_new_tool", call
    print("[PASS] broker routes mass-forge to architect_new_tool")


def test_split_three_goals() -> None:
    assert looks_like_multi_forge(MASS)
    goals = split_forge_goals(MASS)
    assert len(goals) == 3, goals
    assert any("time" in g.lower() for g in goals)
    assert any("random" in g.lower() for g in goals)
    assert any("sandbox" in g.lower() or "files" in g.lower() for g in goals)
    print("[PASS] split_forge_goals → 3")


def test_acoustic_shadow_floor() -> None:
    assert ACOUSTIC_SHADOW_FLOOR >= 0.0020
    assert adaptive_vad_speech_rms() >= ACOUSTIC_SHADOW_FLOOR
    print("[PASS] acoustic shadow floor")


def test_dashboard_write() -> None:
    note_tool_event("forge:demo_tool")
    path = write_dashboard(status="Healthy", pid=12345)
    text = DASHBOARD_PATH.read_text(encoding="utf-8")
    assert "System Status" in text
    assert "12345" in text
    assert "PENDING" in text
    assert path.endswith("dashboard.md")
    print("[PASS] dashboard.md write")


if __name__ == "__main__":
    test_forge_hint_matches_batch()
    test_split_three_goals()
    test_acoustic_shadow_floor()
    test_dashboard_write()
    print("OK")
