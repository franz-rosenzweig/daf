import SwiftUI

/// Recovery, as the page's (web/recovery.js, /api/recovery): the Step 10 and 11 readings for the time
/// of day, the Big Book by its chapters, the prayers, the highlights in it and the other A.A. books.
/// Every reading and prayer opens at its place in the book reader. Private: never in the review,
/// Signal or on the Kindle.
struct RecoveryView: View {
    @Environment(AppModel.self) private var model
    @Environment(\.openWindow) private var openWindow
    @State private var r: J?
    @State private var part = 0

    private var now: String { let h = Calendar.current.component(.hour, from: Date()); return h < 12 ? "morning" : h < 18 ? "day" : "evening" }

    var body: some View {
        ScrollView {
            if let r {
                VStack(alignment: .leading, spacing: 28) {
                    readings(r)
                    book(r)
                    prayers(r)
                    highlights(r)
                    if !r.a("others").isEmpty {
                        Panel("More to read") {
                            ForEach(r.a("others"), id: \.self) { b in
                                Button { show(b.s("id")) } label: {
                                    HStack(spacing: 12) {
                                        Thumb(path: b.b("has_cover") ? "/api/cover/" + API.enc(b.s("id") ?? "") : nil, book: true)
                                        VStack(alignment: .leading, spacing: 2) {
                                            Text(b.s("title") ?? "").font(.system(.body, design: .serif).weight(.semibold))
                                            Text(b.s("author") ?? "").font(.caption).foregroundStyle(.secondary)
                                        }
                                        Spacer()
                                        if let p = b.d("progress"), p > 0 { Text("\(Int(p))%").font(.caption).foregroundStyle(.secondary) }
                                    }
                                }
                                .buttonStyle(.plain)
                            }
                        }
                    }
                }
                .padding(28)
                .frame(maxWidth: 820, alignment: .leading)
                .frame(maxWidth: .infinity)
            } else {
                ProgressView().frame(maxWidth: .infinity).padding(60)
            }
        }
        .navigationTitle("Recovery")
        .navigationSubtitle("Private: never in the review, Signal or on the Kindle")
        .task { r = try? await API.shared.json("/api/recovery") }
    }

    /// The book reader at a place: a chapter's address, "q:" and words to find, "hl:" and a highlight.
    private func read(_ at: String? = nil) {
        guard let id = r?.o("book")?.s("id") else { return }
        openWindow(id: "route", value: "#ebook/" + API.enc(id) + (at.map { "/" + $0 } ?? ""))
    }

    private func show(_ id: String?) {
        guard let id else { return }
        model.place = .books
        Task { try? await Task.sleep(nanoseconds: 300_000_000); model.selection = id }
    }

