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
#   TOKEN=... tools/cloud.sh upload TAG FILE...   # put media into a Release
#   TOKEN=... tools/cloud.sh pages-enable         # Pages source = GitHub Actions
#   TOKEN=... tools/cloud.sh wait [run-id]        # block until a run finishes
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

# Media lives in Releases, never in git. Create the release if it is missing,
# then upload each file, replacing one of the same name (a re-render).
cmd_upload() {
  need_token
  local tag="${1:?usage: cloud.sh upload TAG FILE...}"; shift
  [[ $# -gt 0 ]] || die "no files given"
  local rid
  rid="$(api GET "/releases/tags/$tag" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("id",""))')"
  if [[ -z "$rid" ]]; then
    rid="$(api POST /releases -d "$(python3 -c 'import json,sys; print(json.dumps({"tag_name": sys.argv[1], "name": sys.argv[1], "body": "Published media. git holds the manifest and citations; this holds the files."}))' "$tag")" \
          | python3 -c 'import json,sys; print(json.load(sys.stdin).get("id",""))')"
    [[ -n "$rid" ]] || die "could not create release $tag"
    echo "created release $tag"
  fi
  local existing; existing="$(api GET "/releases/$rid/assets?per_page=100")"
  for f in "$@"; do
    local name; name="$(basename "$f")"
    local old; old="$(printf '%s' "$existing" | python3 -c 'import json,sys; n=sys.argv[1]; print(next((str(a["id"]) for a in json.load(sys.stdin) if a["name"]==n), ""))' "$name")"
    [[ -n "$old" ]] && api DELETE "/releases/assets/$old" -o /dev/null
    local ctype="application/octet-stream"
    case "$name" in *.mp4) ctype=video/mp4;; *.jpg) ctype=image/jpeg;; *.json) ctype=application/json;; *.mp3) ctype=audio/mpeg;; esac
    curl -sS -X POST -H "Authorization: token $TOKEN" -H "Content-Type: $ctype" \
      --data-binary @"$f" -o /dev/null -w "  %{http_code}  $name\n" \
      "https://uploads.github.com/repos/$REPO/releases/$rid/assets?name=$name"
  done
}

# One-time: serve Pages from the Actions artifact (pages.yml), not a branch.
cmd_pages_enable() {
  need_token
  local code
  code="$(api POST /pages -d '{"build_type":"workflow"}' -o /dev/null -w '%{http_code}')"
  if [[ "$code" == "409" ]]; then        # already enabled: make sure it is the workflow kind
    code="$(api PUT /pages -d '{"build_type":"workflow"}' -o /dev/null -w '%{http_code}')"
  fi
  echo "pages: HTTP $code"
  api GET /pages | python3 -c 'import json,sys; d=json.load(sys.stdin); print("  url:", d.get("html_url"), "| build_type:", d.get("build_type"))'
}

# Block until a run completes; exit non-zero unless it succeeded. Polls every
# 20 s, so a hung run costs nothing but wall-clock.
cmd_wait() {
  need_token
  local id="${1:-}"
  if [[ -z "$id" ]]; then
    id="$(api GET "/actions/runs?per_page=1" | python3 -c 'import json,sys; print(json.load(sys.stdin)["workflow_runs"][0]["id"])')"
  fi
  local i=0
  while :; do
    local st; st="$(api GET "/actions/runs/$id" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d["status"], d.get("conclusion") or "-", d["name"])')"
    read -r status conclusion name <<<"$st"
    printf '  [%3ds] %s %s %s\n' "$((i*20))" "$name" "$status" "$conclusion"
    if [[ "$status" == "completed" ]]; then
      cmd_logs "$id"
      [[ "$conclusion" == "success" ]]; return
    fi
    i=$((i+1)); [[ $i -gt ${WAIT_MAX:-80} ]] && { echo "  still running; re-run: cloud.sh wait $id"; return 2; }
    sleep 20
  done
}

case "${1:-}" in
  push)     shift; cmd_push "$@" ;;
  render)   shift; cmd_render "$@" ;;
  runs)     shift; cmd_runs "$@" ;;
  logs)     shift; cmd_logs "$@" ;;
  releases) shift; cmd_releases "$@" ;;
  upload)   shift; cmd_upload "$@" ;;
  pages-enable) shift; cmd_pages_enable "$@" ;;
  wait)     shift; cmd_wait "$@" ;;
  *) sed -n '3,12p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//' ;;
esac
