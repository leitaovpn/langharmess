#!/usr/bin/env bash
set -euo pipefail

# Zip the project: git-tracked files, untracked files that are not gitignored,
# and the .git directory itself.
# Usage: scripts/zip_project.sh [output.zip]

PROJECT_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
OUTPUT=${1:-"$PROJECT_ROOT/dist/langharness-$(date +%Y%m%d-%H%M%S)-src.zip"}

cd "$PROJECT_ROOT"

# zip -@ reads one path per line; refuse paths containing newlines instead of
# silently skipping them.
NULL_PATHS=$(git ls-files -z --cached --others --exclude-standard | tr -cd '\0' | wc -c | tr -d ' ')
LINE_PATHS=$(git ls-files --cached --others --exclude-standard | wc -l | tr -d ' ')
if [[ "$NULL_PATHS" != "$LINE_PATHS" ]]; then
  echo "error: some file paths contain newlines; zip cannot archive them" >&2
  exit 1
fi

mkdir -p "$(dirname "$OUTPUT")"

git ls-files --cached --others --exclude-standard | zip -q "$OUTPUT" -@
zip -rq "$OUTPUT" .git

echo "created $OUTPUT ($(du -h "$OUTPUT" | cut -f1))"
