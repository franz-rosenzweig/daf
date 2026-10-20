import Foundation

/// EPUB CFIs the way foliate-js (the page's book reader, web/vendor/foliate-js/epubcfi.js) writes
/// and reads them, over Foundation's XML tree: a place or a highlight made here is the very string
/// the page would make, and one made there lands on the same words here. Ported step for step,
/// down to its quirks (an id assertion is trusted when it's on the last step; an offset is written
/// only on a text step; a zero offset counts as none when the shared parent is worked out).
enum CFI {
    struct Part: Equatable {
        var index: Int
        var id: String?
        var offset: Int?
    }
    /// The steps, split at each "!" (the package, then the chapter).
    typealias Path = [[Part]]

    enum Parsed {
        case point(Path)
        case range(parent: Path, start: Path, end: Path)

        /// The start (or the end) of a range as one path; a point is itself.
        func collapse(toEnd: Bool = false) -> Path {
            switch self {
            case .point(let p): return p
            case .range(let parent, let start, let end):
                let x = toEnd ? end : start
                guard let last = parent.last else { return x }
                return Array(parent.dropLast()) + [last + (x.first ?? [])] + Array(x.dropFirst())
            }
        }
    }

    // MARK: reading

    private enum Token { case bang, comma, step(Int), offset(Int), other, assertion(String) }

    private static func tokens(_ s: String) -> [(kind: String, token: Token)] {
        var out: [(String, Token)] = []
        var state: String?
        var escape = false
        var value = ""
        func push(_ kind: String, _ t: Token) { out.append((kind, t)); state = nil; value = "" }
        func cat(_ c: Character) { value.append(c); escape = false }
        let chars: [Character?] = Array(s.trimmingCharacters(in: .whitespaces)).map { Optional($0) } + [nil]
        for char in chars {
            if char == "^" && !escape { escape = true; continue }
            let digit = char.map { $0.isASCII && $0.isNumber } ?? false
            if state == "!" { push("!", .bang) }
            else if state == "," { push(",", .comma) }
            else if state == "/" || state == ":" {
                if digit, let c = char { cat(c); continue }
                let n = Int(value) ?? 0
                push(state!, state == "/" ? .step(n) : .offset(n))
            } else if state == "~" {
                if (digit || char == "."), let c = char { cat(c); continue }
                push("~", .other)
            } else if state == "@" {
                if char == ":" { push("@", .other); state = "@"; continue }
                if (digit || char == "."), let c = char { cat(c); continue }
                push("@", .other)
            } else if state == "[" {
                if char == ";" && !escape { push("[", .assertion(value)); state = ";" }
                else if char == "," && !escape { push("[", .assertion(value)); state = "[" }
                else if char == "]" && !escape { push("[", .assertion(value)) }
                else if let c = char { cat(c) }
                continue
            } else if let st = state, st.hasPrefix(";") {
                if char == "=" && !escape { state = ";" + value; value = "" }
                else if char == ";" && !escape { push(st, .other); state = ";" }
                else if char == "]" && !escape { push(st, .other) }
                else if let c = char { cat(c) }
                continue
            }
            if let c = char, "/:~@[!,".contains(c) { state = String(c) }
        }
        return out
    }

    private static func parts(_ toks: ArraySlice<(kind: String, token: Token)>) -> [Part] {
        var parts: [Part] = []
        var state: String?
        for (kind, t) in toks {
            switch t {
            case .step(let n): parts.append(Part(index: n))
            case .offset(let n): if !parts.isEmpty { parts[parts.count - 1].offset = n }
            case .assertion(let v):
                if state == "/" && !v.isEmpty && !parts.isEmpty { parts[parts.count - 1].id = v }
                else { continue }                   // a text assertion: the state stays as it was
            default: break
            }
            state = kind
        }
        return parts
    }

    private static func indir(_ toks: ArraySlice<(kind: String, token: Token)>) -> Path {
        toks.split(omittingEmptySubsequences: false) { $0.kind == "!" }.map { parts($0) }
    }

    static func parse(_ cfi: String) -> Parsed {
        var s = cfi.trimmingCharacters(in: .whitespaces)
        if s.hasPrefix("epubcfi("), s.hasSuffix(")") { s = String(s.dropFirst(8).dropLast()) }
        let toks = tokens(s)[...]
        let pieces = toks.split(omittingEmptySubsequences: false) { $0.kind == "," }
        if pieces.count < 3 { return .point(indir(toks)) }
        return .range(parent: indir(pieces[0]), start: indir(pieces[1]), end: indir(pieces[2]))
    }

    // MARK: writing

    private static func escape(_ s: String) -> String {
        var out = ""
        for c in s { if "^[](),;=".contains(c) { out.append("^") }; out.append(c) }
        return out
    }

    private static func string(_ p: Part) -> String {
        "/\(p.index)" + ((p.id ?? "").isEmpty ? "" : "[\(escape(p.id!))]") + (p.offset != nil && p.index % 2 == 1 ? ":\(p.offset!)" : "")
    }

    static func string(_ path: Path) -> String { path.map { $0.map(string).joined() }.joined(separator: "!") }

    static func wrap(_ inner: String) -> String { "epubcfi(\(inner))" }
    static func unwrap(_ s: String) -> String { s.hasPrefix("epubcfi(") && s.hasSuffix(")") ? String(s.dropFirst(8).dropLast()) : s }

    /// The chapter's CFI and a CFI inside it, as one ("epubcfi(/6/8!/4/2/1:0)").
    static func join(_ section: String, _ local: String) -> String { wrap(unwrap(section) + "!" + unwrap(local)) }

