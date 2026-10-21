import AppKit
import SwiftUI

/// The tap zones, as Mihon lays them out (the page's reader has the same five).
enum MangaZones {
    struct Zone { let x: CGFloat, y: CGFloat, w: CGFloat, h: CGFloat, t: String }
    static let sets: [String: [Zone]] = [
        "rl": [Zone(x: 0, y: 0, w: 1 / 3, h: 1, t: "left"), Zone(x: 2 / 3, y: 0, w: 1 / 3, h: 1, t: "right")],
        "l": [Zone(x: 0, y: 0, w: 1, h: 1 / 3, t: "prev"), Zone(x: 0, y: 1 / 3, w: 1 / 3, h: 1 / 3, t: "prev"),
              Zone(x: 2 / 3, y: 1 / 3, w: 1 / 3, h: 1 / 3, t: "next"), Zone(x: 0, y: 2 / 3, w: 1, h: 1 / 3, t: "next")],
        "kindle": [Zone(x: 0, y: 1 / 3, w: 1 / 3, h: 2 / 3, t: "prev"), Zone(x: 1 / 3, y: 1 / 3, w: 2 / 3, h: 2 / 3, t: "next")],
        "edge": [Zone(x: 0, y: 0, w: 1 / 3, h: 1, t: "next"), Zone(x: 2 / 3, y: 0, w: 1 / 3, h: 1, t: "next"), Zone(x: 1 / 3, y: 2 / 3, w: 1 / 3, h: 1 / 3, t: "prev")],
        "off": [],
    ]

    static func set(_ p: MangaPrefs) -> String { p.zones == "auto" ? (p.paged ? "rl" : "l") : p.zones }

    /// What a click at a place in the window does (fractions of its width and height).
    static func at(_ fx: CGFloat, _ fy: CGFloat, _ p: MangaPrefs) -> String {
        var x = fx, y = fy
        if p.invert == "h" || p.invert == "both" { x = 1 - x }
        if p.invert == "v" || p.invert == "both" { y = 1 - y }
        return (sets[set(p)] ?? []).first { x >= $0.x && x < $0.x + $0.w && y >= $0.y && y < $0.y + $0.h }?.t ?? "menu"
    }

    /// The zones as drawn: flipped as they're read.
    static func drawn(_ p: MangaPrefs) -> [Zone] {
        (sets[set(p)] ?? []).map { z in
            Zone(x: p.invert == "h" || p.invert == "both" ? 1 - z.x - z.w : z.x, y: p.invert == "v" || p.invert == "both" ? 1 - z.y - z.h : z.y, w: z.w, h: z.h, t: z.t)
        }
    }

    static func isNext(_ t: String, _ p: MangaPrefs) -> Bool { t == "next" || (t == "left" && p.mode == "rtl") || (t == "right" && p.mode != "rtl") }
}

extension View {
    /// The page's filters: brightness, contrast, saturation, sepia, grayscale, invert.
    func mangaFilters(_ p: MangaPrefs) -> some View {
        let s = Double(p.sepia) / 100
        return self.brightness(Double(p.brightness - 100) / 200)
            .contrast(Double(p.contrast) / 100)
            .saturation(Double(p.saturate) / 100)
            .grayscale(Double(p.grayscale) / 100)
            .colorMultiply(s > 0 ? Color(red: 1, green: 1 - 0.12 * s, blue: 1 - 0.32 * s) : .white)
            .modifier(MangaInvert(on: p.invertc >= 50))
    }
}

private struct MangaInvert: ViewModifier {
    let on: Bool
    func body(content: Content) -> some View { if on { content.colorInvert() } else { content } }
}

/// A manga volume in its window, as the page's reader: the pages or the strip, the zones, the bars
/// (the page slider, the volumes on either side, the quick settings), the settings, every page at a
/// glance, and the page's keys.
struct MangaReader: View {
    @State private var m: MangaModel
    @State private var bars = false
    @State private var settings = false
    @State private var thumbs = false
    @State private var keys = false
    @State private var zonesShown = false
    @State private var zoom: CGFloat = 1
    @State private var lastZoom: CGFloat = 1
    @State private var pan: CGSize = .zero
    @State private var lastPan: CGSize = .zero
    @State private var monitor: Any?
    @State private var activity: NSObjectProtocol?
    @State private var corner: Color?
    @State private var swipe: CGFloat = 0
    @State private var swiped = false
    @State private var wheelAt = Date.distantPast
    @FocusState private var focused: Bool

