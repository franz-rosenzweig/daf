import Charts
import SwiftUI
import UniformTypeIdentifiers

/// The window: the sidebar, the list, and what's open, with the inspector beside it.
struct MainView: View {
    @MainActor static var watching = false
    @Environment(AppModel.self) private var model
    @Environment(\.openWindow) private var openWindow
    @Environment(\.openSettings) private var openSettings
    @Environment(\.undoManager) private var undoManager

    /// A place that's a page across the window (Today, Review, Stats…).
    @ViewBuilder private var page: some View {
        switch model.place {
        case .today: TodayView()
        case .review: ReviewView()
        case .home: HomeView()
        case .recovery: RecoveryView()
        case .podcasts: PodcastsView()
        case .sources: SourcesView()
        default: StatsView()
        }
    }

    /// What's open from a list.
    @ViewBuilder private var opened: some View {
        if model.place == .highlights {
            if let g = model.highlights.group { HighlightGroupView(group: g).id(HighlightsModel.key(g)) }
            else { ContentUnavailableView("No highlights", systemImage: "highlighter") }
        } else {
            Detail()
        }
    }

    /// The sidebar, as wide as full or mini asks.
    private var sidebar: some View {
        let mini = Side.shared.mini
        return Sidebar().navigationSplitViewColumnWidth(min: mini ? 54 : 190, ideal: mini ? 58 : 220, max: mini ? 64 : 320)
    }

    /// An article (or a PDF, a video, an episode) open from the list: no sidebar while it's read.
    private var reading: Bool {
        guard model.place?.isPage != true, model.place != .highlights, let item = model.selected else { return false }
        return item.isDoc
    }

    var body: some View {
        @Bindable var model = model
        Group {
            if model.place?.isPage == true {
                NavigationSplitView {
                    sidebar
                } detail: {
                    page
                        .frame(maxWidth: .infinity, maxHeight: .infinity)
                        .themed()
                        .toolbar { ToolbarItem(placement: .navigation) { SidebarButton() } }
                }
                .toolbar(removing: .sidebarToggle)
            } else {
                NavigationSplitView {
                    sidebar
                } content: {
                    Group {
                        switch model.place {
                        case .highlights: HighlightGroups()
                        case .torah: TorahList()
                        default: ItemList()
                        }
                    }
                    .navigationSplitViewColumnWidth(min: 300, ideal: 360, max: 520)
                    .themed()
                    .toolbar { ToolbarItem(placement: .navigation) { SidebarButton() } }
                } detail: {
                    opened
                        .frame(maxWidth: .infinity, maxHeight: .infinity)
                        .themed()
                }
                .toolbar(removing: .sidebarToggle)
            }
        }
        .overlay(alignment: .bottom) {
            VStack(spacing: 10) {
                if let t = model.toast {
                    HStack(spacing: 12) {
                        Text(t).font(.callout.weight(.medium))
                        if model.toastUndo { Button("Undo") { model.undoLast() }.buttonStyle(.borderless).font(.callout.weight(.semibold)) }
                    }
                    .padding(.horizontal, 16).padding(.vertical, 9)
                    .glassEffect(.regular, in: Capsule())
                    .transition(.move(edge: .bottom).combined(with: .opacity))
                }
                if Speaker.shared.on { SpeakerBar().transition(.move(edge: .bottom).combined(with: .opacity)) }
            }
            .padding(.bottom, 22)
        }
        .animation(.snappy, value: model.toast)
        .animation(.snappy, value: Speaker.shared.on)
        .onDrop(of: [.fileURL, .url], isTargeted: nil) { model.dropped($0) }
        .tint(Theme.shared.accent)
        .onAppear {
            model.undoManager = undoManager
            if !Self.watching { Self.watching = true; AppModel.watchPaste() }
        }
        .onChange(of: undoManager) { _, u in model.undoManager = u }
        .confirmationDialog("Unfollow \(model.confirmUnfollow.flatMap { model.feed($0)?.s("title") } ?? "the feed")?",
                            isPresented: Binding(get: { model.confirmUnfollow != nil }, set: { if !$0 { model.confirmUnfollow = nil } })) {
            Button("Unfollow", role: .destructive) {
                if let id = model.confirmUnfollow { Task { await model.unfollow(id) } }
                model.confirmUnfollow = nil
            }
        } message: { Text("What's unseen from it leaves the Feed. Highlighted items stay.") }
        .onChange(of: model.showSettings) { _, on in
            guard on else { return }
            openSettings()
            model.showSettings = false
        }
        .onChange(of: model.openRoute) { _, r in
            guard let r else { return }
            openWindow(id: "route", value: r)
            model.openRoute = nil
        }
        .sheet(item: $model.sheet) { s in
            switch s {
            case .addLink: AddSheet().environment(model)
            case .palette: PaletteSheet().environment(model)
            case .shortcuts: ShortcutsSheet()
            case .paper: PaperSheet().environment(model)
            case .feedback: FeedbackSheet().environment(model)
            case .follow: FollowSheet().environment(model)
            case .renameFeed(let id): RenameFeedSheet(id: id).environment(model)
            case .saveView: SaveViewSheet().environment(model)
            case .newShelf(let book): ShelfSheet(book: book).environment(model)
            case .renameShelf(let id): ShelfSheet(shelf: id).environment(model)
            }
        }
        .importsItemProviders([.image]) { PaperPages.take($0) }        // Continuity Camera: File › Import from iPhone
        .onChange(of: model.place) { _, _ in
            model.placeChanged()
            Side.shared.reading = reading
            Side.shared.applySoon()
        }
        .onChange(of: model.selection) { _, _ in Side.shared.reading = reading }
        .onAppear { Side.shared.applySoon() }
        .task {
            model.reload()
            await model.loadViews()
            await model.loadShelves()
        }
        .sheet(isPresented: $model.needsSignIn) { SignInView().environment(model) }
        .alert("Daf", isPresented: Binding(get: { model.error != nil }, set: { if !$0 { model.error = nil } })) {
            Button("OK") { model.error = nil }
        } message: { Text(model.error ?? "") }
    }
}

