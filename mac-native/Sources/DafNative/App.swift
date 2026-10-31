import AppKit
import SwiftUI

@main
struct DafNativeApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) private var delegate
    @State private var model = AppModel.shared
    @AppStorage("menuBar") private var menuBar = MenuBarSetting.byDefault
    @AppStorage("autoHighlight") private var autoHighlight = true
    @AppStorage("torahLang") private var torahLang = "both"

    var body: some Scene {
        WindowGroup("Daf", id: "main") {
            MainView()
                .environment(model)
                .frame(minWidth: 900, minHeight: 560)
                .windowToolbarFullScreenVisibility(.onHover)        // full screen is for reading: the bar comes at the top
        }
        .defaultSize(width: 1280, height: 820)
        .commands {
            CommandGroup(replacing: .sidebar) {
                Button("Switch the Sidebar") { Side.shared.cycle() }.keyboardShortcut("\\", modifiers: .command)
                Picker("Sidebar", selection: Binding(get: { Side.shared.mode }, set: { Side.shared.mode = $0 })) {
                    ForEach(Side.modes, id: \.0) { Text($0.1).tag($0.0) }
                }
            }
            InspectorCommands()
            CommandGroup(after: .toolbar) {
                Button("Focus Mode") { Focus.shared.toggle() }.keyboardShortcut("f", modifiers: [.command, .shift])
            }
            CommandGroup(after: .appSettings) {
                Button("Daf for Safari…") { Task { await Safari.setUp() } }
            }
            CommandGroup(after: .newItem) {
                Button("Add to Daf…") { model.sheet = .addLink }.keyboardShortcut("l", modifiers: .command)
                Button("Log Paper Minutes…") { model.sheet = .paper }.keyboardShortcut("p", modifiers: [.command, .shift])
                Button("Add a Photo of a Page…") { PaperPages.choose() }
            }
            ImportFromDevicesCommands()
            CommandGroup(after: .help) {
                Button("Keyboard Shortcuts") { model.sheet = .shortcuts }.keyboardShortcut("/", modifiers: .command)
                Button("Send Feedback…") { model.sheet = .feedback }
            }
            CommandMenu("Go") {
                Button("Search Everything…") { model.sheet = .palette }.keyboardShortcut("k", modifiers: .command)
                Divider()
                Button("Today") { model.place = .today }.keyboardShortcut("1")
                Button("Review") { model.place = .review }.keyboardShortcut("2")
                Button("Library") { model.place = .home }.keyboardShortcut("3")
                Button("Feed") { model.place = .feed(nil) }.keyboardShortcut("4")
                Button("Highlights") { model.place = .highlights }.keyboardShortcut("5")
                Button("Books") { model.place = .books }.keyboardShortcut("6")
                Button("Manga") { model.place = .manga }.keyboardShortcut("7")
                Button("Stats") { model.place = .stats }.keyboardShortcut("8")
                Divider()
                Button("Paper Pages") { model.place = .paper }
                Button("Torah") { model.place = .torah }
                Button("Recovery") { model.place = .recovery }
                Button("Podcasts") { model.place = .podcasts }
                Button("Sources") { model.place = .sources }
            }
            CommandMenu("Article") {
                Button("Highlight the Selection") { Task { await model.reader?.highlightSelection() } }
                    .keyboardShortcut("h", modifiers: [.command, .shift])
                Button("Highlight with a Note") { Task { await model.reader?.highlightSelection(thenNote: true) } }
                Toggle("Highlight When Selecting", isOn: $autoHighlight)
                Picker("Torah", selection: $torahLang) {
                    Text("Hebrew and English").tag("both")
                    Text("Hebrew").tag("he")
                    Text("English").tag("en")
                }
                Divider()
                Button("Next in the List") { model.step(1) }.keyboardShortcut(.downArrow, modifiers: [.command, .option])
                Button("Previous in the List") { model.step(-1) }.keyboardShortcut(.upArrow, modifiers: [.command, .option])
                Divider()
                Button(model.selected?.j.b("starred") == true ? "Remove from the Shortlist" : "Add to the Shortlist") {
                    if let i = model.selected, i.isDoc, i.whereIn != "feed" { Task { await model.star(i) } }
                }
                .disabled(model.selected?.whereIn == "feed")
                Button("Read Later or Back to Inbox") { if let i = model.selected { Task { await model.later(i) } } }
                    .keyboardShortcut("l", modifiers: [.command, .shift])
                Button("Archive or Mark Seen") { if let i = model.selected { Task { await model.done(i) } } }
                    .keyboardShortcut("e", modifiers: [.command, .shift])
                Button("Delete") { deleteSelected() }
                    .keyboardShortcut(.delete, modifiers: .command)
                Divider()
                Button("Listen or Pause") { model.reader.map { $0.listen() } ?? Speaker.shared.toggle() }
                    .keyboardShortcut("p", modifiers: [.command, .option])
                Button("Read Aloud from the Top") { if let r = model.reader { Speaker.shared.start(r, at: 0) } }
                Divider()
                Button("Tags…") { model.showInspector = true; model.focusTags += 1 }
                    .keyboardShortcut("t", modifiers: [.command, .option])
                Button("Ask…") { model.showInspector = true; model.focusAsk += 1 }
                    .keyboardShortcut("a", modifiers: [.command, .option])
                Divider()
                Button("Send to Kindle") {
                    let ids = model.chosen.filter(\.isDoc).map(\.id)
                    Task { await model.sendToKindle(ids.isEmpty ? (model.selected.map { [$0.id] } ?? []) : ids) }
                }
                Button("Open in a New Window") { if let i = model.selected, let r = model.route(for: i) { model.openRoute = r } }
                    .keyboardShortcut("o", modifiers: [.command, .shift])
                Divider()
                Button("Load the Full Article") { Task { await model.reader?.loadFull() } }
                    .disabled(model.selected?.whereIn != "feed")
                Button("Edit the Title and Author…") { model.editMeta = true }
                Button("Reset Reading Progress") { Task { await model.reader?.resetProgress() } }
                Button("Copy the Link") {
                    if let u = model.reader?.doc?.s("url") ?? model.selected?.j.s("url") { NSPasteboard.general.clearContents(); NSPasteboard.general.setString(u, forType: .string) }
                }
                Button("Open the Note in Obsidian") { model.reader?.openInObsidian() }
                    .disabled(model.reader?.doc?.s("vault_path") == nil)
            }
            CommandMenu("Feed") {
                Button("Mark All Seen") { if let p = model.place { Task { await model.markSeen(p) } } }
                    .keyboardShortcut("k", modifiers: [.command, .option])
                Button("Check for New Posts") { Task { await model.refreshFeed() } }
                    .keyboardShortcut("r", modifiers: [.command, .shift])
                Divider()
                Button("Follow a Site…") { model.sheet = .follow }
            }
        }

        WindowGroup("Daf", id: "route", for: String.self) { $route in
            if let route { RouteView(route: route).environment(model).windowToolbarFullScreenVisibility(.onHover) }
        }
        .defaultSize(width: 860, height: 760)

        Settings {
            PrefsView().environment(model)
        }

        MenuBarExtra(isInserted: $menuBar) {
            MenuBarPanel().environment(model)
        } label: {
            MenuBarLabel().environment(model)
        }
        .menuBarExtraStyle(.window)
    }
}

