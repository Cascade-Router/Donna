# Contributing to Donna

Thank you for helping harden a local-first agentic voice OS. Donna prioritizes **low-latency infrastructure**, **strict state isolation**, and **observable graph orchestration**. PRs that bypass verification or mutate local-state contracts will be rejected.

---

## Ground Rules

1. **Do not commit local state** — `vault/`, `execution_jail/`, `logs/`, `.env`, `settings.json`, `*.onnx`, `*.pt`, `*.bin`, ledgers, and device configs are gitignored for a reason.
2. **Respect mode isolation** — Chat mode must not gain tool-jail side effects; Developer paths must not leak into the chat memory buffer.
3. **Tk is main-thread only** — Background workers update the Live Trace exclusively through `emit_trace()` → `gui_telemetry_queue` (see [`docs/telemetry_and_ui.md`](docs/telemetry_and_ui.md)).
4. **Single instance** — Never run two `run.py` processes against the same workspace; the socket lock exists to protect the jail.

---

## Required Gate: Headless E2E State Reachability Analysis

Any PR that adds or changes:

- tool calls,
- Intent Broker / Cascade routes,
- LangGraph or ReAct node branches,
- mode fast-paths,
- ingest → jail wiring,

**must** demonstrate a passing **Headless E2E State Reachability Analysis** before review.

### Method (InputIngest)

1. Ensure a **single** Donna instance is running (`python run.py`).
2. For Chat / mode switches, inject via `.trigger_ask` (Main file trigger).
3. For Developer tool / jail paths:
   - Switch to developer mode.
   - Write the command into `execution_jail/input.txt`.
   - Wake the session (empty `.trigger_ask` or a documented inject) so `task_queue.json` drains.
4. Verify in `logs/donna_runtime.log` (and Live Trace where applicable):
   - expected mode transitions,
   - Cascade / MoA classification when relevant,
   - tool execution and jail completion (`Queue drain finished: N completed`),
   - no dual-writer corruption symptoms.

Reference outcomes and race notes from prior suite runs in `donna_branch_diagnostics.md` (local artifact; not required in Git).

PRs without evidence of this headless reachability pass (log excerpts, harness output, or equivalent CI) will not be merged.

---

## Suggested Workflow

```bash
python -m venv .venv
.\.venv\Scripts\activate          # Windows
pip install -r requirements.txt
python run.py                     # single instance only
# … implement + headless inject via input.txt / .trigger_ask …
pytest -q                         # run relevant unit tests
```

Document new stages with `emit_trace` hooks. Update `docs/architecture.md` or `docs/telemetry_and_ui.md` when you change public contracts.

---

## Pull Request Checklist

- [ ] No secrets or local state files staged
- [ ] Headless E2E State Reachability Analysis passed for new tools / node branches (`input.txt` injection path)
- [ ] Live Trace emissions are queue-based (no cross-thread Tk)
- [ ] Mode / jail invariants preserved
- [ ] Docs updated if behavior or contracts changed

---

## Code of Conduct (engineering)

Prefer minimal diffs, explicit failure modes, and telemetry over silent fallbacks. Donna is infrastructure: correctness under concurrency beats feature surface area.