    private func readings(_ r: J) -> some View {
        let list = r.a("readings").sorted { ($0.s("when") == now ? 0 : 1) < ($1.s("when") == now ? 0 : 1) }
        return Panel(["morning": "This morning", "day": "Today", "evening": "Tonight"][now] ?? "Today") {
            Text("Steps 10 and 11, in the Big Book").font(.caption).foregroundStyle(.secondary)
            ForEach(list, id: \.self) { x in
                Button { read("q:" + API.enc(x.s("find") ?? "")) } label: {
                    HStack {
                        Text(x.s("title") ?? "").font(.body.weight(x.s("when") == now ? .semibold : .regular))
                        Spacer()
                        Text([x.s("step"), x.s("page").map { "page " + $0 }].compactMap { $0 }.joined(separator: " · ")).font(.caption).foregroundStyle(.secondary)
                    }
                    .padding(.vertical, 6)
                    .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .disabled(r.o("book") == nil)
            }
        }
    }

    @ViewBuilder
    private func book(_ r: J) -> some View {
        if let b = r.o("book") {
            Panel("The Big Book") {
                HStack(alignment: .top, spacing: 16) {
                    AsyncImage(url: b.b("has_cover") ? API.shared.url("/api/cover/" + API.enc(b.s("id") ?? "")) : nil) { p in
                        if let i = p.image { i.resizable().aspectRatio(contentMode: .fill) } else { Color.secondary.opacity(0.1) }
                    }
                    .frame(width: 64, height: 96)
                    .clipShape(RoundedRectangle(cornerRadius: 4))
                    VStack(alignment: .leading, spacing: 6) {
                        Text("Alcoholics Anonymous").font(.system(.title3, design: .serif).weight(.semibold))
                        Text("Fourth Edition").font(.caption).foregroundStyle(.secondary)
                        ProgressView(value: min(100, b.d("progress") ?? 0), total: 100).frame(maxWidth: 220)
                        HStack {
                            if let n = r.o("now"), let href = n.s("href") {
                                Button("Continue: \(n.s("title") ?? "")" + (n.s("page").map { ", p. " + $0 } ?? "")) { read(API.enc(href)) }.buttonStyle(.borderedProminent)
                            } else {
                                Button("Read") { read() }.buttonStyle(.borderedProminent)
                            }
                            Button("The Book's Page") { show(b.s("id")) }
                        }
                    }
                }
                let lists = [r.a("first"), r.a("stories"), r.a("appendices")]
                if !lists[0].isEmpty {
                    Picker("", selection: $part) {
                        Text("First 164 Pages").tag(0)
                        Text("Stories").tag(1)
                        Text("Appendices").tag(2)
                    }
                    .pickerStyle(.segmented)
                    .labelsHidden()
                    .padding(.top, 8)
                    VStack(spacing: 0) {
                        ForEach(Array(lists[part].enumerated()), id: \.offset) { _, c in
                            if c.b("part") && c.s("href") == nil {
                                Text(c.s("title") ?? "").font(.caption.weight(.semibold)).foregroundStyle(.secondary).padding(.top, 10).frame(maxWidth: .infinity, alignment: .leading)
                            } else {
                                Button { if let h = c.s("href") { read(API.enc(h)) } } label: {
                                    HStack(spacing: 10) {
                                        Text(c.s("n") ?? "").font(.caption.monospacedDigit()).foregroundStyle(.secondary).frame(width: 26, alignment: .trailing)
                                        Text(c.s("title") ?? c.s("label") ?? "").lineLimit(1)
                                        Spacer()
                                        if let p = c.s("page") { Text("p. " + p).font(.caption).foregroundStyle(.tertiary) }
                                        ProgressView(value: min(100, c.d("read") ?? 0), total: 100).frame(width: 60)
                                    }
                                    .padding(.vertical, 5)
                                    .contentShape(Rectangle())
                                }
                                .buttonStyle(.plain)
                            }
                        }
                    }
                }
            }
        } else {
            Panel("The Big Book") {
                Text("Add a copy to Calibre (an EPUB), and its chapters show up here.").foregroundStyle(.secondary)
            }
        }
    }

    private func prayers(_ r: J) -> some View {
        Panel("Prayers") {
            ForEach(r.a("prayers"), id: \.self) { p in
                DisclosureGroup {
                    VStack(alignment: .leading, spacing: 8) {
                        Text(p.s("text") ?? p.s("first") ?? "").font(.system(.body, design: .serif)).textSelection(.enabled)
                        if p.s("text") == nil, let find = p.s("find") {
                            Button("Read It on Page \(p.s("page") ?? "")") { read("q:" + API.enc(find)) }
                        }
                    }
                    .padding(.vertical, 4)
                } label: {
                    HStack {
                        Text(p.s("title") ?? "").font(.body.weight(.semibold))
                        Spacer()
                        Text(p.s("note") ?? p.s("page").map { "Big Book, page " + $0 } ?? "").font(.caption).foregroundStyle(.secondary)
                    }
                }
            }
        }
    }

    @ViewBuilder
    private func highlights(_ r: J) -> some View {
        if r.o("book") != nil, !r.a("highlights").isEmpty {
            Panel("Your highlights") {
                ForEach(r.a("highlights"), id: \.self) { h in
                    Button { read("hl:" + API.enc(h.s("id") ?? "")) } label: {
                        Text("“" + (h.s("text") ?? "") + "”").font(.system(.body, design: .serif)).multilineTextAlignment(.leading)
                            .padding(.vertical, 4).frame(maxWidth: .infinity, alignment: .leading)
                    }
                    .buttonStyle(.plain)
                }
                Button("All \(r.i("highlight_count") ?? 0)") { show(r.o("book")?.s("id")) }.buttonStyle(.link)
            }
        }
    }
}
