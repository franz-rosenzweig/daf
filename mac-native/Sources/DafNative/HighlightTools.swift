import AppKit
import SwiftUI

/// What a highlight can have done to it wherever it shows (an article, a book, Highlights): its
/// tags, flashcards made from it, a card of it to share, a word in it looked up. As the page's
/// highlight bar (web/hl.js) and lookup (web/torah.js).
enum HLSheet: Identifiable {
    case tags(J)
    case cards(J)
    case share(J, title: String, author: String?)
    case lookup(String, sentence: String, translate: Bool)

    var id: String {
        switch self {
        case .tags(let h): return "tags " + (h.s("id") ?? "")
        case .cards(let h): return "cards " + (h.s("id") ?? "")
        case .share(let h, _, _): return "share " + (h.s("id") ?? "")
        case .lookup(let w, _, _): return "lookup " + w
        }
    }
}

/// The sheet for an HLSheet; `changed` hears what changed on the highlight (its tags, its cards).
struct HLSheetView: View {
    let sheet: HLSheet
    var changed: (String, [String: Any]) -> Void = { _, _ in }

    var body: some View {
        switch sheet {
        case .tags(let h): HighlightTagsSheet(h: h, changed: changed)
        case .cards(let h): FlashcardSheet(h: h, changed: changed)
        case .share(let h, let title, let author): ShareCardSheet(h: h, title: title, author: author)
        case .lookup(let w, let sentence, let translate): LookupSheet(word: w, sentence: sentence, translate: translate)
        }
    }
}

@MainActor
enum HLTools {
    static func fav(_ id: String, _ on: Bool) async -> Bool {
        do { try await API.shared.send("PUT", "/api/highlights/\(API.enc(id))/fav", ["fav": on]); return true }
        catch { AppModel.shared.error = error.localizedDescription; return false }
    }

    /// Never in review again, or back into it.
    static func review(_ id: String, never: Bool) async -> Bool {
        do {
            try await API.shared.send("POST", "/api/review/\(API.enc(id))", ["action": never ? "never" : "back"])
            AppModel.shared.say(never ? "It won't come up in review again" : "Back in review")
            return true
        } catch { AppModel.shared.error = error.localizedDescription; return false }
    }

    /// The colour the next highlight takes: the last one chosen, as the page does.
    static var lastColour: String { UserDefaults.standard.string(forKey: "hlColor") ?? "yellow" }
    static func chose(_ c: String) { UserDefaults.standard.set(c, forKey: "hlColor") }

    /// Highlighting a selection when it's made (hold ⌥ to select without), as the page does.
    static var autoHighlight: Bool { UserDefaults.standard.object(forKey: "autoHighlight") as? Bool ?? true }

    /// One word (or a short Hebrew phrase) to look up: Define for a word, Translate for Hebrew.
    static func lookupWord(_ s: String) -> (word: String, translate: Bool)? {
        let t = s.trimmingCharacters(in: .whitespacesAndNewlines.union(.punctuationCharacters))
        guard !t.isEmpty else { return nil }
        if t.range(of: "\\p{Hebrew}", options: .regularExpression) != nil, t.count <= 60 { return (t, true) }
        if !t.contains(" "), t.count <= 40 { return (t, false) }
        return nil
    }
}

// MARK: tags

