#!/usr/bin/env bash
# install.sh — Install the `agent-memory` skill across coding harnesses.
#
# Memory is shared by every harness and lives inside each project, the way
# Claude Code keeps `.claude/`:  <project>/.agent/memory/  (+ ~/.agent/memory/
# for cross-project memory). For every harness found on this machine it:
#   1. links the skill where the harness discovers skills,
#   2. adds a managed block to the harness's always-loaded rules file, so every
#      session in every project runs `recall` on its own, without being asked,
#   3. once: creates ~/.agent/memory and copies every Claude Code project memory
#      into that project's .agent/memory/ (hidden from git via .git/info/exclude).
#
# Claude Code (~/.claude) and OpenAI Codex (~/.codex) are not installed into:
# both have built-in memory. Claude Code's memory is the read-only seed.

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_NAME="agent-memory"
SKILL_SRC="${REPO_DIR}/${SKILL_NAME}"
CTL="${SKILL_SRC}/scripts/memory_ctl.py"

# name | directory whose presence means the harness is installed | skills dir | always-loaded rules file ("-" if none)
# dsh, Qwen Code, OpenClaw and OpenCode all read ~/.agents/skills, so they share that link.
HARNESSES=(
  "antigravity|${HOME}/.gemini|${HOME}/.gemini/config/skills|${HOME}/.gemini/config/rules/AGENTS.md"
  "hermes|${HOME}/.hermes|${HOME}/.hermes/skills|${HOME}/.hermes/SOUL.md"
  "dsh|${HOME}/.dsh|${HOME}/.agents/skills|${HOME}/.dsh/AGENTS.md"
  "qwen|${HOME}/.qwen|${HOME}/.agents/skills|${HOME}/.qwen/QWEN.md"
  "openclaw|${HOME}/.openclaw|${HOME}/.agents/skills|${HOME}/.openclaw/workspace/AGENTS.md"
  "opencode|${HOME}/.config/opencode|${HOME}/.agents/skills|${HOME}/.config/opencode/AGENTS.md"
  "agents|${HOME}|${HOME}/.agents/skills|-"
)
# Links left by v1 of this installer that now duplicate the ~/.agents/skills one.
STALE_LINKS=("${HOME}/.config/opencode/skills/${SKILL_NAME}")

usage() {
  cat <<EOF
Usage: ./install.sh [--install | --status | --uninstall]

Options:
  --install     Link the skill, add the auto-start rules, and copy Claude Code memory (default)
  --status      Show installation status for every harness and audit ~/.agent/memory
  --uninstall   Remove skill links and rules blocks (keeps every memory file)
EOF
}

ACTION="install"
if [[ $# -gt 0 ]]; then
  case "$1" in
    --install)   ACTION="install" ;;
    --status)    ACTION="status" ;;
    --uninstall) ACTION="uninstall" ;;
    -h|--help)   usage; exit 0 ;;
    *)           echo "Unknown option: $1" >&2; usage; exit 1 ;;
  esac
fi

print_excluded_harnesses() {
  echo "=== Native Memory (Not Installed Into) ==="
  echo "  [SKIP] claude (~/.claude) — built-in memory; read-only seed for <project>/.agent/memory"
  echo "  [SKIP] codex  (~/.codex)  — built-in ~/.codex/memories/"
  echo ""
}

