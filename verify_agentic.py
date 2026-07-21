"""Local verification: agentic loop + SpatialIR synthesis + vault tool IR (no mic/GUI)."""

from __future__ import annotations

import json
import sys

from test_support_react import patch_scripted_llm, script_line_to_aimessage
from donna.agentic import run_react_loop, REACT_MAX_ITERS
from donna.tools.broker import IntentBroker
from donna.tools.normalize import detect_lang
from donna.tools.schema import ToolCall


class _Monkey:
    """Minimal monkeypatch for verify_agentic (no pytest)."""

    def setattr(self, target, name=None, value=None):
        import langchain_ollama as _lo

        # pytest-style: setattr("pkg.Class", replacement)
        if isinstance(target, str) and name is None and value is not None:
            path, _, attr = target.rpartition(".")
            if target == "langchain_ollama.ChatOllama":
                setattr(_lo, "ChatOllama", value)
                return
            raise AssertionError(f"unsupported setattr path {target!r}")
        if isinstance(target, str) and value is None and callable(name):
            if target == "langchain_ollama.ChatOllama":
                setattr(_lo, "ChatOllama", name)
                return
        raise AssertionError(f"unsupported setattr {target!r} {name!r}")


from donna.prompts.spatial_synthesis import (
    ANTI_DRIFT_EN_BLOCK,
    REACT_PROTOCOL,
    SPATIAL_SYNTHESIS_GUIDE,
    build_agent_system_prompt)


def test_language_lock_and_spatial_guide() -> None:
    prompt = build_agent_system_prompt(
        spatial_block="vis=screen|ui=idle|dom=laptop@center|scene=[laptop@center(a=0.22,d=0.05);cup@top-right(a=0.04,d=0.41)]|intent=چی می‌بینم؟",
        labels_csv="laptop, cup",
        profile_summary="{}",
        reply_lang="fa")
    assert "Persian" in prompt or "Farsi" in prompt
    assert "SpatialIR" in prompt
    assert "Spatial Awareness" in prompt
    assert "CRITICAL INSTRUCTION: Do NOT mention" not in prompt
    assert "FORBIDDEN" in SPATIAL_SYNTHESIS_GUIDE or "Forbidden" in SPATIAL_SYNTHESIS_GUIDE.lower() or "FORBIDDEN" in prompt
    assert "ماشین" in prompt or "car→ماشین" in SPATIAL_SYNTHESIS_GUIDE
    assert "bind_tools" in prompt or "LangChain" in prompt or "Spoken" in prompt
    assert ANTI_DRIFT_EN_BLOCK not in prompt  # FA mode must not English-force
    print("[OK] spatial synthesis + FA language lock in system prompt")

    en_prompt = build_agent_system_prompt(
        spatial_block="vis=screen|ui=idle|dom=none|scene=[none]|intent=Who is Narges?",
        labels_csv="",
        profile_summary="{}",
        reply_lang="en")
    assert en_prompt.rstrip().endswith(ANTI_DRIFT_EN_BLOCK)
    assert "[STRICTLY ENGLISH TEXT]" in en_prompt
    assert "## Silent context" in REACT_PROTOCOL
    assert "<visual_context>" in REACT_PROTOCOL
    assert "JSON Initiative" not in REACT_PROTOCOL
    assert "## Action forcing" not in REACT_PROTOCOL
    print("[OK] English anti-drift block at prompt tail + protocol anchors")