// MARK: lists

struct ItemList: View {
    @Environment(AppModel.self) private var model

    var body: some View {
        @Bindable var model = model
        List(selection: $model.multi) {
            if model.place == .books {
                ForEach(model.bookSections, id: \.0) { title, list in
                    Section(title) { ForEach(list) { item in ItemRow(item: item).tag(item.id) } }
                }
            } else {
                ForEach(model.shown) { item in ItemRow(item: item).tag(item.id) }
            }
        }
        .contextMenu(forSelectionType: Item.ID.self) { ids in
            let chosen = model.items.filter { ids.contains($0.id) }
            if chosen.count > 1 { BulkActions(items: chosen) } else if let one = chosen.first { ItemActions(item: one) }
        } primaryAction: { ids in
            if ids.count == 1, let item = model.items.first(where: { ids.contains($0.id) }), let r = model.route(for: item) { model.openRoute = r }
        }
        .listStyle(.inset)
        .themed(list: true)
        .onDrop(of: [.image], isTargeted: nil) { model.place == .paper ? PaperPages.take($0) : false }
        .navigationTitle(model.title(model.place))
        .navigationSubtitle(model.shown.isEmpty ? "" : model.multi.count > 1 ? "\(model.multi.count) of \(model.shown.count) chosen" : "\(model.shown.count)")
        .overlay {
            if model.shown.isEmpty && !model.loading {
                ContentUnavailableView(model.place == .search ? "Nothing found" : "Nothing here", systemImage: "tray")
            }
        }
        .toolbar {
            if case .kind = model.place {
                ToolbarItem {
                    Picker("Show", selection: $model.libraryTab) {
                        Text("Inbox").tag("inbox")
                        Text("Later").tag("later")
                        Text("Archive").tag("archive")
                    }
                    .pickerStyle(.segmented)
                    .fixedSize()
                }
            }
            if case .library = model.place {
                ToolbarItem {
                    Picker("Kind", selection: $model.kind) {
                        Text("Everything").tag("")
                        Text("Articles").tag("article")
                        Text("Videos").tag("video")
                        Text("Tweets").tag("tweet")
                        Text("PDFs").tag("pdf")
                        Text("Emails").tag("email")
                    }
                    .pickerStyle(.menu)
                    .fixedSize()
                }
            }
            if let p = model.place, isFeed(p) {
                ToolbarItem {
                    Picker("Show", selection: $model.feedTab) {
                        Text("Unseen").tag("unseen")
                        Text("Seen").tag("seen")
                    }
                    .pickerStyle(.segmented)
                    .fixedSize()
                }
                ToolbarItem {
                    Button { Task { await model.markSeen(p) } } label: { Label("Mark All Seen", systemImage: "checkmark.circle.badge.questionmark") }
                        .help("Mark everything here seen")
                        .disabled(model.feedTab == "seen")
                }
            }
            if model.place.map(hasDocs) == true {
                ToolbarItem { ListOptionsMenu() }
            }
            if model.viewChanged {
                ToolbarItem {
                    Button("Update the View") { Task { await model.updateView() } }
                        .help("Keep this order and these filters in the view")
                }
            }
            if model.place == .paper {
                ToolbarItem {
                    Button { PaperPages.choose() } label: { Label("Add a Photo of a Page", systemImage: "camera.badge.ellipsis") }
                        .help("Add a photo of a page you marked (or use File › Import from iPhone)")
                }
            }
            ToolbarItem {
                Button { model.refresh() } label: { Label("Refresh", systemImage: "arrow.clockwise") }
                    .keyboardShortcut("r", modifiers: .command)
            }
        }
        .onChange(of: model.kind) { _, _ in model.reload() }
        .onChange(of: model.listFilter) { _, _ in model.reload() }
        .onChange(of: model.viewFilter) { _, _ in if case .view = model.place { model.reload() } }
        .onChange(of: model.viewSort) { _, _ in if case .view = model.place { model.reload() } }
        .onChange(of: model.sortLibrary) { _, _ in model.reload() }
        .onChange(of: model.sortFeed) { _, _ in model.reload() }
        .onChange(of: model.feedTab) { _, _ in model.reload() }
        .onKeyPress(characters: CharacterSet(charactersIn: "lsftdzjk"), phases: .down) { press in listKey(press.characters) }
        .safeAreaInset(edge: .top) {
            if model.place == .books {
                TextField("Search by title or author", text: $model.booksQuery)
                    .textFieldStyle(.roundedBorder)
                    .padding(.horizontal, 12).padding(.vertical, 6)
            }
            if let p = model.place, isFeed(p), let n = model.counts?.i("expired_in_daf"), n > 0, model.feedTab == "unseen" {
                HStack(spacing: 10) {
                    Text("FreshRSS still counts " + plural(n, "post") + " as unread that Daf has let go.").font(.caption).foregroundStyle(.secondary)
                    Spacer()
                    Button("Mark Them Read in FreshRSS Too") { Task { await model.expireInFreshRSS() } }.controlSize(.small)
                }
                .padding(.horizontal, 12).padding(.vertical, 6)
                .background(.bar)
            }
        }
        .onKeyPress("e") {
            let chosen = model.chosen.filter(\.isDoc)
            if chosen.count > 1 { Task { await model.bulk(chosen, chosen.allSatisfy { $0.whereIn == "feed" } ? "seen" : "archive") }; return .handled }
            guard let item = model.selected, !item.isBook else { return .ignored }
            Task { await model.done(item) }
            return .handled
        }
        .onDeleteCommand {
            let chosen = model.chosen.filter(\.isDoc)
            if chosen.count > 1 { Task { await model.bulk(chosen, "deleted") }; return }
            guard let item = model.selected, item.isDoc else { return }
            Task { await model.delete(item) }
        }
    }
}

