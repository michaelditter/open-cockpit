"""
WINWING PTO2 LED controller (Linux, raw hidraw — no external deps).

Lights the physical indicator LEDs on the PTO2 panel: master caution, jettison,
the five station lights, flaps, the gear lamps (nose/left/right), half/full,
and the hook lamp, plus panel backlight and gear-handle lighting.

Protocol credit: reverse-engineered by the community —
  - DCS-Linux_Winwing-bridge  (github.com/W0lsZcZ4n/DCS-Linux_Winwing-bridge)
  - PTO2-for-BMS by ExoLightFR (github.com/ExoLightFR/PTO2-for-BMS)
VID 0x4098 / PID 0xBF05. HID write: [0x02,0x05,0xBF, 0,0,0x03,0x49, led, value, 0,0,0,0,0]
"""
import glob
import os
import time


class PTO2:
    VENDOR = 0x4098
    PRODUCT = 0xBF05
    PREFIX = [0x02, 0x05, 0xBF]

    # brightness groups (value 0-255)
    BACKLIGHT = 0x00
    GEAR_HANDLE = 0x01
    SL_BRIGHTNESS = 0x02     # station-light group
    FLAG_BRIGHTNESS = 0x03   # warning/flag group
    GROUPS = (BACKLIGHT, GEAR_HANDLE, SL_BRIGHTNESS, FLAG_BRIGHTNESS)

    # individual LEDs (value 0/1) — name -> id
    LEDS = {
        "master_caution": 0x04, "jettison": 0x05,
        "station_ctr": 0x06, "station_li": 0x07, "station_lo": 0x08,
        "station_ro": 0x09, "station_ri": 0x0A,
        "flaps": 0x0B, "nose": 0x0C, "full": 0x0D,
        "right": 0x0E, "left": 0x0F, "half": 0x10, "hook": 0x11,
    }

    def __init__(self):
        self.path = self._find()
        self.h = None

    def _find(self):
        target = f"HID_ID=0003:0000{self.VENDOR:04X}:0000{self.PRODUCT:04X}"
        for hr in glob.glob("/dev/hidraw*"):
            try:
                n = hr.split("hidraw")[1]
                p = f"/sys/class/hidraw/hidraw{n}/device/uevent"
                if os.path.exists(p) and target in open(p).read():
                    return hr
            except Exception:
                continue
        return None

    def open(self):
        if not self.path:
            self.path = self._find()
        if not self.path:
            return False
        try:
            self.h = open(self.path, "wb", buffering=0)
        except Exception as e:
            print(f"[PTO2] open failed ({self.path}): {e}")
            return False
        # turn every brightness group up so individual LEDs are visible
        for g in self.GROUPS:
            self._cmd(g, 255)
        return True

    def _cmd(self, led, value):
        if not self.h:
            return
        cmd = bytes(self.PREFIX + [0x00, 0x00, 0x03, 0x49, led, value & 0xFF, 0, 0, 0, 0, 0])
        try:
            self.h.write(cmd)
            self.h.flush()
        except Exception as e:
            print(f"[PTO2] write failed: {e}")
            self.h = None

    # public API
    def led(self, name, on):
        led = self.LEDS.get(name)
        if led is not None:
            self._cmd(led, 1 if on else 0)

    def led_id(self, led, value):
        self._cmd(led, value)

    def brightness(self, group, value):
        self._cmd(group, max(0, min(255, value)))

    def all(self, on):
        for led in self.LEDS.values():
            self._cmd(led, 1 if on else 0)

    def backlight(self, value=255):
        self._cmd(self.BACKLIGHT, max(0, min(255, value)))
        self._cmd(self.GEAR_HANDLE, max(0, min(255, value)))

    def close(self, leds_off=True):
        if self.h:
            try:
                if leds_off:
                    self.all(False)
                self.h.close()
            except Exception:
                pass
            self.h = None
