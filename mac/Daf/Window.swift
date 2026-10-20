import AppKit
import WebKit

/// One Daf window: the live site (docs/SHELL.md), all page. The content runs to the
/// top edge under a see-through title bar, and the traffic lights sit in the sidebar's
/// top row, level with the views' top bars; shell.js moves "Daf" over for them.
@MainActor
final class DafWindowController: NSWindowController, NSWindowDelegate, WKNavigationDelegate, WKUIDelegate {
    /// Every open window, the way the menus find the one in front.
    static private(set) var all: [DafWindowController] = []

    /// The views' top bars (`.top` in style.css): the traffic lights sit in their middle.
    static let barHeight: CGFloat = 56
    /// Where the close button starts.
    static let lightsInset: CGFloat = 20
    static let minSize = NSSize(width: 900, height: 600)
    private static let autosaveName = "Daf Window"

    private(set) var webView: ShellWebView!
    private let services = ShellServices()
    private let downloads = Downloads()
    private lazy var windowMessages = WindowMessages(owner: self)
    private var urlWatch: NSKeyValueObservation?
    /// The manga reader asked for full screen (dafShell.fullscreen): leaving the reader leaves it too.
    var fullScreenForReader = false
    /// A window of its own for one of Daf's files (the PDF as printed), not the app.
    let start: URL?

    /// The window in front, or any window.
    static var front: DafWindowController? {
        for window in [NSApp.keyWindow, NSApp.mainWindow] {
            if let c = window?.windowController as? DafWindowController { return c }
        }
        return all.first
    }

    /// Opens a window, on a page of the app ("#review") or one of Daf's own addresses.
    @discardableResult
    static func open(_ route: String? = nil, url: URL? = nil) -> DafWindowController {
        let c = DafWindowController(start: url ?? route.map { Server.url($0) })
        all.append(c)
        c.showWindow(nil)
        c.layoutTrafficLights()
        return c
    }

    /// The window in front goes to a page of the app, or a new window opens there.
    static func show(_ route: String) {
        if let c = front, c.start == nil, let w = c.window {
            NSApp.bringForward()
            w.makeKeyAndOrderFront(nil)
            c.command("go:" + String(route.dropFirst()))
        } else {
            NSApp.bringForward()
            open(route)
        }
    }

