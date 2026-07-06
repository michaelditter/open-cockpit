# Hardware & Room Build

Everything here is modular — start with the core electronics and add theatrics as you go. Prices are approximate street prices (mid-2026, USD); check current listings.

## Core electronics (the "it works" tier)

| # | Part | Why | Approx. | Notes |
|---|------|-----|---------|-------|
| 1 | **WINWING PTO2 — Panel of Take Off 2** | Landing gear lever, flaps, hook, launch bar, engine switches, jettison selector, a guarded red JETTISON button, and real indicator LEDs. Kids cannot resist it. | ~$100–130 | Buy from the [official WINWING store](https://winwingsim.com); marketplace listings are frequently marked up 2–3×. |
| 2 | **Raspberry Pi 4** (2GB is plenty) + 32GB microSD + USB-C PSU | Runs everything: input, audio, LEDs, and the bridge display. | ~$60–120 | Kits (CanaKit etc.) include SD, PSU, case, reader. A Pi 5 also works. |
| 3 | **USB-powered speakers** (we used Creative Pebble V3) | The ship's voice. USB audio = one cable for power + sound from the Pi. | ~$40 | Any ALSA-visible USB speaker works. |
| 4 | **HDMI TV or monitor** | The viewscreen (bridge UI in Chromium kiosk). | $0 if you have a spare | Any size; ours is a small TV at kid-eye height. |

**Core total: roughly $200–290.**

## Optional — the theatrics tier

| Part | Why | Approx. |
|------|-----|---------|
| Space wallpaper / murals (peel-and-stick "galaxy" + a printed "space station window" panel) | Instantly transforms the closet walls | $30–80 |
| Flexible aluminum ducting + blue cable clamps | Glorious fake "life-support conduits" across the ceiling | $20–40 |
| Astronaut costume, helmet, boots on wall hooks | Crew locker | $30–60 |
| Kid-size chair / bean bag | Command seat | varies |
| Small shelf across the nook | Instrument console — panel mounts here | scrap wood + foam edge padding |
| A little FM/shortwave radio | "Comms unit" set dressing that actually plays music | $30 |
| Yoke + throttle quadrant + Xbox/PC running a space or flight sim | A second station: the actual *flying* seat. Completely independent of the Pi cockpit | varies |

## Layout that worked for us (closet under the stairs)

- **Panel on the shelf at chest height** for a seated kid, monitor directly behind/below it so voice + screen + LEDs read as one console.
- **Speakers flanking the monitor**, volume set once via `alsamixer`, then physically out of reach.
- **Pi velcroed behind the monitor**; one USB to the panel, one USB to the speakers, HDMI to the screen, power last.
- **Foam padding on every shelf edge** — small heads move fast in red alerts.
- **The sloped ceiling is a feature:** it already feels like a spacecraft hull. Ducting + starfield wallpaper leans into it.

## Wiring / power notes

- The panel is plugged into the **Pi**, not a gaming PC — USB is point-to-point. (Want the panel to also fly a sim on a PC? Run `panel_sounds.py` on that PC instead, or keep sim flying on a separate station.)
- Use the official Pi PSU; under-powered Pis brown out when the speakers peak during red alerts.
- The LED driver writes raw HID to `/dev/hidraw*` — install `99-winwing.rules` (see SETUP_GUIDE) so it works without root.
- Total draw is trivial; everything runs off one wall outlet + a small power strip.

## Substitutions

- **Different switch panel:** any USB HID device the Linux kernel sees works for sounds (`panel_sounds.py --wizard` maps anything). Physical LED control is PTO2-specific today; ports to other panels are welcome PRs.
- **No ElevenLabs:** record your own lines as MP3s named `<id>.mp3` (see `voice_lines.json` for ids) and drop them in `sounds/` — the kids' grandparent doing the voices is a killer feature.
- **No spare TV:** the bridge is just a web page — an old tablet on the shelf pointed at `http://<pi>:8080` works.