# Write (or with "remove", delete) the managed auto-start block in a harness rules file.
# Replaces the hand-written section left by v1 of this skill if there is one.
update_rules() {
  local harness="$1" rules="$2" mode="${3:-write}"
  [[ "${rules}" == "-" ]] && return 0
  if [[ "${mode}" == "remove" && ! -f "${rules}" ]]; then
    return 0
  fi
  mkdir -p "$(dirname "${rules}")"
  python3 - "${harness}" "${rules}" "${SKILL_SRC}" "${mode}" <<'PY'
import re, sys
from pathlib import Path

harness, rules, skill, mode = sys.argv[1:5]
path = Path(rules)
text = path.read_text(encoding="utf-8") if path.exists() else ""
begin, end = "<!-- agent-memory:begin -->", "<!-- agent-memory:end -->"
ctl = f"python3 {skill}/scripts/memory_ctl.py --harness {harness}"
block = f"""{begin}
## Persistent Project Memory (`agent-memory` skill) — automatic

Do this on your own, without being asked, before your first action in every session and whenever you move to a different project:

1. Run `{ctl} recall` (add `--project <path>` when the project is not the current directory). It copies in any Claude Code memory for the project, then prints the project index (`<project>/.agent/memory/MEMORY.md`) and the cross-project index (`~/.agent/memory/MEMORY.md`).
2. Read the topic files relevant to the task, and verify anything they name before relying on it.
3. As you work, save non-obvious findings, dead ends, progress / what's left, and user corrections to `<project>/.agent/memory/` (preferences and feedback that apply everywhere go to `~/.agent/memory/`), following the `agent-memory` skill ([SKILL.md]({skill}/SKILL.md)). Update existing topic files instead of duplicating them, and keep each `MEMORY.md` a one-line-per-link index.
4. Never write to `~/.claude/` or `~/.codex/`; they are other harnesses' built-in memory.
{end}"""
if harness == "antigravity":
    block = block.replace(end, f"\n@[MEMORY.md]({Path.home()}/.agent/memory/MEMORY.md)\n{end}")

managed = re.compile(re.escape(begin) + r".*?" + re.escape(end), re.S)
legacy = re.compile(r"^## \d+\. Persistent Linked-Map Memory \(`agent-memory` Skill\).*?^@\[MEMORY\.md\]\([^)]*\)[ \t]*$", re.S | re.M)
if mode == "remove":
    new = managed.sub("", text)
    new = re.sub(r"\n{3,}", "\n\n", new).rstrip() + "\n" if new.strip() else ""
elif managed.search(text):
    new = managed.sub(lambda _: block, text)
elif legacy.search(text):
    new = legacy.sub(lambda _: block, text)
else:
    new = (text.rstrip() + "\n\n" if text.strip() else "") + block + "\n"
if mode == "remove" and not new and text:
    path.unlink()  # the file only ever held our block
    print(f"  [REMOVED] {rules}")
elif new != text:
    path.write_text(new, encoding="utf-8")
    print(f"  [{'REMOVED' if mode == 'remove' else 'RULES'}] {rules}")
else:
    print(f"  [KEEP]  {rules}")
PY
}

chmod +x "${CTL}"

if [[ "${ACTION}" == "status" ]]; then
  print_excluded_harnesses
  for row in "${HARNESSES[@]}"; do
    IFS='|' read -r name detect skills rules <<<"${row}"
    [[ -d "${detect}" ]] || { echo "=== ${name}: not installed on this machine"; continue; }
    echo "=== ${name}"
    if [[ -L "${skills}/${SKILL_NAME}" && -d "${skills}/${SKILL_NAME}" ]]; then
      echo "  [SKILL]    ${skills}/${SKILL_NAME} -> $(readlink -f "${skills}/${SKILL_NAME}")"
    else
      echo "  [MISSING]  ${skills}/${SKILL_NAME}"
    fi
    if [[ "${rules}" != "-" ]]; then
      if grep -q "agent-memory:begin" "${rules}" 2>/dev/null; then
        echo "  [AUTO]     ${rules}"
      else
        echo "  [NO AUTO]  ${rules}"
      fi
    fi
  done
  echo ""
  echo "=== Shared memory"
  stores=$(find "${HOME}" -maxdepth 6 -path '*/.agent/memory/MEMORY.md' 2>/dev/null | wc -l)
  echo "  ${stores} .agent/memory store(s) under ${HOME}"
  python3 "${CTL}" audit --global | sed 's/^/  /' || true
  exit 0
fi

if [[ "${ACTION}" == "uninstall" ]]; then
  print_excluded_harnesses
  for row in "${HARNESSES[@]}"; do
    IFS='|' read -r name detect skills rules <<<"${row}"
    if [[ -L "${skills}/${SKILL_NAME}" ]]; then
      rm -f "${skills}/${SKILL_NAME}"
      echo "  [REMOVED] ${skills}/${SKILL_NAME}"
    fi
    update_rules "${name}" "${rules}" remove
  done
  echo ""
  echo "Memory in ~/.agent/memory and <project>/.agent/memory was kept."
  exit 0
fi

print_excluded_harnesses
for link in "${STALE_LINKS[@]}"; do
  if [[ -L "${link}" && "$(readlink -f "${link}")" == "$(readlink -f "${SKILL_SRC}")" ]]; then
    rm -f "${link}"
    echo "  [CLEAN] ${link} (duplicate of ~/.agents/skills/${SKILL_NAME})"
  fi
done
for row in "${HARNESSES[@]}"; do
  IFS='|' read -r name detect skills rules <<<"${row}"
  if [[ ! -d "${detect}" ]]; then
    echo "=== ${name}: not installed on this machine, skipped"
    continue
  fi
  echo "=== ${name}"
  mkdir -p "${skills}"
  ln -sfn "${SKILL_SRC}" "${skills}/${SKILL_NAME}"
  echo "  [SKILL] ${skills}/${SKILL_NAME}"
  update_rules "${name}" "${rules}"
done

echo ""
echo "=== Shared memory (<project>/.agent/memory, seeded from Claude Code)"
python3 "${CTL}" --harness agents init
python3 "${CTL}" --harness agents sync-claude --all --summary | sed 's/^/  /' || true