struct HighlightTagsSheet: View {
    let h: J
    let changed: (String, [String: Any]) -> Void
    @Environment(\.dismiss) private var dismiss
    @State private var tags: [String] = []
    @State private var all: [String] = []
    @State private var field = ""

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text(h.s("text") ?? "").font(.system(.callout, design: .serif)).foregroundStyle(.secondary).lineLimit(3)
            Flow {
                ForEach(tags, id: \.self) { t in
                    HStack(spacing: 4) {
                        Text("#" + t)
                        Image(systemName: "xmark.circle.fill").foregroundStyle(Color.secondary).onTapGesture { tags.removeAll { $0 == t } }
                    }
                    .font(.callout)
                    .padding(.leading, 9).padding(.trailing, 5).padding(.vertical, 3)
                    .background(Capsule().fill(Color.accentColor.opacity(0.14)))
                }
            }
            TextField("Add a tag (Return or a comma adds it)", text: $field)
                .textFieldStyle(.roundedBorder)
                .onSubmit { add(field) }
                .onChange(of: field) { _, v in if v.hasSuffix(",") { add(String(v.dropLast())) } }
            let hints = all.filter { !field.isEmpty && $0.hasPrefix(field.lowercased()) && !tags.contains($0) }.prefix(8)
            if !hints.isEmpty {
                Flow { ForEach(Array(hints), id: \.self) { t in Button("#" + t) { add(t) }.buttonStyle(.bordered).controlSize(.small) } }
            }
            HStack {
                Spacer()
                Button("Cancel") { dismiss() }.keyboardShortcut(.cancelAction)
                Button("Save") { Task { await save() } }.keyboardShortcut(.defaultAction)
            }
        }
        .padding(20)
        .frame(width: 460)
        .task {
            tags = h.strings("tags")
            all = (try? await API.shared.json("/api/highlights/tags"))?.strings("tags") ?? []
        }
    }

    /// As the page has them: lower case, words joined with hyphens.
    private func add(_ raw: String) {
        let t = raw.trimmingCharacters(in: .whitespaces).lowercased().replacingOccurrences(of: "#", with: "")
            .split(whereSeparator: \.isWhitespace).joined(separator: "-")
        field = ""
        if !t.isEmpty && !tags.contains(t) { tags.append(t) }
    }

    private func save() async {
        if !field.isEmpty { add(field) }
        let id = h.s("id") ?? ""
        do {
            let r = J(try await API.shared.send("PUT", "/api/highlights/\(API.enc(id))/tags", ["tags": tags]))
            changed(id, ["tags": r?.strings("tags") ?? tags])
            dismiss()
        } catch { AppModel.shared.error = error.localizedDescription }
    }
}

// MARK: flashcards

/// Flashcards from a highlight: fill in the blank (click words to hide them) or a question and its
/// answer; Suggest asks Daf for one; the cards it has, with Edit and Delete. As the page's card editor.
struct FlashcardSheet: View {
    let h: J
    let changed: (String, [String: Any]) -> Void
    @Environment(\.dismiss) private var dismiss
    @State private var cards: [J] = []
    @State private var kind = "cloze"
    @State private var hidden: Set<Int> = []
    @State private var question = ""
    @State private var answer = ""
    @State private var editing: String?
    @State private var busy = false

