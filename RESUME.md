# RESUME — the contract for starting a new session

**Read this first, then `STATE.md`.** This file is the procedure; `STATE.md` is
the current contents of the head. If they disagree with the repo, **the repo
wins** — fix the file.

The goal is stated bluntly because it is the thing that keeps failing: *a new
session must pick up exactly where the last one stopped, without re-deriving
anything and without asking the user to repeat themselves.*

---

## Step 0 — the thirty-second check

```bash
cd /home/user/naat-ai
bash tools/resume.sh
```

That script does the whole of Step 1 for you and prints what it found. If you
would rather do it by hand:

```bash
git log --oneline -3          # is the last session's commit still here?
git status --porcelain        # are the files here but untracked?
du -sh --exclude=.cache --exclude=__pycache__ /home/user   # budget
```

## Step 1 — restore what the sandbox does not persist

Three things are deliberately **not** snapshotted, and each has bitten us:

| what | why | restore |
|---|---|---|
| `.git/config` | credential path, excluded on purpose | `cp setup/git-config.template .git/config` |
| the Urdu voice weights | `~/.cache` is excluded, ~60 MB | `bash setup.sh` fetches them once |
| the **token** | never stored in the workspace, on purpose | ask the user, write it to `/tmp/.ght` (0600) |

`.git` *itself* is also unreliable — see Step 2.

## Step 2 — if a commit was lost

This has happened **twice**. The working tree survives a snapshot; the git
objects sometimes do not.

```bash
cp setup/git-config.template .git/config
git bundle verify /home/user/naat-ai-ahead.bundle   # local commits, one file
git bundle unbundle /home/user/naat-ai-ahead.bundle # or: git fetch <bundle> main
```

The files will be intact either way — only the history is at risk. Re-commit
with the message from the recovered commit, then **push before doing anything
else**, because the remote is the only storage that survives.

## Step 3 — verify before changing

```bash
bash setup.sh --check                          # toolchain, ~9 s
python3 -m unittest discover -s tests          # 91 tests, ~10 s, stdlib, offline
python3 tools/plan_render.py --plan --offline  # the plan the workflow would build
bash tools/resume.sh                           # the whole of steps 1-3 at once
```

`setup.sh --check` must print `ready`. If it does not, run `bash setup.sh`
(the repair path, ~3 min cold).

## Step 4 — orient

* `STATE.md` — what is done, what is blocked, what is next, open items.
* `PHASES.md` — the phase table and the phase log. The last entry is the last
  session.
* `RESEARCH.md` — what was learned outside the repo, with measurements.
* `BLUEPRINT.md` — how the system is put together.

Do not re-derive any of it. Every number in those files was measured and is
recorded with the method, precisely so a new session does not have to measure it
again.

## Step 5 — the standing rules

1. **One phase per session.** Numbered, in `PHASES.md`.
2. **Run the suite before committing.** A change to a gate must be proven.
3. **Push before you finish.** A local commit is not saved anywhere that
   survives. This is rule 1 of the whole project, learned twice the hard way.
4. **Keep the workspace under budget and the repo under its own limit**
   (`bash tools/resume.sh` reports both; the weekly `cleanup` workflow prunes).
5. **Save state at the phase boundary**: `PHASES.md` status + phase log,
   `STATE.md`, commit, push.

## Step 6 — the current handoff

Whatever `STATE.md` → *Next session, in order* says. Read it; it is kept current
and it is the actual instruction.

---

## Why the repo is the source of truth

The workspace is scratch. It is wiped between sessions, it has a hard size
budget, and twice it has eaten a finished commit. The repo is the only thing
that persists reliably, so:

* **code, docs, plans, gates and tests live in the repo** and nothing important
  exists only in the workspace;
* **renders live in the repo** (`web/video/`) so the published site and the
  artefacts it points at are versioned together;
* **narration is ENGLISH by default** (`--narrate english`, voice
  `en_michael` = Kokoro, Apache-2.0, the voice the owner approved) and the card
  always shows both translations. If a clip comes out with no voice, check you
  have not passed `--narrate urdu`.
* **first run each session fetches 353 MB** of Kokoro weights into
  `~/.cache/kokoro` (outside the snapshot). `bash setup.sh` does it;
  `python3 -m islamic.kokoro --check` says whether it is cached.
* **the workspace holds only: the repo, the token, and the sample files currently
  under review.** Anything else is scratch and gets deleted.
