# State — 2026-10-11

Resume capsule. One screen. If this file and the repo disagree, the repo wins —
fix this file.

## Where things stand

* **Phase 0 is complete.** One renderer, clean tree, plan and log in `PHASES.md`.
* **Nothing has been published from the current renderer.** `web/video/` still holds
  the earlier three clips (`quran-30-21`, `quran-81-8`, `ibnmajah-224`); they will be
  re-rendered in Phase 1.
* **The studio renderer does not currently finish a render** (known defect, below).
  That is the whole of Phase 1.

## Blockers, with the evidence, so they are not re-derived

1. **ffmpeg tail-hang in `islamic/studio.py:render()`.** Frames stream in fine
   (375 frames fed in 4.9 s) and the process then waits forever after stdin closes.
   Reproduced twice, including with synthetic frames, so it is the command shape and
   not the compositor. x264 is not the cause: 300 standalone 1080×1920 medium-preset
   frames encode in 8.7 s. Suspects: `apad` + `-shortest` inside the filter-complex
   feed, and AAC encoder delay at the tail. Bound every render with a timeout.
2. **Urdu TTS OOM.** `islamic/produce.py:narrate()` synthesises in the render
   process. Freeing the model returns ~484 MB to the process but not to the OS, and
   ffmpeg is then killed by the OOM killer — as a signal death it produces *no*
   error text, which is why the first diagnosis was wrong. `islamic/narrate.py`
   already runs the model in a short-lived child process; wire `produce.py` to it.
3. **Cold palette for pending words.** Un-recited words in `studio.py` draw in a
   steel tone. Warm them before the first render.

## Ready to wire (written and tested, not yet used by the pipeline)

| File | What it does | Verified |
|---|---|---|
| `islamic/narrate.py` | Urdu narration in a child process; returns the box before encoding | ✅ ran: 10.2 s of audio, 3 measured |

## Facts a next session would otherwise have to look up

* **Audio/timings are authoritative, not estimated.** `islamic/timings.py` reads
  `audio.segments` from the same quran.com v4 response that carries the recitation
  URL, so word timings belong to the exact file we play. Do not reintroduce a
  forced aligner or a separate timing dataset.
* Topic headlines live in `islamic/topics.py` and are the video maker's own words,
  deliberately short (one to two lines). They are captions, never scripture and
  never a translation.
* `output/` is git-ignored. Build folders are the source of truth for publishing:
  `videos.json` + `sources.json`, read by `tools/publish.py`.
* Fonts must never be trusted by filename — verify magic bytes
  (`tools/fetch_fonts.py`). Three shipped as HTML and rendered silently wrong.
* Free tiers used: GitHub Actions for renders (public repo, unlimited minutes),
  Pages for the site. No paid API anywhere in the Qur'an path.

## Toolchain (not persisted — rerun to restore)

`bash setup.sh` re-asserts everything: ffmpeg, pillow/numpy/scipy/soundfile, CPU
torch + transformers for the Urdu voice, verified fonts, ornament. `--check` for a
verification pass that installs nothing.

## Next session, in order

1. `bash setup.sh --check`
2. Read this file, then `PHASES.md` → *Known work for Phase 1*.
3. Fix the hang, wire `narrate.py`, warm the pending-word colour.
4. Render the three references, one at a time, each under a timeout.
5. `python3 tools/publish.py` → confirm `web/video/manifest.json`.
6. Update this file and `PHASES.md`, commit, push.
