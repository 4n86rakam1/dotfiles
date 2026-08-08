#!/bin/bash
set -euo pipefail

readonly PROJECTS_DIR="${HOME}/.claude/projects"
readonly TASK_PATTERN='TODO|pending|later|next time|保留|後で|未完了|要検討|宿題'
readonly TASK_HITS_PER_FILE=5
readonly SECONDS_PER_DAY=86400

# Returns "!" only when the frontmatter is broken, so the caller can turn it
# into a WARN line instead of a FILE line.
parse_frontmatter() {
  awk '
    NR == 1 && $0 != "---" { bad = 1; exit }
    NR == 1 { next }
    $0 == "---" { exit }
    /^name:[[:space:]]*/ {
      line = $0; sub(/^name:[[:space:]]*/, "", line); name = line
    }
    /^description:[[:space:]]*/ {
      line = $0; sub(/^description:[[:space:]]*/, "", line); desc = line
    }
    /^[[:space:]]+type:[[:space:]]*/ {
      line = $0; sub(/^[[:space:]]+type:[[:space:]]*/, "", line); type = line
    }
    END {
      if (bad) { print "!"; exit }
      gsub(/\t/, " ", desc)
      printf "%s\t%s\t%s\n", (name == "" ? "-" : name), (type == "" ? "-" : type), (desc == "" ? "-" : desc)
    }
  ' "$1"
}

emit_tasks() {
  local project="$1" base="$2" file="$3"
  local hit lineno text
  grep -nE "$TASK_PATTERN" "$file" 2>/dev/null | head -n "$TASK_HITS_PER_FILE" |
    while IFS= read -r hit; do
      lineno=${hit%%:*}
      text=${hit#*:}
      printf 'TASK\t%s\t%s\t%s\t%s\n' "$project" "$base" "$lineno" "$text"
    done || true
}

sweep_project() {
  local memdir="$1" now="$2"
  local project entries latest has_index file base mtime age fm
  project=$(basename "$(dirname "$memdir")")

  # A broken symlink must not vanish silently, or the gap in coverage is invisible.
  if [[ ! -d "$memdir" ]]; then
    if [[ -L "$memdir" || -e "$memdir" ]]; then
      printf 'WARN\t%s\t-\tunreadable-memory-dir\n' "$project"
    fi
    return
  fi

  entries=0
  latest=0
  has_index=no

  for file in "$memdir"/*.md; do
    [[ -e "$file" ]] || continue
    base=$(basename "$file")
    mtime=$(stat -c %Y "$file")
    if [[ "$mtime" -gt "$latest" ]]; then
      latest=$mtime
    fi
    age=$(((now - mtime) / SECONDS_PER_DAY))

    if [[ "$base" == "MEMORY.md" ]]; then
      has_index=yes
      continue
    fi
    entries=$((entries + 1))

    fm=$(parse_frontmatter "$file")
    if [[ "$fm" == "!" ]]; then
      printf 'WARN\t%s\t%s\tmalformed-frontmatter\n' "$project" "$base"
    else
      printf 'FILE\t%s\t%s\t%s\t%s\n' "$project" "$base" "$age" "$fm"
    fi

    emit_tasks "$project" "$base" "$file"
  done

  if [[ "$latest" -eq 0 ]]; then
    printf 'PROJ\t%s\t%s\t-\t%s\n' "$project" "$entries" "$has_index"
  else
    printf 'PROJ\t%s\t%s\t%s\t%s\n' "$project" "$entries" "$(((now - latest) / SECONDS_PER_DAY))" "$has_index"
  fi
}

main() {
  local now memdir

  if [[ ! -d "$PROJECTS_DIR" ]]; then
    echo "projects dir not found: $PROJECTS_DIR" >&2
    exit 1
  fi

  now=$(date +%s)

  # A memory directory is often a symlink, which find would not follow.
  for memdir in "$PROJECTS_DIR"/*/memory; do
    sweep_project "$memdir" "$now"
  done
}

main "$@"
