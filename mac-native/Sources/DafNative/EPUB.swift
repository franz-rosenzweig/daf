import Foundation

/// An EPUB opened from its file: the package's spine (with each chapter's CFI and size, as foliate
/// counts them for the place and the percentage), the contents, the printed pages, and the files.
final class EPUB {
    let zip: Zip
    let opfPath: String
    private(set) var title = ""
    private(set) var sections: [Section] = []
    private(set) var toc: [TOCItem] = []
    private(set) var pageList: [Target] = []
    /// Right to left (the spine's page-progression-direction, or a Hebrew book).
    private(set) var rtl = false
    private(set) var language = ""
    private var manifest: [String: (path: String, type: String, props: [String])] = [:]
    private var sectionByPath: [String: Int] = [:]

    struct Section {
        let index: Int
        let path: String
        let type: String
        let linear: Bool
        /// The file's size, which foliate weighs chapters by.
        let size: Int
        /// The itemref's CFI ("epubcfi(/6/8)"), which every place in the chapter starts with.
        let cfi: String
    }

    struct TOCItem: Identifiable, Hashable {
        let id: Int
        let label: String
        let target: Target
        let children: [TOCItem]
        var flat: [TOCItem] { [self] + children.flatMap(\.flat) }
    }

    struct Target: Hashable {
        let label: String
        let path: String
        let fragment: String?
    }

    enum Failure: LocalizedError {
        case noPackage
        var errorDescription: String? { "The book's contents list (its package) is missing or damaged." }
    }

    init(_ data: Data) throws {
        zip = try Zip(data)
        guard let c = zip.read("META-INF/container.xml"), let cx = try? XMLDocument(data: c),
              let rootfile = Self.all(cx.rootElement(), "rootfile").first?.attribute(forName: "full-path")?.stringValue,
              let od = zip.read(rootfile), let opf = try? XMLDocument(data: od, options: [.nodePreserveWhitespace]),
              let package = opf.rootElement() else { throw Failure.noPackage }
        opfPath = rootfile
        let meta = Self.kids(package, "metadata").first
        title = meta.flatMap { Self.kids($0, "title").first?.stringValue } ?? ""
        language = meta.flatMap { Self.kids($0, "language").first?.stringValue } ?? ""
        for item in Self.kids(Self.kids(package, "manifest").first, "item") {
            guard let id = item.attribute(forName: "id")?.stringValue, let href = item.attribute(forName: "href")?.stringValue else { continue }
            manifest[id] = (Self.resolve(href, from: rootfile), item.attribute(forName: "media-type")?.stringValue ?? "",
                            (item.attribute(forName: "properties")?.stringValue ?? "").split(separator: " ").map(String.init))
        }
        let spine = Self.kids(package, "spine").first
        rtl = spine?.attribute(forName: "page-progression-direction")?.stringValue == "rtl" || language.hasPrefix("he") || language.hasPrefix("ar")
        let itemrefs = Self.kids(spine, "itemref")
        let cfis = CFI.spine(itemrefs)
        for (k, ref) in itemrefs.enumerated() {
            guard let idref = ref.attribute(forName: "idref")?.stringValue, let item = manifest[idref] else { continue }
            let index = sections.count
            sections.append(Section(index: index, path: item.path, type: item.type, linear: ref.attribute(forName: "linear")?.stringValue != "no",
                                    size: zip.entries[item.path]?.size ?? 0, cfi: k < cfis.count ? cfis[k] : CFI.wrap("/6/\((k + 1) * 2)")))
            sectionByPath[item.path] = index
        }
        loadContents(spine: spine)
    }

    // MARK: the files

    func data(_ path: String) -> Data? { zip.read(path) }

    func section(of path: String) -> Int? { sectionByPath[path] }

    /// A chapter's own CFI to its index ("epubcfi(/6/8!…)" → the 4th chapter): by the step, as
    /// foliate does when the itemref's id isn't the one it was made with.
    func section(ofCFI parsed: CFI.Parsed) -> Int? {
        guard let top = parsed.collapse().first, let step = top.last?.index else { return nil }
        if let k = sections.firstIndex(where: { CFI.parse($0.cfi).collapse().first?.last?.index == step }) { return k }
        return step / 2 - 1 < sections.count ? max(0, step / 2 - 1) : nil
    }

    // MARK: the contents and the printed pages

