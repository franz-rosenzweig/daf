import AVFoundation
import SwiftUI

// Sound, as the page has it (web/sound.js, daf/soundscape.py): a quiet bed of recorded sound under a
// book that follows the scene you're in. Two ways to have it:
// - in the book reader: each time the pages settle, Daf is told the place and answers with the scene;
// - beside the Kindle: Today's row plays the scene of the page the Kindle is on, asking with a request
//   that waits for the next page, so it goes on with the window in the background.
// The sounds are seamless loops with PAD seconds of their own end before them and of their start after
// them; each layer starts somewhere in its loop and fades in and out over FADE seconds.

@MainActor
@Observable
final class SoundBed {
    static let shared = SoundBed()
    static let pad = 0.5, fade = 4.0

    enum Mode { case book, kindle }
    private(set) var mode: Mode?
    /// Daf's last answer: {state: ready | reading | failed | none, scene, sounds, why, title, seen}.
    private(set) var answer: J?
    /// The Kindle's book, before its Sound is on (Today's row).
    var kindleSeen: J?
    var volume = UserDefaults.standard.object(forKey: "soundVol") as? Double ?? 0.6 {
        didSet { UserDefaults.standard.set(volume, forKey: "soundVol"); engine.mainMixerNode.outputVolume = Float(volume) }
    }
    /// On for books on this Mac until it's turned off.
    var on: Bool { UserDefaults.standard.bool(forKey: "soundOn") }

    @ObservationIgnored private weak var book: BookModel?
    @ObservationIgnored private var asking: Task<Void, Never>?
    @ObservationIgnored private var listening: Task<Void, Never>?

    // MARK: in the book reader

    /// A book opened: with Sound on, its scene plays from the first page it shows.
    func open(_ b: BookModel) {
        if let old = book, old !== b { closed(old) }
        book = b
        answer = nil
        if on && mode != .kindle { mode = .book }
        moved(b)
    }

    /// The pages settled: a moment later, ask for the scene there.
    func moved(_ b: BookModel) {
        guard b === book, mode == .book else { return }
        ask(after: 1.2)
    }

    func closed(_ b: BookModel) {
        guard b === book else { return }
        asking?.cancel()
        if mode == .book { hush(); mode = nil }
        book = nil
        answer = nil
    }

    /// Turn on Sound / Turn off Sound, in the reader.
    func toggleBook() {
        if mode == .book {
            UserDefaults.standard.set(false, forKey: "soundOn")
            asking?.cancel()
            hush(); mode = nil; answer = nil
            return
        }
        if mode == .kindle { stopKindle() }
        UserDefaults.standard.set(true, forKey: "soundOn")
        mode = .book
        ask(after: 0)
    }

    private func ask(after delay: Double) {
        asking?.cancel()
        asking = Task { [weak self] in
            try? await Task.sleep(nanoseconds: UInt64(delay * 1e9))
            while !Task.isCancelled, let self, self.mode == .book, let b = self.book {
                guard let place = b.place() else { return }
                let r: J?
                do { r = J(try await API.shared.send("POST", "/api/ebooks/\(API.enc(b.id))/sound", place)) }
                catch { try? await Task.sleep(nanoseconds: 20_000_000_000); continue }
                guard !Task.isCancelled, self.book === b, self.mode == .book, let r else { return }
                self.got(r)
                guard r.s("state") == "reading" else { return }
                try? await Task.sleep(nanoseconds: 5_000_000_000)
            }
        }
    }

    // MARK: beside the Kindle

    func toggleKindle() { mode == .kindle ? stopKindle() : startKindle() }

    private func startKindle() {
        if mode == .book { asking?.cancel() }
        mode = .kindle
        listening?.cancel()
        listening = Task { [weak self] in
            var after = 0.0
            while !Task.isCancelled {
                guard let self, self.mode == .kindle else { return }
                guard let r = await Self.kindle(after: after) else {
                    try? await Task.sleep(nanoseconds: 15_000_000_000); continue
                }
                guard !Task.isCancelled, self.mode == .kindle else { return }
                self.got(r)
                if r.s("state") == "reading" { after = 0; try? await Task.sleep(nanoseconds: 5_000_000_000) }
                else { after = r.d("seen") ?? Date().timeIntervalSince1970 }
            }
        }
    }

    private func stopKindle() {
        listening?.cancel()
        mode = nil
        hush()
        answer = nil
    }

