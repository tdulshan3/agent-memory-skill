#!/usr/bin/env bash
# install.sh — Install the `agent-memory` skill across coding harnesses.
#
# NOTE: Claude Code (~/.claude) and OpenAI Codex (~/.codex) are explicitly
# excluded because both harnesses already provide built-in persistent memory
# systems (~/.claude/projects/*/memory/MEMORY.md and ~/.codex/memories/).

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_NAME="agent-memory"
SKILL_SRC="${REPO_DIR}/${SKILL_NAME}"
MEMORY_DIR="${HOME}/.gemini/antigravity/memory"

usage() {
  cat <<EOF
Usage: ./install.sh [--install | --status | --uninstall]

Options:
  --install     Install skill symlinks and initialize memory index (default)
  --status      Show installation status across harnesses and run memory audit
  --uninstall   Remove installed skill symlinks (preserves saved memory files)
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
  echo "=== Excluded Harnesses (Built-in Memory Present) ==="
  echo "  [SKIP] claude (~/.claude) — skipped (uses built-in ~/.claude/projects/*/memory/MEMORY.md)"
  echo "  [SKIP] codex  (~/.codex)  — skipped (uses built-in ~/.codex/memories/)"
  echo ""
}

install_target() {
  local label="$1"
  local skills_dir="$2"
  local link_path="${skills_dir}/${SKILL_NAME}"

  mkdir -p "${skills_dir}"
  ln -sfn "${SKILL_SRC}" "${link_path}"
  echo "  [OK]   ${label} -> ${link_path}"
}

uninstall_target() {
  local label="$1"
  local link_path="$2/${SKILL_NAME}"
  if [[ -L "${link_path}" ]]; then
    rm -f "${link_path}"
    echo "  [REMOVED] ${label} (${link_path})"
  else
    echo "  [NONE]    ${label} (${link_path} not installed)"
  fi
}

check_target() {
  local label="$1"
  local link_path="$2/${SKILL_NAME}"
  if [[ -L "${link_path}" && -d "${link_path}" ]]; then
    echo "  [INSTALLED] ${label} -> $(readlink -f "${link_path}")"
  else
    echo "  [MISSING]   ${label} (${link_path})"
  fi
}

chmod +x "${SKILL_SRC}/scripts/memory_ctl.py"

if [[ "${ACTION}" == "status" ]]; then
  print_excluded_harnesses
  echo "=== Target Harnesses ==="
  check_target "antigravity" "${HOME}/.gemini/config/skills"
  check_target "opencode   " "${HOME}/.config/opencode/skills"
  check_target "agents     " "${HOME}/.agents/skills"
  echo ""
  python3 "${SKILL_SRC}/scripts/memory_ctl.py" --dir "${MEMORY_DIR}" status
  echo ""
  python3 "${SKILL_SRC}/scripts/memory_ctl.py" --dir "${MEMORY_DIR}" audit
  exit 0
fi

if [[ "${ACTION}" == "uninstall" ]]; then
  print_excluded_harnesses
  echo "=== Removing Skill Symlinks ==="
  uninstall_target "antigravity" "${HOME}/.gemini/config/skills"
  uninstall_target "opencode   " "${HOME}/.config/opencode/skills"
  uninstall_target "agents     " "${HOME}/.agents/skills"
  exit 0
fi

print_excluded_harnesses
echo "=== Installing '${SKILL_NAME}' Skill ==="
install_target "antigravity" "${HOME}/.gemini/config/skills"
if [[ -d "${HOME}/.config/opencode" ]]; then
  install_target "opencode   " "${HOME}/.config/opencode/skills"
fi
install_target "agents     " "${HOME}/.agents/skills"

# Ensure memory directory and MEMORY.md exist (never overwrite existing memory)
mkdir -p "${MEMORY_DIR}"
if [[ ! -f "${MEMORY_DIR}/MEMORY.md" ]]; then
  cat > "${MEMORY_DIR}/MEMORY.md" <<'EOF'
# Antigravity Persistent Memory & Project Map (`MEMORY.md`)

> Master index of projects, findings, progress, remaining work ("what's left"), and linked chat summaries. Keep entries concise (one line per link) and store detailed findings/status in the linked `.md` files.

## Projects & System Status Map

## Existing Cross-Agent Memory Maps (`~/.claude` Bridge)

## Antigravity Chat History Map
EOF
  echo "  [INIT] Created ${MEMORY_DIR}/MEMORY.md"
else
  echo "  [KEEP] Existing ${MEMORY_DIR}/MEMORY.md preserved"
fi

echo ""
python3 "${SKILL_SRC}/scripts/memory_ctl.py" --dir "${MEMORY_DIR}" audit
