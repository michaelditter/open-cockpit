#!/usr/bin/env python3
"""
OPEN COCKPIT — starship bridge display + sound
==============================================
The ONE program the Pi runs. Reads the WINWING panel, plays the layered David
voice clips, drives the panel LEDs, AND serves a full-screen starship bridge:
  - reactive viewscreen, animated starfield with realistic planets
  - crew roster, ship-status gauges, navigation + star chart
  - sweeping radar, a live galactic database (~30 real objects)
  - a hydrogen/energy schematic, plus greenhouse & external camera "feeds"
  - jettison alarm latches a RED ALERT (screen + LEDs) until silenced

Run:   .venv/bin/python panel_web.py   |   View: http://cockpit.local:8080
Crew photos: drop <crew-id>.jpg (ids from config.json) into a 'crew' folder here.
"""
import json
import os
import threading
import queue
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import panel_sounds as ps
from evdev import ecodes

try:
    from winwing_pto2 import PTO2
except Exception:
    PTO2 = None

HERE = os.path.dirname(os.path.abspath(__file__))
PORT = 8080

# ---------------------------------------------------------------------------
# Identity: ship name + crew live in config.json — edit THAT file, not this one.
# The values below are fallback demo crew used only if config.json is missing.
# ---------------------------------------------------------------------------
CONFIG_PATH = os.path.join(HERE, "config.json")
DEFAULT_CONFIG = {
    "ship_name": "ODYSSEY",
    "saver_title": "DEEP FIELD \u00b7 UNCHARTED SPACE",
    "montage_title": "OUR CREW \u2022 EXPLORERS OF THE STARS",
    "crew": [
        {"id": "captain", "name": "Alex", "age": 9, "callsign": "FALCON", "emoji": "\U0001F985",
         "role": "Mission Commander", "school": "Junior Flight Academy", "galaxy": "Whirlpool Galaxy",
         "specialty": "Black-hole slalom champion", "motto": "To the stars \u2014 send it!"},
        {"id": "engineer", "name": "Sam", "age": 7, "callsign": "WRENCH", "emoji": "\U0001F527",
         "role": "Flight Engineer", "school": "Orbital Engineering School", "galaxy": "Bode\u2019s Galaxy",
         "specialty": "Hydrogen fuel-cell wizard", "motto": "If it breaks, I fix it in zero-g!"},
        {"id": "science", "name": "Nova", "age": 4, "callsign": "STARDUST", "emoji": "\U0001F52D",
         "role": "Science Officer", "school": "Twinkle-Star Academy", "galaxy": "Pinwheel Galaxy",
         "specialty": "Comet cataloguing", "motto": "Twinkle twinkle, found a star!"},
    ],
}
try:
    with open(CONFIG_PATH) as _f:
        _user_cfg = json.load(_f)
except Exception:
    _user_cfg = {}
CONFIG = {**DEFAULT_CONFIG, **_user_cfg}
SHIP_NAME = CONFIG["ship_name"]
CREW = CONFIG["crew"]

LAYOUT = [
    ["LAUNCH & GEAR", [
        ["gear_up", "Gear Up"], ["gear_down", "Gear Down"],
        ["launchbar_extend", "Launch Bar Out"], ["launchbar_retract", "Launch Bar In"],
        ["taxi_lights_on", "Lights On"], ["taxi_lights_off", "Lights Off"],
        ["hook_bypass_carrier", "Hook: Carrier"], ["hook_bypass_field", "Hook: Field"],
    ]],
    ["FUEL & PROBE", [
        ["probe_extend", "Probe Extend"], ["probe_neutral", "Probe Neutral"], ["probe_emergency", "Probe EMERGENCY"],
    ]],
    ["FLIGHT", [
        ["flap_half", "Flaps Half"], ["flap_full", "Flaps Full"], ["flap_auto", "Flaps Auto"],
        ["antiskid_on", "Anti-Skid On"], ["antiskid_off", "Anti-Skid Off"],
    ]],
    ["HYPER DRIVE", [
        ["master_engine", "MASTER ENGINE"], ["left_engine_on", "L Engine On"], ["right_engine_on", "R Engine On"],
        ["left_engine_off", "L Engine Off"], ["right_engine_off", "R Engine Off"], ["emergency_hyperjump_brake", "EMERG BRAKE"],
    ]],
    ["BLACK HOLE", [
        ["hook_in_blackhole", "Hook In"], ["hook_out_blackhole", "Hook Out"], ["hook_neutral", "Hook Neutral"],
    ]],
    ["WINGS", [
        ["wing_spread", "Wings Spread"], ["wing_hold", "Wings Hold"], ["wing_fold", "Wings Fold"],
    ]],
    ["JETTISON", [
        ["jettison", "JETTISON"], ["jettison_alarm", "JETT ALARM"], ["silence_alarms", "Silence Alarms"],
        ["seljett_safe", "Sel: Safe"], ["seljett_left_fuel", "Sel: L Fuel"], ["seljett_right_fuel", "Sel: R Fuel"],
        ["seljett_escape_pod", "Sel: Escape Pod"], ["seljett_stores", "Sel: Stores"],
    ]],
]

LED_MAP = {
    "gear_down": [("nose", 1), ("left", 1), ("right", 1)],
    "gear_up": [("nose", 0), ("left", 0), ("right", 0)],
    "flap_half": [("half", 1), ("full", 0), ("flaps", 1)],
    "flap_full": [("full", 1), ("half", 0), ("flaps", 1)],
    "flap_auto": [("flaps", 1), ("half", 0), ("full", 0)],
    "hook_bypass_carrier": [("hook", 1)], "hook_bypass_field": [("hook", 1)],
    "hook_in_blackhole": [("hook", 1)], "hook_out_blackhole": [("hook", 0)], "hook_neutral": [("hook", 0)],
    "seljett_safe": [("station_ctr", 0), ("station_li", 0), ("station_lo", 0), ("station_ri", 0), ("station_ro", 0)],
    "seljett_left_fuel": [("station_li", 1), ("station_lo", 1)],
    "seljett_right_fuel": [("station_ri", 1), ("station_ro", 1)],
    "seljett_escape_pod": [("station_ctr", 1)],
    "seljett_stores": [("station_ctr", 1), ("station_li", 1), ("station_lo", 1), ("station_ri", 1), ("station_ro", 1)],
    "jettison": [("master_caution", 1), ("jettison", 1)],
    "probe_emergency": [("master_caution", 1)],
    "emergency_hyperjump_brake": [("master_caution", 1)],
    "left_engine_on": [("left", 1)], "left_engine_off": [("left", 0)],
    "right_engine_on": [("right", 1)], "right_engine_off": [("right", 0)],
    "master_engine": [("left", 1), ("right", 1)],
    "silence_alarms": [("master_caution", 0), ("jettison", 0)],
}
LED_BACKLIGHT = {"taxi_lights_on": 255, "taxi_lights_off": 45}
ALARM_LEDS = ["master_caution", "jettison"]
# These LEDs stay lit at all times so the cockpit always looks powered/alive
# (engines left+right, gear lamp, flaps, hook, station lights). A keep-alive
# thread re-asserts them so a button press can never leave them dark.
ALWAYS_ON = ["left", "right", "nose", "flaps", "full", "half", "hook",
             "station_ctr", "station_li", "station_lo", "station_ri", "station_ro"]
_PTO = {"dev": None, "flash": None}
_display = {"on": True}


def display_power(on):
    """Turn the HDMI monitor on/off (real power-save sleep). Best-effort across
    Pi display stacks: vcgencmd (KMS), then wlr-randr for the usual outputs.
    Runs the commands off-thread so the input loop never blocks on wake."""
    if _display["on"] == on:
        return
    _display["on"] = on
    a = "1" if on else "0"
    w = "--on" if on else "--off"

    def _run():
        import subprocess
        for c in (["vcgencmd", "display_power", a],
                  ["wlr-randr", "--output", "HDMI-A-1", w],
                  ["wlr-randr", "--output", "HDMI-1", w]):
            try:
                subprocess.run(c, timeout=4, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception:
                pass
    import threading as _t
    _t.Thread(target=_run, daemon=True).start()

_clients = set()
_clients_lock = threading.Lock()


def broadcast(payload):
    data = json.dumps(payload)
    with _clients_lock:
        dead = []
        for q in _clients:
            try:
                q.put_nowait(data)
            except Exception:
                dead.append(q)
        for q in dead:
            _clients.discard(q)


def input_loop():
    cfg = ps.load_mapping()
    ps.init_audio()
    sounds = ps.load_sounds()
    dev = ps.find_device(cfg.get("device_match", ["winwing", "pto", "orion", "takeoff"]))
    if not dev:
        print("[!] Panel not found — display loads but won't react.")
        return
    bindings = cfg.get("bindings", {})
    default_sound = cfg.get("default_sound")
    abs_threshold = int(cfg.get("abs_threshold", 12000))
    loop_codes = {str(k): str(v) for k, v in cfg.get("loop_codes", {}).items()}
    stop_codes = set(loop_codes.values())
    active_loops = {}
    monophonic = cfg.get("monophonic", True)
    _state = {"ch": None}
    labels = {sid: lbl for _, items in LAYOUT for sid, lbl in items}
    print(f"[+] Cockpit reading panel: {dev.name}")

    pto = None
    if PTO2 is not None:
        try:
            _p = PTO2()
            if _p.open():
                _p.all(False)
                pto = _p
                _PTO["dev"] = _p
                _p.backlight(255)
                for _l in ALWAYS_ON:
                    _p.led(_l, True)
                print(f"[+] PTO2 LEDs live: {_p.path}")
            else:
                print("[!] PTO2 LEDs unavailable (device/permission) — running without lights.")
        except Exception as e:
            print("[!] LED init error:", e)

    import threading as _thr

    def _led_keepalive():
        import time as _t
        while True:
            if pto is not None:
                for l in ALWAYS_ON:
                    try:
                        pto.led(l, True)
                    except Exception:
                        pass
            _t.sleep(2.5)
    if pto is not None:
        _thr.Thread(target=_led_keepalive, daemon=True).start()

    def start_alarm_flash():
        if pto is None or _PTO["flash"]:
            return
        ev = _thr.Event()

        def run():
            s = True
            while not ev.is_set():
                for l in ALARM_LEDS:
                    pto.led(l, s)
                s = not s
                ev.wait(0.4)
            for l in ALARM_LEDS:
                pto.led(l, False)
        _PTO["flash"] = ev
        _thr.Thread(target=run, daemon=True).start()

    def stop_alarm_flash():
        if _PTO["flash"]:
            _PTO["flash"].set()
            _PTO["flash"] = None

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

    last_abs = {}
    for event in dev.read_loop():
        sc = None
        if event.type == ecodes.EV_KEY and event.value == 1:
            sc = str(event.code)
        elif event.type == ecodes.EV_ABS:
            prev = last_abs.get(event.code, 0)
            if abs(event.value) >= abs_threshold and abs(prev) < abs_threshold:
                sc = str(event.code)
            last_abs[event.code] = event.value
        if sc is None:
            continue
        display_power(True)   # any panel press wakes the monitor if it slept
        name = bindings.get(sc, default_sound)
        action = "play"
        if sc in stop_codes:
            stop_loops_for(sc)
            action = "loop_stop"
        if sc in loop_codes and name and name in sounds:
            try:
                if sc in active_loops:
                    active_loops[sc].stop()
                active_loops[sc] = sounds[name].play(loops=-1)
                action = "loop_start"
            except Exception:
                play_oneshot(name)
        elif name:
            play_oneshot(name)
        if pto is not None and name:
            try:
                for led, val in LED_MAP.get(name, ()):
                    pto.led(led, bool(val))
                if name in LED_BACKLIGHT:
                    pto.backlight(LED_BACKLIGHT[name])
            except Exception:
                pass
            if action == "loop_start":
                start_alarm_flash()
            elif action == "loop_stop":
                stop_alarm_flash()
        if name:
            broadcast({"name": name, "label": labels.get(name, name), "action": action, "ts": time.time()})


def render_page():
    """Inject ship/crew identity from config.json into the page template."""
    return (PAGE.replace("{{SHIP_NAME}}", SHIP_NAME)
                .replace("{{SAVER_TITLE}}", CONFIG["saver_title"])
                .replace("{{MONTAGE_TITLE}}", CONFIG["montage_title"]))


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, body, ctype):
        try:
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass   # client (browser) closed the request early — harmless

    def do_GET(self):
        if self.path == "/" or self.path.startswith("/index"):
            self._send(render_page().encode("utf-8"), "text/html; charset=utf-8")
        elif self.path.startswith("/display/"):
            display_power(self.path.rstrip("/").endswith("/on"))
            self._send(b"ok", "text/plain")
        elif self.path == "/config":
            vids = []
            vdir = os.path.join(HERE, "videos")
            if os.path.isdir(vdir):
                vids = [os.path.splitext(f)[0] for f in os.listdir(vdir) if f.lower().endswith(".mp4")]
            def _imgs(folder):
                d = os.path.join(HERE, folder)
                if not os.path.isdir(d):
                    return []
                files = [f for f in os.listdir(d) if f.lower().endswith((".mp4", ".jpg", ".jpeg", ".png"))]
                best = {}  # one entry per stem; prefer .mp4 (moving) over a still
                for f in files:
                    stem = os.path.splitext(f)[0]
                    if stem not in best or f.lower().endswith(".mp4"):
                        best[stem] = f
                return sorted(best.values())
            mdir = os.path.join(HERE, "montage")
            mont = sorted(f for f in os.listdir(mdir) if f.lower().endswith((".mp4", ".jpg", ".jpeg", ".png"))) if os.path.isdir(mdir) else []
            sdir = os.path.join(HERE, "stills")
            stills = [os.path.splitext(f)[0] for f in os.listdir(sdir) if f.lower().endswith((".jpg", ".jpeg", ".png"))] if os.path.isdir(sdir) else []
            ssd = os.path.join(HERE, "screensaver")
            saver = sorted(f for f in os.listdir(ssd) if f.lower().endswith(".mp4")) if os.path.isdir(ssd) else []
            self._send(json.dumps({"layout": LAYOUT, "crew": CREW, "videos": vids, "greenhouse": _imgs("greenhouse"),
                                   "outside": _imgs("outside"), "montage": mont, "stills": stills, "screensaver": saver}).encode("utf-8"), "application/json")
        elif self.path.startswith("/greenhouse/") or self.path.startswith("/outside/") or self.path.startswith("/stills/") or self.path.startswith("/screensaver/") or self.path.startswith("/missions/"):
            folder = self.path.strip("/").split("/", 1)[0]
            fn = os.path.basename(self.path)
            p = os.path.join(HERE, folder, fn)
            if os.path.isfile(p):
                ext = fn.rsplit(".", 1)[-1].lower()
                ctype = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "mp4": "video/mp4", "mp3": "audio/mpeg"}.get(ext, "application/octet-stream")
                with open(p, "rb") as f:
                    self._send(f.read(), ctype)
            else:
                self.send_error(404)
        elif self.path.startswith("/videos/") or self.path.startswith("/montage/"):
            folder = "videos" if self.path.startswith("/videos/") else "montage"
            fn = os.path.basename(self.path)
            p = os.path.join(HERE, folder, fn)
            if os.path.isfile(p):
                ext = fn.rsplit(".", 1)[-1].lower()
                ctype = {"mp4": "video/mp4", "jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png"}.get(ext, "application/octet-stream")
                with open(p, "rb") as f:
                    self._send(f.read(), ctype)
            else:
                self.send_error(404)
        elif self.path == "/montage_anthem.mp3":
            p = os.path.join(HERE, "montage_anthem.mp3")
            if os.path.isfile(p):
                with open(p, "rb") as f:
                    self._send(f.read(), "audio/mpeg")
            else:
                self.send_error(404)
        elif self.path.startswith("/crew/"):
            fn = os.path.basename(self.path)
            p = os.path.join(HERE, "crew", fn)
            if os.path.isfile(p):
                ext = fn.rsplit(".", 1)[-1].lower()
                ctype = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "mp4": "video/mp4", "mp3": "audio/mpeg"}.get(ext, "application/octet-stream")
                with open(p, "rb") as f:
                    self._send(f.read(), ctype)
            else:
                self.send_error(404)
        elif self.path == "/events":
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            q = queue.Queue(maxsize=200)
            with _clients_lock:
                _clients.add(q)
            try:
                self.wfile.write(b": hi\n\n")
                self.wfile.flush()
                while True:
                    try:
                        data = q.get(timeout=15)
                        self.wfile.write(f"data: {data}\n\n".encode("utf-8"))
                    except queue.Empty:
                        self.wfile.write(b": ping\n\n")
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                pass
            finally:
                with _clients_lock:
                    _clients.discard(q)
        else:
            self.send_error(404)