extension ItemList {
    /// The page's list keys (keys.js, scope list).
    func listKey(_ ch: String) -> KeyPress.Result {
        let item = model.selected
        switch ch {
        case "j": model.step(1)
        case "k": model.step(-1)
        case "l": if let item, item.whereIn != "feed", item.isDoc { Task { await model.later(item) } } else { return .ignored }
        case "s": if let item, item.whereIn == "feed" { Task { await model.saveToLibrary(item) } } else { return .ignored }
        case "f": if let item, item.whereIn != "feed", item.isDoc { Task { await model.star(item) } } else { return .ignored }
        case "t": model.showInspector = true; model.focusTags += 1
        case "d": if let item, item.isDoc { Task { await model.delete(item) } } else { return .ignored }
        case "z": model.undoLast()
        default: return .ignored
        }
        return .handled
    }
}

private func isFeed(_ p: Place) -> Bool {
    switch p {
    case .feed, .feedSource: return true
    default: return false
    }
}

/// A list of articles and the like, which has an order and filters (not books, manga or search).
private func hasDocs(_ p: Place) -> Bool {
    switch p {
    case .library, .kind, .shortlist, .feed, .feedSource, .view: return true
    default: return false
    }
}

struct ItemRow: View {
    let item: Item

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            VStack(alignment: .leading, spacing: 3) {
                Text(item.title)
                    .font(.system(.body, design: .serif).weight(.semibold))
                    .lineLimit(2)
                HStack(spacing: 6) {
                    if let s = item.source { Text(s).lineLimit(1) }
                    if let m = item.mins { Text("· \(m) min") }
                    if item.progress > 1 { Text("· \(Int(item.progress))%") }
                }
                .font(.caption)
                .foregroundStyle(.secondary)
            }
            Spacer(minLength: 0)
            Thumb(path: item.thumb, book: item.isBook)
        }
        .padding(.vertical, 4)
    }
}

