#!/usr/bin/env bash
# sync_oss_module.sh — sync external_plugins/opama_<module>/ to its
# opama-oss-* mirror repo as a new additive commit.
#
# The mirror repos have unrelated history from this repo (originally seeded
# as history-less snapshots), so this does NOT use git subtree/force-push —
# it clones/updates a local mirror clone, rsyncs the current module
# directory over it, and commits the diff. Review + push is a separate
# manual step. See external_plugins/README.md for the development workflow
# this supports.

set -euo pipefail

declare -A REPO_MAP=(
  [pokemon_tcg]=opama-oss-pokemon
  [shopify]=opama-oss-shopify
  [storefront]=opama-oss-storefront
  [grading]=opama-oss-card-grader
  [portfolio]=opama-oss-portfolio
  [ai]=opama-oss-ai-assistant
)

MODULE="${1:-}"
ORG="${ORG:-GeneralOperationsDirector}"

need() { command -v "$1" >/dev/null 2>&1 || { echo "Missing: $1"; exit 1; }; }
need git; need rsync

if [[ -z "$MODULE" || -z "${REPO_MAP[$MODULE]:-}" ]]; then
  echo "Usage: $0 <module>"
  echo "  <module> is one of: ${!REPO_MAP[*]}"
  exit 1
fi

SRC_DIR="external_plugins/opama_${MODULE}"
REPO="${REPO_MAP[$MODULE]}"
REPO_URL="${REPO_URL:-git@github.com:${ORG}/${REPO}.git}"
WORK_DIR="${WORK_DIR:-/tmp/oss-sync-${REPO}}"

[[ -d "$SRC_DIR" ]] || { echo "Missing $SRC_DIR"; exit 1; }

if [[ ! -d "$WORK_DIR/.git" ]]; then
  echo "[INFO] Cloning $REPO_URL -> $WORK_DIR"
  git clone "$REPO_URL" "$WORK_DIR"
else
  echo "[INFO] Updating existing clone at $WORK_DIR"
  git -C "$WORK_DIR" fetch origin
  git -C "$WORK_DIR" checkout main
  git -C "$WORK_DIR" reset --hard origin/main
fi

echo "[INFO] Syncing $SRC_DIR/ -> $WORK_DIR/"
rsync -a --delete --exclude .git --exclude __pycache__ --exclude '*.pyc' "$SRC_DIR/" "$WORK_DIR/"

SRC_SHA="$(git rev-parse --short HEAD)"
cd "$WORK_DIR"
git add -A

if git diff --cached --quiet; then
  echo "[INFO] No changes for $MODULE ($REPO) — already in sync."
  exit 0
fi

git commit -m "sync: update from opama@${SRC_SHA}"

echo
echo "[DONE] Committed in $WORK_DIR. Review, then push:"
echo "  cd $WORK_DIR && git show --stat HEAD"
echo "  git -C $WORK_DIR push origin main"
