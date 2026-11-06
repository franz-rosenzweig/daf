import AppKit
import SwiftUI

// Settings › Connections › Reader Apps, as the page has it (web/readerapps.js, daf/greader.py).

/// What outside RSS apps sign in to the Feed with, through the Google Reader API: the server's
/// address, the API's address, the username, and an API password of its own. The password is shown
/// once, when it's made, and only until the section is drawn again.
struct ReaderAppsSection: View {
    @Environment(AppModel.self) private var model
    @State private var s: J?
    @State private var password: String?
    @State private var asking: Ask?

    private enum Ask: Identifiable { case replace, remove; var id: Self { self } }

    var body: some View {
        Section {
            if let s {
                row("Server", s.s("server"))
                row("Google Reader API", s.s("api"))
                row("Username", s.s("user"))
                LabeledContent {
                    HStack {
                        if let password { Button("Copy") { copy(password) }.buttonStyle(.borderedProminent) }
                        Button(s.b("has_password") ? "New Password" : "Make a Password") {
                            if s.b("has_password") { asking = .replace } else { Task { await make() } }
                        }
                        if s.b("has_password") { Button("Remove") { asking = .remove } }
                    }
                } label: {
                    Text("API password")
                    if let password {
                        Text(password).font(.body.monospaced()).textSelection(.enabled)
                    } else if s.b("has_password"), let w = when(s) {
                        Text(w).foregroundStyle(.secondary)
                    }
                }
            } else { ProgressView().controlSize(.small) }
        } header: { Text("Reader Apps") }
        .id("readerapps")
        .task { s = try? await API.shared.json("/api/greader") }
        .confirmationDialog(asking == .remove ? "Remove the API password?" : "Replace the API password?",
                            isPresented: Binding(get: { asking != nil }, set: { if !$0 { asking = nil } }), presenting: asking) { a in
            Button(a == .remove ? "Remove" : "Replace", role: a == .remove ? .destructive : nil) {
                Task { a == .remove ? await remove() : await make() }
            }
        }
    }

    private func row(_ label: String, _ value: String?) -> some View {
        LabeledContent {
            Button("Copy") { copy(value ?? "") }.disabled(value == nil)
        } label: {
            Text(label)
            Text(value ?? "").font(.body.monospaced()).textSelection(.enabled)
        }
    }

    /// "Made 6 November 2026 · Used 3 minutes ago", as the card says it.
    private func when(_ s: J) -> String? {
        let made = s.d("made").map { "Made " + Date(timeIntervalSince1970: $0).formatted(date: .long, time: .omitted) }
        let used = s.d("used").map { "Used " + TodayView.ago($0) }
        let both = [made, used].compactMap { $0 }
        return both.isEmpty ? nil : both.joined(separator: " · ")
    }

    private func copy(_ text: String) {
        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString(text, forType: .string)
        model.say("Copied")
    }

    private func make() async {
        do {
            let r = J(try await API.shared.send("POST", "/api/greader/password", nil))
            password = r?.s("password")
            s = r
        } catch { model.error = error.localizedDescription }
    }

    private func remove() async {
        do {
            s = J(try await API.shared.send("DELETE", "/api/greader/password", nil))
            password = nil
        } catch { model.error = error.localizedDescription }
    }
}