struct Thumb: View {
    let path: String?
    var book = false

    var body: some View {
        if let path {
            AsyncImage(url: API.shared.url(path)) { phase in
                if let image = phase.image { image.resizable().aspectRatio(contentMode: .fill) }
                else { Color.secondary.opacity(0.08) }
            }
            .frame(width: book ? 40 : 54, height: book ? 60 : 54)
            .clipShape(RoundedRectangle(cornerRadius: book ? 3 : 6))
        }
    }
}

/// An article's … menu: what the bar doesn't show, as the page's.
struct ReaderMore: View {
    @Environment(AppModel.self) private var model
    let item: Item

    var body: some View {
        if item.whereIn != "feed" {
            Button(item.j.b("starred") ? "Remove from the Shortlist" : "Add to the Shortlist") { Task { await model.star(item) } }
        }
        if item.whereIn == "library" {
            Button(item.status == "later" ? "Back to Inbox" : "Read Later") { Task { await model.later(item) } }
        }
        if let u = item.j.s("url"), let url = URL(string: u) {
            Button("Open the Original") { NSWorkspace.shared.open(url) }
            Button("Copy the Link") { NSPasteboard.general.clearContents(); NSPasteboard.general.setString(u, forType: .string) }
        }
        Button("Focus Mode") { Focus.shared.toggle() }
        Divider()
        Button("Next in the List") { model.step(1) }
        Button("Previous in the List") { model.step(-1) }
        Divider()
        if let r = model.reader, r.doc != nil, !r.playsMedia {
            Button("Read Aloud from Here") { r.listen(from: r.textView?.selectedRange().location ?? 0) }
            Button("Reset Reading Progress") { Task { await r.resetProgress() } }
        }
        Button("Edit the Title and Author…") { model.editMeta = true }
        Button("Send to Kindle") { Task { await model.sendToKindle([item.id]) } }
        if let r = model.route(for: item) { Button("Open in a New Window") { model.openRoute = r } }
        Divider()
        Button("Delete", role: .destructive) { Task { await model.delete(item) } }
    }
}

struct ItemActions: View {
    @Environment(AppModel.self) private var model
    let item: Item

    var body: some View {
        if !item.isBook {
            if item.whereIn == "feed" {
                Button("Save to Library") { Task { await model.saveToLibrary(item) } }
                Button(item.status == "seen" ? "Back to Unseen" : "Mark Seen") { Task { await model.done(item) } }
            } else {
                Button(item.status == "later" ? "Back to Inbox" : "Read Later") { Task { await model.later(item) } }
                Button(item.status == "archive" ? "Back to Inbox" : "Archive") { Task { await model.done(item) } }
                Button(item.j.b("starred") ? "Remove from the Shortlist" : "Add to the Shortlist") { Task { await model.star(item) } }
            }
            if let u = item.j.s("url"), let url = URL(string: u) {
                Divider()
                Link("Open the Original", destination: url)
                Button("Copy the Link") { NSPasteboard.general.clearContents(); NSPasteboard.general.setString(u, forType: .string) }
            }
            Divider()
            if let r = model.route(for: item) { Button("Open in a New Window") { model.openRoute = r } }
            Button("Send to Kindle") { Task { await model.sendToKindle([item.id]) } }
            Divider()
            Button("Delete", role: .destructive) { Task { await model.delete(item) } }
        }
    }
}

// MARK: Today

struct Heading: View {
    let text: String
    init(_ text: String) { self.text = text }
    var body: some View { Text(text).font(.headline).foregroundStyle(.secondary) }
}

struct Ring: View {
    let today: J

