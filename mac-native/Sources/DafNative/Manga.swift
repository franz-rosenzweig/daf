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
                        Text(plural(s.i("count") ?? 0, "volume") + " · \(s.i("read") ?? 0) read" + ((s.s("status") ?? "ONGOING") == "ONGOING" ? "" : " · " + (s.s("status") ?? "").capitalized))
                            .foregroundStyle(.secondary)
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
                                if b.b("broken") { Text("Komga can't open this file").font(.caption2).foregroundStyle(.orange) }
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
                Rectangle().fill(Color.daf).frame(width: g.size.width * page / pages, height: 4)
            }
            .frame(height: 4)
        }
    }
}

// MARK: the reader's settings

/// The manga reader's settings, as the page's reader has them (web/mreader.js): the reading mode,
/// the layout, the scale and the crop belong to the series; the rest to every series. Kept by Daf
/// (/api/manga/prefs), so the page, the phone and this agree.
struct MangaPrefs: Equatable {
    var mode = "rtl", layout = "auto", shift = false, split = false, scale = "screen", stretch = true, crop = false
    var zones = "auto", invert = "none", swipe = true, animate = true, dbltap = true
    var bg = "black", pagenum = true, progress = true, stripw = 100, gap = 12, showzones = true
    var autospeed = 8, brightness = 100, contrast = 100, saturate = 100, sepia = 0, grayscale = 0, invertc = 0

    static let perSeries: Set<String> = ["mode", "layout", "shift", "split", "scale", "crop"]
    static let modes = [("rtl", "Right to Left", "Paged, as manga"), ("ltr", "Left to Right", "Paged, as comics"), ("vertical", "Vertical", "Paged, top to bottom"),
                        ("strip", "Long Strip", "Webtoons, no gaps"), ("gaps", "Strip with Gaps", "One long column, pages apart")]
    static let layouts = [("auto", "Auto"), ("single", "One Page"), ("double", "Two Pages")]
    static let scales = [("screen", "Fit Screen"), ("width", "Fit Width"), ("height", "Fit Height"), ("original", "Original Size")]
    static let zoneSets = [("auto", "Auto"), ("rl", "Right and Left"), ("l", "L Shape"), ("kindle", "Kindle"), ("edge", "Edge"), ("off", "Off")]
    static let inverts = [("none", "None"), ("h", "Left–Right"), ("v", "Top–Bottom"), ("both", "Both")]
    static let backgrounds = [("black", "Black"), ("gray", "Gray"), ("white", "White"), ("auto", "From the Page")]

    static func label(_ list: [(String, String)], _ v: String) -> String { list.first { $0.0 == v }?.1 ?? v }
    static func label(_ list: [(String, String, String)], _ v: String) -> String { list.first { $0.0 == v }?.1 ?? v }

    var paged: Bool { mode == "rtl" || mode == "ltr" || mode == "vertical" }
    /// Pages side by side (pairs, halves): only paged left and right.
    var side: Bool { mode == "rtl" || mode == "ltr" }

    mutating func apply(_ d: [String: Any]) {
        func s(_ k: String) -> String? { d[k] as? String }
        func b(_ k: String) -> Bool? { (d[k] as? Bool) ?? (d[k] as? NSNumber)?.boolValue }
        func i(_ k: String) -> Int? { (d[k] as? NSNumber)?.intValue }
        mode = s("mode") ?? mode; layout = s("layout") ?? layout; shift = b("shift") ?? shift; split = b("split") ?? split
        scale = s("scale") ?? scale; stretch = b("stretch") ?? stretch; crop = b("crop") ?? crop
        zones = s("zones") ?? zones; invert = s("invert") ?? invert; swipe = b("swipe") ?? swipe; animate = b("animate") ?? animate
        dbltap = b("dbltap") ?? dbltap; bg = s("bg") ?? bg; pagenum = b("pagenum") ?? pagenum; progress = b("progress") ?? progress
        stripw = i("stripw") ?? stripw; gap = i("gap") ?? gap; showzones = b("showzones") ?? showzones; autospeed = i("autospeed") ?? autospeed
        brightness = i("brightness") ?? brightness; contrast = i("contrast") ?? contrast; saturate = i("saturate") ?? saturate
        sepia = i("sepia") ?? sepia; grayscale = i("grayscale") ?? grayscale; invertc = i("invertc") ?? invertc
    }

