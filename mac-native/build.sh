#!/bin/zsh
# Builds "Daf Native.app" (xyz.tiresia.daf.native) beside Daf's web-view app, which it doesn't touch.
#   ./build.sh                 # build/Daf Native.app, signed ad hoc
#   DAF_SIGN="Apple Development: …" ./build.sh    # signed with that identity instead
set -euo pipefail
cd "${0:A:h}"
VERSION=0.1.0
APP="build/Daf Native.app"
swift build -c release --product DafNative 2>&1 | grep -v '^\[' || true
BIN=$(swift build -c release --product DafNative --show-bin-path)/DafNative
[[ -x $BIN ]] || { echo "the build didn't make $BIN" >&2; exit 1; }
rm -rf "$APP"; mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
cp "$BIN" "$APP/Contents/MacOS/DafNative"
# Daf's icon (mac/AppIcon.iconset, the same Tree D)
if [[ -d ../mac/AppIcon.iconset ]]; then iconutil -c icns ../mac/AppIcon.iconset -o "$APP/Contents/Resources/AppIcon.icns"; fi
cat > "$APP/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>CFBundleIdentifier</key><string>xyz.tiresia.daf.native</string>
  <key>CFBundleName</key><string>Daf Native</string>
  <key>CFBundleDisplayName</key><string>Daf Native</string>
  <key>CFBundleExecutable</key><string>DafNative</string>
  <key>CFBundleIconFile</key><string>AppIcon</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>$VERSION</string>
  <key>CFBundleVersion</key><string>1</string>
  <key>LSMinimumSystemVersion</key><string>26.0</string>
  <key>LSApplicationCategoryType</key><string>public.app-category.productivity</string>
  <key>NSHighResolutionCapable</key><true/>
  <key>NSPrincipalClass</key><string>NSApplication</string>
  <key>NSAppTransportSecurity</key><dict><key>NSAllowsArbitraryLoads</key><true/></dict>
  <key>NSLocalNetworkUsageDescription</key><string>Daf Native connects to your Daf server when its address is on your home network or tailnet.</string>
</dict></plist>
PLIST
codesign --force --sign "${DAF_SIGN:--}" "$APP" >/dev/null 2>&1 || codesign --force --sign - "$APP"
echo "built $APP ($VERSION)"
