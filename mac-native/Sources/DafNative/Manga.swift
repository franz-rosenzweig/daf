import AppKit
import SwiftUI

/// A manga series: its volumes as covers; double-click one (or Read) to read it in a window.
struct SeriesView: View {
    @Environment(\.openWindow) private var openWindow
    let id: String
    @State private var series: J?

    var body: some View {
        ScrollView {
            if let s = series {
                VStack(alignment: .leading, spacing: 18) {
                    VStack(alignment: .leading, spacing: 4) {
                        Text(s.s("name") ?? "").font(.system(.title, design: .serif).weight(.semibold))
                        Text(plural(s.i("count") ?? 0, "volume") + " · \(s.i("read") ?? 0) read").foregroundStyle(.secondary)
                        if let sum = s.s("summary") { Text(sum).font(.callout).foregroundStyle(.secondary).lineLimit(4).padding(.top, 4) }
                    }
                    if let next = s.o("next"), let nid = next.s("id") {
                        Button { openWindow(id: "route", value: "#mread/" + API.enc(nid)) } label: {
                            Label((s.i("read") ?? 0) > 0 || (next.i("page") ?? 0) > 1 ? "Keep Reading \(next.s("name") ?? "")" : "Read \(next.s("name") ?? "")", systemImage: "book")
                        }
                        .buttonStyle(.borderedProminent)
                    }
                    LazyVGrid(columns: [GridItem(.adaptive(minimum: 110), spacing: 16)], alignment: .leading, spacing: 18) {
                        ForEach(s.a("books"), id: \.self) { b in
                            VStack(alignment: .leading, spacing: 5) {
                                AsyncImage(url: API.shared.url("/api/manga/thumb/b/" + API.enc(b.s("id") ?? ""))) { p in
                                    if let i = p.image { i.resizable().aspectRatio(contentMode: .fill) } else { Color.secondary.opacity(0.08) }
                                }
                                .frame(width: 110, height: 160)
                                .clipShape(RoundedRectangle(cornerRadius: 5))
                                .overlay(alignment: .bottom) { progress(b) }
                                Text(b.s("name") ?? "").font(.caption.weight(.medium)).lineLimit(2)
                            }
                            .frame(width: 110)
                            .contentShape(Rectangle())
                            .onTapGesture(count: 2) { openWindow(id: "route", value: "#mread/" + API.enc(b.s("id") ?? "")) }
                            .contextMenu { Button("Read") { openWindow(id: "route", value: "#mread/" + API.enc(b.s("id") ?? "")) } }
                        }
                    }
                }
                .padding(24)
            } else {
                ProgressView().frame(maxWidth: .infinity).padding(60)
            }
        }
        .task(id: id) { series = try? await API.shared.json("/api/manga/series/" + API.enc(id)) }
    }

    @ViewBuilder
    private func progress(_ b: J) -> some View {
        let pages = max(1, b.d("pages") ?? 1), page = b.d("page") ?? 0
        if b.b("completed") {
            Image(systemName: "checkmark.circle.fill").foregroundStyle(.white, .green).padding(5).frame(maxWidth: .infinity, alignment: .trailing)
        } else if page > 1 {
            GeometryReader { g in
                Rectangle().fill(Color.accentColor).frame(width: g.size.width * page / pages, height: 4)
            }
            .frame(height: 4)
        }
    }
}

/// A manga volume, read natively: one page or two side by side, right to left unless the series
/// says otherwise; ←/→, Space and a click on either half turn it. The place and the reading time
/// go to Daf as the page sends them (/api/manga/books/{id}/progress, /api/manga/beat).
@MainActor
@Observable
final class MangaModel {
    var id: String
    var book: J?
    var page = 1                     // 1-based
    var pages = 0
    var rtl = true
    var spread = false
    var error: String?
    @ObservationIgnored private var images: [Int: NSImage] = [:]
    @ObservationIgnored private var loading = Set<Int>()
    @ObservationIgnored var lastActive = Date()
    @ObservationIgnored private var beatTimer: Timer?
    @ObservationIgnored private var saveTask: Task<Void, Never>?
    @ObservationIgnored weak var window: NSWindow?
    var tick = 0                    // a page arrived: draw again

    /// The volume open last, for the self-test.
    @ObservationIgnored static weak var last: MangaModel?

    init(id: String) {
        self.id = id
        Self.last = self
    }

    var title: String { book?.s("name") ?? "Manga" }
    var size: Int { min(2400, Int(max(NSScreen.main?.frame.width ?? 1600, NSScreen.main?.frame.height ?? 1000) * (NSScreen.main?.backingScaleFactor ?? 2))) }

    func load() async {
        do {
            let b = try await API.shared.json("/api/manga/books/" + API.enc(id))
            book = b
            pages = b.list("pages").count
            page = max(1, min(pages, b.i("page") ?? 1))
            if b.b("completed") { page = 1 }
            let dir = (b.o("series")?.s("direction") ?? "").uppercased()
            rtl = !(dir == "LEFT_TO_RIGHT" || dir == "VERTICAL" || dir == "WEBTOON")
            images = [:]
            fetchAround()
            startBeats()
        } catch { self.error = error.localizedDescription }
    }

    func image(_ n: Int) -> NSImage? { images[n] }