    init(id: String) { _m = State(initialValue: MangaModel(id: id)) }

    private var ink: Color { m.p.bg == "white" || (m.p.bg == "auto" && corner.map { NSColor($0).brightnessComponent > 0.6 } == true) ? .black : .white }
    private var backdrop: Color {
        switch m.p.bg {
        case "white": return .white
        case "gray": return Color(white: 0.22)
        case "auto": return corner ?? .black
        default: return .black
        }
    }

    var body: some View {
        GeometryReader { g in
            ZStack {
                backdrop
                if let e = m.error {
                    ContentUnavailableView("It didn't open", systemImage: "exclamationmark.triangle", description: Text(e))
                } else if m.book == nil {
                    ProgressView().tint(ink)
                } else if m.p.paged {
                    paged(g.size)
                } else {
                    StripStage(m: m, size: g.size)
                }
                if m.book != nil { overlays(g.size) }
            }
            .contentShape(Rectangle())
            .onTapGesture(count: 2) { if m.p.dbltap { doubleClick() } }
            .onTapGesture(count: 1, coordinateSpace: .local) { loc in act(MangaZones.at(loc.x / max(1, g.size.width), loc.y / max(1, g.size.height), m.p)) }
            .gesture(MagnifyGesture()
                .onChanged { v in
                    if m.p.paged { zoom = min(4, max(1, lastZoom * v.magnification)) }
                    else { m.stripZoom = min(2.5, max(0.5, lastZoom * v.magnification)) }
                }
                .onEnded { _ in
                    lastZoom = m.p.paged ? zoom : m.stripZoom
                    if zoom <= 1.01 { pan = .zero; lastPan = .zero }
                })
            .simultaneousGesture(DragGesture(minimumDistance: 4)
                .onChanged { v in if zoom > 1.01 { pan = CGSize(width: lastPan.width + v.translation.width, height: lastPan.height + v.translation.height) } }
                .onEnded { _ in lastPan = pan })
            .onAppear { m.resized(g.size) }
            .onChange(of: g.size) { _, s in m.resized(s) }
        }
        .background(WindowFinder { m.window = $0 })
        .navigationTitle(m.title)
        .navigationSubtitle(m.book == nil ? "" : m.counter)
        .toolbar { toolbar }
        .sheet(isPresented: $thumbs) { MangaThumbs(m: m) { n in m.go(to: n); thumbs = false } }
        .sheet(isPresented: $keys) { MangaKeys { keys = false } }
        .focusable()
        .focused($focused)
        .focusEffectDisabled()
        .onKeyPress(phases: .down) { press in key(press) }
        .task { await m.load() }
        .onAppear {
            focused = true
            activity = ProcessInfo.processInfo.beginActivity(options: [.idleDisplaySleepDisabled, .userInitiated], reason: "Reading manga")
            monitor = NSEvent.addLocalMonitorForEvents(matching: .scrollWheel) { e in wheel(e) ? nil : e }
        }
        .onDisappear {
            m.stop()
            if let activity { ProcessInfo.processInfo.endActivity(activity) }
            if let monitor { NSEvent.removeMonitor(monitor) }
        }
        .onChange(of: m.k) { _, _ in
            zoom = 1; lastZoom = 1; pan = .zero; lastPan = .zero
            refreshCorner()
        }
        .onChange(of: m.tick) { _, _ in if m.p.bg == "auto" { refreshCorner() } }
        .onChange(of: m.book?.s("id")) { _, _ in zonesHint() }
        .frame(minWidth: 520, minHeight: 600)
    }

    // MARK: the pages

    @ViewBuilder
    private func paged(_ size: CGSize) -> some View {
        MangaUnitView(m: m, unit: m.unit, size: size, ink: ink)
            .id(m.k)
            .transition(m.p.animate ? .push(from: arrival) : .identity)
            .scaleEffect(zoom)
            .offset(pan)
            .animation(m.p.animate ? .easeOut(duration: 0.22) : nil, value: m.k)
    }

    /// Where the next unit comes in from: the left in right to left, below in vertical.
    private var arrival: Edge {
        switch m.p.mode {
        case "rtl": return m.forward ? .leading : .trailing
        case "vertical": return m.forward ? .bottom : .top
        default: return m.forward ? .trailing : .leading
        }
    }

