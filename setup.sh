#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Islamic Video Studio - one-shot environment setup.
#
# Nothing installed by apt or pip survives between sessions in this sandbox:
# only files under /home/user do. So ffmpeg, torch, the fonts and the Python
# wheels all have to be re-asserted at the start of a session. This script is
# idempotent - run it as often as you like, it exits fast when everything is
# already in place.
#
#     bash setup.sh          # install + verify
#     bash setup.sh --check   # verify only, never installs
# ---------------------------------------------------------------------------
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

CHECK_ONLY=0
[[ "${1:-}" == "--check" ]] && CHECK_ONLY=1

SUDO=""
if [[ "$(id -u)" != "0" ]] && command -v sudo >/dev/null 2>&1; then SUDO="sudo"; fi

say() { printf '\n\033[1m== %s\033[0m\n' "$*"; }
ok()  { printf '   ok    %s\n' "$*"; }
bad() { printf '   MISS  %s\n' "$*"; }

FAILED=0

# --- 1. system tools -------------------------------------------------------
say "system tools"
for bin in ffmpeg ffprobe; do
  if command -v "$bin" >/dev/null 2>&1; then
    ok "$bin $(command -v $bin)"
  elif [[ $CHECK_ONLY == 1 ]]; then
    bad "$bin (run setup.sh without --check)"
  else
    echo "   installing ffmpeg ..."
    DEBIAN_FRONTEND=noninteractive $SUDO apt-get install -y -qq ffmpeg >/dev/null 2>&1 \
      || $SUDO apt-get update -qq >/dev/null 2>&1 && \
         DEBIAN_FRONTEND=noninteractive $SUDO apt-get install -y -qq ffmpeg >/dev/null 2>&1
    command -v ffmpeg >/dev/null 2>&1 && ok "ffmpeg installed" || { bad "ffmpeg"; FAILED=1; }
  fi
done

# --- 2. python packages ----------------------------------------------------
say "python packages"
if [[ $CHECK_ONLY == 0 ]]; then
  pip install -q --disable-pip-version-check \
    "pillow>=10" numpy scipy soundfile psutil requests 2>&1 | tail -3
fi

# TTS is only needed for the Urdu narration half of a video. It is a large
# download, so failures here are reported but not fatal for card rendering.
if [[ $CHECK_ONLY == 0 ]]; then
  pip install -q --disable-pip-version-check "setuptools<81" \
    --extra-index-url https://download.pytorch.org/whl/cpu torch 2>&1 | tail -3
  pip install -q --disable-pip-version-check transformers 2>&1 | tail -3
fi

python3 - <<'PY'
import importlib, sys
need = [("PIL","pillow"),("numpy","numpy"),("scipy","scipy"),("soundfile","soundfile")]
optional = [("torch","torch (Urdu narration)"),("transformers","transformers (Urdu narration)")]
bad = 0
for mod, label in need:
    try:
        importlib.import_module(mod); print(f"   ok    {label}")
    except Exception as e:
        print(f"   MISS  {label}: {e}"); bad = 1
for mod, label in optional:
    try:
        importlib.import_module(mod); print(f"   ok    {label}")
    except Exception as e:
        print(f"   note  {label} unavailable -> videos with narration will fail, cards still work")
sys.exit(bad)
PY
[[ $? != 0 ]] && FAILED=1

# libraqm is what lets Pillow shape Nastaliq and Naskh correctly. Without it
# Urdu renders as disconnected letters, so check it explicitly.
python3 - <<'PY'
from PIL import features
print("   ok    raqm (complex text shaping)" if features.check("raqm")
      else "   MISS  raqm -> install libraqm; Urdu will render disconnected")
PY

# --- 3. fonts --------------------------------------------------------------
say "fonts (OFL, verified, repaired if a download was truncated)"
python3 tools/fetch_fonts.py || FAILED=1

# --- 4. textures -----------------------------------------------------------
say "2D ornament"
missing=""
for t in girih arabesque arches; do
  [[ -f "assets/textures/$t.png" ]] || missing="$missing $t"
done
if [[ -z "$missing" ]]; then ok "girih, arabesque, arches present"
else bad "missing textures:$missing  (render with --no-textures to continue)"; fi

# --- 5. summary -----------------------------------------------------------
say "ready"
if [[ $FAILED == 0 ]]; then
  cat <<'EOF'
   Build a video:   python3 -m islamic.produce --ref quran:30:21 --topic marriage
   Preview the web: python3 -m http.server 8000 --bind 0.0.0.0 --directory web
EOF
else
  echo "   Some requirements are missing - see MISS lines above." >&2
fi
exit $FAILED
