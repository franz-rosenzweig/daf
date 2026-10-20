#!/bin/sh
# Install or update the Daf plugin on the Kindle (KOReader, SSH over Tailscale on :2222).
# Safe to rerun: it replaces the plugin folder, and creates settings/daf.lua only once
# (after that the plugin owns that file). Restart KOReader afterwards to load it.
set -eu
DIR="$(cd "$(dirname "$0")/.." && pwd)"
KINDLE="root@100.66.33.78"
SSH="ssh -i $HOME/.ssh/kindle_koreader -p 2222 -o ConnectTimeout=8 -o BatchMode=yes -o StrictHostKeyChecking=no $KINDLE"
TOKEN_FILE=/srv/docker/daf/kindle-token

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
    ["url"] = "http://100.91.202.11:8440",
    ["token"] = "$TOKEN",
    ["tz_offset"] = -25200,
    ["sleep_screen"] = true,
}
EOF

$SSH 'cd /mnt/us/koreader && for f in plugins/daf.koplugin/*.lua settings/daf.lua; do ./luajit -e "assert(loadfile(\"$f\"))" || exit 1; done && echo "Daf plugin installed and checked. Restart KOReader to load it."'
