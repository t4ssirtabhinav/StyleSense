#!/usr/bin/env bash
# PreToolUse hook (Bash): hard-block any push to main/master, regardless of
# what an agent's own instructions say. Defense-in-depth on top of the
# prompt-level rule in .claude/agents/devops.md and the Git Autonomy
# Contract in .claude/CLAUDE.md.
# Uses node (not jq) to parse the hook JSON payload — see format-on-edit.sh.
set -u

cmd="$(node -e '
let data = "";
process.stdin.on("data", c => data += c);
process.stdin.on("end", () => {
  try {
    const j = JSON.parse(data);
    process.stdout.write((j.tool_input && j.tool_input.command) || "");
  } catch (e) {
    process.stdout.write("");
  }
});
')"

deny() {
  printf '%s' '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"Blocked: StyleSense policy forbids pushing to main/master. Only PR merges after review may update main (.claude/CLAUDE.md, .claude/agents/devops.md)."}}'
  exit 0
}

if [ -z "$cmd" ]; then
  exit 0
fi

# Explicit push naming main/master as the target branch.
if printf '%s' "$cmd" | grep -Eiq 'git[[:space:]]+push([[:space:]]+[^|;&]*)?[[:space:]](origin[[:space:]]+)?(main|master)([[:space:]]|$)'; then
  deny
fi

# push with an explicit refspec targeting main/master (HEAD:main, x:refs/heads/main, etc).
if printf '%s' "$cmd" | grep -Eiq 'git[[:space:]]+push[^|;&]*:(refs/heads/)?(main|master)([[:space:]]|$)'; then
  deny
fi

# Bare `git push` (no explicit branch) while the current branch is main/master.
if printf '%s' "$cmd" | grep -Eq '(^|[;&|])[[:space:]]*git[[:space:]]+push[[:space:]]*($|[;&|])'; then
  branch="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || true)"
  if [ "$branch" = "main" ] || [ "$branch" = "master" ]; then
    deny
  fi
fi

exit 0
