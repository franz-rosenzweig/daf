#!/bin/zsh
# Builds Daf.app, with Save to Daf (its share extension) and Daf for Safari inside, using the
# Command Line Tools alone, no Xcode needed:
#   ./build.sh && cp -R build/Daf.app /Applications/ && open /Applications/Daf.app
# The settings and Info.plist keys come from project.yml, the same spec the Xcode project
# is generated from, so the two builds can't drift apart.
set -euo pipefail
cd "${0:A:h}"

command -v swiftc >/dev/null || { echo "no swiftc: run xcode-select --install" >&2; exit 1; }
command -v xcodegen >/dev/null || { echo "no xcodegen: run brew install xcodegen" >&2; exit 1; }

setting() { sed -n "s/^ *$1: *\"*\([^\"]*\)\"*$/\1/p" project.yml | head -1; }
BUNDLE_ID=${DAF_BUNDLE_ID:-$(setting PRODUCT_BUNDLE_IDENTIFIER)}   # selftest.sh builds as another app
VERSION=$(setting MARKETING_VERSION)
BUILD=$(setting CURRENT_PROJECT_VERSION)
MACOS=$(setting macOS)
SDK=$(xcrun --show-sdk-path)
TARGET="$(uname -m)-apple-macos$MACOS"

OUT=${DAF_OUT:-build}                  # selftest.sh builds its copy into build/selftest
APP=$OUT/Daf.app
APPEX=$APP/Contents/PlugIns/DafShare.appex
SAFARI=$APP/Contents/PlugIns/DafSafari.appex

../extension/build.sh >/dev/null       # the web extension's Safari build (extension/dist/safari)
xcodegen generate --quiet              # writes the Info.plists, the entitlements and the Xcode project
rm -rf $APP && mkdir -p $APP/Contents/MacOS $APP/Contents/Resources $APPEX/Contents/MacOS $SAFARI/Contents/MacOS $SAFARI/Contents/Resources

# An Apple Development identity if there is one (Xcode makes it from your Apple ID), ad hoc
# otherwise, which is enough to run it on this Mac; its team names the app group the Safari
# extension shares with the app. Ad hoc there's no team, so no app group and no Safari token.
IDENTITY=${DAF_SIGN:-$(security find-identity -v -p codesigning | sed -n 's/^ *[0-9]*) \([0-9A-F]*\) "Apple Development.*/\1/p' | head -1)}
TEAM=""
if [[ -n $IDENTITY && $IDENTITY != - ]]; then
    TEAM=$(security find-certificate -a -Z -p 2>/dev/null | awk -v h="$IDENTITY" '/^SHA-1 hash:/ { on = ($3 == h) } on' \
        | openssl x509 -noout -subject 2>/dev/null | sed -n 's/.*OU *= *\([A-Z0-9]*\).*/\1/p')
fi

