import AppKit
import SwiftUI
import UniformTypeIdentifiers

/// Add to Daf (File › Add to Daf…, ⌘L), as the page's Add: a link to the Library, or the site followed
/// in the Feed; books (EPUB, MOBI, AZW3, FB2, CBZ) into Calibre, then Books, and PDFs into the Library,
/// chosen here or dropped here or on the window. A link pasted where there's nothing to paste into,
/// or a link or file dropped on the window, opens it with them.
struct AddSheet: View {
    @Environment(AppModel.self) private var model
    @Environment(\.dismiss) private var dismiss
    @State private var url = ""
    @State private var folders: [String] = []
    @State private var folder = ""
    @State private var lines: [String] = []
    @State private var busy = false
    @State private var dropping = false
    @State private var opened: String?

    static let kinds = ["epub", "kepub", "mobi", "azw3", "azw", "fb2", "cbz", "pdf"]
    static func addable(_ u: URL) -> Bool { u.isFileURL && kinds.contains(u.pathExtension.lowercased()) }

    var body: some View {
        Form {
            Section {
                TextField("Link", text: $url, prompt: Text("Paste a link"))
                    .onSubmit { Task { await save() } }
                HStack {
                    Picker("Or follow the site in the Feed, in", selection: $folder) {
                        Text("No folder").tag("")
                        ForEach(folders, id: \.self) { Text($0).tag($0) }
                    }
                    Button("Follow") { Task { await follow() } }.disabled(busy || !url.lowercased().hasPrefix("http"))
                }
            } header: { Text("Add to Daf") } footer: {
                Text("Links go to the Library, and Daf reads the page.").foregroundStyle(.secondary)
            }
            Section {
                VStack(spacing: 6) {
                    Image(systemName: "books.vertical").font(.title2)
                    Text("Drop books or PDFs here").font(.headline)
                    Button("Choose Files…") { choose() }
                }
                .frame(maxWidth: .infinity).padding(.vertical, 12)
                .background(RoundedRectangle(cornerRadius: 10).strokeBorder(style: StrokeStyle(lineWidth: 1.5, dash: [5]))
                    .foregroundStyle(dropping ? Color.daf : Color.secondary.opacity(0.4)))
                .onDrop(of: [.fileURL], isTargeted: $dropping) { providers in
                    AddSheet.files(providers) { urls in Task { await upload(urls) } }
                    return true
                }
                ForEach(Array(lines.enumerated()), id: \.offset) { _, l in Text(l).font(.callout) }
                if let opened {
                    Button("Open It") { model.openRoute = "#read/" + API.enc(opened); dismiss() }
                }
            } footer: {
                Text("EPUB, MOBI, AZW3 and FB2 go into Calibre, then Books, where Daf opens them. PDFs go to the Library.").foregroundStyle(.secondary)
            }
        }
        .formStyle(.grouped)
        .frame(width: 500)
        .toolbar {
            ToolbarItem(placement: .cancellationAction) { Button("Close") { dismiss() } }
            ToolbarItem(placement: .confirmationAction) {
                Button("Save") { Task { await save() } }.disabled(busy || !url.lowercased().hasPrefix("http"))
            }
        }
        .task {
            if let u = model.addURL { url = u; model.addURL = nil }
            else if let s = NSPasteboard.general.string(forType: .string)?.trimmingCharacters(in: .whitespacesAndNewlines), s.hasPrefix("http") { url = s }
            if !model.addFiles.isEmpty {
                let f = model.addFiles
                model.addFiles = []
                await upload(f)
            }
            folders = ((try? await API.shared.json("/api/feed/folders"))?.strings("folders") ?? []).filter { $0 != "Uncategorized" }
        }
    }

    private func save() async {
        let u = url.trimmingCharacters(in: .whitespacesAndNewlines)
        guard u.lowercased().hasPrefix("http") else { return }
        busy = true
        defer { busy = false }
        do {
            let r = J(try await API.shared.send("POST", "/api/add/link", ["url": u]))
            model.say(r?.s("where") == "library" || r?.b("queued") == true ? "Saved to the Library" : "It waits in Daf's inbox and goes in on the next sync")
            if case .library = model.place { model.reload() }
            dismiss()
        } catch { model.error = error.localizedDescription }
    }

    private func follow() async {
        busy = true
        defer { busy = false }
        do {
            let r = J(try await API.shared.send("POST", "/api/add/feed", ["url": url.trimmingCharacters(in: .whitespacesAndNewlines), "folder": folder]))
            lines.append("Following \(r?.s("name") ?? "the site"). New posts show up in the Feed after the next sync.")
            url = ""
            await model.loadSources()
        } catch { lines.append(error.localizedDescription) }
    }

