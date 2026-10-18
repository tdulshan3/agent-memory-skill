---
name: agent-memory
description: "Persistent project memory shared by every coding harness except Claude Code and Codex, kept inside each project in <project>/.agent/memory/ (like Claude Code's .claude/) in Claude Code's two-tier format: a MEMORY.md index plus typed topic .md files. Claude Code files from ~/.claude/projects/<slug>/memory/ are copied in whenever Claude edited them more recently than the local copy. Use it automatically, without being asked, at the start of every session and task in any project to load prior findings, decisions, dead ends, and what's left, and after findings, fixes, corrections, or milestones to save them."
metadata:
  version: "3.0.0"
  harnesses: "Antigravity, Hermes, dsh (DeepSeek), Qwen Code, OpenClaw, OpenCode, Cursor, Windsurf, Cline, Roo. Claude Code and Codex keep their own built-in memory."
---

# Agent Linked-Map Memory Skill (`agent-memory`)

One memory for all your harnesses, stored in each project the way Claude Code keeps `.claude/`, in the same format as Claude Code's own memory. Anything Claude Code has already learned about a project is copied in, so every other harness starts with it.

`SKILL_DIR` is the directory containing this `SKILL.md`. `CTL` below means `python3 SKILL_DIR/scripts/memory_ctl.py`.

---

## 1. Where memory lives

```text
<project>/.agent/
├── memory/                     # this project's memory, shared by every harness
│   ├── MEMORY.md               # index: one line per topic file
│   ├── <topic-slug>.md         # one fact or topic per file
│   └── .claude-sync.json       # sync bookkeeping; do not edit
└── rules/agent-memory.md       # makes Antigravity load the index automatically

~/.agent/memory/                # cross-project memory: user profile, feedback, shared references
```

- **The project** is the git root of the working directory (the main worktree, so all worktrees share one memory). Outside git it is the working directory itself. `~/.agent/memory/` is simply the home folder's own `.agent`.
- **The memory is kept out of git.** Its paths are added to `.git/info/exclude`, not `.gitignore`, so nothing shows up in `git status` and nothing is committed. To share memory with a team, delete those lines and commit `.agent/memory/`.
- **Claude Code memory is copied in, newest edit wins, one way only.** `<slug>` is the project path with every non-alphanumeric character replaced by `-`. For each file in `~/.claude/projects/<slug>/memory/`, the edit times are compared first:
  - Claude's file was edited after the `.agent` copy, or there is no copy yet: it is copied in.
  - The `.agent` copy is newer: nothing happens.
  - A file you deleted here comes back only if Claude edits it again.
  - Claude deleting a file deletes nothing here.
  Index lines follow the same rule.
- **Never write into `~/.claude/` or `~/.codex/`.** They belong to Claude Code and Codex, whose built-in memory this skill does not replace.

---

## 2. Workflow (automatic, never wait to be asked)

### A. At the start of every session, and whenever you switch projects

1. Run `CTL recall`. If the project is not the current directory, add `--project <path>`. The command:
   - syncs Claude Code's memory into `<project>/.agent/memory/` and `~/.agent/memory/`;
   - prints both indexes with their absolute paths.
2. Open the topic files whose title or hook matches the task. Index links are relative to the directory of the index that contains them.
3. **Verify before trusting.** Memory records what was true when it was written. If a memory names a file, function, flag, or service state, check that it still exists before acting on it.

### B. During and at the end of a task

Save memory when any of these happen:
- You find a **non-obvious root cause, constraint, or invariant**.
- You hit a **dead end** that future sessions should not retry.
- You finish a milestone or leave **remaining work or open blockers**.
- The user gives a **correction or preference**, or confirms a non-obvious approach.

How to save:
1. Check the index for an existing topic file that covers it, and **update that file** rather than creating a duplicate. Delete memories that turned out to be wrong.
2. Otherwise, write a new `<topic-slug>.md` with the frontmatter below:
   - in `<project>/.agent/memory/` for project knowledge;
   - in `~/.agent/memory/` for user preferences and feedback that apply in every project.
