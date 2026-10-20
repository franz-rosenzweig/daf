import AppKit
import SwiftUI

@main
struct DafNativeApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) private var delegate
    @State private var model = AppModel.shared

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
                Button("Stats") { model.place = .stats }.keyboardShortcut("7")
            }
            CommandMenu("Article") {
                Button("Highlight the Selection") { Task { await model.reader?.highlightSelection() } }
                    .keyboardShortcut("h", modifiers: [.command, .shift])
                Divider()
                Button("Read Later or Back to Inbox") { if let i = model.selected { Task { await model.later(i) } } }
                    .keyboardShortcut("l", modifiers: [.command, .shift])
                Button("Archive or Mark Seen") { if let i = model.selected { Task { await model.done(i) } } }
                    .keyboardShortcut("e", modifiers: [.command, .shift])
            }
        }

        WindowGroup("Daf", id: "route", for: String.self) { $route in
            if let route { RouteView(route: route).environment(model) }
        }
        .defaultSize(width: 860, height: 760)

        Settings {
            SettingsView().environment(model)
        }
    }
}

extension AppModel {
    static let shared = AppModel()
}

final class AppDelegate: NSObject, NSApplicationDelegate {
    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.setActivationPolicy(.regular)
        NSWindow.allowsAutomaticWindowTabbing = false
        MainActor.assumeIsolated { SelfTest.startIfAsked() }
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { true }
}
