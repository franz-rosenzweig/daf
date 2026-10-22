import Compression
import Foundation

/// As much of ZIP as an EPUB needs: the central directory, and entries stored or deflated.
struct Zip {
    struct Entry {
        let name: String
        let method: UInt16
        let compressed: Int
        let size: Int
        let offset: Int
    }

    enum Failure: LocalizedError {
        case notZip, damaged(String)
        var errorDescription: String? {
            switch self {
            case .notZip: return "The file isn't an EPUB (it isn't a ZIP)."
            case .damaged(let n): return "Part of the book is damaged (\(n))."
            }
        }
    }

    private let bytes: [UInt8]
    let entries: [String: Entry]

    init(_ data: Data) throws {
        bytes = [UInt8](data)
        let n = bytes.count
        guard n >= 22 else { throw Failure.notZip }
        var end = -1
        var i = n - 22
        while i >= max(0, n - 65_557) {
            if Self.u32(bytes, i) == 0x0605_4b50 { end = i; break }
            i -= 1
        }
        guard end >= 0 else { throw Failure.notZip }
        let count = Int(Self.u16(bytes, end + 10))
        var p = Int(Self.u32(bytes, end + 16))
        var out: [String: Entry] = [:]
        for _ in 0..<count {
            guard p + 46 <= n, Self.u32(bytes, p) == 0x0201_4b50 else { break }
            let nameLength = Int(Self.u16(bytes, p + 28)), extra = Int(Self.u16(bytes, p + 30)), comment = Int(Self.u16(bytes, p + 32))
            guard p + 46 + nameLength <= n else { break }
            let name = String(decoding: bytes[(p + 46)..<(p + 46 + nameLength)], as: UTF8.self)
            out[name] = Entry(name: name, method: Self.u16(bytes, p + 10), compressed: Int(Self.u32(bytes, p + 20)),
                              size: Int(Self.u32(bytes, p + 24)), offset: Int(Self.u32(bytes, p + 42)))
            p += 46 + nameLength + extra + comment
        }
        entries = out
    }

    /// An entry's bytes, by its path in the book ("OEBPS/text/ch01.xhtml").
    func read(_ name: String) -> Data? {
        guard let e = entries[name] ?? entries.first(where: { $0.key.caseInsensitiveCompare(name) == .orderedSame })?.value else { return nil }
        let p = e.offset
        guard p + 30 <= bytes.count, Self.u32(bytes, p) == 0x0403_4b50 else { return nil }
        let start = p + 30 + Int(Self.u16(bytes, p + 26)) + Int(Self.u16(bytes, p + 28))
        guard start + e.compressed <= bytes.count else { return nil }
        let raw = bytes[start..<(start + e.compressed)]
        if e.method == 0 { return Data(raw) }
        guard e.method == 8, e.size > 0 else { return e.size == 0 ? Data() : nil }
        var out = [UInt8](repeating: 0, count: e.size)
        let written = raw.withUnsafeBufferPointer { src in
            out.withUnsafeMutableBufferPointer { dst in
                compression_decode_buffer(dst.baseAddress!, e.size, src.baseAddress!, src.count, nil, COMPRESSION_ZLIB)   // raw DEFLATE
            }
        }
        return written > 0 ? Data(out.prefix(written)) : nil
    }

    private static func u16(_ b: [UInt8], _ i: Int) -> UInt16 { UInt16(b[i]) | UInt16(b[i + 1]) << 8 }
    private static func u32(_ b: [UInt8], _ i: Int) -> UInt32 {
        UInt32(b[i]) | UInt32(b[i + 1]) << 8 | UInt32(b[i + 2]) << 16 | UInt32(b[i + 3]) << 24
    }
}
