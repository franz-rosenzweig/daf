import SwiftUI

/// The window's own toolbar, the same on every screen: the web's corner (look2.js side()) the Mac way.
/// Beside the sidebar's button, Back and Forward (FrameNav); at the far end, after the screen's own
/// buttons, Search where the screen has no search of its own, Add, the ⋯ menu and today's minutes (FrameTail).
struct FrameNav: ToolbarContent {
    @Environment(AppModel.self) private var model

    var body: some ToolbarContent {
        ToolbarItemGroup(placement: .navigation) {
            SidebarButton()
            Button { model.go(back: true) } label: { Label("Back", systemImage: "chevron.left") }
                .disabled(!model.canGoBack)
                .help("Back (⌘[)")
            Button { model.go(back: false) } label: { Label("Forward", systemImage: "chevron.right") }
                .disabled(!model.canGoForward)
                .help("Forward (⌘])")
        }
    }
}

/// The far end of the toolbar. It's laid over the screen rather than around it: a toolbar's buttons go in the
/// order their views come, and an overlay comes after the screen's own buttons (around the screen or behind
/// it, they came first). The screen's search field still ends the bar.
struct FrameTail: View {
    @Environment(AppModel.self) private var model

    /// The screens with no search field in the bar: there Search opens ⌘K's.
    static func searchless(_ p: Place) -> Bool {
        switch p {
        case .today, .edition, .recents, .review, .recovery: return true
        default: return false
        }
    }

    var body: some View {
        Color.clear.frame(width: 0, height: 0)
            .allowsHitTesting(false)
            .toolbar {
                if model.place.map(Self.searchless) == true {
                    ToolbarItem {
                        Button { model.sheet = .palette } label: { Label("Search", systemImage: "magnifyingglass") }
                            .help("Search everything (⌘K)")
                    }
                }
                ToolbarItem {
                    Button { model.sheet = .addLink } label: { Label("Add to Daf", systemImage: "plus") }
                        .help("Add a link, a book or a PDF (⌘L)")
                }
                if model.place != .catalog {            // All Books has a ⋯ of its own: the foot of this one is in it
                    ToolbarItem { MoreMenu() }
                }
                ToolbarItem { MinutesRing() }
            }
    }
}

/// The ⋯ menu: what this screen can do that has no button of its own, then the places that sit under no
/// heading (the web's screenItems and footRows in look2.js).
struct MoreMenu: View {
    @Environment(AppModel.self) private var model

    var body: some View {
        Menu {
            screen
            Divider()
            MoreFoot()
        } label: { Label("More", systemImage: "ellipsis") }
        .menuIndicator(.hidden)
        .help("More")
    }

    private func prefs(_ tab: String) {
        UserDefaults.standard.set(tab, forKey: "prefsTab")
        model.showSettings = true
    }

    /// This screen's own.
    @ViewBuilder private var screen: some View {
        switch model.place {
        case .today?:
            Button("Goals…") { prefs("goals") }          // Log Paper and Refresh are buttons of its own
        case .stats?:
            Button("Log Paper Minutes…") { model.sheet = .paper }
            Button("Goals…") { prefs("goals") }
        case .books?, .shelf?:
            Button("New Shelf…") { model.sheet = .newShelf(nil) }
        case .feed?, .feedSource?:
            Button("Check for New Posts") { Task { await model.refreshFeed() } }
            Button("Follow a Site…") { model.sheet = .follow }
            Button("What Shows Where") { model.place = .feeds }
        case .feeds?:
            Button("Follow a Site…") { model.sheet = .follow }
        case .review?:
            Button("Review More") { model.startReview(themed: "n=10") }
        case .manga?:
            Button("AniList…") { prefs("connections") }
        case .home?, .library?, .kind?, .view?, .shortlist?:
            Button("Sync Now") { Task { await model.syncNow() } }
        default:
            EmptyView()
        }
    }
}

/// The foot of every ⋯ menu: the places that sit under no heading, and help.
struct MoreFoot: View {
    @Environment(AppModel.self) private var model

    var body: some View {
        Button("Search Everything…") { model.sheet = .palette }
        if model.place != .stats { Button("Stats") { model.place = .stats } }
        if model.place != .sources { Button("Sources") { model.place = .sources } }
        Button("Preferences…") { model.showSettings = true }
        Divider()
        Button("Keyboard Shortcuts") { model.sheet = .shortcuts }
        Button("Send Feedback…") { model.sheet = .feedback }
    }
}

/// Today's minutes as a ring with the number beside it; a click opens Stats.
struct MinutesRing: View {
    @Environment(AppModel.self) private var model

    var body: some View {
        let main = model.today?.o("main")
        let done = main?.d("done") ?? model.today?.d("counted") ?? 0
        let target = max(1, main?.d("target") ?? model.today?.d("goal") ?? 60)
        Button { model.place = .stats } label: {
            HStack(spacing: 6) {
                ZStack {
                    Circle().stroke(.quaternary, lineWidth: 2.5)
                    Circle().trim(from: 0, to: min(1, done / target))
                        .stroke(Color.daf, style: StrokeStyle(lineWidth: 2.5, lineCap: .round))
                        .rotationEffect(.degrees(-90))
                }
                .frame(width: 15, height: 15)
                Text("\(Int(done))′").font(.callout.weight(.semibold)).monospacedDigit()
            }
            .padding(.horizontal, 2)
        }
        .help("\(Int(done)) of \(Int(target)) today")
        .accessibilityLabel("Stats: \(Int(done)) of \(Int(target)) today")
    }
}