    // MARK: on top of the pages

    @ViewBuilder
    private func overlays(_ size: CGSize) -> some View {
        VStack(spacing: 0) {
            if let t = m.toast {
                Text(t).font(.callout).padding(.horizontal, 14).padding(.vertical, 7)
                    .glassEffect(.regular, in: Capsule()).padding(.top, 12).transition(.opacity)
            }
            Spacer()
            if bars {
                bottomBar.padding(.bottom, 16).transition(.move(edge: .bottom).combined(with: .opacity))
            } else {
                if m.p.pagenum {
                    Text(m.counter).font(.caption.monospacedDigit()).foregroundStyle(ink.opacity(0.75))
                        .shadow(color: .black.opacity(ink == .white ? 0.6 : 0), radius: 2).padding(.bottom, m.p.progress ? 6 : 10)
                }
                if m.p.progress {
                    GeometryReader { g in
                        let n = max(1, m.count), f = CGFloat((m.shownPages.max() ?? 0) + 1) / CGFloat(n)
                        Rectangle().fill(Color.accentColor.opacity(0.85)).frame(width: g.size.width * f, height: 2)
                            .frame(maxWidth: .infinity, alignment: m.p.mode == "rtl" ? .trailing : .leading)
                    }
                    .frame(height: 2)
                }
            }
        }
        .animation(.snappy, value: bars)
        .animation(.snappy, value: m.toast)
        if zonesShown { zonesOverlay(size) }
    }

    private func zonesOverlay(_ size: CGSize) -> some View {
        ZStack(alignment: .topLeading) {
            Text("Menu").font(.headline).foregroundStyle(.white).frame(width: size.width, height: size.height)
            ForEach(Array(MangaZones.drawn(m.p).enumerated()), id: \.offset) { _, z in
                let next = MangaZones.isNext(z.t, m.p)
                Rectangle().fill((next ? Color.green : Color.blue).opacity(0.28))
                    .overlay(Text(next ? "Next" : "Previous").font(.headline).foregroundStyle(.white))
                    .frame(width: z.w * size.width, height: z.h * size.height)
                    .offset(x: z.x * size.width, y: z.y * size.height)
            }
        }
        .allowsHitTesting(false)
        .transition(.opacity)
    }

    private var bottomBar: some View {
        VStack(spacing: 10) {
            HStack(spacing: 12) {
                volumeButton(back: m.p.mode != "rtl")
                Slider(value: Binding(get: { Double((m.shownPages.first ?? 0) + 1) }, set: { m.go(to: Int($0.rounded()) - 1) }),
                       in: 1...Double(max(2, m.count)), step: 1)
                    .environment(\.layoutDirection, m.p.mode == "rtl" ? .rightToLeft : .leftToRight)
                    .frame(minWidth: 220)
                Text(m.counter).font(.caption.monospacedDigit()).frame(minWidth: 64)
                volumeButton(back: m.p.mode == "rtl")
            }
            HStack(spacing: 14) {
                Button { m.cycle("mode", MangaPrefs.modes.map(\.0)) } label: { Label(MangaPrefs.label(MangaPrefs.modes, m.p.mode), systemImage: "book.pages") }
                if m.p.side { Button { m.cycle("layout", MangaPrefs.layouts.map(\.0)) } label: { Label(MangaPrefs.label(MangaPrefs.layouts, m.p.layout), systemImage: "rectangle.split.2x1") } }
                if m.p.paged { Button { m.cycle("scale", MangaPrefs.scales.map(\.0)) } label: { Label(MangaPrefs.label(MangaPrefs.scales, m.p.scale), systemImage: "arrow.up.left.and.arrow.down.right") } }
                Button { m.set("crop", !m.p.crop); m.say(m.p.crop ? "Borders cropped" : "Borders back") } label: { Label("Crop Borders", systemImage: m.p.crop ? "crop.rotate" : "crop") }
                Button { m.toggleAuto() } label: { Label(m.auto ? "Stop" : "Auto Scroll", systemImage: m.auto ? "stop.fill" : "play.fill") }
            }
            .labelStyle(.titleAndIcon)
            .font(.caption)
        }
        .buttonStyle(.borderless)
        .padding(.horizontal, 18).padding(.vertical, 12)
        .glassEffect(.regular, in: RoundedRectangle(cornerRadius: 18))
        .frame(maxWidth: 720)
    }

