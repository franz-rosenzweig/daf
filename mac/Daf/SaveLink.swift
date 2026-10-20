import AppKit

/// Saving a link to Daf's Library (POST /api/save, with the device token): from
/// File → Save a Link…, from the menu-bar menu, and from the share menu's Save to Daf,
/// which holds no token itself and hands the link over as `daf://save?url=…&title=…`.
@MainActor
enum SaveLink {
    /// What was saved, for the self-test.
    static var saved: [String] = []

    /// `daf://save?url=…&title=…&text=…`
    static func handle(_ url: URL) {
        guard url.scheme == "daf", url.host == "save",
              let q = URLComponents(url: url, resolvingAgainstBaseURL: false)?.queryItems else { return }
        let value = { (k: String) in q.first { $0.name == k }?.value }
        let text = value("text")
        guard let link = value("url").flatMap({ $0.isEmpty ? nil : $0 }) ?? text.flatMap(firstLink) else {
            return fail("There was no link to save.")
        }
        Task { await save(link, title: value("title"), text: text) }
    }

    /// File → Save a Link…: an address, with the one on the clipboard filled in.
    static func ask() {
        let alert = NSAlert()
        alert.messageText = "Save a link to Daf"
        alert.informativeText = "It goes to your Library on Daf's next sync."
        let field = NSTextField(frame: NSRect(x: 0, y: 0, width: 340, height: 24))
        field.placeholderString = "https://"
        if let s = NSPasteboard.general.string(forType: .string), let link = firstLink(s) { field.stringValue = link }
        alert.accessoryView = field
        alert.addButton(withTitle: "Save")
        alert.addButton(withTitle: "Cancel")
        alert.window.initialFirstResponder = field
        NSApp.bringForward()
        guard alert.runModal() == .alertFirstButtonReturn else { return }
        guard let link = firstLink(field.stringValue) else { return fail("That isn't a link.") }
        Task { await save(link, title: nil, text: nil) }
    }

    static func save(_ link: String, title: String?, text: String?) async {
        do {
            try await Client.save(url: link, title: title, text: text)
            saved.append(link)
            MenuBar.shared.flash("Saved")
        } catch {
            // a missing or refused token is fixed in Settings; a server that didn't answer isn't
            var offline = false
            if case .unreachable? = error as? Client.Failure { offline = true }
            fail(error.localizedDescription, settings: error is Client.Failure && !offline)
        }
    }

    /// The first http(s) address in a piece of text.
    static func firstLink(_ s: String) -> String? {
        let t = s.trimmingCharacters(in: .whitespacesAndNewlines)
        guard let r = t.range(of: #"https?://\S+"#, options: .regularExpression) else { return nil }
        return String(t[r])
    }

    private static func fail(_ why: String, settings: Bool = false) {
        if Outside.testing { NSLog("Daf: not saved: \(why)"); return }
        let alert = NSAlert()
        alert.messageText = "Daf didn't save the link"
        alert.informativeText = why
        alert.addButton(withTitle: "OK")
        if settings { alert.addButton(withTitle: "Open Settings") }
        NSApp.bringForward()
        if alert.runModal() == .alertSecondButtonReturn { SettingsWindow.show() }
    }
}
