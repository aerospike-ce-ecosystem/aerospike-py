#!/usr/bin/env bash
# PreToolUse hook: gates `gh pr create` on perf-impact-reviewer evidence.
#
# When Claude tries to invoke `gh pr create`, this hook:
#   1. Resolves the PR base branch (`--base <name>`, default "main").
#   2. Diffs the PR against the base and matches each touched file against
#      the globs in .claude/perf-hot-paths.txt.
#   3. If any hot-path file is touched AND the conversation transcript shows
#      no perf-impact-reviewer invocation / `perf-impact:` verdict / benchmark
#      run, denies the tool call with a Claude-visible reason.
#
# A green path (no hot-path files touched, OR evidence already present) is a
# silent allow — the hook prints nothing and exits 0.
#
# Bypass: edit .claude/perf-hot-paths.txt to remove globs that don't actually
# matter, or include the literal string "perf-impact:" in a tool result /
# message earlier in the turn.

set -euo pipefail

input=$(cat)

command=$(printf '%s' "$input" | jq -r '.tool_input.command // empty')
if [[ -z "$command" ]]; then
  exit 0
fi

# Match `gh pr create` (handle leading whitespace, semicolons, pipes, &&).
if ! printf '%s' "$command" | grep -qE '(^|[[:space:];&|(])gh[[:space:]]+pr[[:space:]]+create(\s|$)'; then
  exit 0
fi

cwd=$(printf '%s' "$input" | jq -r '.cwd // empty')
[[ -z "$cwd" ]] && exit 0

repo_root=$(git -C "$cwd" rev-parse --show-toplevel 2>/dev/null) || exit 0
hot_paths_file="$repo_root/.claude/perf-hot-paths.txt"
[[ ! -f "$hot_paths_file" ]] && exit 0

# Resolve PR base branch from the command (--base <name>); default "main".
base="main"
if [[ "$command" =~ --base[[:space:]]+([A-Za-z0-9._/-]+) ]]; then
  base="${BASH_REMATCH[1]}"
fi

# Pick the first ref that resolves: origin/<base>, upstream/<base>, <base>.
diff_ref=""
for candidate in "origin/$base" "upstream/$base" "$base"; do
  if git -C "$repo_root" rev-parse --verify --quiet "$candidate" >/dev/null 2>&1; then
    diff_ref="$candidate"
    break
  fi
done
[[ -z "$diff_ref" ]] && exit 0

touched=$(git -C "$repo_root" diff --name-only "$diff_ref...HEAD" 2>/dev/null || true)
[[ -z "$touched" ]] && exit 0

# Match each touched file against the hot-path globs.
# (No `shopt -s globstar`: case-pattern matching doesn't use it, and macOS's
#  default bash 3.2 doesn't support globstar anyway. The hot-paths file lists
#  nested dirs explicitly when needed.)
hot_hits=()
while IFS= read -r f; do
  [[ -z "$f" ]] && continue
  while IFS= read -r raw_pattern; do
    # Strip comments and trim whitespace.
    pattern="${raw_pattern%%#*}"
    pattern="${pattern#"${pattern%%[![:space:]]*}"}"
    pattern="${pattern%"${pattern##*[![:space:]]}"}"
    [[ -z "$pattern" ]] && continue
    # bash `case` pattern matching against the relative path.
    case "$f" in
      $pattern) hot_hits+=("$f"); break ;;
    esac
  done < "$hot_paths_file"
done <<< "$touched"

(( ${#hot_hits[@]} == 0 )) && exit 0

# Allow if the transcript already shows perf-review evidence.
transcript_path=$(printf '%s' "$input" | jq -r '.transcript_path // empty')
if [[ -n "$transcript_path" && -f "$transcript_path" ]]; then
  if grep -qE 'perf-impact-reviewer|perf-impact:[[:space:]]|cargo[[:space:]]+bench|make[[:space:]]+benchmark|/perf-check' "$transcript_path"; then
    exit 0
  fi
fi

# `git diff --name-only` already yields unique paths, and the inner `break`
# above ensures each path is appended at most once — no dedup needed.
joined=$(printf '%s, ' "${hot_hits[@]}")
joined=${joined%, }

reason="PR touches performance hot-path files (${joined}). Before opening the PR, invoke the perf-impact-reviewer agent on this diff (Agent tool with subagent_type=perf-impact-reviewer), include its 'perf-impact:' verdict in the PR body, then re-run gh pr create. See .claude/agents/perf-impact-reviewer.md and .claude/perf-hot-paths.txt. To override (perf-irrelevant change incorrectly matched), include a 'perf-impact: none — <reason>' line in the PR body and retry."

jq -n --arg reason "$reason" '{
  hookSpecificOutput: {
    hookEventName: "PreToolUse",
    permissionDecision: "deny",
    permissionDecisionReason: $reason
  }
}'
