# State — 2026-10-11 (Phases 0-4a done; cloud dispatch pending a token)

Resume capsule. One screen. If this file and the repo disagree, the repo wins —
fix this file.

## Where things stand

* **Phases 0, 1, 3 and 4 are complete.** The studio renders, the three clips are
  published to `web/video/`, nothing can reach the site without passing the gates
  in `tools/check_video.py`, and nothing can be *planned* whose topic the verse
  does not carry (`tools/check_relevance.py`).
* **Phase 2 is built and rehearsed but not dispatched.** The outstanding step is the
  one that needs GitHub credentials — push, then dispatch the run. See *The one thing
  blocking Phase 2*.
* **Diacritization is a dead end for free.** Proven that harakat change the
  phonemes (6 of 8 test words), so the root cause is reachable in principle —
  but hand-written harakat degraded the words a native ear could check, and
  Piper's bundled Arabic tashkeel turns `دعا` into "daa-anaa". No Urdu
  diacritizer exists on Hugging Face. The remaining gap is the acoustic model,
  which means a heavier engine on Actions or nothing.
* **The card shows Arabic word-by-word, Urdu, and — with `--english` — the
  English translation; `--narrate english` makes the *voice* English. They are
  separate flags on purpose. Verified: `web`-quality frame at
  `english-sample-frame.png`.
* **Narration now reads in flow, and can speak English.** `say_flow()` reads a
  passage in one pass instead of one utterance per line with a flat glue; dead
  air in the clip fell 12.0% -> 7.2% (male) and 15.3% -> 3.5% (female), N=5.
  `--narrate english` renders the same card with an English voice; `en` (Lessac)
  sounds better but is research-licensed, `en_free` (LibriTTS-R, CC BY 4.0) is
  the shippable one. Both need their declared pace or they run ~40 wpm too fast.
* **Five commits are waiting to be pushed** (Phase 2, 3, 4 and 4a work). Clean
  fast-forward over `origin/main`; no force is needed.
* **The narration voice is MIT now.** `facebook/mms-tts-urd-script_arabic` is
  CC-BY-NC — non-commercial — and was replaced by Piper `ur_PK-fasih` (male, MIT,
  63 MB, RTF 0.08, 6.4x faster). `--engine mms` still selects the old one; do not
  ship it.

## Read this first, every session

**Two things are not persisted, and both have already cost a session's work.**

1. **`.git` does not reliably survive the snapshot.** Twice now a finished
   commit has been present at the end of a session and absent afterwards, with
   the working tree fully intact. `.git/config` goes too. The first time was a
   plain rollback; the second was a 154 MB snapshot against a 128 MB budget,
   where 22 files — the new git objects — were dropped.
   Recovery is `cp setup/git-config.template .git/config` then re-commit;
   `naat-ai-ahead.bundle` beside the repo restores the local commits in one
   command if they are ever lost again.
2. **`~/.cache` is excluded from snapshots by design**, so the Urdu voice
   weights are re-fetched by `setup.sh` each session (~60 MB, once). The network
   cache for fetched scripture now lives at `~/.cache/islamic-studio` for the
   same reason — it used to live in the repo and charged 32 MB against the
   budget every session.

## Read this first, every session (git check)

**A commit made in a session does not always survive the sandbox reset.** On
2026-10-11 the Phase 4 commit (`89dec05`) was present at the end of the session
and absent afterwards: `.git` had been rolled back to `67131c2` while the
*working tree* kept every file. The author's own check ("tree clean") passed at
the time and proved nothing about persistence.

So the first command of a session is:

```bash
git log --oneline -3        # is the last session's commit still there?
git status --porcelain      # if the files are here but untracked, it was lost
```

If it was lost, the work is not lost with it — re-commit it. Do not assume.

## Run these before you commit

```bash
bash setup.sh --check                          # ~9 s
python3 -m unittest discover -s tests          # 91 tests, ~15 s, stdlib, offline
python3 tools/check_relevance.py --audit       # topic vs its own refs (needs network)
python3 tools/voice_metrics.py FILE.wav        # delivery: pauses, pitch range, wpm
du -sh --exclude=.cache --exclude=__pycache__ --exclude=node_modules \
  /home/user                                    # budget: must stay under 128 MB
# NOTE: plain `du -sh /home/user` over-reports by ~60 MB of voice weights in
# ~/.cache, which the snapshot excludes. Use the excludes above or you will
# panic about a budget that is fine, or worse, miss a real overrun.
python3 tools/plan_render.py --plan --offline  # the plan the workflow would build
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
* **The voice switch renders.** `--ref quran:81:8 --topic justice` on Piper `fasih`
  produced 11.23 s / 1.18 MB / −15.0 LUFS, passing `check_video.py` and
  `check_relevance.py`. Wall time ~15 s.
* **Topic relevance audits clean.** `tools/check_relevance.py --audit` →
  **34/34 refs across 10 topics** carried by their own headline. The reviewed
  pairing (`daughters` + `quran:81:8`) is **refused**, and `plan_render.py` exits 1
  on it before any runner is spent.
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
   is missing. Read `PHASES.md` → Phase 4, then the runbook above.
2. **Restore the token**, then `tools/cloud.sh push` (now 4 commits).
3. Dispatch ONE clip, read its job log, and compare the runner's output against the
   local render — duration, size and loudness should all agree.
4. If it holds, dispatch the full library. **Re-render `quran-30-21` and `ibnmajah-224`
   on Piper** — both are still the old MMS audio, and the 52 s clip is the one most
   likely to expose a breath-group problem. `quran-81-8` is already Piper, but its
   published headline is still the retired "Daughters — a blessing"; the re-render
   fixes the frame as well as the voice.
5. Then Phase 5: `parents` motif, grow `library.json` from the 34 validated refs
   (~10 at a time, `--audit` after each batch), add `--daily N` rotation.
6. **Get a native Urdu speaker to hear `urdu-english-voice-samples.mp3`.** That is
   the only test that settles the robotic question; every number here is a proxy.

## Open items, honestly

* `parents` still has no motif of its own — it falls back to the generic islimi
  layer. `justice` and `fairness` are new topics with no motif at all. Phase 5.
* **The relevance gate cannot certify a translation.** It checks that the words the
  headline claims actually occur in the text we display. It cannot read context, it
  cannot see a metaphor, and it says nothing about whether the translation is
  right. It is a tripwire for one specific failure, not a review.
* **No Urdu speaker has heard the output.** WER against whisper-base is a weak
  proxy and could not distinguish the voices. A native speaker is the only test
  that settles whether it still sounds robotic.
* **The pause count is noisy.** Piper samples internally, so the same text run 5
  times gives pause counts from 7.9 to 25.8 per minute. Silence *fraction* is the
  stable signal and is what the reduction is claimed on. Do not quote a precise
  pause reduction.
* **Two of the three published clips carry the non-commercial MMS voice.** They are
  still up. Re-render before any monetisation.
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