extension AppModel {
    static let shared = AppModel()
}

extension DafNativeApp {
    /// ⌘⌫ deletes what's open; in a text field it's the field's own (delete to the start of the line).
    @MainActor
    private func deleteSelected() {
        if let tv = NSApp.keyWindow?.firstResponder as? NSTextView, tv.isEditable { tv.deleteToBeginningOfLine(nil); return }
        guard let item = model.selected, item.isDoc else { return }
        Task { await model.delete(item) }
    }
}

final class AppDelegate: NSObject, NSApplicationDelegate {
    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.setActivationPolicy(.regular)
        NSWindow.allowsAutomaticWindowTabbing = false
        MainActor.assumeIsolated {
            _ = Theme.shared                         // this Mac's last theme, before anything shows
            FeedNews.shared.install()
            Cache.prune()
            Task {
                await Migration.run()
                await Outbox.shared.flush()
                await FeedNews.shared.check()
            }
            SelfTest.startIfAsked()
        }
    }

    /// daf://save from the share menu, daf://connect-safari from the Safari extension, daf://go/… from Shortcuts.
    func application(_ application: NSApplication, open urls: [URL]) {
        MainActor.assumeIsolated { urls.forEach(Links.handle) }
    }

    /// With today's minutes in the menu bar, closing the last window leaves Daf there.
    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { !MenuBarSetting.on }
}
