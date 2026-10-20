#!/bin/zsh
# Builds Daf for the Mac, the native app, with Save to Daf (the share extension) and Daf for Safari
# inside, both from ../mac (the extensions are the web-view Daf's own, unchanged):
#   ./build.sh                  build/Daf.app (xyz.tiresia.daf), signed with the Apple Development
#                               identity when there is one (the Safari extension's app group needs its team)
#   DAF_SIGN=- ./build.sh       the same, signed ad hoc
#   DAF_TEST=1 ./build.sh       "build/test/Daf Test.app" (xyz.tiresia.daf.selftest), ad hoc, without the
#                               extensions and on its own daf-selftest:// links: what selftest.sh runs,
#                               so a test never touches Daf's settings, sign-in or keychain
set -euo pipefail
cd "${0:A:h}"
VERSION=0.3.1
BUILD=14
if [[ -n ${DAF_TEST:-} ]]; then
    NAME="Daf Test"; ID=xyz.tiresia.daf.selftest; SCHEME=daf-selftest; OUT=build/test; EXTENSIONS=
else
    NAME=Daf; ID=xyz.tiresia.daf; SCHEME=daf; OUT=build; EXTENSIONS=1
fi
APP="$OUT/$NAME.app"
MACOS=26.0
SDK=$(xcrun --show-sdk-path)
TARGET="$(uname -m)-apple-macos$MACOS"

mkdir -p $OUT
if ! swift build -c release --product DafNative > $OUT/swift-build.log 2>&1; then     # a failed build stops here, never an old binary
    grep -E 'error' -A3 $OUT/swift-build.log >&2; exit 1
fi
BIN=$(swift build -c release --product DafNative --show-bin-path)/DafNative
[[ -x $BIN ]] || { echo "the build didn't make $BIN" >&2; exit 1; }
rm -f $OUT/swift-build.log
rm -rf "$APP"; mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
cp "$BIN" "$APP/Contents/MacOS/Daf"
[[ -d ../mac/AppIcon.iconset ]] && iconutil -c icns ../mac/AppIcon.iconset -o "$APP/Contents/Resources/AppIcon.icns"

# Who signs: an Apple Development identity if there is one; its team names the app group the
# Safari extension shares with the app. Ad hoc there's no team, so no app group and no Safari token.
if [[ -n ${DAF_TEST:-} ]]; then IDENTITY=-; else
    IDENTITY=${DAF_SIGN:-$(security find-identity -v -p codesigning | sed -n 's/^ *[0-9]*) \([0-9A-F]*\) "Apple Development.*/\1/p' | head -1)}
fi
TEAM=""
if [[ -n $IDENTITY && $IDENTITY != - ]]; then
    TEAM=$(security find-certificate -a -Z -p 2>/dev/null | awk -v h="$IDENTITY" '/^SHA-1 hash:/ { on = ($3 == h) } on' \
        | openssl x509 -noout -subject 2>/dev/null | sed -n 's/.*OU *= *\([A-Z0-9]*\).*/\1/p')
fi
GROUP=${TEAM:+$TEAM.xyz.tiresia.daf}

cat > "$APP/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>CFBundleIdentifier</key><string>$ID</string>
  <key>CFBundleName</key><string>$NAME</string>
  <key>CFBundleDisplayName</key><string>$NAME</string>
  <key>CFBundleExecutable</key><string>Daf</string>
  <key>CFBundleIconFile</key><string>AppIcon</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>$VERSION</string>
  <key>CFBundleVersion</key><string>$BUILD</string>
  <key>LSMinimumSystemVersion</key><string>$MACOS</string>
  <key>LSApplicationCategoryType</key><string>public.app-category.books</string>
  <key>NSHighResolutionCapable</key><true/>
  <key>NSPrincipalClass</key><string>NSApplication</string>
  <key>NSHumanReadableCopyright</key><string></string>
  <key>CFBundleURLTypes</key><array><dict>
    <key>CFBundleURLName</key><string>$ID</string>
    <key>CFBundleURLSchemes</key><array><string>$SCHEME</string></array>
  </dict></array>
  <key>DafAppGroup</key><string>$GROUP</string>
  <key>NSAppTransportSecurity</key><dict><key>NSAllowsArbitraryLoads</key><true/></dict>
  <key>NSLocalNetworkUsageDescription</key><string>Daf connects to your Daf server when its address is on your home network or tailnet.</string>