    private var words: [String] { (h.s("text") ?? "").split(whereSeparator: \.isWhitespace).map(String.init) }

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            if !cards.isEmpty {
                Text("Its flashcards").font(.headline)
                ForEach(cards, id: \.self) { c in
                    HStack(alignment: .top) {
                        Text(Self.shown(c)).font(.callout).lineLimit(3)
                        Spacer()
                        Button("Edit") { load(c) }.buttonStyle(.link)
                        Button("Delete") { Task { await delete(c) } }.buttonStyle(.link)
                    }
                }
                Divider()
            }
            Picker("", selection: $kind) {
                Text("Fill in the Blank").tag("cloze")
                Text("Question").tag("qa")
            }
            .pickerStyle(.segmented)
            .labelsHidden()
            if kind == "cloze" {
                Text("Click the words to hide").font(.caption).foregroundStyle(.secondary)
                Flow(spacing: 4) {
                    ForEach(Array(words.enumerated()), id: \.offset) { i, w in
                        Text(w)
                            .font(.system(.body, design: .serif))
                            .padding(.horizontal, 3).padding(.vertical, 1)
                            .background(RoundedRectangle(cornerRadius: 4).fill(hidden.contains(i) ? Color.accentColor.opacity(0.35) : .clear))
                            .onTapGesture { if hidden.contains(i) { hidden.remove(i) } else { hidden.insert(i) } }
                    }
                }
            } else {
                TextField("Question", text: $question, axis: .vertical).textFieldStyle(.roundedBorder)
                TextField("Answer", text: $answer, axis: .vertical).textFieldStyle(.roundedBorder)
            }
            HStack {
                Button("Suggest a Card") { Task { await suggest() } }.disabled(busy)
                if busy { ProgressView().controlSize(.small) }
                Spacer()
                Button("Done") { dismiss() }.keyboardShortcut(.cancelAction)
                Button(editing == nil ? "Add the Card" : "Save the Card") { Task { await save() } }
                    .keyboardShortcut(.defaultAction)
                    .disabled(kind == "cloze" ? hidden.isEmpty : question.isEmpty || answer.isEmpty)
            }
        }
        .padding(20)
        .frame(width: 520)
        .task { await reload() }
    }

    /// A card as it reads: the hidden words as blanks.
    static func shown(_ c: J) -> String {
        let f = c.s("front") ?? ""
        return c.s("kind") == "cloze" ? f.replacingOccurrences(of: "\\{\\{(.+?)\\}\\}", with: "[…]", options: .regularExpression) : f + " → " + (c.s("back") ?? "")
    }

    private var id: String { h.s("id") ?? "" }

    private func reload() async {
        cards = (try? await API.shared.json("/api/highlights/\(API.enc(id))/cards"))?.a("cards") ?? []
    }

    private func load(_ c: J) {
        editing = c.s("id")
        kind = c.s("kind") ?? "cloze"
        if kind == "qa" { question = c.s("front") ?? ""; answer = c.s("back") ?? "" }
        else {
            let f = c.s("front") ?? ""
            let hid = Set((try? NSRegularExpression(pattern: "\\{\\{(.+?)\\}\\}"))?.matches(in: f, range: NSRange(f.startIndex..., in: f))
                .compactMap { Range($0.range(at: 1), in: f).map { String(f[$0]) } } ?? [])
            hidden = Set(words.enumerated().filter { hid.contains($0.element) }.map(\.offset))
        }
    }

    private func save() async {
        var body: [String: Any] = ["kind": kind]
        if kind == "cloze" {
            body["front"] = words.enumerated().map { hidden.contains($0.offset) ? "{{\($0.element)}}" : $0.element }.joined(separator: " ")
        } else { body["front"] = question; body["back"] = answer }
        if let editing { body["id"] = editing }
        do {
            let r = J(try await API.shared.send("POST", "/api/highlights/\(API.enc(id))/cards", body))
            cards = r?.a("cards") ?? cards
            changed(id, ["cards": cards.count])
            AppModel.shared.say(editing == nil ? "A flashcard made" : "Card saved")
            editing = nil; hidden = []; question = ""; answer = ""
        } catch { AppModel.shared.error = error.localizedDescription }
    }

    private func delete(_ c: J) async {
        do {
            try await API.shared.send("DELETE", "/api/cards/\(API.enc(c.s("id") ?? ""))", nil)
            await reload()
            changed(id, ["cards": cards.count])
        } catch { AppModel.shared.error = error.localizedDescription }
    }

    private func suggest() async {
        busy = true
        defer { busy = false }
        guard let r = try? await API.shared.send("POST", "/api/highlights/\(API.enc(id))/cards/suggest", [:]), let s = J(r) else { return }
        if let q = s.s("question"), let a = s.s("answer"), kind == "qa" || s.s("cloze") == nil { kind = "qa"; question = q; answer = a; return }
        if let cz = s.s("cloze") {
            let hid = Set((try? NSRegularExpression(pattern: "\\{\\{(.+?)\\}\\}"))?.matches(in: cz, range: NSRange(cz.startIndex..., in: cz))
                .compactMap { Range($0.range(at: 1), in: cz).map { String(cz[$0]) } } ?? [])
            kind = "cloze"
            hidden = Set(words.enumerated().filter { w in hid.contains { $0.contains(w.element) } }.map(\.offset))
        }
    }
}

// MARK: share as an image

/// The highlight as a card to share (1080 by 1350, as the page makes it): the quote, its colour,
/// the title and the author, and Daf's name.
struct ShareCard: View {
    let h: J
    let title: String
    let author: String?

