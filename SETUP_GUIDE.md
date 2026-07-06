# Open Cockpit — Full Setup Guide (Raspberry Pi)

From blank SD card to a self-booting starship bridge. Budget a relaxed afternoon. No Windows, no SimApp Pro, no cloud dependency after the one-time voice generation.

## How it works (60 seconds)

The Pi reads the WINWING PTO2 (or any USB HID panel) as a standard game controller. Every switch throw arrives as a kernel **evdev** input event; `panel_web.py` maps it to a voice line (pygame → USB speakers), sets the panel's **physical LEDs** (raw HID writes), and pushes the event to the full-screen **bridge UI** (local web page in Chromium kiosk mode).

**One architectural catch:** USB is point-to-point — the panel plugs into the Pi *or* a gaming PC, not both. For a room prop that does everything itself, panel → Pi is the right call.

## Part A — Flash Raspberry Pi OS

On your Mac/PC:

1. Install **Raspberry Pi Imager** from <https://www.raspberrypi.com/software/>.
2. Choose Device: your Pi model → Choose OS: **Raspberry Pi OS (64-bit)** → Choose Storage: the microSD.
3. Click **Next → Edit Settings** and set: hostname (e.g. `cockpit`), a username + password, your Wi-Fi, and **enable SSH** (Services tab). This saves real headaches.
4. Write, wait, eject.

## Part B — First boot

1. SD card in, **speakers into a USB port**, panel into another, HDMI to the TV, power last.
2. Get a terminal: on the desktop, open Terminal — or headless: `ssh <user>@cockpit.local`.
3. Update once: `sudo apt update && sudo apt full-upgrade -y`

## Part C — Point audio at the USB speakers

The Pi defaults to HDMI audio; aim it at the speakers instead.

1. `aplay -l` → find the USB/speaker card number (e.g. `card 1`).
2. Desktop: right-click the volume icon → select the USB device. Headless:
   ```bash
   cat > ~/.asoundrc <<'EOF'
   defaults.pcm.card 1
   defaults.ctl.card 1
   EOF
   ```
   (replace `1` with your card number)
3. `alsamixer` to set volume, then `speaker-test -c2 -twav` — you should hear "front left / front right".

## Part D — Get the project

```bash
git clone https://github.com/michaelditter/open-cockpit.git ~/open-cockpit
cd ~/open-cockpit/cockpit
```

## Part E — Make it YOUR ship

1. **Edit `config.json`** — ship name + your crew (names, callsigns, ages, mottos…). This file drives the bridge header, the montage titles, and the voice pack. *If you use real names, keep your fork private / local.*
2. **Generate the voice pack** (runs anywhere — Pi, Mac, PC):
   ```bash
   export ELEVENLABS_API_KEY=sk_...        # from elevenlabs.io → Profile → API keys
   python3 generate_sounds.py --dry-run    # read the scripts first
   python3 generate_sounds.py              # renders ../sounds/*.mp3 (36 lines)
   ```
   Pick a different voice with `--voice <voice_id>` (browse the ElevenLabs voice library — cinematic trailer voices work brilliantly). No ElevenLabs? Record your own MP3s named `<id>.mp3` into `sounds/`.
3. **Optional media** — drop crew photos in `cockpit/crew/`, screensaver clips in `cockpit/screensaver/`, etc. Each folder's README says exactly what it takes. Everything is optional; the bridge degrades gracefully.

## Part F — Install dependencies

```bash
bash install.sh
```

Installs system packages (python3-venv, ffmpeg, SDL, ALSA tools), creates `.venv`, installs `evdev` + `pygame`, and pre-converts MP3 → WAV for snap-fast playback.

## Part G — LEDs without root (udev rule)

```bash
sudo cp 99-winwing.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules && sudo udevadm trigger
# then UNPLUG and REPLUG the panel
.venv/bin/python led_test.py flash      # all lights flash 5x = success
.venv/bin/python led_test.py sweep      # identify each LED by name
```

## Part H — Map your switches

```bash
.venv/bin/python panel_sounds.py --list     # confirm the panel is detected
.venv/bin/python panel_sounds.py --learn    # (optional) watch raw codes as you flip
.venv/bin/python panel_sounds.py --wizard   # plays each sound; press the control you want for it
```

The repo ships with `mapping.json` pre-filled with **PTO2 codes**, so PTO2 owners can skip the wizard entirely. Any other HID panel: run the wizard once and you're mapped.

## Part I — Fly

```bash
.venv/bin/python panel_web.py
```

Open `http://cockpit.local:8080` (or on the attached TV via kiosk below). Flip switches. Grin.

Quick tests without the panel: `panel_sounds.py --test gear_up`, or open the page and watch the tiles light as you flip.

## Part J — Boot straight into the cockpit

```bash
bash install_kiosk.sh
sudo reboot
```

Sets desktop autologin, disables screen blanking, and autostarts `start_cockpit.sh` (server + full-screen Chromium). From now on: power on → bridge appears.

Headless/sounds-only variant instead (no display): `bash install_service.sh` runs `panel_sounds.py` as a systemd service (`open-cockpit-sounds`).

## Troubleshooting

- **Panel not in `--list`:** try `sudo`, and if that works: `sudo usermod -aG input $USER`, log out/in. Confirm enumeration with `lsusb` (look for `4098:bf05`). Try another cable/port.
- **No sound:** re-check Part C (`aplay -l`, `~/.asoundrc` card number, `alsamixer` unmute with `m`). Direct test: `aplay ~/open-cockpit/sounds/gear_up.wav`.
- **Crackly audio:** the install pre-converts to WAV; if it still crackles, raise `buffer=2048` higher in `panel_sounds.py:init_audio()`.
- **LEDs dead but sounds fine:** the udev rule (Part G) isn't applied or the panel wasn't replugged. `led_test.py` prints exactly what's wrong.
- **A 3-position switch fires on both throws:** expected — map each throw to its own line (that's why gear up/down are separate sounds).
- **Bridge is up but doesn't react:** the browser connects to `/events` (bottom-right shows `● live`). If it shows reconnecting, the Python process died — run it in a terminal and read the traceback.

## Updating

```bash
cd ~/open-cockpit && git pull
sudo reboot   # or restart the kiosk / service
```

Your `config.json`, `mapping.json`, and media folders are yours; review diffs before overwriting them.