    private func loadContents(spine: XMLElement?) {
        var n = 0
        func item(_ label: String, _ href: String, base: String, _ children: [TOCItem]) -> TOCItem {
            n += 1
            let parts = href.split(separator: "#", maxSplits: 1, omittingEmptySubsequences: false)
            let path = parts.first.map { $0.isEmpty ? base : Self.resolve(String($0), from: base) } ?? base
            let label = label.split(whereSeparator: \.isWhitespace).joined(separator: " ")
            return TOCItem(id: n, label: label, target: Target(label: label, path: path, fragment: parts.count > 1 ? String(parts[1]) : nil), children: children)
        }
        // EPUB 3: the nav document
        if let nav = manifest.values.first(where: { $0.props.contains("nav") }), let d = data(nav.path),
           let doc = try? XMLDocument(data: Entities.numbered(String(decoding: d, as: UTF8.self)).data(using: .utf8)!, options: [.nodePreserveWhitespace]) {
            func list(_ ol: XMLElement?) -> [TOCItem] {
                Self.kids(ol, "li").map { li in
                    let a = Self.kids(li, "a").first ?? Self.kids(li, "span").first
                    return item(a?.stringValue ?? "", a?.attribute(forName: "href")?.stringValue ?? "", base: nav.path, list(Self.kids(li, "ol").first))
                }
            }
            for navEl in Self.all(doc.rootElement(), "nav") {
                let type = navEl.attributes?.first(where: { $0.localName == "type" })?.stringValue ?? ""
                let items = list(Self.kids(navEl, "ol").first)
                if type.contains("toc"), toc.isEmpty { toc = items }
                if type.contains("page-list") { pageList = items.flatMap(\.flat).map(\.target) }
            }
        }
        // EPUB 2: the NCX
        if toc.isEmpty, let ncxID = spine?.attribute(forName: "toc")?.stringValue ?? manifest.first(where: { $0.value.type == "application/x-dtbncx+xml" })?.key,
           let ncx = manifest[ncxID], let d = data(ncx.path), let doc = try? XMLDocument(data: d) {
            func points(_ parent: XMLElement?) -> [TOCItem] {
                Self.kids(parent, "navPoint").map { p in
                    let label = Self.kids(Self.kids(p, "navLabel").first, "text").first?.stringValue ?? ""
                    let src = Self.kids(p, "content").first?.attribute(forName: "src")?.stringValue ?? ""
                    return item(label, src, base: ncx.path, points(p))
                }
            }
            toc = points(Self.all(doc.rootElement(), "navMap").first)
            if pageList.isEmpty, let pl = Self.all(doc.rootElement(), "pageList").first {
                pageList = Self.kids(pl, "pageTarget").map { t in
                    item(Self.kids(Self.kids(t, "navLabel").first, "text").first?.stringValue ?? "", Self.kids(t, "content").first?.attribute(forName: "src")?.stringValue ?? "", base: ncx.path, []).target
                }
            }
        }
        if toc.isEmpty { toc = sections.map { item("Part \($0.index + 1)", "", base: $0.path, []) } }
    }

    // MARK: XML helpers

    static func kids(_ n: XMLElement?, _ name: String) -> [XMLElement] {
        (n?.children ?? []).compactMap { $0 as? XMLElement }.filter { ($0.localName ?? $0.name) == name }
    }

    static func all(_ n: XMLElement?, _ name: String) -> [XMLElement] {
        guard let n else { return [] }
        var out: [XMLElement] = []
        for c in n.children ?? [] {
            guard let e = c as? XMLElement else { continue }
            if (e.localName ?? e.name) == name { out.append(e) }
            out += all(e, name)
        }
        return out
    }

    /// A link from one file of the book to another, as a path in the ZIP ("OEBPS/images/a.jpg").
    static func resolve(_ href: String, from base: String) -> String {
        let clean = (href.split(separator: "#", maxSplits: 1, omittingEmptySubsequences: false).first.map(String.init) ?? href)
        let decoded = clean.removingPercentEncoding ?? clean
        if decoded.hasPrefix("/") { return String(decoded.dropFirst()) }
        var parts = base.split(separator: "/", omittingEmptySubsequences: false).dropLast().map(String.init)
        for p in decoded.split(separator: "/", omittingEmptySubsequences: false).map(String.init) {
            if p == ".." { if !parts.isEmpty { parts.removeLast() } } else if p != "." && !p.isEmpty { parts.append(p) }
        }
        return parts.joined(separator: "/")
    }
}
