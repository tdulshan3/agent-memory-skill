# Reference: Linked-Map Memory Format & Templates

This reference documents the file conventions of Claude Code's per-project memory system (`MEMORY.md` + typed `<topic-slug>.md` files), which every harness store uses unchanged so files can be copied between them, plus the project progress ("What's Left"), dead-end, and conversation-link conventions this skill adds.

Required frontmatter: `name`, `description`, `metadata.type`. Optional: `metadata.modified`, `metadata.originSessionId`.

---

## 1. `MEMORY.md` Index Templates

`MEMORY.md` is an index only. Every entry is a single Markdown bullet with a link **relative to the index's own directory** (`- [Title](topic-slug.md) — one-line hook`).

### Project index — `<project>/.agent/memory/MEMORY.md`

Flat list, exactly like Claude Code's per-project index (and seeded from `~/.claude/projects/<slug>/memory/MEMORY.md` by `memory_ctl.py sync-claude`):

```markdown
- [Mario offline sync](mario-offline-sync.md) — client ids + persisted outbox + snapshot index; invariants for updatePage and cascades
- [Mario install procedure](mario-install-procedure.md) — pacman package from packaging/arch, bump pkgrel, then pkexec pacman -U
- [Mario screenshot workflow](mario-screenshot-workflow.md) — GNOME blocks synthetic input; drive the app on a nested Xvfb :99
```

### Cross-project index — `~/.agent/memory/MEMORY.md`

Cross-project memories only (user profile, feedback rules, shared references, chat history):

```markdown
# Cross-Project Memory (`MEMORY.md`)

> Cross-project index: user profile, feedback rules, and references that apply in every project.

## User & Feedback

- [GUI sudo via pkexec](pkexec-for-sudo.md) — when `sudo -n` fails, run the command through `pkexec` instead of asking the user
- [Git attribution](git-attribution.md) — never add AI co-author trailers; commit with the ~/.gitconfig identity

## References

- [Home LAN inference box](lan-llm-host.md) — Ollama on the LAN; model tags and context sizes

## Chat History Map

- [Fix Arch Linux Pacman Lock Error](conversation://cfc7816c-c2b7-4b89-bfd3-ce809a6aee21) (2026-10-18) — removed stale `db.lck` via `pkexec`
```

---

## 2. Topic File Templates by `metadata.type`

### A. `type: project` (Architecture, Findings, Progress, Dead Ends & What's Left)

Use `type: project` for ongoing project state, stack/buildspec overrides, non-obvious invariants, dead ends not to retry, completed milestones, and open blockers ("what's left").

```markdown
---
name: <project-or-feature-slug>
description: "<One-line summary specific enough for an agent to decide relevance from the index>"
metadata:
  type: project
  originSessionId: <conversation-id>
  modified: 2026-10-18T14:30:00Z
---

<1–2 sentence overview of current state and when it was established, e.g., "Asked for on 2026-09-07...">.

**Key Findings & Invariants:**
- **Shape / Files**: Where each piece lives (`path/to/file.ext`) and how data flows.
- **Invariants**: Rules that must never be broken when editing (e.g., "`updatePage` must never overwrite a real `driveFileId` with `null`").
- **Unconfirmed Defaults**: Any product or engineering defaults chosen without explicit user confirmation.

**Dead Ends (Do Not Retry):**
- `<approach 1>` — why it failed (e.g., applet not compiled in, buffer truncated at 40 chars, read-only tunnel).

**Completed Progress:**
- [x] <Milestone 1> (commit `<hash>` / `YYYY-MM-DD`)
- [x] <Milestone 2>

**What's Left / Open Blockers:**
- [ ] <Remaining task 1>
- [ ] **Blocker**: <e.g., missing local `.env`, expired `gcloud auth`, or pending firewall rule>

**Why:** <The motivation, trade-off, or user decision that explains why the system is built this way.>

**How to apply:** <Concrete instructions for future sessions modifying or testing this component.>

Related: [[other-topic-slug]], [Session Title](conversation://<conversation-id>)
```

---

### B. `type: feedback` (User Corrections & Confirmed Practices)

Use `type: feedback` whenever the user corrects an action ("never tag AI as co-author", "use `pkexec` for GUI sudo") or confirms a non-obvious workflow.

```markdown
---
name: <rule-slug>
description: "<Imperative one-line summary of the rule>"
metadata:
  type: feedback
  originSessionId: <conversation-id>
  modified: 2026-10-18T14:30:00Z
---

<Clear, direct statement of the rule to follow or avoid.>

**Why:** <What happened or why the user requested this override.>

**How to apply:** <Exactly when and how to apply this rule, including edge cases or recovery steps.>
```

---

### C. `type: user` (User Profile, Hardware & Trade-Off Preferences)

Use `type: user` for hardware setup, performance priorities, and workflow habits.

```markdown
---
name: <preference-slug>
description: "<One-line summary of what the user prefers in this domain>"
metadata:
  type: user
  originSessionId: <conversation-id>
  modified: 2026-10-18T14:30:00Z
---

Stated by the user on YYYY-MM-DD while working on <context>:

- <Preference 1>
- <Preference 2>

**Why:** <How these preferences resolve trade-offs that code alone cannot decide.>

**How to apply:** <How future tasks should prioritize resources, tooling, or design choices.>
```

---

### D. `type: reference` (External Systems, Credentials Location, SSH & Design Assets)

Use `type: reference` for pointers to external resources (SSH hosts/keys, Figma file keys, cloud instances, local ports).

```markdown
---
name: <resource-slug>
description: "<One-line summary of the external resource and how to reach it>"
metadata:
  type: reference
  originSessionId: <conversation-id>
  modified: 2026-10-18T14:30:00Z
---

- **Resource / Host**: `<url, host:port, or file key>`
- **Access / Auth**: `<SSH key path, tunnel command, or token status>`
- **Gotchas**: `<Rate limits, firewall rules, or offline fallback paths>`
```
