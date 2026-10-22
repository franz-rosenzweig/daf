#!/bin/zsh
# Tests the shell from inside: builds Daf with SelfTest/ linked in, as its own app
# (xyz.tiresia.daf.selftest, so Daf itself can stay open and keeps its settings), and runs
# it against a Daf server:
#
#   ./selftest.sh BASE COOKIE TOKEN             # every section
#   ./selftest.sh BASE COOKIE TOKEN keys,book   # some: load window keys menus article book hidden outside downloads share menubar save settings offline
#
# BASE must be a sandbox copy of Daf, never the real one: the test opens a book and an
# article, saves a link and makes a device token. On the server, tools/mac-sandbox.sh starts
# one and prints the three arguments. It takes the keyboard for about a minute: leave the
# Mac alone meanwhile. Pictures of each window land in build/selftest/out.
set -euo pipefail
cd "${0:A:h}"
(( $# >= 3 )) || { sed -n 2,13p $0 >&2; exit 2; }

OUT=build/selftest
mkdir -p $OUT && rm -rf $OUT/out && mkdir -p $OUT/out/saved
clang -c -target "$(uname -m)-apple-macos13.0" SelfTest/hook.c -o $OUT/hook.o
# quiet unless it fails
DAF_OUT=$OUT DAF_BUNDLE_ID=xyz.tiresia.daf.selftest DAF_EXTRA="SelfTest/SelfTest.swift $OUT/hook.o" \
    ./build.sh >$OUT/build.log 2>&1 || { cat $OUT/build.log; exit 1; }

# a value starting with "-" would read as another setting's name: tokens can, so both get a prefix
ARGS=(-SelfTestBase "$1" -SelfTestCookie "c:$2" -SelfTestToken "t:$3")
(( $# >= 4 )) && ARGS+=(-SelfTestOnly "$4")
BIN=$PWD/$OUT/Daf.app/Contents/MacOS/Daf
( sleep 600; pkill -f "$BIN" ) 2>/dev/null &           # a stuck run ends after ten minutes (offline downloads a manga volume)
watchdog=$!
open -W -n --stdout $OUT/out/log.txt --stderr $OUT/out/log.txt $OUT/Daf.app \
    --args -SelfTestOut "$PWD/$OUT/out" -SelfTestSaveDir "$PWD/$OUT/out/saved" -ApplePersistenceIgnoreState YES "${ARGS[@]}"
kill $watchdog 2>/dev/null || true
# the test build's own extensions would show as a second Daf in Safari and the share menu
pluginkit -m -v 2>/dev/null | awk -F'\t' '/tiresia\.daf\.selftest/ {print $NF}' | while read -r p; do pluginkit -r "$p"; done
grep -E "^(SELFTEST|PASS|FAIL|SKIP|INFO|MENU)" $OUT/out/log.txt
grep -q "SELFTEST passed" $OUT/out/log.txt