def test_broker_vault_and_tool_parse() -> None:
    broker = IntentBroker()  # fresh registry from tools.json
    assert "read_vault_memory" in broker.registry
    assert "write_vault_memory" in broker.registry
    assert "inject_keystrokes" in broker.registry
    assert "read_clipboard_context" in broker.registry
    assert "architect_new_tool" in broker.registry
    assert "read_system_architecture" in broker.registry

    # Native-tool IR via broker structured parse / test script adapter
    legacy = broker.parse_structured(
        "write_vault_memory(key=remembered_ip, value=192.168.1.50)"
    )
    assert legacy is not None
    assert legacy.tool_id == "write_vault_memory"
    assert legacy.arguments.get("key") == "remembered_ip"

    msg = script_line_to_aimessage(
        '{"tool": "inject_keystrokes", "args": {"text": "hello"}}',
        broker=broker)
    assert msg.tool_calls and msg.tool_calls[0]["name"] == "inject_keystrokes"

    clip = script_line_to_aimessage(
        '{"tool": "read_clipboard_context", "args": {}}',
        broker=broker)
    assert clip.tool_calls and clip.tool_calls[0]["name"] == "read_clipboard_context"

    arch = script_line_to_aimessage(
        '{"tool": "read_system_architecture", "args": {}}',
        broker=broker)
    assert arch.tool_calls and arch.tool_calls[0]["name"] == "read_system_architecture"

    # Production lock: architect_new_tool must not reach a sandbox handler.
    from donna.settings import is_dynamic_tool_synthesis_enabled

    assert is_dynamic_tool_synthesis_enabled() is False
    locked = broker.dispatch(
        ToolCall(
            tool_id="architect_new_tool",
            arguments={"tool_name": "x", "python_code": "y"},
            source_lang="en"),
        {"architect_new_tool": lambda _c: "SHOULD_NOT_RUN"})
    assert "LOCKED" in str(locked)
    assert "production safety" in str(locked).lower()

    # FA intent alias (args filled by LLM later)
    intent = broker.parse_utterance("این IP را یادت باشد")
    assert intent is not None
    assert intent.tool_id == "write_vault_memory"

    # FA describe
    desc = broker.parse_utterance("چی میبینم")
    assert desc is not None
    assert desc.tool_id == "describe_spatial_scene"

    # Self-awareness alias
    about = broker.parse_utterance("tell me about your code")
    assert about is not None
    assert about.tool_id == "read_system_architecture"
    print("[OK] vault + spatial + OS + architect lock + architecture IR parsing")


def test_react_loop_farsi_english_visual() -> None:
    """Simulate: Farsi user asks about English YOLO scene; tool then FINAL in FA."""
    spatial = (
        "vis=screen|ui=idle|dom=laptop@center|"
        "scene=[laptop@center(a=0.30,d=0.02);keyboard@bottom(a=0.12,d=0.35)]|"
        "intent=این لپ‌تاپ وسط صفحه چیه؟"
    )
    system = build_agent_system_prompt(
        spatial_block=spatial,
        labels_csv="laptop, keyboard",
        profile_summary="{}",
        reply_lang="fa")
    user = "این لپ‌تاپ انگلیسی که وسط صفحه است چیه؟ بگو فارسی."

    steps = {
        0: "TOOL: describe_spatial_scene(focus=dominant)",
        1: (
            "FINAL: وسط صفحه یک لپ‌تاپ می‌بینم و پایین‌تر کیبورد هست. "
            "برچسب انگلیسی laptop را به لپ‌تاپ ترجمه کردم."
        ),
    }
    counter = {"i": 0}

    def ask_fn(messages):
        idx = counter["i"]
        counter["i"] += 1
        return steps[min(idx, max(steps))]

    vault = {}

    def execute_fn(tc: ToolCall) -> str:
        if tc.tool_id == "describe_spatial_scene":
            return f"SpatialIR={spatial} | focus on dominant object"
        if tc.tool_id == "write_vault_memory":
            vault[tc.arguments["key"]] = tc.arguments["value"]
            return f"OK: saved {tc.arguments['key']}"
        if tc.tool_id == "read_vault_memory":
            key = tc.arguments.get("key")
            return f"OK: {key}={vault.get(key)!r}"
        return f"OK: {tc.tool_id}"

    patch_scripted_llm(_Monkey(), ask_fn)
    result = run_react_loop(
        user_text=user,
        system_prompt=system,
        execute_fn=execute_fn,
        max_iters=REACT_MAX_ITERS,
        broker=IntentBroker())
    from donna.settings import get_assistant_language

    # Production may lock assistant_language=en; then reply_lang follows the lock.
    if get_assistant_language() == "en":
        assert result.reply_lang == "en"
    else:
        assert result.reply_lang == "fa"
        assert detect_lang(result.final_text) in ("fa", "mixed")
    assert result.iterations <= REACT_MAX_ITERS
    assert any(t.get("tool") == "describe_spatial_scene" for t in result.tool_trace)
    assert "لپ‌تاپ" in result.final_text or "لپ تاپ" in result.final_text
    print(
        "[OK] ReAct FA query about EN visual ->",
        result.final_text[:80].encode("ascii", "backslashreplace").decode("ascii"),
        f"iters={result.iterations}")
    print("     trace=", json.dumps(result.tool_trace, ensure_ascii=True))


