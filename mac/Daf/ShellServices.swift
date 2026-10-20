import AppKit
import UniformTypeIdentifiers
import WebKit

/// `window.dafShell` (docs/SHELL.md §2): the share sheet, the save panel, the browser,
/// notifications for new posts, and what's kept on this Mac for no network (OnThisMac), which a
/// page can't do well from inside a web view. Each call is a
/// message with a reply, so the page's promise settles when the panel closes.
@MainActor
final class ShellServices: NSObject, WKScriptMessageHandlerWithReply, NSSharingServicePickerDelegate {
    weak var webView: WKWebView?
    private var picked: CheckedContinuation<Bool, Never>?

    /// Defined before the page's own scripts run, so the page finds it at once.
    static var script: String {
        """
        (() => {
          const call = (op, args) => window.webkit.messageHandlers.dafShell.postMessage({ op, args: args || {} });
          const caps = ['share', 'download', 'openExternal', 'alerts', 'fullscreen', 'offline'];
          const s = v => v == null ? '' : String(v);
          window.dafShell = Object.freeze({
            platform: 'mac', version: \(DafWindowController.json(UserAgent.version)),
            can: op => caps.includes(op),
            share: a => call('share', { text: s(a && a.text), url: s(a && a.url), png: s(a && a.png), name: s(a && a.name) }),
            download: a => call('download', typeof a === 'string' ? { url: a } : { name: s(a && a.name), mime: s(a && a.mime), base64: s(a && a.base64) }),
            openExternal: u => call('openExternal', { url: s(u) }),
            alerts: () => call('alerts', {}),
            fullscreen: () => call('fullscreen', {}),
            // what's kept on this Mac: {op: 'list' | 'has' | 'keep' | 'doc' | 'manga' | 'sync', id?, on?, size?}
            offline: a => call('offline', { op: s(a && a.op) || 'list', id: s(a && a.id), on: !(a && a.on === false), size: +(a && a.size) || 0 }),
          });
        })();
        """
    }

    /// For the self-test: -SelfTestSaveDir DIR saves and shares there, without a panel.
    static var testDir: URL? {
        UserDefaults.standard.string(forKey: "SelfTestSaveDir").map { URL(fileURLWithPath: $0, isDirectory: true) }
    }

    nonisolated func userContentController(_ controller: WKUserContentController, didReceive message: WKScriptMessage,
                                           replyHandler: @escaping @MainActor @Sendable (Any?, String?) -> Void) {
        MainActor.assumeIsolated {
            guard message.frameInfo.isMainFrame, let url = webView?.url, Server.isOurs(url) else {
                return replyHandler(nil, "only Daf's own page may use the shell")
            }
            guard let body = message.body as? [String: Any], let op = body["op"] as? String else {
                return replyHandler(nil, "not a shell message")
            }
            let args = body["args"] as? [String: Any] ?? [:]
            Task { @MainActor in
                do { replyHandler(try await self.answer(op, args), nil) } catch { replyHandler(nil, error.localizedDescription) }
            }
        }
    }

    private func answer(_ op: String, _ args: [String: Any]) async throws -> Any {
        let str = { (k: String) in (args[k] as? String).flatMap { $0.isEmpty ? nil : $0 } }
        switch op {
        case "share":
            var items: [Any] = []
            if let png = str("png") {
                guard let data = Data(base64Encoded: png, options: .ignoreUnknownCharacters) else { throw ShellError("the picture didn't arrive") }
                let name = Self.withExtension(Self.safeName(str("name") ?? "Daf highlight"), "png")
                let file = try Self.scratch(name)
                try data.write(to: file, options: .atomic)
                items.append(file)
            }
            if let u = str("url"), let url = URL(string: u) { items.append(url) }
            if let t = str("text") { items.append(t) }
            guard !items.isEmpty else { return false }
            if let dir = Self.testDir {
                for case let file as URL in items where file.isFileURL {
                    try? FileManager.default.removeItem(at: dir.appendingPathComponent("shared-" + file.lastPathComponent))
                    try FileManager.default.copyItem(at: file, to: dir.appendingPathComponent("shared-" + file.lastPathComponent))
                }
                return true
            }
            return await showShare(items)
        case "download":
            if let u = str("url"), let web = webView {
                guard let url = URL(string: u, relativeTo: web.url)?.absoluteURL else { throw ShellError("not an address: \(u)") }
                let download = await web.startDownload(using: URLRequest(url: url))
                download.delegate = Downloads.shared
                return true
            }
            guard let b = str("base64"), let data = Data(base64Encoded: b, options: .ignoreUnknownCharacters) else {
                throw ShellError("the file's bytes didn't arrive")
            }
            let name = Self.safeName(str("name") ?? "Daf")
            let type = UTType(filenameExtension: (name as NSString).pathExtension) ?? str("mime").flatMap { UTType(mimeType: $0) }
            guard let target = await Self.chooseDestination(name, type: type, window: webView?.window) else { return false }
            try data.write(to: target, options: .atomic)
            return true
        case "openExternal":
            guard let s = str("url"), let url = URL(string: s) else { return false }
            return Outside.open(url)
        case "fullscreen":
            // the manga reader's Full screen: the window's own (macOS full screen), left again with the reader
            guard let w = webView?.window else { return false }
            let entering = !w.styleMask.contains(.fullScreen)
            (w.windowController as? DafWindowController)?.fullScreenForReader = entering
            w.toggleFullScreen(nil)
            return entering
        case "alerts":
            // notifications for new posts in the feeds set to notify (FeedNews)
            return await FeedNews.shared.start()
        case "offline":
            return try await OnThisMac.answer(args)
        default:
            throw ShellError("no such shell call: \(op)")
        }
    }