    var body: some View {
        let main = today.o("main")
        let done = main?.d("done") ?? today.d("counted") ?? 0
        let target = max(1, main?.d("target") ?? today.d("goal") ?? 60)
        HStack(spacing: 18) {
            ZStack {
                Circle().stroke(.quaternary, lineWidth: 10)
                Circle().trim(from: 0, to: min(1, done / target))
                    .stroke(Color.daf, style: StrokeStyle(lineWidth: 10, lineCap: .round))
                    .rotationEffect(.degrees(-90))
                Text("\(Int(done))").font(.system(.title, design: .rounded).weight(.semibold)).monospacedDigit()
            }
            .frame(width: 84, height: 84)
            VStack(alignment: .leading, spacing: 4) {
                Text(main?.s("text") ?? "\(Int(done)) of \(Int(target)) minutes today").font(.headline)
                if let y = today.o("year30") {
                    Text("Year 30, day \((y.i("today_index") ?? 0) + 1) · \(String(format: "%.1f", y.d("total_hours") ?? 0)) hours so far")
                        .font(.subheadline).foregroundStyle(.secondary)
                }
                if let r = today.o("review"), let total = r.i("total"), total > 0 {
                    Text("Review: \(r.i("done") ?? 0) of \(total)").font(.subheadline).foregroundStyle(.secondary)
                }
            }
        }
        .padding(.vertical, 8)
    }
}

struct Week: View {
    let days: [J]

    var body: some View {
        Chart(Array(days.enumerated()), id: \.offset) { _, d in
            BarMark(x: .value("Day", String((d.s("date") ?? "").suffix(2))), y: .value("Minutes", d.d("minutes") ?? 0))
                .foregroundStyle((d.d("minutes") ?? 0) >= (d.d("target") ?? 60) ? Color.daf : Color.daf.opacity(0.45))
            if let t = days.last?.d("target") {
                RuleMark(y: .value("Goal", t)).lineStyle(StrokeStyle(lineWidth: 1, dash: [3, 3])).foregroundStyle(.secondary)
            }
        }
        .chartYAxis { AxisMarks(position: .leading) }
        .frame(height: 120)
        .padding(.vertical, 6)
    }
}

// MARK: what's open

struct Detail: View {
    @Environment(AppModel.self) private var model
    @AppStorage("torahLang") private var torahLang = "both"
    @State private var showAa = false

    var body: some View {
        @Bindable var model = model
        Group {
            if model.multi.count > 1 {
                BulkPane(items: model.chosen)
            } else if let item = model.selected {
                Opened(item: item).id(item.id)
            } else {
                ContentUnavailableView("Nothing open", systemImage: "book", description: Text("Pick something from the list."))
            }
        }
        .toolbar {
            if let item = model.selected, item.kind == "torah" {
                ToolbarItem {
                    Picker("Language", selection: $torahLang) {
                        Text("Both").tag("both")
                        Text("עברית").tag("he")
                        Text("English").tag("en")
                    }
                    .pickerStyle(.segmented)
                    .fixedSize()
                    .help("The reading in Hebrew, English or both")
                }
            }
            // as the page's bar: Aa, Listen, Save (the Feed's, and an episode met only in AntennaPod), Done, …, the notebook
            if let item = model.selected, item.isDoc {
                ToolbarItemGroup {
                    Button { showAa.toggle() } label: { Label("Themes & Settings", systemImage: "textformat.size") }
                        .help("Themes & Settings")
                        .popover(isPresented: $showAa, arrowEdge: .bottom) { ThemesPanel() }
                    if let r = model.reader, r.doc != nil, !r.playsMedia {
                        let on = Speaker.shared.docID == r.id && Speaker.shared.playing
                        Button { r.listen() } label: { Label(on ? "Pause" : "Listen", systemImage: on ? "pause.circle" : "speaker.wave.2") }
                            .help(on ? "Pause (P)" : "Listen (P)")
                    }
                    if item.whereIn == "feed" || item.whereIn == "podcast" {     // podcast: an episode met only in AntennaPod
                        Button { Task { await model.saveToLibrary(item) } } label: { Label("Save to Library", systemImage: "tray.and.arrow.down") }
                            .help("Save to Library (S)")
                    }
                    if item.whereIn != "podcast" {
                        Button { Task { await model.done(item) } } label: {
                            Label(item.whereIn == "feed" ? "Mark Seen" : "Done", systemImage: "checkmark.circle")
                        }
                        .help(item.whereIn == "feed" ? "Mark seen (E)" : "Done: to the Archive (E)")
                    }
                    Menu { ReaderMore(item: item) } label: { Label("More", systemImage: "ellipsis.circle") }
                        .help("More actions")
                    Button { model.showInspector.toggle() } label: { Label("Notebook", systemImage: "sidebar.right") }
                        .help("The notebook: highlights, the note and the tags (⌥⌘I)")
                        .keyboardShortcut("i", modifiers: [.command, .option])
                }
            }
        }
    }
}

struct Opened: View {
    @Environment(AppModel.self) private var model
    let item: Item
    @State private var reader: ReaderModel?
    @AppStorage("torahLang") private var torahLang = "both"

