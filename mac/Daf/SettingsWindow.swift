import AppKit
import ServiceManagement
import SwiftUI
import WebKit

/// Daf → Settings…: the shell's own settings. Daf's own preferences stay in the page.
@MainActor
enum SettingsWindow {
    private static var window: NSWindow?

    static func show() {
        NSApp.bringForward()
        if let window { window.makeKeyAndOrderFront(nil); return }
        let w = NSWindow(contentViewController: NSHostingController(rootView: SettingsView()))
        w.title = "Daf Settings"
        w.styleMask = [.titled, .closable]
        w.isReleasedWhenClosed = false
        w.center()
        w.makeKeyAndOrderFront(nil)
        window = w
    }

    /// Makes this Mac's device token with the sign-in in the Daf window, and keeps it.
    /// Nil when it worked, otherwise what to tell the user.
    static func connect() async -> String? {
        guard let c = DafWindowController.all.first(where: { $0.start == nil }) else {
            DafWindowController.open()
            return "Sign in to Daf in its window, then press Connect again."
        }
        let js = """
        const r = await fetch('/api/devices', { method: 'POST', credentials: 'same-origin',
          headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name: 'mac' }) });
        return { status: r.status, body: await r.text() };
        """
        let answer: Any?
        do { answer = try await c.webView.callAsyncJavaScript(js, arguments: [:], in: nil, contentWorld: .page) } catch {
            return "Daf didn't answer: \(error.localizedDescription)"
        }
        let a = answer as? [String: Any] ?? [:]
        let status = (a["status"] as? NSNumber)?.intValue ?? 0
        let body = (a["body"] as? String).flatMap { try? JSONSerialization.jsonObject(with: Data($0.utf8)) as? [String: Any] }
        switch status {
        case 200..<300:
            guard let token = body?["token"] as? String, !token.isEmpty else { return "Daf answered without a token." }
            return Token.set(token) ? nil : "The Keychain didn't take the token."
        case 401: return "Sign in to Daf in its window first, then press Connect again."
        case 404, 405: return "This Daf can't make tokens for a Mac yet. On morten, run daf kindle-token mac and paste what it prints below."
        default: return (body?["detail"] as? String) ?? "Daf answered \(status)."
        }
    }
}

@MainActor
struct SettingsView: View {
    @ObservedObject private var today = Today.shared
    @State private var address = Server.base.absoluteString
    @State private var addressNote: String?
    @State private var pasted = ""
    @State private var tokenNote: String?
    @State private var connecting = false
    @State private var hasToken = Token.value != nil
    @State private var menuBar = MenuBar.shown
    @State private var atLogin = SMAppService.mainApp.status == .enabled
    @State private var kept = OnThisMac.summary()
    @State private var keptNote: String?
    @State private var updating = false

    var body: some View {
        Form {
            Section {
                HStack {
                    TextField("Address", text: $address, prompt: Text(Server.defaultBase))
                        .labelsHidden()
                        .onSubmit(useAddress)
                    Button("Use", action: useAddress).disabled(address == Server.base.absoluteString)
                }
                note(addressNote ?? "https://daf.tiresia.xyz, or http://100.91.202.11:8440 on the tailnet.")
            } header: { Text("Daf's address") }

            Section {
                Text(status).fixedSize(horizontal: false, vertical: true)
                HStack {
                    Button(hasToken ? "Connect Again" : "Connect This Mac") {
                        connecting = true
                        Task {
                            tokenNote = await SettingsWindow.connect()
                            hasToken = Token.value != nil
                            connecting = false
                        }
                    }.disabled(connecting)
                    if hasToken {
                        Button("Forget the Token") { Token.set(nil); hasToken = false; tokenNote = nil }
                    }
                }
                HStack {
                    SecureField("Token", text: $pasted, prompt: Text("Or paste a token")).labelsHidden()
                    Button("Save") {
                        tokenNote = Token.set(pasted) ? nil : "The Keychain didn't take the token."
                        pasted = ""
                        hasToken = Token.value != nil
                    }.disabled(pasted.trimmingCharacters(in: .whitespaces).isEmpty)
                }
                note(tokenNote ?? "The menu bar and Save to Daf use a device token, kept in the Keychain. Connect makes one with your sign-in in the Daf window.")
            } header: { Text("This Mac") }

            Section {
                Toggle("Show today's minutes in the menu bar", isOn: $menuBar)
                    .onChange(of: menuBar) { on in
                        UserDefaults.standard.set(on, forKey: MenuBar.shownKey)
                        if on { MenuBar.shared.install() } else { MenuBar.shared.remove() }
                    }
                Toggle("Open Daf at login", isOn: $atLogin)
                    .onChange(of: atLogin) { on in
                        do { if on { try SMAppService.mainApp.register() } else { try SMAppService.mainApp.unregister() } } catch {
                            NSLog("Daf: login item: \(error.localizedDescription)")
                        }
                        atLogin = SMAppService.mainApp.status == .enabled
                    }
                note("At login Daf starts in the menu bar, without a window.")
            } header: { Text("Menu bar") }

            Section {
                HStack {
                    Text(kept).fixedSize(horizontal: false, vertical: true)
                    Spacer()
                    Button(updating ? "Updating…" : "Update Now") {
                        updating = true
                        Task {
                            let said = await LocalCopy.refreshNow()
                            keptNote = said.hasPrefix("Daf didn't") ? said : nil
                            kept = OnThisMac.summary()
                            updating = false
                        }
                    }.disabled(updating)
                }
                note(keptNote ?? "Daf keeps its screens, your lists, the articles and books you're reading, and what you keep by hand, so it opens with no connection. What nothing needs any more goes after three weeks.")
            } header: { Text("With no connection") }
        }
        .formStyle(.grouped)
        .frame(width: 460)
        .fixedSize()
    }

    private var status: String {
        if !hasToken { return "Not connected yet." }
        if let w = today.widget, !today.stale { return "Connected: \(Int(w.minutes)) of \(Int(w.goal)) minutes today." }
        if let p = today.problem { return p }
        return "Connected."
    }

    private func useAddress() {
        let typed = address.trimmingCharacters(in: .whitespaces)
        if Server.setBase(typed.isEmpty ? Server.defaultBase : typed) {
            address = Server.base.absoluteString
            addressNote = nil
        } else {
            addressNote = "That isn't an address Daf can use. It starts with https:// or http://."
        }
    }

    private func note(_ s: String) -> some View {
        Text(s).font(.caption).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
    }
}
