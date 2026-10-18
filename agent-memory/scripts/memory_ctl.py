#!/usr/bin/env python3
"""
memory_ctl.py — CLI helper for the `agent-memory` skill.

Commands:
  status       Show MEMORY.md budget and list all topic memory files with metadata.
  audit        Validate MEMORY.md links, orphan topic files, and YAML frontmatter.
  sync-chats   List recent Antigravity conversations from conversation_summaries.db.
  bridge       Discover read-only Claude Code & Codex memory indexes on this machine.
"""

from __future__ import annotations

import argparse
import os
import re
import sqlite3
import sys
from pathlib import Path

VALID_TYPES = {"project", "feedback", "user", "reference"}


def default_memory_dir() -> Path:
    env_dir = os.environ.get("AGENT_MEMORY_DIR")
    if env_dir:
        return Path(env_dir).expanduser().resolve()
    agy_dir = Path.home() / ".gemini" / "antigravity" / "memory"
    if agy_dir.exists():
        return agy_dir
    return Path.home() / ".agents" / "memory"


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
            val = km.group(1).strip().strip('"').strip("'")
            result[key] = val
    return result


def cmd_status(mem_dir: Path) -> int:
    index_path = mem_dir / "MEMORY.md"
    print(f"Memory Directory: {mem_dir}")
    if not index_path.exists():
        print("  [!] MEMORY.md does not exist yet.")
        return 1

    content = index_path.read_text(encoding="utf-8", errors="replace")
    lines = content.splitlines()
    size_bytes = len(content.encode("utf-8"))
    print(f"Index File      : {index_path} ({len(lines)}/200 lines, {size_bytes}/24000 bytes)\n")

    topic_files = sorted(p for p in mem_dir.glob("*.md") if p.name != "MEMORY.md")
    print(f"Topic Files ({len(topic_files)}):")
    print(f"  {'FILE':<28} {'TYPE':<10} {'MODIFIED':<22} DESCRIPTION")
    print(f"  {'-'*28} {'-'*10} {'-'*22} {'-'*40}")
    for tf in topic_files:
        fm = parse_frontmatter(tf)
        mtype = fm.get("type", "missing")
        mod = fm.get("modified", "-")[:20]
        desc = fm.get("description", "(no frontmatter description)")
        if len(desc) > 65:
            desc = desc[:62] + "..."
        print(f"  {tf.name:<28} {mtype:<10} {mod:<22} {desc}")
    return 0


def cmd_audit(mem_dir: Path) -> int:
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
        for match in re.finditer(r"\[([^\]]+)\]\(([^)]+)\)", line):
            target = match.group(2)
            if target.startswith("conversation://") or target.startswith("http://") or target.startswith("https://"):
                continue
            if target.startswith("file://"):
                target_path = Path(target[len("file://") :].split("#")[0])
            else:
                target_path = (mem_dir / target.split("#")[0]).resolve()
            linked_files.add(target_path)
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


def cmd_sync_chats(limit: int) -> int:
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
    for cid, title, ws, date_str in conn.execute(query, (limit,)):
        label = title.strip() if title and title.strip() else f"Untitled Session ({cid[:8]})"
        ws_Hint = f" — workspace: `{ws}`" if ws else ""
        print(f"- [{label}](conversation://{cid}) ({date_str}){ws_Hint}")
    return 0


def cmd_bridge() -> int:
    print("# Discovered Read-Only Upstream Memory Indexes:\n")
    claude_root = Path.home() / ".claude" / "projects"
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
    parser = argparse.ArgumentParser(description="Manage and audit the Linked-Map Agent Memory system.")
    parser.add_argument("--dir", type=Path, default=default_memory_dir(), help="Memory directory path")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("status", help="Show index budget and topic memory table")
    sub.add_parser("audit", help="Validate links, frontmatter, and orphan files")
    p_sync = sub.add_parser("sync-chats", help="Print recent Antigravity chat links")
    p_sync.add_argument("--limit", type=int, default=15, help="Max conversations to list")
    sub.add_parser("bridge", help="List existing Claude Code and Codex memory indexes")

    args = parser.parse_args()
    if args.cmd == "status":
        return cmd_status(args.dir)
    if args.cmd == "audit":
        return cmd_audit(args.dir)
    if args.cmd == "sync-chats":
        return cmd_sync_chats(args.limit)
    if args.cmd == "bridge":
        return cmd_bridge()
    return 0


if __name__ == "__main__":
    sys.exit(main())
