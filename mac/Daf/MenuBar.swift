import AppKit
import SwiftUI

/// Today's minutes, from /api/phone/widget with the device token. Asked every five
/// minutes while the Mac is awake, on wake, and when the menu opens; the last answer
/// is kept, so offline the menu bar shows what it last knew.
@MainActor
final class Today: ObservableObject {
    static let shared = Today()

    @Published private(set) var widget: Client.Widget?
    /// When the server last answered.
    @Published private(set) var at: Date?
    /// Why the last ask failed, if it did.
    @Published private(set) var problem: String?
    @Published private(set) var noToken = false

    private var timer: Timer?
    private var asking = false
    private static let keptKey = "widget.last", keptAtKey = "widget.at"

    init() {
        if let data = UserDefaults.standard.data(forKey: Self.keptKey) {
            widget = try? JSONDecoder().decode(Client.Widget.self, from: data)
            at = UserDefaults.standard.object(forKey: Self.keptAtKey) as? Date
        }
    }

    func start() {
        timer?.invalidate()
        timer = Timer.scheduledTimer(withTimeInterval: 300, repeats: true) { _ in
            Task { @MainActor in await Today.shared.refresh() }
        }
        timer?.tolerance = 30
        let ws = NSWorkspace.shared.notificationCenter
        for name in [NSWorkspace.didWakeNotification, NSWorkspace.screensDidWakeNotification] {
            ws.addObserver(forName: name, object: nil, queue: .main) { _ in
                Task { @MainActor in
                    try? await Task.sleep(nanoseconds: 3_000_000_000)   // the network comes back a moment after the screen
                    await Today.shared.refresh()
                }
            }
        }
        for name in [Notification.Name.dafBaseChanged, .dafTokenChanged] {
            NotificationCenter.default.addObserver(forName: name, object: nil, queue: .main) { _ in
                Task { @MainActor in await Today.shared.refresh() }
            }
        }
        Task { await refresh() }
    }

    func refresh() async {
        guard !asking else { return }
        asking = true
        defer { asking = false }
        do {
            let w = try await Client.widget()
            widget = w
            at = Date()
            problem = nil
            noToken = false
            if let data = try? JSONEncoder().encode(w) {
                UserDefaults.standard.set(data, forKey: Self.keptKey)
                UserDefaults.standard.set(at, forKey: Self.keptAtKey)
            }
        } catch Client.Failure.noToken {
            noToken = true
            problem = nil
        } catch {
            noToken = false
            problem = error.localizedDescription
        }
        MenuBar.shared.update()
        await FeedNews.shared.check()
    }

    /// The main goal met (Preferences → Goals), or the day's minutes for an older Daf.
    var done: Bool {
        guard let w = widget else { return false }
        return w.main.map { $0.met ?? ($0.done >= $0.target) } ?? (w.minutes >= w.goal)
    }

    /// How far along the main goal is, 0…1.
    var fraction: Double {
        guard let w = widget else { return 0 }
        if let m = w.main { return min(1, (m.pct ?? (m.target > 0 ? 100 * m.done / m.target : 0)) / 100) }
        return w.goal > 0 ? min(1, w.minutes / w.goal) : 0
    }

    /// What to say once it's met: "That's the hour." only while the goal is the hour.
    var metLine: String {
        guard let m = widget?.main, !(m.isDailyMinutes && m.target == 60) else { return "That's the hour." }
        switch m.period_label ?? "" {
        case "today": return "That's today's goal."
        case "this week": return "That's this week's goal."
        case "this month": return "That's this month's goal."
        case "this year": return "That's this year's goal."
        default: return "That's the goal."
        }
    }
    /// The last answer is old: more than 20 minutes, or from another day.
    var stale: Bool {
        guard let at else { return true }
        return Date().timeIntervalSince(at) > 1200
    }
}

/// The menu-bar item: `38′`, or `60′ ✓` once the hour is done. The point is to see it,
/// not to click it; clicking it shows the ring, the day's highlight and a few commands.
@MainActor
final class MenuBar: NSObject, NSMenuDelegate {
    static let shared = MenuBar()
    static let shownKey = "menuBarShown"

    private(set) var item: NSStatusItem?
    /// The menu's top while it's open, to fit it again when a fresh answer arrives.
    private weak var header: NSView?
    /// A word in place of the minutes for a moment ("Saved").
    private var flashText: String?

    static var shown: Bool {
        UserDefaults.standard.object(forKey: shownKey) == nil || UserDefaults.standard.bool(forKey: shownKey)
    }

    func install() {
        guard Self.shown, item == nil else { return update() }
        let item = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
        item.autosaveName = "Daf minutes"
        let menu = NSMenu()
        menu.delegate = self
        item.menu = menu
        self.item = item
        update()
    }

    func remove() {
        if let item { NSStatusBar.system.removeStatusItem(item) }
        item = nil
    }

    /// The title, from what Today knows.
    var title: String {
        if let flashText { return flashText }
        guard let w = Today.shared.widget else { return "" }
        let check = Today.shared.done ? " ✓" : ""
        // minutes a day as always ("38′"); another main goal as "33/200"
        if let m = w.main, !m.isDailyMinutes { return "\(Int(m.done))/\(Int(m.target))" + check }
        return "\(Int(w.minutes))′" + check
    }

    func update() {
        guard let button = item?.button else { return }
        let t = title
        button.font = NSFont.monospacedDigitSystemFont(ofSize: NSFont.systemFontSize, weight: .regular)
        if t.isEmpty {
            button.title = ""
            button.image = NSImage(systemSymbolName: "book.closed", accessibilityDescription: "Daf")
            button.imagePosition = .imageOnly
        } else {
            button.image = nil
            button.title = t
        }
        button.appearsDisabled = flashText == nil && Today.shared.widget != nil && Today.shared.stale
        if let header { header.frame.size = header.fittingSize }
        button.toolTip = Today.shared.widget.map { "Daf: " + ($0.main?.text ?? "\(Int($0.minutes)) of \(Int($0.goal)) minutes today") } ?? "Daf"
    }

