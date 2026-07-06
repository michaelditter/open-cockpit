#!/usr/bin/env python3
"""
Open Cockpit — Panel Sounds
===========================
Reads buttons/switches from a WINWING PTO 2 (or any USB HID joystick) on a
Raspberry Pi and plays a sound for each control through the USB speakers.

Modes
-----
  python3 panel_sounds.py              Run the sound daemon (normal use)
  python3 panel_sounds.py --list       List detected input devices
  python3 panel_sounds.py --learn      Live-print every button code you press
  python3 panel_sounds.py --wizard     Interactive: press a button for each sound
  python3 panel_sounds.py --test NAME  Play one sound by name (e.g. gear_up)
  python3 panel_sounds.py --sounds     List available sound names

Config lives in mapping.json next to this file. Sounds live in ../sounds.
Nothing here is WINWING-specific except the default device name match, so it
also works with throttles, button boxes, or any joystick the kernel exposes.
"""

import argparse
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
MAPPING_PATH = os.path.join(HERE, "mapping.json")
SOUNDS_DIR = os.path.normpath(os.path.join(HERE, "..", "sounds"))

# ---------------------------------------------------------------------------
# Audio backend (pygame mixer: low latency, overlapping playback)
# ---------------------------------------------------------------------------
import pygame  # noqa: E402


def init_audio():
    # 44.1kHz matches the sound files; a roomy 2048-sample buffer prevents the
    # underrun crackle/static you get with a tiny buffer on the Pi's USB speakers.
    pygame.mixer.pre_init(frequency=44100, size=-16, channels=2, buffer=2048)
    pygame.mixer.init()
    # Allow many overlapping effects (rapid switch flips).
    pygame.mixer.set_num_channels(24)


def load_sounds():
    """Load every sound file in SOUNDS_DIR keyed by its stem (no extension).
    Prefers .wav (lowest latency) and falls back to .mp3."""
    sounds = {}
    if not os.path.isdir(SOUNDS_DIR):
        print(f"[!] Sounds folder not found: {SOUNDS_DIR}")
        return sounds
    by_stem = {}
    for fn in os.listdir(SOUNDS_DIR):
        stem, ext = os.path.splitext(fn)
        if ext.lower() not in (".wav", ".mp3", ".ogg"):
            continue
        # Prefer wav > ogg > mp3 if duplicates exist.
        rank = {".wav": 0, ".ogg": 1, ".mp3": 2}[ext.lower()]
        if stem not in by_stem or rank < by_stem[stem][0]:
            by_stem[stem] = (rank, os.path.join(SOUNDS_DIR, fn))
    for stem, (_, path) in by_stem.items():
        try:
            sounds[stem] = pygame.mixer.Sound(path)
        except Exception as e:
            print(f"[!] Could not load {path}: {e}")
    return sounds


def play(sounds, name):
    snd = sounds.get(name)
    if snd is None:
        print(f"[!] No sound named '{name}'")
        return
    snd.play()


# ---------------------------------------------------------------------------
# Input backend (evdev)
# ---------------------------------------------------------------------------
from evdev import InputDevice, categorize, ecodes, list_devices  # noqa: E402


def all_devices():
    devs = []
    for path in list_devices():
        try:
            devs.append(InputDevice(path))
        except Exception:
            pass
    return devs


def find_device(match_tokens, explicit_path=None):
    if explicit_path:
        return InputDevice(explicit_path)
    tokens = [t.lower() for t in match_tokens]
    for dev in all_devices():
        name = (dev.name or "").lower()
        if any(tok in name for tok in tokens):
            return dev
    return None


def load_mapping():
    with open(MAPPING_PATH) as f:
        return json.load(f)


def save_mapping(mapping):
    with open(MAPPING_PATH, "w") as f:
        json.dump(mapping, f, indent=2)
    print(f"[+] Saved mapping -> {MAPPING_PATH}")


def code_name(code):
    """Human-readable evdev key name for a code, e.g. 288 -> 'BTN_TRIGGER'."""
    names = ecodes.keys.get(code)
    if isinstance(names, list):
        return names[0]
    return names or str(code)


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------
def cmd_list():
    devs = all_devices()
    if not devs:
        print("No input devices found. Is the panel plugged in? Try sudo.")
        return
    print("Detected input devices:")
    for dev in devs:
        print(f"  {dev.path:18}  {dev.name}")


def cmd_sounds():
    init_audio()
    sounds = load_sounds()
    print(f"Sounds in {SOUNDS_DIR}:")
    for name in sorted(sounds):
        print(f"  {name}")


def cmd_test(name):
    init_audio()
    sounds = load_sounds()
    play(sounds, name)
    time.sleep(3)  # let it finish before exit


def cmd_learn(args):
    cfg = load_mapping()
    dev = find_device(cfg.get("device_match", ["winwing", "pto"]), args.device)
    if not dev:
        print("Could not find the panel. Run --list to see device names,")
        print("then pass --device /dev/input/eventN or edit device_match.")
        return
    abs_threshold = int(cfg.get("abs_threshold", 12000))
    print(f"Listening on: {dev.name}  ({dev.path})")
    print("Flip ONE switch / button at a time. Ctrl-C to stop.\n")
    last_abs = {}
    try:
        for event in dev.read_loop():
            # Only show FRESH presses (value 1) — ignore 'held' and release spam.
            if event.type == ecodes.EV_KEY and event.value == 1:
                print(f"  >>> BUTTON  code={event.code:<5} ({code_name(event.code)})", flush=True)
            elif event.type == ecodes.EV_ABS:
                prev = last_abs.get(event.code, 0)
                if abs(event.value) >= abs_threshold and abs(prev) < abs_threshold:
                    print(f"  >>> AXIS    code={event.code:<5} ({code_name(event.code)})", flush=True)
                last_abs[event.code] = event.value
    except KeyboardInterrupt:
        print("\nDone.")