    init(start: URL?) {
        self.start = start.flatMap { $0.path.isEmpty || $0.path == "/" ? nil : $0 }
        let window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 1280, height: 840),
                              styleMask: [.titled, .closable, .miniaturizable, .resizable, .fullSizeContentView],
                              backing: .buffered, defer: false)
        window.title = "Daf"
        window.titleVisibility = .hidden
        window.titlebarAppearsTransparent = true
        window.tabbingMode = .disallowed
        window.minSize = Self.minSize
        window.collectionBehavior.insert(.fullScreenPrimary)
        window.isReleasedWhenClosed = false
        super.init(window: window)
        window.delegate = self
        // The first window remembers its frame; another opens cascaded from the one in front.
        if !Self.all.contains(where: { $0.window?.frameAutosaveName == Self.autosaveName }) && self.start == nil {
            if !window.setFrameUsingName(Self.autosaveName) { window.center() }
            window.setFrameAutosaveName(Self.autosaveName)
        } else if let front = Self.front?.window {
            window.setFrame(front.frame, display: false)
            window.setFrameTopLeftPoint(window.cascadeTopLeft(from: NSPoint(x: front.frame.minX, y: front.frame.maxY)))
        } else {
            window.center()
        }
        makeWebView(start ?? (LocalCopy.active && LocalCopy.ready ? LocalCopy.origin : Server.base))
        NotificationCenter.default.addObserver(forName: .dafBaseChanged, object: nil, queue: .main) { [weak self] _ in
            MainActor.assumeIsolated {
                guard let self else { return }
                if self.start != nil { self.close() } else { self.webView.load(URLRequest(url: Server.base)) }
            }
        }
    }

    @available(*, unavailable)
    required init?(coder: NSCoder) { fatalError("not from a nib") }

    // MARK: the page

    private func makeWebView(_ url: URL) {
        let config = WKWebViewConfiguration()
        config.websiteDataStore = .default()      // the sign-in cookie and the page's settings outlive a launch
        config.applicationNameForUserAgent = UserAgent.name
        config.preferences.isElementFullscreenEnabled = true
        let content = config.userContentController
        // the app's own copy of Daf, for when the server can't be reached (LocalCopy)
        config.setURLSchemeHandler(AppScheme.shared, forURLScheme: LocalCopy.scheme)
        Self.scripts(content)
        content.addScriptMessageHandler(services, contentWorld: .page, name: "dafShell")
        content.add(windowMessages, contentWorld: .page, name: "dafWindow")

        let view = ShellWebView(frame: window?.contentView?.bounds ?? .zero, configuration: config)
        view.autoresizingMask = [.width, .height]
        view.navigationDelegate = self
        view.uiDelegate = self
        view.allowsBackForwardNavigationGestures = true
        view.allowsMagnification = false
        if #available(macOS 13.3, *) { view.isInspectable = true }   // Safari → Develop, for a look inside the page
        services.webView = view
        downloads.webView = view
        webView = view
        window?.contentView = view
        // The menus' ticks and greys follow the page, hash changes included.
        urlWatch = view.observe(\.url, options: [.new]) { [weak self] _, _ in
            Task { @MainActor in
                Menus.refresh()
                self?.readerChanged()
            }
        }
        view.load(URLRequest(url: url, cachePolicy: .reloadIgnoringLocalCacheData))
    }

    /// In the manga reader (#mread/…) a sideways two-finger swipe turns its pages, so it isn't the
    /// window's Back gesture then; and the full screen the reader asked for ends with it.
    private func readerChanged() {
        let reading = webView.url?.fragment?.hasPrefix("mread/") ?? false
        webView.allowsBackForwardNavigationGestures = !reading
        if !reading, fullScreenForReader {
            fullScreenForReader = false
            if window?.styleMask.contains(.fullScreen) == true { window?.toggleFullScreen(nil) }
        }
    }

    /// Runs one of the page's commands (docs/SHELL.md §3). The answer is whether the page did something.
    func command(_ name: String, _ done: ((Bool) -> Void)? = nil) {
        webView.evaluateJavaScript("window.dafCommand ? window.dafCommand(\(Self.json(name))) : false") { result, _ in
            MainActor.assumeIsolated { done?((result as? Bool) ?? false) }
        }
    }

    /// Back: whatever is in front closes, or Daf goes back a page. A beep when there's nowhere to go.
    func back() {
        webView.evaluateJavaScript("window.dafBack ? window.dafBack() : null") { [weak self] result, _ in
            MainActor.assumeIsolated {
                if let went = result as? Bool { if !went { NSSound.beep() } }
                else if self?.webView.canGoBack == true { self?.webView.goBack() }   // a page without shell.js
                else { NSSound.beep() }
            }
        }
    }

    func reload() {
        if webView.url == nil || !(webView.url.map(Server.isOurs) ?? false) {
            webView.load(URLRequest(url: start ?? (LocalCopy.active && LocalCopy.ready ? LocalCopy.origin : Server.base), cachePolicy: .reloadIgnoringLocalCacheData))
        } else {
            webView.reloadFromOrigin()
        }
    }

    // MARK: with no network: the copy, and back

    /// The page's route: "#today", from either address.
    private var route: String? { webView.url?.fragment.map { "#" + $0 } }

    /// The page's own scripts: the shell's, and the copy's seed, read again each time so it carries
    /// the newest snapshot of the live page's settings.
    static func scripts(_ content: WKUserContentController) {
        content.removeAllUserScripts()
        content.addUserScript(WKUserScript(source: ShellServices.script, injectionTime: .atDocumentStart, forMainFrameOnly: true, in: .page))
        content.addUserScript(WKUserScript(source: LocalCopy.seedScript, injectionTime: .atDocumentStart, forMainFrameOnly: true, in: .page))
    }

    /// Daf didn't answer: the same page from the app's own copy.
    func goLocal() {
        guard LocalCopy.ready, start == nil else { return }
        LocalCopy.active = true
        Self.scripts(webView.configuration.userContentController)
        webView.load(URLRequest(url: LocalCopy.url(route)))
        Reconnect.shared.watch()
    }

    /// Daf answers again: what was done on the copy goes first (its outbox), then the live site.
    func goLive() async {
        guard webView.url?.scheme == LocalCopy.scheme else { return }
        let r = route
        _ = try? await webView.evaluateJavaScript("window.DafCore && DafCore.outbox && DafCore.outbox.flush && DafCore.outbox.flush(), 1")
        for _ in 0..<30 {
            let left = (try? await webView.evaluateJavaScript("JSON.parse(localStorage.getItem('daf.outbox') || '[]').length")) as? Int ?? 0
            if left == 0 { break }
            try? await Task.sleep(nanoseconds: 1_000_000_000)
        }
        webView.load(URLRequest(url: r.map { Server.url($0) } ?? Server.base, cachePolicy: .reloadIgnoringLocalCacheData))
    }

    /// The live page's settings, kept for the copy (not its outbox).
    func snapshotSettings() {
        guard webView.url.map({ $0.scheme != LocalCopy.scheme && Server.isOurs($0) }) ?? false else { return }
        webView.evaluateJavaScript(LocalCopy.snapshotJS) { result, _ in
            if let json = result as? String { MainActor.assumeIsolated { LocalCopy.keepSnapshot(json) } }
        }
    }

    static func json(_ value: Any) -> String {
        guard let data = try? JSONSerialization.data(withJSONObject: [value]), let s = String(data: data, encoding: .utf8) else { return "null" }
        return String(s.dropFirst().dropLast())
    }

    // MARK: the traffic lights

    /// Close, minimize and zoom in the middle of a 56-point strip rather than the
    /// 28-point title bar they come in. AppKit puts them back whenever it lays the
    /// title bar out again, so this runs after each of those.
    func layoutTrafficLights() {
        guard let window, !window.styleMask.contains(.fullScreen),
              let close = window.standardWindowButton(.closeButton),
              let titlebar = close.superview, let container = titlebar.superview else { return }
        let height = Self.barHeight
        var frame = container.frame
        frame.size.height = height
        frame.origin.y = window.frame.height - height
        container.frame = frame
        titlebar.frame = container.bounds
        let buttons: [NSWindow.ButtonType] = [.closeButton, .miniaturizeButton, .zoomButton]
        for (i, kind) in buttons.enumerated() {
            guard let b = window.standardWindowButton(kind) else { continue }
            b.setFrameOrigin(NSPoint(x: Self.lightsInset + CGFloat(i) * 20, y: ((height - b.frame.height) / 2).rounded()))
        }
    }

    func windowDidResize(_ notification: Notification) { layoutTrafficLights() }
    func windowDidEndLiveResize(_ notification: Notification) { layoutTrafficLights() }
    func windowDidBecomeKey(_ notification: Notification) { layoutTrafficLights(); Menus.refresh() }
    func windowDidResignKey(_ notification: Notification) { layoutTrafficLights() }
    func windowDidExitFullScreen(_ notification: Notification) { layoutTrafficLights(); tellFullScreen() }
    func windowDidEnterFullScreen(_ notification: Notification) { tellFullScreen() }

    /// In full screen the traffic lights are gone, and the page need not leave room for them.
    private func tellFullScreen() {
        let on = window?.styleMask.contains(.fullScreen) ?? false
        webView.evaluateJavaScript("document.documentElement.classList.toggle('shell-fullscreen', \(on))", completionHandler: nil)
    }

    func windowWillClose(_ notification: Notification) {
        urlWatch = nil
        webView.stopLoading()
        // a closed window must stop counting: the page goes with it
        webView.loadHTMLString("", baseURL: nil)
        webView.configuration.userContentController.removeAllScriptMessageHandlers()
        Self.all.removeAll { $0 === self }
    }

    // MARK: moving the window from the page's bars

    /// A press on an empty part of a top bar (shell.js) moves the window, as a title
    /// bar would; two zoom it, or do what System Settings says a double-click does.
    fileprivate func windowMessage(_ what: String) {
        guard let window, let down = webView.lastMouseDown,
              ProcessInfo.processInfo.systemUptime - down.timestamp < 1 else { return }
        switch what {
        case "drag":
            guard NSEvent.pressedMouseButtons & 1 == 1 else { return }
            window.performDrag(with: down)
            // The drag took the release, which WebKit is still waiting for.
            if NSEvent.pressedMouseButtons & 1 == 0,
               let up = NSEvent.mouseEvent(with: .leftMouseUp, location: window.mouseLocationOutsideOfEventStream,
                                           modifierFlags: [], timestamp: ProcessInfo.processInfo.systemUptime,
                                           windowNumber: window.windowNumber, context: nil, eventNumber: 0,
                                           clickCount: 1, pressure: 0) {
                webView.mouseUp(with: up)
            }
        case "zoom":
            switch UserDefaults(suiteName: UserDefaults.globalDomain)?.string(forKey: "AppleActionOnDoubleClick") ?? "Maximize" {
            case "Minimize": window.miniaturize(nil)
            case "None": break
            default: window.zoom(nil)
            }
        default: break
        }
    }

    // MARK: WKNavigationDelegate

    /// Only Daf in the window. Anything else opens where it belongs: the browser, Mail, Obsidian.
    func webView(_ webView: WKWebView, decidePolicyFor action: WKNavigationAction,
                 decisionHandler: @escaping @MainActor @Sendable (WKNavigationActionPolicy) -> Void) {
        guard let target = action.request.url else { return decisionHandler(.allow) }
        if action.shouldPerformDownload { return decisionHandler(.download) }
        // frames inside the page (the book reader's, a video) are the page's business
        guard action.targetFrame?.isMainFrame ?? true else { return decisionHandler(.allow) }
        if Server.isOurs(target) || ["about", "blob", "data"].contains(target.scheme?.lowercased() ?? "") {
            return decisionHandler(.allow)
        }
        Outside.open(target)
        decisionHandler(.cancel)
    }

    /// An export or a book file: to the save panel, by the name the server gives it.
    func webView(_ webView: WKWebView, decidePolicyFor response: WKNavigationResponse,
                 decisionHandler: @escaping @MainActor @Sendable (WKNavigationResponsePolicy) -> Void) {
        if response.isForMainFrame, let code = (response.response as? HTTPURLResponse)?.statusCode,
           [502, 503, 504].contains(code) || (520...530).contains(code), LocalCopy.ready, start == nil, webView.url?.scheme != LocalCopy.scheme {
            decisionHandler(.cancel)
            return goLocal()
        }
        let disposition = (response.response as? HTTPURLResponse)?.value(forHTTPHeaderField: "Content-Disposition") ?? ""
        if response.isForMainFrame && (!response.canShowMIMEType || disposition.lowercased().hasPrefix("attachment")) {
            return decisionHandler(.download)
        }
        decisionHandler(.allow)
    }

    func webView(_ webView: WKWebView, navigationAction: WKNavigationAction, didBecome download: WKDownload) {
        download.delegate = downloads
    }

    func webView(_ webView: WKWebView, navigationResponse: WKNavigationResponse, didBecome download: WKDownload) {
        download.delegate = downloads
    }

    func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
        if window?.styleMask.contains(.fullScreen) == true { tellFullScreen() }
        Menus.refresh()
        if webView.url?.scheme != LocalCopy.scheme {
            if LocalCopy.active { LocalCopy.active = false }
            snapshotSettings()
            LocalCopy.keepUpToDate()
        }
    }

    func webView(_ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!, withError error: Error) {
        let e = error as NSError
        if e.domain == NSURLErrorDomain && e.code == NSURLErrorCancelled { return }
        if e.domain == "WebKitErrorDomain" && e.code == 102 { return }   // a download, not a page
        NSLog("Daf: could not open \(Server.base.absoluteString): \(error.localizedDescription)")
        // Daf didn't answer: its own copy on this Mac, when there is one
        if LocalCopy.ready && start == nil && webView.url?.scheme != LocalCopy.scheme { return goLocal() }
        webView.loadHTMLString(Self.unreachable(error.localizedDescription), baseURL: nil)
    }

    func webViewWebContentProcessDidTerminate(_ webView: WKWebView) {
        NSLog("Daf: the page's process ended; loading it again")
        webView.load(URLRequest(url: start ?? Server.base))
    }

    private static func unreachable(_ why: String) -> String {
        let esc = { (s: String) in s.replacingOccurrences(of: "&", with: "&amp;").replacingOccurrences(of: "<", with: "&lt;") }
        let base = Server.base.absoluteString
        return """
        <!doctype html><meta charset="utf-8"><style>
        body{font:13px -apple-system,sans-serif;color:#555;display:flex;height:100vh;margin:0;align-items:center;justify-content:center;text-align:center}
        @media (prefers-color-scheme:dark){body{color:#bbb;background:#16171a}}
        h1{font-size:17px;font-weight:600;color:inherit}a{color:inherit}
        </style><div><h1>Daf didn't answer</h1><p>\(esc(base)): \(esc(why))</p>
        <p><a href="\(esc(base))/">Try again</a> · or change the address in Daf → Settings.</p></div>
        """
    }

    // MARK: WKUIDelegate

    /// window.open and target=_blank: Daf's own files in a window of their own, anything else outside.
    func webView(_ webView: WKWebView, createWebViewWith configuration: WKWebViewConfiguration,
                 for action: WKNavigationAction, windowFeatures: WKWindowFeatures) -> WKWebView? {
        if let target = action.request.url {
            if Server.isOurs(target) { Self.open(url: target) } else { Outside.open(target) }
        }
        return nil
    }

    func webView(_ webView: WKWebView, runJavaScriptAlertPanelWithMessage message: String,
                 initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping @MainActor @Sendable () -> Void) {
        let alert = NSAlert()
        alert.messageText = message
        alert.addButton(withTitle: "OK")
        present(alert) { _ in completionHandler() }
    }

    func webView(_ webView: WKWebView, runJavaScriptConfirmPanelWithMessage message: String,
                 initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping @MainActor @Sendable (Bool) -> Void) {
        let alert = NSAlert()
        alert.messageText = message
        alert.addButton(withTitle: "OK")
        alert.addButton(withTitle: "Cancel")
        present(alert) { completionHandler($0 == .alertFirstButtonReturn) }
    }

    func webView(_ webView: WKWebView, runJavaScriptTextInputPanelWithPrompt prompt: String, defaultText: String?,
                 initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping @MainActor @Sendable (String?) -> Void) {
        let alert = NSAlert()
        alert.messageText = prompt
        let field = NSTextField(frame: NSRect(x: 0, y: 0, width: 300, height: 24))
        field.stringValue = defaultText ?? ""
        alert.accessoryView = field
        alert.addButton(withTitle: "OK")
        alert.addButton(withTitle: "Cancel")
        alert.window.initialFirstResponder = field
        present(alert) { completionHandler($0 == .alertFirstButtonReturn ? field.stringValue : nil) }
    }

    /// <input type=file>: a photo of a paper page, say.
    func webView(_ webView: WKWebView, runOpenPanelWith parameters: WKOpenPanelParameters,
                 initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping @MainActor @Sendable ([URL]?) -> Void) {
        let panel = NSOpenPanel()
        panel.canChooseFiles = true
        panel.canChooseDirectories = parameters.allowsDirectories
        panel.allowsMultipleSelection = parameters.allowsMultipleSelection
        if let window { panel.beginSheetModal(for: window) { completionHandler($0 == .OK ? panel.urls : nil) } } else {
            completionHandler(panel.runModal() == .OK ? panel.urls : nil)
        }
    }

    private func present(_ alert: NSAlert, _ done: @escaping @MainActor (NSApplication.ModalResponse) -> Void) {
        if let window, window.isVisible, window.attachedSheet == nil {
            alert.beginSheetModal(for: window) { r in MainActor.assumeIsolated { done(r) } }
        } else {
            done(alert.runModal())
        }
    }
}

