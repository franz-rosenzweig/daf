import AppKit
import SwiftUI

// Settings › Connections › AniList, as the page has it (web/anilist.js).

/// AniList: the sign-in Daf's manga tracker sets your progress on AniList with, every hour.
/// Connect opens AniList in the browser, which comes back to Daf's own page.
struct AniListSection: View {
    @Environment(AppModel.self) private var model
    @State private var s: J?
    @State private var clientID = ""

    var body: some View {
        Section {
            Text("Every hour Daf's manga tracker works out how far you've read each series (on the Kindle, in Daf, in Komga) and sets it on AniList, turning volumes into chapters. It never lowers what AniList has.")
                .font(.callout).foregroundStyle(.secondary)
            if let s {
                LabeledContent {
                    if s.s("client_id") != nil {
                        HStack {
                            if s.b("connected") && !s.b("expired") { Button("Forget It") { Task { await forget() } } }
                            if let u = s.s("authorize").flatMap(URL.init(string:)) {
                                Button(s.b("connected") ? "Connect Again…" : "Connect AniList…") { NSWorkspace.shared.open(u) }
                            }
                        }
                    }
                } label: {
                    Text("Sign-in")
                    Text(state(s)).foregroundStyle(s.b("expired") ? .red : .secondary)
                }
                if let lr = s.o("last_run"), lr.s("summary") != nil || failed(s) {
                    LabeledContent {
                        EmptyView()
                    } label: {
                        Text("Last update")
                        Text(TodayView.ago(lr.d("at")) + ": " + (failed(s) ? lr.s("error") ?? "" : lr.s("summary") ?? ""))
                            .foregroundStyle(failed(s) ? .red : .secondary)
                    }
                }
                DisclosureGroup("The AniList client (once)") {
                    VStack(alignment: .leading, spacing: 8) {
                        Text("1. On AniList, open Settings → Developer and press Create New Client.")
                        HStack(alignment: .firstTextBaseline) {
                            Text("2. Name it Daf, and for the Redirect URL paste \(s.s("redirect") ?? "") exactly as it is. If Connect doesn't bring you back to Daf, this is usually why.")
                            Button("Copy") {
                                NSPasteboard.general.clearContents()
                                NSPasteboard.general.setString(s.s("redirect") ?? "", forType: .string)
                            }
                        }
                        Text("3. Save, then paste its Client ID (a number) here. Daf doesn't need the secret.")
                        HStack {
                            TextField("Client ID", text: $clientID).frame(width: 140)
                            Button("Save") { Task { await save() } }
                            Spacer()
                            Link("AniList's developer settings", destination: URL(string: "https://anilist.co/settings/developer")!)
                        }
                    }
                    .font(.callout)
                    .textSelection(.enabled)
                }
            } else { ProgressView().controlSize(.small) }
        } header: { Text("AniList") }
        .id("anilist")
        .task { await load() }
    }

    private func failed(_ s: J) -> Bool { s.o("last_run")?.s("error") != nil && s.b("connected") && !s.b("expired") }

    private func state(_ s: J) -> String {
        let day = { (t: Double?) in t.map { Date(timeIntervalSince1970: $0).formatted(date: .long, time: .omitted) } ?? "" }
        if s.b("expired") { return "The AniList sign-in ran out on " + day(s.d("expires_at")) + ". Connect again to renew it." }
        if s.b("connected") {
            let soon = (s.d("expires_at") ?? .infinity) - Date().timeIntervalSince1970 < 21 * 86400
            return "Connected as " + (s.o("user")?.s("name") ?? "") + ", until " + day(s.d("expires_at")) + "." + (soon ? " Renew it soon." : "")
        }
        return "Not connected yet."
    }

    private func load() async {
        s = try? await API.shared.json("/api/anilist")
        clientID = s?.s("client_id") ?? ""
    }

    private func save() async {
        do {
            s = J(try await API.shared.send("PUT", "/api/anilist", ["client_id": clientID.trimmingCharacters(in: .whitespaces)]))
            model.say("Saved. Now Connect AniList.")
        } catch { model.error = error.localizedDescription }
    }

    private func forget() async {
        do {
            try await API.shared.send("DELETE", "/api/anilist", nil)
            model.say("Daf forgot the AniList sign-in")
            await load()
        } catch { model.error = error.localizedDescription }
    }
}
