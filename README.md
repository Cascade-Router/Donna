# Donna Workspace (CAMGRASPER)

Repo root is the runtime workspace (`DONNA_WORKSPACE == PROJECT_ROOT`).

| Folder | Contents |
|--------|----------|
| `logs/` | `donna_runtime.log`, `donna_conversation.log` |
| `tracker/` | `bug_tracker.json`, `pending_patches/` |
| `execution_jail/` | Filesystem jail (`task_queue.json`, `library/`, fixture copies). Not the Python package. |
| `donna_security/` | Importable security package + `patch_ledger.md` |
| `custom_tools/` | Sole Tool Forge write/load root (ephemeral; wiped on context reset) |
| `cursor_handoffs/` | `donna_handoff.md` (mirrored into `.cursor/instructions/`) |
| `captures/` | Screen captures from OS computer-use |
| `_archive/` | Unused legacy snapshots (not loaded at runtime) |

Promoted tools: `donna/tools/general/` (Git-tracked). Do not merge `execution_jail/` with `donna_security/`.