    /// The volume before (back) or after, on the side it's read from.
    @ViewBuilder
    private func volumeButton(back: Bool) -> some View {
        let prev = m.book?.s("prev"), next = m.book?.s("next")
        let isPrev = (m.p.mode == "rtl") ? !back : back
        let id = isPrev ? prev : next
        Button { if let id { Task { await m.other(id) } } } label: {
            Image(systemName: back ? "chevron.left.2" : "chevron.right.2")
        }
        .disabled(id == nil)
        .help(isPrev ? "The volume before ([)" : "The next volume (])")
    }

    @ToolbarContentBuilder
    private var toolbar: some ToolbarContent {
        ToolbarItemGroup {
            Button { thumbs = true } label: { Label("All Pages", systemImage: "square.grid.3x3") }.help("Every page (T)")
            Button { settings.toggle() } label: { Label("Reading Settings", systemImage: "slider.horizontal.3") }
                .help("Reading settings (S)")
                .popover(isPresented: $settings, arrowEdge: .bottom) { MangaSettingsView(m: m, showZones: { settings = false; showZones() }) }
            Menu {
                Button(m.window?.styleMask.contains(.fullScreen) == true ? "Leave Full Screen" : "Full Screen") { m.window?.toggleFullScreen(nil) }
                Button("Show the Tap Zones") { showZones() }
                Button("Save This Page…") { savePage() }
                Divider()
                Button("Keys") { keys = true }
            } label: { Label("More", systemImage: "ellipsis.circle") }
        }
    }

    // MARK: acting

    /// A zone's action: the bars, or a turn (left and right as the reading direction has them).
    private func act(_ t: String) {
        focused = true
        if t == "menu" { bars.toggle(); return }
        if bars { bars = false; return }
        switch t {
        case "next": next()
        case "prev": prev()
        case "left": m.p.mode == "rtl" ? next() : prev()
        case "right": m.p.mode == "rtl" ? prev() : next()
        default: break
        }
    }

    private func next() { m.p.paged ? m.go(1) : m.scrollScreen(1) }
    private func prev() { m.p.paged ? m.go(-1) : m.scrollScreen(-1) }

    private func doubleClick() {
        if m.p.paged {
            withAnimation(.snappy) { zoom = zoom > 1.01 ? 1 : 2.2; lastZoom = zoom; if zoom == 1 { pan = .zero; lastPan = .zero } }
        } else {
            m.stripZoom = m.stripZoom > 1.01 ? 1 : 1.8
            lastZoom = m.stripZoom
        }
    }

    private func showZones() {
        withAnimation { zonesShown = true }
        Task { try? await Task.sleep(nanoseconds: 1_800_000_000); withAnimation { zonesShown = false } }
    }

    /// Once for each mode, zone layout and inversion, as the page shows them.
    private func zonesHint() {
        guard m.p.showzones else { return }
        let k = "\(m.p.mode)/\(MangaZones.set(m.p))/\(m.p.invert)"
        var seen = UserDefaults.standard.stringArray(forKey: "manga.zonesSeen") ?? []
        guard !seen.contains(k) else { return }
        seen.append(k)
        UserDefaults.standard.set(Array(seen.suffix(40)), forKey: "manga.zonesSeen")
        showZones()
    }

    private func refreshCorner() {
        guard m.p.bg == "auto" else { return }
        corner = m.cornerColour().map { Color(nsColor: $0) }
    }

    /// The wheel and the trackpad: a swipe turns (paged, unless a page is bigger than the window and
    /// scrolls first); the wheel turns, at most every third of a second.
    private func wheel(_ e: NSEvent) -> Bool {
        guard e.window === m.window, m.p.paged, zoom <= 1.01, !settings, !thumbs, m.p.scale == "screen" || m.p.scale == "height" else { return false }
        if e.hasPreciseScrollingDeltas {
            if e.phase == .began { swipe = 0; swiped = false }
            guard e.momentumPhase.isEmpty else { return true }
            let horizontal = abs(e.scrollingDeltaX) > abs(e.scrollingDeltaY)
            if horizontal && !m.p.swipe { return true }
            swipe += horizontal ? e.scrollingDeltaX : e.scrollingDeltaY
            if !swiped, abs(swipe) > 50 {
                swiped = true
                let forwardSign: Bool = {
                    if !horizontal { return swipe < 0 }
                    return m.p.mode == "rtl" ? swipe > 0 : swipe < 0
                }()
                forwardSign ? next() : prev()
            }
            if e.phase == .ended || e.phase == .cancelled { swipe = 0; swiped = false }
            return true
        }
        guard Date().timeIntervalSince(wheelAt) > 0.32, abs(e.scrollingDeltaY) > 0.5 else { return true }
        wheelAt = Date()
        e.scrollingDeltaY < 0 ? next() : prev()
        return true
    }

