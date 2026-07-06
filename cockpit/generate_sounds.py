#!/usr/bin/env python3
"""
Open Cockpit — voice pack generator (ElevenLabs)
================================================
Renders every line in voice_lines.json with YOUR crew's names (from
config.json) and writes MP3s into ../sounds — the exact filenames the
cockpit plays. Zero dependencies beyond the Python standard library.

Setup
-----
  1. Create an ElevenLabs account and grab an API key (Profile -> API keys).
  2. export ELEVENLABS_API_KEY="sk_..."
  3. Edit config.json (your ship + crew names).

Usage
-----
  python3 generate_sounds.py --dry-run          # print the final scripts, no API calls
  python3 generate_sounds.py                    # render ALL lines -> ../sounds/*.mp3
  python3 generate_sounds.py --only gear_up     # re-render a single line
  python3 generate_sounds.py --voice <voiceId>  # use a different ElevenLabs voice
  python3 generate_sounds.py --bed bed.mp3      # optional: mix a music bed under each line (needs ffmpeg)

Tokens available in voice_lines.json scripts:
  {c1} {c2} {c3}  -> names of the first three crew members in config.json
  {ship}          -> ship_name_spoken (falls back to ship_name)

Run it on any machine (Mac/PC/Pi). Copy or sync the sounds folder to the Pi,
then `bash install.sh` converts MP3 -> WAV for low-latency playback.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(HERE, "config.json")
LINES_PATH = os.path.join(HERE, "voice_lines.json")
DEFAULT_OUT = os.path.normpath(os.path.join(HERE, "..", "sounds"))
API_URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def build_tokens(config):
    crew = config.get("crew", [])
    names = [c.get("name", "crew") for c in crew]
    while len(names) < 3:                      # pad so {c3} never crashes a 1-2 kid crew
        names.append("crew")
    ship = config.get("ship_name_spoken") or config.get("ship_name", "Odyssey")
    return {"c1": names[0], "c2": names[1], "c3": names[2], "ship": ship}


def render_script(template, tokens):
    out = template
    for k, v in tokens.items():
        out = out.replace("{" + k + "}", str(v))
    return out


def tts(text, voice_id, model_id, api_key):
    body = json.dumps({
        "text": text,
        "model_id": model_id,
        "voice_settings": {"stability": 0.45, "similarity_boost": 0.8, "style": 0.35},
    }).encode("utf-8")
    req = urllib.request.Request(
        API_URL.format(voice_id=voice_id),
        data=body,
        headers={"xi-api-key": api_key, "Content-Type": "application/json",
                 "Accept": "audio/mpeg"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        return resp.read()


def mix_bed(voice_mp3, bed_path, out_path):
    """Duck a music bed ~12dB under the voice, pad 0.4s head/tail. Needs ffmpeg."""
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-i", voice_mp3, "-i", bed_path,
        "-filter_complex",
        "[0:a]adelay=400|400,apad=pad_dur=0.4[v];"
        "[1:a]volume=0.25[b];"
        "[b][v]sidechaincompress=threshold=0.06:ratio=8:attack=40:release=400[duck];"
        "[duck][v]amix=inputs=2:duration=shortest:normalize=0",
        "-c:a", "libmp3lame", "-q:a", "3", out_path,
    ]
    subprocess.run(cmd, check=True)


def main():
    p = argparse.ArgumentParser(description="Generate the Open Cockpit voice pack via ElevenLabs")
    p.add_argument("--only", metavar="ID", help="render just one line id (e.g. gear_up)")
    p.add_argument("--voice", metavar="VOICE_ID", help="override the ElevenLabs voice id")
    p.add_argument("--model", metavar="MODEL_ID", help="override the model id")
    p.add_argument("--out", metavar="DIR", default=DEFAULT_OUT, help="output folder (default ../sounds)")
    p.add_argument("--bed", metavar="MP3", help="optional music bed to duck under every line (needs ffmpeg)")
    p.add_argument("--force", action="store_true", help="re-render even if the file already exists")
    p.add_argument("--dry-run", action="store_true", help="print final scripts and exit (no API calls)")
    args = p.parse_args()

    config = load_json(CONFIG_PATH)
    lines = load_json(LINES_PATH)
    tokens = build_tokens(config)
    voice_id = args.voice or lines.get("voice_id")
    model_id = args.model or lines.get("model_id", "eleven_multilingual_v2")
    entries = [e for e in lines["entries"] if not args.only or e["id"] == args.only]
    if not entries:
        sys.exit(f"No line with id {args.only!r}. Valid ids:\n  " +
                 "\n  ".join(e["id"] for e in lines["entries"]))

    print(f"Crew: {tokens['c1']}, {tokens['c2']}, {tokens['c3']}  |  Ship: {tokens['ship']}")
    if args.dry_run:
        for e in entries:
            print(f"\n[{e['id']}] {e['label']}\n  {render_script(e['script'], tokens)}")
        return

    api_key = os.environ.get("ELEVENLABS_API_KEY")
    if not api_key:
        sys.exit("Set ELEVENLABS_API_KEY first:  export ELEVENLABS_API_KEY=sk_...")
    if args.bed and not shutil.which("ffmpeg"):
        sys.exit("--bed needs ffmpeg on your PATH (brew install ffmpeg / apt install ffmpeg)")
    os.makedirs(args.out, exist_ok=True)

    done = skipped = 0
    for e in entries:
        dest = os.path.join(args.out, e["id"] + ".mp3")
        if os.path.exists(dest) and not args.force:
            skipped += 1
            print(f"  = {e['id']} exists (use --force to re-render)")
            continue
        text = render_script(e["script"], tokens)
        print(f"  > {e['id']}: {text[:64]}...")
        try:
            audio = tts(text, voice_id, model_id, api_key)
        except urllib.error.HTTPError as err:
            detail = err.read().decode("utf-8", "replace")[:300]
            sys.exit(f"ElevenLabs API error {err.code} on {e['id']}: {detail}")
        if args.bed:
            tmp = dest + ".voice.mp3"
            with open(tmp, "wb") as f:
                f.write(audio)
            mix_bed(tmp, args.bed, dest)
            os.remove(tmp)
        else:
            with open(dest, "wb") as f:
                f.write(audio)
        done += 1
        time.sleep(0.5)  # be polite to the API

    print(f"\nDone: {done} rendered, {skipped} skipped -> {args.out}")
    print("Next: run `bash install.sh` (on the Pi) to convert MP3 -> WAV for low latency.")


if __name__ == "__main__":
    main()