    var dict: [String: Any] {
        ["mode": mode, "layout": layout, "shift": shift, "split": split, "scale": scale, "stretch": stretch, "crop": crop, "zones": zones,
         "invert": invert, "swipe": swipe, "animate": animate, "dbltap": dbltap, "bg": bg, "pagenum": pagenum, "progress": progress,
         "stripw": stripw, "gap": gap, "showzones": showzones, "autospeed": autospeed, "brightness": brightness, "contrast": contrast,
         "saturate": saturate, "sepia": sepia, "grayscale": grayscale, "invertc": invertc]
    }
}

/// Where the settings are kept: Daf's defaults and each series' own, sent a moment after a change.
@MainActor
enum MangaSettings {
    private static var defaults: [String: Any] = [:]
    private static var series: [String: [String: Any]] = [:]
    private static var loaded = false
    private static var pending: (defaults: [String: Any], series: [String: [String: Any]]) = ([:], [:])
    private static var sendTask: Task<Void, Never>?

    static func load() async {
        guard !loaded, let j = try? await API.shared.json("/api/manga/prefs") else { return }
        loaded = true
        defaults = j.o("defaults")?.raw ?? [:]
        series = (j.o("series")?.raw ?? [:]).compactMapValues { $0 as? [String: Any] }
    }

    /// A series' settings: its own, else every series', else Komga's reading direction.
    static func prefs(series sid: String, direction: String) -> MangaPrefs {
        var p = MangaPrefs()
        p.apply(defaults)
        let own = series[sid] ?? [:]
        p.apply(own)
        if own["mode"] == nil && defaults["mode"] == nil {
            p.mode = direction == "LEFT_TO_RIGHT" ? "ltr" : direction == "WEBTOON" || direction == "VERTICAL" ? "strip" : "rtl"
        }
        return p
    }

    static func hasOwn(_ sid: String) -> Bool { !(series[sid] ?? [:]).isEmpty }

    static func set(_ key: String, _ value: Any, series sid: String) {
        if MangaPrefs.perSeries.contains(key) {
            series[sid, default: [:]][key] = value
            pending.series[sid, default: [:]][key] = value
        } else {
            defaults[key] = value
            pending.defaults[key] = value
        }
        sendTask?.cancel()
        sendTask = Task {
            try? await Task.sleep(nanoseconds: 700_000_000)
            guard !Task.isCancelled else { return }
            let body: [String: Any] = ["defaults": pending.defaults, "series": pending.series]
            pending = ([:], [:])
            _ = try? await API.shared.send("PUT", "/api/manga/prefs", body)
        }
    }

    /// "Use for Every Series": this series' layout becomes every series', and it stops having its own.
    static func forEverySeries(_ p: MangaPrefs, series sid: String) async {
        var d: [String: Any] = [:]
        for k in MangaPrefs.perSeries { d[k] = p.dict[k]; defaults[k] = p.dict[k] }
        series[sid] = nil
        _ = try? await API.shared.send("PUT", "/api/manga/prefs", ["defaults": d, "series": [sid: ["_clear": true]]])
    }
}

// MARK: a volume being read

/// What's on screen at once: the card before the first page (there's a volume before), pages (one,
/// or two side by side), half of a wide page, or the card after the last.
enum MangaUnit: Equatable {
    case start, end
    case pages([Int])                     // from 0
    case half(Int, left: Bool)

    var pages: [Int] {
        switch self {
        case .pages(let p): return p
        case .half(let n, _): return [n]
        default: return []
        }
    }
}

/// A manga volume read natively, as the page's reader reads it: its units laid out by the settings,
/// turned with the keys, the trackpad, the wheel or the tap zones; the place and the reading time
/// sent as the page sends them (/api/manga/books/{id}/progress, /api/manga/beat).
@MainActor
@Observable
final class MangaModel {
    var id: String
    var book: J?
    var p = MangaPrefs()
    private(set) var units: [MangaUnit] = []
    var k = 0
    /// The way the last turn went, for the slide.
    var forward = true
    var error: String?
    var auto = false
    /// The stage's size, which decides Auto's two pages and the size asked of Daf.
    var stage = CGSize(width: 1200, height: 900)
    var stripZoom: CGFloat = 1
    var tick = 0
    /// The page shown in a strip (from 0), and whether its end card is in view.
    var stripPage = 0
    var stripEnd = false
    var toast: String?
    /// The strip goes to stripPage (a jump), or a screen on (a step), when these change.
    var jump = 0
    var step = 0
    var stepDirection = 1