    private func key(_ press: KeyPress) -> KeyPress.Result {
        m.lastActive = Date()
        switch press.key {
        case .leftArrow: act("left"); return .handled
        case .rightArrow: act("right"); return .handled
        case .downArrow, .pageDown: if m.p.paged { next(); return .handled }; return .ignored
        case .upArrow, .pageUp: if m.p.paged { prev(); return .handled }; return .ignored
        case .space: press.modifiers.contains(.shift) ? prev() : next(); return .handled
        case .home: m.first(); return .handled
        case .end: m.lastPage(); return .handled
        case .escape:
            if settings { settings = false } else if zonesShown { zonesShown = false } else if zoom > 1.01 { zoom = 1; lastZoom = 1; pan = .zero; lastPan = .zero }
            else if bars { bars = false } else { m.window?.close() }
            return .handled
        default: break
        }
        guard press.modifiers.isDisjoint(with: [.command, .control, .option]) else { return .ignored }
        switch press.characters {
        case "[": if let id = m.book?.s("prev") { Task { await m.other(id) } }
        case "]": if let id = m.book?.s("next") { Task { await m.other(id) } }
        case "m": bars.toggle()
        case "t": thumbs = true
        case "s": settings.toggle()
        case "r": m.cycle("mode", MangaPrefs.modes.map(\.0))
        case "d": if m.p.side { m.cycle("layout", MangaPrefs.layouts.map(\.0)) }
        case "c": if m.p.paged { m.cycle("scale", MangaPrefs.scales.map(\.0)) }
        case "b": m.set("crop", !m.p.crop); m.say(m.p.crop ? "Borders cropped" : "Borders back")
        case "a": m.toggleAuto()
        case "f": m.window?.toggleFullScreen(nil)
        case "?": keys = true
        default: return .ignored
        }
        return .handled
    }

    private func savePage() {
        guard let n = m.shownPages.first else { return }
        let title = m.title, url = API.shared.url(m.path(n, size: 2400))
        Task {
            guard let data = await API.shared.picture(url) else { m.say("The page didn't come"); return }
            let ext = data.starts(with: [0x89, 0x50]) ? "png" : data.starts(with: [0xFF, 0xD8]) ? "jpg" : "webp"
            let panel = NSSavePanel()
            panel.nameFieldStringValue = "\(title) p\(n + 1).\(ext)"
            if panel.runModal() == .OK, let to = panel.url { try? data.write(to: to) }
        }
    }
}

// MARK: one unit: a page, two, half a wide one, or a card

struct MangaUnitView: View {
    let m: MangaModel
    let unit: MangaUnit
    let size: CGSize
    let ink: Color

    var body: some View {
        let _ = m.tick
        Group {
            switch unit {
            case .start: MangaStartCard(m: m, ink: ink)
            case .end: MangaEndCard(m: m, ink: ink)
            case .pages(let ps): pages(ps)
            case .half(let n, let left): half(n, left: left)
            }
        }
        .frame(width: size.width, height: size.height)
    }

    @ViewBuilder
    private func pages(_ ps: [Int]) -> some View {
        let order = m.p.mode == "rtl" ? Array(ps.reversed()) : ps
        let row = HStack(spacing: 0) { ForEach(order, id: \.self) { n in page(n, of: ps.count) } }
        switch m.p.scale {
        case "width": ScrollView(.vertical, showsIndicators: false) { row.frame(width: size.width) }
        case "height": ScrollView(.horizontal, showsIndicators: false) { row.frame(height: size.height) }
        case "original": ScrollView([.horizontal, .vertical]) { row }
        default: row
        }
    }

