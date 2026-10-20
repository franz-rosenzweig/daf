import AppKit

/// Daf for macOS: the live site (docs/SHELL.md) in a window made to look like Readwise
/// Reader's, with Daf's menus, today's minutes in the menu bar, and Save to Daf in the
/// share menu. Everything a person reads is the page; this adds what a page can't do.
@main
@MainActor
final class AppDelegate: NSObject, NSApplicationDelegate {
    static func main() {
        let app = NSApplication.shared
        let delegate = AppDelegate()
        app.delegate = delegate
        app.run()
    }

    /// Opened to save a link (daf://save from the share menu): no window for that.
    private var openedForLink = false

    func applicationWillFinishLaunching(_ notification: Notification) {
        NSApp.mainMenu = Menus.build()
    }

    func applicationDidFinishLaunching(_ notification: Notification) {
        FeedNews.shared.install()
        Today.shared.start()
        MenuBar.shared.install()
        // At login Daf starts in the menu bar only; otherwise a window, unless all it was
        // asked to do was save a link (the URL arrives a moment after launch).
        let launch = NSAppleEventManager.shared().currentAppleEvent
        let atLogin = launch?.eventID == AEEventID(kAEOpenApplication)
            && launch?.paramDescriptor(forKeyword: AEKeyword(keyAEPropData))?.enumCodeValue == OSType(keyAELaunchedAsLogInItem)
        if atLogin || UserDefaults.standard.string(forKey: "SelfTestOut") != nil && UserDefaults.standard.bool(forKey: "SelfTestNoWindow") { return }
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.3) {
            MainActor.assumeIsolated {
                if !self.openedForLink && DafWindowController.all.isEmpty {
                    DafWindowController.open()
                    NSApp.bringForward()
                }
            }
        }
    }

    func application(_ application: NSApplication, open urls: [URL]) {
        for url in urls where url.scheme == "daf" {
            if url.host == "save" {
                openedForLink = true
                SaveLink.handle(url)
            } else if url.host == "connect-safari" {
                // the Safari extension asks for its token (SafariExtension); no window for that
                openedForLink = true
                SafariExtension.handle(url)
            } else if url.host == "go", let route = url.pathComponents.dropFirst().first {
                // daf://go/review, for Shortcuts and the like
                DafWindowController.show("#" + route)
            }
        }
    }

    /// Closing the last window leaves Daf in the menu bar; the Dock icon brings a window back.
    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { false }

    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool {
        if !DafWindowController.all.contains(where: { $0.window?.isVisible == true && $0.start == nil }) {
            DafWindowController.open()
        }
        return true
    }

    func applicationSupportsSecureRestorableState(_ app: NSApplication) -> Bool { true }
}

extension NSApplication {
    /// Comes to the front. From macOS 14 the system has the last word, as it should.
    func bringForward() {
        if #available(macOS 14, *) { activate() } else { activate(ignoringOtherApps: true) }
    }
}
