import SwiftUI

/// File › Add a Link…: a link into the Library, read by Daf (/api/add/link).
struct AddLinkSheet: View {
    @Environment(AppModel.self) private var model
    @Environment(\.dismiss) private var dismiss
    @State private var url = ""
    @State private var busy = false

    var body: some View {
        Form {
            Section {
                TextField("Link", text: $url, prompt: Text("https://…"))
                    .onAppear {
                        if let s = NSPasteboard.general.string(forType: .string), s.hasPrefix("http") { url = s }
                    }
            } header: { Text("Add a link to the Library") } footer: {
                Text("Daf reads the page and keeps its text.").foregroundStyle(.secondary)
            }
        }
        .formStyle(.grouped)
        .frame(width: 440)
        .toolbar {
            ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() } }
            ToolbarItem(placement: .confirmationAction) {
                Button("Add") { Task { await add() } }.disabled(busy || !url.lowercased().hasPrefix("http"))
            }
        }
    }

    private func add() async {
        busy = true
        defer { busy = false }
        do {
            try await API.shared.send("POST", "/api/add/link", ["url": url.trimmingCharacters(in: .whitespaces)])
            model.say("Added to the Library")
            dismiss()
            if case .library = model.place { model.reload() }
        } catch { model.error = error.localizedDescription }
    }
}

/// File › Log Paper Minutes…: minutes read on paper, for today, yesterday or Shabbat (/api/paper).
struct PaperSheet: View {
    @Environment(AppModel.self) private var model
    @Environment(\.dismiss) private var dismiss
    @State private var minutes = 30
    @State private var pages = 0
    @State private var note = ""
    @State private var day = "today"

    var body: some View {
        Form {
            Section("Log paper minutes") {
                Stepper(value: $minutes, in: 1...720, step: 5) { LabeledContent("Minutes", value: "\(minutes)") }
                Stepper(value: $pages, in: 0...2000, step: 1) { LabeledContent("Pages", value: pages == 0 ? "—" : "\(pages)") }
                TextField("What I read (optional)", text: $note)
                Picker("When", selection: $day) {
                    Text("Today").tag("today")
                    Text("Yesterday").tag("yesterday")
                    Text("Shabbat").tag("shabbat")
                }
                .pickerStyle(.segmented)
            }
        }
        .formStyle(.grouped)
        .frame(width: 420)
        .toolbar {
            ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() } }
            ToolbarItem(placement: .confirmationAction) { Button("Log") { Task { await log() } } }
        }
    }

    private func log() async {
        var body: [String: Any] = ["minutes": minutes, "pages": pages, "note": note]
        if day == "shabbat" { body["shabbat"] = true; if note.isEmpty { body["note"] = "Shabbat" } }
        if day == "yesterday", let t = Calendar.current.date(byAdding: .day, value: -1, to: Date()) {
            let f = DateFormatter()
            f.dateFormat = "yyyy-MM-dd"
            body["date"] = f.string(from: t)
        }
        do {
            try await API.shared.send("POST", "/api/paper", body)
            model.say("Logged " + plural(minutes, "minute"))
            dismiss()
            model.reload()
        } catch { model.error = error.localizedDescription }
    }
}

/// A window for one thing at one spot: "#read/<doc>/hl:<id>" natively, a book or manga as the page.
struct RouteView: View {
    let route: String
    @State private var reader: ReaderModel?

    private var parts: [String] { route.drop { $0 == "#" }.split(separator: "/").map { $0.removingPercentEncoding.map(String.init) ?? String($0) } }

    var body: some View {
        Group {
            if parts.first == "mread", parts.count > 1 {
                MangaReader(id: parts[1])
            } else if parts.first == "ebook", parts.count > 1 {
                BookReaderView(id: parts[1])
            } else if parts.first == "pdf", parts.count > 1 {
                PDFPane(id: parts[1])
            } else if parts.first == "page", parts.count > 1 {
                WebPane(route: "#" + parts.dropFirst().map { API.enc($0) }.joined(separator: "/"))
            } else if parts.first == "read", parts.count > 1 {
                if let reader, reader.doc != nil { ArticleReader(model: reader) }
                else if let e = reader?.error { ContentUnavailableView("It didn't open", systemImage: "exclamationmark.triangle", description: Text(e)) }
                else { ProgressView().frame(maxWidth: .infinity, maxHeight: .infinity) }
            } else {
                WebPane(route: route)
            }
        }
        .frame(minWidth: 640, minHeight: 520)
        .navigationTitle(reader?.title ?? "Daf")
        .task(id: route) {
            guard parts.first == "read", parts.count > 1 else { return }
            let r = ReaderModel(id: parts[1])
            r.pendingReveal = parts.last.flatMap { $0.hasPrefix("hl:") ? String($0.dropFirst(3)) : nil }
            reader = r
            await r.load()
        }
        .onDisappear { reader?.stop() }
        .sheet(item: Binding(get: { reader?.editing }, set: { reader?.editing = $0 })) { e in
            NoteSheet(h: e.h, saved: { n in reader?.changed(e.id) { $0["user_note"] = n } })
        }
    }
}