    /// A page's size by the scale; small pages stretched only when that's on.
    private func dims(_ n: Int, of count: Int) -> CGSize {
        let a = m.aspect(n), col = size.width / CGFloat(count)
        var w: CGFloat, h: CGFloat
        switch m.p.scale {
        case "width": w = col; h = w / a
        case "height": h = size.height; w = h * a
        case "original":
            let px = m.image(n).flatMap { $0.representations.first.map { CGSize(width: $0.pixelsWide, height: $0.pixelsHigh) } } ?? CGSize(width: 1200 * a, height: 1200)
            let s = m.window?.backingScaleFactor ?? 2
            return CGSize(width: px.width / s, height: px.height / s)
        default:
            if col / a <= size.height { w = col; h = col / a } else { h = size.height; w = h * a }
        }
        if !m.p.stretch, let img = m.image(n), let rep = img.representations.first {
            let s = m.window?.backingScaleFactor ?? 2, nw = CGFloat(rep.pixelsWide) / s
            if w > nw { h = h * nw / w; w = nw }
        }
        return CGSize(width: w, height: h)
    }

    private func page(_ n: Int, of count: Int) -> some View {
        let d = dims(n, of: count)
        return Group {
            if let img = m.image(n) { Image(nsImage: img).resizable().interpolation(.high) }
            else { ProgressView().tint(ink.opacity(0.6)) }
        }
        .frame(width: d.width, height: d.height)
        .mangaFilters(m.p)
    }

    /// Half of a wide page, as the page's reader splits it: the right half first in right to left.
    private func half(_ n: Int, left: Bool) -> some View {
        let a = m.aspect(n) / 2
        let w: CGFloat = size.width / a <= size.height ? size.width : size.height * a
        let h = w / a
        return Group {
            if let img = m.image(n) {
                Image(nsImage: img).resizable().interpolation(.high).frame(width: w * 2, height: h)
                    .frame(width: w, height: h, alignment: left ? .leading : .trailing).clipped()
            } else { ProgressView().tint(ink.opacity(0.6)) }
        }
        .mangaFilters(m.p)
    }
}

struct MangaStartCard: View {
    let m: MangaModel
    let ink: Color
    var body: some View {
        VStack(spacing: 10) {
            Text("Before this").foregroundStyle(ink.opacity(0.6))
            Text(m.book?.s("prev_name") ?? "The volume before").font(.title2.weight(.semibold)).foregroundStyle(ink)
            Button("Read It") { if let id = m.book?.s("prev") { Task { await m.other(id) } } }.buttonStyle(.borderedProminent)
            Text(m.p.mode == "rtl" ? "Turn back once more for its last page" : "Turn back for its last page").font(.caption).foregroundStyle(ink.opacity(0.5))
        }
        .environment(\.colorScheme, ink == .white ? .dark : .light)
    }
}

struct MangaEndCard: View {
    let m: MangaModel
    let ink: Color
    var body: some View {
        VStack(spacing: 10) {
            Text("Finished").foregroundStyle(ink.opacity(0.6))
            Text(m.title).font(.title2.weight(.semibold)).foregroundStyle(ink)
            if let next = m.book?.s("next") {
                Text("Next").foregroundStyle(ink.opacity(0.6)).padding(.top, 8)
                Text(m.book?.s("next_name") ?? "The next volume").font(.title3.weight(.semibold)).foregroundStyle(ink)
                Button("Keep Reading") { Task { await m.other(next) } }.buttonStyle(.borderedProminent)
                Text("or keep turning").font(.caption).foregroundStyle(ink.opacity(0.5))
            } else {
                Text("That's the last volume in Komga.").foregroundStyle(ink.opacity(0.6))
            }
            Button("Back to the Series") {
                AppModel.shared.place = .manga
                AppModel.shared.selection = m.seriesID
                m.window?.close()
            }
            .buttonStyle(.bordered)
            .padding(.top, 6)
        }
        .environment(\.colorScheme, ink == .white ? .dark : .light)       // controls that show on the page's background
    }
}

// MARK: the long strip

struct StripStage: View {
    let m: MangaModel
    let size: CGSize
    @State private var position = ScrollPosition(idType: Int.self)
    @State private var offset: CGFloat = 0