    var body: some View {
        let he = (h.s("text") ?? "").range(of: "\\p{Hebrew}", options: .regularExpression) != nil
        VStack(alignment: he ? .trailing : .leading, spacing: 40) {
            Rectangle().fill(Color(ReaderModel.colour(h.s("color")).withAlphaComponent(1))).frame(width: 120, height: 10)
            Text(h.s("text") ?? "")
                .font(.system(size: (h.s("text") ?? "").count > 420 ? 40 : 52, design: .serif))
                .lineSpacing(10)
                .foregroundStyle(Color(white: 0.12))
                .multilineTextAlignment(he ? .trailing : .leading)
                .minimumScaleFactor(0.4)
            Spacer(minLength: 0)
            VStack(alignment: he ? .trailing : .leading, spacing: 8) {
                Text(title).font(.system(size: 34, weight: .semibold, design: .serif)).foregroundStyle(Color(white: 0.15)).lineLimit(2)
                if let author { Text(author).font(.system(size: 28)).foregroundStyle(Color(white: 0.4)) }
            }
            Text("Daf").font(.system(size: 24, weight: .semibold)).foregroundStyle(Color(white: 0.55))
        }
        .padding(90)
        .frame(width: 1080, height: 1350, alignment: he ? .topTrailing : .topLeading)
        .background(Color(red: 0.99, green: 0.98, blue: 0.96))
        .environment(\.layoutDirection, he ? .rightToLeft : .leftToRight)
    }

    @MainActor
    func png() -> Data? {
        let r = ImageRenderer(content: self)
        r.scale = 1
        return r.nsImage?.tiffRepresentation.flatMap { NSBitmapImageRep(data: $0)?.representation(using: .png, properties: [:]) }
    }
}

struct ShareCardSheet: View {
    let h: J
    let title: String
    let author: String?
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        let card = ShareCard(h: h, title: title, author: author)
        VStack(spacing: 14) {
            card.scaleEffect(0.32).frame(width: 1080 * 0.32, height: 1350 * 0.32)
                .shadow(radius: 6, y: 2)
            HStack {
                ShareLink(item: ShareImage(png: card.png() ?? Data()), preview: SharePreview("A highlight from \(title)")) { Label("Share…", systemImage: "square.and.arrow.up") }
                Button("Copy the Image") {
                    if let d = card.png(), let img = NSImage(data: d) { NSPasteboard.general.clearContents(); NSPasteboard.general.writeObjects([img]); AppModel.shared.say("Copied") }
                }
                Button("Save…") {
                    let p = NSSavePanel()
                    p.nameFieldStringValue = "A highlight from \(title.prefix(40)).png"
                    if p.runModal() == .OK, let url = p.url, let d = card.png() { try? d.write(to: url) }
                }
                Spacer()
                Button("Done") { dismiss() }.keyboardShortcut(.defaultAction)
            }
        }
        .padding(20)
        .frame(width: 420)
    }
}

/// The card's PNG, for the share menu.
struct ShareImage: Transferable {
    let png: Data
    static var transferRepresentation: some TransferRepresentation { DataRepresentation(exportedContentType: .png) { $0.png } }
}

// MARK: Define and Translate

/// A word looked up as the page does: the dictionary (Wiktionary, or Sefaria for Hebrew), and "In
/// this sentence", where Daf explains the word where it stands.
struct LookupSheet: View {
    let word: String
    let sentence: String
    let translate: Bool
    @Environment(\.dismiss) private var dismiss
    @State private var found: J?
    @State private var context: String?
    @State private var asking = false

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text(word).font(.system(.title2, design: .serif).weight(.semibold))
            if !translate {
                if let f = found {
                    if f.a("entries").isEmpty { Text("Not in \(f.s("source") ?? "the dictionary").").foregroundStyle(.secondary) }
                    ForEach(Array(f.a("entries").enumerated()), id: \.offset) { _, e in
                        VStack(alignment: .leading, spacing: 3) {
                            Text([e.s("head"), e.s("pos")].compactMap { $0 }.joined(separator: " · ")).font(.callout.weight(.semibold))
                            ForEach(e.strings("defs"), id: \.self) { d in Text("• " + d).font(.callout) }
                            if let s = e.s("source") { Text(s).font(.caption2).foregroundStyle(.tertiary) }
                        }
                    }
                } else { ProgressView() }
            }
            if let context { Text(Inspector.markdown(context)).font(.callout).textSelection(.enabled) }
            if asking { HStack { ProgressView().controlSize(.small); Text("Thinking it over…").foregroundStyle(.secondary) } }
            HStack {
                if context == nil && !sentence.isEmpty { Button(translate ? "Translate It Here" : "In This Sentence") { Task { await inContext() } }.disabled(asking) }
                Spacer()
                Button("Done") { dismiss() }.keyboardShortcut(.defaultAction)
            }
        }
        .padding(20)
        .frame(width: 440)
        .task {
            if translate { await inContext() } else { found = try? await API.shared.json("/api/lookup?q=" + API.enc(word)) }
        }
    }

    private func inContext() async {
        asking = true
        defer { asking = false }
        context = J(try? await API.shared.send("POST", "/api/lookup/context", ["word": word, "sentence": sentence]))?.s("answer") ?? "Daf didn't answer."
    }
}

