import AppKit
import SwiftUI
import WebKit

/// Called from hook.c before main: start once the app has launched.
@_cdecl("selftest_install")
public func selftestInstall() {
    // The sandbox's address, in the app's own settings before anything reads them; a
    // command-line default would win over every later change (the offline check makes one).
    if let base = UserDefaults.standard.string(forKey: "SelfTestBase") {
        UserDefaults.standard.set(base, forKey: Server.baseKey)
    }
    NotificationCenter.default.addObserver(forName: NSApplication.didFinishLaunchingNotification,
                                           object: nil, queue: .main) { _ in
        Task { @MainActor in await SelfTest.run() }
    }
}

/// Drives the real app from inside, against a Daf server (a sandbox copy, never the real
/// one: it opens books, saves links and makes a device token). Keys are genuine NSEvents
/// posted to the app's own queue, so a key takes the path a keypress does: the page
/// first, then the menus. Pictures land in -SelfTestOut.
@MainActor
enum SelfTest {
    static var failures = 0
    static var skipped = 0
    static var outDir: URL { URL(fileURLWithPath: UserDefaults.standard.string(forKey: "SelfTestOut") ?? NSTemporaryDirectory()) }
    static var saveDir: URL { URL(fileURLWithPath: UserDefaults.standard.string(forKey: "SelfTestSaveDir") ?? NSTemporaryDirectory()) }

    /// -SelfTestOnly keys,menus,… runs some sections.
    static func wants(_ part: String) -> Bool {
        guard let only = UserDefaults.standard.string(forKey: "SelfTestOnly") else { return true }
        return only.split(separator: ",").contains { $0 == part }
    }

    static func run() async {
        try? FileManager.default.createDirectory(at: outDir, withIntermediateDirectories: true)
        try? FileManager.default.createDirectory(at: saveDir, withIntermediateDirectories: true)
        log("SELFTEST against \(Server.base.absoluteString), token \(Token.value == nil ? "none" : "given")")
        // the sandbox's sign-in, as the page's own form would have left it
        if let given = UserDefaults.standard.string(forKey: "SelfTestCookie"),
           case let cookie = given.hasPrefix("c:") ? String(given.dropFirst(2)) : given,
           let host = Server.base.host,
           let c = HTTPCookie(properties: [.name: "daf", .value: cookie, .domain: host, .path: "/"]) {
            await WKWebsiteDataStore.default().httpCookieStore.setCookie(c)
        }
        _ = await until(10) { !DafWindowController.all.isEmpty }
        guard let first = DafWindowController.all.first, let w = first.window else {
            check(false, "a window opened")
            return finish()
        }
        // the page again, now signed in; the old one answers until the new one replaces it
        _ = await until(10) { !first.webView.isLoading }
        await js(first.webView, "window.__selftestOld = 1, 1")
        first.reload()
        let ready = await until(25) { await js(first.webView, "!window.__selftestOld && window.dafState && dafState().signedIn && dafState().minutes !== null ? 1 : 0") == "1" }
        check(ready, "Daf opens, signed in", await js(first.webView, "document.body ? document.body.innerText.slice(0, 160) : ''"))
        guard ready else { return finish() }
        await front(w)
        await pause(1)
        capture(w, "01-today")
        dumpMenus()

        if wants("load") { await load(first) }
        if wants("window") { await window(first) }
        if wants("keys") { await keys(first) }
        if wants("menus") { await menus(first) }
        if wants("article") { await article(first) }
        if wants("book") { await book(first) }
        if wants("hidden") { await hidden(first) }
        if wants("outside") { await outside(first) }
        if wants("downloads") { await downloads(first) }
        if wants("share") { await share(first) }
        if wants("menubar") { await menubar(first) }
        if wants("save") { await save() }
        if wants("settings") { await settings() }
        if wants("offline") { await offline(first) }
        finish()
    }

    static func finish() {
        let note = skipped > 0 ? " (\(skipped) skipped: run again with the Mac left alone)" : ""
        log((failures == 0 ? "SELFTEST passed" : "SELFTEST \(failures) failed") + note)
        exit(failures == 0 ? 0 : 1)
    }

    static func route(_ web: WKWebView) async -> String { await js(web, "document.body.dataset.view || ''") }
    static func go(_ web: WKWebView, _ hash: String) async {
        await js(web, "location.hash = \(DafWindowController.json(hash)), 1")
        _ = await until(10) { await route(web) == hash.split(separator: "/").first.map(String.init) }
        await pause(0.4)
    }

    // MARK: sections

    /// The page knows it's in the shell, and the shell's calls are there before it runs.
    static func load(_ c: DafWindowController) async {
        let web = c.webView!
        let ua = await js(web, "navigator.userAgent")
        check(ua.hasSuffix(UserAgent.name), "the user agent names the shell", ua)
        check(await js(web, "document.documentElement.className").contains("shell-mac"), "shell.js marks the page shell-mac")
        check(await js(web, "['share','download','openExternal'].every(k => dafShell.can(k)) && !dafShell.can('notify') ? 1 : 0") == "1",
              "window.dafShell offers share, download and openExternal")
        check(await js(web, "typeof dafCommand === 'function' && typeof dafBack === 'function' ? 1 : 0") == "1", "the page answers dafCommand and dafBack")
        check(await js(web, "(() => { const b = document.querySelector('.brand'); return b.getBoundingClientRect().height === 56 && getComputedStyle(b.querySelector('b')).display === 'none' && !!document.getElementById('dafSideBtn'); })()") == "1",
              "the sidebar's top row is the traffic lights' and the sidebar button's")
        let sw = await js(web, "!navigator.serviceWorker ? 'no API' : navigator.serviceWorker.getRegistration().then(r => (navigator.serviceWorker.controller ? 'in control' : 'not in control') + ', registration ' + (r ? (r.active ? r.active.state : 'not active') : 'none')).catch(e => 'error ' + e.message)")
        log("INFO  service worker: \(sw), secure context \(await js(web, "window.isSecureContext"))")
    }

