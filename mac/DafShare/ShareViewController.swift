import AppKit
import UniformTypeIdentifiers

/// "Save to Daf" in the share menu. The extension is sandboxed and holds no token: it
/// hands the link to Daf itself as daf://save?url=…&title=…, and Daf saves it with the
/// device token from the Keychain (SaveLink.swift), then says "Saved" in the menu bar.
@objc(ShareViewController)
final class ShareViewController: NSViewController {
    private let label = NSTextField(labelWithString: "Saving to Daf…")

    override var nibName: NSNib.Name? { nil }

    override func loadView() {
        let v = NSView(frame: NSRect(x: 0, y: 0, width: 280, height: 64))
        label.font = .systemFont(ofSize: 13)
        label.translatesAutoresizingMaskIntoConstraints = false
        v.addSubview(label)
        NSLayoutConstraint.activate([label.centerXAnchor.constraint(equalTo: v.centerXAnchor),
                                     label.centerYAnchor.constraint(equalTo: v.centerYAnchor)])
        view = v
    }

    override func viewDidAppear() {
        super.viewDidAppear()
        Task { @MainActor in await handOff() }
    }

    @MainActor
    private func handOff() async {
        let items = extensionContext?.inputItems as? [NSExtensionItem] ?? []
        var link: String?, text: String?
        let title = items.lazy.compactMap { $0.attributedContentText?.string ?? $0.attributedTitle?.string }.first { !$0.isEmpty }
        for provider in items.flatMap({ $0.attachments ?? [] }) {
            if link == nil, provider.hasItemConformingToTypeIdentifier(UTType.url.identifier),
               let u = await load(provider, UTType.url), u.scheme?.hasPrefix("http") == true {
                link = u.absoluteString
            } else if text == nil, provider.hasItemConformingToTypeIdentifier(UTType.plainText.identifier) {
                text = await loadText(provider)
            }
        }
        var q = URLComponents()
        q.scheme = "daf"
        q.host = "save"
        q.queryItems = [URLQueryItem(name: "url", value: link ?? ""), URLQueryItem(name: "title", value: title ?? ""),
                        URLQueryItem(name: "text", value: String((text ?? "").prefix(2000)))]
        guard link != nil || text?.contains("http") == true, let url = q.url, NSWorkspace.shared.open(url) else {
            label.stringValue = "There's no link to save."
            try? await Task.sleep(nanoseconds: 1_200_000_000)
            extensionContext?.cancelRequest(withError: NSError(domain: NSCocoaErrorDomain, code: NSUserCancelledError))
            return
        }
        extensionContext?.completeRequest(returningItems: nil)
    }

    private func load(_ p: NSItemProvider, _ type: UTType) async -> URL? {
        guard let item = try? await p.loadItem(forTypeIdentifier: type.identifier) else { return nil }
        if let u = item as? URL { return u }
        if let d = item as? Data { return URL(dataRepresentation: d, relativeTo: nil) }
        if let s = item as? String { return URL(string: s) }
        return nil
    }

    private func loadText(_ p: NSItemProvider) async -> String? {
        guard let item = try? await p.loadItem(forTypeIdentifier: UTType.plainText.identifier) else { return nil }
        if let s = item as? String { return s }
        if let d = item as? Data { return String(data: d, encoding: .utf8) }
        return nil
    }
}