3. Add one line to that directory's `MEMORY.md`: `- [Title](topic-slug.md) — one-line hook`. Use a relative link and keep the line under about 150 characters.
4. Run `CTL audit` (project) or `CTL audit --global` to check links and frontmatter.

Do not save:
- what the repo already records: code structure, git history, README or AGENTS.md content;
- what only matters to the current conversation.

---

## 3. File format (Claude Code compatible)

### `MEMORY.md`, the index

- Contains **only one-line links**, never paragraphs: `- [Short Title](topic-slug.md) — the non-obvious takeaway`.
- Stays under 200 lines and 24 KB, because it is loaded at the start of every session.
- Indexes seeded from Claude Code are a flat list; keep new lines in the same style. Optional sections such as `## Chat History Map` (`- [Chat Title](conversation://<id>) (YYYY-MM-DD) — outcome & what's left`) are fine.

### `<topic-slug>.md`, one fact or topic per file

```yaml
---
name: <kebab-case-slug>
description: "<specific one-line summary, used to decide relevance>"
metadata:
  type: <project|feedback|user|reference>
  modified: <YYYY-MM-DDTHH:MM:SSZ>        # optional, recommended
  originSessionId: <conversation-id>      # optional
---
```

Link related memories in the body with `[[other-slug]]`, using the other file's `name`. A `[[link]]` with no file behind it yet is fine: it marks something worth writing later.

---

## 4. The four memory types (`metadata.type`)

Full templates are in `SKILL_DIR/references/claude-memory-format.md`.

| Type | What to store | Body |
|---|---|---|
| **`project`** | Ongoing work, goals, constraints, non-obvious findings, dead ends, what's left. | Current state with absolute dates; **Key Findings & Invariants**; **Dead Ends (Do Not Retry)**; **Completed Progress** (`- [x]`); **What's Left / Open Blockers** (`- [ ]`); `**Why:**`; `**How to apply:**`; `Related:` links. |
| **`feedback`** | User corrections ("don't do X") and confirmed approaches ("yes, keep doing Y"). | The rule first, then `**Why:**` and `**How to apply:**`. |
| **`user`** | Role, expertise, environment, trade-off and communication preferences. | Dated bullet points, then `**Why:**` and `**How to apply:**`. |
| **`reference`** | Pointers to external systems: hosts, ports, dashboards, design files, tickets. | Location, access/auth, gotchas, verification command. |

---

## 5. Commands

```bash
CTL recall                     # sync, then print the cross-project + project indexes
CTL where                      # harness, project root, memory directories, Claude source
CTL sync-claude                # detailed sync report for this project
CTL sync-claude --all          # copy/refresh every Claude Code project into its .agent/memory
CTL sync-claude --force        # copy every Claude file even where the local copy is newer
CTL status [--global]          # index budget and topic table
CTL audit  [--global]          # broken links, orphan files, frontmatter
CTL bridge                     # list every Claude Code / Codex memory index on this machine
CTL sync-chats                 # recent Antigravity conversations as index lines
```

Global options go before the command: `--harness <name>`, `--project <path>`, `--dir <memory-dir>`.

---

## 6. Discipline (prevent memory rot)

1. **No duplicating code or git.** Record why things are the way they are, invariants the code cannot express, dead ends, external topology, and what's left.
2. **Update in place.** Tick finished items (`[ ]` → `[x]`), remove stale blockers, and bump `metadata.modified`. Never append a contradiction.
3. **Absolute dates only.** Convert "today", "yesterday" or "next Friday" to `YYYY-MM-DD`.
4. **Stay in `.agent`.** Read Claude Code and Codex memory, but never write, edit, or delete anything in `~/.claude/` or `~/.codex/`: only Claude Code and Codex change those. `memory_ctl.py` refuses to write there.