</dict></plist>
PLIST

ents() {   # app-sandbox (true|false), app group (yes|no) → a file
    local f=$OUT/$RANDOM.entitlements
    { echo '<?xml version="1.0" encoding="UTF-8"?><!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd"><plist version="1.0"><dict>'
      echo "<key>com.apple.security.app-sandbox</key><$1/>"
      [[ $2 == yes && -n $GROUP ]] && echo "<key>com.apple.security.application-groups</key><array><string>$GROUP</string></array>"
      echo '</dict></plist>'; } > $f
    echo $f
}

if [[ -n $EXTENSIONS ]]; then
    SHARE="$APP/Contents/PlugIns/DafShare.appex" SAFARI="$APP/Contents/PlugIns/DafSafari.appex"
    mkdir -p "$SHARE/Contents/MacOS" "$SAFARI/Contents/MacOS" "$SAFARI/Contents/Resources"
    swiftc -O -wmo -sdk $SDK -target $TARGET -swift-version 5 -parse-as-library -application-extension \
        -module-name DafShare ../mac/DafShare/*.swift -Xlinker -e -Xlinker _NSExtensionMain -o "$SHARE/Contents/MacOS/DafShare"
    swiftc -O -wmo -sdk $SDK -target $TARGET -swift-version 5 -parse-as-library -application-extension \
        -module-name DafSafari ../mac/DafSafari/*.swift -framework SafariServices -Xlinker -e -Xlinker _NSExtensionMain \
        -o "$SAFARI/Contents/MacOS/DafSafari"
    ../extension/build.sh >/dev/null                 # the web extension's Safari build (extension/dist/safari)
    cp -R ../extension/dist/safari/ "$SAFARI/Contents/Resources/"
    appex() {   # plist path, executable, id, display name, NSExtension dict
        cat > "$1" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>CFBundleIdentifier</key><string>$3</string>
  <key>CFBundleName</key><string>$2</string>
  <key>CFBundleDisplayName</key><string>$4</string>
  <key>CFBundleExecutable</key><string>$2</string>
  <key>CFBundlePackageType</key><string>XPC!</string>
  <key>CFBundleShortVersionString</key><string>$VERSION</string>
  <key>CFBundleVersion</key><string>$BUILD</string>
  <key>CFBundleInfoDictionaryVersion</key><string>6.0</string>
  <key>LSMinimumSystemVersion</key><string>$MACOS</string>
  <key>NSHumanReadableCopyright</key><string></string>
  <key>DafAppGroup</key><string>$GROUP</string>
  <key>NSExtension</key>$5
</dict></plist>
PLIST
    }
    appex "$SHARE/Contents/Info.plist" DafShare $ID.share "Save to Daf" '<dict>
    <key>NSExtensionPointIdentifier</key><string>com.apple.share-services</string>
    <key>NSExtensionPrincipalClass</key><string>ShareViewController</string>
    <key>NSExtensionAttributes</key><dict><key>NSExtensionActivationRule</key><dict>
      <key>NSExtensionActivationSupportsWebURLWithMaxCount</key><integer>1</integer>
      <key>NSExtensionActivationSupportsText</key><true/>
    </dict></dict></dict>'
    appex "$SAFARI/Contents/Info.plist" DafSafari $ID.safari Daf '<dict>
    <key>NSExtensionPointIdentifier</key><string>com.apple.Safari.web-extension</string>
    <key>NSExtensionPrincipalClass</key><string>SafariWebExtensionHandler</string></dict>'
    # the extensions first, then the app around them
    codesign --force --options runtime --entitlements $(ents true no) --sign "${IDENTITY:--}" "$SHARE"
    codesign --force --options runtime --entitlements $(ents true yes) --sign "${IDENTITY:--}" "$SAFARI"
fi
codesign --force --options runtime --entitlements $(ents false yes) --sign "${IDENTITY:--}" "$APP"
rm -f $OUT/*.entitlements
[[ -n $IDENTITY && $IDENTITY != - ]] || [[ -n ${DAF_TEST:-} ]] || echo "note: signed ad hoc; Safari won't load the extension, and the keychain asks again"
echo "built $APP ($VERSION${TEAM:+, team $TEAM})"
