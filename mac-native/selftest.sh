#!/bin/zsh
# Tests Daf from inside, against a sandbox Daf (never the real one), as its own app ("Daf Test",
# xyz.tiresia.daf.selftest, so Daf's settings, sign-in and keychain are never touched), and keeps a
# picture of each step:
#   ./selftest.sh BASE COOKIE [TOKEN]       → build/selftest/log.txt and *.png
set -euo pipefail
cd "${0:A:h}"
(( $# >= 2 )) || { sed -n 2,5p $0 >&2; exit 2; }
DAF_TEST=1 ./build.sh >/dev/null || { echo "SELFTEST: the build failed" >&2; exit 1; }
APP="build/test/Daf Test.app"
OUT=$PWD/build/selftest; rm -rf $OUT; mkdir -p $OUT
ARGS=(-SelfTestBase "$1" -SelfTestCookie "c:$2")
(( $# >= 3 )) && ARGS+=(-SelfTestToken "t:$3")
( sleep 480; pkill -f "Daf Test.app/Contents/MacOS/Daf" ) 2>/dev/null & watchdog=$!
open -W -n "$APP" --args -SelfTestOut "$OUT" -ApplePersistenceIgnoreState YES "${ARGS[@]}"
kill $watchdog 2>/dev/null || true
# what the test build kept: its sign-in, its settings, its files
rm -rf ~/Library/HTTPStorages/xyz.tiresia.daf.selftest ~/Library/HTTPStorages/xyz.tiresia.daf.selftest.binarycookies \
    "$HOME/Library/Application Support/xyz.tiresia.daf.selftest"
defaults delete xyz.tiresia.daf.selftest >/dev/null 2>&1 || true
cat $OUT/log.txt
grep -q "SELFTEST passed" $OUT/log.txt
