#!/usr/bin/env bash
# git_history_slim.sh — analyze/strip history in a mirror clone safely.

set -euo pipefail

REPO_URL="${REPO_URL:-}"           # e.g. git@github.com:USER/REPO.git
THRESHOLD="${THRESHOLD:-75M}"      # strip blobs bigger than this (history only)
PURGE_GLOBS="${PURGE_GLOBS:-}"     # e.g. "*.mp4,*.zip"
MIRROR_DIR="${MIRROR_DIR:-repo.mirror}"
MODE="${1:-}"                      # analyze | strip

need() { command -v "$1" >/dev/null 2>&1 || { echo "Missing: $1"; exit 1; }; }

if [[ -z "$REPO_URL" ]]; then
  echo "Set REPO_URL first. Example:"
  echo '  REPO_URL=git@github.com:USER/REPO.git scripts/git_history_slim.sh analyze'
  exit 1
fi

echo "[INFO] Mirror dir: $MIRROR_DIR"
if [[ ! -d "$MIRROR_DIR" ]]; then
  echo "[INFO] Creating mirror clone..."
  git clone --mirror "$REPO_URL" "$MIRROR_DIR"
else
  echo "[INFO] Mirror exists; fetching latest..."
  git -C "$MIRROR_DIR" remote set-url origin "$REPO_URL"
  git -C "$MIRROR_DIR" fetch --prune origin
fi

if [[ "$MODE" == "analyze" || -z "$MODE" ]]; then
  need pip
  pip show git-filter-repo >/dev/null 2>&1 || pip install --user git-filter-repo
  echo "[INFO] Analyzing large blobs (no changes)…"
  git -C "$MIRROR_DIR" filter-repo --analyze || true

  # Report can be in either of these:
  REPORT_A="$MIRROR_DIR/filter-repo/analysis/large-blobs.txt"
  REPORT_B="$MIRROR_DIR/.git/filter-repo/analysis/large-blobs.txt"  # non-bare case
  REPORT=""
  if [[ -f "$REPORT_A" ]]; then REPORT="$REPORT_A"
  elif [[ -f "$REPORT_B" ]]; then REPORT="$REPORT_B"
  fi

  if [[ -n "$REPORT" ]]; then
    echo "[INFO] Report ready: $REPORT"
    echo "------ Top 50 entries ------"
    head -n 50 "$REPORT" || true
    echo "----------------------------"
  else
    echo "[WARN] large-blobs.txt not found. Look for a directory named 'filter-repo/analysis' under '$MIRROR_DIR'."
    find "$MIRROR_DIR" -maxdepth 2 -type d -name "analysis" -path "*/filter-repo/analysis" -print 2>/dev/null || true
  fi

  echo "[DONE] Review the report. When ready, run:"
  echo "THRESHOLD=$THRESHOLD PURGE_GLOBS=\"$PURGE_GLOBS\" REPO_URL=\"$REPO_URL\" $0 strip"
  exit 0
fi

if [[ "$MODE" == "strip" ]]; then
  need pip
  pip show git-filter-repo >/dev/null 2>&1 || pip install --user git-filter-repo
  pushd "$MIRROR_DIR" >/dev/null

  args=( --strip-blobs-bigger-than "$THRESHOLD" )
  if [[ -n "$PURGE_GLOBS" ]]; then
    IFS=',' read -ra GLOBS <<< "$PURGE_GLOBS"
    for g in "${GLOBS[@]}"; do args+=( --path-glob "$g" ); done
    args+=( --invert-paths )
  fi

  echo "[INFO] Running filter-repo with args:"
  printf '  %q ' git filter-repo "${args[@]}"; echo
  git filter-repo "${args[@]}"

  echo "[INFO] Compacting…"
  git reflog expire --expire=now --all || true
  git gc --prune=now --aggressive || true

  echo "[INFO] Size after cleanup:"
  git count-objects -vH | sed -n '1,25p'

  echo
  echo "[NEXT] Verify, then publish cleaned history:"
  echo "  cd $MIRROR_DIR"
  echo "  git push --mirror --prune origin"
  echo
  echo "[TIP] In your working repo afterwards:"
  echo "  git fetch --all"
  echo "  git reset --hard origin/master"
  popd >/dev/null
  exit 0
fi

echo "Usage:"
echo "  REPO_URL=<remote> $0 analyze"
echo "  REPO_URL=<remote> $0 strip"
exit 1
