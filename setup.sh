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

say() { printf '\n\033[1m== %s\033[0m\n' "$*"; }
ok()  { printf '   ok    %s\n' "$*"; }
bad() { printf '   MISS  %s\n' "$*"; }

FAILED=0

CHECK_ONLY=0
[[ "${1:-}" == "--check" ]] && CHECK_ONLY=1

# --check is the session-start command. It verifies the toolchain, the shaping
# library, the fonts and the ornament in a few seconds and exits non-zero if
# anything is missing. It never installs and never touches the network. The full
# run stays available as the repair path.
if [[ $CHECK_ONLY == 1 ]]; then
  rc=0
  for bin in ffmpeg ffprobe; do
    if command -v "$bin" >/dev/null 2>&1; then ok "$bin"; else bad "$bin"; rc=1; fi
  done

  python3 - <<'PYCHK'
import importlib, sys
from PIL import features
bad = 0
for mod, label, required in (("PIL", "pillow", 1), ("numpy", "numpy", 1),
                             ("scipy", "scipy", 1), ("soundfile", "soundfile", 1),
                             ("torch", "torch (Urdu voice)", 0),
                             ("transformers", "transformers (Urdu voice)", 0)):
    try:
        importlib.import_module(mod); print(f"   ok    {label}")
    except Exception:
        print(f"   {'MISS' if required else 'note'}  {label}")
        bad = bad or required
if features.check("raqm"):
    print("   ok    raqm (complex text shaping)")
else:
    print("   MISS  raqm - Urdu will not shape"); bad = 1
sys.exit(bad)
PYCHK
  [[ $? != 0 ]] && rc=1

  if python3 tools/fetch_fonts.py --check >/dev/null 2>&1; then
    ok "fonts verified"
  else
    bad "fonts (run: bash setup.sh)"; rc=1
  fi

  missing=""
  for t in girih arabesque arches; do
    [[ -f "assets/textures/$t.png" ]] || missing="$missing $t"
  done
  if [[ -z "$missing" ]]; then ok "ornament (girih, arabesque, arches)"
  else bad "ornamental assets:$missing"; rc=1; fi

  echo
  if [[ $rc == 0 ]]; then
    echo "ready.  next: python3 -m islamic.produce --ref quran:30:21 --topic marriage"
  else
    echo "not ready - run: bash setup.sh" >&2
  fi
  exit $rc
fi


SUDO=""
if [[ "$(id -u)" != "0" ]] && command -v sudo >/dev/null 2>&1; then SUDO="sudo"; fi


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

# One pip front door, because the two environments disagree:
#   * this sandbox installs into the system interpreter as root;
#   * a GitHub runner's Ubuntu is PEP 668 "externally managed", so the exact same
#     command fails outright unless --break-system-packages is passed.
# Try the plain form first (correct wherever it works), then the flagged form.
pipi() {
  pip install -q --disable-pip-version-check "$@" 2>/dev/null \
    || pip install -q --disable-pip-version-check --break-system-packages "$@" 2>&1 | tail -3
}

if [[ $CHECK_ONLY == 0 ]]; then
  pipi "pillow>=10" numpy scipy soundfile psutil requests
fi

# TTS is only needed for the Urdu narration half of a video. It is a large
# download, so failures here are reported but not fatal for card rendering.
if [[ $CHECK_ONLY == 0 ]]; then
  # --index-url (exclusive), NOT --extra-index-url: with an extra index pip can
  # resolve the PyPI 'torch' wheel, which bundles CUDA and is ~900 MB+. We want
  # the CPU build, and nothing else in this command comes from PyPI.
  pipi "setuptools<81"
  pipi torch --index-url https://download.pytorch.org/whl/cpu
  pipi transformers
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
