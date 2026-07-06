# 🚀 Open Cockpit

**Turn a closet into a starship bridge.** A real flight-sim switch panel + a Raspberry Pi + AI-generated voice lines = a fully alive spaceship cockpit for kids. Every switch they flip talks back in a movie-trailer voice, lights real LEDs, and drives a full starship bridge display — no gaming PC, no internet required after setup, no subscriptions.

Built by a dad for three small astronauts in the closet under the stairs. Open-sourced so your crew can fly too.

> **The 60-second pitch:** a WINWING PTO2 panel (landing gear, flaps, engine switches, a guarded JETTISON button…) plugs into a Raspberry Pi. Python reads every switch as a USB input event, plays a cinematic voice line ("Landing gear, retracting. Hold on tight, crew…"), drives the panel's physical LEDs over reverse-engineered USB HID, and updates a full-screen bridge: animated starfield, telemetry gauges, tactical radar, a 30-object galactic database, energy schematic, camera feeds, red-alert lockdowns, secret mission sequences, and an idle "deep field" screensaver.

## What it does

- **Every control talks.** 36 scripted voice lines rendered with your kids' names and your ship's name via the ElevenLabs API (`generate_sounds.py`). A looping jettison alarm blares until someone flips SILENCE ALARMS.
- **Real lights.** The PTO2's gear lamps, master caution, flap/hook/station LEDs are driven directly over USB HID on Linux — no SimApp Pro, no Windows. Red alerts flash the physical panel.
- **A living bridge display.** Single-file web UI served by the Pi, shown full-screen in kiosk mode: warp-reactive starfield with procedural planets, ship telemetry, navigation map, sweeping radar, galactic database with real astronomy facts, hydrogen/energy schematic, greenhouse & EVA "camera feeds," and crew cards for your astronauts.
- **Secret missions.** Flip the right sequence of controls and a full-screen mission cinematic takes over (launch, black-hole slingshot, asteroid run, escape-pod rescue). Triple-flip any switch for the family-montage easter egg.
- **Kiosk boot.** Power on the Pi and it comes up straight into the cockpit. Idle 75 seconds and it drifts into a 30-scene deep-space screensaver; any switch wakes the bridge.
- **Works offline.** After the one-time voice generation, everything runs locally. Optional imagery enrichments load from Wikimedia when online.

## Hardware (~$300 all-in, much of it optional)