    var body: some View {
        let _ = m.tick
        let w = m.stripWidth, gap: CGFloat = m.p.mode == "gaps" ? CGFloat(m.p.gap) : 0
        ScrollView(.vertical) {
            LazyVStack(spacing: gap) {
                ForEach(0..<m.count, id: \.self) { n in
                    Group {
                        if let img = m.image(n) { Image(nsImage: img).resizable().interpolation(.high) } else { Color.white.opacity(0.04) }
                    }
                    .frame(width: w, height: w / m.aspect(n))
                    .mangaFilters(m.p)
                    .onAppear { m.need(n); m.need(n + 1); m.need(n + 2) }
                    .id(n)
                }
                MangaEndCard(m: m, ink: m.p.bg == "white" ? .black : .white).frame(width: w, height: max(320, size.height * 0.6)).id(-1)
            }
            .scrollTargetLayout()
            .frame(maxWidth: .infinity)
        }
        .scrollPosition($position, anchor: .top)
        .onScrollTargetVisibilityChange(idType: Int.self, threshold: 0.05) { ids in m.stripVisible(ids) }
        .onScrollGeometryChange(for: CGFloat.self, of: { $0.contentOffset.y }) { _, y in offset = y }
        .onAppear { position.scrollTo(id: m.stripPage, anchor: .top) }
        .onChange(of: m.jump) { _, _ in position.scrollTo(id: m.stripPage, anchor: .top) }
        .onChange(of: m.step) { _, _ in
            let y = max(0, offset + CGFloat(m.stepDirection) * size.height * 0.85)
            if m.p.animate { withAnimation(.easeOut(duration: 0.3)) { position.scrollTo(y: y) } } else { position.scrollTo(y: y) }
        }
        .task(id: m.auto) {
            while m.auto && !Task.isCancelled {
                try? await Task.sleep(nanoseconds: 16_000_000)
                position.scrollTo(y: offset + size.height * 0.85 / CGFloat(max(2, m.p.autospeed)) * 0.016)
                if m.stripEnd { m.stopAuto() }
            }
        }
    }
}

// MARK: every page, the settings, the keys

struct MangaThumbs: View {
    let m: MangaModel
    let pick: (Int) -> Void
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        VStack(spacing: 0) {
            HStack {
                Text(m.title).font(.headline)
                Spacer()
                Button("Done") { dismiss() }.keyboardShortcut(.cancelAction)
            }
            .padding(14)
            ScrollViewReader { r in
                ScrollView {
                    LazyVGrid(columns: [GridItem(.adaptive(minimum: 120), spacing: 12)], spacing: 14) {
                        ForEach(0..<m.count, id: \.self) { n in
                            Button { pick(n) } label: {
                                VStack(spacing: 4) {
                                    AsyncImage(url: API.shared.url(m.path(n, size: 400))) { ph in
                                        if let i = ph.image { i.resizable().aspectRatio(contentMode: .fit) } else { Color.secondary.opacity(0.1) }
                                    }
                                    .frame(height: 170)
                                    .overlay(RoundedRectangle(cornerRadius: 3).stroke(m.shownPages.contains(n) ? Color.accentColor : .clear, lineWidth: 3))
                                    Text("\(n + 1)").font(.caption.monospacedDigit()).foregroundStyle(.secondary)
                                }
                            }
                            .buttonStyle(.plain)
                            .id(n)
                        }
                    }
                    .padding(14)
                    .environment(\.layoutDirection, m.p.mode == "rtl" ? .rightToLeft : .leftToRight)
                }
                .onAppear { r.scrollTo(m.shownPages.first ?? 0, anchor: .center) }
            }
        }
        .frame(width: 780, height: 600)
    }
}

struct MangaSettingsView: View {
    let m: MangaModel
    let showZones: () -> Void

    private func pick(_ key: String, _ title: String, _ list: [(String, String)]) -> some View {
        Picker(title, selection: Binding(get: { m.p.dict[key] as? String ?? list[0].0 }, set: { m.set(key, $0) })) {
            ForEach(list, id: \.0) { Text($0.1).tag($0.0) }
        }
    }

    private func toggle(_ key: String, _ title: String) -> some View {
        Toggle(title, isOn: Binding(get: { m.p.dict[key] as? Bool ?? false }, set: { m.set(key, $0) }))
    }

    private func slider(_ key: String, _ title: String, _ range: ClosedRange<Double>, step: Double, unit: String = "") -> some View {
        LabeledContent(title) {
            HStack {
                Slider(value: Binding(get: { Double(m.p.dict[key] as? Int ?? 0) }, set: { m.set(key, Int($0.rounded())) }), in: range, step: step)
                    .frame(width: 170)
                Text("\(m.p.dict[key] as? Int ?? 0)\(unit)").monospacedDigit().frame(width: 46, alignment: .trailing)
            }
        }
    }

