# State — 2026-10-11 (after Phase 1)

Resume capsule. One screen. If this file and the repo disagree, the repo wins —
fix this file.

## Where things stand

* **Phases 0 and 1 are complete.** The studio renders, and all three clips are
  published to `web/video/`.
* **Next is Phase 2 — cloud rendering.** The local box has no blockers left; the
  reason to move is that a GitHub runner gives 4 vCPU / 16 GB free on a public repo
  versus 2 GB here, which is 6–17× faster and removes the memory ceiling entirely.

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

1. `bash setup.sh --check`, then read `PHASES.md` → Phase 2.
2. Add `.github/workflows/render.yml`: matrix over references, one runner each,
   `max-parallel` 5, outputs to a Release. Model it on the design in `PHASES.md`
   § *Auto-render plan*, which records what was verified about runner specs and cost.
3. The runner needs `bash setup.sh` (no apt fonts required — the fonts are committed)
   and no secrets: **use the automatic `GITHUB_TOKEN` with `contents: write`**, not a
   personal PAT. Do not add a PAT to the repo or to the workflow.
4. Render one reference on the runner before fanning out; compare its output against
   the local render of the same reference.
5. Update this file and `PHASES.md`, commit, push.

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