    static func window(_ c: DafWindowController) async {
        let w = c.window!
        check(w.styleMask.contains(.fullSizeContentView) && w.titlebarAppearsTransparent && w.titleVisibility == .hidden,
              "the page runs under a see-through title bar")
        check(w.minSize.width >= 900 && w.minSize.height >= 600, "the window is at least 900 by 600", "\(w.minSize)")
        check(w.frameAutosaveName == "Daf Window", "the window's frame is remembered")
        if let close = w.standardWindowButton(.closeButton), let zoom = w.standardWindowButton(.zoomButton) {
            let r = close.convert(close.bounds, to: nil), z = zoom.convert(zoom.bounds, to: nil)
            let fromTop = w.frame.height - r.midY
            check(abs(fromTop - DafWindowController.barHeight / 2) <= 1.5, "the traffic lights sit level with the top bars", "centre \(fromTop) pt from the top")
            let button = await js(c.webView, "document.getElementById('dafSideBtn').getBoundingClientRect().left")
            check(z.maxX < (Double(button) ?? 0), "the traffic lights end before the sidebar button", "\(z.maxX) and \(button)")
        }
        // a press on the top bar's empty part asks to move the window; on a button it doesn't
        WindowMessages.received = []
        await js(c.webView, "(() => { const t = document.querySelector('.top h1'), r = t.getBoundingClientRect(); t.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, button: 0, clientX: r.left + 2, clientY: r.top + 2, detail: 1 })); const b = document.querySelector('.top button'); if (b) b.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, button: 0, detail: 1 })); return 1; })()")
        _ = await until(2) { !WindowMessages.received.isEmpty }
        check(WindowMessages.received == ["drag"], "the top bar moves the window, its buttons don't", "\(WindowMessages.received)")

        // View → Hide Sidebar: the lights and the button move to the view's bar, and back
        let web = c.webView!
        Menus.refresh()
        await pause(0.4)
        perform("Hide Sidebar")
        check(await until(3) { await js(web, "document.documentElement.classList.contains('shell-noside') && getComputedStyle(document.querySelector('.side')).display === 'none' && document.getElementById('dafSideBtn').getBoundingClientRect().left === 86 && getComputedStyle(document.querySelector('.top')).paddingLeft === '132px'") == "1" },
              "View → Hide Sidebar: the traffic lights and the sidebar button start the view's bar")
        await pause(0.3)
        capture(w, "01c-nosidebar")
        Menus.refresh()
        await pause(0.4)
        if let item = find("Hide Sidebar", in: NSApp.mainMenu!) ?? find("Show Sidebar", in: NSApp.mainMenu!) {
            _ = MenuTarget.shared.validateMenuItem(item)
            check(item.title == "Show Sidebar", "and the item says Show Sidebar then", item.title)
        }
        await js(web, "document.getElementById('dafSideBtn').click(), 1")
        check(await until(3) { await js(web, "!document.documentElement.classList.contains('shell-noside') && getComputedStyle(document.querySelector('.side')).display !== 'none'") == "1" }, "the round button brings it back")

        // the sidebar's edge, dragged 60 px wider, then back
        let drag = { (dx: Int) in "(() => { const s = document.querySelector('.side').getBoundingClientRect(); const at = (t, x) => window.dispatchEvent(new PointerEvent(t, { bubbles: true, clientX: x, clientY: 300, pointerId: 1, button: 0, isPrimary: true })); at('pointermove', s.right - 1); at('pointerdown', s.right - 1); at('pointermove', s.right - 1 + \(dx)); at('pointerup', s.right - 1 + \(dx)); return Math.round(document.querySelector('.side').getBoundingClientRect().width); })()" }
        let before = Int(await js(web, "Math.round(document.querySelector('.side').getBoundingClientRect().width)")) ?? 0
        let wider = Int(await js(web, drag(60))) ?? 0
        check(wider == before + 60, "the sidebar's edge drags it wider", "\(before) → \(wider)")
        check(await js(web, "localStorage.getItem('daf.shell.sidew')") == String(wider), "and the width is kept")
        _ = await js(web, drag(-60))
    }

