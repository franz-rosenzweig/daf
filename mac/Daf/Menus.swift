import AppKit

/// The menu bar. Each Daf item calls the page's own command (`window.dafCommand`,
/// docs/SHELL.md §3) in the window in front; what's greyed comes from `window.dafState()`,
/// asked when a menu opens and whenever the page moves.
///
/// The page hears a key before the menus do (ShellWebView), so its own keys run there.
/// The Reader items show the page's single-letter keys (h, n, b) for the eye only:
/// DafMainMenu never fires an item from a key without ⌘ or ⌃, so typing an "h" in a
/// note stays an "h".
@MainActor
enum Menus {
    /// What the page in front said last (dafState).
    static var state: [String: Any] = [:]
    /// The page's commands run from the menus, for the self-test.
    static var ran: [String] = []

    static func can(_ key: String) -> Bool {
        guard let can = state["can"] as? [String: Any] else { return false }
        return (can[key] as? Bool) ?? ((can[key] as? NSNumber)?.boolValue ?? false)
    }

    /// Asks the page in front for its state, and shows it in whatever menu is open.
    static func refresh(_ menu: NSMenu? = nil) {
        guard let web = DafWindowController.front?.webView else { state = [:]; return }
        web.evaluateJavaScript("window.dafState ? window.dafState() : null") { result, _ in
            MainActor.assumeIsolated {
                state = (result as? [String: Any]) ?? [:]
                showKeys()
                menu?.update()
            }
        }
    }

    /// The Reader items show the keys bound now in the page's Preferences → Keyboard (dafState().keys):
    /// "J" is Shift-J, the arrows show as arrows, and an action with no key shows none.
    static func showKeys() {
        guard let keys = state["keys"] as? [String: Any], !keys.isEmpty, let bar = NSApp.mainMenu else { return }
        for top in bar.items {
            for case let p as PageItem in top.submenu?.items ?? [] where p.pageKey {
                guard let k = keys[p.command] as? String else { continue }
                switch k {
                case "ArrowRight": (p.keyEquivalent, p.keyEquivalentModifierMask) = (Menus.right, [])
                case "ArrowLeft": (p.keyEquivalent, p.keyEquivalentModifierMask) = (Menus.left, [])
                case let c where c.count == 1 && c != " ":
                    (p.keyEquivalent, p.keyEquivalentModifierMask) = (c.lowercased(), c == c.lowercased() ? [] : [.shift])
                default: (p.keyEquivalent, p.keyEquivalentModifierMask) = ("", [])
                }
            }
        }
    }

