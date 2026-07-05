#!/usr/bin/env bash
# PostToolUse hook (Write|Edit): auto-format the touched file immediately,
# so subagents in the StyleSense ticket pipeline (.claude/agents/) don't
# wait for CI or QA to catch style issues.
# Uses node (not jq) to parse the hook JSON payload — every contributor on
# this repo already has Node for the mobile app, jq is not guaranteed.
set -u

file_path="$(node -e '
let data = "";
process.stdin.on("data", c => data += c);
process.stdin.on("end", () => {
  try {
    const j = JSON.parse(data);
    const f = (j.tool_input && j.tool_input.file_path) || (j.tool_response && j.tool_response.filePath) || "";
    process.stdout.write(f);
  } catch (e) {
    process.stdout.write("");
  }
});
')"

if [ -z "$file_path" ]; then
  exit 0
fi

# Normalize Windows backslashes to forward slashes for matching.
norm="${file_path//\\//}"

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

case "$norm" in
  *mobile/*.ts|*mobile/*.tsx)
    rel="${norm#*mobile/}"
    ( cd "$repo_root/mobile" && npx biome check --write "$rel" ) 2>/dev/null || true
    ;;
  *backend/*.py)
    rel="${norm#*backend/}"
    ruff_bin="ruff"
    if ! command -v ruff >/dev/null 2>&1; then
      if [ -x "$repo_root/backend/venv/Scripts/ruff.exe" ]; then
        ruff_bin="$repo_root/backend/venv/Scripts/ruff.exe"
      elif [ -x "$repo_root/backend/venv/bin/ruff" ]; then
        ruff_bin="$repo_root/backend/venv/bin/ruff"
      fi
    fi
    ( cd "$repo_root/backend" && "$ruff_bin" format "$rel" ) 2>/dev/null || true
    ;;
esac

exit 0
