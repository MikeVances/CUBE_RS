
#!/usr/bin/env bash
set -euo pipefail

# human time label
NOW_TS="$(date +'%Y-%m-%d %H:%M:%S')"
TMP_MSG_PREFIX="💾 Temporary save before pull"
TMP_MSG="${TMP_MSG_PREFIX} (${NOW_TS})"
MADE_TEMP_COMMIT=0

echo "🔍 Checking for local changes..."
if [[ -n "$(git status --porcelain)" ]]; then
  echo "💡 Changes detected. Creating a temporary commit..."
  git add .
  git commit -m "${TMP_MSG}" || true
  MADE_TEMP_COMMIT=1
  echo "✅ Temporary commit created: ${TMP_MSG}"
else
  echo "📭 No local changes detected."
fi

echo "⬇️  Pulling latest changes with rebase..."
# Use rebase to keep history linear; if conflicts occur, user will resolve and re-run
if git pull --rebase; then
  echo "✅ Pull completed."
else
  echo "⚠️  Pull encountered conflicts. Please resolve them, then run: git rebase --continue"
  exit 1
fi

if [[ "${MADE_TEMP_COMMIT}" -eq 1 ]]; then
  echo "♻️ Restoring working state (dropping temporary commit)..."
  # If the last commit is our temp one, drop it and keep changes in the working tree
  LAST_MSG="$(git log -1 --pretty=%B | tr -d '\r')"
  if echo "${LAST_MSG}" | grep -q "${TMP_MSG_PREFIX}"; then
    # reset --mixed keeps changes and unstages them (closest to original state)
    git reset --mixed HEAD~1
    echo "✅ Local changes restored to working tree."
  else
    echo "ℹ️  Temporary commit is not the last one anymore (probably rebased on top). Leaving history as-is."
  fi
else
  echo "ℹ️  Nothing to restore — no temporary commit was made."
fi

echo "\n🧭 Summary:"
if [[ -n "$(git status --porcelain)" ]]; then
  echo " • Local modifications present (not committed)."
else
  echo " • No local modifications. Working tree clean."
fi
CURRENT_BRANCH="$(git rev-parse --abbrev-ref HEAD)"
UPSTREAM="$(git rev-parse --abbrev-ref --symbolic-full-name @{u} 2>/dev/null || echo 'no upstream')"
echo " • Branch: ${CURRENT_BRANCH} (upstream: ${UPSTREAM})"

echo "\n✅ Safe pull finished."
