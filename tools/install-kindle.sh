#!/bin/sh
# Install or update the Daf plugin on the Kindle (KOReader, SSH over Tailscale on :2222).
# Safe to rerun: it replaces the plugin folder, and creates settings/daf.lua only once
# (after that the plugin owns that file). Restart KOReader afterwards to load it.
set -eu
DIR="$(cd "$(dirname "$0")/.." && pwd)"
KINDLE="${DAF_KINDLE_SSH:?set DAF_KINDLE_SSH to the Kindle, e.g. root@<its address>}"
SSH="ssh -i $HOME/.ssh/kindle_koreader -p 2222 -o ConnectTimeout=8 -o BatchMode=yes -o StrictHostKeyChecking=no $KINDLE"
TOKEN_FILE="${DAF_STATE:-/srv/docker/daf}/kindle-token"
PY="$DIR/.venv/bin/python"; [ -x "$PY" ] || PY=python3
# The address the Kindle reaches Daf on (DAF_KINDLE_URL, else the last address Daf listens on), and the
# home time zone's offset in seconds, both from Daf's own config.
URL="${DAF_KINDLE_URL:-$(cd "$DIR" && "$PY" -c 'from daf import config; print(f"http://{config.HOSTS[-1]}:{config.PORT}")')}"
TZ_OFFSET="$(cd "$DIR" && "$PY" -c 'from datetime import datetime; from zoneinfo import ZoneInfo; from daf import config; z = ZoneInfo(config.load_settings().get("home_tz") or "UTC"); print(int(datetime.now(z).utcoffset().total_seconds()))')"

if ! $SSH true 2>/dev/null; then
  echo "The Kindle isn't reachable (asleep, or Wi-Fi off). Wake it, open KOReader, and run this again."
  exit 1
fi

if [ ! -s "$TOKEN_FILE" ]; then
  umask 077
  "$DIR/bin/daf" kindle-token kindle > "$TOKEN_FILE"
fi
TOKEN="$(cat "$TOKEN_FILE")"

tar -C "$DIR/kindle" -cf - daf.koplugin | $SSH 'rm -rf /mnt/us/koreader/plugins/daf.koplugin && tar -C /mnt/us/koreader/plugins -xf -'

$SSH "test -f /mnt/us/koreader/settings/daf.lua || cat > /mnt/us/koreader/settings/daf.lua" <<EOF
-- Daf plugin settings (created by tools/install-kindle.sh; the plugin keeps it up to date)
return {
    ["url"] = "$URL",
    ["token"] = "$TOKEN",
    ["tz_offset"] = $TZ_OFFSET,
    ["sleep_screen"] = true,
}
EOF

$SSH 'cd /mnt/us/koreader && for f in plugins/daf.koplugin/*.lua settings/daf.lua; do ./luajit -e "assert(loadfile(\"$f\"))" || exit 1; done && echo "Daf plugin installed and checked. Restart KOReader to load it."'
