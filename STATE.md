# State — 2026-10-11 (Phases 0-3 done; cloud dispatch pending a token)

Resume capsule. One screen. If this file and the repo disagree, the repo wins —
fix this file.

## Where things stand

* **Phases 0, 1 and 3 are complete.** The studio renders, the three clips are
  published to `web/video/`, and nothing can reach the site now without passing the
  gates in `tools/check_video.py`.
* **Phase 2 is built and rehearsed but not dispatched.** The outstanding step is the
  one that needs GitHub credentials — push, then dispatch the run. See *The one thing
  blocking Phase 2*.
* **Three commits are waiting to be pushed** (Phase 2 and Phase 3 work). They are a
  clean fast-forward over `origin/main`; no force is needed.

## Run these before you commit

```bash
bash setup.sh --check                          # ~9 s
python3 -m unittest discover -s tests          # 27 tests, ~10 s, stdlib only
python3 tools/publish.py                       # gates every clip, then writes the site
```

## The one thing blocking Phase 2

The sandbox reset wiped `/tmp/.ght`, where the PAT lives. That is the design
working correctly — `/tmp` is outside the snapshot on purpose, because the
workspace is shareable and the repo is public — but it means the token has to be
supplied again to push. The workflow itself needs **no** PAT: it uses GitHub's
automatic `GITHUB_TOKEN`.

```bash
printf '%s' '<token>' > /tmp/.ght && chmod 600 /tmp/.ght
tools/cloud.sh push                          # the Phase 2 commits
tools/cloud.sh render quran-81-8             # ONE clip first, to validate the runner
tools/cloud.sh runs                          # then read the run id
tools/cloud.sh logs <run-id>
tools/cloud.sh render                        # then the full library
```

Validate on one clip before fanning out: it costs minutes and catches a
runner-environment failure without burning three parallel runners on it.

## The published set (verified this session)

| File | Duration | Size | Reference | Topic |
|---|---|---|---|---|
| `quran-81-8.mp4` | 11.60 s | 1.26 MB | `quran:81:8` | Daughters |
| `quran-30-21.mp4` | 52.57 s | 5.98 MB | `quran:30:21` | Marriage |
| `ibnmajah-224.mp4` | 47.60 s | 4.27 MB | `ibnmajah:224` | Knowledge |

All 1080×1920 @ 30 fps, h264 high + AAC 192k, `+faststart`, averaged −14.3 LUFS.
Word-by-word Arabic for the Qur'an clips; the hadith shows its isnad and is not
auto-narrated.

## What Phase 1 changed (do not re-fix these)

1. **The render hang is gone.** Root cause: a bare `apad` pads with silence forever
   and `-shortest` cannot propagate EOF from a stdin video feed, so the encode never
   ended. Now `apad=whole_dur=<total>` plus an explicit `-t`. A 5 s A/B: 32 s+ hang
   versus 2.6 s. `-shortest` must not come back.
2. **A render can no longer eat a session.** `render()` has a deadline, a bounded
   wait at the close, and writes ffmpeg's stderr to `output/video/render.log`.
   A failure now reports itself.
3. **Urdu narration runs in a child process** (`islamic/narrate.py`), called from
   `produce.narrate()`. In-process synthesis left ~484 MB of torch memory that the
   OS never got back, and ffmpeg was then killed by a signal with no stderr.
4. **The static-Arabic fitter** is constrained by stage height, not by a line cap
   of 22 (which was also capping the type at 64 px). The isnad now sets at 87 px.
5. **Pending words** are brass in shadow (`146,124,84`), not cold steel.

## The gates (Phase 3) — what now stands between a render and the site

`tools/check_video.py` runs inside `tools/publish.py`, so a clip must pass before it
is copied to `web/video/`. A failure holds that clip back, exits non-zero, and leaves
the previously published version in place.

| Checked | Why it matters |
|---|---|
| citation present (reference + readable source) | a clip with no citation must never ship |
| sacred text present and non-empty | an empty Arabic body is a broken card |
| **a Qur'an clip names its reciter** | the fingerprint of the TTS fallback; real recitation is the promise |
| a Qur'an clip records its `timings_source` | word-level sync has to be evidenceable |
| collection on `TRUSTED_COLLECTIONS` | the trust boundary, re-asserted at publication |
| hadith carries a grade | the frame always shows one |
| timed word count == words on the clip | catches a reveal silently dropping a word |
| h264 / yuv420p / 1080×1920 / aac 44.1 kHz | it has to play everywhere |
| duration floor and ceiling, agreement with the build record | catches truncation |
| integrated loudness within −18..−11 LUFS | catches a silent or blown mix |

`tests/test_gates.py` pins all of it. Every promise has a test that fails it on
purpose, so the gate cannot rot into a rubber stamp.

## Verified, with the measurement, so it does not have to be re-checked

* **Word-level sync is real.** Settled-word ink grows monotonically at t≈1.0 / 1.5 /
  2.9 s for `quran:81:8`, matching the word boundaries in `audio.segments`.
  Method: seek and count pixels near the settled colour in the body band.
* **Timings are the publisher's own.** `islamic/timings.py` reads `audio.segments`
  from the same quran.com v4 response that carries the recitation URL. Do not
  reintroduce a forced aligner or a separate timing dataset.
* **Loudness** is −14.3 LUFS (I) across the set, LRA 4.9.
* **The site serves.** `index.html`, `video/manifest.json`, an MP4 and a poster all
  return 200 from `python3 -m http.server --directory web`.

## Environment (not persisted — one command restores it)

```bash
bash setup.sh --check     # ~9 s: ffmpeg, wheels, raqm shaping, fonts, ornament
bash setup.sh             # ~3 min cold: the repair/install path
```

A fresh session also needs `cp setup/git-config.template .git/config` if `.git/config`
is missing (the workspace snapshot excludes it), and the PAT lives at `/tmp/.ght`
(0600, deliberately outside `/home/user` so it is never snapshotted).

## Next session, in order

1. `bash setup.sh --check`; `cp setup/git-config.template .git/config` if the remote
   is missing. Read `PHASES.md` → Phase 2, then the runbook above.
2. Restore the token, then `tools/cloud.sh push`.
3. Dispatch one clip, read its job log, and compare the runner's output against the
   local render of the same clip — duration, size and loudness should all agree.
4. If it holds, dispatch the full library, and confirm the Release and the site commit.
5. Mark Phase 2 done, then start Phase 3: expand `tools/check_video.py` into the full
   QA layer.

## Open items, honestly

* `parents` still has no motif of its own (7 of 8) — it falls back to the generic
  islimi layer. Phase 4.
* Topic reference lists in `islamic/topics.py` are seeds and want a human check
  before they are treated as authoritative.
* The Urdu translation narration is TTS reading published text. A human voice would
  be better; that is a consent and naming problem, not a technical one.
* `ibnmajah:224` is graded "See a scholar — this collection contains a range of
  grades", which is shown on the frame. A better-sourced collection would let the
  set lead with a hadith whose grade is unambiguous.
* The cloud workflow commits `web/video` to `main`, so a local session must
  `git fetch` before committing or it will diverge. Phase 5 could move delivery to a
  Pages artifact instead, removing the churn.
* `tools/cloud.sh` is thin and its argument handling is unverified beyond the
  no-token path.
* The gate is deliberately quiet about **whether the Arabic is correct**. That is
  enforced upstream by fetching verbatim and validating; this layer is the last cheap
  net, not a proof of authenticity. `STATE.md` should not be read as claiming the
  gate can certify scripture — only that it can catch a clip that has lost its
  citation, its reciter or a word.