    /// A word in the menu bar for a few seconds: "Saved".
    func flash(_ text: String) {
        flashText = text
        update()
        Task {
            try? await Task.sleep(nanoseconds: 2_500_000_000)
            flashText = nil
            update()
        }
    }

    // MARK: the menu

    nonisolated func menuNeedsUpdate(_ menu: NSMenu) {
        MainActor.assumeIsolated {
            fill(menu)
            Task { await Today.shared.refresh() }
        }
    }

    private func fill(_ menu: NSMenu) {
        menu.removeAllItems()
        let header = NSMenuItem()
        let host = NSHostingView(rootView: TodayHeader(today: Today.shared))
        host.frame.size = host.fittingSize
        header.view = host
        self.header = host
        menu.addItem(header)
        menu.addItem(.separator())
        menu.addItem(action("Open Daf", #selector(openDaf)))
        menu.addItem(action("Review", #selector(openReview)))
        menu.addItem(action("Reading Goals…", #selector(openGoals)))
        menu.addItem(.separator())
        menu.addItem(action("Save a Link…", #selector(saveLink)))
        menu.addItem(action("Log Paper Minutes…", #selector(logPaper)))
        menu.addItem(.separator())
        menu.addItem(action("Settings…", #selector(settings)))
        menu.addItem(action("Quit Daf", #selector(quit)))
    }

    private func action(_ title: String, _ sel: Selector) -> NSMenuItem {
        let i = NSMenuItem(title: title, action: sel, keyEquivalent: "")
        i.target = self
        return i
    }

    @objc func openDaf() { DafWindowController.show("#today") }
    @objc func openReview() { DafWindowController.show("#review") }
    @objc func openGoals() { DafWindowController.show("#prefs/goals") }
    @objc func saveLink() { SaveLink.ask() }
    @objc func logPaper() {
        DafWindowController.show("#today")
        // after the page has had a moment to be there
        Task {
            try? await Task.sleep(nanoseconds: 600_000_000)
            DafWindowController.front?.command("paper")
        }
    }
    @objc func settings() { SettingsWindow.show() }
    @objc func quit() { NSApp.terminate(nil) }
}

/// The top of the menu: the ring and the day, then the day's highlight with its book.
@MainActor
struct TodayHeader: View {
    @ObservedObject var today: Today

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            if let w = today.widget {
                HStack(spacing: 12) {
                    Ring(fraction: today.fraction, done: today.done)
                        .frame(width: 40, height: 40)
                    VStack(alignment: .leading, spacing: 2) {
                        Text(today.done ? today.metLine : (w.main?.text ?? "\(Int(w.minutes)) of \(Int(w.goal)) minutes today"))
                            .font(.system(size: 13, weight: .semibold))
                        Text(subtitle(w)).font(.system(size: 11)).foregroundStyle(.secondary)
                    }
                }
                if let h = w.highlight, !h.text.isEmpty {
                    VStack(alignment: .leading, spacing: 4) {
                        Text(h.text)
                            .font(.system(size: 13, design: .serif))
                            .lineLimit(4)
                            .fixedSize(horizontal: false, vertical: true)
                        if let t = h.title, !t.isEmpty {
                            Text(t).font(.system(size: 11)).foregroundStyle(.secondary).lineLimit(1)
                        }
                    }
                }
            } else {
                Text("Daf").font(.system(size: 13, weight: .semibold))
            }
            if let note {
                Text(note).font(.system(size: 11)).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
            }
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 10)
        .frame(width: 300, alignment: .leading)
    }

    private func subtitle(_ w: Client.Widget) -> String {
        let day = w.year_day.map { "Year 30, day \(Int($0))" }
        // the main goal said above; the day's minutes here when it isn't them, or once it's met
        let minutes = today.done || !(w.main?.isDailyMinutes ?? true) ? "\(Int(w.minutes)) minutes today" : nil
        return [minutes, day].compactMap { $0 }.joined(separator: " · ")
    }

    /// Said when there's something to say: no token yet, or offline.
    private var note: String? {
        if today.noToken { return "Add a device token in Settings to see today's minutes here." }
        guard today.problem != nil || (today.widget != nil && today.stale) else { return nil }
        let when = today.at.map { "as of " + $0.formatted(date: Calendar.current.isDateInToday($0) ? .omitted : .abbreviated, time: .shortened) }
        return ["Offline", when].compactMap { $0 }.joined(separator: ", ")
    }
}

/// The hour as a ring, like Today's.
struct Ring: View {
    var fraction: Double
    var done: Bool

    /// Daf's blue (style.css), lighter on a dark menu.
    static let blue = Color(nsColor: NSColor(name: nil) { look in
        look.bestMatch(from: [.darkAqua, .aqua]) == .darkAqua
            ? NSColor(srgbRed: 0.35, green: 0.71, blue: 0.86, alpha: 1)
            : NSColor(srgbRed: 0.10, green: 0.49, blue: 0.64, alpha: 1)
    })

    var body: some View {
        ZStack {
            Circle().stroke(Color.secondary.opacity(0.25), lineWidth: 5)
            Circle()
                .trim(from: 0, to: max(0.001, fraction))
                .stroke(done ? Color.green : Self.blue, style: StrokeStyle(lineWidth: 5, lineCap: .round))
                .rotationEffect(.degrees(-90))
            if done {
                Image(systemName: "checkmark").font(.system(size: 13, weight: .bold)).foregroundStyle(.green)
            }
        }
    }
}