    @ObservationIgnored private var images: [String: NSImage] = [:]
    @ObservationIgnored private var loading = Set<String>()
    @ObservationIgnored var lastActive = Date()
    @ObservationIgnored private var beatTimer: Timer?
    @ObservationIgnored private var autoTimer: Timer?
    @ObservationIgnored private var saveTask: Task<Void, Never>?
    @ObservationIgnored private var savedPage = 0
    @ObservationIgnored private var savedDone = false
    @ObservationIgnored weak var window: NSWindow?
    @ObservationIgnored private var toastTask: Task<Void, Never>?
    /// For the self-test.
    @ObservationIgnored static weak var last: MangaModel?

    init(id: String) { self.id = id }

    var title: String { book?.s("name") ?? "Manga" }
    var seriesID: String { book?.o("series")?.s("id") ?? "" }
    var count: Int { book?.list("pages").count ?? 0 }
    var unit: MangaUnit { units.indices.contains(k) ? units[k] : .end }

    /// The pages on screen; the card after the last counts as the last page.
    var shownPages: [Int] {
        if !p.paged { return stripEnd ? [max(0, count - 1)] : [stripPage] }
        switch unit {
        case .end: return [max(0, count - 1)]
        case .start: return [0]
        default: return unit.pages
        }
    }

    /// "3–4 / 120", "Start", "End".
    var counter: String {
        if p.paged, case .end = unit { return "End / \(count)" }
        if p.paged, case .start = unit { return "Start / \(count)" }
        let s = shownPages
        return (s.count > 1 ? "\(s[0] + 1)–\(s[1] + 1)" : "\(s[0] + 1)") + " / \(count)"
    }

    func say(_ s: String) {
        toast = s
        toastTask?.cancel()
        toastTask = Task { try? await Task.sleep(nanoseconds: 2_200_000_000); if !Task.isCancelled { toast = nil } }
    }

    // MARK: opening

    func load(atEnd: Bool = false, quiet: Bool = false) async {
        Self.last = self            // the one on screen (SwiftUI may make others it throws away)
        do {
            async let b = API.shared.json("/api/manga/books/" + API.enc(id))
            await MangaSettings.load()
            let book = try await b
            self.book = book
            images = [:]
            p = MangaSettings.prefs(series: book.o("series")?.s("id") ?? "", direction: (book.o("series")?.s("direction") ?? "").uppercased())
            savedPage = book.i("page") ?? 0
            savedDone = book.b("completed")
            var start = book.b("completed") ? 0 : max(0, (book.i("page") ?? 1) - 1)
            if atEnd { start = max(0, count - 1) }
            build(at: min(start, max(0, count - 1)))
            startBeats()
            if !quiet { say(MangaPrefs.label(MangaPrefs.modes, p.mode) + (units.contains { $0.pages.count > 1 } ? " · two pages" : "")) }
        } catch { self.error = error.localizedDescription }
    }

    /// Two pages at once: the layout says so, or Auto and the window is wider than it is tall.
    var twoUp: Bool { p.side && (p.layout == "double" || (p.layout == "auto" && stage.width > stage.height * 1.05)) }

    private func wide(_ n: Int) -> Bool {
        let dims = book?.list("pages") ?? []
        guard n >= 0, n < dims.count, let d = dims[n] as? [String: Any], let w = (d["w"] as? NSNumber)?.doubleValue,
              let h = (d["h"] as? NSNumber)?.doubleValue, w > 0, h > 0 else { return false }
        return w > h * 1.1
    }

    func aspect(_ n: Int) -> CGFloat {
        let dims = book?.list("pages") ?? []
        guard n >= 0, n < dims.count, let d = dims[n] as? [String: Any], let w = (d["w"] as? NSNumber)?.doubleValue,
              let h = (d["h"] as? NSNumber)?.doubleValue, w > 0, h > 0 else { return 2.0 / 3.0 }
        return CGFloat(w / h)
    }

    /// The units, as the page's buildUnits makes them, around a page (from 0).
    func build(at page: Int) {
        var us: [MangaUnit] = []
        let n = count
        if book?.s("prev") != nil && p.paged { us.append(.start) }
        var i = 0
        if twoUp {
            if !p.shift && n > 0 { us.append(.pages([0])); i = 1 }     // the cover alone
            while i < n {
                if wide(i) || i + 1 >= n || wide(i + 1) { us.append(.pages([i])); i += 1 }
                else { us.append(.pages([i, i + 1])); i += 2 }
            }
        } else {
            while i < n {
                if p.side && p.split && wide(i) {
                    let rightFirst = p.mode == "rtl"
                    us.append(.half(i, left: !rightFirst))
                    us.append(.half(i, left: rightFirst))
                } else { us.append(.pages([i])) }
                i += 1
            }
        }
        us.append(.end)
        units = us
        k = units.firstIndex { $0.pages.contains(page) } ?? 0
        stripPage = page
        fetchAround()
        tick += 1
    }

