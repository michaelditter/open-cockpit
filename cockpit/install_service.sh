#!/usr/bin/env bash
# Installs a systemd service so the panel sounds start automatically on boot.
# Run from inside the open-cockpit-sounds folder:  bash install_service.sh
set -e

APP_DIR="$(cd "$(dirname "$0")" && pwd)"
USER_NAME="$(whoami)"
PYTHON="$APP_DIR/.venv/bin/python"

if [ ! -x "$PYTHON" ]; then
  echo "Virtualenv not found. Run 'bash install.sh' first."
  exit 1
fi

SERVICE=/etc/systemd/system/open-cockpit-sounds.service
echo "==> Writing $SERVICE"
sudo tee "$SERVICE" >/dev/null <<EOF
[Unit]
Description=Open Cockpit Panel Sounds (headless, sounds-only)
After=sound.target

[Service]
Type=simple
User=$USER_NAME
WorkingDirectory=$APP_DIR
ExecStart=$PYTHON $APP_DIR/panel_sounds.py
Restart=on-failure
RestartSec=2
# Audio + input device access for a normal user
SupplementaryGroups=audio input

[Install]
WantedBy=multi-user.target
EOF

echo "==> Enabling + starting service"
sudo systemctl daemon-reload
sudo systemctl enable open-cockpit-sounds.service
sudo systemctl restart open-cockpit-sounds.service
echo ""
echo "Service installed. Useful commands:"
echo "  systemctl status open-cockpit-sounds       # is it running?"
echo "  journalctl -u open-cockpit-sounds -f        # live logs"
echo "  sudo systemctl restart open-cockpit-sounds  # after editing mapping.json"
