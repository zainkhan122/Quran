#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Cloud operations for this repo: push, render, watch.
#
#   TOKEN=... tools/cloud.sh push                 # push the current branch
#   TOKEN=... tools/cloud.sh render               # render everything in library.json, and wait
#   TOKEN=... tools/cloud.sh render quran-81-8    # render one clip, and wait
#   TOKEN=... tools/cloud.sh runs                 # recent workflow runs
#   TOKEN=... tools/cloud.sh logs <run-id>        # tail of every failed step
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

# Dispatch a render and wait for THAT run (not "the latest run", which once
# meant polling nothing for ten minutes). ghapi.py returns the run's id.
cmd_render() {
  need_token
  local only="${1:-}" id
  id="$(TOKEN="$TOKEN" python3 "$ROOT/tools/ghapi.py" dispatch render.yml "only=$only")" || die "dispatch failed"
  echo "render run $id"
  TOKEN="$TOKEN" python3 "$ROOT/tools/ghapi.py" wait "$id"
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

case "${1:-}" in
  push)     shift; cmd_push "$@" ;;
  render)   shift; cmd_render "$@" ;;
  runs)     shift; TOKEN="$TOKEN" python3 "$ROOT/tools/ghapi.py" runs "$@" ;;
  logs)     shift; TOKEN="$TOKEN" python3 "$ROOT/tools/ghapi.py" log "$@" ;;
  releases) shift; cmd_releases "$@" ;;
  upload)   shift; cmd_upload "$@" ;;
  pages-enable) shift; cmd_pages_enable "$@" ;;
  wait)     shift; TOKEN="$TOKEN" python3 "$ROOT/tools/ghapi.py" wait "$@" ;;
  *) sed -n '3,12p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//' ;;
esac
