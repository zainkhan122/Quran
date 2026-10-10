# Naat Studio

Open-source **Urdu naat** generation that runs on free, CPU-only infrastructure.

Sacred text in → mastered recitation out. No GPU. No paid API. No cloud bill.

```
یا نبی سلام علیک، یا رسول سلام علیک۔   ──►   demo-naat.mp3   (−16.7 LUFS, 44.1 kHz)
```

Read [`BLUEPRINT.md`](BLUEPRINT.md) for the research behind this: what the
`ai-music-generation` and `text-to-music` topic pages actually offer, what fits in 2 GB,
what needs the free 16 GB GitHub Actions runner, and why the pipeline is split the way it is.

## Install

```bash
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install transformers numpy scipy soundfile
sudo apt-get install -y ffmpeg          # for mixing / loudness normalisation
```

## Use

```bash
# 1. write your naat — one breath group per line, ۔ ends a stanza
$EDITOR lyrics/my_naat.txt

# 2. render
python -m naat.pipeline --lyrics lyrics/my_naat.txt --style a-cappella   # adab default
python -m naat.pipeline --lyrics lyrics/my_naat.txt --style daf-drone    # with percussion
python -m naat.pipeline --lyrics lyrics/my_naat.txt --style ney          # ML bed (needs ~4 GB+)
```

Output lands in `output/`: `<stem>.mp3`, `<stem>.wav`, `<stem>.json` (render metrics) and
`output/stems/` (isolated vocal and backing, for remixing).

### Voices

| Engine | Model | Peak RSS | RTF | Notes |
|---|---|---|---|---|
| `mms` *(default)* | `facebook/mms-tts-urd-script_arabic` | 748 MB | 0.61× | offline, CC-BY-NC |
| `mms-ft` | `syedmuhammad/mms-tts-urdu-vits_finetuned` | 838 MB | 0.38× | offline, unhurried delivery — suits recitation |
| `gtts` | Google Translate TTS | 52 MB | 0.06× | **online only**, unofficial endpoint |

```bash
python -m naat.pipeline --lyrics lyrics/my_naat.txt --engine mms-ft
```

Sacred vocabulary is controlled by `lexicon/urdu_overrides.json` — a hand-reviewed
surface-form → spoken-form table applied before synthesis. Edit it when an engine
mispronounces a word; it's the human checkpoint for devotional terms.

### Backing styles

| Style | Engine | Needs | Character |
|---|---|---|---|
| `a-cappella` *(default)* | — | any | vocal only — the traditional and conservative choice |
| `daf` | NumPy | 2 GB | frame-drum percussion only |
| `daf-drone` / `full` | NumPy | 2 GB | percussion + harmonium-style drone |
| `drone` | NumPy | 2 GB | sustained tanpura/harmonium pad |
| `ney`, `ney-daf`, `strings` | MusicGen | **~4 GB+** | ML-scored instrumental bed (use CI or a local GPU box) |

On a low-RAM machine the MusicGen styles **warn and fall back** to the procedural bed rather
than failing — the same command works everywhere.

## Measured performance

Sandbox: 2 vCPU / 2 GB RAM / no GPU.

| | |
|---|---|
| TTS model | `facebook/mms-tts-urd-script_arabic` (VITS, 36.3 M params) |
| Load time | 4.7 s |
| Peak RSS, full pipeline | **722–739 MB** |
| Throughput | **RTF 0.46–0.48×** (~2× faster than realtime) |
| Master | −16.7 LUFS integrated, −1.5 dBTP, 44.1 kHz stereo, 192 kbps MP3 |

Full pipeline on a 4-line naat: **~10 s wall → 17 s of finished audio.**

## Free infrastructure

| Tier | Spec | Cost |
|---|---|---|
| This sandbox | 2 vCPU / 2 GB | free |
| GitHub Actions, **public** repo | **4 vCPU / 16 GB / unlimited minutes** | free |
| GitHub Pages | static hosting + audio | free |
| In-browser MusicGen (q8 ONNX / WASM) | the visitor's own CPU | free |

Push a file to `lyrics/` or run the **Naat Studio - generate** workflow manually; it renders,
uploads an artifact and publishes to Pages. See [`.github/workflows/naat.yml`](.github/workflows/naat.yml).

## Layout

```
naat/tts.py        Urdu normalisation, breath-grouping, pluggable recitation engines
lexicon/           pronunciation overrides for sacred vocabulary
naat/backing.py    NumPy synthesis: ney flute, harmonium drone, daf strokes
naat/musicgen.py   MusicGen bed with crossfaded chunking (16 GB runner)
naat/mix.py        ffmpeg sidechain ducking + EBU R128 master
naat/pipeline.py   CLI orchestrator
tools/             ONNX in-sandbox MusicGen probe, Pages manifest builder
web/index.html     self-contained studio UI (GitHub Pages)
lyrics/            naat texts; authoring comments with # are stripped
```

## Please read before publishing

Machine TTS can mispronounce the diacritics that carry sacred names. **Have a human
recite-check any naat before sharing it.** Default a cappella; never clone a living reciter's
voice without consent; keep lyrics original or traditional and public-domain; label output as
machine-generated.

Licensing: `facebook/mms-tts-*` and MusicGen **weights** are **CC-BY-NC 4.0 — non-commercial
use only**. Personal, mosque, community and educational use is fine; a monetised channel needs
permissively licensed weights. See §9 of the blueprint.