def cmd_wizard(args):
    """Walk through each sound and record the button the user presses for it."""
    cfg = load_mapping()
    dev = find_device(cfg.get("device_match", ["winwing", "pto"]), args.device)
    if not dev:
        print("Could not find the panel. Run --list first.")
        return
    init_audio()
    sounds = load_sounds()
    sound_names = sorted(sounds)
    print(f"Mapping device: {dev.name}\n")
    print("For each sound, press the button/switch you want to trigger it.")
    print("Press the SAME button twice quickly to SKIP a sound. Ctrl-C to stop early.\n")

    bindings = {}

    def next_press():
        # Block until a fresh PRESS, ignoring releases/holds.
        for event in dev.read_loop():
            if event.type == ecodes.EV_KEY and event.value == 1:
                return ("KEY", event.code)
            if event.type == ecodes.EV_ABS and abs(event.value) > 12000:
                return ("ABS", event.code)

    try:
        for name in sound_names:
            play(sounds, name)
            print(f"  >>> Press the control for: {name!r}")
            kind, code = next_press()
            key = str(code)
            bindings[key] = name
            print(f"      bound {code_name(code)} (code {code}) -> {name}\n")
            time.sleep(0.4)  # debounce
    except KeyboardInterrupt:
        print("\nStopped early; keeping what we have.")

    cfg["bindings"] = bindings
    save_mapping(cfg)
    print("\nAll set. Run the daemon with:  python3 panel_sounds.py")


def cmd_run(args):
    cfg = load_mapping()
    init_audio()
    sounds = load_sounds()
    if not sounds:
        print("No sounds loaded; nothing to play. Exiting.")
        return
    dev = find_device(cfg.get("device_match", ["winwing", "pto"]), args.device)
    if not dev:
        print("Panel not found. Run --list to check the name, then edit")
        print("'device_match' in mapping.json or pass --device /dev/input/eventN.")
        return

    bindings = cfg.get("bindings", {})
    default_sound = cfg.get("default_sound")
    play_on = cfg.get("play_on", "press")  # press | both
    abs_threshold = int(cfg.get("abs_threshold", 12000))
    # loop_codes: {start_code: stop_code}. Pressing start_code loops its sound
    # until stop_code is pressed (e.g. jettison alarm until "silence alarms").
    loop_codes = {str(k): str(v) for k, v in cfg.get("loop_codes", {}).items()}
    stop_codes = set(loop_codes.values())
    active_loops = {}  # start_code -> looping Channel (alarm)
    monophonic = cfg.get("monophonic", True)  # a new press cuts the previous clip
    _state = {"ch": None}  # current one-shot Channel

    def stop_loops_for(stop_code):
        for start, stop in loop_codes.items():
            if stop == stop_code and start in active_loops:
                try:
                    active_loops[start].stop()
                except Exception:
                    pass
                active_loops.pop(start, None)

    def play_oneshot(name):
        snd = sounds.get(name)
        if snd is None:
            return
        if monophonic and _state["ch"] is not None:
            try:
                _state["ch"].stop()
            except Exception:
                pass
        _state["ch"] = snd.play()

    print(f"[+] Open Cockpit panel live on: {dev.name}")
    print(f"[+] {len(bindings)} bindings, {len(sounds)} sounds loaded. Ctrl-C to quit.")

    last_abs = {}
    for event in dev.read_loop():
        sc = None  # the code that fired a fresh press
        if event.type == ecodes.EV_KEY:
            if event.value == 1 or (event.value == 0 and play_on == "both"):
                sc = str(event.code)
        elif event.type == ecodes.EV_ABS:
            prev = last_abs.get(event.code, 0)
            if abs(event.value) >= abs_threshold and abs(prev) < abs_threshold:
                sc = str(event.code)
            last_abs[event.code] = event.value
        if sc is None:
            continue
        name = bindings.get(sc, default_sound)
        if sc in stop_codes:          # this control silences a running loop
            stop_loops_for(sc)
        if sc in loop_codes and name and name in sounds:   # this control starts a loop
            try:
                if sc in active_loops:
                    active_loops[sc].stop()
                active_loops[sc] = sounds[name].play(loops=-1)
            except Exception:
                play_oneshot(name)
        elif name:
            play_oneshot(name)


def main():
    p = argparse.ArgumentParser(description="Open Cockpit panel sounds")
    p.add_argument("--list", action="store_true", help="list input devices")
    p.add_argument("--sounds", action="store_true", help="list available sounds")
    p.add_argument("--learn", action="store_true", help="print button codes live")
    p.add_argument("--wizard", action="store_true", help="interactively build mapping")
    p.add_argument("--test", metavar="NAME", help="play one sound and exit")
    p.add_argument("--device", metavar="PATH", help="force /dev/input/eventN")
    args = p.parse_args()

    if args.list:
        cmd_list()
    elif args.sounds:
        cmd_sounds()
    elif args.test:
        cmd_test(args.test)
    elif args.learn:
        cmd_learn(args)
    elif args.wizard:
        cmd_wizard(args)
    else:
        cmd_run(args)


if __name__ == "__main__":
    main()