    /// Keys as the keyboard sends them: the page's own first, the menus' after.
    static func keys(_ c: DafWindowController) async {
        let web = c.webView!, w = c.window!
        guard await front(w) else { return skip("keys") }
        await go(web, "today")
        web.window?.makeFirstResponder(web)
        press("2", 19, .command)
        check(await until(4) { await route(web) == "review" }, "⌘2 goes to Review", await route(web))
        press("5", 23, .command)
        check(await until(4) { await route(web) == "highlights" }, "⌘5 goes to Highlights", await route(web))
        press("1", 18, .command)
        check(await until(4) { await route(web) == "today" }, "⌘1 goes back to Today", await route(web))
        await pause(0.5)

        let ran = Menus.ran.count
        press("k", 40, .command)
        _ = await until(3) { await js(web, "document.getElementById('palette').hidden ? 0 : 1") == "1" }
        await pause(0.4)
        check(await js(web, "document.getElementById('palette').hidden ? 0 : 1") == "1", "⌘K opens search, once")
        log("INFO  ⌘K reached the menu too: \(Menus.ran.count != ran) (harmless: Search leaves an open search alone)")
        press("[", 33, .command)
        check(await until(3) { await js(web, "document.getElementById('palette').hidden ? 1 : 0") == "1" }, "⌘[ closes search first")
        check(await route(web) == "today", "and stays on Today", await route(web))

        // a key without ⌘ is the page's alone, even when a menu item shows it
        let before = Menus.ran.count
        press("h", 4)
        press("]", 30)
        await pause(0.6)
        check(Menus.ran.count == before, "h and ] never fire the Reader and View items from the keyboard", "\(Menus.ran.suffix(3))")

        press("p", 35, [.command, .shift])
        check(await until(3) { await js(web, "!document.getElementById('modal').hidden && /Log paper minutes/.test(document.getElementById('modal').textContent) ? 1 : 0") == "1" },
              "⇧⌘P logs paper minutes")
        press("\u{1B}", 53)
        check(await until(3) { await js(web, "document.getElementById('modal').hidden ? 1 : 0") == "1" }, "Escape closes it")
        press("o", 31, .command)
        check(await until(3) { await js(web, "!document.getElementById('modal').hidden && /Add to Daf/.test(document.getElementById('modal').textContent) ? 1 : 0") == "1" },
              "⌘O opens Add to Daf")
        press("\u{1B}", 53)
        _ = await until(3) { await js(web, "document.getElementById('modal').hidden ? 1 : 0") == "1" }
        capture(w, "02-keys")
    }

    static func menus(_ c: DafWindowController) async {
        let web = c.webView!
        await go(web, "today")
        guard let stats = find("Stats", in: NSApp.mainMenu!), let m = stats.menu else { return check(false, "View → Stats is there") }
        m.performActionForItem(at: m.index(of: stats))
        check(await until(4) { await route(web) == "stats" }, "View → Stats", await route(web))
        if let back = find("Back", in: NSApp.mainMenu!), let bm = back.menu {
            bm.performActionForItem(at: bm.index(of: back))
            check(await until(4) { await route(web) == "today" }, "Go → Back", await route(web) + " " + (await js(web, "JSON.stringify(dafState())")))
        }
        Menus.refresh()
        await pause(0.5)
        if let hl = find("Highlight", in: NSApp.mainMenu!) {
            check(!MenuTarget.shared.validateMenuItem(hl), "Reader → Highlight is greyed on Today")
        }
        if let del = find("Delete", in: NSApp.mainMenu!) {
            check(!MenuTarget.shared.validateMenuItem(del), "Reader → Delete is greyed on Today")
        } else { check(false, "Reader → Delete is in the menu") }
        perform("Send Feedback…")
        check(await until(4) { await js(web, "!document.getElementById('modal').hidden && document.getElementById('fbtext') ? 1 : 0") == "1" }, "Help → Send Feedback… opens the feedback sheet")
        await js(web, "(document.querySelector('#modal [data-act=close]') || document.body).click(), 1")
    }

    /// An article from the Library: the Reader items come alive and reach the page.
    static func article(_ c: DafWindowController) async {
        let web = c.webView!
        let id = await js(web, "fetch('/api/docs?where=library&limit=20').then(r => r.json()).then(j => { const d = (j.items || j.docs || []).find(d => d.kind === 'article'); return d ? d.id : ''; })")
        guard !id.isEmpty, !id.hasPrefix("error") else { return check(false, "an article to open", id) }
        await js(web, "location.hash = 'read/' + encodeURIComponent(\(DafWindowController.json(id))), 1")
        check(await until(12) { await js(web, "document.getElementById('docbody') ? 1 : 0") == "1" }, "an article opens", id)
        await pause(1)
        Menus.refresh()
        await pause(0.5)
        for title in ["Highlight", "Side Panel", "Typography", "Listen"] {
            if let i = find(title, in: NSApp.mainMenu!) { check(MenuTarget.shared.validateMenuItem(i), "\(title) is there in an article") }
        }
        check(find("Bookmark This Page", in: NSApp.mainMenu!).map { !MenuTarget.shared.validateMenuItem($0) } ?? false, "Bookmark is greyed in an article")
        let had = await js(web, "document.querySelector('.rvgrid').classList.contains('withpanel') ? 1 : 0")
        log("INFO  before Side Panel: ran \(Menus.ran.suffix(2)), front \(DafWindowController.front === c), state \(await js(web, "JSON.stringify(dafState())"))")
        perform("Side Panel")
        check(await until(3) { await js(web, "document.querySelector('.rvgrid').classList.contains('withpanel') ? 1 : 0") != had }, "View → Side Panel",
              "ran \(Menus.ran.suffix(2)) · \(await js(web, "dafCommand('panel')"))")
        perform("Side Panel")
        perform("Typography")
        check(await until(3) { await js(web, "document.getElementById('pop').hidden ? 0 : 1") == "1" }, "View → Typography opens Aa")
        capture(c.window!, "03-article")
        // Tags… and Delete come alive in an article; Tags… presses the key keys.js has for it
        await js(web, "document.getElementById('pop').hidden = true, 1")
        // a key changed in Preferences → Keyboard: the menu shows it, and Tags… presses it
        let keysWere = await js(web, "JSON.stringify(JSON.parse(localStorage.getItem('daf.keys') || '{}'))")
        await js(web, "DafCore.Keys.set({ article: { tag: 'g', delete: '' } }), 1")
        Menus.refresh()
        await pause(0.5)
        let tagItem = find("Tags…", in: NSApp.mainMenu!), delItem = find("Delete", in: NSApp.mainMenu!)
        check(tagItem?.keyEquivalent == "g" && delItem?.keyEquivalent == "", "the Reader menu shows the keys as rebound",
              "\(tagItem?.keyEquivalent ?? "-") \(delItem?.keyEquivalent ?? "-")")
        for title in ["Tags…", "Delete"] {
            if let i = find(title, in: NSApp.mainMenu!) { check(MenuTarget.shared.validateMenuItem(i), "Reader → \(title) is there in an article") }
            else { check(false, "Reader → \(title) is in the menu") }
        }
        perform("Tags…")
        check(await until(4) { await js(web, "!document.getElementById('pop').hidden && /Enter adds a tag/.test(document.getElementById('pop').innerText) ? 1 : 0") == "1" },
              "Reader → Tags… opens the article's tags")
        await js(web, "document.getElementById('pop').hidden = true, 1")
        await js(web, "DafCore.Keys.set(\(keysWere)), 1")
        Menus.refresh()
        await pause(0.5)
        check(find("Tags…", in: NSApp.mainMenu!)?.keyEquivalent == "t", "and back to t when the keys are reset")
        perform("Back")
        check(await until(3) { await js(web, "document.getElementById('pop').hidden ? 1 : 0") == "1" }, "Back closes Aa before leaving")
    }