def test_react_max_iter_and_tool_error() -> None:
    def ask_fn(_messages):
        return "TOOL: read_vault_memory(key=missing_key)"

    def execute_fn(tc: ToolCall) -> str:
        raise RuntimeError("simulated vault failure")

    patch_scripted_llm(_Monkey(), ask_fn)
    result = run_react_loop(
        user_text="What is my saved IP?",
        system_prompt="You are Donna.\n" + build_agent_system_prompt(
            spatial_block="vis=screen|ui=idle|dom=none@center|scene=[]|intent=",
            labels_csv="",
            profile_summary="{}",
            reply_lang="en"),
        execute_fn=execute_fn,
        max_iters=2,
        broker=IntentBroker())
    assert result.iterations <= 2
    assert "ERROR" in result.tool_trace[0].get("observation", "") or "Tool result" in result.final_text or "ERROR" in result.final_text
    print(f"[OK] tool failure / max-iter safe exit -> \"{result.final_text}\"")


def test_vault_remember_fewshot_path() -> None:
    vault: dict = {}
    responses = [
        "TOOL: write_vault_memory(key=remembered_ip, value=10.0.0.8)",
        "FINAL: Saved IP 10.0.0.8 to memory.",
    ]
    i = {"n": 0}

    def ask_fn(_m):
        out = responses[min(i["n"], len(responses) - 1)]
        i["n"] += 1
        return out

    def execute_fn(tc: ToolCall) -> str:
        if tc.tool_id == "write_vault_memory":
            vault[tc.arguments["key"]] = tc.arguments["value"]
            return f"OK: saved {tc.arguments['key']}={tc.arguments['value']!r}"
        return "OK"

    patch_scripted_llm(_Monkey(), ask_fn)
    result = run_react_loop(
        user_text="Remember this IP address on my screen: 10.0.0.8",
        system_prompt=build_agent_system_prompt(
            spatial_block="vis=screen|ui=idle|dom=none@center|scene=[]|intent=remember",
            labels_csv="",
            profile_summary="{}",
            reply_lang="en"),
        execute_fn=execute_fn,
        max_iters=3,
        broker=IntentBroker())
    assert vault.get("remembered_ip") == "10.0.0.8"
    assert "10.0.0.8" in result.final_text
    print("[OK] write_vault_memory agentic path")