    var body: some View {
        @Bindable var model = model
        Group {
            switch (item.isBook, item.kind) {
            case (_, "series"): SeriesView(id: item.id)
            case (_, "paper"): PaperPageView(id: item.id)
            case (true, _): BookPage(id: item.id)
            case (_, "pdf") where item.j.b("has_pdf") || item.kind == "pdf": PDFPane(id: item.id)
            case (_, "manga"): WebPane(route: "#mread/" + API.enc(item.id))
            default:
                if let reader {
                    if let e = reader.error { ContentUnavailableView("It didn't open", systemImage: "exclamationmark.triangle", description: Text(e)) }
                    else if reader.doc == nil { ProgressView().frame(maxWidth: .infinity, maxHeight: .infinity) }
                    else if reader.playsMedia { VideoArticle(model: reader) }
                    else { ArticleReader(model: reader).overlay(alignment: .bottom) { MinutesLeft(model: reader) } }
                } else { ProgressView().frame(maxWidth: .infinity, maxHeight: .infinity) }
            }
        }
        .navigationTitle(item.title)
        .inspector(isPresented: $model.showInspector) {
            Inspector(item: item, reader: reader).inspectorColumnWidth(min: 240, ideal: 280, max: 380)
        }
        .sheet(item: Binding(get: { reader?.editing }, set: { reader?.editing = $0 })) { e in
            NoteSheet(h: e.h, saved: { n in reader?.changed(e.id) { $0["user_note"] = n } }).environment(model)
        }
        .sheet(item: Binding(get: { reader?.sheet }, set: { reader?.sheet = $0 })) { s in
            HLSheetView(sheet: s) { hid, fields in reader?.changed(hid) { raw in for (k, v) in fields { raw[k] = v } } }
        }
        .sheet(isPresented: Binding(get: { model.editMeta && reader != nil }, set: { model.editMeta = $0 })) {
            if let reader { MetaSheet(reader: reader) }
        }
        .task(id: item.id) {
            guard item.isDoc, !["pdf", "manga"].contains(item.kind) else { return }
            // the same article made again by SwiftUI (a list refreshing beside it): the one already open
            if let r = model.reader, r.id == item.id, r.doc != nil { reader = r; return }
            // a vault essay: Daf makes it readable first (/api/torah/essay)
            if let path = item.j.s("vault_essay"), !path.isEmpty {
                _ = try? await API.shared.send("POST", "/api/torah/essay", ["path": path])
            }
            let r = ReaderModel(id: item.id)
            reader = r
            model.reader = r
            await r.load()
        }
        .onDisappear { if model.selection != item.id { reader?.stop() } }
        .onChange(of: torahLang) { _, _ in if item.kind == "torah" { reader?.compose(keepPlace: true) } }
    }
}

struct Inspector: View {
    @Environment(AppModel.self) private var model
    let item: Item
    let reader: ReaderModel?
    /// For a PDF or a video, which have no reader: the doc's note and tags all the same.
    @State private var meta: ReaderModel?
    @State private var newTag = ""
    @State private var known: [String] = []
    @FocusState private var tagField: Bool
    @State private var question = ""
    @FocusState private var askField: Bool
    @FocusState private var noteField: Bool
    @State private var summarizing = false

    private var doc: ReaderModel? { reader ?? meta }

