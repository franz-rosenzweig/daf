import SwiftUI

/// The day's review, as the page has it: the highlights to see again (Keep, Less often, a note,
/// Never) and the flashcards that are due (Again, Hard, Good, Easy), one at a time.
@MainActor
@Observable
final class ReviewModel {
    var items: [J] = []
    var actions: [String: String] = [:]          // id → what was done
    var index = 0
    var showAnswer = false
    var writing = false
    var note = ""
    var streak: J?
    var loaded = false
    var error: String?
    /// A themed review ("#tag", "Favorites", a colour, a book): the highlights asked for, apart from the day's.
    var theme: String?
    @ObservationIgnored var themedQuery: String?

    var current: J? { items.indices.contains(index) ? items[index] : nil }
    var isCard: Bool { current?.b("card") == true }
    var reviewed: Int { items.prefix(index).count }

    func load(day: String?) async {
        do {
            let d = day ?? Self.today()
            let r = try await API.shared.json("/api/review?day=\(d)")
            var all = r.a("items").filter { $0.s("action") == nil }
            streak = r.o("streak")
            if let cards = try? await API.shared.json("/api/cards/due") {
                all += cards.a("items").map { c in var raw = c.raw; raw["card"] = true; return J(raw) }
            }
            items = all
            index = 0
            loaded = true
        } catch { self.error = error.localizedDescription; loaded = true }
    }

    /// A review by theme, as the page's #review/tag/…, /fav, /color/…, /book/…, /filter/… (/api/review/themed).
    func load(themed q: String) async {
        do {
            let r = try await API.shared.json("/api/review/themed?" + q)
            items = r.a("items")
            theme = r.s("theme")
            themedQuery = q
            index = 0
            actions = [:]
            loaded = true
        } catch { self.error = error.localizedDescription; loaded = true }
    }

    static func today() -> String {
        let f = DateFormatter()
        f.dateFormat = "yyyy-MM-dd"
        return f.string(from: Date())
    }

    func act(_ action: String, model: AppModel) async {
        guard let x = current, let id = x.s("id") else { return }
        var body: [String: Any] = ["action": action, "at": Int(Date().timeIntervalSince1970)]
        if action == "note" {
            let n = note.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !n.isEmpty else { writing = false; return }
            body["note"] = n
        }
        do {
            try await API.shared.send("POST", "/api/review/\(API.enc(id))", body)
            actions[id] = action
            writing = false
            note = ""
            index += 1
            if action == "never" { model.say("It won't come up in review again") }
            if action == "note" { model.say("Note saved") }
        } catch { model.error = error.localizedDescription }
    }

    func grade(_ g: String, model: AppModel) async {
        guard let x = current, let id = x.s("id") else { return }
        do {
            try await API.shared.send("POST", "/api/cards/\(API.enc(id))/grade", ["grade": g])
            actions[id] = g
            if g == "again" { var raw = x.raw; raw["again"] = true; items.append(J(raw)) }   // once more before you're done
            showAnswer = false
            index += 1
        } catch { model.error = error.localizedDescription }
    }

    func fav(model: AppModel) async {
        guard let x = current, let id = x.s("id") else { return }
        let on = !x.b("fav")
        do {
            try await API.shared.send("PUT", "/api/highlights/\(API.enc(id))/fav", ["fav": on])
            var raw = x.raw
            raw["fav"] = on
            items[index] = J(raw)
            model.say(on ? "Favorited: it comes back more often" : "No longer a favorite")
        } catch { model.error = error.localizedDescription }
    }
}

struct ReviewView: View {
    @Environment(AppModel.self) private var model
    @Environment(\.openWindow) private var openWindow
    @FocusState private var noteFocused: Bool
    @State private var sheet: HLSheet?
    private var review: ReviewModel { model.review }

