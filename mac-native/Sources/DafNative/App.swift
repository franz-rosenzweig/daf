import AppKit
import SwiftUI

@main
struct DafNativeApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) private var delegate
    @State private var model = AppModel.shared
    @AppStorage("menuBar") private var menuBar = false

    var body: some Scene {
        WindowGroup("Daf", id: "main") {
            MainView()
                .environment(model)
                .frame(minWidth: 900, minHeight: 560)
        }
        .defaultSize(width: 1280, height: 820)
        .commands {
            SidebarCommands()
            InspectorCommands()
            CommandGroup(after: .newItem) {
                Button("Add a Link…") { model.sheet = .addLink }.keyboardShortcut("l", modifiers: .command)
                Button("Log Paper Minutes…") { model.sheet = .paper }.keyboardShortcut("p", modifiers: [.command, .shift])
            }
            CommandMenu("Go") {
                Button("Today") { model.place = .today }.keyboardShortcut("1")
                Button("Review") { model.place = .review }.keyboardShortcut("2")
                Button("Inbox") { model.place = .library("inbox") }.keyboardShortcut("3")
                Button("Feed") { model.place = .feed(nil) }.keyboardShortcut("4")
                Button("Highlights") { model.place = .highlights }.keyboardShortcut("5")
                Button("Books") { model.place = .books }.keyboardShortcut("6")
                Button("Manga") { model.place = .manga }.keyboardShortcut("7")
                Button("Stats") { model.place = .stats }.keyboardShortcut("8")
                Divider()
                Button("Torah") { model.place = .torah }
                Button("Podcasts") { model.place = .podcasts }
                Button("Sources") { model.place = .sources }
            }
            CommandMenu("Article") {
                Button("Highlight the Selection") { Task { await model.reader?.highlightSelection() } }
                    .keyboardShortcut("h", modifiers: [.command, .shift])
                Divider()
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
            if let route { RouteView(route: route).environment(model) }
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
        MainActor.assumeIsolated { SelfTest.startIfAsked() }
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { true }
}