    var body: some View {
        let d = doc?.doc ?? item.j
        List {
            Section {
                Text(d.s("title") ?? item.title).font(.headline)
                if let s = d.s("source") { LabeledContent("From", value: s) }
                if let a = d.s("author") { LabeledContent("By", value: a) }
                if let m = d.i("mins") { LabeledContent("Length", value: "\(m) min") }
                if let u = d.s("url"), let url = URL(string: u) { Link("Open the original", destination: url) }
            }
            if let doc, doc.doc != nil {
                Section("Note") {
                    TextEditor(text: Binding(get: { doc.note }, set: { doc.write(note: $0) }))
                        .font(.callout)
                        .scrollContentBackground(.hidden)
                        .frame(minHeight: 64)
                        .focused($noteField)
                    if let p = doc.doc?.s("vault_path") {
                        LabeledContent("In the vault") { Button("Open in Obsidian") { doc.openInObsidian() }.buttonStyle(.link) }
                            .help(p)
                    }
                }
                Section("Tags") {
                    if !doc.tags.isEmpty {
                        Flow {
                            ForEach(doc.tags, id: \.self) { t in
                                HStack(spacing: 4) {
                                    Text(t)
                                    Image(systemName: "xmark.circle.fill")
                                        .foregroundStyle(Color.secondary)
                                        .contentShape(Circle())
                                        .onTapGesture { Task { await doc.set(tags: doc.tags.filter { $0 != t }) } }
                                        .help("Take the tag off")
                                }
                                .font(.caption)
                                .padding(.leading, 9)
                                .padding(.trailing, 5)
                                .padding(.vertical, 3)
                                .background(Capsule().fill(Color.daf.opacity(0.14)))
                                .contextMenu { Button("Take the Tag Off") { Task { await doc.set(tags: doc.tags.filter { $0 != t }) } } }
                            }
                        }
                    }
                    TextField("Add a tag", text: $newTag)
                        .focused($tagField)
                        .onSubmit { add(newTag) }
                    let hints = suggestions(doc)
                    if !hints.isEmpty {
                        Flow {
                            ForEach(hints, id: \.self) { t in
                                Button(t) { add(t) }.buttonStyle(.bordered).controlSize(.small)
                            }
                        }
                    }
                }
            } else {
                let tags = d.strings("tags")
                if !tags.isEmpty { Section("Tags") { Text(tags.joined(separator: ", ")).font(.callout) } }
            }
            if let sum = d.s("ai_summary") ?? d.s("summary") {
                Section(d.s("ai_summary") != nil ? "Summary (written by AI)" : "Summary") { Text(sum).font(.callout) }
            }
            if d.s("ai_summary") == nil, let doc, doc.doc != nil, item.kind != "podcast" {
                Section { Button(summarizing ? "Summarizing…" : "Summarize") { Task { summarizing = true; await doc.summarize(); summarizing = false } }.disabled(summarizing) }
            }
            if let doc, doc.doc != nil { ask(doc) }
            if let reader, !reader.highlights.isEmpty {
                Section("Highlights") {
                    ForEach(Array(reader.highlights.enumerated()), id: \.offset) { _, h in
                        Button { reader.reveal(highlight: h.s("id") ?? "") } label: {
                            VStack(alignment: .leading, spacing: 4) {
                                Text(h.s("text") ?? "").font(.system(.callout, design: .serif)).lineLimit(4)
                                if let n = h.s("user_note") { Text(n).font(.caption).foregroundStyle(.secondary).lineLimit(3) }
                            }
                            .padding(.leading, 6)
                            .overlay(alignment: .leading) { Rectangle().fill(Color(ReaderModel.colour(h.s("color")).withAlphaComponent(1))).frame(width: 3) }
                        }
                        .buttonStyle(.plain)
                        .contextMenu {
                            Button((h.s("user_note") ?? "").isEmpty ? "Add a Note…" : "Edit the Note…") { reader.editing = .init(h: h) }
                            Button("Remove Highlight", role: .destructive) { Task { await reader.remove(highlight: h.s("id") ?? "") } }
                        }
                    }
                }
            }
        }
        .task(id: item.id) {
            if reader == nil, item.isDoc {
                let m = ReaderModel(id: item.id)
                await m.loadMeta()
                meta = m
            }
            known = (try? await API.shared.json("/api/docs/tags"))?.strings("tags") ?? []
        }
        .onChange(of: model.focusTags) { _, _ in tagField = true }
        .onChange(of: model.focusAsk) { _, _ in askField = true }
        .onChange(of: model.focusNote) { _, _ in noteField = true }
        .onDisappear { meta?.stop() }
    }

    /// Ask: the answers so far, the question field, and Daf's suggested questions before the first.
    @ViewBuilder
    private func ask(_ doc: ReaderModel) -> some View {
        Section("Ask") {
            ForEach(Array(doc.asks.enumerated()), id: \.offset) { _, a in
                VStack(alignment: .leading, spacing: 5) {
                    if let q = a.s("quote") {
                        Text("“\(q)”").font(.system(.caption, design: .serif)).foregroundStyle(.secondary).lineLimit(3)
                    }
                    Text(a.s("q") ?? "").font(.callout.weight(.semibold))
                    Text(Self.markdown(a.s("a") ?? "")).font(.callout).textSelection(.enabled)
                }
                .fixedSize(horizontal: false, vertical: true)
                .padding(.vertical, 3)
            }
            if doc.asking {
                HStack(spacing: 8) { ProgressView().controlSize(.small); Text("Thinking it over…").foregroundStyle(.secondary) }
            }
            TextField("Ask about this", text: $question, axis: .vertical)
                .focused($askField)
                .onSubmit { let q = question; question = ""; Task { await doc.ask(q) } }
                .disabled(doc.asking)
            if doc.asks.isEmpty && !doc.asking && !doc.questions.isEmpty {
                VStack(alignment: .leading, spacing: 6) {
                    ForEach(doc.questions.prefix(4), id: \.self) { q in
                        Button(q) { Task { await doc.ask(q) } }
                            .buttonStyle(.link)
                            .multilineTextAlignment(.leading)
                    }
                }
            }
        }
    }