PAGE = r"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{{SHIP_NAME}}</title>
<style>
  :root{ --neon:#43e0ff; --green:#3ad07a; --red:#ff3b3b; --gold:#ffd66b; --edge:#1e3850; --panelbg:rgba(9,18,30,.72); }
  *{ box-sizing:border-box; margin:0; padding:0; }
  html,body{ height:100%; background:#02040a; color:#dff3ff; overflow:hidden;
        font-family:"Segoe UI",Roboto,system-ui,sans-serif; user-select:none; cursor:none; }
  #stars{ position:fixed; inset:0; z-index:0; }
  .vignette{ position:fixed; inset:0; z-index:1; pointer-events:none; box-shadow:inset 0 0 240px 60px rgba(0,0,0,.8); }
  #redalert{ position:fixed; inset:0; z-index:8; pointer-events:none; opacity:0; box-shadow:inset 0 0 300px 100px rgba(255,30,30,.85); transition:opacity .3s; }
  #redalert.on{ animation:redpulse 1s infinite; }
  @keyframes redpulse{ 0%,100%{opacity:.22;} 50%{opacity:.9;} }
  .wrap{ position:relative; z-index:3; height:100%; display:flex; flex-direction:column; padding:12px 16px; gap:10px; }
  header{ display:flex; justify-content:space-between; align-items:center; }
  h1{ font-size:30px; letter-spacing:6px; font-weight:800;
        background:linear-gradient(90deg,#43e0ff,#9b8cff,#ffd66b); -webkit-background-clip:text; background-clip:text; color:transparent;
        text-shadow:0 0 28px rgba(67,224,255,.3); }
  .crew{ display:flex; gap:12px; }
  .cc{ display:flex; gap:9px; align-items:center; background:var(--panelbg); border:1px solid #20415c; border-radius:13px; padding:6px 12px 6px 6px; }
  .cc .pic{ width:52px; height:52px; border-radius:50%; object-fit:cover; border:2px solid var(--gold); background:#0c1a2a;
        display:flex; align-items:center; justify-content:center; font-size:26px; box-shadow:0 0 14px rgba(255,214,107,.4); }
  .cc .info b{ font-size:14px; color:#eafaff; letter-spacing:1px; }
  .cc .info .cs{ color:var(--gold); font-size:10px; letter-spacing:2px; }
  .cc .info .sp{ color:#7fb8da; font-size:10px; }
  /* layout */
  .deck{ flex:1; display:flex; gap:10px; min-height:0; }
  .col{ display:flex; flex-direction:column; gap:10px; min-height:0; }
  .col.left{ width:21%; } .col.right{ width:23%; } .col.center{ flex:1; min-width:0; }
  .panel{ background:var(--panelbg); border:1px solid var(--edge); border-radius:12px; padding:8px 10px; position:relative; backdrop-filter:blur(2px); }
  .panel.grow{ flex:1; min-height:0; display:flex; flex-direction:column; }
  .ph{ font-size:10px; letter-spacing:3px; color:#5fa8d6; margin-bottom:6px; display:flex; justify-content:space-between; }
  .ph .dotlive{ color:var(--red); animation:blink 1s steps(1) infinite; }
  @keyframes blink{ 50%{opacity:.3;} }
  /* viewscreen */
  .screen{ flex:1; display:flex; flex-direction:column; align-items:center; justify-content:center; }
  #ship{ font-size:120px; line-height:1; filter:drop-shadow(0 0 36px rgba(67,224,255,.5)); transition:transform .6s cubic-bezier(.2,.8,.2,1); }
  #callout{ margin-top:12px; font-size:44px; font-weight:800; letter-spacing:2px; text-align:center; color:#eafaff; text-shadow:0 0 24px rgba(67,224,255,.6); min-height:52px; max-width:92%; }
  #sub{ margin-top:4px; font-size:15px; letter-spacing:2px; color:#8fd0ff; opacity:.8; }
  .alertbadge{ position:absolute; top:8px; left:50%; transform:translateX(-50%); font-size:26px; font-weight:900; letter-spacing:6px; color:#fff; background:#c01010; padding:8px 26px; border-radius:8px; display:none; box-shadow:0 0 30px rgba(255,40,40,.8); z-index:4; }
  .alertbadge.on{ display:block; animation:blink2 .6s steps(1) infinite; }
  @keyframes blink2{ 50%{ background:#3a0000; color:#ff8a8a; } }
  /* gauges */
  .gauge{ margin-bottom:7px; } .gl{ display:flex; justify-content:space-between; font-size:11px; color:#bfe2f5; margin-bottom:3px; }
  .gbar{ height:9px; background:#0c1a26; border-radius:5px; overflow:hidden; }
  .gbar i{ display:block; height:100%; width:50%; background:#3ad07a; border-radius:5px; transition:width .85s linear, background .85s; }
  .navrow{ display:flex; justify-content:space-between; align-items:center; font-size:12px; color:#9fd0ee; padding:5px 2px; border-bottom:1px solid rgba(30,56,80,.5); }
  .navrow b{ color:#eafaff; font-size:14px; } .navrow:last-child{ border:0; }
  #map{ width:100%; height:96px; margin-top:4px; }
  /* radar */
  .radar{ position:relative; width:100%; aspect-ratio:1/1; max-height:230px; margin:2px auto; border-radius:50%;
        background:radial-gradient(circle, rgba(20,60,40,.5) 0%, rgba(4,16,10,.8) 70%); border:1px solid #1c5a3a; overflow:hidden; }
  .radar::before, .radar::after{ content:""; position:absolute; border:1px solid rgba(58,208,122,.25); border-radius:50%; }
  .radar::before{ inset:22%; } .radar::after{ inset:42%; }
  .rgrid{ position:absolute; inset:0; } .rgrid:before,.rgrid:after{ content:""; position:absolute; background:rgba(58,208,122,.2); }
  .rgrid:before{ left:50%; top:0; bottom:0; width:1px; } .rgrid:after{ top:50%; left:0; right:0; height:1px; }
  .sweep{ position:absolute; inset:0; border-radius:50%; background:conic-gradient(from 0deg, rgba(58,208,122,.55), rgba(58,208,122,0) 70deg, transparent 100%); animation:spin 3.4s linear infinite; }
  @keyframes spin{ to{ transform:rotate(360deg); } }
  .blip{ position:absolute; width:7px; height:7px; border-radius:50%; background:#5dffa0; box-shadow:0 0 10px #5dffa0; transform:translate(-50%,-50%); transition:opacity 1.2s; }
  /* galactic db */
  .galmedia{ position:relative; width:100%; height:150px; }
  #galcanvas{ position:absolute; inset:0; width:100%; height:100%; }
  #galimg{ position:absolute; inset:0; width:100%; height:100%; object-fit:cover; border-radius:8px; opacity:0; transition:opacity .6s; border:1px solid #1e3850; }
  #galname{ font-size:16px; font-weight:700; color:#eafaff; letter-spacing:1px; }
  #galtype{ font-size:11px; color:var(--gold); letter-spacing:2px; margin-bottom:5px; }
  .galstat{ display:flex; justify-content:space-between; font-size:11px; color:#9fd0ee; padding:2px 0; }
  #galfact{ font-size:11px; color:#7fb8da; margin-top:5px; font-style:italic; line-height:1.35; }
  /* energy schematic */
  #energysvg{ width:100%; flex:1; min-height:130px; }
  .flow{ stroke-dasharray:5 7; animation:flow 1s linear infinite; }
  @keyframes flow{ to{ stroke-dashoffset:-24; } }
  /* feeds */
  .feedrow{ display:flex; gap:10px; height:30%; min-height:150px; }
  .feed{ flex:1; padding:0; overflow:hidden; }
  .feed canvas{ width:100%; height:100%; display:block; }
  .feedlabel{ position:absolute; top:8px; left:10px; font-size:11px; letter-spacing:2px; color:#dff3ff; text-shadow:0 1px 3px #000; z-index:2; }
  .feedlabel .rec{ color:var(--red); animation:blink 1s steps(1) infinite; }
  .feedtime{ position:absolute; bottom:8px; right:10px; font-size:11px; color:#cfe; text-shadow:0 1px 3px #000; z-index:2; font-variant-numeric:tabular-nums; }
  .scan{ position:absolute; inset:0; pointer-events:none; z-index:1; background:repeating-linear-gradient(rgba(0,0,0,0) 0 2px, rgba(0,0,0,.18) 2px 3px); }
  /* control tiles strip */
  .panels{ display:flex; gap:8px; overflow:hidden; }
  .sect{ background:var(--panelbg); border:1px solid var(--edge); border-radius:10px; padding:5px 7px; flex:1; min-width:0; }
  .sect h2{ font-size:8px; letter-spacing:1px; color:#5fa8d6; margin:0 2px 5px; }
  .tiles{ display:flex; flex-wrap:wrap; gap:4px; }
  .tile{ flex:1 1 auto; min-width:46px; text-align:center; font-size:8.5px; padding:4px 3px; border-radius:5px; background:#0e1c2c; border:1px solid #244257; color:#bfe2f5; transition:all .12s, box-shadow .4s; }
  .tile.lit{ background:#0d3322; border-color:var(--green); color:#eafff3; box-shadow:0 0 14px var(--green); }
  .tile.alert.lit{ background:#3a1010; border-color:var(--red); box-shadow:0 0 16px var(--red); }
  .ticker{ height:18px; overflow:hidden; font-size:12px; letter-spacing:1px; color:#6fb8e0; }
  .conn{ position:fixed; right:10px; bottom:6px; z-index:9; font-size:10px; color:#3a6a86; }
  .cc{ align-items:flex-start; }
  .cc .info .sp{ font-size:9.5px; line-height:1.45; color:#7fb8da; }
  .cc .mt{ font-size:9.5px; color:var(--gold); font-style:italic; margin-top:2px; }
  .feed img{ width:100%; height:100%; object-fit:cover; display:block; }
  #ghimg{ opacity:0; transition:opacity .8s; }
  #eximg{ position:absolute; inset:0; opacity:0; transition:opacity .8s; z-index:1; }
  #montage{ position:fixed; inset:0; z-index:50; background:#000; display:none; align-items:center; justify-content:center; }
  #montage.on{ display:flex; }
  #montvid,#montimg{ width:100%; height:100%; object-fit:cover; }
  #montimg{ display:none; animation:kenburns 5s ease-in-out infinite alternate; }
  #monthud{ position:absolute; top:6%; left:0; right:0; text-align:center; font-size:17px; letter-spacing:6px; color:#fff; opacity:.85; }
  #monttitle{ position:absolute; bottom:7%; left:0; right:0; text-align:center; font-size:44px; font-weight:900; letter-spacing:7px;
    background:linear-gradient(90deg,#ff4d4d 20%,#ffffff 50%,#5aa0ff 80%); -webkit-background-clip:text; background-clip:text; color:transparent; text-shadow:0 0 30px rgba(255,255,255,.25); }
  .kb{ animation:kenburns 22s ease-in-out infinite alternate; }
  @keyframes kenburns{ from{transform:scale(1.06);} to{transform:scale(1.26) translate(-3%,-2%);} }
  #ghvid,#exvid{ animation:none !important; transform:none !important; }
  #saver{ position:fixed; inset:0; z-index:48; background:#000; display:none; }
  #saver.on{ display:block; }
  #savervid,#savervid2,#saverimg{ position:absolute; inset:0; width:100%; height:100%; object-fit:cover; opacity:0; transition:opacity 1.4s ease; }
  #saverimg{ animation:kenburns 20s ease-in-out infinite alternate; }
  #saver::after{ content:''; position:absolute; inset:0; box-shadow:inset 0 0 240px rgba(0,0,0,.85); pointer-events:none; }
  #saver .svgrain{ position:absolute; inset:0; opacity:.05; pointer-events:none; background-image:repeating-linear-gradient(0deg,rgba(255,255,255,.5) 0,rgba(255,255,255,.5) 1px,transparent 1px,transparent 3px); }
  #saverttl{ position:absolute; top:7%; left:0; right:0; text-align:center; font-size:15px; letter-spacing:9px; color:#8fd0ff; opacity:.85; }
  #savercap{ position:absolute; bottom:12%; left:0; right:0; text-align:center; font-size:42px; font-weight:900; letter-spacing:5px; color:#fff; text-shadow:0 0 28px rgba(120,180,255,.55); transition:opacity .6s ease; }
  #saverhint{ position:absolute; bottom:6.5%; left:0; right:0; text-align:center; font-size:12px; letter-spacing:4px; color:#6a90b0; opacity:.7; }
  #sleep{ position:fixed; inset:0; z-index:60; background:#000; display:none; }
  #sleep.on{ display:block; }
  #mission{ position:fixed; inset:0; z-index:52; background:#000; display:none; }
  #mission.on{ display:block; }
  #mfilm,#mimg{ position:absolute; inset:0; width:100%; height:100%; object-fit:cover; }
  #mimg{ display:none; }
  #mission::after{ content:''; position:absolute; inset:0; box-shadow:inset 0 0 200px rgba(0,0,0,.7); pointer-events:none; }
  #mtitle{ position:absolute; bottom:8%; left:0; right:0; text-align:center; font-size:40px; font-weight:900; letter-spacing:5px;
    background:linear-gradient(90deg,#ff4d4d 18%,#ffffff 50%,#5aa0ff 82%); -webkit-background-clip:text; background-clip:text; color:transparent; text-shadow:0 0 30px rgba(255,255,255,.25); }
  #mtag{ position:absolute; top:7%; left:0; right:0; text-align:center; font-size:14px; letter-spacing:8px; color:#ffd479; opacity:.9; }
  .nac .nacwrap{ display:flex; gap:6px; height:100%; padding:24px 6px 6px; }
  .nacelle{ flex:1; position:relative; border-radius:8px; overflow:hidden; border:1px solid #233a4a; background:#06121a; }
  .nacelle img{ width:100%; height:100%; object-fit:cover; filter:grayscale(.6) brightness(.45); transition:filter .4s; }
  .nacelle.on img{ animation:flick .14s steps(2) infinite; }
  @keyframes flick{ 0%{filter:brightness(1.15) saturate(1.3);} 50%{filter:brightness(1.5) saturate(1.6);} }
  .nacelle.on{ border-color:#ff8a2a; box-shadow:inset 0 0 20px rgba(255,140,40,.6), 0 0 14px rgba(255,140,40,.45); }
  .nstat{ position:absolute; bottom:4px; left:5px; font-size:9px; letter-spacing:1px; color:#9fd0ee; text-shadow:0 1px 2px #000; }
  .nacelle.on .nstat{ color:#ffb86a; }
  .contact{ position:absolute; transform:translate(-50%,-50%); opacity:0; transition:opacity .5s; display:flex; align-items:center; gap:3px; pointer-events:none; }
  .contact i{ width:7px; height:7px; border-radius:50%; display:block; }
  .contact span{ font-size:7px; letter-spacing:.5px; white-space:nowrap; text-shadow:0 1px 2px #000; }
  #viewimg{ position:absolute; inset:0; width:100%; height:100%; object-fit:cover; opacity:0; transition:opacity .6s; z-index:0; border-radius:12px; }
  #viewvid{ position:absolute; inset:0; width:100%; height:100%; object-fit:cover; z-index:0; border-radius:12px; display:none; }
  .screen.hasimg::after{ content:""; position:absolute; inset:0; border-radius:12px; background:linear-gradient(to bottom, rgba(2,4,10,.25), rgba(2,4,10,.8)); z-index:1; }
  .camlabel{ position:absolute; top:10px; left:14px; z-index:3; font-size:13px; letter-spacing:3px; color:#dff3ff; text-shadow:0 1px 4px #000; display:none; }
  .camlabel .rec{ color:var(--red); animation:blink 1s steps(1) infinite; }
  .screen.hasimg .camlabel{ display:block; }
  #ship,#callout,#sub,.alertbadge{ position:relative; z-index:3; }
</style></head>
<body>
  <canvas id="stars"></canvas>
  <div class="vignette"></div>
  <div id="redalert"></div>
  <div class="wrap">
    <header>
      <h1>&#128640; {{SHIP_NAME}}</h1>
      <div class="crew" id="crew"></div>
    </header>
    <div class="deck">
      <div class="col left">
        <div class="panel"><div class="ph"><span>SHIP STATUS</span></div><div id="telemetry"></div></div>
        <div class="panel grow"><div class="ph"><span>GALACTIC DATABASE</span><span id="galidx"></span></div>
          <div class="galmedia"><canvas id="galcanvas"></canvas><img id="galimg" alt=""></div>
          <div id="galname">&mdash;</div><div id="galtype"></div>
          <div id="galstats"></div><div id="galfact"></div></div>
      </div>
      <div class="col center">
        <div class="panel screen" id="screen">
          <img id="viewimg" alt="">
          <video id="viewvid" muted loop playsinline></video>
          <div class="camlabel"><span class="rec">&#9679;</span> <span id="camname">CAM</span></div>
          <div class="alertbadge" id="alertbadge">&#9888; RED ALERT</div>
          <div id="ship">&#128640;</div><div id="callout">ALL SYSTEMS GO</div>
          <div id="sub">flip a switch, crew &mdash; the galaxy awaits</div>
        </div>
        <div class="feedrow">
          <div class="panel feed"><div class="feedlabel"><span class="rec">&#9679;</span> LIVE &middot; GREENHOUSE BAY 3</div><img id="ghimg" class="kb" alt=""><video id="ghvid" class="kb" muted loop playsinline style="opacity:0"></video><div class="scan"></div><div class="feedtime" id="ghtime"></div></div>
          <div class="panel feed"><div class="feedlabel"><span class="rec">&#9679;</span> LIVE &middot; EXT-CAM 04 / EVA</div><img id="eximg" class="kb" alt=""><video id="exvid" class="kb" muted loop playsinline style="opacity:0"></video><canvas id="extcam"></canvas><div class="scan"></div><div class="feedtime" id="extime"></div></div>
          <div class="panel feed nac"><div class="feedlabel">HYPER-DRIVE NACELLES</div><div class="nacwrap">
            <div class="nacelle off" id="nacL"><img alt=""><div class="nstat">L &middot; STANDBY</div></div>
            <div class="nacelle off" id="nacR"><img alt=""><div class="nstat">R &middot; STANDBY</div></div>
          </div></div>
        </div>
      </div>
      <div class="col right">
        <div class="panel"><div class="ph"><span>TACTICAL RADAR</span><span class="dotlive">&#9679; SCAN</span></div>
          <div class="radar"><div class="rgrid"></div><div class="sweep"></div><div id="blips"></div></div></div>
        <div class="panel"><div class="ph"><span>NAVIGATION</span></div><div id="nav"></div><svg id="map" viewBox="0 0 240 100" preserveAspectRatio="xMidYMid meet"></svg></div>
        <div class="panel grow"><div class="ph"><span>HYDROGEN / ENERGY</span></div><svg id="energysvg" viewBox="0 0 240 150" preserveAspectRatio="xMidYMid meet"></svg></div>
      </div>
    </div>
    <div class="panels" id="panels"></div>
    <div class="ticker" id="ticker">&#128225; Mission log standing by&hellip;</div>
  </div>
  <div id="montage"><div id="monthud">&#11088; {{SHIP_NAME}} &#11088;</div><img id="montimg" alt=""><video id="montvid" muted playsinline></video><div id="monttitle">{{MONTAGE_TITLE}}</div></div>
  <audio id="anthem" src="/montage_anthem.mp3" preload="auto"></audio>
  <div id="saver"><video id="savervid" muted loop playsinline></video><video id="savervid2" muted loop playsinline></video><img id="saverimg" alt=""><div class="svgrain"></div><div id="saverttl">&#9670; {{SAVER_TITLE}} &#9670;</div><div id="savercap"></div><div id="saverhint">PRESS ANY CONTROL TO RETURN TO THE BRIDGE</div></div>
  <div id="sleep"></div>
  <div id="mission"><video id="mfilm" muted playsinline></video><img id="mimg" alt=""><div id="mtag">&#9733; MISSION SEQUENCE ENGAGED &#9733;</div><div id="mtitle"></div><audio id="mtrack" preload="auto"></audio></div>
  <div class="conn" id="conn">connecting&hellip;</div>
<script>
const FX={ gear_up:'ascend',launchbar_extend:'ascend',taxi_lights_on:'flash',
  gear_down:'descend',launchbar_retract:'descend',wing_fold:'descend',hook_bypass_carrier:'descend',hook_bypass_field:'descend',
  master_engine:'warp',left_engine_on:'warp',right_engine_on:'warp',wing_spread:'warp',wing_hold:'warp',antiskid_on:'warp',antiskid_off:'warp',
  left_engine_off:'calm',right_engine_off:'calm',flap_auto:'calm',probe_neutral:'calm',hook_neutral:'calm',seljett_safe:'calm',silence_alarms:'calm',taxi_lights_off:'calm',
  emergency_hyperjump_brake:'shake',flap_full:'shake',flap_half:'shake',
  hook_in_blackhole:'swirl',hook_out_blackhole:'swirl',probe_extend:'dock',
  jettison:'alert',probe_emergency:'alert',seljett_escape_pod:'alert',seljett_left_fuel:'alert',seljett_right_fuel:'alert',seljett_stores:'alert',jettison_alarm:'alert' };
const SHIP={ascend:'\u{1F680}',descend:'\u{1F6F0}\u{FE0F}',warp:'\u{1F680}',calm:'\u{1FA90}',shake:'☄\u{FE0F}',swirl:'\u{1F300}',dock:'⛽',flash:'\u{1F4A1}',alert:'\u{1F4A5}'};
const ALERT_IDS=new Set(Object.keys(FX).filter(k=>FX[k]==='alert'));
const tiles={};
let VIDEOS=new Set();
let STILLS=new Set();
let GHLOCAL=[];
let OUTSIDE=[];
let MONTAGE=[];
const $=id=>document.getElementById(id);

// ===== starfield + realistic planets =====
const cv=$('stars'), cx=cv.getContext('2d');
let W,H,stars=[],bodies=[],warp=0;
function resize(){ W=cv.width=innerWidth; H=cv.height=innerHeight; }
addEventListener('resize',resize); resize();
for(let i=0;i<240;i++) stars.push({x:(Math.random()-.5)*W,y:(Math.random()-.5)*H,z:Math.random()*W});
const BT=['planet','planet','planet','ringed','gas','sun','blackhole','asteroids'];
function spawnBody(init){ const type=BT[Math.floor(Math.random()*BT.length)];
  const r=type==='sun'?72:type==='blackhole'?54:type==='asteroids'?0:30+Math.random()*52;
  return {type,x:init?Math.random()*W:W+170,y:80+Math.random()*(H-320),r,hue:Math.floor(Math.random()*360),
    vx:-(0.10+Math.random()*0.26),ring:Math.random()<0.5,phase:Math.random()*6,
    rocks:type==='asteroids'?Array.from({length:18},()=>({dx:(Math.random()-.5)*210,dy:(Math.random()-.5)*140,s:2+Math.random()*4})):null}; }
for(let i=0;i<6;i++) bodies.push(spawnBody(true));
function planet(b,gas){ const g=cx, x=b.x, y=b.y, r=b.r;
  // base sphere
  const rg=g.createRadialGradient(x-r*.35,y-r*.35,r*.1,x,y,r);
  rg.addColorStop(0,'hsl('+b.hue+',65%,72%)'); rg.addColorStop(.7,'hsl('+b.hue+',60%,42%)'); rg.addColorStop(1,'hsl('+b.hue+',55%,20%)');
  g.fillStyle=rg; g.beginPath(); g.arc(x,y,r,0,7); g.fill();
  // banding for gas giants
  if(gas){ g.save(); g.beginPath(); g.arc(x,y,r,0,7); g.clip();
    for(let i=-3;i<=3;i++){ g.globalAlpha=.18; g.strokeStyle='hsl('+((b.hue+18)%360)+',60%,'+(50+i*4)+'%)'; g.lineWidth=r*0.18;
      g.beginPath(); g.ellipse(x,y+i*r*0.28,r*1.1,r*0.16,0,0,7); g.stroke(); } g.restore(); g.globalAlpha=1; }
  // terminator shadow
  const sh=g.createRadialGradient(x+r*.55,y+r*.5,r*.2,x,y,r*1.05);
  sh.addColorStop(0,'rgba(0,0,0,0)'); sh.addColorStop(1,'rgba(0,0,8,.7)');
  g.fillStyle=sh; g.beginPath(); g.arc(x,y,r,0,7); g.fill();
  // atmosphere limb
  g.strokeStyle='hsla('+b.hue+',80%,80%,.35)'; g.lineWidth=2; g.beginPath(); g.arc(x,y,r+1.5,0,7); g.stroke();
  if(b.type==='ringed'||(b.ring&&gas)){ g.strokeStyle='hsla('+b.hue+',55%,80%,.6)'; g.lineWidth=4;
    g.beginPath(); g.ellipse(x,y,r*1.8,r*.55,-0.5,0,7); g.stroke(); }
}
function drawBody(b){ const g=cx;
  if(b.type==='sun'){ const rg=g.createRadialGradient(b.x,b.y,0,b.x,b.y,b.r*2.3);
    rg.addColorStop(0,'#fff6cf');rg.addColorStop(.28,'#ffd25a');rg.addColorStop(.7,'rgba(255,140,30,.4)');rg.addColorStop(1,'rgba(255,120,0,0)');
    g.fillStyle=rg; g.beginPath(); g.arc(b.x,b.y,b.r*2.3,0,7); g.fill(); }
  else if(b.type==='blackhole'){ const rg=g.createRadialGradient(b.x,b.y,b.r*.3,b.x,b.y,b.r*1.9);
    rg.addColorStop(0,'#000');rg.addColorStop(.55,'#000');rg.addColorStop(.68,'rgba(150,90,255,.85)');rg.addColorStop(.82,'rgba(90,160,255,.45)');rg.addColorStop(1,'rgba(0,0,0,0)');
    g.fillStyle=rg; g.beginPath(); g.arc(b.x,b.y,b.r*1.9,0,7); g.fill();
    g.strokeStyle='rgba(190,150,255,.55)'; g.lineWidth=2.5; g.beginPath(); g.ellipse(b.x,b.y,b.r*1.6,b.r*.5,0.5,0,7); g.stroke(); }
  else if(b.type==='asteroids'){ g.fillStyle='#6b6b78'; for(const r of b.rocks){ g.beginPath(); g.arc(b.x+r.dx,b.y+r.dy,r.s,0,7); g.fill(); } }
  else planet(b, b.type==='gas');
}
function draw(){
  // free the GPU for video while a full-screen overlay covers the bridge
  // (check the DOM, NOT the state vars — they're declared later and would throw here)
  if(document.querySelector('#saver.on,#mission.on,#montage.on,#sleep.on')){ requestAnimationFrame(draw); return; }
  cx.fillStyle='#02040a'; cx.fillRect(0,0,W,H);
  const sp=1+warp*30;
  for(const b of bodies){ b.x+=b.vx*sp; if(b.x<-190) Object.assign(b,spawnBody(false)); drawBody(b); }
  cx.save(); cx.translate(W/2,H/2); const speed=2+warp*40;
  for(const s of stars){ s.z-=speed; if(s.z<1){s.z=W;s.x=(Math.random()-.5)*W;s.y=(Math.random()-.5)*H;}
    const k=128/s.z,x=s.x*k,y=s.y*k,k2=128/(s.z+speed),px=s.x*k2,py=s.y*k2;
    cx.strokeStyle='rgba(150,225,255,'+(1-s.z/W)+')'; cx.lineWidth=(1-s.z/W)*2.1;
    cx.beginPath(); cx.moveTo(px,py); cx.lineTo(x,y); cx.stroke(); }
  cx.restore();
  if(warp>0) warp*=0.95; if(warp<0.01) warp=0;
  requestAnimationFrame(draw);
}
draw();

// ===== crew + control tiles =====
fetch('/config').then(r=>r.json()).then(cfg=>{
  VIDEOS=new Set(cfg.videos||[]);
  STILLS=new Set(cfg.stills||[]);
  SAVER=cfg.screensaver||[];
  GHLOCAL=cfg.greenhouse||[];
  OUTSIDE=cfg.outside||[];
  MONTAGE=cfg.montage||[];
  const cr=$('crew');
  cfg.crew.forEach(c=>{ const d=document.createElement('div'); d.className='cc';
    d.innerHTML='<img class="pic" src="/crew/'+c.id+'.jpg" alt="" onerror="this.outerHTML=\'<div class=&quot;pic&quot;>'+c.emoji+'</div>\'">'+
      '<div class="info"><b>'+c.name+', '+c.age+'</b><div class="cs">'+c.callsign+'</div>'+
      '<div class="sp">'+c.role+'</div>'+
      '<div class="sp">\u{1F393} '+c.school+'</div>'+
      '<div class="sp">\u{1F30C} '+c.galaxy+'</div>'+
      '<div class="sp">⭐ '+c.specialty+'</div>'+
      '<div class="mt">"'+c.motto+'"</div></div>';
    cr.appendChild(d); });
  const p=$('panels');
  cfg.layout.forEach(([title,items])=>{ const s=document.createElement('div'); s.className='sect'; s.innerHTML='<h2>'+title+'</h2>';
    const t=document.createElement('div'); t.className='tiles';
    items.forEach(([id,label])=>{ const d=document.createElement('div'); d.className='tile'+(ALERT_IDS.has(id)?' alert':''); d.textContent=label; t.appendChild(d); tiles[id]=d; });
    s.appendChild(t); p.appendChild(s); });
  start();
});

const ship=$('ship'),callout=$('callout'),ticker=$('ticker'),redalert=$('redalert'),badge=$('alertbadge');
let shakeT=0;
function react(name,label,action){
  noteActivity();
  if(typeof missionOn!=='undefined' && missionOn){ return; }
  const fx=FX[name]||'calm', el=tiles[name];
  if(el){ el.classList.add('lit'); setTimeout(()=>el.classList.remove('lit'),1400); }
  callout.textContent=(label||name).toUpperCase(); ship.textContent=SHIP[fx]||'\u{1F680}';
  let tf='none';
  if(fx==='ascend') tf='translateY(-80px) rotate(-12deg) scale(1.1)';
  else if(fx==='descend') tf='translateY(64px) rotate(8deg) scale(.95)';
  else if(fx==='warp'){ warp=1; tf='scale(1.3)'; }
  else if(fx==='swirl'){ warp=.6; tf='rotate(360deg) scale(1.1)'; }
  else if(fx==='dock') tf='scale(1.1)'; else if(fx==='flash') tf='scale(1.18)';
  else if(fx==='alert'){ tf='scale(1.3)'; flashRed(); }
  ship.style.transform=tf; setTimeout(()=>{ship.style.transform='none';},1400);
  if(fx==='shake'||fx==='alert') doShake();
  if(action==='loop_start'){ redalert.classList.add('on'); badge.classList.add('on'); }
  if(action==='loop_stop'){ redalert.classList.remove('on'); badge.classList.remove('on'); }
  ticker.textContent='\u{1F4E1} '+new Date().toLocaleTimeString()+'   —   '+(label||name);
  telemetryReact(name); radarPing();
  if(name==='left_engine_on') setEngine('L',true); else if(name==='left_engine_off') setEngine('L',false);
  if(name==='right_engine_on') setEngine('R',true); else if(name==='right_engine_off') setEngine('R',false);
  if(name==='master_engine'){ setEngine('L',true); setEngine('R',true); }
  showView(name); checkTriple(name); comboPush(name);
}
function flashRed(){ redalert.style.opacity=.9; if(!redalert.classList.contains('on')) setTimeout(()=>{redalert.style.opacity=0;},350); }
function doShake(){ const w=document.querySelector('.deck'); let n=0; clearInterval(shakeT);
  shakeT=setInterval(()=>{ n++; w.style.transform='translate('+(Math.random()*12-6)+'px,'+(Math.random()*12-6)+'px)'; if(n>10){ clearInterval(shakeT); w.style.transform='none'; } },50); }
function start(){ const es=new EventSource('/events'),c=$('conn');
  es.onopen=()=>{c.textContent='● live';c.style.color='#3ad07a';};
  es.onerror=()=>{c.textContent='○ reconnecting';c.style.color='#3a6a86';};
  es.onmessage=e=>{ try{const d=JSON.parse(e.data);react(d.name,d.label,d.action);}catch(_){} }; }

// ===== telemetry HUD =====
const tel={fuel:86,o2:97,co2:0.4,pressure:101.3,heat:42,greenhouse:91,heading:47,distance:384400,speed:160,destIdx:0,eta:300,boost:0};
const DESTS=['LUNA BASE ALPHA','MARS COLONY','ASTEROID BELT','EUROPA STATION','TITAN OUTPOST','PROXIMA B'];
const GA=[{k:'fuel',label:'FUEL',unit:'%',max:100,good:'hi'},{k:'o2',label:'OXYGEN',unit:'%',max:100,good:'hi'},
  {k:'greenhouse',label:'GREENHOUSE',unit:'%',max:100,good:'hi'},{k:'co2',label:'CO₂',unit:'%',max:5,good:'lo'},
  {k:'heat',label:'HULL TEMP',unit:'%',max:100,good:'lo'},{k:'pressure',label:'CABIN PRESS',unit:'kPa',max:140,good:'mid'}];
const clamp=(v,a,b)=>Math.max(a,Math.min(b,v));
function gcolor(g,v){ const p=v/g.max*100; if(g.good==='hi') return p>50?'#3ad07a':p>25?'#ffb028':'#ff3b3b';
  if(g.good==='lo') return p<35?'#3ad07a':p<65?'#ffb028':'#ff3b3b'; return '#43e0ff'; }
$('telemetry').innerHTML=GA.map(g=>'<div class="gauge"><div class="gl"><span>'+g.label+'</span><span id="gv_'+g.k+'">--</span></div><div class="gbar"><i id="gb_'+g.k+'"></i></div></div>').join('');
$('nav').innerHTML='<div class="navrow"><span>HEADING</span><b id="t_head">047&deg;</b></div>'+
  '<div class="navrow"><span>DESTINATION</span><b id="t_dest">--</b></div>'+
  '<div class="navrow"><span>ETA</span><b id="t_eta">--</b></div>'+
  '<div class="navrow"><span>DIST &middot; EARTH</span><b id="t_dist">--</b></div>';
function drawMap(){ const m=$('map'); const n=DESTS.length,w=212,x0=14; let dots='';
  for(let i=0;i<n;i++){ const x=x0+i*(w/(n-1)); dots+='<circle cx="'+x+'" cy="58" r="3" fill="'+(i<=tel.destIdx?'#43e0ff':'#27465c')+'"/>'; }
  const prog=tel.destIdx+(1-tel.eta/300), px=clamp(x0+prog*(w/(n-1)),x0,x0+w);
  m.innerHTML='<line x1="14" y1="58" x2="226" y2="58" stroke="#1e3850" stroke-width="2" stroke-dasharray="3 4"/>'+dots+
    '<circle cx="14" cy="58" r="7" fill="#3a7bd5"/><text x="14" y="78" fill="#6fb8e0" font-size="8" text-anchor="middle">EARTH</text>'+
    '<text x="'+px+'" y="46" font-size="13" text-anchor="middle">\u{1F680}</text>'; }
function hudTick(){
  tel.fuel=clamp(tel.fuel-0.05+(Math.random()-.5)*0.1,0,100);
  tel.o2=clamp(tel.o2+(96.5-tel.o2)*0.1+(Math.random()-.5)*0.6,75,100);
  tel.co2=clamp(tel.co2+(0.4-tel.co2)*0.1+(Math.random()-.5)*0.05,0,5);
  tel.pressure=clamp(tel.pressure+(101.3-tel.pressure)*0.1+(Math.random()-.5)*0.4,80,140);
  tel.heat=clamp(tel.heat+(40-tel.heat)*0.06+(Math.random()-.5)*1.2,20,100);
  tel.greenhouse=clamp(tel.greenhouse+(91-tel.greenhouse)*0.05+(Math.random()-.5)*0.5,40,100);
  tel.heading=(tel.heading+(Math.random()-.5)*2+360)%360;
  tel.distance+=tel.speed*(1+tel.boost); tel.boost*=0.85;
  tel.eta-=1; if(tel.eta<=0){ tel.destIdx=(tel.destIdx+1)%DESTS.length; tel.eta=240+Math.random()*180; }
  for(const g of GA){ const v=tel[g.k], bar=$('gb_'+g.k); if(bar){ bar.style.width=clamp(v/g.max*100,2,100)+'%'; bar.style.background=gcolor(g,v); }
    const tv=$('gv_'+g.k); if(tv) tv.textContent=(g.k==='co2'?v.toFixed(2):v.toFixed(g.k==='pressure'?1:0))+g.unit; }
  $('t_head').innerHTML=String(Math.round(tel.heading)).padStart(3,'0')+'&deg;';
  $('t_dest').textContent=DESTS[tel.destIdx];
  const mm=Math.floor(tel.eta/60),ss=Math.floor(tel.eta%60); $('t_eta').textContent=mm+'m '+String(ss).padStart(2,'0')+'s';
  $('t_dist').textContent=Math.round(tel.distance).toLocaleString()+' km'; drawMap();
}
function telemetryReact(name){ const fx=FX[name]||'';
  if(fx==='warp'){ tel.boost=8; tel.fuel=clamp(tel.fuel-1.5,0,100); tel.heat=clamp(tel.heat+8,0,100); }
  if(fx==='swirl'){ tel.boost=40; tel.distance+=8e6; tel.heat=clamp(tel.heat+12,0,100); }
  if(name==='master_engine'){ tel.boost=14; tel.fuel=clamp(tel.fuel-2,0,100); }
  if(name==='probe_extend'){ tel.fuel=clamp(tel.fuel+22,0,100); }
  if(fx==='alert'){ tel.o2=clamp(tel.o2-7,0,100); tel.co2=clamp(tel.co2+0.5,0,5); tel.pressure=clamp(tel.pressure-6,0,140); tel.greenhouse=clamp(tel.greenhouse-5,0,100); tel.heat=clamp(tel.heat+10,0,100); }
  if(name==='silence_alarms'){ tel.o2=clamp(tel.o2+5,0,100); tel.co2=clamp(tel.co2-0.4,0,5); tel.greenhouse=clamp(tel.greenhouse+3,0,100); }
}
hudTick(); setInterval(hudTick,900);

// ===== tactical radar contacts =====
const RCON=[['ASTEROID','#9fb0c0'],['COMET','#7be0ff'],['DEBRIS','#8893a8'],['UNKNOWN','#ffb028'],
  ['FRIENDLY','#5dffa0'],['WORMHOLE','#b48bff'],['SATELLITE','#9fd0ee'],['NEBULA','#ff9ad0'],['DERELICT','#c0a060']];
function mkContact(lab,col,ping){ const b=$('blips'); if(!b) return; const a=Math.random()*6.28, r=(ping?10+Math.random()*36:8+Math.random()*40);
  const d=document.createElement('div'); d.className='contact'; d.style.left=(50+Math.cos(a)*r)+'%'; d.style.top=(50+Math.sin(a)*r)+'%';
  d.innerHTML='<i style="background:'+col+';box-shadow:0 0 8px '+col+'"></i>'+(lab?'<span style="color:'+col+'">'+lab+'</span>':'');
  b.appendChild(d); requestAnimationFrame(()=>d.style.opacity=1);
  if(ping){ setTimeout(()=>{d.style.opacity=0; setTimeout(()=>d.remove(),700);},1100); return; }
  const dx=(Math.random()-.5)*0.32, dy=(Math.random()-.5)*0.32; let life=0;
  const mv=setInterval(()=>{ life++; d.style.left=(parseFloat(d.style.left)+dx)+'%'; d.style.top=(parseFloat(d.style.top)+dy)+'%';
    if(life>44){ clearInterval(mv); d.style.opacity=0; setTimeout(()=>d.remove(),700);} },150); }
function radarContact(){ const r=RCON[Math.floor(Math.random()*RCON.length)]; mkContact(r[0],r[1],false); }
function radarPing(){ mkContact('','#5dffa0',true); }
setInterval(()=>{ if(Math.random()<.6) radarContact(); }, 1700);
for(let i=0;i<3;i++) radarContact();

// ===== galactic database =====
const GAL=[
 {n:'The Sun',t:'G-TYPE STAR',r:'star',c:'#ffcf4d',s:[['Composition','Hydrogen & Helium'],['Location','Center of our system'],['Diameter','1.39 million km'],['Surface temp','5,500°C'],['Water','None'],['Life','Gives life to Earth']],f:'Holds 99.8% of the Solar System’s mass.'},
 {n:'Mercury',t:'PLANET',r:'planet',c:'#b3a394',s:[['Composition','Rock & iron'],['From Sun','57.9 million km'],['Diameter','4,879 km'],['Temp','-173 to 427°C'],['Water','Trace ice in craters'],['Life','None']],f:'The smallest planet — and the fastest.'},
 {n:'Venus',t:'PLANET',r:'planet',c:'#e6c87a',s:[['Composition','Rock, thick CO₂ air'],['From Sun','108 million km'],['Diameter','12,104 km'],['Surface','465°C (hottest)'],['Water','Boiled away long ago'],['Life','None']],f:'Spins backwards; a day is longer than its year.'},
 {n:'Earth',t:'PLANET • HOME',r:'planet',c:'#3f8fd0',s:[['Composition','Rock, metal & water'],['From Sun','149.6 million km'],['Diameter','12,742 km'],['Avg temp','15°C'],['Water','71% of surface'],['Life','YES — millions of species']],f:'The only known world with life.'},
 {n:'Mars',t:'PLANET',r:'planet',c:'#c9572f',s:[['Composition','Rock & rusty iron'],['From Sun','227.9 million km'],['Diameter','6,779 km'],['Avg temp','-63°C'],['Water','Polar ice + old riverbeds'],['Life','None found — still searching']],f:'Home to the tallest volcano in the Solar System.'},
 {n:'Jupiter',t:'GAS GIANT',r:'gas',c:'#d8a874',s:[['Composition','Hydrogen & Helium gas'],['From Sun','778 million km'],['Diameter','139,820 km'],['Temp','-110°C'],['Moons','95+'],['Feature','Great Red Spot storm']],f:'You could fit 1,300 Earths inside it.'},
 {n:'Saturn',t:'RINGED GIANT',r:'ringed',c:'#e3cf94',s:[['Composition','Hydrogen & Helium'],['From Sun','1.4 billion km'],['Diameter','116,460 km'],['Temp','-140°C'],['Rings','Ice & rock'],['Moons','146']],f:'Less dense than water — it would float.'},
 {n:'Uranus',t:'ICE GIANT',r:'gas',c:'#8fe0e6',s:[['Composition','Ice, methane & gas'],['From Sun','2.9 billion km'],['Diameter','50,724 km'],['Temp','-224°C'],['Tilt','98° (on its side)'],['Moons','28']],f:'Rolls on its side as it orbits the Sun.'},
 {n:'Neptune',t:'ICE GIANT',r:'planet',c:'#3b6fd4',s:[['Composition','Ice & gas'],['From Sun','4.5 billion km'],['Diameter','49,244 km'],['Temp','-214°C'],['Winds','2,100 km/h (fastest)'],['Moons','16']],f:'The windiest, farthest planet from the Sun.'},
 {n:'Pluto',t:'DWARF PLANET',r:'planet',c:'#c9b6a0',s:[['Composition','Rock & ice'],['From Sun','5.9 billion km'],['Diameter','2,377 km'],['Temp','-229°C'],['Water','Frozen nitrogen & ice'],['Moons','5']],f:'Has a giant heart-shaped glacier of ice.'},
 {n:'The Moon',t:'MOON OF EARTH',r:'moon',c:'#cfd3d8',s:[['Composition','Rock & dust'],['Distance','384,400 km'],['Diameter','3,475 km'],['Temp','-173 to 127°C'],['Water','Ice at the poles'],['Life','None']],f:'Drifting ~3.8 cm farther from Earth each year.'},
 {n:'Europa',t:'MOON OF JUPITER',r:'moon',c:'#dcc9a8',s:[['Composition','Ice shell over rock'],['Orbits','Jupiter'],['Diameter','3,122 km'],['Temp','-160°C'],['Water','Hidden ocean below ice'],['Life','Maybe — a top target']],f:'May hide twice Earth’s water beneath its ice.'},
 {n:'Titan',t:'MOON OF SATURN',r:'moon',c:'#d8a24a',s:[['Composition','Ice & rock'],['Orbits','Saturn'],['Diameter','5,150 km'],['Temp','-179°C'],['Liquid','Lakes of methane'],['Air','Thick nitrogen']],f:'The only moon with a thick atmosphere.'},
 {n:'Io',t:'MOON OF JUPITER',r:'moon',c:'#e6d36a',s:[['Composition','Rock & sulfur'],['Orbits','Jupiter'],['Diameter','3,643 km'],['Volcanoes','400+ active'],['Water','None'],['Record','Most volcanic world']],f:'The most volcanically active world we know.'},
 {n:'Betelgeuse',t:'RED SUPERGIANT',r:'star',c:'#ff7042',s:[['Composition','Hydrogen & Helium'],['Distance','~650 light-years'],['Radius','~750× the Sun'],['Surface','~3,200°C'],['Constellation','Orion'],['Fate','Will go supernova']],f:'So vast it would swallow Jupiter’s orbit.'},
 {n:'Sirius',t:'BRIGHTEST STAR',r:'star',c:'#bfe0ff',s:[['Composition','Hydrogen & Helium'],['Distance','8.6 light-years'],['Size','~1.7× the Sun'],['Surface','~9,940°C'],['System','Two stars'],['Brightness','Brightest in our sky']],f:'The brightest star in Earth’s night sky.'},
 {n:'Proxima Centauri',t:'RED DWARF',r:'star',c:'#ff8a5a',s:[['Composition','Hydrogen & Helium'],['Distance','4.24 light-years'],['Size','~0.15× the Sun'],['Surface','~2,800°C'],['Planets','Proxima b (Earth-size)'],['Note','Closest star to the Sun']],f:'The nearest star to our Solar System.'},
 {n:'Polaris',t:'THE NORTH STAR',r:'star',c:'#ffe9b0',s:[['Composition','Hydrogen & Helium'],['Distance','~430 light-years'],['Size','~46× the Sun'],['Type','Cepheid supergiant'],['Brightness','~2,500× the Sun'],['Use','Finding true north']],f:'Sits almost exactly above the North Pole.'},
 {n:'VY Canis Majoris',t:'RED HYPERGIANT',r:'star',c:'#ff5a3a',s:[['Composition','Hydrogen & Helium'],['Distance','~3,800 light-years'],['Radius','~1,400× the Sun'],['Surface','~3,200°C'],['Class','Hypergiant'],['Fate','Hypernova one day']],f:'One of the largest known stars in the galaxy.'},
 {n:'Sagittarius A*',t:'BLACK HOLE',r:'blackhole',c:'#caa6ff',s:[['Type','Supermassive black hole'],['Location','Center of the Milky Way'],['Mass','4.3 million Suns'],['Distance','26,000 light-years'],['Gravity','Nothing escapes'],['Photographed','2022']],f:'Our galaxy’s heart — first imaged in 2022.'},
 {n:'TON 618',t:'ULTRAMASSIVE BH',r:'blackhole',c:'#b48bff',s:[['Type','Ultramassive black hole'],['Distance','10.4 billion light-years'],['Mass','66 billion Suns'],['Powers','A blazing quasar'],['Size','Bigger than our system'],['Light','From the early universe']],f:'One of the most massive black holes ever found.'},
 {n:'Milky Way',t:'OUR GALAXY',r:'galaxy',c:'#bcd2ff',s:[['Composition','Stars, gas & dust'],['Width','100,000 light-years'],['Stars','100–400 billion'],['Type','Barred spiral'],['Age','13.6 billion yrs'],['Home','Yes — Earth is here']],f:'Our home — the Sun is one of its billions of stars.'},
 {n:'Andromeda',t:'GALAXY • M31',r:'galaxy',c:'#cdb8ff',s:[['Composition','Stars, gas & dust'],['Distance','2.5 million light-years'],['Stars','~1 trillion'],['Type','Spiral galaxy'],['Width','220,000 ly'],['Future','Will merge with us']],f:'On a collision course with the Milky Way (~4.5 B yrs).'},
 {n:'Whirlpool',t:'GALAXY • M51',r:'galaxy',c:'#a9c6ff',s:[['Composition','Stars, gas & dust'],['Distance','31 million light-years'],['Type','Grand-design spiral'],['Width','76,000 ly'],['Companion','A small buddy galaxy'],['Where','In Canes Venatici']],f:'A textbook spiral with a little companion galaxy.'},
 {n:'Orion Nebula',t:'NEBULA • M42',r:'nebula',c:'#ff9ad0',s:[['Composition','Gas & dust'],['Distance','1,344 light-years'],['Width','24 light-years'],['Role','Star nursery'],['New stars','~700 forming'],['Visible','Naked eye in Orion']],f:'A stellar nursery you can spot in Orion’s sword.'},
 {n:'Crab Nebula',t:'SUPERNOVA REMNANT',r:'nebula',c:'#7be0ff',s:[['Composition','Glowing gas'],['Distance','6,500 light-years'],['Width','11 light-years'],['Born','1054 AD supernova'],['Core','Pulsar spins 30×/sec'],['Status','Still expanding fast']],f:'The glowing wreck of a star that exploded in 1054.'},
 {n:'Eagle Nebula',t:'PILLARS OF CREATION',r:'nebula',c:'#9affc0',s:[['Composition','Cold gas & dust'],['Distance','5,700 light-years'],['Pillars','Light-years tall'],['Role','Making new stars'],['Width','70 light-years'],['Famous','Hubble photo, 1995']],f:'Towers of gas where brand-new stars are born.'},
 {n:'Halley’s Comet',t:'COMET',r:'comet',c:'#bfe9ff',s:[['Composition','Ice, dust & rock'],['Orbit','Returns every 76 yrs'],['Nucleus','~15 km wide'],['Tail','Millions of km long'],['Next visit','2061'],['Seen since','240 BC']],f:'The famous comet you might see once in a lifetime.'},
 {n:'TRAPPIST-1',t:'STAR SYSTEM',r:'system',c:'#ff9c5a',s:[['Star','Tiny red dwarf'],['Distance','40 light-years'],['Planets','7 Earth-size worlds'],['Water','Maybe on 3'],['Life','Possible — being studied'],['Found','2017']],f:'Seven rocky worlds circling one tiny red star.'},
 {n:'Kepler-452b',t:'EXOPLANET',r:'planet',c:'#7fd0a0',s:[['Composition','Likely rocky'],['Distance','1,400 light-years'],['Size','~1.6× Earth'],['Year','385 days'],['Water','Possibly'],['Nickname','Earth’s older cousin']],f:'A possible rocky world in its star’s habitable zone.'},
];
let galIdx=-1;
const gc=$('galcanvas'), gx=gc.getContext('2d');
function galResize(){ gc.width=gc.clientWidth; gc.height=gc.clientHeight; }
function galDraw(o){ galResize(); const w=gc.width,h=gc.height,cx2=w/2,cy=h/2,R=Math.min(w,h)*0.34; gx.clearRect(0,0,w,h);
  // faint stars
  gx.fillStyle='rgba(255,255,255,.5)'; for(let i=0;i<30;i++){ gx.globalAlpha=Math.random()*.5; gx.fillRect(Math.random()*w,Math.random()*h,1,1);} gx.globalAlpha=1;
  const c=o.c;
  if(o.r==='blackhole'){ const rg=gx.createRadialGradient(cx2,cy,R*.35,cx2,cy,R*1.5); rg.addColorStop(0,'#000'); rg.addColorStop(.55,'#000'); rg.addColorStop(.7,c); rg.addColorStop(1,'rgba(0,0,0,0)');
    gx.fillStyle=rg; gx.beginPath(); gx.arc(cx2,cy,R*1.5,0,7); gx.fill(); gx.strokeStyle=c; gx.lineWidth=3; gx.beginPath(); gx.ellipse(cx2,cy,R*1.3,R*.4,.5,0,7); gx.stroke(); }
  else if(o.r==='galaxy'){ for(let a=0;a<3;a++){ gx.strokeStyle=c; gx.globalAlpha=.5; gx.lineWidth=3; gx.beginPath();
      for(let t=0;t<6.2;t+=.1){ const rr=R*t/6.2*1.4, x=cx2+Math.cos(t+a*2.1)*rr, y=cy+Math.sin(t+a*2.1)*rr*.6; t===0?gx.moveTo(x,y):gx.lineTo(x,y);} gx.stroke(); }
    gx.globalAlpha=1; const rg=gx.createRadialGradient(cx2,cy,0,cx2,cy,R*.5); rg.addColorStop(0,'#fff'); rg.addColorStop(1,c); gx.fillStyle=rg; gx.beginPath(); gx.arc(cx2,cy,R*.35,0,7); gx.fill(); }
  else if(o.r==='nebula'){ for(let i=0;i<5;i++){ const rg=gx.createRadialGradient(cx2+(Math.random()-.5)*R,cy+(Math.random()-.5)*R,2,cx2,cy,R*1.4); rg.addColorStop(0,c); rg.addColorStop(1,'rgba(0,0,0,0)'); gx.globalAlpha=.4; gx.fillStyle=rg; gx.fillRect(0,0,w,h);} gx.globalAlpha=1;
    gx.fillStyle='#fff'; for(let i=0;i<8;i++){ gx.beginPath(); gx.arc(cx2+(Math.random()-.5)*R,cy+(Math.random()-.5)*R,1.4,0,7); gx.fill(); } }
  else if(o.r==='comet'){ gx.save(); const g2=gx.createLinearGradient(cx2-R,cy+R,cx2+R*.4,cy-R*.2); g2.addColorStop(0,'rgba(0,0,0,0)'); g2.addColorStop(1,c);
    gx.strokeStyle=g2; gx.lineWidth=R*.5; gx.lineCap='round'; gx.beginPath(); gx.moveTo(cx2-R,cy+R*.7); gx.lineTo(cx2+R*.3,cy-R*.1); gx.stroke(); gx.restore();
    const rg=gx.createRadialGradient(cx2+R*.3,cy-R*.1,1,cx2+R*.3,cy-R*.1,R*.45); rg.addColorStop(0,'#fff'); rg.addColorStop(1,c); gx.fillStyle=rg; gx.beginPath(); gx.arc(cx2+R*.3,cy-R*.1,R*.32,0,7); gx.fill(); }
  else if(o.r==='star'){ const rg=gx.createRadialGradient(cx2,cy,0,cx2,cy,R*1.5); rg.addColorStop(0,'#fff'); rg.addColorStop(.3,c); rg.addColorStop(.7,c); rg.addColorStop(1,'rgba(0,0,0,0)'); gx.fillStyle=rg; gx.beginPath(); gx.arc(cx2,cy,R*1.5,0,7); gx.fill();
    gx.strokeStyle='rgba(255,255,255,.5)'; gx.lineWidth=2; for(let a=0;a<4;a++){ gx.beginPath(); gx.moveTo(cx2-R*1.7*Math.cos(a*0.79),cy-R*1.7*Math.sin(a*0.79)); gx.lineTo(cx2+R*1.7*Math.cos(a*0.79),cy+R*1.7*Math.sin(a*0.79)); gx.stroke(); } }
  else if(o.r==='system'){ gx.strokeStyle='rgba(255,255,255,.3)'; for(let i=1;i<=4;i++){ gx.beginPath(); gx.ellipse(cx2,cy,R*0.4*i,R*0.18*i,0,0,7); gx.stroke(); }
    const rg=gx.createRadialGradient(cx2,cy,0,cx2,cy,R*.4); rg.addColorStop(0,'#fff'); rg.addColorStop(1,c); gx.fillStyle=rg; gx.beginPath(); gx.arc(cx2,cy,R*.3,0,7); gx.fill();
    gx.fillStyle='#9fd0ee'; for(let i=1;i<=4;i++){ const an=i*1.7; gx.beginPath(); gx.arc(cx2+Math.cos(an)*R*0.4*i,cy+Math.sin(an)*R*0.18*i,3,0,7); gx.fill(); } }
  else { // planet / gas / ringed / moon
    const rg=gx.createRadialGradient(cx2-R*.35,cy-R*.35,R*.1,cx2,cy,R); rg.addColorStop(0,'#fff'); rg.addColorStop(.25,c); rg.addColorStop(1,'rgba(0,0,10,.9)');
    gx.fillStyle=rg; gx.beginPath(); gx.arc(cx2,cy,R,0,7); gx.fill();
    if(o.r==='gas'){ gx.save(); gx.beginPath(); gx.arc(cx2,cy,R,0,7); gx.clip(); gx.globalAlpha=.2;
      for(let i=-3;i<=3;i++){ gx.strokeStyle='#fff'; gx.lineWidth=R*.16; gx.beginPath(); gx.ellipse(cx2,cy+i*R*.28,R*1.1,R*.14,0,0,7); gx.stroke(); } gx.restore(); gx.globalAlpha=1; }
    if(o.r==='moon'){ gx.fillStyle='rgba(0,0,0,.18)'; for(let i=0;i<7;i++){ gx.beginPath(); gx.arc(cx2+(Math.random()-.5)*R*1.3,cy+(Math.random()-.5)*R*1.3,2+Math.random()*4,0,7); gx.fill(); } }
    const sh=gx.createRadialGradient(cx2+R*.5,cy+R*.45,R*.2,cx2,cy,R*1.05); sh.addColorStop(0,'rgba(0,0,0,0)'); sh.addColorStop(1,'rgba(0,0,8,.65)'); gx.fillStyle=sh; gx.beginPath(); gx.arc(cx2,cy,R,0,7); gx.fill();
    if(o.r==='ringed'){ gx.strokeStyle=c; gx.lineWidth=4; gx.globalAlpha=.8; gx.beginPath(); gx.ellipse(cx2,cy,R*1.7,R*.5,-.5,0,7); gx.stroke(); gx.globalAlpha=1; }
  }
}
const WIKI={'The Sun':'Sun','Mercury':'Mercury (planet)','Venus':'Venus','Earth':'Earth','Mars':'Mars','Jupiter':'Jupiter','Saturn':'Saturn','Uranus':'Uranus','Neptune':'Neptune','Pluto':'Pluto','The Moon':'Moon','Europa':'Europa (moon)','Titan':'Titan (moon)','Io':'Io (moon)','Betelgeuse':'Betelgeuse','Sirius':'Sirius','Proxima Centauri':'Proxima Centauri','Polaris':'Polaris','VY Canis Majoris':'VY Canis Majoris','Sagittarius A*':'Sagittarius A*','TON 618':'TON 618','Milky Way':'Milky Way','Andromeda':'Andromeda Galaxy','Whirlpool':'Whirlpool Galaxy','Orion Nebula':'Orion Nebula','Crab Nebula':'Crab Nebula','Eagle Nebula':'Eagle Nebula','Halley’s Comet':"Halley's Comet",'TRAPPIST-1':'TRAPPIST-1','Kepler-452b':'Kepler-452b'};
function galNext(){ galIdx=(galIdx+1)%GAL.length; const o=GAL[galIdx];
  $('galidx').textContent=(galIdx+1)+'/'+GAL.length; $('galname').textContent=o.n; $('galtype').textContent=o.t;
  $('galstats').innerHTML=o.s.map(s=>'<div class="galstat"><span>'+s[0]+'</span><b style="color:#cfeaff">'+s[1]+'</b></div>').join('');
  $('galfact').textContent='“'+o.f+'”'; galDraw(o);
  const img=$('galimg'); img.style.opacity=0; const want=galIdx, title=WIKI[o.n];
  if(title){ fetch('https://en.wikipedia.org/w/api.php?action=query&format=json&prop=pageimages&piprop=thumbnail&pithumbsize=560&titles='+encodeURIComponent(title)+'&origin=*')
    .then(r=>r.json()).then(j=>{ if(want!==galIdx) return; const ps=j.query.pages, pg=ps[Object.keys(ps)[0]], src=pg&&pg.thumbnail&&pg.thumbnail.source;
      if(src){ img.onload=()=>{ if(want===galIdx) img.style.opacity=1; }; img.onerror=()=>{img.style.opacity=0;}; img.src=src; } }).catch(()=>{}); } }
galNext(); setInterval(galNext,7000);

// ===== hydrogen / energy schematic =====
$('energysvg').innerHTML=
 '<defs></defs>'+
 '<rect x="14" y="20" width="34" height="110" rx="6" fill="#0c1a26" stroke="#2b5a78"/>'+
 '<rect id="tankA" x="16" y="60" width="30" height="68" rx="4" fill="#2ad0e0"/>'+
 '<text x="31" y="142" fill="#7fb8da" font-size="8" text-anchor="middle">H₂ TANK A</text>'+
 '<rect x="14" y="20" width="34" height="110" rx="6" fill="none" stroke="#2b5a78"/>'+
 '<rect x="192" y="20" width="34" height="110" rx="6" fill="#0c1a26" stroke="#2b5a78"/>'+
 '<rect id="tankB" x="194" y="55" width="30" height="73" rx="4" fill="#2ad0e0"/>'+
 '<text x="209" y="142" fill="#7fb8da" font-size="8" text-anchor="middle">H₂ TANK B</text>'+
 '<rect x="192" y="20" width="34" height="110" rx="6" fill="none" stroke="#2b5a78"/>'+
 '<circle cx="120" cy="62" r="22" fill="#10263a" stroke="#43e0ff" stroke-width="2"/>'+
 '<circle id="reactor" cx="120" cy="62" r="13" fill="#43e0ff"><animate attributeName="opacity" values="1;.5;1" dur="1.6s" repeatCount="indefinite"/></circle>'+
 '<text x="120" y="98" fill="#bfe2f5" font-size="8" text-anchor="middle">REACTOR</text>'+
 '<path class="flow" d="M48 75 H120" stroke="#43e0ff" stroke-width="3" fill="none"/>'+
 '<path class="flow" d="M192 70 H120" stroke="#43e0ff" stroke-width="3" fill="none"/>'+
 '<path class="flow" d="M120 84 V120 H60" stroke="#3ad07a" stroke-width="3" fill="none"/>'+
 '<path class="flow" d="M120 84 V120 H180" stroke="#3ad07a" stroke-width="3" fill="none"/>'+
 '<circle cx="60" cy="120" r="6" fill="#10263a" stroke="#3ad07a" stroke-width="2"/>'+
 '<text x="60" y="138" fill="#7fb8da" font-size="7.5" text-anchor="middle">ENGINES</text>'+
 '<circle cx="180" cy="120" r="6" fill="#10263a" stroke="#3ad07a" stroke-width="2"/>'+
 '<text x="180" y="138" fill="#7fb8da" font-size="7.5" text-anchor="middle">LIFE SUP</text>';
function energyTick(){ const a=$('tankA'),b=$('tankB'); if(!a) return;
  const fa=clamp(tel.fuel/100,.05,1), fb=clamp((tel.fuel-6)/100,.05,1);
  a.setAttribute('y',(128-68*fa).toFixed(0)); a.setAttribute('height',(68*fa).toFixed(0));
  b.setAttribute('y',(128-73*fb).toFixed(0)); b.setAttribute('height',(73*fb).toFixed(0)); }
setInterval(energyTick,900); energyTick();

// ===== shared helpers + camera feeds =====
function wikiImg(title,size,cb){ fetch('https://en.wikipedia.org/w/api.php?action=query&format=json&prop=pageimages&piprop=thumbnail&pithumbsize='+size+'&titles='+encodeURIComponent(title)+'&origin=*')
  .then(r=>r.json()).then(j=>{ const ps=j.query.pages,pg=ps[Object.keys(ps)[0]],s=pg&&pg.thumbnail&&pg.thumbnail.source; if(s) cb(s); }).catch(()=>{}); }
function clock2(){ const s=new Date().toLocaleTimeString(); const a=$('ghtime'),b=$('extime'); if(a)a.textContent=s; if(b)b.textContent=s; }
setInterval(clock2,1000); clock2();
// greenhouse — cycle real plant / greenhouse photos
const GH=['Vegetable Production System','Hydroponics','Greenhouse','Vertical farming','Plant nursery']; let ghI=0, ghCur='';
function ghNext(){ const im=$('ghimg'), vd=$('ghvid');
  if(GHLOCAL.length){ const f=GHLOCAL[ghI++%GHLOCAL.length]; if(f===ghCur) return; ghCur=f;
    if(/\.mp4$/i.test(f)){ im.style.opacity=0; vd.src='/greenhouse/'+f; vd.style.opacity=1; vd.play().catch(()=>{}); }
    else { try{vd.pause();}catch(e){} vd.style.opacity=0; const u='/greenhouse/'+f, pre=new Image(); pre.onload=()=>{ im.src=u; im.style.opacity=1; }; pre.src=u; }
    return; }
  const t=GH[ghI++%GH.length]; wikiImg(t,720,u=>{ vd.style.opacity=0; const pre=new Image(); pre.onload=()=>{ im.src=u; im.style.opacity=1; }; pre.src=u; }); }
ghNext(); setInterval(ghNext,9000);
// external antenna cam — live starfield
const ef=Array.from({length:60},()=>({x:Math.random(),y:Math.random(),s:Math.random()*1.6+.3}));
(function(){ const c=$('extcam'),x=c.getContext('2d'); let t=0; setInterval(()=>{ c.width=c.clientWidth;c.height=c.clientHeight; const w=c.width,h=c.height;
  x.fillStyle='#01030a'; x.fillRect(0,0,w,h);
  for(const s of ef){ s.x-=0.0016*(1+warp*8); if(s.x<0)s.x=1; x.globalAlpha=.4+s.s/2; x.fillStyle='#bfe0ff'; x.fillRect(s.x*w,s.y*h,s.s,s.s);} x.globalAlpha=1;
  const px=(w*1.2-(t*0.6)%(w*1.6)),pr=22,rg=x.createRadialGradient(px-8,h*.4-8,4,px,h*.4,pr); rg.addColorStop(0,'#9fd0ff');rg.addColorStop(1,'#14406a'); x.fillStyle=rg; x.beginPath(); x.arc(px,h*.4,pr,0,7); x.fill();
  x.strokeStyle='rgba(120,150,170,.6)';x.lineWidth=2;x.beginPath();x.moveTo(0,h);x.lineTo(w*.3,h*.55);x.moveTo(w,h);x.lineTo(w*.7,h*.5);x.stroke();
  if(Math.random()<.04){x.fillStyle='rgba(255,255,255,.08)';x.fillRect(0,Math.random()*h,w,2);} t++; },120); })();
// EXT-CAM: if we have family EVA / exploration photos, show those over the starfield
let exI=0, exCur='';
function exNext(){ const im=$('eximg'), vd=$('exvid'); if(!im) return;
  if(!OUTSIDE.length){ im.style.opacity=0; if(vd) vd.style.opacity=0; return; }
  const f=OUTSIDE[exI++%OUTSIDE.length]; if(f===exCur) return; exCur=f;
  if(/\.mp4$/i.test(f)){ im.style.opacity=0; vd.src='/outside/'+f; vd.style.opacity=1; vd.play().catch(()=>{}); }
  else { try{vd.pause();}catch(e){} vd.style.opacity=0; const u='/outside/'+f, pre=new Image(); pre.onload=()=>{ im.src=u; im.style.opacity=1; }; pre.src=u; } }
exNext(); setInterval(exNext,9000);

// ===== montage easter egg: triple-tap a control -> family montage + anthem =====
let montOn=false, montI=0;
function playMontage(){ if(montOn || !MONTAGE.length) return; montOn=true;
  const ov=$('montage'), v=$('montvid'), im=$('montimg'), a=$('anthem'); ov.classList.add('on'); montI=0;
  function nextClip(){ const f=MONTAGE[montI++%MONTAGE.length]; clearTimeout(window._montImgT);
    if(/\.(jpg|jpeg|png)$/i.test(f)){ v.style.display='none'; try{v.pause();}catch(_){} im.style.display='block'; im.src='/montage/'+f; window._montImgT=setTimeout(nextClip,3800); }
    else { im.style.display='none'; v.style.display='block'; v.src='/montage/'+f; v.play().catch(()=>{}); } }
  v.muted=true; v.onended=nextClip; nextClip();
  try{ a.currentTime=0; a.volume=1; a.play().catch(()=>{}); }catch(_){}
  a.onended=stopMontage;
  clearTimeout(window._montT); window._montT=setTimeout(stopMontage, 60000);
}
function stopMontage(){ if(!montOn) return; montOn=false; const ov=$('montage'),v=$('montvid'),im=$('montimg'),a=$('anthem');
  ov.classList.remove('on'); try{v.pause(); v.removeAttribute('src');}catch(_){} im.style.display='none'; try{a.pause();}catch(_){} clearTimeout(window._montT); clearTimeout(window._montImgT); }

let tapName='', taps=[];
function checkTriple(name){ const now=Date.now();
  if(name!==tapName){ tapName=name; taps=[now]; return; }
  taps.push(now); taps=taps.filter(t=>now-t<2200);
  if(taps.length>=3){ taps=[]; if(montOn) stopMontage(); else playMontage(); } }

// ===== idle screensaver "DEEP FIELD" (A/B crossfade) + deep sleep =====
let SAVER=[], saverOn=false, saverI=0, lastAct=performance.now(), asleep=false, svEls=null, svFront=0;
const IDLE_MS=75000;      // -> screensaver after 75s idle
const SLEEP_MS=360000;    // -> dark + monitor-off after 6 min idle
const SV_DWELL=16000, SV_RATE=0.5;   // hold each vista 16s, play at half speed (calm)
const SAVER_NAMES=['STAR NURSERY','THE COSMIC CLIFFS','RINGED GIANT','OCEAN WORLD','LAVA WORLD','ICE MOON','TWIN SUNS','THE GREAT SPIRAL','EVENT HORIZON','THE PULSAR','EMERALD VALLEY','CRYSTAL CAVERNS','AURORA WORLD','THE QUASAR','SUPERNOVA REMNANT','GAS GIANT STORM','GLOBULAR CLUSTER','ROGUE PLANET','RED DWARF FLARE','THE GOLDEN RINGS','DESERT EXOWORLD','BIOLUMINESCENT FOREST','FROZEN GEYSERS','CANYON OF WINDS','THE NEBULA VEIL','MOONRISE','GALACTIC CORE','COMET PASSAGE','FLOATING ISLANDS','THE DARK BETWEEN'];
const SAVER_WIKI=[['Pillars of Creation','STAR NURSERY'],['Carina Nebula','THE COSMIC CLIFFS'],['Saturn','RINGED GIANT'],['Whirlpool Galaxy','THE GREAT SPIRAL'],['Black hole','EVENT HORIZON'],['Crab Nebula','SUPERNOVA REMNANT'],['Helix Nebula','THE NEBULA VEIL'],['Jupiter','GAS GIANT STORM'],['Europa (moon)','ICE MOON'],['Orion Nebula','STAR NURSERY'],['Andromeda Galaxy','NEIGHBORING GALAXY'],['Eagle Nebula','THE PILLARS'],['Ring Nebula','THE GOLDEN RING'],['Messier 87','GALACTIC CORE']];
function noteActivity(){ lastAct=performance.now(); if(asleep) wake(); if(saverOn) stopSaver(); }
function startSaver(){ if(saverOn||montOn||missionOn||asleep) return; saverOn=true; saverI=0; svFront=0; svEls=[$('savervid'),$('savervid2')]; svEls.forEach(v=>{v.style.opacity=0;}); $('saverimg').style.opacity=0; $('saver').classList.add('on'); saverShow(); }
function stopSaver(){ if(!saverOn) return; saverOn=false; $('saver').classList.remove('on'); if(svEls) svEls.forEach(v=>{try{v.pause(); v.removeAttribute('src');}catch(_){} v.style.opacity=0;}); $('saverimg').style.opacity=0; clearTimeout(window._svT); clearTimeout(window._svReady); }
function saverShow(){ if(!saverOn) return;
  if(!SAVER.length){ const pair=SAVER_WIKI[saverI++%SAVER_WIKI.length], im=$('saverimg'); $('savercap').textContent=pair[1];
    wikiImg(pair[0],1280,u=>{ if(!saverOn) return; const pre=new Image(); pre.onload=()=>{ if(!saverOn) return; im.src=u; im.style.opacity=1; }; pre.src=u; });
    clearTimeout(window._svT); window._svT=setTimeout(saverShow,8000); return; }
  const f=SAVER[saverI%SAVER.length], mm=f.match(/(\d+)/), nm=(mm?SAVER_NAMES[parseInt(mm[1],10)-1]:'')||''; saverI++;
  const inEl=svEls[svFront^1], outEl=svEls[svFront]; let done=false;
  const go=()=>{ if(done||!saverOn) return; done=true; clearTimeout(window._svReady);
    inEl.playbackRate=SV_RATE; inEl.play().catch(()=>{});
    $('savercap').style.opacity=0; setTimeout(()=>{ if(saverOn){ $('savercap').textContent=nm; $('savercap').style.opacity=1; } },350);
    inEl.style.opacity=1; outEl.style.opacity=0; svFront^=1;
    clearTimeout(window._svT); window._svT=setTimeout(saverShow,SV_DWELL); };
  inEl.oncanplaythrough=go; inEl.src='/screensaver/'+f; try{inEl.load();}catch(_){}
  window._svReady=setTimeout(go,2000); }   // safety if canplaythrough is slow
function goSleep(){ if(asleep) return; asleep=true; if(saverOn) stopSaver(); $('sleep').classList.add('on'); }   // black overlay only — monitor stays powered, wakes on any button
function wake(){ if(!asleep) return; asleep=false; $('sleep').classList.remove('on'); }
// auto-idle only goes to the screensaver (which runs indefinitely). Sleep/dark is MANUAL via the combo, never automatic.
setInterval(()=>{ if(montOn||missionOn||asleep){ return; } const idle=performance.now()-lastAct;
  if(idle>IDLE_MS && !saverOn) startSaver(); },2000);
window.addEventListener('pointerdown',noteActivity); window.addEventListener('keydown',noteActivity);

// ===== mission combo engine — secret control sequences trigger a cinematic =====
const MISSIONS=[
  {id:'launch', name:'PUNCH IT — LAUNCH', seq:['left_engine_on','right_engine_on','master_engine','launchbar_extend','flap_full','gear_up','wing_spread'], beats:['launchbar_extend','gear_up','master_engine','wing_spread']},
  {id:'blackhole', name:'BLACK HOLE SLINGSHOT', seq:['hook_in_blackhole','master_engine','wing_fold','antiskid_on','hook_out_blackhole'], beats:['hook_in_blackhole','*blackhole_spiral','hook_out_blackhole']},
  {id:'asteroid', name:'ASTEROID RUN', seq:['gear_up','wing_fold','flap_half','antiskid_on','taxi_lights_on'], beats:['flap_half','flap_full','taxi_lights_on']},
  {id:'pod', name:'ESCAPE POD - BRING US HOME', seq:['jettison_alarm','seljett_stores','seljett_left_fuel','seljett_right_fuel','seljett_escape_pod','silence_alarms'], beats:['jettison_alarm','seljett_left_fuel','seljett_escape_pod','*pod_safe']},
];
const SAVER_COMBO=['taxi_lights_off','taxi_lights_on','taxi_lights_off'];      // -> DEEP FIELD screensaver
const SLEEP_COMBO=['taxi_lights_off','gear_down','taxi_lights_off'];           // -> screen dark / sleep
let comboBuf=[], missionOn=false;
function comboPush(name){ const t=performance.now(); comboBuf.push({n:name,t}); comboBuf=comboBuf.filter(e=>t-e.t<24000); if(comboBuf.length>48) comboBuf=comboBuf.slice(-48);
  if(matchSeq(SLEEP_COMBO)){ comboBuf=[]; goSleep(); return; }
  if(matchSeq(SAVER_COMBO)){ comboBuf=[]; startSaver(); return; }
  let best=null; for(const m of MISSIONS){ if(matchSeq(m.seq) && (!best||m.seq.length>best.seq.length)) best=m; }
  if(best){ comboBuf=[]; playMission(best); } }
function matchSeq(seq){ const b=comboBuf; if(!b.length||b[b.length-1].n!==seq[seq.length-1]) return false; let si=seq.length-1; for(let i=b.length-1;i>=0&&si>=0;i--){ if(b[i].n===seq[si]) si--; } return si<0; }
function mSrc(b){ if(b[0]==='*') return {t:'v',u:'/missions/'+b.slice(1)+'.mp4'}; if(VIDEOS.has(b)) return {t:'v',u:'/videos/'+b+'.mp4'}; if(STILLS.has(b)) return {t:'i',u:'/stills/'+b+'.jpg'}; return {t:'i',u:''}; }
function playMission(m){ if(missionOn) return; missionOn=true; if(saverOn) stopSaver();
  const ov=$('mission'), v=$('mfilm'), im=$('mimg'), a=$('mtrack'); ov.classList.add('on'); $('mtitle').textContent=m.name;
  try{ a.src='/missions/'+m.id+'.mp3'; a.currentTime=0; a.volume=1; a.play().catch(()=>{}); a.onended=endMission; }catch(_){}
  let i=0; (function beat(){ if(!missionOn) return; const s=mSrc(m.beats[i++ % m.beats.length]); clearTimeout(window._mbT);
    if(s.t==='v'){ im.style.display='none'; v.style.display='block'; v.src=s.u; v.play().catch(()=>{}); v.onended=beat; window._mbT=setTimeout(beat,8000); }
    else { v.style.display='none'; try{v.pause();}catch(_){} im.style.display='block'; if(s.u) im.src=s.u; window._mbT=setTimeout(beat,3500); } })();
  clearTimeout(window._mEnd); window._mEnd=setTimeout(endMission,32000); }
function endMission(){ if(!missionOn) return; missionOn=false; const ov=$('mission'),v=$('mfilm'),a=$('mtrack');
  ov.classList.remove('on'); try{v.pause(); v.removeAttribute('src');}catch(_){} $('mimg').style.display='none'; try{a.pause();}catch(_){} clearTimeout(window._mbT); clearTimeout(window._mEnd); lastAct=performance.now(); }

// hyper-drive nacelles — real engine photos that ignite on/off
const engUrls=[]; ['RS-25','Rocket engine','RD-180','Aerospike engine'].forEach(t=>wikiImg(t,460,u=>{ engUrls.push(u);
  ['L','R'].forEach(s=>{ const el=$('nac'+s),im=el&&el.querySelector('img'); if(im&&!im.getAttribute('src')) im.src=engUrls[0]; }); }));
const engState={L:false,R:false};
function setEngine(side,on){ engState[side]=on; const el=$('nac'+side); if(!el) return; el.classList.toggle('on',on); el.classList.toggle('off',!on);
  el.querySelector('.nstat').innerHTML=side+' &middot; '+(on?'FIRING':'STANDBY');
  if(on&&engUrls.length) el.querySelector('img').src=engUrls[Math.floor(Math.random()*engUrls.length)]; }
setInterval(()=>{ ['L','R'].forEach(s=>{ if(engState[s]&&engUrls.length) $('nac'+s).querySelector('img').src=engUrls[Math.floor(Math.random()*engUrls.length)]; }); }, 4500);

// ===== reactive viewscreen: switch a 'camera' to show the action =====
const VIEW={
 gear_down:['Landing gear','GEAR BAY CAM'], gear_up:['Landing gear','GEAR BAY CAM'],
 launchbar_extend:['Aircraft catapult','CATAPULT CAM'], launchbar_retract:['Aircraft catapult','CATAPULT CAM'],
 taxi_lights_on:['Landing light','APPROACH CAM'], taxi_lights_off:['Runway','RUNWAY CAM'],
 hook_bypass_carrier:['Tailhook','DECK CAM'], hook_bypass_field:['Arresting gear','DECK CAM'],
 probe_extend:['Aerial refueling','REFUEL CAM'], probe_neutral:['Aerial refueling','REFUEL CAM'], probe_emergency:['Aerial refueling','REFUEL CAM'],
 flap_half:['Flap (aeronautics)','WING CAM'], flap_full:['Flap (aeronautics)','WING CAM'], flap_auto:['Flap (aeronautics)','WING CAM'],
 antiskid_on:['Disc brake','BRAKE CAM'], antiskid_off:['Disc brake','BRAKE CAM'],
 master_engine:['Rocket engine','ENGINE CAM'], left_engine_on:['Rocket engine','PORT ENGINE CAM'], right_engine_on:['Rocket engine','STBD ENGINE CAM'],
 left_engine_off:['Rocket engine','PORT ENGINE CAM'], right_engine_off:['Rocket engine','STBD ENGINE CAM'], emergency_hyperjump_brake:['Rocket engine','ENGINE CAM'],
 hook_in_blackhole:['Black hole','ASTRO CAM'], hook_out_blackhole:['Black hole','ASTRO CAM'], hook_neutral:['Milky Way','ASTRO CAM'],
 wing_spread:['Grumman F-14 Tomcat','WING CAM'], wing_hold:['Grumman F-14 Tomcat','WING CAM'], wing_fold:['Grumman F-14 Tomcat','WING CAM'],
 jettison:['Multistage rocket','SEPARATION CAM'], jettison_alarm:['Multistage rocket','SEPARATION CAM'],
 seljett_left_fuel:['Drop tank','STORES CAM'], seljett_right_fuel:['Drop tank','STORES CAM'],
 seljett_escape_pod:['Apollo Command and Service Module','STORES CAM'], seljett_stores:['External fuel tank','STORES CAM']
};
let viewWant=0;
function showView(name){ const v=VIEW[name], screen=$('screen'), img=$('viewimg'), vid=$('viewvid'); const want=++viewWant;
  if(VIDEOS.has(name)){ img.style.opacity=0; vid.style.display='block'; vid.src='/videos/'+name+'.mp4'; vid.play().catch(()=>{});
    $('camname').textContent=(v&&v[1])||'CAM'; screen.classList.add('hasimg'); $('ship').style.display='none'; return; }
  vid.style.display='none'; vid.removeAttribute('src');
  if(STILLS.has(name)){ $('camname').textContent=(v&&v[1])||'CAM'; img.style.opacity=0; const u='/stills/'+name+'.jpg', pre=new Image(); pre.onload=()=>{ if(want!==viewWant) return; img.src=u; img.style.opacity=1; screen.classList.add('hasimg'); $('ship').style.display='none'; }; pre.src=u; return; }
  if(!v||!v[0]){ screen.classList.remove('hasimg'); img.style.opacity=0; $('ship').style.display=''; return; }
  $('camname').textContent=v[1];
  wikiImg(v[0],900,u=>{ if(want!==viewWant) return; const pre=new Image(); pre.onload=()=>{ if(want!==viewWant) return; img.src=u; img.style.opacity=1; screen.classList.add('hasimg'); $('ship').style.display='none'; }; pre.src=u; });
}
</script>
</body></html>
"""


def main():
    threading.Thread(target=input_loop, daemon=True).start()
    srv = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(f"[+] OPEN COCKPIT bridge live: http://<this-pi>:{PORT}  (Ctrl-C to quit)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nbye")
    finally:
        if _PTO["dev"]:
            try:
                _PTO["dev"].close()
            except Exception:
                pass


if __name__ == "__main__":
    main()