swiftc -O -wmo -sdk $SDK -target $TARGET -swift-version 5 -parse-as-library \
    -module-name Daf Daf/*.swift ${=DAF_EXTRA:-} -o $APP/Contents/MacOS/Daf

# The share extension: a small binary of its own, which starts in Foundation's NSExtensionMain.
swiftc -O -wmo -sdk $SDK -target $TARGET -swift-version 5 -parse-as-library -application-extension \
    -module-name DafShare DafShare/*.swift -Xlinker -e -Xlinker _NSExtensionMain -o $APPEX/Contents/MacOS/DafShare

# Daf in Safari: the native half, then the web extension itself (extension/, its Safari build).
swiftc -O -wmo -sdk $SDK -target $TARGET -swift-version 5 -parse-as-library -application-extension \
    -module-name DafSafari DafSafari/*.swift -framework SafariServices -Xlinker -e -Xlinker _NSExtensionMain \
    -o $SAFARI/Contents/MacOS/DafSafari
cp -R ../extension/dist/safari/ $SAFARI/Contents/Resources/

# Info.plist: XcodeGen's, with what Xcode would fill in.
plist() {   # source destination executable bundle-id package-type
    sed -e "s/\$(DEVELOPMENT_LANGUAGE)/en/" -e "s/\$(EXECUTABLE_NAME)/$3/" -e "s/\$(PRODUCT_NAME)/$3/" \
        -e "s/\$(PRODUCT_BUNDLE_IDENTIFIER)/$4/" -e "s/\$(MARKETING_VERSION)/$VERSION/" \
        -e "s/\$(CURRENT_PROJECT_VERSION)/$BUILD/" -e "s/\$(PRODUCT_BUNDLE_PACKAGE_TYPE)/$5/" \
        -e "s/\$(MACOSX_DEPLOYMENT_TARGET)/$MACOS/" -e "s/\$(TeamIdentifierPrefix)/${TEAM:+$TEAM.}/" $1 > $2
    [[ -n $TEAM ]] || ! plutil -extract DafAppGroup raw $2 >/dev/null 2>&1 || plutil -replace DafAppGroup -string "" $2
    plutil -replace CFBundlePackageType -string "$5" $2
    plutil -lint -s $2
    ! grep -q '\$(' $2 || { echo "$2 still has an unfilled \$(…):" >&2; grep '\$(' $2 >&2; exit 1; }
}
plist Daf/Info.plist $APP/Contents/Info.plist Daf $BUNDLE_ID APPL
plist DafShare/Info.plist $APPEX/Contents/Info.plist DafShare $BUNDLE_ID.share 'XPC!'
plist DafSafari/Info.plist $SAFARI/Contents/Info.plist DafSafari $BUNDLE_ID.safari 'XPC!'

# The entitlements, with the team in the app group's name, or without the app group ad hoc.
ents() {   # source → $OUT/<name>
    local out=$OUT/${1:t}
    sed -e "s/\$(TeamIdentifierPrefix)/${TEAM:+$TEAM.}/" $1 > $out
    [[ -n $TEAM ]] || /usr/libexec/PlistBuddy -c "Delete :com.apple.security.application-groups" $out 2>/dev/null || true
    echo $out
}

# The icon (design/icon/final): AppIcon.iconset has each size drawn at its own size, the
# 16 and 32 px from the simpler drawing. Without it, the sizes come from icon-1024.png.
if [[ -d AppIcon.iconset ]]; then
    iconutil -c icns AppIcon.iconset -o $APP/Contents/Resources/AppIcon.icns
else
    SET=$OUT/AppIcon.iconset && rm -rf $SET && mkdir -p $SET
    for s in 16 32 128 256 512; do
        sips -z $s $s icon-1024.png --out $SET/icon_${s}x${s}.png >/dev/null
        sips -z $((s * 2)) $((s * 2)) icon-1024.png --out $SET/icon_${s}x${s}@2x.png >/dev/null
    done
    iconutil -c icns $SET -o $APP/Contents/Resources/AppIcon.icns
    rm -rf $SET
fi
plutil -replace CFBundleIconFile -string AppIcon $APP/Contents/Info.plist

# The extensions first, then the app around them.
codesign --force --options runtime --entitlements DafShare/DafShare.entitlements --sign "${IDENTITY:--}" $APPEX
codesign --force --options runtime --entitlements $(ents DafSafari/DafSafari.entitlements) --sign "${IDENTITY:--}" $SAFARI
codesign --force --options runtime --entitlements $(ents Daf/Daf.entitlements) --sign "${IDENTITY:--}" $APP
[[ -n $IDENTITY && $IDENTITY != - ]] || echo "note: signed ad hoc; fine on this Mac, but the Keychain asks again after each build, and Safari won't load the extension"
echo "built $APP"
if [[ $OUT == build ]]; then
    echo "install it with: cp -R $APP /Applications/   (the share menu finds Save to Daf from there)"
fi
