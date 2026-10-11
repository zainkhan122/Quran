#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Cloud operations for this repo: push, render, watch.
#
#   TOKEN=... tools/cloud.sh push                 # push the current branch
#   TOKEN=... tools/cloud.sh render               # render everything in library.json
#   TOKEN=... tools/cloud.sh render quran-81-8    # render one clip
#   TOKEN=... tools/cloud.sh runs                 # recent workflow runs
#   TOKEN=... tools/cloud.sh logs <run-id>        # per-job conclusions
#   TOKEN=... tools/cloud.sh releases             # published master sets
#
# The token is read from $TOKEN, else $GH_TOKEN, else /tmp/.ght — never written
# to disk, never echoed, and stripped from anything this script prints. It is
# deliberately NOT stored anywhere inside the repository: the workspace is
# snapshotted and shareable, and the repo is public.
#
# GitHub's automatic GITHUB_TOKEN is what the workflow itself uses, so no
# personal token is needed for a render to be authenticated. A PAT is only
# needed here, to push commits and to dispatch a run.
# ---------------------------------------------------------------------------
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO="zainkhan122/Quran"
API="https://api.github.com/repos/$REPO"

TOKEN="${TOKEN:-${GH_TOKEN:-}}"
if [[ -z "$TOKEN" && -f /tmp/.ght ]]; then TOKEN="$(cat /tmp/.ght)"; fi

die() { printf '\033[1m%s\033[0m\n' "$*" >&2; exit 1; }
need_token() { [[ -n "$TOKEN" ]] || die "no token: set TOKEN, GH_TOKEN, or write it to /tmp/.ght"; }

# Never let a token reach the terminal, a log, or a file.
scrub() { sed -E "s#(x-access-token:|token )[A-Za-z0-9_-]+#\1***#g"; }

api() {
  local method="$1" path="$2"; shift 2
  curl -sS -X "$method" \
    -H "Authorization: token $TOKEN" \
    -H "Accept: application/vnd.github+json" \
    -H "X-GitHub-Api-Version: 2022-11-28" \
    "$API$path" "$@"
}

cmd_push() {
  need_token
  cd "$ROOT"
  local branch; branch="$(git rev-parse --abbrev-ref HEAD)"
  [[ "$branch" == "HEAD" ]] && die "detached HEAD — check out a branch first"
  git push "https://x-access-token:${TOKEN}@github.com/${REPO}.git" "HEAD:${branch}" 2>&1 | scrub
}

cmd_render() {
  need_token
  local only="${1:-}"
  api POST /actions/workflows/render.yml/dispatches \
    -d "$(python3 -c '
import json, sys
print(json.dumps({"ref": "main", "inputs": {"only": sys.argv[1]}}))' "$only")" \
    -o /dev/null -w "dispatch: HTTP %{http_code}\n" || die "dispatch failed"
  echo "queued. watch with: tools/cloud.sh runs"
}

cmd_runs() {
  need_token
  api GET "/actions/runs?per_page=${1:-5}" | python3 -c '
import json, sys
d = json.load(sys.stdin)
if not d.get("workflow_runs"):
    print("no runs yet"); raise SystemExit
for r in d["workflow_runs"]:
    print(f"  {r[\"id\"]}  {r[\"status\"]:<12} {str(r.get(\"conclusion\")):<10} "
          f"{r[\"created_at\"][:19]}  {r[\"head_branch\"]}  {r.get(\"display_title\",\"\")[:44]}")'
}

cmd_logs() {
  need_token
  local id="${1:?usage: cloud.sh logs <run-id>}"
  api GET "/actions/runs/$id/jobs" | python3 -c '
import json, sys
for j in json.load(sys.stdin).get("jobs", []):
    steps = [s for s in j.get("steps", []) if s.get("conclusion") not in (None, "success", "skipped")]
    bad = ", ".join(f"{s[\"name\"]}={s[\"conclusion\"]}" for s in steps) or "-"
    print(f"  {j[\"name\"]:<26} {j[\"status\"]:<12} {str(j.get(\"conclusion\")):<10} {bad}")'
}

cmd_releases() {
  need_token
  api GET "/releases?per_page=5" | python3 -c '
import json, sys
for r in json.load(sys.stdin):
    assets = ", ".join(a["name"] for a in r.get("assets", []))
    print(f"  {r[\"tag_name\"]:<22} {len(r.get(\"assets\", []))} asset(s)  {r[\"published_at\"][:10]}")
    if assets: print(f"      {assets[:150]}")'
}

case "${1:-}" in
  push)     shift; cmd_push "$@" ;;
  render)   shift; cmd_render "$@" ;;
  runs)     shift; cmd_runs "$@" ;;
  logs)     shift; cmd_logs "$@" ;;
  releases) shift; cmd_releases "$@" ;;
  *) sed -n '3,12p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//' ;;
esac