    /// The layout again for a new window size, keeping the page.
    func resized(_ size: CGSize) {
        let was = twoUp
        stage = size
        if was != twoUp, let first = shownPages.first { build(at: first) }
    }

    // MARK: pages

    /// The size asked of Daf for a page, as the page's reader asks (capped at 2400).
    private func size(_ n: Int) -> Int {
        let scale = Double(window?.backingScaleFactor ?? NSScreen.main?.backingScaleFactor ?? 2)
        let w = Double(stage.width), h = Double(stage.height), r = Double(1 / max(0.1, aspect(n)))
        if !p.paged { return min(2400, Int((Double(stripWidth) * scale * max(1, r)).rounded(.up))) }
        if p.scale == "width" { return min(2400, Int((w * scale * max(1, r)).rounded(.up))) }
        if p.scale == "original" { return 2400 }
        return min(2400, Int((max(w, h) * scale).rounded(.up)))
    }

    private func key(_ n: Int) -> String { "\(n)|\(p.crop)" }

    func image(_ n: Int) -> NSImage? { images[key(n)] }

    func path(_ n: Int, size: Int? = nil) -> String {
        "/api/manga/books/\(API.enc(id))/pages/\(n + 1)?size=\(size ?? self.size(n))" + (p.crop ? "&crop=1" : "")
    }

    func need(_ n: Int) {
        guard n >= 0, n < count, images[key(n)] == nil, !loading.contains(key(n)) else { return }
        let kk = key(n), url = API.shared.url(path(n))
        loading.insert(kk)
        Task {
            defer { loading.remove(kk) }
            guard let data = await API.shared.picture(url), let img = NSImage(data: data) else { return }
            images[kk] = img
            if images.count > 24, let here = shownPages.first { for x in images.keys where abs((Int(x.split(separator: "|")[0]) ?? 0) - here) > 10 { images[x] = nil } }
            tick += 1
        }
    }

    /// The units on either side, and two and three ahead, as the page preloads.
    func fetchAround() {
        if p.paged {
            for o in [0, 1, -1, 2, 3, -2] where units.indices.contains(k + o) { units[k + o].pages.forEach(need) }
        } else {
            for n in (stripPage - 2)...(stripPage + 5) { need(n) }
        }
    }

    var stripWidth: CGFloat {
        let w = stage.width
        return min(w, w >= 700 ? max(320, min(980, w * CGFloat(p.stripw) / 100)) : w) * stripZoom
    }

    // MARK: turning

    func go(_ d: Int) {
        lastActive = Date()
        let t = k + d
        if t >= units.count { if let next = book?.s("next") { Task { await other(next) } } else { say("That's the end of what Komga has") }; return }
        if t < 0 { if let prev = book?.s("prev") { Task { await other(prev, atEnd: true) } } else { say("The start of \(title)") }; return }
        forward = d > 0
        k = t
        fetchAround()
        turned()
    }

    func first() { go(to: 0) }
    func lastPage() { go(to: count - 1) }

    func go(to page: Int) {
        lastActive = Date()
        let page = max(0, min(count - 1, page))
        if p.paged {
            forward = page >= (shownPages.first ?? 0)
            k = units.firstIndex { $0.pages.contains(page) } ?? k
            fetchAround()
            turned()
        } else {
            stripPage = page
            fetchAround()
            jump += 1
            saveSoon(false)
        }
    }

    /// A strip a screen on, or back.
    func scrollScreen(_ d: Int) {
        lastActive = Date()
        stepDirection = d
        step += 1
    }

    private func turned() {
        if case .end = unit { saveSoon(true) } else { queueSave() }
    }

    /// The volume before or after, opened in this window.
    func other(_ vid: String, atEnd: Bool = false) async {
        let done: Bool = { if case .end = unit { return true }; return false }()
        await save(done)
        id = vid
        book = nil
        await load(atEnd: atEnd, quiet: true)
        say(title)
    }

    // MARK: the strip

    func stripVisible(_ ids: [Int]) {
        guard !p.paged else { return }
        lastActive = Date()
        let pages = ids.filter { $0 >= 0 }
        if let first = pages.min(), first != stripPage { stripPage = first; fetchAround(); queueSave() }
        let end = ids.contains(-1)
        if end && !stripEnd { stripEnd = true; saveSoon(true) } else if !end { stripEnd = false }
    }

