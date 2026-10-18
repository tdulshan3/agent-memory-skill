# Reference: Linked-Map Memory Format & Templates

This reference documents the exact file conventions distilled from Claude Code's per-project memory system (`MEMORY.md` + typed `<topic-slug>.md` files), enhanced with project progress tracking ("What's Left"), dead-end tracking, and conversation links.

---

## 1. `MEMORY.md` Index Template

`MEMORY.md` is an index only. Every entry is a single Markdown bullet (`- [Title](path) — one-line hook`):

```markdown
# Persistent Memory & Project Map (`MEMORY.md`)

> Master index of projects, findings, progress, remaining work ("what's left"), and linked chat summaries. Keep entries concise (one line per link) and store detailed findings/status in the linked `.md` files.

## Projects & System Status Map

- [Home Lab & Router Setup](file:///path/to/memory/home-lab-dashboard.md) — M09 root shell, Dropbear SSH, dnsmasq → AdGuard, termox panel, and LAN LLM setup
- [Mario Note App](file:///path/to/memory/mario.md) — Apple macOS 27 UI redesign, local-first offline sync invariants, pluggable LAN AI backends, and open items

## Existing Cross-Agent Memory Maps (Read-Only Bridge)

- [Home Lab Claude Memory](file:///home/user/.claude/projects/-home-user-Projects-home-lab-dashboard/memory/MEMORY.md) — Phone SSH, test workspace, LLM preferences, termox deploy, and M09 notes

## Chat History Map

- [Fix Arch Linux Pacman Lock Error](conversation://cfc7816c-c2b7-4b89-bfd3-ce809a6aee21) (2026-10-18) — Removed stale `/var/lib/pacman/db.lck` via `pkexec` and configured global memory skill
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
  node_type: memory
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
  node_type: memory
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
  node_type: memory
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
  node_type: memory
  type: reference
  originSessionId: <conversation-id>
  modified: 2026-10-18T14:30:00Z
---

- **Resource / Host**: `<url, host:port, or file key>`
- **Access / Auth**: `<SSH key path, tunnel command, or token status>`
- **Gotchas**: `<Rate limits, firewall rules, or offline fallback paths>`
```
