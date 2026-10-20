import SwiftUI

/// A list's filters, as the page's Filter has them: length, when it came, highlighted, not started.
struct ListFilter: Equatable {
    var length = ""         // "", "0-10", "10-30", "30-"
    var since = 0           // days
    var hl = false
    var fresh = false

    var isEmpty: Bool { self == ListFilter() }

    /// As /api/docs takes them (and a saved view keeps them).
    var dict: [String: Any] {
        var d: [String: Any] = [:]
        let p = length.split(separator: "-", omittingEmptySubsequences: false)
        if p.count == 2 {
            if let a = Int(p[0]), a > 0 { d["minlen"] = a }
            if let b = Int(p[1]) { d["maxlen"] = b }
        }
        if since > 0 { d["since"] = since }
        if hl { d["hl"] = 1 }
        if fresh { d["fresh"] = 1 }
        return d
    }

    static let lengths = [("", "Any Length"), ("0-10", "Under 10 Minutes"), ("10-30", "10 to 30 Minutes"), ("30-", "Over 30 Minutes")]
    static let times = [(0, "Any Time"), (1, "Today"), (7, "This Week"), (30, "This Month")]
}

// MARK: the list's toolbar

/// Order and filters, and keeping the list as a view in the sidebar.
struct ListOptionsMenu: View {
    @Environment(AppModel.self) private var model

    var body: some View {
        @Bindable var model = model
        let feed: Bool = { if case .feed = model.place { return true }; if case .feedSource = model.place { return true }; return false }()
        let active = !model.listFilter.isEmpty || model.tag != nil
        Menu {
            if case .view(let id)? = model.place {
                Text("A saved view keeps its own order and filters")
                Button("Remove This View", role: .destructive) { Task { await model.removeView(id) } }
            } else {
                Picker("Order", selection: feed ? $model.sortFeed : $model.sortLibrary) {
                    ForEach(AppModel.sorts, id: \.0) { Text($0.1).tag($0.0) }
                }
                .pickerStyle(.inline)
                Divider()
                Picker("Length", selection: $model.listFilter.length) {
                    ForEach(ListFilter.lengths, id: \.0) { Text($0.1).tag($0.0) }
                }
                Picker("Added", selection: $model.listFilter.since) {
                    ForEach(ListFilter.times, id: \.0) { Text($0.1).tag($0.0) }
                }
                Toggle("Highlighted", isOn: $model.listFilter.hl)
                Toggle("Not Started", isOn: $model.listFilter.fresh)
                if !feed {
                    let tags = tagsHere
                    if !tags.isEmpty || model.tag != nil {
                        Picker("Tag", selection: $model.tag) {
                            Text("All Tags").tag(String?.none)
                            ForEach(tags, id: \.self) { Text($0).tag(String?.some($0)) }
                        }
                    }
                }
                if active {
                    Button("Clear the Filters") { model.listFilter = ListFilter(); model.tag = nil }
                }
                Divider()
                Button("Save as View…") { model.sheet = .saveView }
                    .disabled(model.currentView(named: "") == nil)
            }
        } label: {
            Label("Order and Filters", systemImage: active ? "line.3.horizontal.decrease.circle.fill" : "line.3.horizontal.decrease.circle")
        }
        .help("Order and filters")
    }

    /// The tags in this list, most used first.
    private var tagsHere: [String] {
        var n: [String: Int] = [:]
        for i in model.items { for t in i.j.strings("tags") { n[t, default: 0] += 1 } }
        return n.keys.sorted { (n[$0]!, $1) > (n[$1]!, $0) }
    }
}

// MARK: several chosen

/// What's open when several are chosen: how many, and what can be done to all of them.
struct BulkPane: View {
    @Environment(AppModel.self) private var model
    let items: [Item]