    var body: some View {
        TabView {
            Form {
                Section {
                    LabeledContent(m.book?.o("series")?.s("name") ?? "This series",
                                   value: MangaSettings.hasOwn(m.seriesID) ? "Its own way" : "As every series reads")
                    Button("Use for Every Series") { Task { await MangaSettings.forEverySeries(m.p, series: m.seriesID); m.say("Every series now reads this way, unless it has its own") } }
                }
                Picker("Reading mode", selection: Binding(get: { m.p.mode }, set: { m.set("mode", $0) })) {
                    ForEach(MangaPrefs.modes, id: \.0) { Text($0.1).tag($0.0) }
                }
                if m.p.side {
                    pick("layout", "Pages", MangaPrefs.layouts)
                    toggle("shift", "Shift pairs by one")
                    toggle("split", "Split wide pages")
                }
                if m.p.paged {
                    pick("scale", "Scale", MangaPrefs.scales)
                    toggle("stretch", "Stretch small pages")
                } else {
                    slider("stripw", "Strip width", 40...100, step: 5, unit: "%")
                    if m.p.mode == "gaps" { slider("gap", "Gap", 0...60, step: 2, unit: " pt") }
                }
                toggle("crop", "Crop borders")
            }
            .formStyle(.grouped)
            .tabItem { Text("Reading") }

            Form {
                pick("zones", "Tap zones", MangaPrefs.zoneSets)
                Button("Show the Tap Zones", action: showZones)
                pick("invert", "Invert tap zones", MangaPrefs.inverts)
                if m.p.paged { toggle("swipe", "Swipe to turn") }
                toggle("animate", m.p.paged ? "Slide pages" : "Smooth scrolling")
                toggle("dbltap", "Double-click to zoom")
                slider("autospeed", m.p.paged ? "Auto scroll, a page every" : "Auto scroll, a screen every", 2...30, step: 1, unit: " s")
                toggle("showzones", "Show the tap zones when they change")
            }
            .formStyle(.grouped)
            .tabItem { Text("Controls") }

            Form {
                pick("bg", "Background", MangaPrefs.backgrounds)
                toggle("pagenum", "Page number")
                toggle("progress", "Progress line")
            }
            .formStyle(.grouped)
            .tabItem { Text("Display") }

            Form {
                slider("brightness", "Brightness", 30...130, step: 1, unit: "%")
                slider("contrast", "Contrast", 50...150, step: 1, unit: "%")
                slider("saturate", "Saturation", 0...200, step: 1, unit: "%")
                slider("sepia", "Sepia", 0...100, step: 1)
                slider("grayscale", "Grayscale", 0...100, step: 1)
                Toggle("Invert", isOn: Binding(get: { m.p.invertc >= 50 }, set: { m.set("invertc", $0 ? 100 : 0) }))
                Button("Reset the Filters") {
                    for (k, v) in [("brightness", 100), ("contrast", 100), ("saturate", 100), ("sepia", 0), ("grayscale", 0), ("invertc", 0)] { m.set(k, v) }
                }
            }
            .formStyle(.grouped)
            .tabItem { Text("Filters") }
        }
        .frame(width: 440, height: 500)
        .padding(.top, 8)
    }
}

struct MangaKeys: View {
    let done: () -> Void
    private let rows: [(String, String)] = [
        ("← →", "The page to the left or right"), ("Space, ↓, Page Down", "The next page"), ("⇧Space, ↑, Page Up", "The page before"),
        ("Home, End", "The first or last page"), ("[ ]", "The volume before or after"), ("M", "Show or hide the bars"),
        ("T", "Every page"), ("S", "Reading settings"), ("R", "The reading mode"), ("D", "The page layout"), ("C", "The scale"),
        ("B", "Crop the borders"), ("A", "Auto scroll"), ("F", "Full screen"), ("Esc", "Close what's open, then the volume"),
    ]
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Keys in the manga reader").font(.headline)
            Grid(alignment: .leading, horizontalSpacing: 18, verticalSpacing: 6) {
                ForEach(rows, id: \.0) { k, what in GridRow { Text(k).font(.callout.monospaced()); Text(what).foregroundStyle(.secondary) } }
            }
            HStack { Spacer(); Button("Done", action: done).keyboardShortcut(.defaultAction) }
        }
        .padding(20)
        .frame(width: 440)
    }
}
