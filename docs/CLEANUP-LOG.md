# Cleanup log

Housekeeping is done by `tools/cleanup.py` (and `cleanup.yml` weekly). This file
records the changes that were **destructive** and why, so the reasoning is not
lost with the bytes.

## 2026-10-11 — removed 37.6 MB of abandoned audio from git history

**What:** every `output/*.wav`, `output/*.mp3` and `output/stems/*` blob, plus
the branch that carried them.

**Why:** the workspace snapshot came up over its 128 MB budget twice, and the
second time it dropped 22 files — including the git objects for a finished
commit. An audit found **37.6 MB of naat and tarannum audio** sitting in history:
`recite-ft-bhairavi.wav` (4.8 MB), `ab-mms-ft.wav` (4.7 MB), `demo-naat*.wav`,
`recite-yaman.wav`, `recite-bhairavi.wav` and their stem separations.

None of it was referenced by anything. It was output from the naat/recitation
pipeline, which was **abandoned by the owner** ("Instead of Naats…", and the
tarannum layer explicitly did not satisfy). Output directories are git-ignored
today, so these were early commits made before that rule existed.

**How:** `git filter-branch --index-filter 'git rm -r --cached --ignore-unmatch output'`
over `main`, then the stale local `master` branch was deleted, then the reflog
was expired and the pack pruned.

**Verification before and after:** the HEAD **tree** hash was identical
(`d585e841`), so the contents were unchanged and only history was rewritten. The
104-test suite and every video gate were re-run afterwards.

**Recoverability:** the pre-rewrite tip is `5fb4c507`. The branch that held the
naat work was `f082a18` ("Add tarantum recitation engine") on top of `d71071b`
(the naat pipeline itself). Both were local-only and were never a remote branch.

**Standing rule:** renders and audio go to `output/`, which is git-ignored, and
only the published set (`web/video/`, with its `.build.json`) is committed. If a
render is worth keeping, it is worth putting in `web/video/` through
`tools/publish.py` — which gates it on the way in.

## 2026-10-11 (later) — removed 39.1 MB of retired renders from history

**What:** eleven superseded versions of the three published clips, at the same
three paths in `web/video/`.

**Why:** every re-render commits a new mp4 over the old one and the old blob
stays in `.git` for ever. Three rounds of design changes later the repository
held 26.6 MB of clip bytes for a 10.7 MB published set, on top of the 37.6 MB
of audio removed earlier the same day, and the workspace was back to **4.7 MB of
headroom** against the snapshot limit.

**Why `git gc` was not the fix**, and the note in `tools/cleanup.py` says so:
these blobs are reachable - they are in the trees of the very commits that
published them - so nothing is unreachable for the pruner to collect. Only a
history rewrite frees the space.

**How:** `git filter-branch --index-filter` with a filter that drops an index
entry **only when its staged blob is one of the retired shas**. The path is
never removed, and HEAD's own version of each clip has a different sha, so the
published tree is untouched. Verified: HEAD tree `b84a47f0c2` before and after,
byte for byte. Then the stale `refs/remotes/origin/main` (pointing at the
pre-rewrite commit) was deleted, the reflog expired and the pack pruned - a
tracking ref holds objects alive just as firmly as a branch, which is what made
the first attempt at this look like it had failed.

**Result:** `.git` 86.7 -> 48.9 MB; workspace 123.3 -> **85.5 MB** (42.5 MB
headroom). All eleven retired blobs gone; the three current clips verified
present in the object store at their exact on-disk sizes.

**Standing rule, restated:** the clip set is published from `web/video/`, and a
re-render therefore costs ~11 MB of permanent history every time. Squeeze when
headroom drops below ~15 MB, batched - not after every render.
