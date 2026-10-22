import SwiftUI

/// Hardcover on a book's page, as the page's (web/hardcover.js): find the book there and link it, put
/// it on a shelf, its status and rating, Finished with the date.
struct HardcoverSection: View {
    @Environment(AppModel.self) private var model
    let bookID: String
    let title: String
    @State private var s: J?
    @State private var hits: [J]?
    @State private var query = ""
    @State private var finishing = false
    @State private var failed: String?

    static let statuses = [(1, "Want to Read"), (2, "Reading"), (3, "Read"), (4, "Paused"), (5, "Did Not Finish")]

    var body: some View {
        Panel("Hardcover") {
            if let failed {
                Text(failed).font(.callout).foregroundStyle(.secondary)
            } else if let s {
                if !s.b("linked") {
                    Text("This book isn't linked to Hardcover yet.").font(.callout).foregroundStyle(.secondary)
                    if hits == nil { Button("Find It on Hardcover") { Task { await find(nil) } } }
                    else { results }
                } else if !s.b("on_shelf") {
                    HStack {
                        Button("Add as Want to Read") { Task { await put(["status_id": 1], "On your Hardcover shelves") } }
                        Button("Add as Reading") { Task { await put(["status_id": 2], "On your Hardcover shelves") } }
                    }
                } else {
                    HStack(spacing: 12) {
                        Picker("Status", selection: Binding(get: { s.i("status_id") ?? 1 }, set: { v in
                            if v == 3 { finishing = true } else { Task { await put(["status_id": v], (Self.statuses.first { $0.0 == v }?.1 ?? "") + ", on Hardcover") } }
                        })) { ForEach(Self.statuses, id: \.0) { Text($0.1).tag($0.0) } }
                        .fixedSize()
                        if s.i("status_id") == 3 {
                            Stars(value: s.d("rating") ?? 0) { v in Task { await put(["rating": v], "\(v.formatted()) stars on Hardcover") } }
                        } else {
                            Button("Finished") { finishing = true }.buttonStyle(.borderedProminent)
                        }
                    }
                    Text([s.i("progress_pages").map { p in "Page \(p)" + (s.i("pages").map { " of \($0)" } ?? "") }, s.s("finished_at").map { "Finished " + String($0.prefix(10)) }]
                        .compactMap { $0 }.joined(separator: " · ")).font(.caption).foregroundStyle(.secondary)
                }
                if let u = s.s("url"), let url = URL(string: u) { Link("Open on Hardcover", destination: url).font(.callout) }
            } else {
                ProgressView().controlSize(.small)
            }
        }
        .task(id: bookID) { await load() }
        .sheet(isPresented: $finishing) { FinishSheet(bookID: bookID, title: title) { await load() } }
    }

    @ViewBuilder private var results: some View {
        if let hits {
            if hits.isEmpty { Text("Nothing found on Hardcover.").font(.callout).foregroundStyle(.secondary) }
            ForEach(hits, id: \.self) { h in
                Button { Task { await link(h) } } label: {
                    HStack(spacing: 10) {
                        AsyncImage(url: h.s("image").flatMap(URL.init(string:))) { p in
                            if let i = p.image { i.resizable().aspectRatio(contentMode: .fill) } else { Color.secondary.opacity(0.1) }
                        }
                        .frame(width: 32, height: 48).clipShape(RoundedRectangle(cornerRadius: 3))
                        VStack(alignment: .leading, spacing: 2) {
                            Text(h.s("title") ?? "").font(.callout.weight(.semibold))
                            Text([h.s("author"), h.s("year"), h.b("isbn") ? "the same ISBN" : h.i("readers").map { plural($0, "reader") }].compactMap { $0 }.joined(separator: " · "))
                                .font(.caption).foregroundStyle(.secondary)
                        }
                        Spacer()
                        Text("Link").font(.caption).foregroundStyle(.tint)
                    }
                    .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
            }
            HStack {
                TextField("Search Hardcover", text: $query).textFieldStyle(.roundedBorder).onSubmit { Task { await find(query) } }
                Button("Search") { Task { await find(query) } }
            }
        }
    }

    private func load() async {
        do { s = try await API.shared.json("/api/hardcover/book/" + API.enc(bookID)); failed = nil }
        catch { failed = "Hardcover: " + error.localizedDescription }
    }

    private func find(_ q: String?) async {
        let path = "/api/hardcover/search?" + (q.map { "q=" + API.enc($0) } ?? "book_id=" + API.enc(bookID))
        hits = (try? await API.shared.json(path))?.a("hits") ?? []
    }

    private func link(_ h: J) async {
        guard let hid = h.i("id") else { return }
        do {
            try await API.shared.send("POST", "/api/hardcover/book/\(API.enc(bookID))/link", ["hc_book_id": hid])
            model.say("Linked to Hardcover")
            hits = nil
            await load()
        } catch { model.error = error.localizedDescription }
    }

    private func put(_ body: [String: Any], _ said: String) async {
        do {
            try await API.shared.send("PUT", "/api/hardcover/book/" + API.enc(bookID), body)
            model.say(said)
            await load()
        } catch { model.error = error.localizedDescription }
    }
}

/// Half stars, clicked to choose.
struct Stars: View {
    let value: Double
    let set: (Double) -> Void
    var body: some View {
        HStack(spacing: 2) {
            ForEach(1...5, id: \.self) { k in
                let on = value >= Double(k) ? "star.fill" : value >= Double(k) - 0.5 ? "star.leadinghalf.filled" : "star"
                Image(systemName: on).foregroundStyle(.yellow)
                    .overlay(HStack(spacing: 0) {
                        Color.clear.contentShape(Rectangle()).onTapGesture { set(Double(k) - 0.5) }
                        Color.clear.contentShape(Rectangle()).onTapGesture { set(Double(k)) }
                    })
            }
        }
        .help("Half stars: click the left or right half")
    }
}

/// Finished: Read on Hardcover, with a rating (or none) and the date.
struct FinishSheet: View {
    @Environment(AppModel.self) private var model
    @Environment(\.dismiss) private var dismiss
    let bookID: String
    let title: String
    let after: () async -> Void
    @State private var rating = 0.0
    @State private var date = Date()
    @State private var busy = false

    var body: some View {
        Form {
            Section {
                LabeledContent("Your rating") {
                    HStack {
                        Stars(value: rating) { rating = $0 }
                        Button("No Rating") { rating = 0 }.buttonStyle(.link)
                    }
                }
                DatePicker("Finished on", selection: $date, displayedComponents: .date)
            } header: { Text("Finished " + PaperPages.short(title)) } footer: {
                Text("Marks it Read on Hardcover, with the date. The vault note follows on its next sync.").foregroundStyle(.secondary)
            }
        }
        .formStyle(.grouped)
        .frame(width: 440)
        .toolbar {
            ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() } }
            ToolbarItem(placement: .confirmationAction) {
                Button(busy ? "Telling Hardcover…" : "Mark It Read") { Task { await finish() } }.disabled(busy)
            }
        }
    }

    private func finish() async {
        busy = true
        defer { busy = false }
        let f = DateFormatter()
        f.dateFormat = "yyyy-MM-dd"
        var body: [String: Any] = ["date": f.string(from: date)]
        body["rating"] = rating > 0 ? rating : NSNull()
        do {
            try await API.shared.send("POST", "/api/hardcover/book/\(API.enc(bookID))/finish", body)
            model.say("Read, on Hardcover" + (rating > 0 ? " · \(rating.formatted()) stars" : ""))
            dismiss()
            await after()
        } catch { model.error = error.localizedDescription }
    }
}
