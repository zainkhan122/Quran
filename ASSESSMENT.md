# Assessment — 6 Urdu TTS repos, Hypit, Lightpanda, vox-director

**Companion to [`BLUEPRINT.md`](BLUEPRINT.md).** Every verdict below is from reading the repos and,
where a model actually exists, from **running it in this sandbox**.

---

## 1. Summary

Of the six Urdu TTS repos, **one turned into a working upgrade**, **one contributed an idea that's
now in the code**, and **four are not directly usable** — three because they never published
weights, one because its model is too large and too slow for this hardware.

Of the three extras you flagged, **Hypit is the most valuable thing in this whole message** —
not for making the audio, but for making the *video* that a naat actually gets shared as.
Lightpanda is genuinely useful but for a narrower job than it first appears.

| Item | Verdict for our pipeline |
|---|---|
| [`ahmedHanzala/urdu-tts`](https://github.com/ahmedHanzala/urdu-tts) | ⚠️ Real weights (3 × 1.7 GB), **MIT licensed** — but too big/slow here |
| [`RamizSaud/TTS`](https://github.com/RamizSaud/TTS) | 📄 Best *documented* quality (MOS 4.2) — ⚠️ no published weights |
| [`harisbinzia/PronouncUR`](https://github.com/harisbinzia/PronouncUR) | 💡 Idea adopted → `lexicon/urdu_overrides.json` |
| [`asghar-rizvi/…Voice-Cloning`](https://github.com/asghar-rizvi/-Urdu-Text-to-Speech-with-Voice-Cloning) | ❌ No weights · **⛔ ethical problem, see §6** |
| [`Ahmad-Ali-Rafique/Urdu-Voice-Chatbot`](https://github.com/Ahmad-Ali-Rafique/Urdu-Voice-Chatbot) | ✅ Contributed the gTTS path → now a working backend |
| — *(6th link was a duplicate of asghar-rizvi)* | — |
| [`hypit-ai/hypit`](https://github.com/hypit-ai/hypit) | 🎯 **Adopt** — the distribution/video layer |
| [`lightpanda-io/browser`](https://github.com/lightpanda-io/browser) | ✅ Adopt for scraping only — ⚠️ **can't render video**, AGPL |
| [`Alisa0808/vox-director`](https://github.com/Alisa0808/vox-director) | ⚠️ Partial — steal `beats.json`, skip the paid cloud |

**Undiscovered bonus:** while verifying these, `syedmuhammad/mms-tts-urdu-vits_finetuned`
(**5,558 downloads** — by far the most-downloaded Urdu TTS model) turned up. Same architecture as
our current voice, so the same memory footprint. It's now engine `mms-ft`. Details in §3.

---

## 2. Repo-by-repo

### `Ahmad-Ali-Rafique/Urdu-Voice-Chatbot` — API wrapper, but one useful part
Streamlit app: Google Speech Recognition → Gemini → Google TTS (`gTTS`), deployed on Streamlit
Cloud. Last commit Aug 2024.

**Not a generation tool** — it needs a Gemini API key and its whole purpose is conversation.
But its third component is worth having: **`gTTS` genuinely supports Urdu**, needs no key, and is
free. I tested it here:

| | |
|---|---|
| Wall time | **0.1 s** for 4.5 s of audio |
| Peak RSS | **52 MB** |
| Audio | 14.33 s for the sample naat at RTF 0.063 |

It's now engine `gtts`. The catch, and it's a real one: it's an **unofficial Google Translate
endpoint**, so it can rate-limit or break without notice, and it needs network. Use it as a
fallback or a second voice, never as the offline backbone.

Its **ASR half is more useful than its chatbot half** — Google/whisper Urdu transcription is
exactly the alignment-QA step I proposed, to diff rendered audio against your lyrics.

### `harisbinzia/PronouncUR` — old tool, good idea, now implemented
2018 research tool: a seq2seq G2P model (2-layer LSTM, 512 hidden) trained on a **hand-curated
expert lexicon of ~39,000 Urdu words**, emitting pronunciation dictionaries for CMUSphinx, Kaldi
or MaryTTS. Last touched May 2020.

It won't run: TensorFlow 1.x on the `g2p-seq2seq` toolkit, on Python 3.13, is not a fight worth
having. But the *concept* is the right one and it's now in our code as
`lexicon/urdu_overrides.json` — a hand-curated surface-form → spoken-form table applied before
synthesis. For sacred vocabulary you want an explicit, human-reviewed, diffable list rather than
trusting whatever a model learned. Their 39k-word lexicon is worth mining later as a data source.

This is the honest version of "adopt the idea, not the code."

### `RamizSaud/TTS` — the best-documented quality, but you can't have it
Tacotron2 + dataset built from YouTube audiobooks, with a **published MDPI paper**. The numbers
are the best I've seen for Urdu TTS anywhere:

- **MOS 4.2** naturalness (vs 3.45 for the Jamal baseline they compare against)
- **WER 8.5%** on test data
- Speaker similarity **85%** for cloned voices (via RVC)

**But:** no HuggingFace weights (I searched — `RamizSaud` has no models on the Hub), Python 3.7,
and the paper's own "Data Availability" points at the GitHub repo for weights that aren't
obviously there. Training from scratch needs a GPU and the audiobook dataset.

Two other flags: the dataset is **audiobook audio scraped from YouTube** (copyright), and the
cloning path is RVC.

**Worth doing:** open an issue asking the author to publish the Tacotron2 + HiFi-GAN checkpoints
to the Hub. If those weights exist, they'd likely beat what we're using, and a Tacotron2 + vocoder
pair (~40 M params) would still fit in this sandbox.

### `ahmedHanzala/urdu-tts` — real weights, wrong size
Tortoise-TTS fine-tune, **MIT licensed** (notable — the most permissive of the six), and
specifically tuned for **South-Asian accent** voice cloning rather than the Americanised output
Tortoise normally produces.

The weights are real and public: [`zohann/urdu-tts`](https://huggingface.co/zohann/urdu-tts) —
but each `ar-model.pth` is **1,716,991,085 bytes (1.7 GB)**, and there are three variants
(single-speaker, multi-speaker, south-asian accent).

1.7 GB of weights in a 2 GB container, plus autoregressive Tortoise inference which is slow even
on a GPU, means **no** for the sandbox. On the 16 GB Actions runner it would load, but
autoregressive TTS on 4 vCPU is slow enough to make it impractical for whole naats. The MIT
licence is the real find — if you ever need a commercially clean Urdu voice, start here.

### `asghar-rizvi/…Voice-Cloning` — don't use this one. See §6.

---

## 3. The upgrade nobody asked for

`syedmuhammad/mms-tts-urdu-vits_finetuned` — **5,558 downloads/month**, the most-downloaded pure
Urdu TTS checkpoint on the Hub (the next real one is ~3,000, then it drops to double digits).

Same VITS architecture as our baseline, fine-tuned on a real Urdu speaker. Heads-up that the
checkpoint carries leftover `discriminator.*` training weights that `transformers` reports as
`UNEXPECTED` — harmless, they're discarded at inference.

Measured side by side on the same 4-line naat:

| Engine | Audio | RTF | Peak RSS |
|---|---|---|---|
| `mms` — Meta baseline | 17.07 s | 0.61× | 748 MB |
| `mms-ft` — fine-tuned | **27.68 s** | **0.38×** | 838 MB |
| `gtts` — Google | 14.33 s | 0.06× | 52 MB |

The fine-tuned voice is **62% slower in delivery** — 27.7 s versus 17.1 s for identical text. For
naat recitation that's not a defect, it's the point: devotional recitation is unhurried, and the
baseline's brighter pace sounds like a news reader. It's also *faster to compute* (RTF 0.38 vs
0.61) because VITS generation cost tracks the padding, not the final duration.

All three are rendered and playing in the studio's library — same lyrics, same seed logic,
back-to-back, so you can judge delivery rather than take my word for it.

---

## 4. Hypit — the one to actually adopt

[`hypit-ai/hypit`](https://github.com/hypit-ai/hypit) · **20.5k ★**, Apache-2.0 *with conditions*,
TypeScript, Node 22.15+, ~1 day since last commit.

It's an agent skill + markup language (**SVML**) for video. You hand an agent a reference clip or
a brief; it produces an editable, re-runnable composition — footage, captions, B-roll, effects —
instead of a one-off MP4.

**Why it matters for naat specifically: timing is anchored to words, not seconds.** Your naat's
lines change length constantly across renders (different engine, different seed, different
tempo), and that is exactly what breaks caption sync in ordinary editors. Word-anchored timing
means rewriting a line re-flows the captions instead of desyncing the edit. And since our whole
pipeline already produces line-timed audio, the fit is direct.

Three more things that line up:

- **$0 rendering is real.** Captions, motion graphics and code-rendered visuals compile **without
  calling any generation model**. For a lyric video — Urdu text over geometric/calligraphic
  backgrounds — you need no paid API at all. This is the correct naat default anyway.
- **Word-level alignment via WhisperX** is already in its pipeline. WhisperX on Urdu gives you the
  timing track, and the same alignment doubles as our **pronunciation-QA** step. One tool, both jobs.
- **Variant generation.** One naat → 9:16 Shorts, 1:1, 16:9; different opening lines; with and
  without backing. Each variant re-runs the same composition.

**Where it breaks for us:** rendering runs through **headless Chromium**, and the authors'
own example describes **64 concurrent browser processes**. That will not run in this 2 GB
sandbox — but it runs fine on the 16 GB Actions runner, which is already in our architecture.

**Licence caution:** advertised Apache-2.0 but published as `NOASSERTION` / "with conditions",
and independent reviewers flag that you should read the LICENSE before commercial use. Read it.

### The pipeline this unlocks

```
lyrics ─► our Urdu TTS + backing + master ─► naat.mp3  (+ line timings)
                                                   │
                                          Hypit / SVML composition
                                                   │
                                    9:16 Shorts · 1:1 · 16:9 lyric videos
```

Audio is solved; Hypit is the missing half that turns audio into something that actually travels.

---

## 5. Lightpanda — useful, but not for what you'd assume

[`lightpanda-io/browser`](https://github.com/lightpanda-io/browser) · ~26k ★, **AGPL-3.0**,
written in Zig, ~10,400 commits and commits 12 hours ago — genuinely active.

The numbers are real and they matter here:

| | Lightpanda | Chrome headless |
|---|---|---|
| Memory | **24–66 MB** (~2 MB/page) | 207–829 MB |
| Startup | ~5 ms | ~3 s |
| Speed | 9–11× faster | — |
| Pages per GB RAM | ~500 | ~10–20 |

It speaks **CDP**, so Puppeteer/Playwright scripts work nearly as-is. In a 2 GB sandbox where
Chrome headless can't even start comfortably, **Lightpanda can run 50+ concurrent pages.**

**The critical limitation, stated plainly: Lightpanda does not render.** It skips CSS layout and
graphical rendering entirely — no screenshots, no visual output. So:

- ❌ It **cannot** replace Chromium for Hypit's rendering step. Hypit turns captions and motion
  graphics into pixels; Lightpanda has no pixel path at all. They are not substitutes.
- ❌ It **cannot** do visual QA of a finished video.
- ✅ It **can** scrape — naat lyric archives, poet biographies, release metadata, traditional
  naat collections to review before you write your own.
- ✅ It **can** automate the boring web side of publishing (form fills, upload flows
  where a plain HTTP client won't do).
- ✅ It **can** run web-research at a scale this sandbox otherwise couldn't.

**Licence:** **AGPL-3.0.** This is the sharpest flag in this whole document. AGPL's network clause
means if you build a *hosted* service around it, you may be obliged to publish your source.
Running it as a local tool for scraping doesn't trigger that, but if the naat site ever grows a
backend that embeds Lightpanda, get real legal advice first.

---

## 6. Two things I won't help with, and why

### Cloning Zia Mohiuddin's voice — please don't

`asghar-rizvi/-Urdu-Text-to-Speech-with-Voice-Cloning` (and
`mradermacher/Orpheus-Urdu-TTS-Zia-Mohyeddin-GGUF`, and
`Aasher/Orpheus-Urdu-TTS-Zia-Mohyeddin`) all clone **Zia Mohyeddin**, the Pakistani broadcaster
and actor who **died in 2021**.

Three independent problems stack up:

1. **Consent.** He cannot consent. His voice is a fixed part of his estate and his family's memory.
2. **Personality rights.** Post-mortem voice/personality protections exist in many jurisdictions
   and are expanding specifically in response to voice cloning.
3. **Adab.** Naat is worship. Putting *someone else's borrowed voice* into an act of devotion —
   unasked, and after their death — is not what the tradition asks for. The reciter's own voice,
   or an honestly synthetic one, is the correct choice.

There's also a practical note: that repo published **no weights at all** and reports only
"mid-level quality" after 50 epochs on a GPU — so it's not even a good trade to make.

**Our default stands: no real person's voice, living or dead, without explicit written consent.**
Our engines are a Meta-trained synthetic voice and Google Translate's synthetic voice. Neither
impersonates anyone. If you *do* want a distinctive voice later, the honest route is to record
yourself or a consenting reciter, then fine-tune VITS on that — `ylacombe/finetune-hf-vits`
will do it, and it's a far better outcome than borrowing a dead man's throat.

### `vox-director` — usable in parts, not as shipped

[`Alisa0808/vox-director`](https://github.com/Alisa0808/vox-director) · 30 commits, updated
5 days ago. An agent skill that turns a topic into a Vox-style paper-collage explainer. Pipeline:
script → collage keyframes → motion → voice-over → music → captions, driven by one `beats.json`.

**The good idea:** `beats.json` — a single machine-readable storyboard that every stage reads.
That's a clean pattern worth copying regardless of the rest.

**What doesn't work for us:**

- It runs on **Atlas Cloud**, a paid image/video generation service. There's no free tier doing
  the heavy lifting; its costs are real.
- Its **voice-over is English-oriented**. It will not recite Urdu — that's our half, and we
  already have it.
- A **Vox-style editorial explainer is tonally wrong for naat.** Busy collage animations and
  rapid cuts fight the register of devotional recitation.

**The verdict:** adopt the `beats.json` pattern for our timeline data; take its ffmpeg assembly
and caption-burning recipes; **drop Atlas Cloud and drop the Vox look.** Pair its ffmpeg layer
with our Urdu narration and you have a lyric video with about 10% of the complexity and none of
the API spend. Hypit is the better-engineered version of the same ambition.

---

## 7. What changed in the code

| Change | File |
|---|---|
| Pluggable voices: `--engine mms \| mms-ft \| gtts` | `naat/tts.py`, `naat/pipeline.py` |
| Pronunciation lexicon applied before synthesis | `lexicon/urdu_overrides.json` |
| A/B renders of all three voices, published to the player | `web/audio/ab-*.mp3` |
| Voice picker + engine in the Actions form | `web/index.html`, `.github/workflows/naat.yml` |
| Manifest now carries voice, engine and memory | `tools/build_manifest.py` |

```bash
python -m naat.pipeline --lyrics lyrics/my_naat.txt --engine mms-ft --style a-cappella
python -m naat.pipeline --lyrics lyrics/my_naat.txt --engine gtts  --style drone
```

Listen to the three `ab-*.mp3` renders in the studio library and tell me which voice you want as
the default — that's the one call here I can't make for you, because it's a question of what
sounds right for recitation, and that's your ear, not mine.

---

## 8. What I'd do next, in order

1. **Pick a voice** from the three A/B renders — one sentence from you and I'll set the default.
2. **Open an issue on `RamizSaud/TTS`** asking for the Tacotron2 + HiFi-GAN checkpoints. MOS 4.2
   would be a real quality jump, and it needs no code from us to find out.
3. **Build the Hypit lyric-video leg** on the 16 GB runner: our MP3 + WhisperX alignment →
   SVML → 9:16 Shorts. This is where naat actually gets heard.
4. **Add the alignment-QA gate** — transcribe each render with Whisper-Urdu and diff against the
   source lines, so a mispronounced honorific is caught by a machine before a human hears it.
5. **Mine PronouncUR's 39k-word lexicon** into our overrides file for broader coverage.

*Assessed 2026-10-11. All audio figures measured in-sandbox during this session.*