    var body: some View {
        VStack(spacing: 0) {
            if !review.loaded {
                ProgressView().frame(maxWidth: .infinity, maxHeight: .infinity)
            } else if let x = review.current {
                ScrollView {
                    VStack(spacing: 22) {
                        Text("\(review.index + 1) of \(review.items.count)")
                            .font(.subheadline).foregroundStyle(.secondary).monospacedDigit()
                        if review.isCard { card(x) } else { highlight(x) }
                    }
                    .frame(maxWidth: 640)
                    .padding(.horizontal, 32)
                    .padding(.vertical, 40)
                    .frame(maxWidth: .infinity)
                }
                Divider()
                bar(x)
            } else {
                done
            }
        }
        .navigationTitle(review.theme.map { "Review: " + $0 } ?? "Daily Review")
        .task { await start() }
        .onChange(of: model.reviewTheme) { _, q in if q != nil { Task { await start() } } }
        .sheet(item: $sheet) { s in HLSheetView(sheet: s) }
        .onKeyPress(phases: .down) { press in keys(press) }
        .focusable()
        .focusEffectDisabled()
    }

    // MARK: a highlight

    private func highlight(_ x: J) -> some View {
        VStack(alignment: .leading, spacing: 16) {
            HLQuote(text: x.s("text") ?? "", size: 22)
                .frame(maxWidth: .infinity, alignment: .leading)
                .environment(\.layoutDirection, Self.hebrew(x.s("text")) ? .rightToLeft : .leftToRight)
            if let n = x.s("user_note") ?? x.s("note") {
                Text(n).font(.callout).foregroundStyle(.secondary)
                    .padding(10).frame(maxWidth: .infinity, alignment: .leading)
                    .background(.quaternary.opacity(0.5), in: RoundedRectangle(cornerRadius: 8))
            }
            VStack(alignment: .leading, spacing: 2) {
                Text(x.s("title") ?? "").font(.headline)
                Text([x.s("author"), x.s("chapter"), x.s("page").map { "page " + $0 }].compactMap { $0 }.joined(separator: " · "))
                    .font(.subheadline).foregroundStyle(.secondary)
            }
            if review.writing {
                TextField("A note, kept with the highlight and in the vault", text: Bindable(review).note, axis: .vertical)
                    .textFieldStyle(.roundedBorder)
                    .lineLimit(2...6)
                    .focused($noteFocused)
                    .onSubmit { Task { await review.act("note", model: model) } }
                    .onAppear { noteFocused = true }
            }
        }
    }

    // MARK: a flashcard

    private func card(_ x: J) -> some View {
        VStack(alignment: .leading, spacing: 18) {
            Text(Self.front(x, shown: review.showAnswer))
                .font(.system(size: 22, design: .serif))
                .lineSpacing(6)
                .frame(maxWidth: .infinity, alignment: .leading)
            if review.showAnswer, x.s("kind") == "qa" {
                Divider()
                Text(x.s("back") ?? "").font(.system(size: 19, design: .serif))
            }
            Text([x.s("title"), x.s("author")].compactMap { $0 }.joined(separator: " · ")).font(.subheadline).foregroundStyle(.secondary)
        }
    }

    static func front(_ x: J, shown: Bool) -> AttributedString {
        let f = x.s("front") ?? ""
        if x.s("kind") == "qa" { return AttributedString(f) }
        var out = AttributedString()
        var rest = Substring(f)
        while let open = rest.range(of: "{{"), let close = rest[open.upperBound...].range(of: "}}") {
            out += AttributedString(String(rest[..<open.lowerBound]))
            let word = String(rest[open.upperBound..<close.lowerBound])
            var w = AttributedString(shown ? word : String(repeating: "_", count: max(4, min(18, word.count))))
            if shown { w.backgroundColor = .yellow.opacity(0.35) } else { w.foregroundColor = .secondary }
            out += w
            rest = rest[close.upperBound...]
        }
        return out + AttributedString(String(rest))
    }

    static func hebrew(_ s: String?) -> Bool { s?.unicodeScalars.contains { (0x0590...0x05FF).contains($0.value) } ?? false }

    // MARK: the buttons

