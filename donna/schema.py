"""Leaf shared types for Donna — no imports from core_agent / agentic / tools workers."""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from typing import Annotated, Any, Literal, TypedDict

from langgraph.graph.message import add_messages

TraceEventType = Literal[
    "node_enter",
    "node_exit",
    "tool_execution",
    "state_update",
    "mode",
    "status",
]


@dataclass(frozen=True)
class TraceEvent:
    """Normalized bus payload for Live Trace rendering."""

    event_type: TraceEventType
    node: str = ""
    message: str = ""
    mode: str = ""
    tool: str = ""
    latency_ms: float | None = None
    payload: str = ""
    state_keys: tuple[str, ...] = ()
    ts: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["state_keys"] = list(self.state_keys)
        return data


# Back-compat aliases.
NodeEnterEvent = TraceEvent
NodeExitEvent = TraceEvent
ToolExecutionEvent = TraceEvent
StateUpdateEvent = TraceEvent


@dataclass
class AgenticResult:
    final_text: str
    iterations: int
    tool_trace: list[dict[str, Any]]
    reply_lang: str
    reflection: dict[str, Any] | None = None
    reflection_ms: float = 0.0
    had_errors: bool = False
    tts_streamed: bool = False


class ReactGraphState(TypedDict):
    """LangGraph ReAct state — messages use add_messages reducer."""

    messages: Annotated[list, add_messages]
    iterations: int
    last_obs: str
    final_raw: str
    halt: bool
    # Deduped broker merge (mode + forced + explicit ids); agent node binds exactly this.
    always_include: list[str]