    /// The share picker beside the pointer (the page's Share button was just pressed there).
    /// True once something was picked, false if it was dismissed.
    private func showShare(_ items: [Any]) async -> Bool {
        guard let view = webView, let window = view.window else { return false }
        let at = view.convert(window.convertPoint(fromScreen: NSEvent.mouseLocation), from: nil)
        let picker = NSSharingServicePicker(items: items)
        picker.delegate = self
        picked?.resume(returning: false)
        return await withCheckedContinuation { (c: CheckedContinuation<Bool, Never>) in
            picked = c
            picker.show(relativeTo: NSRect(x: at.x, y: at.y, width: 1, height: 1), of: view, preferredEdge: .minY)
        }
    }

    nonisolated func sharingServicePicker(_ sharingServicePicker: NSSharingServicePicker, didChoose service: NSSharingService?) {
        MainActor.assumeIsolated {
            picked?.resume(returning: service != nil)
            picked = nil
        }
    }

    /// A save panel for `name`, as a sheet on the window. Nil if cancelled.
    static func chooseDestination(_ name: String, type: UTType?, window: NSWindow?) async -> URL? {
        if let testDir { return testDir.appendingPathComponent(safeName(name)) }
        let panel = NSSavePanel()
        panel.nameFieldStringValue = safeName(name)
        panel.canCreateDirectories = true
        panel.isExtensionHidden = false
        panel.directoryURL = FileManager.default.urls(for: .downloadsDirectory, in: .userDomainMask).first
        if let type { panel.allowedContentTypes = [type] }
        guard let window, window.isVisible else { return panel.runModal() == .OK ? panel.url : nil }
        let response = await panel.beginSheetModal(for: window)
        return response == .OK ? panel.url : nil
    }

    /// A file of that name in a folder of its own under the temporary directory.
    static func scratch(_ name: String) throws -> URL {
        let dir = FileManager.default.temporaryDirectory.appendingPathComponent("Daf Share/\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        return dir.appendingPathComponent(safeName(name))
    }

    static func safeName(_ name: String) -> String {
        let cleaned = name.replacingOccurrences(of: "/", with: "-").replacingOccurrences(of: ":", with: "-")
            .trimmingCharacters(in: .whitespacesAndNewlines)
        return cleaned.isEmpty ? "Daf" : cleaned
    }

    static func withExtension(_ name: String, _ ext: String) -> String {
        (name as NSString).pathExtension.lowercased() == ext ? name : name + "." + ext
    }
}

struct ShellError: LocalizedError {
    let message: String
    init(_ message: String) { self.message = message }
    var errorDescription: String? { message }
}

/// Downloads: `<a download>`, attachments and blob links (the highlight exports, a book's
/// file, Share as image's Download). They go where the save panel says.
@MainActor
final class Downloads: NSObject, WKDownloadDelegate {
    static let shared = Downloads()
    weak var webView: WKWebView?
    /// What the self-test saw arrive.
    static var finished: [URL] = []
    private var targets: [ObjectIdentifier: URL] = [:]

    func download(_ download: WKDownload, decideDestinationUsing response: URLResponse, suggestedFilename: String) async -> URL? {
        let name = suggestedFilename.isEmpty ? (response.suggestedFilename ?? "Daf") : suggestedFilename
        let type = UTType(filenameExtension: (name as NSString).pathExtension)
        let window = (download.webView ?? webView)?.window ?? DafWindowController.front?.window
        guard let target = await ShellServices.chooseDestination(name, type: type, window: window) else { return nil }
        // the panel asked about replacing it; WebKit won't write over a file
        try? FileManager.default.removeItem(at: target)
        targets[ObjectIdentifier(download)] = target
        return target
    }

    func downloadDidFinish(_ download: WKDownload) {
        if let url = targets.removeValue(forKey: ObjectIdentifier(download)) { Self.finished.append(url) }
    }

    func download(_ download: WKDownload, didFailWithError error: Error, resumeData: Data?) {
        targets.removeValue(forKey: ObjectIdentifier(download))
        let e = error as NSError
        if e.domain == NSURLErrorDomain && e.code == NSURLErrorCancelled { return }
        NSLog("Daf: a download failed: \(error.localizedDescription)")
        let alert = NSAlert()
        alert.messageText = "The download didn't finish"
        alert.informativeText = error.localizedDescription
        alert.runModal()
    }
}