    var body: some View {
        let mins = items.compactMap(\.mins).reduce(0, +)
        VStack(spacing: 14) {
            Image(systemName: "square.stack.3d.up").font(.system(size: 46, weight: .light)).foregroundStyle(.secondary)
            Text("\(items.count) chosen").font(.title2.weight(.semibold))
            if mins > 0 { Text("About " + plural(mins, "minute") + " of reading").foregroundStyle(.secondary) }
            HStack {
                if items.allSatisfy({ $0.whereIn == "feed" }) {
                    Button("Mark Seen") { Task { await model.bulk(items, "seen") } }
                } else {
                    Button("Archive") { Task { await model.bulk(items, "archive") } }
                    Button("Read Later") { Task { await model.bulk(items, "later") } }
                }
                Button("Send to Kindle") { Task { await model.sendToKindle(items.map(\.id)) } }
                Button("Delete", role: .destructive) { Task { await model.bulk(items, "deleted") } }
            }
            .controlSize(.large)
            .padding(.top, 6)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}

/// The right-click menu for several at once.
struct BulkActions: View {
    @Environment(AppModel.self) private var model
    let items: [Item]

    var body: some View {
        if items.allSatisfy({ $0.whereIn == "feed" }) {
            Button("Mark \(items.count) Seen") { Task { await model.bulk(items, "seen") } }
            Button("Mark \(items.count) Unseen") { Task { await model.bulk(items, "unseen") } }
        } else {
            Button("Archive \(items.count)") { Task { await model.bulk(items, "archive") } }
            Button("Move \(items.count) to Later") { Task { await model.bulk(items, "later") } }
            Button("Move \(items.count) to the Inbox") { Task { await model.bulk(items, "inbox") } }
        }
        Divider()
        Button("Send \(items.count) to Kindle") { Task { await model.sendToKindle(items.map(\.id)) } }
        Divider()
        Button("Delete \(items.count)", role: .destructive) { Task { await model.bulk(items, "deleted") } }
    }
}

// MARK: the sidebar's views and shelves

struct ViewsSection: View {
    @Environment(AppModel.self) private var model

    var body: some View {
        if !model.views.isEmpty {
            Section("Views") {
                ForEach(model.views, id: \.self) { v in
                    Label(v.s("name") ?? "View", systemImage: "line.3.horizontal.decrease.circle")
                        .tag(Place.view(v.s("id") ?? ""))
                        .contextMenu { Button("Remove the View", role: .destructive) { Task { await model.removeView(v.s("id") ?? "") } } }
                }
            }
        }
    }
}

/// Books, opening onto its shelves.
struct BooksRow: View {
    @Environment(AppModel.self) private var model
    @AppStorage("shelvesOpen") private var open = false

    var body: some View {
        if model.shelves.isEmpty {
            books
        } else {
            DisclosureGroup(isExpanded: $open) {
                ForEach(model.shelves, id: \.self) { s in
                    Label(s.s("name") ?? "Shelf", systemImage: s.b("hardcover") ? "list.star" : "books.vertical")
                        .badge(s.i("count") ?? 0)
                        .tag(Place.shelf(s.s("id") ?? ""))
                        .contextMenu {
                            Button("Rename…") { model.sheet = .renameShelf(s.s("id") ?? "") }
                            Button("Delete the Shelf", role: .destructive) { Task { await model.deleteShelf(s.s("id") ?? "") } }
                                .disabled(s.b("hardcover"))
                            Divider()
                            Button("New Shelf…") { model.sheet = .newShelf(nil) }
                        }
                }
            } label: { books }
        }
    }

    private var books: some View {
        Label("Books", systemImage: "books.vertical")
            .tag(Place.books)
            .contextMenu { Button("New Shelf…") { model.sheet = .newShelf(nil) } }
    }
}

/// The book page's Shelves menu: each shelf ticked when the book is on it.
struct ShelvesMenu: View {
    @Environment(AppModel.self) private var model
    let book: String
    @State private var on: Set<String> = []

    var body: some View {
        Menu {
            ForEach(model.shelves, id: \.self) { s in
                let id = s.s("id") ?? ""
                Toggle(s.s("name") ?? "Shelf", isOn: Binding(get: { on.contains(id) }, set: { v in
                    Task { if await model.shelve(book, on: id, v) { if v { on.insert(id) } else { on.remove(id) } } }
                }))
            }
            if !model.shelves.isEmpty { Divider() }
            Button("New Shelf…") { model.sheet = .newShelf(book) }
        } label: { Label(on.isEmpty ? "Shelves" : "On \(on.count == 1 ? "a shelf" : "\(on.count) shelves")", systemImage: "books.vertical") }
        .fixedSize()
        .task(id: model.shelves.map { "\($0.s("id") ?? "")\($0.i("count") ?? 0)" }.joined()) { await membership() }
    }

    /// Daf doesn't say which shelves a book is on, so each shelf is asked.
    private func membership() async {
        var have = Set<String>()
        for s in model.shelves {
            guard let id = s.s("id"), let j = try? await API.shared.json("/api/shelves/" + API.enc(id)) else { continue }
            if j.a("books").contains(where: { $0.s("id") == book }) { have.insert(id) }
        }
        on = have
    }
}

// MARK: sheets

struct SaveViewSheet: View {
    @Environment(AppModel.self) private var model
    @Environment(\.dismiss) private var dismiss
    @State private var name = ""

    var body: some View {
        Form {
            Section {
                TextField("Name", text: $name)
            } header: { Text("Save this list as a view") } footer: {
                Text("It keeps the list's order, filters and tag, and sits in the sidebar, here and in the page.").foregroundStyle(.secondary)
            }
        }
        .formStyle(.grouped)
        .frame(width: 420)
        .onAppear { name = model.title(model.place) }
        .toolbar {
            ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() } }
            ToolbarItem(placement: .confirmationAction) {
                Button("Save") { Task { if await model.saveCurrentView(named: name.trimmingCharacters(in: .whitespaces)) { dismiss() } } }
                    .disabled(name.trimmingCharacters(in: .whitespaces).isEmpty)
            }
        }
    }
}

/// A new shelf, or a shelf renamed.
struct ShelfSheet: View {
    @Environment(AppModel.self) private var model
    @Environment(\.dismiss) private var dismiss
    var shelf: String? = nil
    var book: String? = nil
    @State private var name = ""

    var body: some View {
        Form {
            Section(shelf == nil ? "A new shelf" : "Rename the shelf") {
                TextField("Name", text: $name)
            }
        }
        .formStyle(.grouped)
        .frame(width: 400)
        .onAppear { if let shelf { name = model.shelves.first { $0.s("id") == shelf }?.s("name") ?? "" } }
        .toolbar {
            ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() } }
            ToolbarItem(placement: .confirmationAction) {
                Button(shelf == nil ? "Make It" : "Rename") {
                    let n = name.trimmingCharacters(in: .whitespaces)
                    Task {
                        let ok = if let shelf { await model.renameShelf(shelf, to: n) } else { await model.newShelf(n, with: book) }
                        if ok { dismiss() }
                    }
                }
                .disabled(name.trimmingCharacters(in: .whitespaces).isEmpty)
            }
        }
    }
}
