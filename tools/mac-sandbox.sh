#!/bin/sh
# A throwaway Daf for the Mac self-test (mac/selftest.sh): a copy of the state on the
# tailnet, with a sign-in cookie and a device token made for it. Prints the arguments.
#
#   tools/mac-sandbox.sh [PORT]      # default 8441; stop it with: kill $(cat $DIR/server.pid)
#
# Nothing it does reaches the real Daf: the state is a copy, the vault an empty folder,
# and no sync thread runs. FreshRSS is a dead address unless DAF_FRESHRSS_URL names a stand-in,
# so marking an item seen in the sandbox never marks it read in the real FreshRSS. Komga likewise:
# a copy of its settings pointing nowhere unless DAF_KOMGA_CONF names one (a read-only stand-in),
# so a manga read in the sandbox never moves the real progress.
set -eu
PORT=${1:-8441}
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DIR=$(mktemp -d -t daf-mac-sandbox.XXXXXX)
cp -a /srv/docker/daf "$DIR/state"
mkdir -p "$DIR/vault"
cd "$ROOT"
PY="$ROOT/.venv/bin/python"; [ -x "$PY" ] || PY=/srv/dev/daf/.venv/bin/python   # a worktree has no venv of its own
if [ -z "${DAF_KOMGA_CONF:-}" ]; then
    DAF_KOMGA_CONF="$DIR/komga.json"
    "$PY" -c 'import json, sys; c = json.load(open("/srv/docker/manga-import/komga.json")); c["url"] = "http://127.0.0.1:9"; json.dump(c, open(sys.argv[1], "w"))' "$DAF_KOMGA_CONF" 2>/dev/null || true
    chmod 600 "$DAF_KOMGA_CONF" 2>/dev/null || true
fi
DAF_KOMGA_CONF="$DAF_KOMGA_CONF" DAF_FRESHRSS_URL="${DAF_FRESHRSS_URL:-http://127.0.0.1:9}" DAF_STATE="$DIR/state" DAF_VAULT="$DIR/vault" nohup "$PY" -m uvicorn daf.app:app \
    --host 100.91.202.11 --port "$PORT" >"$DIR/server.log" 2>&1 &
echo $! >"$DIR/server.pid"
COOKIE=$(DAF_STATE="$DIR/state" "$PY" -c 'from daf import auth; print(auth.make_cookie())')
TOKEN=$(DAF_STATE="$DIR/state" DAF_VAULT="$DIR/vault" "$PY" -m daf.cli kindle-token selftest)
for _ in 1 2 3 4 5 6 7 8 9 10; do curl -sf "http://100.91.202.11:$PORT/api/health" >/dev/null && break; sleep 0.5; done
echo "sandbox in $DIR (pid $(cat "$DIR/server.pid"))" >&2
echo "http://100.91.202.11:$PORT $COOKIE $TOKEN"
