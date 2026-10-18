# Agent Linked-Map Memory Skill (`agent-memory`)

A portable Agent Skill (`SKILL.md` + CLI helper) that brings Claude Code's **two-tier linked-map memory architecture** (`MEMORY.md` index + typed `<topic-slug>.md` files) to AI coding harnesses that lack built-in structured project memory, with explicit support for tracking **findings**, **dead ends not to retry**, **completed progress**, **what's left / open blockers**, and **linked chat history**.

---

## Harness Compatibility & Install Exceptions

| Harness | Target Path | Behavior in `./install.sh` |
|---|---|---|
| **Antigravity** | `~/.gemini/config/skills/agent-memory` | **Installed** (plus `~/.gemini/antigravity/memory/MEMORY.md` inlined via `~/.gemini/config/rules/AGENTS.md`) |
| **OpenCode** | `~/.config/opencode/skills/agent-memory` | **Installed** (if `~/.config/opencode` exists) |
| **Generic `.agents`** | `~/.agents/skills/agent-memory` | **Installed** (Cursor, Windsurf, Cline, Roo) |
| **Claude Code** | `~/.claude` | **Skipped (Exception)** — already has native `~/.claude/projects/*/memory/MEMORY.md` |
| **OpenAI Codex** | `~/.codex` | **Skipped (Exception)** — already has native `~/.codex/memories/` |

> **Read-Only Upstream Bridge:** While `./install.sh` never touches `~/.claude` or `~/.codex`, the skill and `memory_ctl.py bridge` allow other harnesses (like Antigravity) to link and read existing Claude/Codex project memories in read-only mode so prior project context is never lost.

---

## Repository Structure

```text
agent-memory-skill/
├── install.sh                                   # Cross-harness installer (excludes claude & codex)
├── README.md                                    # Documentation
└── agent-memory/
    ├── SKILL.md                                 # Main skill instructions & workflow
    ├── references/
    │   └── claude-memory-format.md              # Templates for MEMORY.md and all 4 memory types
    └── scripts/
        └── memory_ctl.py                        # Zero-dependency CLI for status, audit, chat sync & bridging
```

---

## Quick Start

```bash
# Install into supported harnesses (skips Claude Code & Codex)
./install.sh

# Check installation status, index budget, and topic files
./install.sh --status

# Run link & frontmatter audit on MEMORY.md
python3 agent-memory/scripts/memory_ctl.py audit

# List recent Antigravity conversations as Markdown links
python3 agent-memory/scripts/memory_ctl.py sync-chats

# List read-only Claude Code & Codex memory indexes on this machine
python3 agent-memory/scripts/memory_ctl.py bridge
```

---

## Two-Tier Memory Design

1. **`MEMORY.md` (The Index Map — `<200` lines / `<24 KB`)**
   - Strictly a concise index of 1-line Markdown pointers (`- [Title](path.md) — one-line hook`).
   - Automatically inlined into the agent's context via global rules (`@[MEMORY.md](...)`).
2. **`<topic-slug>.md` (Typed Memory Nodes — Read On-Demand)**
   - Uses YAML frontmatter (`name`, `description`, `metadata.node_type: memory`, `metadata.type`, `metadata.originSessionId`, `metadata.modified`).
   - Supports 4 memory types:
     - `project`: Current state, key findings/invariants, dead ends not to retry, completed progress, what's left / open blockers, `**Why:**`, and `**How to apply:**`.
     - `feedback`: User corrections and confirmed practices (`Rule` + `**Why:**` + `**How to apply:**`).
     - `user`: Hardware, environment, and workflow trade-off preferences.
     - `reference`: External system pointers (SSH hosts/keys, ports, Figma keys, cloud VMs).