    @ViewBuilder
    private func bar(_ x: J) -> some View {
        HStack(spacing: 10) {
            if review.isCard {
                if !review.showAnswer {
                    Button("Show the Answer") { review.showAnswer = true }.keyboardShortcut(.space, modifiers: []).buttonStyle(.borderedProminent)
                } else {
                    ForEach(Array(["again", "hard", "good", "easy"].enumerated()), id: \.offset) { k, g in
                        Button(g.capitalized) { Task { await review.grade(g, model: model) } }
                            .keyboardShortcut(KeyEquivalent(Character("\(k + 1)")), modifiers: [])
                            .buttonStyle(.bordered)
                    }
                }
            } else {
                Button { Task { await review.act("less", model: model) } } label: { Label("Less Often", systemImage: "arrow.left") }
                Button { review.writing.toggle() } label: { Label("Note", systemImage: "square.and.pencil") }
                Button { Task { await review.act("never", model: model) } } label: { Label("Never", systemImage: "eye.slash") }
                Button { Task { await review.fav(model: model) } } label: { Label("Favorite", systemImage: x.b("fav") ? "star.fill" : "star") }
                if let open = x.s("open") {
                    Button { openWindow(id: "route", value: open) } label: { Label("Open at Its Spot", systemImage: "book") }
                }
                Menu {
                    Button("Tags…") { sheet = .tags(x) }
                    Button("Make a Flashcard…") { sheet = .cards(x) }
                    Button("Share as Image…") { sheet = .share(x, title: x.s("title") ?? "", author: x.s("author")) }
                    Button("Copy") { NSPasteboard.general.clearContents(); NSPasteboard.general.setString(x.s("text") ?? "", forType: .string) }
                } label: { Label("More", systemImage: "ellipsis.circle") }
                .menuStyle(.borderlessButton)
                .fixedSize()
                Spacer()
                if review.writing {
                    Button("Save the Note") { Task { await review.act("note", model: model) } }.buttonStyle(.borderedProminent)
                } else {
                    Button { Task { await review.act("keep", model: model) } } label: { Label("Keep", systemImage: "arrow.right") }
                        .buttonStyle(.borderedProminent)
                }
            }
        }
        .controlSize(.large)
        .padding(14)
    }

    /// The day's review, or a themed one asked for (Review These, Review More).
    private func start() async {
        model.review = ReviewModel()
        if let q = model.reviewTheme {
            model.reviewTheme = nil
            await model.review.load(themed: q)
        } else {
            await model.review.load(day: model.today?.s("today"))
        }
    }

    private var done: some View {
        ContentUnavailableView {
            Label(review.items.isEmpty ? (review.theme == nil ? "Nothing to review today" : "Nothing to review here") : review.theme == nil ? "That's today's review" : "That's the round", systemImage: "checkmark.circle")
        } description: {
            let kept = review.actions.values.filter { $0 == "keep" || $0 == "note" }.count
            let less = review.actions.values.filter { $0 == "less" }.count
            Text(review.items.isEmpty ? "New highlights come back here." : "\(kept) kept · \(less) less often · \(review.items.count) seen" + (review.streak?.i("days").map { " · \($0)-day streak" } ?? ""))
            if let week = review.streak?.a("week"), !week.isEmpty {
                HStack(spacing: 6) {
                    ForEach(week, id: \.self) { d in Circle().fill(d.b("done") ? Color.daf : Color.secondary.opacity(0.25)).frame(width: 9, height: 9) }
                }
                .padding(.top, 4)
            }
        } actions: {
            if let q = review.themedQuery { Button("Another Round") { model.startReview(themed: q) } }
            Button("Review More Highlights") { model.startReview(themed: "n=10") }
        }
    }

    // MARK: keys, as in the page: → keep, ← less, n note, f favorite, o open; space and 1–4 for cards

    private func keys(_ press: KeyPress) -> KeyPress.Result {
        guard !review.writing, let x = review.current else { return .ignored }
        if review.isCard {
            if press.key == .space, !review.showAnswer { review.showAnswer = true; return .handled }
            if review.showAnswer, let n = Int(press.characters), (1...4).contains(n) {
                Task { await review.grade(["again", "hard", "good", "easy"][n - 1], model: model) }
                return .handled
            }
            return .ignored
        }
        switch press.key {
        case .rightArrow: Task { await review.act("keep", model: model) }
        case .leftArrow: Task { await review.act("less", model: model) }
        default:
            switch press.characters {
            case "k": Task { await review.act("keep", model: model) }
            case "l": Task { await review.act("less", model: model) }
            case "n": review.writing = true
            case "f": Task { await review.fav(model: model) }
            case "o": if let open = x.s("open") { openWindow(id: "route", value: open) }
            default: return .ignored
            }
        }
        return .handled
    }
}
