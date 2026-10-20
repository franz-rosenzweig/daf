#!/bin/zsh
# Tests the native app from inside, against a sandbox Daf (never the real one), and keeps a picture
# of each step:   ./selftest.sh BASE COOKIE        → build/selftest/log.txt and *.png
set -euo pipefail
cd "${0:A:h}"
(( $# >= 2 )) || { sed -n 2,3p $0 >&2; exit 2; }
./build.sh >/dev/null
OUT=$PWD/build/selftest; rm -rf $OUT; mkdir -p $OUT
( sleep 300; pkill -f "Daf Native.app/Contents/MacOS/DafNative" ) 2>/dev/null & watchdog=$!
open -W -n "build/Daf Native.app" --args -SelfTestBase "$1" -SelfTestCookie "c:$2" -SelfTestOut "$OUT" -ApplePersistenceIgnoreState YES
kill $watchdog 2>/dev/null || true
cat $OUT/log.txt
grep -q "SELFTEST passed" $OUT/log.txt