    /// The Kindle's scene: with `after`, Daf waits for a page newer than that. Asked straight, not
    /// through API.send, so the waiting answers aren't kept on the Mac one by one.
    static func kindle(after: Double) async -> J? {
        var r = URLRequest(url: API.shared.url("/api/sound/kindle" + (after > 0 ? "?after=\(after)&wait=20" : "")))
        r.cachePolicy = .reloadIgnoringLocalCacheData
        r.timeoutInterval = 45
        guard let (data, res) = try? await API.shared.session.data(for: r), (res as? HTTPURLResponse)?.statusCode == 200 else { return nil }
        return J(try? JSONSerialization.jsonObject(with: data))
    }

    /// Today asks whether the Kindle has sent a page in the last half hour.
    func lookAtKindle() async {
        guard mode != .kindle, let r = await Self.kindle(after: 0) else { return }
        kindleSeen = r
    }

    private func got(_ r: J) {
        answer = r
        switch r.s("state") {
        case "ready": mix(r.o("sounds")?.raw.compactMapValues { ($0 as? NSNumber)?.doubleValue } ?? [:])
        case "none", "failed": hush()
        default: break
        }
    }

    // MARK: the mixer

    private struct Layer { let node: AVAudioPlayerNode; var level: Float; var target: Float; var step: Float }
    @ObservationIgnored private let engine = AVAudioEngine()
    @ObservationIgnored private var layers: [String: Layer] = [:]
    @ObservationIgnored private var going: [String: Layer] = [:]
    @ObservationIgnored private var loops: [String: AVAudioPCMBuffer] = [:]
    @ObservationIgnored private var want: [String: Double] = [:]
    @ObservationIgnored private var ramp: Timer?

    /// sounds: {id: level}. What's playing and not wanted fades out; what's wanted fades in or to its level.
    private func mix(_ sounds: [String: Double]) {
        want = sounds
        for (id, l) in layers where sounds[id] == nil { fadeOut(id, l) }
        for (id, level) in sounds {
            if var l = layers[id] {
                l.target = Float(level); l.step = abs(l.target - l.level) / Float(Self.fade * 20)
                layers[id] = l
                continue
            }
            Task { [weak self] in
                guard let buf = await self?.loop(id), let self, self.want[id] != nil, self.layers[id] == nil else { return }
                self.start(id, buf, level: Float(self.want[id] ?? level))
            }
        }
        tick()
    }

    private func hush() { mix([:]) }

    /// For the self-test: the layers sounding, and a mix asked for straight.
    var sounding: Int { layers.count }
    var fading: Int { going.count }
    func testMix(_ sounds: [String: Double]) { mix(sounds) }

    private func fadeOut(_ id: String, _ l: Layer) {
        layers[id] = nil
        var l = l
        l.target = 0; l.step = max(0.001, l.level / Float(Self.fade * 20))
        going[id + "#" + UUID().uuidString] = l
    }

    private func start(_ id: String, _ loop: AVAudioPCMBuffer, level: Float) {
        let node = AVAudioPlayerNode()
        engine.attach(node)
        engine.connect(node, to: engine.mainMixerNode, format: loop.format)
        engine.mainMixerNode.outputVolume = Float(volume)
        if !engine.isRunning { try? engine.start() }
        // somewhere in the loop first, so two of a kind never line up; then the loop, over and over
        let n = loop.frameLength, from = AVAudioFrameCount(Double.random(in: 0..<0.9) * Double(n))
        if from > 0, let tail = Self.slice(loop, from: from, count: n - from) { node.scheduleBuffer(tail) }
        node.scheduleBuffer(loop, at: nil, options: .loops)
        node.volume = 0
        node.play()
        layers[id] = Layer(node: node, level: 0, target: level, step: level / Float(Self.fade * 20))
        tick()
    }

    /// The volumes a twentieth of a second on, until each is where it's going.
    private func tick() {
        guard ramp == nil else { return }
        ramp = Timer.scheduledTimer(withTimeInterval: 0.05, repeats: true) { _ in
            MainActor.assumeIsolated { SoundBed.shared.step() }
        }
    }

    private func step() {
        func move(_ l: inout Layer) -> Bool {
            if l.level < l.target { l.level = min(l.target, l.level + max(l.step, 0.001)) }
            else if l.level > l.target { l.level = max(l.target, l.level - max(l.step, 0.001)) }
            l.node.volume = l.level
            return l.level == l.target
        }
        var still = false
        for id in Array(layers.keys) { if var l = layers[id] { if !move(&l) { still = true }; layers[id] = l } }
        for id in Array(going.keys) {
            guard var l = going[id] else { continue }
            if move(&l) {
                l.node.stop(); engine.detach(l.node); going[id] = nil
            } else { going[id] = l; still = true }
        }
        if !still {
            ramp?.invalidate(); ramp = nil
            if layers.isEmpty && going.isEmpty && engine.isRunning { engine.stop() }
        }
    }

