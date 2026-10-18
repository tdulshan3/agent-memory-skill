---
name: agent-memory
description: "Maintain a persistent two-tier linked-map memory system (MEMORY.md index + typed topic .md files) across sessions and projects. Captures non-obvious findings, architecture decisions, dead ends not to retry, completed progress, what's left / open blockers, user preferences, and linked chat summaries. Activate at the start of project tasks to load prior context and after findings, fixes, or milestones to update project status."
metadata:
  version: "1.0.0"
  harnesses: "Antigravity, OpenCode, Cursor, Windsurf, Cline/Roo (excludes Claude Code & Codex by default on install, as they have built-in memory)"
---

# Agent Linked-Map Memory Skill (`agent-memory`)

This skill gives any AI coding harness a persistent, structured **two-tier linked-map memory** modeled on Claude Code's per-project `MEMORY.md` architecture, extended with explicit **project status tracking ("what's left")**, **dead-end prevention**, and **cross-session chat links**.

`SKILL_DIR` refers to the directory containing this `SKILL.md`.

---

## 1. Architecture: Two-Tier Linked Map

Never dump raw multi-paragraph notes into a single giant file. Memory is split into two tiers so the index stays tiny enough to auto-load on every turn while detailed topic files are read on demand:

```text
<memory-root>/
├── MEMORY.md                        # Tier 1: Concise 1-line-per-link index map (<200 lines)
├── <project-or-topic-slug>.md       # Tier 2: Detailed memory node with YAML frontmatter
└── projects/                        # Optional per-project subdirectories for multi-repo setups
    └── <project-slug>/
        ├── MEMORY.md
        └── <topic-slug>.md
```

### Tier 1: `MEMORY.md` (The Index Map)
- **Strictly an index of Markdown links** — never write raw paragraphs or unlinked notes directly inside `MEMORY.md`.
- **One line per entry** (keep under ~150 characters per line):
  ```markdown
  - [Short Descriptive Title](file:///absolute/or/relative/path/to/topic-slug.md) — one-line hook with the non-obvious takeaway
  ```
- **Sections in `MEMORY.md`**:
  1. `## Projects & System Status Map` — links to active project/topic `.md` files.
  2. `## Existing Cross-Agent Memory Maps` *(optional bridge)* — read-only links to `~/.claude/projects/*/memory/MEMORY.md` or `~/.codex/memories/memory_summary.md` if present on the host.
  3. `## Chat History Map` — reverse-chronological links to conversations (`- [Chat Title](conversation://<id>) (YYYY-MM-DD) — one-line summary of outcome & what's left`).

### Tier 2: `<topic-slug>.md` (Individual Memory Files)
Every topic file **must** begin with YAML frontmatter:

```yaml
---
name: <kebab-case-slug>
description: "<Specific one-line summary of what is inside and when to read it — used to decide relevance>"
metadata:
  node_type: memory
  type: <project|feedback|user|reference>
  originSessionId: <conversation-or-session-id>
  modified: <YYYY-MM-DDTHH:MM:SSZ>
---
```

---

## 2. The Four Memory Types (`metadata.type`)

Choose the `type` that matches the knowledge being persisted (see `SKILL_DIR/references/claude-memory-format.md` for complete templates):

| Type | What to Store | Required Body Structure |
|---|---|---|
| **`project`** | Architecture overrides, non-obvious findings, shipped milestones, **what's left / open blockers**, **dead ends not to retry**, and unconfirmed product defaults. | 1. **Summary & Current State** (with explicit `YYYY-MM-DD` dates & commit/file pointers)<br>2. **Key Findings & Invariants**<br>3. **Dead Ends (Do Not Retry)**<br>4. **Completed Progress** (`- [x] ...`)<br>5. **What's Left / Open Blockers** (`- [ ] ...`)<br>6. **`**Why:**`** & **`**How to apply:**`**<br>7. **`Related:`** (`[[other-slug]]` and chat links) |
| **`feedback`** | User corrections ("don't do X") and confirmed workflows ("yes, always do Y"). | 1. **The Rule** (clear, imperative statement upfront)<br>2. **`**Why:**`** (the incident, constraint, or preference behind it)<br>3. **`**How to apply:**`** (when and where to enforce it) |
| **`user`** | User role, hardware/LAN environment, performance vs. conventions trade-offs, communication preferences. | Bullet points of stated preferences (with `YYYY-MM-DD` dates) followed by **`**Why:**`** and **`**How to apply:**`**. |
| **`reference`** | Pointers to external systems: SSH targets, ports, VM instances, Figma file keys, dashboards, API quirks. | Direct connection details, URLs/keys, auth/firewall caveats, and verification commands. |

---

## 3. Workflow: When & How to Use This Skill

### Step A — At the Start of a Task (Read Before Acting)
1. Check `MEMORY.md` (already inlined via global rules or located at `~/.gemini/antigravity/memory/MEMORY.md` / `<workspace>/.agents/memory/MEMORY.md`).
2. Open any linked `<topic-slug>.md` file whose title or hook matches the current project or task.
3. If the project also has a read-only bridge link under `Existing Cross-Agent Memory Maps` (e.g., `~/.claude/projects/<slug>/memory/MEMORY.md`), read that index and relevant topic files so you inherit all prior decisions, invariants, and dead ends.
4. **Verify before trusting**: Memory records what was true when written. If a memory names a specific file, function, or service state, verify it before editing.

### Step B — During & At the End of a Task (Save & Update)
Update the memory map whenever any of the following happen:
- You discover a **non-obvious root cause, hardware/network constraint, or invariant**.
- You hit a **dead end** that future sessions should never waste time retrying.
- You complete a milestone or leave **remaining work / open blockers ("what's left")**.
- The user gives a **correction or preference** (`type: feedback` or `type: user`).

Use either your file editing tools directly or the bundled CLI helper:

```bash
python3 SKILL_DIR/scripts/memory_ctl.py status
python3 SKILL_DIR/scripts/memory_ctl.py sync-chats
python3 SKILL_DIR/scripts/memory_ctl.py audit
```

---

## 4. Golden Discipline Rules (Prevent Memory Rot)

1. **No Code/Git Duplication**: Do **not** copy full source files, directory trees, or standard `git log` history into memory files. Record *why* a design was chosen, *invariants* the code alone cannot express, *dead ends*, *external topology*, and *what's left*.
2. **Update In-Place Instead of Appending Contradictions**: Before creating a new `<topic-slug>.md`, check `MEMORY.md` for an existing topic file. Update completed items (`[ ]` -> `[x]`), remove obsolete blockers, and bump `metadata.modified`.
3. **Explicit Dates Only**: Convert relative dates (`"today"`, `"yesterday"`, `"next Friday"`) into ISO dates (`2026-10-18`) so the note remains unambiguous months later.
4. **Respect Claude & Codex Native Memory**: Do not overwrite `~/.claude/projects/*/memory/` or `~/.codex/memories/` from another harness unless explicitly asked—treat them as read-only upstream bridges and write your harness updates to the configured memory directory.