    /// A Calibre book in the EPUB reader (foliate-js): WebKit draws it, pages turn.
    static func book(_ c: DafWindowController) async {
        let web = c.webView!
        let id = await js(web, "fetch('/api/ebooks').then(r => r.json()).then(j => { const a = j.items || j.books || j; const b = Array.isArray(a) ? a.find(b => b.readable !== false) : null; return b ? b.id : ''; })")
        guard !id.isEmpty, !id.hasPrefix("error") else { return check(false, "a book to open", id) }
        await js(web, "location.hash = 'ebook/' + encodeURIComponent(\(DafWindowController.json(id))), 1")
        let text = "(() => { const v = document.querySelector('foliate-view'); try { const d = v.renderer.getContents()[0].doc; return d.body.innerText.trim().length; } catch (e) { return 0; } })()"
        check(await until(25) { (Int(await js(web, text)) ?? 0) > 50 }, "the book reader shows the book's text in WebKit", id)
        await pause(1.5)
        capture(c.window!, "04-book")
        Menus.refresh()
        await pause(0.5)
        check(find("Bookmark This Page", in: NSApp.mainMenu!).map { MenuTarget.shared.validateMenuItem($0) } ?? false, "Bookmark is there in a book")
        let place = "(() => { const v = document.querySelector('foliate-view'); return v && v.lastLocation ? v.lastLocation.fraction : -1; })()"
        let at = Double(await js(web, place)) ?? -1
        perform("Next")
        await pause(1)
        perform("Next")
        check(await until(4) { (Double(await js(web, place)) ?? -1) > at }, "Reader → Next turns the page", "\(at) → \(await js(web, place))")
        perform("Previous")
        perform("Contents")
        await pause(0.8)
        capture(c.window!, "05-book-contents")
        perform("Contents")
        await go(web, "today")
    }

    /// Minutes count only while someone can see the page.
    static func hidden(_ c: DafWindowController) async {
        let web = c.webView!, w = c.window!
        if await front(w) {
            check(await until(3) { await js(web, "document.visibilityState") == "visible" }, "the page is visible in front")
        } else { skip("the page is visible in front") }
        w.miniaturize(nil)
        check(await until(5) { await js(web, "document.visibilityState") == "hidden" }, "minimized, the page is hidden", await js(web, "document.visibilityState"))
        w.deminiaturize(nil)
        check(await until(5) { await js(web, "document.visibilityState") == "visible" }, "back from the Dock, visible again")
        NSApp.hide(nil)
        check(await until(5) { await js(web, "document.visibilityState") == "hidden" }, "with Daf hidden (⌘H), the page is hidden")
        NSApp.unhide(nil)
        _ = await until(5) { await js(web, "document.visibilityState") == "visible" }
        await front(w)
    }

    /// Only Daf in the window.
    static func outside(_ c: DafWindowController) async {
        let web = c.webView!
        Outside.opened = []
        await js(web, "window.open('https://example.com/opened', '_blank'), 1")
        await js(web, "(() => { const a = document.createElement('a'); a.href = 'https://example.org/linked'; document.body.appendChild(a); a.click(); a.remove(); return 1; })()")
        await js(web, "location.href = 'obsidian://open?vault=vault&file=x', 1")
        _ = await until(3) { Outside.opened.count >= 3 }
        let got = Outside.opened.map(\.absoluteString)
        check(got.contains("https://example.com/opened"), "window.open elsewhere goes to the browser", "\(got)")
        check(got.contains("https://example.org/linked"), "a link elsewhere goes to the browser", "\(got)")
        check(got.contains { $0.hasPrefix("obsidian://") }, "obsidian:// goes to Obsidian", "\(got)")
        check(Server.isOurs(web.url ?? URL(string: "about:blank")!), "and the window stays on Daf", web.url?.absoluteString ?? "")
    }

