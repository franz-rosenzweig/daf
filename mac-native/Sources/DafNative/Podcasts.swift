import SwiftUI

/// Podcasts, as the page has them: what I listened to lately and my clips, each opening its
/// episode's page (episodes.py), and the shows; a show is its episodes, newest first.
struct PodcastsView: View {
    @Environment(AppModel.self) private var model
    @State private var p: J?
    @State private var error: String?

    var body: some View {
        Group {
            if let feed = model.podcastShow {
                ShowView(feed: feed)
            } else {
                ScrollView {
                    if let p { page(p) }
                    else if let error { Text(error).foregroundStyle(.secondary).padding(60) }
                    else { ProgressView().frame(maxWidth: .infinity).padding(60) }
                }
                .navigationTitle("Podcasts")
                .task {
                    do { p = try await API.shared.json("/api/podcasts") } catch { self.error = error.localizedDescription }
                }
            }
        }
        .onDisappear { model.podcastShow = nil }
    }

    private func page(_ p: J) -> some View {
        let recent = p.a("recent"), clips = p.a("clips"), subs = p.a("subs")
        return VStack(alignment: .leading, spacing: 22) {
            if subs.isEmpty {
                VStack(alignment: .leading, spacing: 8) {
                    Heading("AntennaPod isn't syncing yet")
                    Button("Podcasts in Settings…") { model.openSettings(tab: "connections", at: "podcasts") }
                }
            }
            if !recent.isEmpty {
                VStack(alignment: .leading, spacing: 4) {
                    Heading("Listened lately")
                    rows(Array(recent.prefix(8)))
                    if recent.count > 8 {
                        DisclosureGroup("More") { rows(Array(recent.dropFirst(8))) }
                    }
                }
            }
            if !clips.isEmpty {
                VStack(alignment: .leading, spacing: 10) {
                    HStack(alignment: .firstTextBaseline) {
                        Heading("Clips")
                        Text("\(clips.count)").font(.caption).foregroundStyle(.tertiary)
                    }
                    ForEach(clips, id: \.self) { c in clip(c) }
                }
            }
            if !subs.isEmpty {
                VStack(alignment: .leading, spacing: 10) {
                    Heading("Shows")
                    LazyVGrid(columns: [GridItem(.adaptive(minimum: 120, maximum: 150), alignment: .top)], alignment: .leading, spacing: 14) {
                        ForEach(subs, id: \.self) { s in show(s) }
                    }
                    if let t = p.d("last_sync") { Text("AntennaPod synced " + TodayView.ago(t)).font(.caption).foregroundStyle(.secondary) }
                }
            }
        }
        .padding(28)
        .frame(maxWidth: 900, alignment: .leading)
        .frame(maxWidth: .infinity)
    }

    private func rows(_ list: [J]) -> some View {
        VStack(spacing: 0) {
            ForEach(Array(list.enumerated()), id: \.offset) { k, r in
                if k > 0 { Divider() }
                EpisodeRow(r: r, sub: r.s("author"))
            }
        }
    }

    /// A clip: its words, and its episode, opened 30 seconds before it.
    private func clip(_ c: J) -> some View {
        let pos = c.s("pos").flatMap { $0.data(using: .utf8) }.flatMap { J(try? JSONSerialization.jsonObject(with: $0)) }?.d("t")
        let text = c.s("text") ?? ""
        return VStack(alignment: .leading, spacing: 4) {
            Text(text)
                .font(.system(.body, design: .serif))
                .environment(\.layoutDirection, Podcasts.rtl(text) ? .rightToLeft : .leftToRight)
                .textSelection(.enabled)
            HStack(spacing: 4) {
                if let doc = c.s("doc") {
                    Button(c.s("title") ?? "") {
                        model.openRoute = "#read/" + API.enc(doc) + (pos.map { "/t:\(max(0, Int($0) - 30))" } ?? "")
                    }
                    .buttonStyle(.link)
                } else {
                    Text(c.s("title") ?? "")
                }
                Text([c.s("author"), pos.map { VideoPlayer.clock($0) }, c.d("created").map(Podcasts.date)].compactMap { $0 }.map { " · " + $0 }.joined())
                    .foregroundStyle(.secondary)
            }
            .font(.caption)
            .lineLimit(1)
        }
        .padding(.leading, 12)
        .overlay(alignment: .leading) { Rectangle().fill(Theme.shared.accent.opacity(0.5)).frame(width: 3) }
    }