    /// A range from two places, with their shared steps as the parent (foliate's buildRange).
    static func range(_ from: Path, _ to: Path) -> String {
        guard let a = from.last, let b = to.last else { return wrap(string(from)) }
        var parent: [Part] = [], start: [Part] = [], end: [Part] = []
        var shared = true
        for i in 0..<max(a.count, b.count) {
            let x = i < a.count ? a[i] : nil, y = i < b.count ? b[i] : nil
            shared = shared && x?.index == y?.index && (x?.offset ?? 0) == 0 && (y?.offset ?? 0) == 0
            if shared, let x { parent.append(x) }
            else {
                if let x { start.append(x) }
                if let y { end.append(y) }
            }
        }
        return wrap([Array(from.dropLast()) + [parent], [start], [end]].map(string).joined(separator: ","))
    }

    // MARK: the document's nodes, as CFI counts them

    /// A parent's children as CFI numbers them: elements at even indices, the text between them at
    /// odd ones (several text nodes in a row are one chunk; an empty gap still counts), and the
    /// "virtual" places before, first, last and after.
    enum Slot {
        case before, first, last, after, empty
        case node(XMLNode)
        case chunk([XMLNode])

        func holds(_ n: XMLNode) -> Bool {
            switch self {
            case .node(let x): return x === n
            case .chunk(let xs): return xs.contains { $0 === n }
            default: return false
            }
        }
    }

    static func isText(_ n: XMLNode) -> Bool { n.kind == .text }
    static func isElement(_ n: XMLNode) -> Bool { n.kind == .element }

    static func slots(_ node: XMLNode) -> [Slot] {
        var arr: [Slot] = []
        for n in node.children ?? [] where isText(n) || isElement(n) {
            guard let last = arr.last else { arr.append(.node(n)); continue }
            if isText(n) {
                switch last {
                case .chunk(let xs): arr[arr.count - 1] = .chunk(xs + [n])
                case .node(let l) where isText(l): arr[arr.count - 1] = .chunk([l, n])
                default: arr.append(.node(n))
                }
            } else {
                if case .node(let l) = last, isElement(l) { arr.append(.empty) }
                arr.append(.node(n))
            }
        }
        if case .node(let f)? = arr.first, isElement(f) { arr.insert(.first, at: 0) }
        if case .node(let l)? = arr.last, isElement(l) { arr.append(.last) }
        return [.before] + arr + [.after]
    }

    static func length(_ n: XMLNode) -> Int { ((n.stringValue ?? "") as NSString).length }

    static func elementID(_ n: XMLNode) -> String? {
        guard let e = n as? XMLElement, let v = e.attribute(forName: "id")?.stringValue, !v.isEmpty else { return nil }
        return v
    }

    /// A node and an offset in it (a text node's characters) as steps from the document's root element.
    static func parts(of node: XMLNode, offset: Int?) -> [Part] {
        guard let parent = node.parent else { return [] }
        let indexed = slots(parent)
        let index = indexed.firstIndex { $0.holds(node) } ?? -1
        var off = offset
        if index >= 0, case .chunk(let xs) = indexed[index] {
            var sum = 0
            for x in xs {
                if x === node { sum += offset ?? 0; break }
                sum += length(x)
            }
            off = sum
        }
        let part = Part(index: index, id: elementID(node), offset: off)
        let root = node.rootDocument?.rootElement()
        return (parent === root ? [part] : parts(of: parent, offset: nil) + [part]).filter { $0.index != -1 }
    }

    struct Found {
        let node: XMLNode
        var offset: Int?
        var before = false
        var after = false
    }

    /// Where steps lead in a document (foliate's partsToNode); `ids` finds an element by its id.
    static func find(_ steps: [Part], in root: XMLNode, ids: [String: XMLElement]) -> Found? {
        if let id = steps.last?.id, let el = ids[id] { return Found(node: el, offset: 0) }
        var node: Slot = .node(root)
        for p in steps {
            guard case .node(let n) = node else { return nil }
            let kids = slots(n)
            let next = p.index >= 0 && p.index < kids.count ? kids[p.index] : nil
            switch next {
            case .first?: return Found(node: n.child(at: 0) ?? n)
            case .last?: return Found(node: n.children?.last ?? n)
            case .before?: return Found(node: n, before: true)
            case .after?: return Found(node: n, after: true)
            case nil: return nil
            default: node = next!
            }
        }
        let offset = steps.last?.offset
        switch node {
        case .node(let n): return Found(node: n, offset: offset)
        case .chunk(let xs):
            var sum = 0
            for x in xs {
                let len = length(x)
                if sum + len >= (offset ?? 0) { return Found(node: x, offset: (offset ?? 0) - sum) }
                sum += len
            }
            return xs.last.map { Found(node: $0, offset: length($0)) }
        default: return nil
        }
    }

    /// The CFI of each itemref in the package's spine, as foliate makes them (fromElements).
    static func spine(_ itemrefs: [XMLElement]) -> [String] {
        guard let spine = itemrefs.first?.parent else { return [] }
        let base = parts(of: spine, offset: nil)
        var out: [String] = []
        for (index, slot) in slots(spine).enumerated() {
            guard out.count < itemrefs.count, case .node(let n) = slot, n === itemrefs[out.count] else { continue }
            out.append(wrap(string([base + [Part(index: index, id: elementID(n))]])))
        }
        return out
    }
}