    static func downloads(_ c: DafWindowController) async {
        let web = c.webView!
        Downloads.finished = []
        await js(web, "(() => { const a = document.createElement('a'); a.href = URL.createObjectURL(new Blob(['hello from Daf'], { type: 'text/plain' })); a.download = 'selftest blob.txt'; document.body.appendChild(a); a.click(); a.remove(); return 1; })()")
        let blob = saveDir.appendingPathComponent("selftest blob.txt")
        check(await until(15) { text(blob) == "hello from Daf" }, "a blob link with download saves the file", "\(Downloads.finished)")
        await js(web, "(() => { const a = document.createElement('a'); a.href = '/api/highlights/export?fmt=md'; a.setAttribute('download', ''); document.body.appendChild(a); a.click(); a.remove(); return 1; })()")
        check(await until(10) { Downloads.finished.contains { $0.pathExtension == "md" && text($0).count > 10 } }, "Export highlights (Markdown) saves a file", "\(Downloads.finished.map(\.lastPathComponent))")
        let r = await js(web, "dafShell.download({ name: 'selftest bytes.txt', mime: 'text/plain', base64: btoa('bytes') })")
        check(r == "1" && text(saveDir.appendingPathComponent("selftest bytes.txt")) == "bytes", "dafShell.download saves bytes", r)
    }

    static func share(_ c: DafWindowController) async {
        let web = c.webView!
        // a 1×1 PNG
        let png = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
        let r = await js(web, "dafShell.share({ png: '\(png)', name: 'selftest.png' })")
        check(r == "1" && FileManager.default.fileExists(atPath: saveDir.appendingPathComponent("shared-selftest.png").path), "dafShell.share hands a PNG to the share sheet", r)
        check(await js(web, "navigator.canShare({ files: [new File([new Uint8Array(4)], 'h.png', { type: 'image/png' })] }) ? 1 : 0") == "1",
              "Share as image finds the share sheet behind navigator.share")
    }

    /// Today's minutes in the menu bar, from the device token.
    static func menubar(_ c: DafWindowController) async {
        await Today.shared.refresh()
        check(Today.shared.widget != nil && Today.shared.problem == nil, "the menu bar asks /api/phone/widget with the token", Today.shared.problem ?? "")
        let minutes = Int(await js(c.webView, "dafState().minutes")) ?? -1
        let title = MenuBar.shared.item?.button?.title ?? ""
        check(title.hasSuffix("′") || title.hasSuffix("′ ✓"), "the menu bar shows the minutes", title)
        if let w = Today.shared.widget { check(abs(Int(w.minutes) - minutes) <= 1, "the same minutes as Today", "\(Int(w.minutes)) and \(minutes)") }
        let picture = ImageRenderer(content: TodayHeader(today: Today.shared).background(Color(nsColor: .windowBackgroundColor)))
        picture.scale = 2
        save(picture.nsImage, "06-menubar-header")
        // another main goal (Preferences → Goals): the title says its count, the menu its words
        let put = { (goals: String) in "fetch('/api/goals', { method: 'PUT', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ goals: \(goals) }) }).then(r => r.status)" }
        let status = await js(c.webView, put("[{ id: 'pages', period: 'week', target: 200, on: true, main: true }]"))
        if status == "200" {
            await Today.shared.refresh()
            let t = MenuBar.shared.item?.button?.title ?? ""
            check(t.hasSuffix("/200") || t.hasSuffix("/200 ✓"), "with 200 pages a week as the main goal, the menu bar says n/200", t)
            check(Today.shared.widget?.main?.text?.contains("pages") == true, "and the menu says it in words", Today.shared.widget?.main?.text ?? "")
            _ = await js(c.webView, put("[{ id: 'minutes', period: 'day', target: 60, on: true, main: true }]"))
            await Today.shared.refresh()
            check((MenuBar.shared.item?.button?.title ?? "").hasSuffix("′"), "back to the hour, back to minutes", MenuBar.shared.item?.button?.title ?? "")
        } else { check(false, "the sandbox takes a new main goal", status) }

        // offline: the last answer stays
        let base = Server.base.absoluteString
        UserDefaults.standard.set("http://127.0.0.1:9", forKey: Server.baseKey)
        await Today.shared.refresh()
        check(Today.shared.problem != nil && MenuBar.shared.item?.button?.title == title, "offline, the menu bar keeps what it knew", Today.shared.problem ?? "")
        UserDefaults.standard.set(base, forKey: Server.baseKey)
        await Today.shared.refresh()
    }

