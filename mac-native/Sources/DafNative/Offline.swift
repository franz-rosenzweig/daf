import CryptoKit
import Foundation
import Observation

/// Where the app keeps things on this Mac: Application Support/<its own id>/, so the test build
/// never touches what Daf keeps.
enum Store {
    static let dir: URL = {
        let u = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
            .appendingPathComponent(Bundle.main.bundleIdentifier ?? "xyz.tiresia.daf", isDirectory: true)
        try? FileManager.default.createDirectory(at: u, withIntermediateDirectories: true)
        return u
    }()

    static func folder(_ name: String) -> URL {
        let u = dir.appendingPathComponent(name, isDirectory: true)
        try? FileManager.default.createDirectory(at: u, withIntermediateDirectories: true)
        return u
    }
}

/// Daf's answers as they last came, so what I've seen opens again with no connection: lists,
/// articles, a book's details, Today. A month unread, an answer goes.
enum Cache {
    static let folder = Store.folder("Answers")

    static func file(_ path: String) -> URL {
        folder.appendingPathComponent(SHA256.hash(data: Data(path.utf8)).map { String(format: "%02x", $0) }.joined() + ".json")
    }
    static func put(_ path: String, _ data: Data) { try? data.write(to: file(path), options: .atomic) }
    static func get(_ path: String) -> Data? {
        let f = file(path)
        guard let d = try? Data(contentsOf: f) else { return nil }
        try? FileManager.default.setAttributes([.modificationDate: Date()], ofItemAtPath: f.path)
        return d
    }
    static func has(_ path: String) -> Bool { FileManager.default.fileExists(atPath: file(path).path) }

    static func prune() {
        let old = Date().addingTimeInterval(-30 * 86400)
        for f in (try? FileManager.default.contentsOfDirectory(at: folder, includingPropertiesForKeys: [.contentModificationDateKey])) ?? [] {
            if let d = try? f.resourceValues(forKeys: [.contentModificationDateKey]).contentModificationDate, d < old { try? FileManager.default.removeItem(at: f) }
        }
    }
}

/// Whether Daf answers. When it stops, the app shows what it kept and keeps my changes; every
/// twenty seconds it asks again, and when Daf is back the kept changes go.
@MainActor
@Observable
final class Connection {
    static let shared = Connection()
    private(set) var offline = false
    /// The self-test's way to be without a connection.
    @ObservationIgnored var forced = false
    @ObservationIgnored private var timer: Timer?

    func lost() {
        guard !offline else { return }
        offline = true
        timer?.invalidate()
        timer = Timer.scheduledTimer(withTimeInterval: 20, repeats: true) { _ in
            MainActor.assumeIsolated { Task { _ = try? await API.shared.get("/api/health") } }
        }
    }

    func reached() {
        guard offline else { return }
        offline = false
        timer?.invalidate()
        timer = nil
        Task { await Outbox.shared.flush() }
    }

    /// A failure that means no connection, not an answer.
    nonisolated static func isOffline(_ e: Error) -> Bool {
        guard let u = e as? URLError else { return false }
        return [.notConnectedToInternet, .cannotConnectToHost, .cannotFindHost, .timedOut, .networkConnectionLost,
                .dnsLookupFailed, .dataNotAllowed, .internationalRoamingOff, .secureConnectionFailed].contains(u.code)
    }
}

/// Changes made with no connection, kept in order on this Mac and sent when Daf answers again.
/// Each keeps the X-Daf-Op it was made with, so one that already reached Daf is never done twice.
@MainActor
@Observable
final class Outbox {
    static let shared = Outbox()

    struct Op: Codable {
        let id: String
        let method: String
        let path: String
        let body: Data?
    }
    private(set) var ops: [Op] = []
    @ObservationIgnored private var flushing = false
    @ObservationIgnored private let file = Store.dir.appendingPathComponent("outbox.json")

    init() {
        if let d = try? Data(contentsOf: file), let o = try? JSONDecoder().decode([Op].self, from: d) { ops = o }
    }

    static func newID() -> String { UUID().uuidString.replacingOccurrences(of: "-", with: "").lowercased() }

    /// What can wait: everything but what needs Daf's answer then and there.
    static func canWait(_ method: String, _ path: String) -> Bool {
        let now = ["/api/login", "/api/sync", "/api/feed/refresh", "/api/add/feed", "/api/kindle/send", "/api/devices", "/api/tts"]
        return method != "GET" && !now.contains { path.hasPrefix($0) } && !path.hasSuffix("/ask")
    }

    func add(_ op: Op) {
        if ops.isEmpty { AppModel.shared.say("Kept on this Mac until Daf answers") }
        ops.append(op)
        save()
    }

    func flush() async {
        guard !flushing, !ops.isEmpty else { return }
        flushing = true
        defer { flushing = false }
        while let op = ops.first {
            let body = op.body.flatMap { try? JSONSerialization.jsonObject(with: $0) as? [String: Any] }
            do {
                try await API.shared.send(op.method, op.path, body, op: op.id)
            } catch let e as APIError where e.status >= 400 && e.status < 500 && e.status != 401 {
                // Daf said no (a doc that's gone, say): it won't say yes later
            } catch { return }
            ops.removeFirst()
            save()
        }
        AppModel.shared.reload()
    }

    private func save() {
        if let d = try? JSONEncoder().encode(ops) { try? d.write(to: file, options: .atomic) }
    }
}

extension AppModel {
    /// The Inbox's and Later's articles kept on this Mac, a few at a time, as the page keeps them
    /// for the phone (?prefetch=1 doesn't mark them opened).
    func keepForLater(_ items: [Item]) {
        guard UserDefaults.standard.object(forKey: "keepOffline") as? Bool ?? true, !Connection.shared.offline else { return }
        let todo = items.filter { ["article", "tweet", "email"].contains($0.kind) && !Cache.has("/api/docs/" + API.enc($0.id)) }.prefix(30)
        guard !todo.isEmpty else { return }
        Task {
            for item in todo {
                guard !Connection.shared.offline else { return }
                await API.shared.keep("/api/docs/\(API.enc(item.id))?prefetch=1", as: "/api/docs/" + API.enc(item.id))
                try? await Task.sleep(nanoseconds: 300_000_000)
            }
        }
    }

    /// The nightstand's books kept on this Mac, so they open on a plane.
    func keepNightstand() {
        guard UserDefaults.standard.object(forKey: "keepOffline") as? Bool ?? true, !Connection.shared.offline else { return }
        let ids = (today?.a("nightstand") ?? []).compactMap { $0.s("id") }
        Task {
            for id in ids {
                guard let d = try? await API.shared.json("/api/ebooks/" + API.enc(id)), ["EPUB", "KEPUB"].contains((d.s("format") ?? "").uppercased()),
                      (d.i("size") ?? 0) < 80_000_000 else { continue }
                _ = try? await BookModel.file(for: id, size: d.i("size"))
            }
        }
    }
}
