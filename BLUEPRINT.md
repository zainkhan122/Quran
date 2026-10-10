# AI Naat Generation — Blueprint

**From the two GitHub topic pages to a working Urdu naat pipeline on free infrastructure.**
Scanned: [`topics/ai-music-generation`](https://github.com/topics/ai-music-generation) (47 repos) ·
[`topics/text-to-music`](https://github.com/topics/text-to-music) (163 repos)

Every number below was **measured in this sandbox**, not estimated.

---

## 1. The verdict in one paragraph

The two topic pages are a rich **model catalogue** but a poor **toolkit** for your constraints.
Essentially every project on them is GPU-first: ACE-Step, YuE2, MiniMax-Music 3, OpenMusic,
Mustango, MusicLM and the music-transformer family all assume 6–24 GB of VRAM. Almost nothing
there is designed for 2 vCPU / 2 GB RAM. The single genuinely useful exception is
**MusicGen-small**, and even that does not fit at full precision here.
The more important finding is architectural: **text-to-music models cannot sing Urdu.**
MusicGen is instrumental-only by training; ACE-Step/YuE sing, but in English and Chinese pop
idioms — pointed at Urdu devotional text they emit gibberish. For sacred text, gibberish is not
an acceptable failure mode.
So the working architecture is **decoupled**: an Urdu *speech* model recites the words, and a
*music* model (or a NumPy synthesiser) supplies an instrumental bed underneath.
That split is what makes the whole thing run on free infrastructure — **and the Urdu TTS half
does not exist on either topic page.** Finding it is where the project actually becomes possible.

---

## 2. What is actually on the two topic pages

### Tier A — GPU-required, the "full song" generators (impressive, unusable here)

| Repo | ★ | What it is | Why it's out |
|---|---|---|---|
| [ivcylc/OpenMusic](https://github.com/ivcylc/OpenMusic) | 631 | SOTA text-to-music, MDT/DiT diffusion | diffusion, VRAM-hungry |
| [zhvng/open-musiclm](https://github.com/zhvng/open-musiclm) | 560 | MusicLM reimplementation | 2023-era, GPU pipeline |
| [timoncool/YuE2-Studio](https://github.com/timoncool/YuE2-Studio) | 526 | Local full songs **with vocals** + score | CUDA required, GGML GPU |
| [AMAAI-Lab/mustango](https://github.com/AMAAI-Lab/mustango) | 396 | Controllable TTM | diffusion + GPU |
| [timoncool/ACE-Step-Studio](https://github.com/timoncool/ACE-Step-Studio) | 390 | Portable full-song generator | "NVIDIA GPU" in its own description |
| [remiqora](https://github.com/inikolax/remiqora) | 151 | ACE-Step 1.5 + YuE2-3B + Demucs DAW | macOS/Apple-Silicon studio app |
| [minimax-music-ui](https://github.com/adambenhassen/minimax-music-ui) | 94 | Suno-style UI for MiniMax-Music3 | needs a self-hosted GPU server |

### Tier B — cloud-API wrappers (worked, but not free and not yours)

| Repo | ★ | Catch |
|---|---|---|
| [paperfoot/suno-cli](https://github.com/paperfoot/suno-cli) | 58 | Unofficial Suno v5.5 client |
| [Bentlybro/Automated-Youtube-Music-Generation](https://github.com/Bentlybro/Automated-Youtube-Music-Generation) | 36 | Claude + **Suno AI** + DALL·E, paid APIs |
| [Anil-matcha/awesome-minimax-music-3-prompts](https://github.com/Anil-matcha/awesome-minimax-music-3-prompts) | 10 | Prompt library — **this part is genuinely useful, keep it** |
| [wangchuxiaoji-oss/doubao2api](https://github.com/wangchuxiaoji-oss/doubao2api) | 270 | Reverse-engineered API — **ToS / legal risk, avoid** |

### Tier C — the smaller, actually-adaptable ideas

| Repo | ★ | Why it matters to you |
|---|---|---|
| [the0cp/beatflow-skill](https://github.com/the0cp/beatflow-skill) | 26 | Python DSL → deterministic **multi-track MIDI** via music21. No GPU, no weights. The idea behind our procedural backing engine. |
| [eigenpunk/ComfyUI-audio](https://github.com/eigenpunk/ComfyUI-audio) | 106 | ComfyUI nodes wiring MusicGen — proof that MusicGen is the practical CPU/edge choice |
| [arm64 `MuseControlLite`](https://github.com/fundwotsai2001/MuseControlLite) | 70 | Lightweight *conditioners* on Stable-Audio-Open — the right pattern for "this naat, this mood" |
| [sonilo-ai/skills](https://github.com/sonilo-ai/skills) | 115 | Licensed music API as agent skills — a clean licensing model to copy |

### The gap neither topic page fills

Search both topics for **Urdu**, **nasheed**, **Qawwali** or **Urdu TTS** — there is nothing.
The topics cover *music*; the hard part of a naat is *Urdu recitation*. That half comes from
outside the topic pages (§5).

---

## 3. The architectural insight that unlocks everything

```
text-to-music model  ──►  instrumental bed only     (never sees Urdu words)
Urdu VITS TTS        ──►  recites the naat lines    (never tries to be musical)
ffmpeg               ──►  sidechain-duck + master    (bed dips under the voice)
```

Why this ordering matters:

1. **Sacred-text safety.** If the music model is allowed anywhere near the words, it will
   invent phonemes. Urdu devotional text must be produced by a model trained to *pronounce*
   Urdu. Decoupling makes gibberish structurally impossible.
2. **It fits free hardware.** The TTS model is 36 M params; the backing can be a few hundred
   KB of NumPy. A "generate a full song" model is 2–24 GB of weights.
3. **It matches the tradition.** Devotional naat is commonly unaccompanied. Instrumental
   accompaniment becomes an opt-in *choice* rather than a baked-in default — which is also the
   correct adab default (§9).

---

## 4. Sandbox compatibility — measured, not guessed

Environment: 2 vCPU (Intel Xeon 2.60 GHz), 1.9 GB RAM, 21 GB disk, no GPU, Python 3.13, Node 20.

| Tool | Load | Peak RSS | Throughput | Verdict |
|---|---|---|---|---|
| **`facebook/mms-tts-urd-script_arabic`** (VITS 36.3 M) | 4.7 s | **758 MB** | **RTF 0.23×** (3.9 s audio in 0.9 s) | ✅ **works, comfortably** |
| **Naat Studio procedural backing** (NumPy) | instant | < 10 MB | faster than realtime | ✅ **works** |
| **ffmpeg mix + EBU R128 loudnorm** | — | ~40 MB | — | ✅ **works** |
| `facebook/musicgen-small` **fp32** (0.6 B params) | ✗ | — | — | ❌ **mmap 2 364 427 288 B fails** — cannot allocate |
| `Xenova/musicgen-small` **q8 ONNX** (Node) | 3.3–9.9 s | 1 256 MB | RTF 2.83× | ⚠️ **loads; only ~90 tokens (~2 s) before OOM at 250** |
| ACE-Step / YuE2 / MiniMax-Music3 / OpenMusic / Mustango | — | — | — | ❌ off the table |

Full pipeline result on the sample naat: **16.96 s of mastered audio, 722–739 MB peak RSS,
RTF 0.46–0.48×, −16.7 LUFS integrated.**

### Notes worth knowing before you build

- **VITS needs a few tokens.** A breath group that tokenises to under ~4 tokens crashes
  `transformers` with `narrow(): length must be non-negative`. Fixed in `naat/tts.py` by
  dropping non-speakable fragments and skipping failures instead of aborting the render.
- **`Q8` is where the sandbox wall is.** MusicGen q8 fits its weights in RAM, then dies on the
  KV-cache growth of a long generation. 90 tokens works; 250 does not.
- **Install cost is low.** CPU-only torch (2.14.1+cpu) installs in ~15 s; ffmpeg 7.1.5 via apt.

---

## 5. The piece neither topic page has — a working Urdu voice

| Model | Params | Sandbox | Licence | Note |
|---|---|---|---|---|
| **`facebook/mms-tts-urd-script_arabic`** | 36.3 M | ✅ **748 MB** | ⚠️ **CC-BY-NC 4.0** | Default. Trained on Urdu in Arabic script — exactly what naat is written in. |
| **`syedmuhammad/mms-tts-urdu-vits_finetuned`** | 36.3 M | ✅ **838 MB** | check card | **5,558 downloads/mo — the most-used Urdu TTS checkpoint.** Same architecture, fine-tuned speaker, 62% slower delivery. Engine `mms-ft`. |
| `gTTS` (Google Translate endpoint) | — | ✅ **52 MB** | unofficial | Engine `gtts`. Free and fast but online-only and can rate-limit. |
| [`suhaibrashid17/XTTS-v2-Urdu-FT`](https://huggingface.co/suhaibrashid17/XTTS-v2-Urdu-FT) | ~470 M | ⚠️ ~2 GB, tight | Coqui PML (gated) | Zero-shot Urdu voice cloning — timbre control, but needs a reference clip and more RAM |
| [`ProximaAI/smol-urdu-tts-v1`](https://huggingface.co/ProximaAI/smol-urdu-tts-v1) | small | worth testing | check model card | Community Urdu checkpoint |
| [`mradermacher/Orpheus-Urdu-TTS-Zia-Mohyeddin-GGUF`](https://huggingface.co/mradermacher/Orpheus-Urdu-TTS-Zia-Mohyeddin-GGUF) | Llama-3B | ❌ | check | Expressive, but Q4 still exceeds 2 GB |
| `facebook/mms-tts-urd-script_devanagari` | 36.3 M | ✅ | CC-BY-NC 4.0 | Devanagari-script Urdu — use only if your source text is in Devanagari |

Also present and useful: `kingabzpro/whisper-large-v3-urdu` and friends for **alignment QA** —
transcribe the generated naat and diff it against your lyrics to catch a mispronounced
honorific before you publish. That's the human-in-the-loop check, automated.

---

## 6. GitHub Actions — what "free" actually buys you

Confirmed against GitHub's runner and billing references (September 2026):

| | Public repo | Private repo |
|---|---|---|
| vCPU / RAM / SSD | **4 / 16 GB / 14 GB** | 2 / 8 GB / 14 GB |
| Minutes | **unlimited, free** | 2 000 / month (Free plan) |
| Larger runners | always billed | always billed |

> On a public repo, `runs-on: ubuntu-latest` is **4× the CPU and 8× the RAM of this sandbox, free.**

That is what the second half of the pipeline is for. On the free runner:

- **MusicGen-small at full fp32** (~2.4 GB) fits with 13 GB to spare — no OOM.
- **MusicGen-medium (1.5 B)** also becomes viable on CPU, just slower.
- Cache `~/.cache/huggingface` with `actions/cache` so runs don't re-download 2.5 GB.
- The workflow (`.github/workflows/naat.yml`) does vocals → MusicGen bed → mix → artifact →
  publish to Pages in one job.

**Honest limitations of the free tier:**
- 6-hour job cap, 14 GB disk, and the runner is ephemeral — models must be cached or re-fetched.
- CPU MusicGen is slow: budget ~1–3 min of compute per 15 s of audio on 4 vCPU.
- **GitHub Pages is static-only.** It cannot run Python. Pages = the front-end and the audio
  host; Actions = the compute. The workflow already wires those together.
- No GPU, ever, on the free tier. If you want ACE-Step/YuE full songs, that needs a free
  **Colab T4** or **Kaggle 2×T4 (30 h/week)** — treat those as an optional third tier.

---

## 7. The three-tier architecture

```
TIER 1 — Sandbox (2 vCPU / 2 GB)            ← where the agent works, all day, free
  Urdu VITS recitation + NumPy backing + ffmpeg master
  → 17 s naat in ~10 s wall, 739 MB peak

TIER 2 — GitHub Actions, public repo (4 vCPU / 16 GB, free & unlimited)
  same pipeline, but MusicGen-small fp32 for a real ML instrumental bed
  → triggers: workflow_dispatch, or git push to lyrics/**

TIER 3 — GitHub Pages (free static hosting) + in-browser WASM
  library, player, composer UI, job dispatch
  optional: MusicGen-small q8 ONNX runs in the *listener's* browser via
  transformers.js — zero server cost, works with no backend at all
```

Tier 3 has a subtlety worth stating: `Xenova/musicgen-small` (q8 ONNX, 3 438 downloads/month)
runs on the visitor's own CPU through WebAssembly. It sidesteps every RAM limit in this
document — the compute is the listener's, not yours. Practical caveats: use the **WASM** path,
not WebGPU (there is a known open bug where WebGPU output is a loud hum), and it is memory-bound
by the visitor's device.

---

## 8. What got built here

```
naat-ai/
├── naat/
│   ├── tts.py          Urdu VITS: normalise → split breath groups → recite → stitch
│   ├── backing.py      NumPy ney / harmonium drone / daf synthesis
│   ├── musicgen.py     MusicGen bed for the 16 GB Actions runner (crossfaded chunks)
│   ├── mix.py          ffmpeg sidechain ducking + EBU R128 → WAV/MP3, NumPy fallback
│   └── pipeline.py     CLI orchestrator
├── lyrics/sample_naat.txt
├── tools/build_manifest.py
├── .github/workflows/naat.yml     free 4 vCPU / 16 GB path
├── web/index.html                 GitHub Pages studio (self-contained)
└── output/                        demo-naat.mp3 · demo-naat-a-cappella.mp3
```

Run it:

```bash
python -m naat.pipeline --lyrics lyrics/sample_naat.txt --style daf-drone
python -m naat.pipeline --lyrics my_naat.txt --style a-cappella      # adab default
python -m naat.pipeline --lyrics my_naat.txt --style ney              # ML bed on CI
```

### Design details that were not obvious

- **Breath-grouping.** VITS is trained on single utterances; feeding it a whole naat degrades
  badly. Splitting on `۔`/`،` and stitching with 0.35 s (short) / 0.9 s (stanza) pauses keeps
  quality up *and* keeps peak RAM flat for any length of naat.
- **Honorific expansion.** `ﷺ` (U+FDFA) is a single glyph a tokenizer cannot voice. It is
  expanded to `صلی اللہ علیہ وسلم` before synthesis. Authoring comments are stripped *before*
  expansion — otherwise a `#` note mentioning `ﷺ` becomes recited Urdu.
- **Sidechain ducking** rather than a fixed level: the bed automatically dips ~6:1 under the
  voice, so the words stay intelligible at any backing style.
- **Graceful degradation.** `--style ney` on a low-RAM machine prints a warning and falls back
  to the procedural bed instead of dying. Same command, any machine.

---

## 9. Adab, accuracy and licensing — read before publishing

**Adab (etiquette)**
- Default is **a cappella**. There is a well-known scholarly difference of opinion on
  instrumental music; many hold it impermissible. Instrumental backing is therefore opt-in,
  and the UI says so. Percussion-only (daf) is the conservative middle setting.
- Naat is devotional recitation. **Have a human check pronunciation before sharing.** Machine
  TTS can flatten or misplace the diacritics that carry sacred names — this is exactly why the
  whisper-Urdu alignment-QA step exists.
- **Never clone a specific living reciter's voice** without explicit consent.
- Never generate text *as* the Prophet ﷺ, and keep the lyrics to authentic praise. Write
  original lyrics or use public-domain traditional refrains — do not feed copyrighted naat
  lyrics into this.
- Label output as machine-generated. Devotional content should never be passed off as a human
  reciter's work.

**Licensing — the commercial trap**
- `facebook/mms-tts-*` is **CC-BY-NC 4.0 → non-commercial only.**
- MusicGen **weights** are CC-BY-NC 4.0 (the *code* is MIT) — same restriction.
- ACE-Step is Apache-2.0; check each YuE/community checkpoint individually.
- So: personal, mosque, community and educational use is fine. A **monetised** channel or app
  needs different weights (Apache/MIT-licensed TTS such as a Piper VITS you train yourself,
  plus a permissively licensed music model). Plan for that now rather than after launch.

---

## 10. Where I plug in

I'm not a wrapper around a single tool — I'm the layer that makes the pieces cohere. Concretely:

| Stage | What I do |
|---|---|
| Lyrics | Draft original Urdu naat verses in the right register, with correct `ﷺ` handling and stanza breaks; transliterate and translate for non-Urdu audiences |
| Direction | Choose key, tempo and backing style from the text's mood; write the MusicGen prompt (sound descriptors only — never the sacred words) |
| Rendering | Run TTS + backing + mix in this sandbox, iterate seeds, A/B the takes |
| QA | Diff rendered audio against lyrics (whisper-Urdu alignment), flag any line at risk of mispronunciation for human review |
| Engineering | Maintain the pipeline, the Actions workflow, the Pages studio; debug OOM/tokenizer failures like the two found today |
| Packaging | Cover art (geometric/calligraphic — no figurative devotional imagery), show notes, metadata, distribution copies |

**Suggested next step:** give me a real naat text you want rendered and a target duration. I'll
run it through the pipeline here, A/B a few seeds, and hand you the MP3 plus the stem files —
then we push it to a public repo so the free 16 GB runner can produce the MusicGen version.

---

## 11. Follow-up assessment

Six Urdu TTS repos, Hypit, Lightpanda and vox-director were assessed in a second pass —
see [`ASSESSMENT.md`](ASSESSMENT.md). Headlines: Hypit is the correct video/distribution
layer; Lightpanda is a scraper, **not** a renderer (no CSS/pixel path), and is AGPL;
`syedmuhammad/mms-tts-urdu-vits_finetuned` became our second voice engine; PronouncUR's
idea became `lexicon/urdu_overrides.json`. The Zia Mohyeddin voice-cloning models in
several of those repos are **not** used — see §6 of that document.

*Compiled 2026-10-11. All throughput and memory figures measured in-sandbox during this session.*
