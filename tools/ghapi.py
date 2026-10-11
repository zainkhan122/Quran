#!/usr/bin/env python3
"""
GitHub Actions from the command line: list runs, wait for one, read its jobs.

    python3 tools/ghapi.py runs [N]
    python3 tools/ghapi.py dispatch WORKFLOW [key=value ...]   # prints the new run id
    python3 tools/ghapi.py wait [RUN_ID] [--max-minutes 40]
    python3 tools/ghapi.py jobs RUN_ID
    python3 tools/ghapi.py log RUN_ID [--failed]               # tail of failed steps

Why a module and not inline Python in cloud.sh: the inline versions were
double-quoted Python inside single-quoted shell, and `runs` had never once
parsed (SyntaxError on the escaped quotes). Worse, `wait` with no run id took
"the latest run", found none, and polled nothing for ten minutes. Here a
missing run is an immediate error, and `dispatch` returns the id of the run it
created, so `wait` is always pointed at the right one.

Token: $TOKEN, $GH_TOKEN or /tmp/.ght. Never printed.
"""

from __future__ import annotations

import io
import json
import os
import sys
import time
import urllib.error
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path

REPO = "zainkhan122/Quran"
API = f"https://api.github.com/repos/{REPO}"


def token() -> str:
    t = os.environ.get("TOKEN") or os.environ.get("GH_TOKEN")
    if not t and Path("/tmp/.ght").exists():
        t = Path("/tmp/.ght").read_text().strip()
    if not t:
        sys.exit("no token: set TOKEN, GH_TOKEN, or write it to /tmp/.ght")
    return t


def call(path: str, method: str = "GET", body: dict | None = None, raw: bool = False):
    req = urllib.request.Request(
        path if path.startswith("http") else API + path, method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Authorization": f"Bearer {token()}",
                 "Accept": "application/vnd.github+json",
                 "X-GitHub-Api-Version": "2022-11-28"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            data = r.read()
    except urllib.error.HTTPError as e:
        sys.exit(f"{method} {path}: HTTP {e.code} {e.read()[:300]!r}")
    if raw:
        return data
    return json.loads(data) if data else {}


def runs(n: int = 8) -> list[dict]:
    return call(f"/actions/runs?per_page={n}").get("workflow_runs", [])


def show_runs(n: int = 8) -> int:
    rs = runs(n)
    if not rs:
        print("no runs yet")
        return 0
    for r in rs:
        print(f"  {r['id']}  {r['name']:<8} {r['event']:<18} {r['status']:<11} "
              f"{str(r.get('conclusion') or '-'):<10} {r['created_at'][:16]}")
    return 0


def dispatch(workflow: str, inputs: dict) -> int:
    """Dispatch and return the id of the run it created.

    The dispatch endpoint returns 204 with no body, so the run is found by
    polling for a run of that workflow created after the call - up to 60 s.
    """
    t0 = datetime.now(timezone.utc).replace(microsecond=0)
    call(f"/actions/workflows/{workflow}/dispatches", "POST",
         {"ref": "main", "inputs": inputs})
    for _ in range(20):
        time.sleep(3)
        for r in call(f"/actions/workflows/{workflow}/runs?per_page=5&event=workflow_dispatch"
                      ).get("workflow_runs", []):
            created = datetime.fromisoformat(r["created_at"].replace("Z", "+00:00"))
            if created >= t0:
                print(r["id"])
                return r["id"]
    sys.exit(f"dispatched {workflow} but no run appeared within 60 s")


def jobs(run_id: int) -> list[dict]:
    return call(f"/actions/runs/{run_id}/jobs?per_page=50").get("jobs", [])


def show_jobs(run_id: int) -> None:
    for j in jobs(run_id):
        bad = [s["name"] for s in j.get("steps", [])
               if s.get("conclusion") not in (None, "success", "skipped")]
        dur = ""
        if j.get("started_at") and j.get("completed_at"):
            a = datetime.fromisoformat(j["started_at"].replace("Z", "+00:00"))
            b = datetime.fromisoformat(j["completed_at"].replace("Z", "+00:00"))
            dur = f"{(b - a).total_seconds():5.0f}s"
        print(f"    {j['name']:<34} {j['status']:<11} {str(j.get('conclusion') or '-'):<10} "
              f"{dur}  {'FAILED: ' + ', '.join(bad) if bad else ''}")


def wait(run_id: int | None, max_minutes: float = 40) -> int:
    if run_id is None:
        rs = runs(1)
        if not rs:
            print("no runs exist - nothing to wait for", file=sys.stderr)
            return 2
        run_id = rs[0]["id"]
    deadline = time.time() + max_minutes * 60
    last = ""
    while True:
        r = call(f"/actions/runs/{run_id}")
        state = f"{r['status']} {r.get('conclusion') or ''}".strip()
        if state != last:
            print(f"  [{time.strftime('%H:%M:%S')}] {r['name']} #{run_id}: {state}", flush=True)
            last = state
        if r["status"] == "completed":
            show_jobs(run_id)
            print(f"  {r['html_url']}")
            return 0 if r.get("conclusion") == "success" else 1
        if time.time() > deadline:
            print(f"  still {state} after {max_minutes} min; resume with: "
                  f"tools/ghapi.py wait {run_id}")
            show_jobs(run_id)
            return 3
        time.sleep(15)


def log(run_id: int, failed_only: bool = True, tail: int = 40) -> None:
    """The last lines of each failed step, from the run's log archive."""
    blob = call(f"/actions/runs/{run_id}/logs", raw=True)
    z = zipfile.ZipFile(io.BytesIO(blob))
    bad_jobs = {j["name"]: [s["name"] for s in j["steps"]
                            if s.get("conclusion") == "failure"] for j in jobs(run_id)}
    for name in sorted(z.namelist()):
        if "/" not in name:
            continue
        job, step = name.split("/", 1)
        if failed_only and not any(job.startswith(k.split(" /")[0][:20]) or k.startswith(job)
                                   for k, v in bad_jobs.items() if v):
            continue
        if failed_only and not any(s.lower()[:25] in step.lower().replace("_", " ")
                                   for v in bad_jobs.values() for s in v):
            continue
        lines = z.read(name).decode(errors="replace").splitlines()
        print(f"\n===== {name} (last {tail}) =====")
        for ln in lines[-tail:]:
            print("  " + ln[29:] if len(ln) > 29 and ln[4] == "-" else "  " + ln)


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 0
    cmd, rest = argv[0], argv[1:]
    if cmd == "runs":
        return show_runs(int(rest[0]) if rest else 8)
    if cmd == "dispatch":
        inputs = dict(kv.split("=", 1) for kv in rest[1:])
        dispatch(rest[0], inputs)
        return 0
    if cmd == "wait":
        mx = 40.0
        if "--max-minutes" in rest:
            i = rest.index("--max-minutes")
            mx = float(rest[i + 1])
            rest = rest[:i] + rest[i + 2:]
        return wait(int(rest[0]) if rest else None, mx)
    if cmd == "jobs":
        show_jobs(int(rest[0]))
        return 0
    if cmd == "log":
        log(int(rest[0]), failed_only="--all" not in rest)
        return 0
    sys.exit(f"unknown command {cmd!r}")


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