    /// No network: the window comes up on the app's own copy of Daf (LocalCopy, daf-app://app/) with
    /// the data it kept, and goes back to the live site, its outbox sent, once Daf answers again.
    static func offline(_ c: DafWindowController) async {
        do { try await LocalCopy.refreshScreens() } catch { return check(false, "Daf's screens are copied to this Mac", error.localizedDescription) }
        await LocalCopy.keepData()
        check(LocalCopy.ready, "Daf's screens are kept on this Mac", LocalCopy.appDir.path)
        check(LocalCopy.kept("/api/today", "") != nil, "and its data, today among it")
        let base = Server.base.absoluteString
        let q = { (s: String) in DafWindowController.json(s) }
        // kept by hand through the page's own calls (dafShell.offline), as its menus do
        check(await js(c.webView, "dafShell.can('offline') ? 1 : 0") == "1", "the Mac keeps things for no network (dafShell.offline)")
        // a long article with a colon in its id (kk:…), one the plan doesn't name if there is one
        let article = await js(c.webView, "Promise.all([fetch('/api/offline/plan').then(r => r.json()), ...['archive', 'inbox', 'later'].map(t => fetch('/api/docs?where=library&tab=' + t + '&kind=article&limit=100').then(r => r.json()))])"
            + ".then(([p, ...ls]) => { const all = ls.flatMap(l => l.items || []).filter(d => (d.words || 0) > 300 && d.id.includes(':')); return ((all.find(d => !p.docs.includes(d.id)) || all[0]) || {}).id || ''; })")
        await js(c.webView, "dafShell.offline({ op: 'doc', id: \(q(article)), on: true }).then(() => 1)")
        check(!article.isEmpty && OnThisMac.state.docs.contains(article), "an article kept by hand", article)
        let book = await js(c.webView, "fetch('/api/books').then(r => r.json()).then(j => ([...(j.others || [])].reverse().find(b => b.readable) || {}).id || '')")
        await js(c.webView, "dafShell.offline({ op: 'keep', id: \(q(book)), on: true }).then(() => 1)")
        let bookFile = LocalCopy.dataFile(OnThisMac.bookPath(book) + "/file")
        check(OnThisMac.state.books[book]?.kept == true && FileManager.default.fileExists(atPath: bookFile.path), "a book kept by hand, with its file", book)
        let vol = await js(c.webView, "fetch('/api/manga').then(r => r.json()).then(async j => { for (const s of (j.series || []).slice(0, 8)) { const d = await fetch('/api/manga/series/' + encodeURIComponent(s.id)).then(r => r.json()); const b = (d.books || []).filter(b => b.ok !== false && b.pages > 0).sort((a, b) => a.pages - b.pages)[0]; if (b) return b.id; } return ''; })")
        await js(c.webView, "dafShell.offline({ op: 'manga', id: \(q(vol)), on: true, size: 600 }).then(() => 1)")
        let downloaded = await until(240) { ["done", "failed"].contains(OnThisMac.state.manga[vol]?.state ?? "") } && OnThisMac.state.manga[vol]?.state == "done"
        let m = OnThisMac.state.manga[vol]
        check(downloaded, "a manga volume downloads", "\(vol) \(m?.done ?? 0)/\(m?.total ?? 0) \(m?.error ?? "")")
        let pdf = await js(c.webView, "Promise.all([fetch('/api/offline/plan').then(r => r.json()), fetch('/api/docs?where=library&tab=inbox&kind=pdf&limit=40').then(r => r.json())]).then(([p, j]) => ((j.items || []).find(d => p.docs.includes(d.id)) || {}).id || '')")
        if !pdf.isEmpty {
            check(FileManager.default.fileExists(atPath: LocalCopy.dataFile(LocalCopy.docPath(pdf) + "/pdf").path), "a PDF in the plan keeps its file", pdf)
        } else { log("SKIP  no PDF in the plan") }
        // the live page's settings go with it (a theme, say): a snapshot, as after each live load
        await js(c.webView, "localStorage.setItem('daf.selftest.seed', 'one'), 1")
        LocalCopy.keepSnapshot(await js(c.webView, LocalCopy.snapshotJS))
        UserDefaults.standard.set("http://127.0.0.1:59999", forKey: Server.baseKey)   // Daf out of reach: nothing listens there
        c.webView.load(URLRequest(url: Server.url("#today")))
        let local = await until(20) { c.webView.url?.scheme == LocalCopy.scheme }
        check(local, "Daf out of reach: the window comes up on the copy", c.webView.url?.absoluteString ?? "")
        check(await until(10) { await js(c.webView, "localStorage.getItem('daf.selftest.seed')") == "one" }, "with the live page's settings")
        let today = await until(25) { await js(c.webView, "window.DafCore && document.body.dataset.view === 'today' && /Today/.test(document.body.innerText) ? 1 : 0") == "1" }
        check(today, "and shows Today from what was kept", await js(c.webView, "document.body ? document.body.innerText.slice(0, 120) : ''"))
        if let w = c.window { capture(w, "40-offline-today") }
        await go(c.webView, "#books")
        check(await js(c.webView, "document.querySelectorAll('#main img, #main a').length > 3 ? 1 : 0") == "1", "Books opens from the copy too")
        check(await js(c.webView, "document.fonts.check('16px Figtree') ? 1 : 0") == "1", "with Daf's own fonts")
        // what was kept by hand opens from the copy
        await go(c.webView, "read/" + OnThisMac.enc(article))
        check(await until(20) { await js(c.webView, "document.getElementById('docbody') && document.getElementById('docbody').innerText.split(/\\s+/).length > 200 ? 1 : 0") == "1" },
              "the kept article opens from the copy, all of it", article)
        if !pdf.isEmpty {
            await go(c.webView, "pdf/" + OnThisMac.enc(pdf))
            check(await until(40) { await js(c.webView, "document.querySelectorAll('.pdfpages canvas').length > 0 ? 1 : 0") == "1" },
                  "a PDF's pages open from the copy", await js(c.webView, "document.body.innerText.slice(0, 160)"))
        }
        await go(c.webView, "ebook/" + OnThisMac.enc(book))
        check(await until(40) { await js(c.webView, "(document.querySelector('foliate-view') || {}).lastLocation ? 1 : 0") == "1" }, "the kept book opens from the copy", book)
        if downloaded {
            await go(c.webView, "mread/" + OnThisMac.enc(vol))
            check(await until(30) { await js(c.webView, "document.body.dataset.view === 'mread' && [...document.querySelectorAll('#mreader img')].some(i => i.complete && i.naturalWidth > 0) ? 1 : 0") == "1" },
                  "the downloaded manga volume reads from the copy", vol)
            await js(c.webView, "history.back(), 1")
        }
        await go(c.webView, "books")
        // a change made with Daf out of reach waits in the outbox
        await js(c.webView, "DafCore.api('/api/docs/selftest-offline/progress', { method: 'PUT', body: JSON.stringify({ progress: 1 }) }).catch(e => 0)")
        let waiting = await js(c.webView, "JSON.parse(localStorage.getItem('daf.outbox') || '[]').length")
        check((Int(waiting) ?? 0) > 0, "a change made offline waits in the outbox", waiting)
        UserDefaults.standard.set(base, forKey: Server.baseKey)                       // Daf back
        await Reconnect.shared.check()
        let live = await until(30) { ["http", "https"].contains(c.webView.url?.scheme ?? "") }
        check(live, "Daf back: the window returns to the live site", c.webView.url?.absoluteString ?? "")
        _ = await until(25) { await js(c.webView, "window.dafState && dafState().signedIn ? 1 : 0") == "1" }
        check(await until(10) { !LocalCopy.active }, "and the copy steps aside")
        // a setting changed online reaches the copy the next time, over the one it already has
        await js(c.webView, "localStorage.setItem('daf.selftest.seed', 'two'), 1")
        await pause(1.1)
        LocalCopy.keepSnapshot(await js(c.webView, LocalCopy.snapshotJS))
        UserDefaults.standard.set("http://127.0.0.1:59999", forKey: Server.baseKey)
        c.webView.load(URLRequest(url: Server.url("#today")))
        _ = await until(20) { c.webView.url?.scheme == LocalCopy.scheme }
        let seed = await until(10) { await js(c.webView, "localStorage.getItem('daf.selftest.seed')") == "two" }
        check(seed, "a setting changed online reaches the copy next time", await js(c.webView, "localStorage.getItem('daf.selftest.seed')"))
        await js(c.webView, "localStorage.removeItem('daf.selftest.seed'), 1")
        UserDefaults.standard.set(base, forKey: Server.baseKey)
        await Reconnect.shared.check()
        _ = await until(30) { ["http", "https"].contains(c.webView.url?.scheme ?? "") }
        _ = await until(25) { await js(c.webView, "window.dafState && dafState().signedIn ? 1 : 0") == "1" }
        await js(c.webView, "localStorage.removeItem('daf.selftest.seed'), 1")
        // what nothing names any more goes after three weeks; what something names stays, however old
        let old = Date(timeIntervalSinceNow: -30 * 24 * 3600), fm = FileManager.default
        let stale = LocalCopy.dataDir.appendingPathComponent("deadbeefdeadbeef"), fresh = LocalCopy.dataDir.appendingPathComponent("cafecafecafecafe")
        try? Data("x".utf8).write(to: stale)
        try? Data("x".utf8).write(to: fresh)
        try? fm.setAttributes([.modificationDate: old], ofItemAtPath: stale.path)
        try? fm.setAttributes([.modificationDate: old], ofItemAtPath: bookFile.path)
        // a Feed item kept by hand, then deleted in Daf (the sandbox's FreshRSS is a stand-in)
        var feed = ""
        _ = await until(20) {                       // the page may still be loading after coming back
            feed = await js(c.webView, "fetch('/api/docs?where=feed&tab=unseen&limit=30').then(r => r.json()).then(j => ((j.items || []).find(d => (d.words || 0) > 40) || {}).id || '')")
            return !feed.isEmpty && !feed.hasPrefix("error")
        }
        await js(c.webView, "dafShell.offline({ op: 'doc', id: \(q(feed)), on: true }).then(() => 1)")
        check(OnThisMac.state.docs.contains(feed), "a Feed item kept by hand", feed)
        await js(c.webView, "fetch('/api/docs/' + encodeURIComponent(\(q(feed))) + '/status', { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ status: 'deleted' }) }).then(r => r.status)")
        let said = await LocalCopy.keepData()
        check(!fm.fileExists(atPath: stale.path), "a file nothing names, old, goes", said)
        check(fm.fileExists(atPath: fresh.path), "one nothing names but new stays")
        check(fm.fileExists(atPath: bookFile.path), "and a kept book's file stays, however old")
        check(!OnThisMac.state.docs.contains(feed), "a kept item deleted in Daf leaves the Mac")
        check(!fm.fileExists(atPath: LocalCopy.dataFile(LocalCopy.docPath(feed)).path), "with its file")
        try? fm.removeItem(at: fresh)
        // and let go by hand
        await js(c.webView, "Promise.all([dafShell.offline({ op: 'doc', id: \(q(article)), on: false }), dafShell.offline({ op: 'keep', id: \(q(book)), on: false }), dafShell.offline({ op: 'manga', id: \(q(vol)), on: false })]).then(() => 1)")
        check(!OnThisMac.state.docs.contains(article) && OnThisMac.state.manga[vol] == nil && OnThisMac.state.books[book]?.kept != true, "Remove lets each go")
    }