    static func markdown(_ s: String) -> AttributedString {
        (try? AttributedString(markdown: s, options: .init(interpretedSyntax: .inlineOnlyPreservingWhitespace))) ?? AttributedString(s)
    }

    private func suggestions(_ doc: ReaderModel) -> [String] {
        let q = newTag.trimmingCharacters(in: .whitespaces).lowercased()
        guard !q.isEmpty else { return [] }
        return Array(known.filter { $0.lowercased().hasPrefix(q) && !doc.tags.contains($0) }.prefix(6))
    }

    private func add(_ tag: String) {
        let t = tag.trimmingCharacters(in: .whitespaces)
        guard !t.isEmpty, let doc, !doc.tags.contains(where: { $0.lowercased() == t.lowercased() }) else { newTag = ""; return }
        newTag = ""
        Task {
            let all = await doc.set(tags: doc.tags + [t])
            if !all.isEmpty { known = all }
        }
    }
}

/// Little things in rows that wrap, as tags do.
struct Flow: Layout {
    var spacing: CGFloat = 6

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let width = proposal.width ?? 260
        var x: CGFloat = 0, y: CGFloat = 0, row: CGFloat = 0, widest: CGFloat = 0
        for v in subviews {
            let z = v.sizeThatFits(.unspecified)
            if x > 0 && x + z.width > width { x = 0; y += row + spacing; row = 0 }
            x += z.width + spacing
            row = max(row, z.height)
            widest = max(widest, x - spacing)
        }
        return CGSize(width: min(width, widest), height: y + row)
    }

    func placeSubviews(in b: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        var x = b.minX, y = b.minY, row: CGFloat = 0
        for v in subviews {
            let z = v.sizeThatFits(.unspecified)
            if x > b.minX && x + z.width > b.maxX { x = b.minX; y += row + spacing; row = 0 }
            v.place(at: CGPoint(x: x, y: y), proposal: ProposedViewSize(z))
            x += z.width + spacing
            row = max(row, z.height)
        }
    }
}

// MARK: signing in, and Settings

struct SignInView: View {
    @Environment(AppModel.self) private var model
    @Environment(\.dismiss) private var dismiss
    @State private var user = ""
    @State private var password = ""
    @State private var address = API.shared.base.absoluteString
    @State private var said: String?
    @State private var busy = false

    var body: some View {
        Form {
            Section {
                TextField("Daf's address", text: $address)
                TextField("Username", text: $user)
                SecureField("Password", text: $password)
            } header: { Text("Sign in to Daf") } footer: {
                if let said { Text(said).foregroundStyle(.red) }
            }
        }
        .formStyle(.grouped)
        .frame(width: 400)
        .toolbar {
            ToolbarItem(placement: .confirmationAction) {
                Button("Sign In") { Task { await signIn() } }.disabled(busy || user.isEmpty || password.isEmpty)
            }
        }
    }

    private func signIn() async {
        busy = true
        defer { busy = false }
        UserDefaults.standard.set(address, forKey: API.baseKey)
        do {
            try await API.shared.signIn(user: user, password: password)
            model.needsSignIn = false
            dismiss()
            model.reload()
        } catch { said = error.localizedDescription }
    }
}

struct SettingsView: View {
    @Environment(AppModel.self) private var model
    @State private var address = API.shared.base.absoluteString

    var body: some View {
        Form {
            Section("Daf") {
                TextField("Address", text: $address).onSubmit { UserDefaults.standard.set(address, forKey: API.baseKey); model.reload() }
                LabeledContent("Signed in", value: API.shared.cookie == nil ? "No" : "Yes")
                Button("Sign Out") { API.shared.signOut(); model.needsSignIn = true }
            }
            Section {
                Text("This is the native trial of Daf for the Mac. Books, manga and videos open as Daf's own pages inside the window; everything else is native.")
                    .font(.callout).foregroundStyle(.secondary)
            }
        }
        .formStyle(.grouped)
        .frame(width: 440)
    }
}