    // MARK: the place and the reading time

    private func queueSave() {
        saveTask?.cancel()
        saveTask = Task {
            try? await Task.sleep(nanoseconds: 1_500_000_000)
            guard !Task.isCancelled else { return }
            await self.save(false)
        }
    }

    func save(_ done: Bool) async {
        saveTask?.cancel()
        guard book != nil else { return }
        let page = (shownPages.max() ?? 0) + 1
        let completed = done || page >= count
        if page == savedPage && !completed { return }
        if completed && savedDone { return }
        savedPage = page
        savedDone = completed
        _ = try? await API.shared.send("PUT", "/api/manga/books/\(API.enc(id))/progress", ["page": page, "completed": completed, "at": Int(Date().timeIntervalSince1970)])
    }

    func saveSoon(_ done: Bool) { Task { await save(done) } }

    private func startBeats() {
        beatTimer?.invalidate()
        beatTimer = Timer.scheduledTimer(withTimeInterval: 15, repeats: true) { [weak self] _ in
            MainActor.assumeIsolated {
                guard let self, let w = self.window, w.occlusionState.contains(.visible), NSApp.isActive,
                      Date().timeIntervalSince(self.lastActive) < 120 || self.auto else { return }
                let id = self.id
                Task { try? await API.shared.send("POST", "/api/manga/beat", ["book": id, "seconds": 15, "at": Int(Date().timeIntervalSince1970)]) }
            }
        }
    }

    func stop() {
        beatTimer?.invalidate()
        beatTimer = nil
        stopAuto()
        Task { await save(false) }
    }

    // MARK: settings

    func set(_ key: String, _ value: Any) {
        var raw = p.dict
        raw[key] = value
        var q = MangaPrefs()
        q.apply(raw)
        let relayout = ["mode", "layout", "shift", "split"].contains(key) || (key == "crop")
        let page = shownPages.first ?? 0
        p = q
        MangaSettings.set(key, value, series: seriesID)
        if key == "crop" { images = [:] }
        if relayout { build(at: page) } else { tick += 1 }
    }

    func cycle(_ key: String, _ list: [String]) {
        let cur = (p.dict[key] as? String) ?? list[0]
        let next = list[((list.firstIndex(of: cur) ?? -1) + 1) % list.count]
        set(key, next)
        say(key == "mode" ? MangaPrefs.label(MangaPrefs.modes, next) : key == "layout" ? MangaPrefs.label(MangaPrefs.layouts, next) : MangaPrefs.label(MangaPrefs.scales, next))
    }

    // MARK: auto scroll

    /// Paged: a page every so many seconds, stopping at the end card. A strip: a screen in that time
    /// (StripStage scrolls it; this only says it's on).
    func toggleAuto() { auto ? stopAuto() : startAuto() }

    func startAuto() {
        auto = true
        say("Auto scroll: \(p.autospeed) s " + (p.paged ? "a page" : "a screen") + ". Press A to stop")
        guard p.paged else { return }
        autoTimer?.invalidate()
        autoTimer = Timer.scheduledTimer(withTimeInterval: TimeInterval(p.autospeed), repeats: true) { [weak self] _ in
            MainActor.assumeIsolated {
                guard let self, self.auto else { return }
                if case .end = self.unit { self.stopAuto(); return }
                self.go(1)
            }
        }
    }

    func stopAuto() {
        auto = false
        autoTimer?.invalidate()
        autoTimer = nil
    }

    // MARK: the page's own colour, for the background "From the Page"

    func cornerColour() -> NSColor? {
        guard let n = shownPages.first, let img = image(n), let cg = img.cgImage(forProposedRect: nil, context: nil, hints: nil) else { return nil }
        let rep = NSBitmapImageRep(cgImage: cg)
        let w = rep.pixelsWide, h = rep.pixelsHigh
        guard w > 2, h > 2 else { return nil }
        let at = [(1, 1), (w - 2, 1), (1, h - 2), (w - 2, h - 2)].compactMap { rep.colorAt(x: $0.0, y: $0.1)?.usingColorSpace(.deviceRGB) }
        guard !at.isEmpty else { return nil }
        let r = at.map(\.redComponent).reduce(0, +) / CGFloat(at.count), g = at.map(\.greenComponent).reduce(0, +) / CGFloat(at.count)
        let b = at.map(\.blueComponent).reduce(0, +) / CGFloat(at.count)
        return NSColor(red: r, green: g, blue: b, alpha: 1)
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