| Part | Role | Approx. |
|---|---|---|
| WINWING PTO2 "Panel of Take Off" | The switches — the heart of the build | ~$100–130 from the [official store](https://winwingsim.com) (third-party listings vary wildly) |
| Raspberry Pi 4 (2GB+) + 32GB microSD | The brain | ~$60–120 (kit) |
| USB speakers (e.g. Creative Pebble V3) | The voice of the ship | ~$40 |
| Any HDMI TV/monitor | The viewscreen | whatever you have |
| Space-themed peel-and-stick wallpaper, foam ducting, a chair | The room | your imagination |

Minimum viable cockpit: panel + Pi + speakers. Full parts list, room-build notes, and alternatives in [HARDWARE.md](HARDWARE.md).

## Quick start

```bash
# On the Pi (Raspberry Pi OS 64-bit):
git clone https://github.com/michaelditter/open-cockpit.git ~/open-cockpit
cd ~/open-cockpit/cockpit

# 1. Make it YOUR ship — names, callsigns, mottos:
nano config.json

# 2. Generate the voice pack with your crew's names (any machine works):
export ELEVENLABS_API_KEY=sk_...
python3 generate_sounds.py --dry-run   # preview the scripts
python3 generate_sounds.py             # render ../sounds/*.mp3

# 3. Install dependencies + convert audio for low latency:
bash install.sh

# 4. Map YOUR panel's switches to sounds (any USB HID panel works):
.venv/bin/python panel_sounds.py --wizard

# 5. Fly:
.venv/bin/python panel_web.py          # bridge at http://<pi>:8080

# 6. Make it permanent — boot straight into the cockpit:
bash install_kiosk.sh && sudo reboot
```

Full walkthrough (flashing the SD card, audio config, udev rules for LEDs, troubleshooting): [SETUP_GUIDE.md](SETUP_GUIDE.md).

## How it works

```
 WINWING PTO2 ──USB──► Raspberry Pi 4
   switches                │
   (evdev input) ──► panel_web.py ──► pygame/ALSA ──► USB speakers
                           │  ▲                        (voice lines)
   LEDs ◄──USB HID─────────┘  │
   (winwing_pto2.py,          │ config.json  (your ship + crew)
    raw hidraw writes)        │ mapping.json (switch → sound)
                              │ voice_lines.json (the scripts)
                              ▼
                    HTTP + Server-Sent Events
                              ▼
                 Chromium kiosk (the bridge UI)
              starfield · telemetry · radar · missions
```

One Python process (`panel_web.py`) does everything: reads the panel, plays sounds, drives LEDs, serves the bridge, and pushes every event to the browser over SSE. `panel_sounds.py` is the headless sounds-only variant plus the CLI tools (`--list`, `--learn`, `--wizard`, `--test`).

## Make it yours

- **`config.json`** — ship name, screensaver title, and your crew (names, ages, callsigns, emoji, roles, schools, home galaxies, mottos). The bridge header, montage, and voice pack all render from this one file.
- **`voice_lines.json`** — all 36 scripts with `{c1}/{c2}/{c3}/{ship}` tokens. Edit any line, re-run `generate_sounds.py --only <id>`.
- **Media folders** — drop your own content into `cockpit/videos`, `stills`, `screensaver`, `montage`, `greenhouse`, `outside`, `missions` (each folder has a README explaining exactly what goes in). We generated ours with AI video tools; the cockpit gracefully falls back to Wikimedia imagery or procedural graphics when folders are empty.
- **Different panel?** Nothing except the LED driver is WINWING-specific. Any USB HID button box / throttle / joystick the Linux kernel exposes works: run `--wizard` to map it. (LED support for other panels = great first PR.)

## Secret combos (don't tell the crew)

| Sequence | Result |
|---|---|
| Same control 3× fast | Family montage + anthem |
| Lights OFF → ON → OFF | Deep-field screensaver |
| Lights OFF → Gear DOWN → Lights OFF | Screen sleep |
| Engines L+R → Master → Launch bar → Full flaps → Gear up → Wings spread | 🚀 LAUNCH cinematic |
| Hook IN → Master engine → Wings fold → Anti-skid → Hook OUT | 🌀 Black-hole slingshot |
| Gear up → Wings fold → Half flaps → Anti-skid → Lights on | ☄️ Asteroid run |
| Jettison alarm → Stores → L fuel → R fuel → Escape pod → Silence | 🛟 Escape-pod rescue |

## Privacy by design

This repo ships with a fictional demo crew ("Alex, Sam & Nova of the ODYSSEY"). Your family's identity lives only in `config.json` + the media folders, and **`.gitignore` excludes all generated audio, photos, and video** — so even if you fork this publicly, your kids' names, faces, and voices stay on your Pi. Keep it that way: review any PR/screenshot for personal content before sharing, and if you photograph your build, check what's on the screen first.

## Roadmap

Voice-interactive ship AI (push-to-talk → Whisper → LLM → ElevenLabs, ship-aware persona), a stateful mission engine with per-kid ranks and weekly AI-generated missions, live ISS/launch data on the bridge, and WLED room-lighting sync. PRs welcome — `good first issue` labels are seeded.

## Credits

- WINWING PTO2 HID LED protocol: reverse-engineered by the community — [DCS-Linux_Winwing-bridge](https://github.com/W0lsZcZ4n/DCS-Linux_Winwing-bridge), [PTO2-for-BMS](https://github.com/ExoLightFR/PTO2-for-BMS), [schenlap/winwing_fcu](https://github.com/schenlap/winwing_fcu), and the mainline Linux `hid-winwing` driver.
- Voice: [ElevenLabs](https://elevenlabs.io). Input: python-evdev. Audio: pygame/SDL. Space imagery fallbacks: Wikimedia Commons.
- Built with Claude as copilot, by a dad who wanted the closet under the stairs to be bigger on the inside.

## License

[MIT](LICENSE). Fly safe. 🖖