// MARK: the right-click menu on a highlight, shared by the readers

/// A reader that shows highlights (an article, a book): what the shared menu needs from it.
@MainActor
protocol HighlightHost: AnyObject {
    func highlight(withID hid: String) -> J?
    var sheet: HLSheet? { get set }
    var editing: ReaderModel.Editing? { get set }
    func set(color: String, of hid: String) async
    func remove(highlight hid: String) async
    func changed(_ hid: String, _ f: (inout [String: Any]) -> Void)
    var shareTitle: String { get }
    var shareAuthor: String? { get }
    /// The paragraph a character is in, for Define's "In This Sentence".
    func paragraph(around loc: Int) -> String
}

/// A menu item that runs a closure (the item keeps it).
final class MenuAction: NSObject {
    let run: () -> Void
    init(_ run: @escaping () -> Void) { self.run = run }
    @objc func go() { run() }

    static func item(_ title: String, checked: Bool = false, _ run: @escaping () -> Void) -> NSMenuItem {
        let a = MenuAction(run)
        let i = NSMenuItem(title: title, action: #selector(go), keyEquivalent: "")
        i.target = a
        i.representedObject = a
        i.state = checked ? .on : .off
        return i
    }
}

@MainActor
enum HLMenu {
    /// What a highlight under the pointer can do: as the page's highlight bar and its More menu.
    static func items(for hid: String, host: HighlightHost, kindle: Bool = false) -> [NSMenuItem] {
        guard let h = host.highlight(withID: hid) else { return [] }
        var out: [NSMenuItem] = []
        out.append(MenuAction.item((h.s("user_note") ?? "").isEmpty ? "Add a Note…" : "Edit the Note…") { host.editing = .init(h: h) })
        out.append(MenuAction.item("Tags…") { host.sheet = .tags(h) })
        let colours = NSMenuItem(title: "Color", action: nil, keyEquivalent: "")
        let sub = NSMenu()
        for c in ["yellow", "green", "blue", "pink", "purple"] {
            sub.addItem(MenuAction.item(c.capitalized, checked: (h.s("color") ?? "yellow") == c) { Task { HLTools.chose(c); await host.set(color: c, of: hid) } })
        }
        colours.submenu = sub
        out.append(colours)
        let fav = h.b("fav")
        out.append(MenuAction.item(fav ? "Not a Favorite" : "Favorite") { Task { if await HLTools.fav(hid, !fav) { host.changed(hid) { $0["fav"] = !fav } } } })
        out.append(MenuAction.item("Make a Flashcard…") { host.sheet = .cards(h) })
        out.append(MenuAction.item("Copy the Highlight") { NSPasteboard.general.clearContents(); NSPasteboard.general.setString(h.s("text") ?? "", forType: .string) })
        out.append(MenuAction.item("Share as Image…") { host.sheet = .share(h, title: host.shareTitle, author: host.shareAuthor) })
        if !kindle { out.append(MenuAction.item("Remove Highlight") { Task { await host.remove(highlight: hid) } }) }
        return out
    }

    /// Define a word, or translate Hebrew, from a selection.
    static func lookup(_ selected: String, at loc: Int, host: HighlightHost) -> NSMenuItem? {
        guard let w = HLTools.lookupWord(selected) else { return nil }
        return MenuAction.item(w.translate ? "Translate “\(w.word.prefix(24))”" : "Define “\(w.word)”") {
            host.sheet = .lookup(w.word, sentence: host.paragraph(around: loc), translate: w.translate)
        }
    }
}
