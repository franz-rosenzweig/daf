// swift-tools-version:6.2
// Daf for the Mac, native (Nathan, 20 Oct: "do it", the native trial beside the web-view app).
// SwiftUI and AppKit over Daf's own API, the one the page uses; books, manga and videos stay the
// page's, in a web view inside the native window. Built into an .app by build.sh.
import PackageDescription

let package = Package(
    name: "DafNative",
    platforms: [.macOS(.v26)],
    targets: [
        .executableTarget(name: "DafNative", path: "Sources/DafNative")
    ],
    swiftLanguageModes: [.v5]
)
