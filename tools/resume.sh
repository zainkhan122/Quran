#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# One command to bring a new session up to speed and say what state it is in.
#
#     bash tools/resume.sh            # restore + verify + report
#     bash tools/resume.sh --quick    # skip the test suite
#
# It is deliberately idempotent and safe: it only ever *repairs* (a missing
# .git/config, a missing voice model) and never discards work.
# ---------------------------------------------------------------------------
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# The workspace snapshot restores file contents but not modes, so every
# executable comes back 0644 and `tools/cloud.sh ...` fails with "Permission
# denied" for no visible reason. Git records the right mode; re-apply it.
git ls-files -s | awk '$1 == "100755" {print $4}' | xargs -r chmod +x
# .git/config is excluded from snapshots as a credential path; restore it.
git config user.name >/dev/null 2>&1 || cp setup/git-config.template .git/config

QUICK=0
[[ "${1:-}" == "--quick" ]] && QUICK=1

bold() { printf '\n\033[1m== %s\033[0m\n' "$*"; }
ok()   { printf '   \033[32mok\033[0m    %s\n' "$*"; }
warn() { printf '   \033[33mnote\033[0m  %s\n' "$*"; }
bad()  { printf '   \033[31mFAIL\033[0m  %s\n' "$*"; }
PROBLEMS=0

bold "repo"
echo "   root        $ROOT"

# --- 1. .git/config ---------------------------------------------------------
if [[ -f .git/config ]]; then
  ok ".git/config present"
else
  warn ".git/config missing (the snapshot excludes it) - restoring"
  cp setup/git-config.template .git/config && ok "restored from setup/git-config.template"
fi

if git remote get-url origin >/dev/null 2>&1; then
  ok "remote: $(git remote get-url origin)"
else
  bad "no origin remote configured"; PROBLEMS=1
fi

# --- 2. history: is anything lost? ------------------------------------------
LAST="$(git log --oneline -1 2>/dev/null | cut -c1-9)"
echo "   HEAD        ${LAST:-<none>}"
dirty=$(git status --porcelain 2>/dev/null | wc -l | tr -d ' ')
if [[ "$dirty" == "0" ]]; then
  ok "working tree clean"
else
  warn "$dirty uncommitted change(s) - if these are last session's work, the"
  echo "            commit was lost to the snapshot. Re-commit, then push."
fi

if git rev-parse --verify origin/main >/dev/null 2>&1; then
  ahead=$(git rev-list --count origin/main..HEAD 2>/dev/null || echo 0)
  behind=$(git rev-list --count HEAD..origin/main 2>/dev/null || echo 0)
  if [[ "$ahead" != "0" ]]; then
    warn "$ahead local commit(s) NOT pushed - they are the only unsaved work"
  else
    ok "in sync with origin/main"
  fi
  [[ "$behind" != "0" ]] && warn "$behind commit(s) behind origin/main - fetch first"
fi

# A bundle is a local copy of commits that are not on the remote. Once
# everything is pushed it is a 20 MB duplicate of GitHub, which is the one
# store that has never lost anything - so its absence is only worth a note when
# there is genuinely unpushed work.
if git rev-parse --verify origin/main >/dev/null 2>&1 \
   && [[ "$(git rev-list --count origin/main..HEAD 2>/dev/null || echo 1)" == "0" ]]; then
  [[ -f /home/user/naat-ai-ahead.bundle ]] \
    && warn "a recovery bundle is present but redundant - everything is pushed" \
    || ok "nothing unpushed; origin/main is the backup (no bundle needed)"
else
  warn "unpushed commits exist - either push, or: git bundle create ../naat-ai-ahead.bundle 68f0d23..main"
fi

# --- 3. budget --------------------------------------------------------------
bold "budget"
WS=$(du -sm --exclude=.cache --exclude=__pycache__ --exclude=node_modules /home/user 2>/dev/null | cut -f1)
REPO=$(du -sm --exclude=.git . 2>/dev/null | cut -f1)
GITD=$(du -sm .git 2>/dev/null | cut -f1)
echo "   workspace   ${WS} MB  (snapshot limit 128 MB)"
echo "   repo        ${REPO} MB  (excl. .git)"
echo "   .git        ${GITD} MB"
if [[ "${WS:-0}" -gt 118 ]]; then
  bad "workspace is within 10 MB of the limit - it WILL drop files"; PROBLEMS=1
else
  ok "workspace has $((128 - WS)) MB of headroom"
fi

# --- 4. token ---------------------------------------------------------------
bold "token"
if [[ -f /tmp/.ght ]]; then
  ok "/tmp/.ght present"
else
  warn "/tmp/.ght absent - pushing needs the user to supply the token again."
  echo "            Do NOT store it under /home/user: that is snapshotted."
fi

# --- 5. toolchain -----------------------------------------------------------
bold "toolchain"
if bash setup.sh --check >/tmp/resume-check.txt 2>&1; then
  ok "setup.sh --check passed"
else
  warn "toolchain incomplete - running the repair path (~3 min)"
  bash setup.sh >/tmp/resume-setup.txt 2>&1 && ok "setup.sh completed" \
    || { bad "setup.sh failed; see /tmp/resume-setup.txt"; PROBLEMS=1; }
fi

# --- 6. tests ---------------------------------------------------------------
if [[ $QUICK == 0 ]]; then
  bold "gates"
  if out=$(python3 -m unittest discover -s tests 2>&1); then
    ok "$(echo "$out" | grep -E '^Ran ' | sed 's/^/       /')"
  else
    bad "test suite FAILED - do not commit until you know why"
    echo "$out" | tail -20
    PROBLEMS=1
  fi
fi

# --- 7. the handoff ---------------------------------------------------------
bold "next session, in order"
sed -n '/^## Next session, in order/,/^## /p' STATE.md 2>/dev/null \
  | grep -E '^[0-9]+\.' | sed 's/^/   /' || warn "STATE.md has no next-steps section"

bold "result"
if [[ $PROBLEMS == 0 ]]; then
  echo "   ready. Nothing is blocking. Read STATE.md, then work the next step."
else
  echo "   attention needed - see the FAIL lines above."
fi
exit $PROBLEMS