def test_schedule_routing_insotter() -> None:
    """Trace 1: mangled STT schedule query must route to web_search (FIFA bias)."""
    broker = IntentBroker()
    prompt = build_agent_system_prompt(
        spatial_block="vis=screen|ui=idle|dom=book@center|scene=[book@center(a=0.4,d=0.01)]|intent=",
        labels_csv="book",
        profile_summary="{}",
        reply_lang="en")
    assert "Routing guardrails" in prompt or "FORBID describe_spatial_scene" in prompt
    assert "context-aware" in prompt.lower() or "What hour" in prompt

    utter = "When is the next InSotter match?"
    call = broker.parse_utterance(utter)
    assert call is not None, "expected web_search routing for InSotter schedule query"
    assert call.tool_id == "web_search", f"got {call.tool_id}"
    # Must not prefer vision despite book in SpatialIR context.
    spatial = broker.parse_utterance("One is the next before match.")
    assert spatial is not None and spatial.tool_id == "web_search"

    captured: list[str] = []

    def ask_fn(messages):
        # First LLM step should be free to choose; we script web_search + FIFA correction.
        if len(captured) == 0:
            captured.append("tool")
            return "TOOL: web_search(query=FIFA World Cup next match schedule)"
        return (
            "FINAL: The next FIFA World Cup runs June 11–July 19, 2026 "
            "(interpreting InSotter as FIFA)."
        )

    def execute_fn(tc: ToolCall) -> str:
        assert tc.tool_id == "web_search"
        q = str(tc.arguments.get("query") or "")
        assert "FIFA" in q.upper() or "world cup" in q.lower()
        return (
            "Observation: FIFA World Cup 2026 begins June 11, 2026 "
            "(source: fifa.com)."
        )

    patch_scripted_llm(_Monkey(), ask_fn)
    result = run_react_loop(
        user_text=utter,
        system_prompt=prompt,
        execute_fn=execute_fn,
        max_iters=3,
        broker=broker,
        enable_reflection=False)
    assert any(t.get("tool") == "web_search" for t in result.tool_trace)
    assert "June" in result.final_text or "FIFA" in result.final_text
    print("[OK] InSotter schedule -> web_search (FIFA-corrected)")


def test_multiturn_hour_followup_research() -> None:
    """Trace 2: follow-up 'What hour?' with Turn-2 history must re-search, not FINAL-fail."""
    broker = IntentBroker()
    hour = broker.parse_utterance("What hour is the match?")
    assert hour is not None and hour.tool_id == "web_search"

    prior = [
        {
            "role": "user",
            "content": "When is the next FIFA match like FIFA and InSotter?",
        },
        {
            "role": "assistant",
            "content": "The World Cup starts June 11, 2026 and runs through July 19.",
        },
    ]
    seen_queries: list[str] = []
    history_ok = {"v": False}

    def ask_fn(messages):
        blob = " | ".join(m.get("content", "") for m in messages)
        if "June 11" in blob and "What hour is the match?" in blob:
            history_ok["v"] = True
        if not seen_queries:
            return "TOOL: web_search(query=FIFA World Cup 2026 kickoff times)"
        return "FINAL: Opening matches kick off around 15:00–21:00 local time depending on venue."

    def execute_fn(tc: ToolCall) -> str:
        assert tc.tool_id == "web_search"
        q = str(tc.arguments.get("query") or "")
        seen_queries.append(q)
        assert "FIFA" in q.upper() or "kickoff" in q.lower() or "2026" in q
        return "Observation: FIFA 2026 kickoff windows vary by host city; group matches often 15:00–21:00 local."

    patch_scripted_llm(_Monkey(), ask_fn)
    result = run_react_loop(
        user_text="What hour is the match?",
        system_prompt=build_agent_system_prompt(
            spatial_block="vis=screen|ui=idle|dom=book@center|scene=[book@center(a=0.4,d=0.01)]|intent=",
            labels_csv="book",
            profile_summary="{}",
            reply_lang="en"),
        execute_fn=execute_fn,
        max_iters=3,
        broker=broker,
        prior_messages=prior,
        enable_reflection=False)
    assert history_ok["v"], "Turn-2 answer must be present in ReAct message history"
    assert seen_queries, "expected a follow-up web_search"
    assert "enough information" not in result.final_text.lower()
    assert any(t.get("tool") == "web_search" for t in result.tool_trace)
    print(f"[OK] hour follow-up -> web_search({seen_queries[0]!r})")


def main() -> int:
    test_language_lock_and_spatial_guide()
    test_broker_vault_and_tool_parse()
    test_react_loop_farsi_english_visual()
    test_react_max_iter_and_tool_error()
    test_vault_remember_fewshot_path()
    test_schedule_routing_insotter()
    test_multiturn_hour_followup_research()
    print("\nAll local agentic verification checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