    static func build() -> NSMenu {
        let bar = DafMainMenu()
        for m in [appMenu(), fileMenu(), editMenu(), viewMenu(), goMenu(), readerMenu()] {
            m.delegate = Opening.shared
            bar.addItem(submenu(m))
        }
        let window = NSMenu(title: "Window")
        window.addItem(withTitle: "Minimize", action: #selector(NSWindow.performMiniaturize(_:)), keyEquivalent: "m")
        window.addItem(withTitle: "Zoom", action: #selector(NSWindow.performZoom(_:)), keyEquivalent: "")
        window.addItem(.separator())
        window.addItem(withTitle: "Bring All to Front", action: #selector(NSApplication.arrangeInFront(_:)), keyEquivalent: "")
        bar.addItem(submenu(window))
        NSApp.windowsMenu = window
        let help = NSMenu(title: "Help")
        help.addItem(item("Keyboard Shortcuts", "keys"))
        help.addItem(item("Send Feedback…", "feedback"))
        bar.addItem(submenu(help))
        NSApp.helpMenu = help
        return bar
    }

    // MARK: the menus

    private static func appMenu() -> NSMenu {
        let m = NSMenu(title: "Daf")
        m.addItem(withTitle: "About Daf", action: #selector(NSApplication.orderFrontStandardAboutPanel(_:)), keyEquivalent: "")
        m.addItem(.separator())
        m.addItem(shell("Settings…", #selector(MenuTarget.settings(_:)), ","))
        m.addItem(item("Reading Goals…", "go:prefs/goals"))
        m.addItem(shell("Safari Extension…", #selector(MenuTarget.safari(_:))))
        m.addItem(.separator())
        let services = NSMenuItem(title: "Services", action: nil, keyEquivalent: "")
        services.submenu = NSMenu(title: "Services")
        NSApp.servicesMenu = services.submenu
        m.addItem(services)
        m.addItem(.separator())
        m.addItem(withTitle: "Hide Daf", action: #selector(NSApplication.hide(_:)), keyEquivalent: "h")
        let others = m.addItem(withTitle: "Hide Others", action: #selector(NSApplication.hideOtherApplications(_:)), keyEquivalent: "h")
        others.keyEquivalentModifierMask = [.command, .option]
        m.addItem(withTitle: "Show All", action: #selector(NSApplication.unhideAllApplications(_:)), keyEquivalent: "")
        m.addItem(.separator())
        m.addItem(withTitle: "Quit Daf", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")
        return m
    }

    private static func fileMenu() -> NSMenu {
        let m = NSMenu(title: "File")
        m.addItem(shell("New Window", #selector(MenuTarget.newWindow(_:)), "n"))
        m.addItem(.separator())
        m.addItem(item("Add to Daf…", "add", "o"))
        m.addItem(shell("Save a Link…", #selector(MenuTarget.saveLink(_:)), "s", [.command, .shift]))
        m.addItem(item("Log Paper Minutes…", "paper", "p", [.command, .shift]))
        m.addItem(item("Export Highlights…", "export", "e", [.command, .shift]))
        m.addItem(.separator())
        m.addItem(withTitle: "Close Window", action: #selector(NSWindow.performClose(_:)), keyEquivalent: "w")
        return m
    }

    private static func editMenu() -> NSMenu {
        let m = NSMenu(title: "Edit")
        m.addItem(withTitle: "Undo", action: Selector(("undo:")), keyEquivalent: "z")
        let redo = m.addItem(withTitle: "Redo", action: Selector(("redo:")), keyEquivalent: "z")
        redo.keyEquivalentModifierMask = [.command, .shift]
        m.addItem(.separator())
        m.addItem(withTitle: "Cut", action: #selector(NSText.cut(_:)), keyEquivalent: "x")
        m.addItem(withTitle: "Copy", action: #selector(NSText.copy(_:)), keyEquivalent: "c")
        m.addItem(withTitle: "Paste", action: #selector(NSText.paste(_:)), keyEquivalent: "v")
        let plain = m.addItem(withTitle: "Paste and Match Style", action: #selector(NSTextView.pasteAsPlainText(_:)), keyEquivalent: "v")
        plain.keyEquivalentModifierMask = [.command, .option, .shift]
        m.addItem(withTitle: "Select All", action: #selector(NSText.selectAll(_:)), keyEquivalent: "a")
        return m
    }

    private static func viewMenu() -> NSMenu {
        let m = NSMenu(title: "View")
        for (i, (title, route)) in [("Today", "today"), ("Review", "review"), ("Library", "library"), ("Feed", "feed"),
                                    ("Highlights", "highlights"), ("Books", "books"), ("Stats", "stats")].enumerated() {
            m.addItem(item(title, "go:" + route, String(i + 1)))
        }
        m.addItem(item("Shortlist", "go:library/starred"))
        m.addItem(item("Torah", "go:torah"))
        m.addItem(item("Paper Pages", "go:paper"))
        m.addItem(.separator())
        m.addItem(item("Hide Sidebar", "sidebar", "s", [.command, .control]))
        m.addItem(item("Contents", "toc"))
        m.addItem(item("Side Panel", "panel", "]", []))
        m.addItem(item("Typography", "aa"))
        m.addItem(.separator())
        m.addItem(shell("Actual Size", #selector(MenuTarget.zoomReset(_:)), "0"))
        m.addItem(shell("Zoom In", #selector(MenuTarget.zoomIn(_:)), "+"))
        let plainZoom = shell("Zoom In", #selector(MenuTarget.zoomIn(_:)), "=")    // ⌘= as well, without the Shift
        plainZoom.isHidden = true
        plainZoom.allowsKeyEquivalentWhenHidden = true
        m.addItem(plainZoom)
        m.addItem(shell("Zoom Out", #selector(MenuTarget.zoomOut(_:)), "-"))
        m.addItem(.separator())
        m.addItem(shell("Reload Page", #selector(MenuTarget.reload(_:)), "r"))
        m.addItem(withTitle: "Enter Full Screen", action: #selector(NSWindow.toggleFullScreen(_:)), keyEquivalent: "f")
            .keyEquivalentModifierMask = [.command, .control]
        return m
    }

    private static func goMenu() -> NSMenu {
        let m = NSMenu(title: "Go")
        m.addItem(shell("Back", #selector(MenuTarget.back(_:)), "["))
        m.addItem(shell("Forward", #selector(MenuTarget.forward(_:)), "]"))
        m.addItem(.separator())
        m.addItem(item("Search", "search", "k"))
        return m
    }

    private static func readerMenu() -> NSMenu {
        let m = NSMenu(title: "Reader")
        m.addItem(item("Highlight", "highlight", "h", []))
        m.addItem(item("Highlight with a Note", "note", "n", []))
        m.addItem(item("Bookmark This Page", "bookmark", "b", []))
        m.addItem(item("Listen", "listen"))
        m.addItem(item("Add to Shortlist", "star", "f", []))
        m.addItem(item("Tags…", "tag", "t", []))
        m.addItem(item("Delete", "delete", "d", []))
        m.addItem(.separator())
        m.addItem(item("Next", "next", Menus.right, []))
        m.addItem(item("Previous", "prev", Menus.left, []))
        m.addItem(item("Next in the List", "nextdoc", "j", [.shift]))
        m.addItem(item("Previous in the List", "prevdoc", "k", [.shift]))
        return m
    }

    static let left = "\u{F702}", right = "\u{F703}"

    // MARK: making items

    private static func submenu(_ menu: NSMenu) -> NSMenuItem {
        let item = NSMenuItem(title: menu.title, action: nil, keyEquivalent: "")
        item.submenu = menu
        return item
    }

    /// An item that runs one of the page's commands.
    private static func item(_ title: String, _ command: String, _ key: String = "",
                             _ mods: NSEvent.ModifierFlags = [.command]) -> NSMenuItem {
        let i = PageItem(title: title, action: #selector(MenuTarget.page(_:)), keyEquivalent: key)
        i.command = command
        i.keyEquivalentModifierMask = key.isEmpty ? [] : mods
        i.pageKey = !key.isEmpty && !mods.contains(.command) && !mods.contains(.control)
        i.target = MenuTarget.shared
        return i
    }

    /// An item the shell answers itself.
    private static func shell(_ title: String, _ action: Selector, _ key: String = "",
                              _ mods: NSEvent.ModifierFlags = [.command]) -> NSMenuItem {
        let i = NSMenuItem(title: title, action: action, keyEquivalent: key)
        i.keyEquivalentModifierMask = key.isEmpty ? [] : mods
        i.target = MenuTarget.shared
        return i
    }
}

/// The main menu. A key without ⌘ or ⌃ never fires an item: it's the page's (Reader's
/// h, n, b, f, ⇧J, ⇧K, the arrows), and the items only show it.
final class DafMainMenu: NSMenu {
    override func performKeyEquivalent(with event: NSEvent) -> Bool {
        if event.modifierFlags.intersection([.command, .control]).isEmpty { return false }
        return super.performKeyEquivalent(with: event)
    }
}

/// An item that runs a page command (docs/SHELL.md §3).
final class PageItem: NSMenuItem {
    var command = ""
    /// Shows one of the page's own keys (no ⌘ or ⌃), which follows Preferences → Keyboard.
    var pageKey = false
}

/// Menus ask the page for its state as they open.
@MainActor
final class Opening: NSObject, NSMenuDelegate {
    static let shared = Opening()
    nonisolated func menuWillOpen(_ menu: NSMenu) {
        MainActor.assumeIsolated { Menus.refresh(menu) }
    }
}

@MainActor
final class MenuTarget: NSObject, NSMenuItemValidation {
    static let shared = MenuTarget()

    private var front: DafWindowController? { DafWindowController.front }

    @objc func page(_ sender: NSMenuItem) {
        guard let command = (sender as? PageItem)?.command else { return }
        Menus.ran.append(command)
        guard let c = front, c.start == nil else {
            // no window on the app: open one, and go there if it's a place
            NSApp.bringForward()
            DafWindowController.open(command.hasPrefix("go:") ? "#" + String(command.dropFirst(3)) : nil)
            return
        }
        if command == "back" { return c.back() }
        c.command(command) { did in if !did { NSSound.beep() } }
    }

    @objc func back(_ sender: Any?) { Menus.ran.append("back"); front?.back() }
    @objc func forward(_ sender: Any?) { if front?.webView.canGoForward == true { front?.webView.goForward() } else { NSSound.beep() } }
    @objc func reload(_ sender: Any?) { front?.reload() }
    @objc func newWindow(_ sender: Any?) { NSApp.bringForward(); DafWindowController.open() }
    @objc func settings(_ sender: Any?) { SettingsWindow.show() }
    @objc func safari(_ sender: Any?) { SafariExtension.setUp() }
    @objc func saveLink(_ sender: Any?) { SaveLink.ask() }
    @objc func zoomIn(_ sender: Any?) { zoom(by: 1.1) }
    @objc func zoomOut(_ sender: Any?) { zoom(by: 1 / 1.1) }
    @objc func zoomReset(_ sender: Any?) { front?.webView.pageZoom = 1 }

    private func zoom(by f: CGFloat) {
        guard let web = front?.webView else { return }
        web.pageZoom = min(3, max(0.5, (web.pageZoom * f * 100).rounded() / 100))
    }

    func validateMenuItem(_ item: NSMenuItem) -> Bool {
        if let p = item as? PageItem {
            if p.command == "sidebar" {
                p.title = (Menus.state["sidebar"] as? Bool) == false ? "Show Sidebar" : "Hide Sidebar"
                return front?.start == nil
            }
            switch p.command {
            case "toc", "panel", "aa", "listen", "highlight", "note", "bookmark", "next", "prev", "nextdoc", "prevdoc", "star", "tag", "delete":
                if p.command == "listen" { p.title = Menus.state["listening"] as? Bool == true ? "Stop Listening" : "Listen" }
                if p.command == "star" { p.title = Menus.state["starred"] as? Bool == true ? "Remove from Shortlist" : "Add to Shortlist" }
                return front?.start == nil && Menus.can(p.command)
            default:
                return true
            }
        }
        switch item.action {
        case #selector(back(_:)), #selector(forward(_:)), #selector(reload(_:)),
             #selector(zoomIn(_:)), #selector(zoomOut(_:)), #selector(zoomReset(_:)):
            return front != nil
        default:
            return true
        }
    }
}
