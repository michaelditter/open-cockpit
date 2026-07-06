#!/usr/bin/env bash
# Open Cockpit - one-shot installer for Raspberry Pi OS.
# Run from inside the cockpit folder:  bash install.sh
set -e

echo "==> Installing system packages (sudo may prompt for your password)..."
sudo apt-get update
sudo apt-get install -y python3-venv python3-pip ffmpeg libsdl2-mixer-2.0-0 alsa-utils

echo "==> Creating Python virtual environment (.venv)..."
python3 -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

echo "==> Converting MP3 sounds to WAV for low-latency playback..."
SOUNDS_DIR="$(cd .. && pwd)/sounds"
if [ -d "$SOUNDS_DIR" ]; then
  for mp3 in "$SOUNDS_DIR"/*.mp3; do
    [ -e "$mp3" ] || continue
    wav="${mp3%.mp3}.wav"
    if [ ! -e "$wav" ]; then
      ffmpeg -y -loglevel error -i "$mp3" -ar 44100 -ac 2 "$wav"
      echo "    converted $(basename "$wav")"
    fi
  done
else
  echo "    (no sounds folder found at $SOUNDS_DIR - skipping)"
fi

echo ""
echo "==> Done. Next steps:"
echo "    1) Plug the panel in, then find it:   .venv/bin/python panel_sounds.py --list"
echo "    2) Build your button map:             .venv/bin/python panel_sounds.py --wizard"
echo "    3) Run it:                            .venv/bin/python panel_sounds.py"
echo "    (To start on boot, see install_service.sh)"