    /// A sound's loop, PAD to PAD + its whole seconds, from the file kept on this Mac.
    private func loop(_ id: String) async -> AVAudioPCMBuffer? {
        if let b = loops[id] { return b }
        let file = Store.folder("Sounds").appendingPathComponent(id + ".mp3")
        if !FileManager.default.fileExists(atPath: file.path) {
            guard let data = try? await API.shared.data("/api/sounds/\(API.enc(id)).mp3") else { return nil }
            try? data.write(to: file, options: .atomic)
        }
        guard let f = try? AVAudioFile(forReading: file),
              let all = AVAudioPCMBuffer(pcmFormat: f.processingFormat, frameCapacity: AVAudioFrameCount(f.length)),
              (try? f.read(into: all)) != nil else { try? FileManager.default.removeItem(at: file); return nil }
        let rate = f.processingFormat.sampleRate, seconds = Double(all.frameLength) / rate
        let whole = max(1, (seconds - 2 * Self.pad).rounded())
        let from = AVAudioFrameCount(Self.pad * rate), count = min(AVAudioFrameCount(whole * rate), all.frameLength - from)
        let b = Self.slice(all, from: from, count: count)
        loops[id] = b
        return b
    }

    private static func slice(_ b: AVAudioPCMBuffer, from: AVAudioFrameCount, count: AVAudioFrameCount) -> AVAudioPCMBuffer? {
        guard count > 0, from + count <= b.frameLength,
              let out = AVAudioPCMBuffer(pcmFormat: b.format, frameCapacity: count),
              let src = b.floatChannelData, let dst = out.floatChannelData else { return nil }
        for ch in 0..<Int(b.format.channelCount) {
            dst[ch].update(from: src[ch].advanced(by: Int(from)), count: Int(count))
        }
        out.frameLength = count
        return out
    }
}

/// The reader's Sound button: the scene, the volume, and Turn On / Turn Off.
struct SoundMenu: View {
    @State private var bed = SoundBed.shared

    var body: some View {
        let on = bed.mode == .book, r = bed.answer
        VStack(alignment: .leading, spacing: 12) {
            if on {
                let what = r?.s("state") == "ready" ? r?.s("scene") : r?.s("state") == "reading" ? "…" : r?.s("why")
                if let what, !what.isEmpty { Text(what).font(.headline) }
                LabeledContent("Volume") { Slider(value: $bed.volume, in: 0...1).frame(width: 160) }
                Divider()
            }
            Button(on ? "Turn Off Sound" : "Turn On Sound") { bed.toggleBook() }
        }
        .padding(14)
        .frame(minWidth: 220, alignment: .leading)
    }
}

/// Today's Sound row: the Kindle's book when it has sent a page in the last half hour, its scene and
/// the volume while it plays, and Sound / Stop.
struct KindleSoundRow: View {
    @State private var bed = SoundBed.shared

    var body: some View {
        Group {
            let on = bed.mode == .kindle, r = on ? bed.answer ?? bed.kindleSeen : bed.kindleSeen
            if on || fresh(r) {
                Notice(icon: "waveform") {
                    HStack(spacing: 6) {
                        Text(Self.short(r?.s("title") ?? "Kindle")).bold()
                        if on, let scene = r?.s("scene"), r?.s("state") == "ready" { Text("· " + scene).foregroundStyle(.secondary) }
                        else if on, r?.s("state") == "reading" { Text("· …").foregroundStyle(.secondary) }
                    }
                } actions: {
                    if on { Slider(value: $bed.volume, in: 0...1).frame(width: 120).accessibilityLabel("Volume") }
                    if on { Button("Stop") { bed.toggleKindle() } }
                    else { Button("Sound") { bed.toggleKindle() }.buttonStyle(.borderedProminent) }
                }
            }
        }
        .task { await bed.lookAtKindle() }
    }

    private func fresh(_ r: J?) -> Bool { (r?.d("seen") ?? 0) > Date().timeIntervalSince1970 - 1800 }
    static func short(_ t: String) -> String { String(t.split(separator: ": ", maxSplits: 1).first ?? Substring(t)) }
}
