#!/usr/bin/env bash
# Launch the Open Cockpit bridge (sound + screen + LEDs) and a
# full-screen kiosk browser. Called automatically at login by install_kiosk.sh.
APP="$HOME/open-cockpit/cockpit"
LOG="$APP/cockpit.log"
cd "$APP" || exit 1

port_open() { (exec 3<>/dev/tcp/127.0.0.1/8080) 2>/dev/null; }

# Start the cockpit server if it isn't already serving on 8080
if ! port_open; then
  "$APP/.venv/bin/python" "$APP/panel_web.py" >>"$LOG" 2>&1 &
fi

# Wait (up to ~20s) for it to come up
for _ in $(seq 1 40); do port_open && break; sleep 0.5; done

# Launch Chromium full-screen, pointed at the cockpit
CHROME="$(command -v chromium-browser || command -v chromium)"
[ -z "$CHROME" ] && { echo "chromium not found" >>"$LOG"; exit 1; }
exec "$CHROME" --kiosk --noerrordialogs --disable-infobars \
  --disable-session-crashed-bubble --disable-features=Translate \
  --password-store=basic --check-for-update-interval=31536000 \
  --autoplay-policy=no-user-gesture-required \
  --start-fullscreen "http://localhost:8080"
