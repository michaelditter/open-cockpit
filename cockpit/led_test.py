#!/usr/bin/env python3
"""
PTO2 LED tester.

  .venv/bin/python led_test.py allon     # light EVERY LED (and backlight)
  .venv/bin/python led_test.py alloff     # all off
  .venv/bin/python led_test.py flash      # flash all 5x
  .venv/bin/python led_test.py sweep       # light each LED one at a time (names printed)
  .venv/bin/python led_test.py led hook 1  # one LED on/off by name
  .venv/bin/python led_test.py id 0x04 1   # one LED on/off by raw id
"""
import sys
import time
from winwing_pto2 import PTO2


def main():
    p = PTO2()
    if not p.path:
        print("PTO2 not found at /dev/hidraw*.")
        print(" - Is the panel plugged into the Pi?  (check: lsusb | grep 4098)")
        sys.exit(1)
    print(f"PTO2 found at {p.path}")
    if not p.open():
        print("Could not OPEN the device for writing — almost always a permissions thing.")
        print("Install the udev rule, then UNPLUG/REPLUG the panel:")
        print("  sudo cp ~/open-cockpit/cockpit/99-winwing.rules /etc/udev/rules.d/")
        print("  sudo udevadm control --reload-rules && sudo udevadm trigger")
        sys.exit(1)

    cmd = sys.argv[1] if len(sys.argv) > 1 else "allon"
    if cmd == "allon":
        p.backlight(255)
        p.all(True)
        print("All LEDs + backlight ON (they stay on after exit).")
    elif cmd == "alloff":
        p.all(False)
        print("All LEDs OFF.")
    elif cmd == "flash":
        for _ in range(5):
            p.all(True); time.sleep(0.3)
            p.all(False); time.sleep(0.3)
        print("Flashed.")
    elif cmd == "sweep":
        print("Lighting each LED for ~1.2s — note which physical light turns on:")
        for name, led in p.LEDS.items():
            p.all(False); p.led(name, True)
            print(f"   -> {name:14s} (id {hex(led)})")
            time.sleep(1.2)
        p.all(False)
        print("Sweep done (all off).")
    elif cmd == "led" and len(sys.argv) == 4:
        p.led(sys.argv[2], sys.argv[3] in ("1", "on", "true"))
        print(f"{sys.argv[2]} -> {sys.argv[3]}")
    elif cmd == "id" and len(sys.argv) == 4:
        p.led_id(int(sys.argv[2], 0), int(sys.argv[3], 0))
        print(f"id {sys.argv[2]} -> {sys.argv[3]}")
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
