# Agent Linked-Map Memory Skill (`agent-memory`)

A portable Agent Skill (`SKILL.md` + a zero-dependency Python CLI) that gives every coding harness **one shared, per-project memory**, in the same two-tier format as Claude Code's memory: a `MEMORY.md` index plus typed `<topic-slug>.md` files. It records findings, dead ends not to retry, completed progress, what's left, and user corrections.

- **Inside each project**, the way Claude Code keeps `.claude/`: `<project>/.agent/memory/`. Cross-project memory goes in `~/.agent/memory/`.
- **Seeded from Claude Code, newest edit wins**: a file in `~/.claude/projects/<slug>/memory/` is copied in only when Claude edited it after the `.agent` copy. Otherwise nothing happens.
- **Starts on its own**: each harness's always-loaded rules file tells the agent to run `recall` before its first action in every session. No one has to ask for it.
- **Claude Code and Codex are left alone**: both already have built-in memory. Claude Code's memory is only ever read.

---

## Layout

```text
<project>/.agent/
├── memory/
│   ├── MEMORY.md               # index: one line per topic file (loaded every session)
│   ├── <topic-slug>.md         # typed memory with YAML frontmatter
│   └── .claude-sync.json       # which Claude Code files were copied, and their hashes
└── rules/agent-memory.md       # Antigravity auto-loads .agent/rules/*.md, so it inlines the index

~/.agent/memory/                # cross-project memory (the home folder's own .agent)
```

- **Project** means the git root of the working directory. For linked worktrees it is the main worktree, so they all share one memory. Outside git it is the working directory itself.
- **Out of git**: `/.agent/memory/` and `/.agent/rules/agent-memory.md` are added to `.git/info/exclude`, so nothing is committed and `git status` stays clean. To share memory with your team, remove those lines.
- **`<slug>`** is Claude Code's encoding of the project path: every non-alphanumeric character becomes `-`.

### How the Claude Code sync behaves

The edit times are compared before anything is copied. Copying is one way: `~/.claude` and `~/.codex` are only ever read, and `memory_ctl.py` refuses to write inside them.

| Situation | Result |
|---|---|
| File exists only in Claude Code | Copied in, and its index line is added |
| Claude's file was edited **after** the `.agent` copy | Copied in (it keeps Claude's edit time) |
| The `.agent` copy was edited after Claude's file | Nothing happens |
| You deleted a copied file | Nothing happens, unless Claude edits it again later |
| Claude Code deleted a file | Nothing happens |
| Claude's `MEMORY.md` was edited after the `.agent` one | Claude's lines are added or updated; your own lines stay |

`sync-claude --force` copies every Claude file regardless of time.

---

## Harness Support

`./install.sh` handles every harness it finds on the machine:

| Harness | Skill link | Auto-start rules (always loaded) |
|---|---|---|
| **Antigravity** | `~/.gemini/config/skills/` | `~/.gemini/config/rules/AGENTS.md` (also `@`-imports `~/.agent/memory/MEMORY.md`), plus each project's `.agent/rules/agent-memory.md` |
| **Hermes** | `~/.hermes/skills/` | `~/.hermes/SOUL.md` |
| **dsh** (DeepSeek) | `~/.agents/skills/` | `~/.dsh/AGENTS.md` |
| **Qwen Code** | `~/.agents/skills/` | `~/.qwen/QWEN.md` |
| **OpenClaw** | `~/.agents/skills/` | `~/.openclaw/workspace/AGENTS.md` |
| **OpenCode** | `~/.agents/skills/` | `~/.config/opencode/AGENTS.md` |
| **Cursor, Windsurf, Cline, Roo** | `~/.agents/skills/` | — (add the rules block to their user rules yourself) |
| **Claude Code** | — | **Skipped**: built-in `~/.claude/projects/<slug>/memory/` |
| **OpenAI Codex** | — | **Skipped**: built-in `~/.codex/memories/` |

The rules block sits between `<!-- agent-memory:begin -->` and `<!-- agent-memory:end -->`. Re-running the installer updates it in place, and `--uninstall` removes it. Everything else in those files is left alone.

---

## Quick Start

```bash
./install.sh              # link the skill, add auto-start rules, copy all Claude Code memory
./install.sh --status     # what is installed where, and an audit of ~/.agent/memory
./install.sh --uninstall  # remove links and rules blocks (memory files are kept)

CTL="python3 agent-memory/scripts/memory_ctl.py"
$CTL recall               # what agents run automatically: sync, then print both indexes
$CTL where                # detected harness, project root, memory dirs, Claude source
$CTL sync-claude --all    # refresh every Claude Code project into its .agent/memory
$CTL audit                # broken links, orphan files, frontmatter (add --global for ~/.agent)
$CTL bridge               # list every Claude Code / Codex memory index on this machine
```

---

## Repository Structure

```text
agent-memory-skill/
├── install.sh                              # Cross-harness installer (skips Claude Code & Codex)
├── README.md
└── agent-memory/
    ├── SKILL.md                            # Skill instructions & workflow
    ├── references/
    │   └── claude-memory-format.md         # Templates for MEMORY.md and the 4 memory types
    └── scripts/
        └── memory_ctl.py                   # recall, sync-claude, status, audit, bridge, sync-chats
```

---

## Memory Format

1. **`MEMORY.md`** is the index: under 200 lines and 24 KB, with one `- [Title](topic-slug.md) — hook` line per topic file and relative links. It is never a place for paragraphs.
2. **`<topic-slug>.md`** files carry YAML frontmatter compatible with Claude Code: `name`, `description`, `metadata.type`, and optionally `metadata.modified` and `metadata.originSessionId`. There are four types:
   - `project`: current state, key findings and invariants, dead ends, completed progress, what's left, `**Why:**`, `**How to apply:**`.
   - `feedback`: the rule, `**Why:**`, `**How to apply:**`.
   - `user`: role, environment, trade-off and communication preferences.
   - `reference`: hosts, ports, dashboards, design files, tickets.

Memory written by v1 of this skill in `~/.gemini/antigravity/memory/` is copied into `~/.agent/memory/` on first run. The original is left in place.