    static func save() async {
        SaveLink.handle(URL(string: "daf://save?url=https%3A%2F%2Fexample.com%2Fdaf-selftest&title=Selftest")!)
        check(await until(8) { SaveLink.saved.contains("https://example.com/daf-selftest") }, "daf://save saves the link with the token")
        check(MenuBar.shared.item?.button?.title == "Saved", "and the menu bar says Saved", MenuBar.shared.item?.button?.title ?? "")
    }

    static func settings() async {
        SettingsWindow.show()
        await pause(0.8)
        if let w = NSApp.windows.first(where: { $0.title == "Daf Settings" }) {
            capture(w, "07-settings")
            check(true, "Settings opens")
            w.close()
        } else { check(false, "Settings opens") }
        let before = Token.value
        let problem = await SettingsWindow.connect()
        check(problem == nil && Token.value != nil && Token.value != before, "Connect This Mac makes a token with the window's sign-in", problem ?? "")
        await Today.shared.refresh()
        check(Today.shared.problem == nil, "and the menu bar works with it", Today.shared.problem ?? "")
    }

    // MARK: helpers

    static func perform(_ title: String) {
        guard let i = find(title, in: NSApp.mainMenu!), let m = i.menu else { return log("INFO  no menu item \(title)") }
        m.update()          // as opening the menu would: an item greyed when the page was elsewhere does nothing
        m.performActionForItem(at: m.index(of: i))
    }

