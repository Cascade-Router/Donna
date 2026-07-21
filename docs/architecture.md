# Donna Architecture

Donna is a **local-first agentic voice OS**: a multi-threaded perception plane, a mode-gated cognitive router, and a filesystem execution jail under a single-instance process lock. This document describes the production control paths relevant to operators and contributors.

---

## 1. Multi-Threaded Ingestion Pipeline

Donna never blocks the cognitive loop on a single I/O source. Two complementary ingest planes feed the conversation finite-state machine.

### 1.1 MicIngest (continuous audio producer)

| Concern | Behavior |
|---------|----------|
| Thread | `MicIngest` daemon — single shared `sounddevice` `InputStream` |
| Format | 16 kHz mono float frames (wake + VAD consumers) |
| Role | Owns mic open/close; pushes frames onto an internal audio buffer queue |
| Recovery | Soft reopen on PortAudio faults; restart signal when GUI changes `mic_id` |

Downstream consumers:

1. **WakeWord** — OpenWakeWord on the live ring buffer; on hit, sets `is_recording` and yields to VAD.
2. **VAD / Conversation** — WebRTC VAD consumes frames for utterance capture → Whisper STT (JIT / background-loaded) → brain turn.

MicIngest is deliberately **producer-only**: it does not call the LLM, mutate modes, or write the execution jail.

### 1.2 InputIngest (headless / automation plane)

| Concern | Behavior |
|---------|----------|
| Watcher | Polls `execution_jail/input.txt` (silent when empty; ~0.75s back-off) |
| Conversion | Paragraph-splits free-form text → pending objects in `execution_jail/task_queue.json` |
| Session wake | Empty or non-empty `.trigger_ask` on the Main loop starts a conversation session |

**Mode gate:** `allows_react_task_jail()` is **false in Chat mode**. Pending jail tasks drain only when the agent is in a non-chat mode (typically **Developer**). This prevents casual chat turns from executing tool-jail payloads.

Equivalent session inject (including Chat / mode switches): write text to `.trigger_ask` — Main sets an injected transcript and arms the conversation loop without Whisper.

```text
input.txt ──► InputIngest ──► task_queue.json ──► drain on session (non-chat)
.trigger_ask ──► Main ──► injected question / listen ──► Conversation FSM
```

---

## 2. Cascade Router & Mode Map

The **Cascade Router** (`donna/cascade_router.py`) classifies complexity and selects local backends. Modes (`donna/agentic.py`) are a hard process-wide switch that changes which graph edges are legal.

| Mode | Color (Live Trace) | Cognitive path | Tool jail |
|------|--------------------|----------------|-----------|
| **Chat** | `#10B981` | Lightweight local `llama3.2`; rolling chat memory only | **Blocked** |
| **Developer** | `#8B5CF6` | ReAct / LangGraph tool loop; high-complexity → MoA (`deepseek-r1`) foresight | **Allowed** |
| **Vision** | `#3B82F6` | Scaffolded; enables JIT YOLOv8 tracker path | Allowed (scaffold) |
| **Research** | `#F59E0B` | Scaffolded research heuristics on cascade | Allowed (scaffold) |

### Fast-paths (no LLM)

Mode switches (`switch to chat/developer/vision/research mode`) and `clear chat memory` short-circuit in the conversation handler: set state, speak canned ack, emit telemetry — **zero** Ollama round-trip.

### Developer / MoA path

1. Intent Broker may force-route tools such as `draft_cursor_prompt`.
2. Cascade foresight tags high-complexity → `route=moa` with DeepSeek-R1 as reasoner.
3. Bound-tools ReAct iterations stay on the fast local chat model for reliable `bind_tools` on Ollama; R1 is reserved for MoA stages.

---

## 3. Single-Instance Socket Lock

**Bind address:** `127.0.0.1:47473` (exclusive TCP listen; no `SO_REUSEADDR`)

Implemented at process entry in `run.py` before `core_agent.main()`:

- First instance holds the socket for the process lifetime.
- Second instance prints:

  `[Main] ERROR: Another instance of Donna is already running. Aborting to protect execution jail.`

  and exits with code `1`.

### Why this is critical

Donna’s durable control plane lives on disk:

| Artifact | Risk under concurrent writers |
|----------|-------------------------------|
| `execution_jail/task_queue.json` | Double-drain, lost completions, corrupt JSON |
| `execution_jail/input.txt` | Raced clear/ingest; duplicate or dropped tasks |
| `donna_security/patch_ledger.md` | Interleaved ticket writes; `Errno 22` / failed drains |
| `.trigger_ask` | Two Mains consuming one inject; duplicated sessions |

Headless E2E and Startup-registered `pythonw` launches make multi-instance races likely without a lock. The socket gate is **fail-closed infrastructure**, not a UX nicety.

> Note: an additional singleton bind may exist inside the agent for legacy/dashboard purposes. The **advertised release lock** for jail protection is **`127.0.0.1:47473`** in `run.py`.

---

## 4. Thread Topology (summary)

| Thread / owner | Responsibility |
|----------------|----------------|
| Tk main (`DonnaGUI.mainloop`) | Live Trace + settings; only thread that mutates widgets |
| AgentLoop | Wake/VAD/Whisper/brain/TTS orchestration |
| MicIngest | Mic producer |
| InputIngest watcher | `input.txt` → queue |
| Tracker | JIT YOLO when Vision (or warmed) |
| System tray (`pystray`) | Open Settings / Quit |

Telemetry contract between workers and UI: [`telemetry_and_ui.md`](telemetry_and_ui.md).
