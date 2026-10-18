#!/usr/bin/env python3
"""
memory_ctl.py — CLI helper for the `agent-memory` skill.

One shared memory for every harness except Claude Code and Codex (which have
their own), kept inside each project the way Claude Code keeps `.claude/`:

  <project>/.agent/memory/MEMORY.md     project index + typed topic files
  ~/.agent/memory/MEMORY.md             cross-project index (the home folder's own .agent)

Each store is seeded from Claude Code's memory for the same path
(~/.claude/projects/<slug>/memory/, where <slug> is the path with every
non-alphanumeric character replaced by '-'). Copying is one way and by edit time:
a Claude file edited after the local copy is copied in; otherwise nothing happens.
~/.claude and ~/.codex are only ever read: only Claude Code and Codex change them.

Commands:
  where        Show the detected harness, project, and memory directories.
  recall       Sync Claude memory, then print the cross-project + project indexes.
  sync-claude  Copy Claude Code memory that is newer than the local copy (--all: every project).
  init         Create ~/.agent/memory (adopting legacy memory if present).
  status       Show MEMORY.md budget and topic files with metadata.
  audit        Validate MEMORY.md links, orphan topic files, and YAML frontmatter.
  sync-chats   List recent Antigravity conversations from conversation_summaries.db.
  bridge       List read-only Claude Code & Codex memory indexes on this machine.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
from urllib.parse import unquote
from datetime import datetime, timezone
from pathlib import Path

VALID_TYPES = {"project", "feedback", "user", "reference"}
MEMORY_SUBDIR = Path(".agent") / "memory"
RULE_FILE = Path(".agent") / "rules" / "agent-memory.md"  # Antigravity loads .agent/rules/*.md
SYNC_MANIFEST = ".claude-sync.json"
LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")

# `paths` are markers in the path the skill was invoked from; `procs` are executable
# names (or distinctive path fragments, when 8+ chars) of a parent harness process.
HARNESSES: dict[str, dict] = {
    "antigravity": {"paths": ["/.gemini/"], "procs": ["antigravity", "agy"]},
    "hermes": {"paths": ["/.hermes/"], "procs": ["hermes", "hermes-agent"]},
    "dsh": {"paths": ["/.dsh/"], "procs": ["dsh", "deepseek-harness", "@deepseek-ai/dsh"]},
    "qwen": {"paths": ["/.qwen/"], "procs": ["qwen", "@qwen-code"]},
    "openclaw": {"paths": ["/.openclaw/"], "procs": ["openclaw"]},
    "opencode": {"paths": ["/.config/opencode/", "/.opencode/"], "procs": ["opencode"]},
    "codex": {"paths": ["/.codex/"], "procs": ["codex"]},
    "claude": {"paths": ["/.claude/"], "procs": ["claude"]},
    "agents": {"paths": [], "procs": []},
}
FALLBACK_HARNESS = "agents"
NATIVE_HARNESSES = {"claude", "codex"}  # built-in memory; they only read .agent/memory
SKIP_PROCS = {"sh", "bash", "zsh", "fish", "dash", "env", "timeout", "sudo"}
INTERPRETERS = {"node", "bun", "deno", "python", "npx", "pnpm", "uv"}

# Memory written by v1 of this skill, adopted into ~/.agent/memory by `init`.
LEGACY_GLOBAL_DIRS = [Path("~/.gemini/antigravity/memory")]


# --------------------------------------------------------------------------- paths


def claude_home() -> Path:
    return Path(os.environ.get("CLAUDE_CONFIG_DIR") or "~/.claude").expanduser()


def project_slug(path: Path) -> str:
    return re.sub(r"[^A-Za-z0-9]", "-", str(path))


def memory_dir(project: Path) -> Path:
    return project / MEMORY_SUBDIR


def global_memory_dir() -> Path:
    return memory_dir(Path.home())


def _git(cwd: Path, *args: str) -> str | None:
    try:
        out = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return out.stdout.strip() if out.returncode == 0 and out.stdout.strip() else None


def project_candidates(start: Path) -> list[Path]:
    """Project roots for `start`, most canonical first.

    The main worktree root comes first so linked worktrees share one memory, then
    the current worktree root, then `start` itself.
    """
    found: list[Path] = []
    common = _git(start, "rev-parse", "--path-format=absolute", "--git-common-dir")
    if common and Path(common).name == ".git":
        found.append(Path(common).parent)
    top = _git(start, "rev-parse", "--show-toplevel")
    if top:
        found.append(Path(top))
    found.append(start)
    unique: list[Path] = []
    for p in found:
        p = p.resolve()
        if p not in unique:
            unique.append(p)
    return unique


def claude_sources(candidates: list[Path]) -> list[Path]:
    """Claude Code memory directories for any of the candidate roots."""
    result = []
    for root in candidates:
        src = claude_home() / "projects" / project_slug(root) / "memory"
        if src.is_dir() and any(src.glob("*.md")) and src not in result:
            result.append(src)
    return result


def claude_project_path(slug_dir: Path) -> Path | None:
    """Recover the real project path behind a ~/.claude/projects/<slug> directory.

    The slug is lossy, so read the `cwd` Claude Code recorded in the session logs.
    """
    for log in sorted(slug_dir.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)[:5]:
        try:
            with log.open(encoding="utf-8", errors="replace") as fh:
                for _, line in zip(range(50), fh):
                    try:
                        cwd = json.loads(line).get("cwd")
                    except (json.JSONDecodeError, AttributeError):
                        continue
                    if cwd and project_slug(Path(cwd)) == slug_dir.name:
                        return Path(cwd)
        except OSError:
            continue
    return _decode_slug(Path("/"), slug_dir.name[1:]) if slug_dir.name.startswith("-") else None


def _decode_slug(base: Path, rest: str, depth: int = 0) -> Path | None:
    """Find the existing directory under `base` whose slug is `rest` (no session logs to read)."""
    if depth > 12:
        return None
    try:
        children = [c for c in base.iterdir() if c.is_dir()]
    except OSError:
        return None
    for child in children:
        s = project_slug(Path(child.name))
        if rest == s:
            return child
        if rest.startswith(s + "-"):
            found = _decode_slug(child, rest[len(s) + 1 :], depth + 1)
            if found:
                return found
    return None


def git_exclude(project: Path) -> None:
    """Keep the local memory out of commits via .git/info/exclude (never .gitignore)."""
    common = _git(project, "rev-parse", "--path-format=absolute", "--git-common-dir")
    if not common:
        return
    exclude = Path(common) / "info" / "exclude"
    text = exclude.read_text() if exclude.exists() else ""
    if f"/{MEMORY_SUBDIR.as_posix()}/" in text.splitlines():
        return
    exclude.parent.mkdir(parents=True, exist_ok=True)
    entry = f"# agent-memory skill: local project memory\n/{MEMORY_SUBDIR.as_posix()}/\n/{RULE_FILE.as_posix()}\n"
    exclude.write_text(text + ("" if not text or text.endswith("\n") else "\n") + entry)


def write_rule(project: Path) -> None:
    """Antigravity auto-loads <project>/.agent/rules/*.md: inline the project index there."""
    index = memory_dir(project) / "MEMORY.md"
    rule = project / RULE_FILE
    body = f"""---
trigger: always_on
description: Project memory index maintained by the agent-memory skill
---

# Project Memory (`agent-memory`)

This project's memory lives in `{MEMORY_SUBDIR.as_posix()}/` (index below; links are relative to it). Read the topic files relevant to the task and verify what they name before relying on it. Save non-obvious findings, dead ends, progress / what's left, and user corrections there, following the `agent-memory` skill.

@[MEMORY.md]({index})
"""
    if not rule.exists() or rule.read_text(encoding="utf-8", errors="replace") != body:
        rule.parent.mkdir(parents=True, exist_ok=True)
        rule.write_text(body, encoding="utf-8")


def is_protected(path: Path) -> bool:
    """True inside ~/.claude or ~/.codex: only Claude Code and Codex may change those."""
    resolved = path.resolve()
    for root in (claude_home(), Path.home() / ".codex"):
        root = root.resolve()
        if resolved == root or root in resolved.parents:
            return True
    return False


def ensure_store(project: Path) -> Path:
    """Create <project>/.agent/memory with an index, hidden from git, plus the Antigravity rule."""
    if is_protected(project):
        raise SystemExit(f"Refusing to write in {project}: only Claude Code and Codex may change ~/.claude and ~/.codex.")
    mdir = memory_dir(project)
    mdir.mkdir(parents=True, exist_ok=True)
    (mdir / "MEMORY.md").touch(exist_ok=True)
    git_exclude(project)
    write_rule(project)
    return mdir


# ----------------------------------------------------------------- harness detection


def _process_chain() -> list[list[str]]:
    """argv of each ancestor process, nearest first."""
    chain: list[list[str]] = []
    pid = os.getppid()
    for _ in range(40):
        if pid <= 1:
            break
        proc = Path("/proc") / str(pid)
        if proc.is_dir():
            try:
                argv = [a.decode(errors="replace") for a in (proc / "cmdline").read_bytes().split(b"\0") if a]
                ppid_line = next(l for l in (proc / "status").read_text().splitlines() if l.startswith("PPid:"))
                parent = int(ppid_line.split()[1])
            except (OSError, StopIteration, ValueError):
                break
        else:  # macOS / BSD
            try:
                out = subprocess.run(["ps", "-o", "ppid=,command=", "-p", str(pid)], capture_output=True, text=True, timeout=5)
                ppid_str, _, command = out.stdout.strip().partition(" ")
                argv, parent = command.split(), int(ppid_str)
            except (OSError, ValueError, subprocess.TimeoutExpired):
                break
        chain.append(argv)
        pid = parent
    return chain


def _match_process(argv: list[str]) -> str | None:
    if not argv:
        return None
    exe = os.path.basename(argv[0]).lower()
    if exe in SKIP_PROCS:
        return None
    # For `node /usr/bin/dsh ...` the harness is the script, not the interpreter.
    heads = [h.lower() for h in (argv[:3] if re.sub(r"[\d.]+$", "", exe) in INTERPRETERS else argv[:1])]
    names = {re.sub(r"\.(c?m?js|py)$", "", os.path.basename(h)) for h in heads}
    for harness, spec in HARNESSES.items():
        for marker in spec["procs"]:
            if marker in names or (len(marker) >= 8 and any(marker in h for h in heads)):
                return harness
    return None


def detect_harness(explicit: str | None) -> tuple[str, str]:
    """Return (harness, how it was determined)."""
    if explicit:
        return explicit, "--harness"
    env = os.environ.get("AGENT_MEMORY_HARNESS")
    if env in HARNESSES:
        return env, "AGENT_MEMORY_HARNESS"
    invoked = os.path.abspath(sys.argv[0])  # unresolved: keeps the harness's skill symlink path
    for harness, spec in HARNESSES.items():
        if any(marker in invoked for marker in spec["paths"]):
            return harness, f"skill path {invoked}"
    for argv in _process_chain():
        harness = _match_process(argv)
        if harness:
            return harness, f"parent process {os.path.basename(argv[0])}"
    ai_agent = os.environ.get("AI_AGENT", "").lower()
    for harness in HARNESSES:
        if ai_agent.startswith(harness):
            return harness, "AI_AGENT"
    if os.environ.get("CLAUDECODE"):
        return "claude", "CLAUDECODE"
    return FALLBACK_HARNESS, "fallback"


# ------------------------------------------------------------------- file helpers


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_frontmatter(md_path: Path) -> dict[str, str]:
    text = md_path.read_text(encoding="utf-8", errors="replace")
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.S)
    if not m:
        return {}
    block = m.group(1)
    result: dict[str, str] = {}
    for key in ("name", "description", "node_type", "type", "originSessionId", "modified"):
        km = re.search(rf"^\s*{key}:\s*(.+?)\s*$", block, re.M)
        if km:
            result[key] = km.group(1).strip().strip('"').strip("'")
    return result


def link_target_name(target: str, mem_dir: Path) -> str | None:
    """File name of a MEMORY.md link target if it points at a .md file inside mem_dir."""
    target = target.split("#")[0].strip()
    if not target or ("://" in target and not target.startswith("file://")):
        return None
    if target.startswith("file://"):
        target = unquote(target[len("file://"):])
    path = Path(target) if os.path.isabs(target) else mem_dir / target
    try:
        if path.resolve().parent != mem_dir.resolve():
            return None
    except OSError:
        return None
    return path.name if path.suffix == ".md" and path.name != "MEMORY.md" else None


def index_lines_by_target(index_text: str, mem_dir: Path) -> dict[str, str]:
    """Map topic file name -> the first index line linking to it."""
    result: dict[str, str] = {}
    for line in index_text.splitlines():
        for match in LINK_RE.finditer(line):
            name = link_target_name(match.group(2), mem_dir)
            if name:
                result.setdefault(name, line)
                break
    return result


# -------------------------------------------------------------------- claude sync


def sync_claude_dir(src: Path, dst: Path, *, force: bool = False, dry_run: bool = False) -> dict[str, list[str]]:
    """Copy Claude memory into dst wherever Claude edited it more recently. One way only.

    Each file is decided by modification time: a Claude file newer than its local copy
    (or with no local copy yet) is copied, keeping Claude's mtime; a local copy edited
    after Claude's version is left alone. Nothing is ever written to or deleted from
    `src`, and nothing in dst is deleted. A file deleted locally comes back only when
    Claude edits it again. `force` copies every Claude file regardless of time.
    """
    report: dict[str, list[str]] = {k: [] for k in ("new", "updated", "local-newer", "deleted-locally")}
    manifest_path = dst / SYNC_MANIFEST
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    state = manifest.setdefault("sources", {}).setdefault(str(src), {})
    # name -> mtime of the Claude version last copied (older manifests held hashes instead).
    copied: dict[str, float] = {}
    for name, value in state.get("files", {}).items():
        if isinstance(value, (int, float)):
            copied[name] = float(value)
        elif (src / name).exists():
            copied[name] = (src / name).stat().st_mtime
    state.pop("index", None)

    src_topics = {p.name: p for p in sorted(src.glob("*.md")) if p.name != "MEMORY.md"}
    for name, sp in src_topics.items():
        dp = dst / name
        src_mtime = sp.stat().st_mtime
        if dp.exists():
            if dp.read_bytes() == sp.read_bytes():
                copied[name] = src_mtime
                continue
            if src_mtime <= dp.stat().st_mtime and not force:
                report["local-newer"].append(name)
                continue
            action = "updated"
        elif name in copied and src_mtime <= copied[name] and not force:
            report["deleted-locally"].append(name)
            continue
        else:
            action = "new"
        report[action].append(name)
        if not dry_run:
            dst.mkdir(parents=True, exist_ok=True)
            shutil.copy2(sp, dp)  # keeps Claude's mtime, so the copy never looks newer than its source
        copied[name] = src_mtime

    merge_index(src, dst, report["new"] + report["updated"], force=force, dry_run=dry_run)
    if not dry_run:
        state["files"] = copied
        state["synced_at"] = now_iso()
        dst.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return report


def merge_index(src: Path, dst: Path, copied: list[str], *, force: bool, dry_run: bool) -> None:
    """Bring Claude's MEMORY.md lines into the local index; the newest edit wins.

    Lines for files copied in this run always follow Claude. Other Claude lines are
    applied only when Claude's MEMORY.md was edited after the local one. Local-only
    lines are never touched.
    """
    src_index, dst_index = src / "MEMORY.md", dst / "MEMORY.md"
    if not src_index.exists():
        return
    src_text = src_index.read_text(encoding="utf-8", errors="replace")
    dst_text = dst_index.read_text(encoding="utf-8", errors="replace") if dst_index.exists() else ""
    src_lines = index_lines_by_target(src_text, src)

    def present(name: str) -> bool:
        return (dst / name).exists() or name in copied

    if not dst_text.strip():
        # Fresh local index: start from Claude's verbatim, minus links to files not here.
        dropped = {l for n, l in src_lines.items() if not present(n)}
        keep = [l for l in src_text.splitlines() if l not in dropped]
        new_text = "\n".join(keep).strip("\n") + "\n" if any(l.strip() for l in keep) else ""
    else:
        index_newer = force or src_index.stat().st_mtime > dst_index.stat().st_mtime
        lines = dst_text.splitlines()
        dst_lines = index_lines_by_target(dst_text, dst)
        claude_lines = set(src_lines.values())
        for name, src_line in src_lines.items():
            if not present(name) or not (index_newer or name in copied):
                continue
            current = dst_lines.get(name)
            if current is None:
                anchor = max((i for i, l in enumerate(lines) if l in claude_lines), default=len(lines) - 1)
                lines.insert(anchor + 1, src_line)
            elif current != src_line:
                lines[lines.index(current)] = src_line
        new_text = "\n".join(lines) + "\n"

    if new_text != dst_text and not dry_run:
        dst_index.write_text(new_text, encoding="utf-8")


def print_sync_report(report: dict[str, list[str]], label: str) -> None:
    labels = {"new": "NEW", "updated": "UPDATED", "local-newer": "LOCAL NEWER", "deleted-locally": "SKIP"}
    notes = {
        "updated": "Claude's version is newer",
        "local-newer": "edited here after Claude's version; left alone",
        "deleted-locally": "deleted here; comes back only if Claude edits it again (--force re-copies)",
    }
    changed = [(k, n) for k in labels for n in report[k]]
    if not changed:
        print(f"  [OK] {label}: up to date")
        return
    print(f"  {label}:")
    for kind, name in changed:
        note = f" — {notes[kind]}" if kind in notes else ""
        print(f"    [{labels[kind]}] {name}{note}")


def summarize(report: dict[str, list[str]], keys: tuple[str, ...] = ("new", "updated", "local-newer", "deleted-locally")) -> str:
    parts = [f"{len(report[k])} {k}" for k in keys if report.get(k)]
    return ", ".join(parts) if parts else "up to date"


def merge_reports(reports: list[dict[str, list[str]]]) -> dict[str, list[str]]:
    merged: dict[str, list[str]] = {}
    for r in reports:
        for k, v in r.items():
            merged.setdefault(k, []).extend(v)
    return merged


def sync_project(project: Path, **kw) -> dict[str, list[str]]:
    """Copy newer Claude Code memory that belongs to `project` into its .agent/memory."""
    sources = claude_sources(project_candidates(project))
    if not sources or is_protected(project):
        return {}
    if not kw.get("dry_run"):
        ensure_store(project)
    return merge_reports([sync_claude_dir(src, memory_dir(project), **kw) for src in sources])


# ----------------------------------------------------------------------- commands


def adopt_legacy(gdir: Path) -> None:
    """Copy memory written by v1 of this skill into ~/.agent/memory (originals left in place)."""
    for legacy in LEGACY_GLOBAL_DIRS:
        src = legacy.expanduser()
        marker = gdir / f".adopted-{project_slug(src)}"
        if not (src / "MEMORY.md").exists() or marker.exists():
            continue
        for p in src.glob("*.md"):
            dp = gdir / p.name
            text = p.read_text(encoding="utf-8", errors="replace")
            text = text.replace(f"file://{src}/", "").replace(f"{src}/", "")
            existing = dp.read_text(encoding="utf-8", errors="replace").strip() if dp.exists() else ""
            if p.name == "MEMORY.md" and existing:
                text = existing + "\n\n" + text
            elif existing:
                continue  # never overwrite a topic file already in ~/.agent/memory
            dp.write_text(text, encoding="utf-8")
        marker.write_text(now_iso() + "\n")
        print(f"  [ADOPT] {src} -> {gdir} (original left in place)")


def native_note(harness: str) -> str:
    return f"{harness} keeps its own built-in memory; .agent/memory is shared by the other harnesses (read-only here)."


def cmd_where(ctx: argparse.Namespace) -> int:
    print(f"Harness        : {ctx.harness}  ({ctx.harness_source})")
    print(f"Project root   : {ctx.project}")
    print(f"Project memory : {memory_dir(ctx.project)}")
    print(f"Global memory  : {global_memory_dir()}")
    sources = claude_sources(project_candidates(ctx.project))
    print(f"Claude source  : {', '.join(map(str, sources)) or '(no Claude Code memory for this project)'}")
    if ctx.harness in NATIVE_HARNESSES:
        print(f"\nNote: {native_note(ctx.harness)}")
    return 0


def cmd_recall(ctx: argparse.Namespace) -> int:
    native = ctx.harness in NATIVE_HARNESSES
    roots = [Path.home()] + ([ctx.project] if ctx.project != Path.home() else [])
    notes = {}
    for root in roots:
        if native:
            notes[root] = native_note(ctx.harness)
            continue
        if is_protected(root):
            notes[root] = "inside ~/.claude or ~/.codex; only Claude Code / Codex change this folder"
            continue
        if root == Path.home():
            ensure_store(root)
            adopt_legacy(global_memory_dir())
        if ctx.no_sync:
            ensure_store(root)
            notes[root] = "Claude sync skipped"
            continue
        report = sync_project(root)
        ensure_store(root)
        if not report:
            notes[root] = "no Claude Code memory for this path"
        else:
            notes[root] = f"Claude sync: {summarize(report, ('new', 'updated'))}"

    print(f"# agent-memory · harness={ctx.harness} ({ctx.harness_source}) · project={ctx.project}")
    print("# Index links are relative to the directory of the index that contains them.\n")
    for root in roots:
        title = "Cross-project memory" if root == Path.home() else "Project memory"
        index = memory_dir(root) / "MEMORY.md"
        text = index.read_text(encoding="utf-8", errors="replace").strip() if index.exists() else ""
        print(f"## {title} — {index}  [{notes[root]}]\n")
        print(text if text else "(empty)")
        print()
    return 0


def cmd_sync_claude(ctx: argparse.Namespace) -> int:
    if ctx.harness in NATIVE_HARNESSES:
        print(native_note(ctx.harness))
        return 0
    kw = {"force": ctx.force, "dry_run": ctx.dry_run}
    skipped: list[str] = []
    if ctx.all:
        projects: list[Path] = []
        for slug_dir in sorted((claude_home() / "projects").iterdir()):
            src = slug_dir / "memory"
            if not (src.is_dir() and any(src.glob("*.md"))):
                continue
            path = claude_project_path(slug_dir)
            if path is None or not path.is_dir():
                skipped.append(slug_dir.name)
                continue
            root = project_candidates(path)[0]
            if is_protected(root):
                continue
            if root not in projects:
                projects.append(root)
    else:
        projects = [ctx.project]

    verb = "Would sync" if ctx.dry_run else "Syncing"
    print(f"{verb} Claude Code memory into <project>/{MEMORY_SUBDIR.as_posix()}/ ({len(projects)} project(s))")
    for slug in skipped:
        print(f"  [SKIP] {slug}: project folder no longer exists (memory stays in Claude Code)")
    for root in projects:
        report = sync_project(root, **kw)
        if not report:
            print(f"  [--] {root}: no Claude Code memory")
        elif ctx.summary:
            print(f"  [OK] {root}: {summarize(report)}")
        else:
            print_sync_report(report, str(root))
    return 0


def cmd_init(ctx: argparse.Namespace) -> int:
    gdir = ensure_store(Path.home())
    adopt_legacy(gdir)
    print(f"  [OK] cross-project memory: {gdir}")
    return 0


def target_dir(ctx: argparse.Namespace) -> Path:
    if ctx.dir:
        return ctx.dir
    return global_memory_dir() if ctx.use_global else memory_dir(ctx.project)


def cmd_status(ctx: argparse.Namespace) -> int:
    mem_dir = target_dir(ctx)
    index_path = mem_dir / "MEMORY.md"
    print(f"Memory Directory: {mem_dir}")
    if not index_path.exists():
        print("  [!] MEMORY.md does not exist yet (run `recall`).")
        return 1

    content = index_path.read_text(encoding="utf-8", errors="replace")
    lines = content.splitlines()
    size_bytes = len(content.encode("utf-8"))
    print(f"Index File      : {index_path} ({len(lines)}/200 lines, {size_bytes}/24000 bytes)")
    manifest = mem_dir / SYNC_MANIFEST
    if manifest.exists():
        for src, state in json.loads(manifest.read_text()).get("sources", {}).items():
            print(f"Claude Sync     : {len(state.get('files', {}))} file(s) from {src} at {state.get('synced_at')}")
    print()

    topic_files = sorted(p for p in mem_dir.glob("*.md") if p.name != "MEMORY.md")
    print(f"Topic Files ({len(topic_files)}):")
    print(f"  {'FILE':<34} {'TYPE':<10} {'MODIFIED':<22} DESCRIPTION")
    print(f"  {'-'*34} {'-'*10} {'-'*22} {'-'*40}")
    for tf in topic_files:
        fm = parse_frontmatter(tf)
        mtype = fm.get("type", "missing")
        mod = fm.get("modified") or datetime.fromtimestamp(tf.stat().st_mtime, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        desc = fm.get("description", "(no frontmatter description)")
        if len(desc) > 65:
            desc = desc[:62] + "..."
        print(f"  {tf.name:<34} {mtype:<10} {mod[:20]:<22} {desc}")
    return 0


def cmd_audit(ctx: argparse.Namespace) -> int:
    mem_dir = target_dir(ctx)
    index_path = mem_dir / "MEMORY.md"
    issues = 0
    if not index_path.exists():
        print(f"[ERROR] Missing index file: {index_path}")
        return 1

    content = index_path.read_text(encoding="utf-8", errors="replace")
    lines = content.splitlines()
    size_bytes = len(content.encode("utf-8"))

    if len(lines) > 200:
        print(f"[WARN] MEMORY.md has {len(lines)} lines (recommended max: 200)")
        issues += 1
    if size_bytes > 24000:
        print(f"[WARN] MEMORY.md is {size_bytes} bytes (rule inline cap: 24,000 bytes)")
        issues += 1

    # Check links inside MEMORY.md
    linked_files: set[Path] = set()
    for lineno, line in enumerate(lines, 1):
        for match in LINK_RE.finditer(line):
            target = match.group(2)
            if "://" in target and not target.startswith("file://"):
                continue
            if target.startswith("file://"):
                target_path = Path(unquote(target[len("file://") :].split("#")[0]))
            else:
                target_path = (mem_dir / target.split("#")[0]).resolve()
            linked_files.add(target_path.resolve())
            if not target_path.exists():
                print(f"[ERROR] Line {lineno}: broken link target -> {target_path}")
                issues += 1

    # Check topic files in mem_dir
    for tf in sorted(mem_dir.glob("*.md")):
        if tf.name == "MEMORY.md":
            continue
        if tf.resolve() not in linked_files:
            print(f"[WARN] Orphan topic file not linked in MEMORY.md: {tf.name}")
            issues += 1
        fm = parse_frontmatter(tf)
        if not fm:
            print(f"[WARN] {tf.name}: missing YAML frontmatter (--- name/description/metadata ---)")
            issues += 1
        elif fm.get("type") not in VALID_TYPES:
            print(f"[WARN] {tf.name}: metadata.type={fm.get('type')!r} not in {sorted(VALID_TYPES)}")
            issues += 1

    if issues == 0:
        print(f"[OK] Audit passed for {mem_dir} (0 issues found).")
        return 0
    print(f"\n[!] Audit completed with {issues} issue(s).")
    return 1


def cmd_sync_chats(ctx: argparse.Namespace) -> int:
    db_path = Path.home() / ".gemini" / "antigravity" / "conversation_summaries.db"
    if not db_path.exists():
        print(f"No Antigravity database found at {db_path}")
        return 0

    conn = sqlite3.connect(str(db_path))
    query = """
        SELECT conversation_id, title, workspace_uris, substr(last_modified_time, 1, 10)
        FROM conversation_summaries
        ORDER BY last_modified_time DESC
        LIMIT ?
    """
    print("# Recent Antigravity Conversations (Markdown Links for MEMORY.md):\n")
    for cid, title, ws, date_str in conn.execute(query, (ctx.limit,)):
        label = title.strip() if title and title.strip() else f"Untitled Session ({cid[:8]})"
        ws_hint = f" — workspace: `{ws}`" if ws else ""
        print(f"- [{label}](conversation://{cid}) ({date_str}){ws_hint}")
    return 0


def cmd_bridge(ctx: argparse.Namespace) -> int:
    print("# Discovered Read-Only Upstream Memory Indexes:\n")
    claude_root = claude_home() / "projects"
    if claude_root.exists():
        for mem_index in sorted(claude_root.glob("*/memory/MEMORY.md")):
            proj_slug = mem_index.parent.parent.name
            count = len(list(mem_index.parent.glob("*.md"))) - 1
            print(f"- [{proj_slug}](file://{mem_index}) — Claude Code memory ({count} topic files)")

    codex_summary = Path.home() / ".codex" / "memories" / "memory_summary.md"
    if codex_summary.exists():
        print(f"- [Codex Memory Summary](file://{codex_summary}) — OpenAI Codex rollout & user profile summary")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Manage the shared per-project linked-map agent memory (<project>/.agent/memory).")
    parser.add_argument("--harness", choices=sorted(HARNESSES), help="Harness name (default: auto-detect)")
    parser.add_argument("--project", help="Project path (default: git root of the current directory)")
    parser.add_argument("--dir", type=Path, default=os.environ.get("AGENT_MEMORY_DIR"), help="Explicit memory directory for status/audit")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("where", help="Show detected harness, project, and memory directories")
    p_recall = sub.add_parser("recall", help="Sync Claude memory, then print the cross-project + project indexes")
    p_recall.add_argument("--no-sync", action="store_true", help="Skip the Claude Code sync")
    p_sync = sub.add_parser("sync-claude", help="Copy Claude Code memory that is newer than the local copy into <project>/.agent/memory")
    p_sync.add_argument("--all", action="store_true", help="Sync every Claude Code project, not just this one")
    p_sync.add_argument("--force", action="store_true", help="Copy every Claude file even when the local copy is newer, and re-copy files deleted here")
    p_sync.add_argument("--dry-run", action="store_true", help="Report what would change without writing")
    p_sync.add_argument("--summary", action="store_true", help="One line per project instead of per file")
    sub.add_parser("init", help="Create ~/.agent/memory (adopting legacy memory if present)")
    for name, help_text in (("status", "Show index budget and topic memory table"), ("audit", "Validate links, frontmatter, and orphan files")):
        p = sub.add_parser(name, help=help_text)
        p.add_argument("--global", dest="use_global", action="store_true", help="Target ~/.agent/memory instead of the project")
    p_chats = sub.add_parser("sync-chats", help="Print recent Antigravity chat links")
    p_chats.add_argument("--limit", type=int, default=15, help="Max conversations to list")
    sub.add_parser("bridge", help="List existing Claude Code and Codex memory indexes")

    ctx = parser.parse_args()
    ctx.dir = ctx.dir.expanduser() if ctx.dir else None
    ctx.harness, ctx.harness_source = detect_harness(ctx.harness)
    start = Path(ctx.project or os.environ.get("AGENT_MEMORY_PROJECT") or os.getcwd()).expanduser().resolve()
    ctx.project = project_candidates(start)[0]

    commands = {
        "where": cmd_where,
        "recall": cmd_recall,
        "sync-claude": cmd_sync_claude,
        "init": cmd_init,
        "status": cmd_status,
        "audit": cmd_audit,
        "sync-chats": cmd_sync_chats,
        "bridge": cmd_bridge,
    }
    return commands[ctx.cmd](ctx)


if __name__ == "__main__":
    sys.exit(main())