    private func choose() {
        let p = NSOpenPanel()
        p.allowsMultipleSelection = true
        p.allowedContentTypes = Self.kinds.compactMap { UTType(filenameExtension: $0) }
        if p.runModal() == .OK { let urls = p.urls; Task { await upload(urls) } }
    }

    /// One after another, each with its own line.
    private func upload(_ urls: [URL]) async {
        for u in urls where Self.addable(u) {
            let k = lines.count
            lines.append("Sending \(u.lastPathComponent)…")
            guard let data = try? Data(contentsOf: u) else { lines[k] = "\(u.lastPathComponent) didn't open."; continue }
            do {
                let r = J(try await API.shared.uploadFile("/api/add/file", name: u.lastPathComponent, data: data))
                if r?.s("where") == "books" {
                    lines[k] = "\(r?.s("name") ?? u.lastPathComponent) is on its way into Calibre. It shows up under Books in a few minutes, once Calibre-Web has taken it in and Daf has synced."
                } else {
                    lines[k] = "\(u.lastPathComponent) is saved to the Library." + (r?.s("id") == nil ? " It shows up after the next sync." : "")
                    opened = r?.s("id") ?? opened
                    if case .library = model.place { model.reload() }
                }
            } catch { lines[k] = u.lastPathComponent + ": " + error.localizedDescription }
        }
        for u in urls where !Self.addable(u) { lines.append("\(u.lastPathComponent) isn't a book or a PDF.") }
    }

    /// The files in a drop, on the main thread.
    static func files(_ providers: [NSItemProvider], _ then: @escaping @MainActor ([URL]) -> Void) {
        var urls: [URL] = []
        let group = DispatchGroup()
        for p in providers where p.hasItemConformingToTypeIdentifier(UTType.fileURL.identifier) {
            group.enter()
            _ = p.loadObject(ofClass: URL.self) { u, _ in
                DispatchQueue.main.async {
                    if let u { urls.append(u) }
                    group.leave()
                }
            }
        }
        group.notify(queue: .main) { MainActor.assumeIsolated { then(urls) } }
    }
}

extension AppModel {
    /// Something dropped on the window: books and PDFs, or a link, go to Add to Daf.
    func dropped(_ providers: [NSItemProvider]) -> Bool {
        if providers.contains(where: { $0.hasItemConformingToTypeIdentifier(UTType.fileURL.identifier) }) {
            AddSheet.files(providers) { [weak self] urls in
                guard let self else { return }
                let books = urls.filter(AddSheet.addable)
                guard !books.isEmpty else { self.say("Daf takes books (EPUB, MOBI, AZW3, FB2, CBZ) and PDFs"); return }
                self.addFiles = books
                self.sheet = .addLink
            }
            return true
        }
        guard let p = providers.first(where: { $0.canLoadObject(ofClass: URL.self) }) else { return false }
        _ = p.loadObject(ofClass: URL.self) { u, _ in
            DispatchQueue.main.async {
                MainActor.assumeIsolated {
                    guard let u, let s = u.scheme, s.hasPrefix("http") else { return }
                    self.addURL = u.absoluteString
                    self.sheet = .addLink
                }
            }
        }
        return true
    }

    /// ⌘V with nothing to paste into (the list, the page): a link, or books and PDFs copied in the
    /// Finder, go to Add to Daf. Anything else is left to the window.
    static func watchPaste() {
        NSEvent.addLocalMonitorForEvents(matching: .keyDown) { e in
            guard e.modifierFlags.intersection(.deviceIndependentFlagsMask) == .command, e.charactersIgnoringModifiers == "v",
                  let w = NSApp.keyWindow, w.identifier?.rawValue.hasPrefix("main") == true, w.attachedSheet == nil else { return e }
            if let tv = w.firstResponder as? NSTextView, tv.isEditable { return e }
            return AppModel.shared.pasted() ? nil : e
        }
    }

    /// What's on the pasteboard, if it's for Add to Daf: books and PDFs, or one link.
    func pasted(from pb: NSPasteboard = .general) -> Bool {
        let files = (pb.readObjects(forClasses: [NSURL.self], options: [.urlReadingFileURLsOnly: true]) as? [URL] ?? []).filter(AddSheet.addable)
        if !files.isEmpty { addFiles = files; sheet = .addLink; return true }
        guard let s = pb.string(forType: .string)?.trimmingCharacters(in: .whitespacesAndNewlines),
              s.range(of: "^https?://\\S+$", options: .regularExpression) != nil else { return false }
        addURL = s
        sheet = .addLink
        return true
    }
}
