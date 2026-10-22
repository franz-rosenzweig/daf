#!/bin/zsh
# Checks the test build on the phone plugged into this Mac (USB debugging on), against a
# sandbox Daf on the server, never the real one: it signs in there, opens a book and saves a
# link. On the server, tools/mac-sandbox.sh starts one and prints the three arguments.
#
#   ./check.sh BASE COOKIE TOKEN
#
# It builds and installs the test build ("Daf dev", xyz.tiresia.daf.debug, beside the real
# app) and runs check.py: the page in the app over DevTools, Back and the volume keys
# pressed on the phone (leave it unlocked), Share into Daf, the widget's numbers.
set -euo pipefail
cd "${0:A:h}"
ulimit -n 4096 2>/dev/null || true          # a long sync opens many connections through check.py's forwarder
(( $# >= 3 )) || { sed -n 2,11p $0 >&2; exit 2; }
export JAVA_HOME=${JAVA_HOME:-/Library/Java/JavaVirtualMachines/temurin-17.jdk/Contents/Home}
export ANDROID_HOME=${ANDROID_HOME:-$HOME/android-sdk}
ADB=$ANDROID_HOME/platform-tools/adb
$ADB get-state >/dev/null 2>&1 || { echo "no phone: plug it in and allow USB debugging" >&2; exit 2; }
./gradlew assembleDebug -q --console=plain
$ADB install -r app/build/outputs/apk/debug/app-debug.apk >/dev/null
python3 -I check.py "$@"
