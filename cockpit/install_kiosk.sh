#!/usr/bin/env bash
# Make the Pi boot straight into the Open Cockpit bridge, full-screen.
# Run once on the Pi:  bash ~/open-cockpit/cockpit/install_kiosk.sh
set -e
APP="$HOME/open-cockpit/cockpit"
chmod +x "$APP/start_cockpit.sh"

echo "==> Boot to desktop w/ autologin + no screen blanking (sudo)..."
sudo raspi-config nonint do_boot_behaviour B4 || true   # desktop autologin
sudo raspi-config nonint do_blanking 1 || true          # disable screen blank

LINE="$APP/start_cockpit.sh &"
if command -v labwc >/dev/null 2>&1 || [ -e "$HOME/.config/labwc" ]; then
  mkdir -p "$HOME/.config/labwc"
  touch "$HOME/.config/labwc/autostart"
  grep -qF "start_cockpit.sh" "$HOME/.config/labwc/autostart" || echo "$LINE" >> "$HOME/.config/labwc/autostart"
  chmod +x "$HOME/.config/labwc/autostart"
  echo "==> autostart hooked into labwc"
elif [ -f "$HOME/.config/wayfire.ini" ] || command -v wayfire >/dev/null 2>&1; then
  python3 - "$APP" <<'PY'
import configparser, os, sys
app = sys.argv[1]
p = os.path.expanduser('~/.config/wayfire.ini')
c = configparser.ConfigParser(); c.optionxform = str
if os.path.exists(p): c.read(p)
if not c.has_section('autostart'): c.add_section('autostart')
c.set('autostart', 'cockpit', app + '/start_cockpit.sh')
with open(p, 'w') as f: c.write(f)
print("==> autostart hooked into wayfire")
PY
else
  mkdir -p "$HOME/.config/autostart"
  cat > "$HOME/.config/autostart/cockpit.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Open Cockpit
Exec=$APP/start_cockpit.sh
X-GNOME-Autostart-enabled=true
EOF
  echo "==> autostart hooked into XDG (~/.config/autostart)"
fi

echo ""
echo "KIOSK INSTALLED. Reboot to test it:  sudo reboot"
echo "(After reboot the Pi will come up straight into the full-screen cockpit.)"
