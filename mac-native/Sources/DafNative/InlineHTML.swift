import AppKit

/// A block's inline HTML (Daf's "h": <strong>, <em>, <a href>, <code>, <br>, entities) as styled text.
/// The plain text must come out the same as the block's "x", since highlights point into that by
/// character; when it doesn't, the plain text is used as it is.
enum InlineHTML {
    static func styled(_ html: String?, plain: String, base: [NSAttributedString.Key: Any], baseURL: URL) -> NSAttributedString {
        guard let html, !html.isEmpty else { return NSAttributedString(string: plain, attributes: base) }
        let out = NSMutableAttributedString()
        var bold = 0, italic = 0, code = 0
        var links: [URL?] = []
        var i = html.startIndex
        var text = ""

        func flush() {
            guard !text.isEmpty else { return }
            var a = base
            let f = (base[.font] as? NSFont) ?? NSFont.systemFont(ofSize: 17)
            var traits: NSFontDescriptor.SymbolicTraits = []
            if bold > 0 { traits.insert(.bold) }
            if italic > 0 { traits.insert(.italic) }
            if code > 0 {
                a[.font] = NSFont.monospacedSystemFont(ofSize: f.pointSize * 0.88, weight: .regular)
            } else if !traits.isEmpty {
                let d = f.fontDescriptor.withSymbolicTraits(f.fontDescriptor.symbolicTraits.union(traits))
                a[.font] = NSFont(descriptor: d, size: f.pointSize) ?? f
            }
            if let u = links.last ?? nil {
                a[.link] = u
            }
            out.append(NSAttributedString(string: decode(text), attributes: a))
            text = ""
        }

        while i < html.endIndex {
            let c = html[i]
            if c == "<", let close = html[i...].firstIndex(of: ">") {
                flush()
                let tag = html[html.index(after: i)..<close].trimmingCharacters(in: .whitespaces)
                let lower = tag.lowercased()
                let name = lower.split(whereSeparator: { $0 == " " || $0 == "/" }).first.map(String.init) ?? ""
                let closing = lower.hasPrefix("/")
                switch closing ? String(lower.dropFirst()).split(separator: " ").first.map(String.init) ?? "" : name {
                case "b", "strong": bold += closing ? -1 : 1
                case "i", "em", "cite": italic += closing ? -1 : 1
                case "code", "kbd", "samp": code += closing ? -1 : 1
                case "a":
                    if closing { if !links.isEmpty { links.removeLast() } }
                    else { links.append(href(tag).flatMap { URL(string: $0, relativeTo: baseURL)?.absoluteURL }) }
                case "br": if !closing { text += "\n" }
                default: break
                }
                bold = max(bold, 0); italic = max(italic, 0); code = max(code, 0)
                i = html.index(after: close)
            } else {
                text.append(c)
                i = html.index(after: i)
            }
        }
        flush()
        return out.string == plain ? out : NSAttributedString(string: plain, attributes: base)
    }

    private static func href(_ tag: String) -> String? {
        guard let r = tag.range(of: "href=", options: .caseInsensitive) else { return nil }
        var rest = tag[r.upperBound...]
        guard let q = rest.first, q == "\"" || q == "'" else { return rest.split(separator: " ").first.map(String.init) }
        rest = rest.dropFirst()
        return rest.firstIndex(of: q).map { decode(String(rest[..<$0])) }
    }

    static func decode(_ s: String) -> String {
        guard s.contains("&") else { return s }
        var out = s
        let named = ["&amp;": "&", "&lt;": "<", "&gt;": ">", "&quot;": "\"", "&#39;": "'", "&apos;": "'", "&nbsp;": "\u{a0}",
                     "&mdash;": "—", "&ndash;": "–", "&hellip;": "…", "&rsquo;": "’", "&lsquo;": "‘", "&rdquo;": "”", "&ldquo;": "“"]
        for (k, v) in named where k != "&amp;" { out = out.replacingOccurrences(of: k, with: v) }
        // numeric ones: &#8217; &#x2019;
        var result = ""
        var i = out.startIndex
        while i < out.endIndex {
            if out[i] == "&", out[i...].hasPrefix("&#"), let semi = out[i...].firstIndex(of: ";"), out.distance(from: i, to: semi) < 10 {
                let body = out[out.index(i, offsetBy: 2)..<semi]
                let n = body.hasPrefix("x") || body.hasPrefix("X") ? UInt32(body.dropFirst(), radix: 16) : UInt32(body)
                if let n, let u = Unicode.Scalar(n) { result.unicodeScalars.append(u); i = out.index(after: semi); continue }
            }
            result.append(out[i])
            i = out.index(after: i)
        }
        return result.replacingOccurrences(of: "&amp;", with: "&")
    }
}
