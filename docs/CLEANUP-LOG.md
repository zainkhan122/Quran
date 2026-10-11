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
