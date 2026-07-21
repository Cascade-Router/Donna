"""CustomTkinter Live Trace panel — drains TraceEventBus on the Tk main thread."""

from __future__ import annotations

import time
from typing import Any

import customtkinter as ctk

from donna.ui.trace_bus import TraceEvent, get_trace_bus

_MODE_COLORS = {
    "chat": "#10B981",
    "developer": "#8B5CF6",
    "agentic": "#8B5CF6",
    "vision": "#3B82F6",
    "research": "#F59E0B",
    "idle": "#9CA3AF",
    "routing": "#F59E0B",
    "tool": "#8B5CF6",
    "synthesis": "#10B981",
}

_STATUS_PILLS = {
    "idle": ("[IDLE]", "#9CA3AF"),
    "routing": ("[ROUTING]", "#F59E0B"),
    "tool": ("[TOOL]", "#8B5CF6"),
    "synthesis": ("[SYNTHESIS]", "#10B981"),
    "active": ("[ACTIVE]", "#6366F1"),
}


class LiveTracePanel(ctk.CTkFrame):
    """Dark Live Trace dashboard: status pill, timeline, payload viewer."""

    def __init__(self, master: Any, *, poll_ms: int = 50) -> None:
        super().__init__(master, fg_color=("gray94", "#0b1220"))
        self._poll_ms = max(30, int(poll_ms))
        self._phase = "idle"
        self._mode = "chat"
        self._node_t0: dict[str, float] = {}
        self._timeline_rows: list[ctk.CTkFrame] = []
        self._max_rows = 80
        self._build()
        self.after(self._poll_ms, self._drain_trace_queue)

    def _build(self) -> None:
        header = ctk.CTkFrame(self, fg_color=("gray90", "#121a2b"), corner_radius=0)
        header.pack(fill="x")
        self.pill = ctk.CTkLabel(
            header,
            text="[IDLE]",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=_STATUS_PILLS["idle"][1],
            fg_color=("gray85", "#1a2438"),
            corner_radius=12,
            padx=12,
            pady=6,
        )
        self.pill.pack(side="left", padx=12, pady=10)
        self.mode_label = ctk.CTkLabel(
            header,
            text="Mode: Chat",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=_MODE_COLORS["chat"],
            anchor="w",
        )
        self.mode_label.pack(side="left", padx=8, pady=10)
        ctk.CTkLabel(
            header,
            text="LangGraph Live Trace",
            text_color=("gray40", "gray60"),
            font=ctk.CTkFont(size=12),
        ).pack(side="right", padx=14, pady=10)

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=10, pady=(4, 10))
        body.grid_columnconfigure(0, weight=3)
        body.grid_columnconfigure(1, weight=2)
        body.grid_rowconfigure(0, weight=1)

        left = ctk.CTkFrame(body, fg_color=("gray92", "#121a2b"))
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        ctk.CTkLabel(
            left,
            text="State Graph Timeline",
            anchor="w",
            font=ctk.CTkFont(size=13, weight="bold"),
        ).pack(fill="x", padx=10, pady=(10, 4))
        self.timeline = ctk.CTkScrollableFrame(left, fg_color="transparent")
        self.timeline.pack(fill="both", expand=True, padx=6, pady=(0, 8))

        right = ctk.CTkFrame(body, fg_color=("gray92", "#121a2b"))
        right.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
        ctk.CTkLabel(
            right,
            text="Payload Viewer",
            anchor="w",
            font=ctk.CTkFont(size=13, weight="bold"),
        ).pack(fill="x", padx=10, pady=(10, 4))
        self.payload = ctk.CTkTextbox(
            right,
            wrap="word",
            font=ctk.CTkFont(family="Consolas", size=12),
            fg_color=("gray96", "#0b1220"),
        )
        self.payload.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self.payload.insert("1.0", "Waiting for LangGraph transitions…\n")
        self.payload.configure(state="disabled")

    def _set_pill(self, phase: str, *, tool: str = "") -> None:
        self._phase = phase
        if phase == "tool" and tool:
            label = f"[TOOL: {tool}]"
            color = _MODE_COLORS["tool"]
        else:
            label, color = _STATUS_PILLS.get(phase, _STATUS_PILLS["active"])
        try:
            self.pill.configure(text=label, text_color=color)
        except Exception:  # noqa: BLE001
            pass

    def _set_mode(self, mode: str) -> None:
        key = (mode or "chat").strip().lower() or "chat"
        if key == "agentic":
            key = "developer"
        self._mode = key
        color = _MODE_COLORS.get(key, _MODE_COLORS["idle"])
        try:
            self.mode_label.configure(
                text=f"Mode: {key.title()}",
                text_color=color,
            )
        except Exception:  # noqa: BLE001
            pass

    def _append_timeline(self, line: str, *, accent: str | None = None) -> None:
        row = ctk.CTkFrame(self.timeline, fg_color=("gray88", "#1a2438"), corner_radius=6)
        row.pack(fill="x", padx=2, pady=2)
        ctk.CTkLabel(
            row,
            text=line,
            anchor="w",
            justify="left",
            font=ctk.CTkFont(size=12),
            text_color=accent or ("gray20", "gray85"),
        ).pack(fill="x", padx=8, pady=6)
        self._timeline_rows.append(row)
        while len(self._timeline_rows) > self._max_rows:
            old = self._timeline_rows.pop(0)
            try:
                old.destroy()
            except Exception:  # noqa: BLE001
                pass
        try:
            self.timeline._parent_canvas.yview_moveto(1.0)  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001
            pass

    def _set_payload(self, text: str) -> None:
        snippet = (text or "").strip()
        if not snippet:
            return
        try:
            self.payload.configure(state="normal")
            self.payload.delete("1.0", "end")
            self.payload.insert("1.0", snippet + "\n")
            self.payload.configure(state="disabled")
        except Exception:  # noqa: BLE001
            pass

    def _handle_event(self, event: TraceEvent) -> None:
        if event.mode:
            self._set_mode(event.mode)
        et = event.event_type
        node = event.node or "node"
        if et == "node_enter":
            self._node_t0[node] = time.perf_counter()
            phase = "routing" if "router" in node.lower() or node.lower() == "agent" else "active"
            if "tool" in node.lower():
                phase = "tool"
            if "synth" in node.lower() or "finish" in node.lower():
                phase = "synthesis"
            self._set_pill(phase, tool=event.tool)
            self._append_timeline(
                f"→ enter {node}",
                accent=_MODE_COLORS.get(self._mode),
            )
        elif et == "node_exit":
            t0 = self._node_t0.pop(node, None)
            ms = event.latency_ms
            if ms is None and t0 is not None:
                ms = (time.perf_counter() - t0) * 1000.0
            latency = f" ({ms:.0f}ms)" if ms is not None else ""
            self._append_timeline(f"← exit {node}{latency}")
            if event.payload:
                self._set_payload(event.payload)
        elif et == "tool_execution":
            tool = event.tool or node or "tool"
            self._set_pill("tool", tool=tool)
            ms = f" ({event.latency_ms:.0f}ms)" if event.latency_ms is not None else ""
            self._append_timeline(
                f"Router Node → Tool: {tool}{ms}",
                accent=_MODE_COLORS["tool"],
            )
            if event.payload:
                self._set_payload(event.payload)
            elif event.message:
                self._set_payload(event.message)
        elif et == "state_update":
            keys = ", ".join(event.state_keys) if event.state_keys else "state"
            self._append_timeline(f"state ← {keys}")
            if event.payload:
                self._set_payload(event.payload)
        elif et == "mode":
            self._set_mode(event.mode or event.message)
            self._append_timeline(event.message or f"mode={self._mode}")
        else:
            if event.message:
                self._append_timeline(event.message)
            if event.payload:
                self._set_payload(event.payload)

    def _drain_trace_queue(self) -> None:
        """Poll TraceEventBus on the Tk main thread (never from worker threads)."""
        if not self.winfo_exists():
            return
        try:
            for event in get_trace_bus().drain(max_items=48):
                self._handle_event(event)
        except Exception:  # noqa: BLE001
            pass
        try:
            self.after(self._poll_ms, self._drain_trace_queue)
        except Exception:  # noqa: BLE001
            pass


class LiveTraceWindow(ctk.CTkToplevel):
    """Optional standalone Live Trace window."""

    def __init__(self, master: Any | None = None) -> None:
        super().__init__(master)
        self.title("Donna — Live Trace")
        self.geometry("820x520")
        self.minsize(640, 400)
        ctk.set_appearance_mode("dark")
        self.panel = LiveTracePanel(self)
        self.panel.pack(fill="both", expand=True)
