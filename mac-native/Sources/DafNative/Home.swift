import SwiftUI

/// The Library's home, as the page's: shelves of what to read (continue reading, recently added,
/// quick reads, long reads, recently highlighted, new in the Feed), each one hidden or shown.
struct HomeView: View {
    @Environment(AppModel.self) private var model
    @Environment(\.openWindow) private var openWindow
    @AppStorage("homeHidden") private var hidden = ""
    /// Its search: the whole Library (inbox, later and archive), found on the server.
    @State private var q = ""
    @State private var hits: [Item]?

    private static let shelves = [("continue", "Continue Reading"), ("recent", "Recently Added"), ("quick", "Quick Reads"),
                                  ("long", "Long Reads"), ("highlighted", "Recently Highlighted"), ("feed", "New in the Feed")]

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 26) {
                if !q.trimmingCharacters(in: .whitespaces).isEmpty {
                    found
                } else if let home = model.home {
                    ForEach(Self.shelves.filter { !hidden.split(separator: ",").contains(Substring($0.0)) }, id: \.0) { key, title in
                        let list = home.a(key).map(Item.init)
                        if !list.isEmpty {
                            VStack(alignment: .leading, spacing: 10) {
                                Text(title).font(.title3.weight(.semibold))
                                ScrollView(.horizontal, showsIndicators: false) {
                                    HStack(alignment: .top, spacing: 16) {
                                        ForEach(list) { item in card(item) }
                                    }
                                }
                            }
                        }
                    }
                } else {
                    ProgressView().frame(maxWidth: .infinity).padding(60)
                }
            }
            .padding(28)
        }
        .navigationTitle("Home")
        .searchable(text: $q, placement: .toolbar, prompt: "Search the Library")
        .task(id: q) {
            let words = q.trimmingCharacters(in: .whitespaces)
            guard !words.isEmpty else { hits = nil; return }
            try? await Task.sleep(nanoseconds: 300_000_000)
            guard !Task.isCancelled else { return }
            hits = (try? await API.shared.json("/api/docs?where=library&tab=any&every=1&limit=200&q=" + API.enc(words)))?.a("items").map(Item.init) ?? []
        }
        .toolbar {
            ToolbarItem {
                Menu {
                    ForEach(Self.shelves, id: \.0) { key, title in
                        Toggle(title, isOn: Binding(get: { !hidden.split(separator: ",").contains(Substring(key)) }, set: { on in
                            var h = hidden.split(separator: ",").map(String.init).filter { $0 != key }
                            if !on { h.append(key) }
                            hidden = h.joined(separator: ",")
                        }))
                    }
                } label: { Label("Shelves", systemImage: "slider.horizontal.3") }
                .help("Which shelves Home shows")
            }
            ToolbarItem {
                Button { model.refresh() } label: { Label("Sync Now", systemImage: "arrow.clockwise") }
                    .keyboardShortcut("r", modifiers: .command)
                    .help("Daf reads every source again")
            }
        }
    }

    /// What the search found, by where it is: Inbox, Later, Archive.
    @ViewBuilder private var found: some View {
        if let hits {
            if hits.isEmpty { Text("Nothing matches").font(.headline).foregroundStyle(.secondary).frame(maxWidth: .infinity).padding(40) }
            ForEach([("inbox", "Inbox"), ("later", "Later"), ("archive", "Archive")], id: \.0) { key, title in
                let these = hits.filter { ($0.status ?? "inbox") == key || (key == "inbox" && !["later", "archive"].contains($0.status ?? "")) }
                if !these.isEmpty {
                    VStack(alignment: .leading, spacing: 6) {
                        Text(title + " · \(these.count)").font(.title3.weight(.semibold))
                        VStack(spacing: 0) {
                            ForEach(these) { item in
                                Button { if let r = model.route(for: item) { openWindow(id: "route", value: r) } } label: { ItemRow(item: item).contentShape(Rectangle()) }
                                    .buttonStyle(.plain)
                                Divider()
                            }
                        }
                    }
                }
            }
        } else { ProgressView().frame(maxWidth: .infinity).padding(60) }
    }

    private func card(_ item: Item) -> some View {
        Button { if let r = model.route(for: item) ?? (item.isBook ? nil : "#read/" + API.enc(item.id)) { openWindow(id: "route", value: r) } } label: {
            VStack(alignment: .leading, spacing: 6) {
                ZStack(alignment: .bottomLeading) {
                    Group {
                        if let t = item.thumb ?? (item.j.b("has_cover") ? "/api/cover/" + API.enc(item.id) : nil) {
                            AsyncImage(url: API.shared.url(t)) { p in
                                if let i = p.image { i.resizable().aspectRatio(contentMode: .fill) } else { Color.secondary.opacity(0.08) }
                            }
                        } else {
                            ZStack {
                                Color.daf.opacity(0.12)
                                Text(String(item.title.prefix(1))).font(.system(size: 40, weight: .semibold, design: .serif)).foregroundStyle(Color.daf)
                            }
                        }
                    }
                    .frame(width: 180, height: item.isBook ? 240 : 112)
                    .clipShape(RoundedRectangle(cornerRadius: 8))
                    if item.progress > 1 {
                        Rectangle().fill(Color.daf).frame(width: 180 * min(1, item.progress / 100), height: 3)
                    }
                }
                Text(item.title).font(.system(.callout, design: .serif).weight(.semibold)).lineLimit(2).frame(width: 180, alignment: .leading)
                Text([item.source, item.mins.map { "\($0) min" }, item.j.i("highlights").map { plural($0, "highlight") }].compactMap { $0 }.joined(separator: " · "))
                    .font(.caption).foregroundStyle(.secondary).lineLimit(1).frame(width: 180, alignment: .leading)
            }
        }
        .buttonStyle(.plain)
        .contextMenu { ItemActions(item: item) }
    }
}

/// Article › Edit the Title and Author…
struct MetaSheet: View {
    let reader: ReaderModel
    @Environment(\.dismiss) private var dismiss
    @State private var title = ""
    @State private var author = ""

    var body: some View {
        Form {
            Section("The title and author") {
                TextField("Title", text: $title)
                TextField("Author", text: $author)
            }
        }
        .formStyle(.grouped)
        .frame(width: 440)
        .onAppear { title = reader.doc?.s("title") ?? ""; author = reader.doc?.s("author") ?? "" }
        .toolbar {
            ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() } }
            ToolbarItem(placement: .confirmationAction) {
                Button("Save") { Task { if await reader.editMeta(title: title, author: author) { dismiss() } } }
                    .disabled(title.trimmingCharacters(in: .whitespaces).isEmpty)
            }
        }
    }
}