    @discardableResult
    static func front(_ w: NSWindow) async -> Bool {
        if NSApp.isActive && w.isKeyWindow { return true }
        NSApp.bringForward()
        w.makeKeyAndOrderFront(nil)
        let ok = await until(3) { NSApp.isActive && w.isKeyWindow }
        if !ok { log("INFO  another app is in front; the next checks need Daf in front") }
        await pause(0.2)
        return ok
    }

    static func find(_ title: String, in menu: NSMenu) -> NSMenuItem? {
        for i in menu.items where !i.isHidden {
            if i.title == title { return i }
            if let sub = i.submenu, let hit = find(title, in: sub) { return hit }
        }
        return nil
    }

    static func text(_ url: URL) -> String { (try? String(contentsOf: url, encoding: .utf8)) ?? "" }

    @discardableResult
    static func js(_ web: WKWebView, _ src: String) async -> String {
        // promises are awaited, so fetch() answers come back as values
        do {
            let v = try await web.callAsyncJavaScript("return await (\(src))", arguments: [:], in: nil, contentWorld: .page)
            if let b = v as? Bool { return b ? "1" : "0" }
            return String(describing: v ?? "undefined")
        } catch { return "error: \(error.localizedDescription)" }
    }

    /// A key as the keyboard sends it.
    static func press(_ key: String, _ code: UInt16, _ flags: NSEvent.ModifierFlags = []) {
        for type in [NSEvent.EventType.keyDown, .keyUp] {
            if let e = NSEvent.keyEvent(with: type, location: .zero, modifierFlags: flags,
                                        timestamp: ProcessInfo.processInfo.systemUptime,
                                        windowNumber: NSApp.keyWindow?.windowNumber ?? 0, context: nil,
                                        characters: key, charactersIgnoringModifiers: key,
                                        isARepeat: false, keyCode: code) {
                NSApp.postEvent(e, atStart: false)
            }
        }
    }

    static func log(_ s: String) { FileHandle.standardError.write(Data((s + "\n").utf8)) }
    static func check(_ ok: Bool, _ what: String, _ detail: String = "") {
        log((ok ? "PASS  " : "FAIL  ") + what + (detail.isEmpty ? "" : "  [" + detail.replacingOccurrences(of: "\n", with: "⏎") + "]"))
        if !ok { failures += 1 }
    }
    static func skip(_ what: String) { log("SKIP  \(what): Daf couldn't come to the front"); skipped += 1 }
    static func pause(_ s: Double) async { try? await Task.sleep(nanoseconds: UInt64(s * 1_000_000_000)) }
    static func until(_ timeout: Double, _ cond: () async -> Bool) async -> Bool {
        let end = Date().addingTimeInterval(timeout)
        repeat { if await cond() { return true }; await pause(0.15) } while Date() < end
        return false
    }

    static func save(_ image: NSImage?, _ name: String) {
        guard let tiff = image?.tiffRepresentation, let rep = NSBitmapImageRep(data: tiff),
              let png = rep.representation(using: .png, properties: [:]) else { return }
        try? png.write(to: outDir.appendingPathComponent(name + ".png"))
    }
    /// The app's own windows, chrome and all; no Screen Recording permission needed for these.
    static func capture(_ w: NSWindow, _ name: String) {
        guard let cg = CGWindowListCreateImage(.null, .optionIncludingWindow, CGWindowID(w.windowNumber),
                                               [.boundsIgnoreFraming, .bestResolution]) else { return }
        save(NSImage(cgImage: cg, size: .zero), name)
    }
    static func dumpMenus() {
        for top in NSApp.mainMenu?.items ?? [] {
            let items = (top.submenu?.items ?? []).filter { !$0.isSeparatorItem && !$0.isHidden }.map { i -> String in
                let m = i.keyEquivalentModifierMask
                let mods = (m.contains(.control) ? "⌃" : "") + (m.contains(.option) ? "⌥" : "") + (m.contains(.shift) ? "⇧" : "") + (m.contains(.command) ? "⌘" : "")
                let named: [String: String] = [Menus.left: "←", Menus.right: "→"]
                let key = named[i.keyEquivalent] ?? i.keyEquivalent.uppercased()
                return i.keyEquivalent.isEmpty ? i.title : "\(i.title) \(mods)\(key)"
            }
            log("MENU  \(top.title): " + items.joined(separator: " · "))
        }
    }
}