/// The page's bars tell the window where a press landed (shell.js). Its own object, held
/// weakly, so the configuration, which keeps its handlers, doesn't keep the window alive.
final class WindowMessages: NSObject, WKScriptMessageHandler {
    weak var owner: DafWindowController?
    init(owner: DafWindowController) { self.owner = owner }

    /// What the pages have asked, for the self-test.
    @MainActor static var received: [String] = []

    func userContentController(_ controller: WKUserContentController, didReceive message: WKScriptMessage) {
        guard let what = message.body as? String else { return }
        MainActor.assumeIsolated {
            Self.received.append(what)
            owner?.windowMessage(what)
        }
    }
}

/// The page hears every key first, so Daf's own keys (h, n, ⌘K…) work as in a browser;
/// a key it leaves alone goes on to the menus. Chords with ⌃ go to the menus first.
final class ShellWebView: WKWebView {
    /// The last press, for a drag the page asks for a moment later.
    private(set) var lastMouseDown: NSEvent?

    override func mouseDown(with event: NSEvent) {
        lastMouseDown = event
        super.mouseDown(with: event)
    }

    override func performKeyEquivalent(with event: NSEvent) -> Bool {
        if event.modifierFlags.contains(.control), NSApp.mainMenu?.performKeyEquivalent(with: event) == true {
            return true
        }
        return super.performKeyEquivalent(with: event)
    }

    /// Keys go to the page from the moment its window opens.
    override func viewDidMoveToWindow() {
        super.viewDidMoveToWindow()
        window?.makeFirstResponder(self)
    }

    /// The page's presses are the page's; moving the window is asked for.
    override var mouseDownCanMoveWindow: Bool { false }
}

/// The browser, Mail or Obsidian, for anything that isn't Daf. The self-test only notes it.
@MainActor
enum Outside {
    static var opened: [URL] = []
    static var testing: Bool { UserDefaults.standard.string(forKey: "SelfTestOut") != nil }
    static let schemes: Set<String> = ["http", "https", "mailto", "obsidian"]

    @discardableResult
    static func open(_ url: URL) -> Bool {
        guard schemes.contains(url.scheme?.lowercased() ?? "") else { return false }
        opened.append(url)
        if !testing { NSWorkspace.shared.open(url) }
        return true
    }
}