    private func fetchAround() {
        for n in (page - 1)...(page + 4) where n >= 1 && n <= pages && images[n] == nil && !loading.contains(n) {
            loading.insert(n)
            let url = API.shared.url("/api/manga/books/\(API.enc(id))/pages/\(n)?size=\(size)")
            Task {
                defer { loading.remove(n) }
                guard let data = try? await API.shared.session.data(from: url).0, let img = NSImage(data: data) else { return }
                images[n] = img
                if images.count > 14 { for k in images.keys where abs(k - page) > 6 { images[k] = nil } }
                tick += 1
            }
        }
    }

    /// Wide pages (a spread already) and the cover stand alone.
    func shows(_ n: Int) -> [Int] {
        guard spread, n > 1, n < pages else { return [n] }
        let dims = book?.list("pages") ?? []
        func wide(_ k: Int) -> Bool {
            guard k - 1 < dims.count, let d = dims[k - 1] as? [String: Any], let w = (d["w"] as? NSNumber)?.doubleValue, let h = (d["h"] as? NSNumber)?.doubleValue else { return false }
            return w > h
        }
        return wide(n) || wide(n + 1) ? [n] : [n, n + 1]
    }

    func turn(_ forward: Bool) {
        lastActive = Date()
        let step = shows(page).count
        let next = forward ? page + step : max(1, page - (spread && page > 2 ? shows(max(1, page - 2)).count : 1))
        guard next >= 1, next <= pages else { return }
        page = next
        fetchAround()
        save()
    }

    func go(to n: Int) {
        page = max(1, min(pages, n))
        fetchAround()
        save()
    }

    private func save() {
        saveTask?.cancel()
        let id = self.id, page = self.page, done = page + shows(page).count - 1 >= pages
        saveTask = Task {
            try? await Task.sleep(nanoseconds: 1_200_000_000)
            guard !Task.isCancelled else { return }
            try? await API.shared.send("PUT", "/api/manga/books/\(API.enc(id))/progress", ["page": page, "completed": done, "at": Int(Date().timeIntervalSince1970)])
        }
    }

    private func startBeats() {
        beatTimer?.invalidate()
        beatTimer = Timer.scheduledTimer(withTimeInterval: 15, repeats: true) { [weak self] _ in
            MainActor.assumeIsolated {
                guard let self, let w = self.window, w.occlusionState.contains(.visible), NSApp.isActive,
                      Date().timeIntervalSince(self.lastActive) < 90 else { return }
                let id = self.id
                Task { try? await API.shared.send("POST", "/api/manga/beat", ["book": id, "seconds": 15, "at": Int(Date().timeIntervalSince1970)]) }
            }
        }
    }

    func stop() { beatTimer?.invalidate(); beatTimer = nil }

    func open(_ other: String?) {
        guard let other else { return }
        id = other
        book = nil
        Task { await load() }
    }
}

struct MangaReader: View {
    @State private var m: MangaModel
    @FocusState private var focused: Bool

    init(id: String) { _m = State(initialValue: MangaModel(id: id)) }

    var body: some View {
        GeometryReader { g in
            ZStack {
                Color.black
                if let e = m.error {
                    ContentUnavailableView("It didn't open", systemImage: "exclamationmark.triangle", description: Text(e))
                } else if m.book == nil {
                    ProgressView().tint(.white)
                } else {
                    let shown = m.shows(m.page)
                    HStack(spacing: 0) {
                        ForEach(m.rtl ? shown.reversed() : shown, id: \.self) { n in
                            if let img = m.image(n) {
                                Image(nsImage: img).resizable().aspectRatio(contentMode: .fit)
                            } else {
                                ProgressView().tint(.white).frame(maxWidth: .infinity, maxHeight: .infinity)
                            }
                        }
                    }
                    .id(m.tick)
                    if m.page + shown.count - 1 >= m.pages, let next = m.book?.s("next") {
                        VStack {
                            Spacer()
                            Button("Next: \(m.book?.s("next_name") ?? "the next volume")") { m.open(next) }
                                .buttonStyle(.borderedProminent).controlSize(.large).padding(24)
                        }
                    }
                }
            }
            .contentShape(Rectangle())
            .onTapGesture { location in
                let leftHalf = location.x < g.size.width / 2
                m.turn(m.rtl ? leftHalf : !leftHalf)
            }
            .onAppear { m.spread = g.size.width > g.size.height * 1.3 }       // two portrait pages need the width
            .onChange(of: g.size) { _, s in m.spread = s.width > s.height * 1.3 }
        }
        .background(WindowFinder { m.window = $0 })
        .navigationTitle(m.title)
        .navigationSubtitle(m.pages > 0 ? "\(m.page) of \(m.pages)" : "")
        .toolbar {
            ToolbarItem {
                Toggle(isOn: $m.spread) { Label("Two Pages", systemImage: "book.pages") }
            }
        }
        .focusable()
        .focused($focused)
        .focusEffectDisabled()
        .onAppear { focused = true }
        .onKeyPress(phases: .down) { press in
            switch press.key {
            case .leftArrow: m.turn(m.rtl); return .handled
            case .rightArrow: m.turn(!m.rtl); return .handled
            case .space: m.turn(!press.modifiers.contains(.shift)); return .handled
            case .home: m.go(to: 1); return .handled
            default: return .ignored
            }
        }
        .task { await m.load() }
        .onDisappear { m.stop() }
        .frame(minWidth: 520, minHeight: 600)
    }
}

/// The window a SwiftUI view is in.
struct WindowFinder: NSViewRepresentable {
    let found: (NSWindow?) -> Void
    func makeNSView(context: Context) -> NSView {
        let v = NSView()
        DispatchQueue.main.async { found(v.window) }
        return v
    }
    func updateNSView(_ v: NSView, context: Context) {}
}