    private func show(_ s: J) -> some View {
        Button { model.podcastShow = s.s("url") } label: {
            VStack(alignment: .leading, spacing: 6) {
                Podcasts.cover(s.s("image"), size: 120)
                Text(s.s("title") ?? s.s("url") ?? "").font(.callout).lineLimit(2).multilineTextAlignment(.leading)
            }
            .frame(width: 120, alignment: .leading)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
    }
}

/// A show's page: its episodes, newest first, with how far each was played.
struct ShowView: View {
    @Environment(AppModel.self) private var model
    let feed: String
    @State private var x: J?
    @State private var error: String?

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                Button { model.podcastShow = nil } label: { Label("Podcasts", systemImage: "chevron.left") }
                    .buttonStyle(.link)
                if let x {
                    HStack(alignment: .top, spacing: 16) {
                        if x.s("image") != nil { Podcasts.cover(x.s("image"), size: 96) }
                        Text(x.s("title") ?? "Podcast").font(.title2.bold())
                    }
                    let eps = x.a("episodes")
                    if eps.isEmpty { Text("No episodes in the feed.").foregroundStyle(.secondary) }
                    VStack(spacing: 0) {
                        ForEach(Array(eps.enumerated()), id: \.offset) { k, r in
                            if k > 0 { Divider() }
                            EpisodeRow(r: J(r.raw.merging(["at": r.raw["played"] ?? NSNull()]) { _, b in b }), sub: nil)
                        }
                    }
                } else if let error {
                    Text(error).foregroundStyle(.secondary)
                } else {
                    ProgressView().frame(maxWidth: .infinity).padding(40)
                }
            }
            .padding(28)
            .frame(maxWidth: 900, alignment: .leading)
            .frame(maxWidth: .infinity)
        }
        .navigationTitle(x?.s("title") ?? "Podcasts")
        .task(id: feed) {
            x = nil
            do { x = try await API.shared.json("/api/podcasts/show?feed=" + API.enc(feed)) } catch { self.error = error.localizedDescription }
        }
    }
}

/// An episode: its title, the show (on the Podcasts page), how far, when, and whether it has a
/// transcript. It opens its page, made the first time (/api/podcasts/open).
struct EpisodeRow: View {
    @Environment(AppModel.self) private var model
    let r: J
    let sub: String?

    var body: some View {
        Button { Task { await open() } } label: {
            VStack(alignment: .leading, spacing: 3) {
                let title = r.s("title") ?? "Podcast episode"
                Text(title)
                    .fontWeight(.medium)
                    .lineLimit(2)
                    .multilineTextAlignment(Podcasts.rtl(title) ? .trailing : .leading)
                    .frame(maxWidth: .infinity, alignment: Podcasts.rtl(title) ? .trailing : .leading)
                HStack(spacing: 0) {
                    Text([sub, Podcasts.time(r), (r.d("published") ?? r.d("start")).map(Podcasts.date)].compactMap { $0 }.filter { !$0.isEmpty }.joined(separator: " · "))
                    if r.b("transcript") { Text(" · Transcript").foregroundStyle(Theme.shared.accent) }
                }
                .font(.caption)
                .foregroundStyle(.secondary)
                .lineLimit(1)
            }
            .padding(.vertical, 8)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
    }

    private func open() async {
        if let doc = r.s("doc") { model.openRoute = "#read/" + API.enc(doc); return }
        guard let audio = r.s("audio") else { return }
        do {
            let o = J(try await API.shared.send("POST", "/api/podcasts/open", ["audio": audio]))
            if let id = o?.s("id") { model.openRoute = "#read/" + API.enc(id) }
        } catch { model.error = error.localizedDescription }
    }
}

@MainActor
enum Podcasts {
    /// "12:40 of 58:02", "Finished", or "58 min".
    static func time(_ r: J) -> String? {
        if let d = r.d("duration"), d > 0, let at = r.d("at") { return at >= d - 60 ? "Finished" : VideoPlayer.clock(at) + " of " + VideoPlayer.clock(d) }
        if let d = r.d("duration"), d > 0 { return "\(Int((d / 60).rounded())) min" }
        if let s = r.d("seconds"), s > 0 { return "\(Int((s / 60).rounded())) min" }
        return nil
    }

    static func date(_ t: Double) -> String {
        let d = Date(timeIntervalSince1970: t)
        return Calendar.current.isDate(d, equalTo: Date(), toGranularity: .year) ? d.formatted(.dateTime.month().day()) : d.formatted(.dateTime.month().day().year())
    }

    static func rtl(_ s: String) -> Bool { s.range(of: "[\u{0590}-\u{05FF}]", options: .regularExpression) != nil }

    static func cover(_ src: String?, size: CGFloat) -> some View {
        AsyncImage(url: src.map { API.shared.url($0) }) { p in
            if let i = p.image { i.resizable().scaledToFill() } else { Color.secondary.opacity(0.15) }
        }
        .frame(width: size, height: size)
        .clipShape(RoundedRectangle(cornerRadius: 10))
    }
}
