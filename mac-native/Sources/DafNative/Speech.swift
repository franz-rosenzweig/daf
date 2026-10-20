import AVFoundation
import MediaPlayer
import SwiftUI

/// Read aloud, as the page does it: each paragraph's speech from Daf (/api/tts?doc=&b=, Kokoro in
/// the chosen voice), one after another, the next one fetched while this one plays; the paragraph
/// marked in the reader and kept in view; the play/pause and skip keys on the keyboard work; and
/// the listening counts as reading, in beats of 15 seconds.
@MainActor
@Observable
final class Speaker {
    static let shared = Speaker()

    private(set) var docID: String?
    private(set) var title = ""
    /// The doc's blocks that are read (not pictures or page marks), by their index.
    private(set) var blocks: [Int] = []
    private(set) var index = 0
    private(set) var playing = false
    /// Daf is still making this paragraph's speech.
    private(set) var waiting = false
    var rate: Float = (UserDefaults.standard.object(forKey: "ttsRate") as? NSNumber)?.floatValue ?? 1 {
        didSet { UserDefaults.standard.set(rate, forKey: "ttsRate"); player?.rate = rate }
    }
    /// The self-test listens with the sound off (the app's own player, never the Mac's volume).
    @ObservationIgnored var volume: Float = 1
    /// For the self-test: paragraphs that started.
    @ObservationIgnored private(set) var started = 0

    var on: Bool { docID != nil }

    @ObservationIgnored private var player: AVAudioPlayer?
    @ObservationIgnored private let ended = Ended()
    @ObservationIgnored private var cache: [Int: Data] = [:]
    @ObservationIgnored private var fetching: [Int: Task<Data?, Never>] = [:]
    @ObservationIgnored private weak var reader: ReaderModel?
    @ObservationIgnored private var beatTimer: Timer?
    @ObservationIgnored private var remoteReady = false
    @ObservationIgnored private var failures = 0

    private init() {
        ended.done = { [weak self] p in MainActor.assumeIsolated { if p === self?.player { self?.skip(1) } } }
    }

    /// Starts reading an article: from a paragraph, or from the one at the top of the window.
    func start(_ r: ReaderModel, at block: Int? = nil) {
        guard let d = r.doc else { return }
        stop()
        reader = r
        docID = r.id
        title = r.title
        blocks = d.list("blocks").enumerated().compactMap { i, any in
            guard let b = J(any) else { return nil }
            let t = b.s("t") ?? "p"
            return t != "img" && t != "pg" && !(b.s("x") ?? "").trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ? i : nil
        }
        let from = block ?? r.firstVisibleBlock() ?? 0
        index = blocks.firstIndex { $0 >= from } ?? 0
        remote()
        startBeats()
        playing = true
        Task { await playCurrent() }
    }

    /// The reader for the article again (a new window, the same article opened again).
    func attach(_ r: ReaderModel) {
        guard r.id == docID else { return }
        reader = r
        mark()
    }

    func toggle() { playing ? pause() : resume() }

    func pause() {
        playing = false
        player?.pause()
        nowPlaying()
    }

    func resume() {
        guard on else { return }
        playing = true
        if let p = player { p.play(); nowPlaying() } else { Task { await playCurrent() } }
    }

    /// The next paragraph (1) or the one before (-1).
    func skip(_ by: Int) {
        guard on else { return }
        player?.stop()
        player = nil
        index = max(0, index + by)
        if index >= blocks.count { finished(); return }
        if playing { Task { await playCurrent() } } else { mark() }
    }

    func stop() {
        player?.stop()
        player = nil
        playing = false
        waiting = false
        reader?.markSpeaking(nil)
        reader = nil
        docID = nil
        blocks = []
        cache = [:]
        fetching.values.forEach { $0.cancel() }
        fetching = [:]
        beatTimer?.invalidate()
        beatTimer = nil
        MPNowPlayingInfoCenter.default().nowPlayingInfo = nil
        MPNowPlayingInfoCenter.default().playbackState = .stopped
    }

    private func finished() {
        stop()
        AppModel.shared.say("Read to the end")
    }

    private func playCurrent() async {
        guard let doc = docID, blocks.indices.contains(index) else { return finished() }
        let b = blocks[index]
        waiting = true
        mark()
        let data = await speech(b)
        guard docID == doc, blocks.indices.contains(index), blocks[index] == b, playing, player == nil else { return }  // moved on meanwhile
        waiting = false
        guard let data, let p = try? AVAudioPlayer(data: data) else {
            failures += 1
            if failures >= 2 { stop(); AppModel.shared.say("Kokoro isn't answering, so reading aloud stopped"); return }
            AppModel.shared.say("Kokoro didn't answer for that paragraph; skipping")
            return skip(1)
        }
        failures = 0
        p.delegate = ended
        p.enableRate = true
        p.rate = rate
        p.volume = volume
        p.prepareToPlay()
        player = p
        p.play()
        started += 1
        nowPlaying()
        for k in 1...2 where blocks.indices.contains(index + k) { _ = fetch(blocks[index + k]) }
    }

    private func speech(_ b: Int) async -> Data? {
        if let d = cache[b] { return d }
        return await fetch(b).value
    }

    @discardableResult
    private func fetch(_ b: Int) -> Task<Data?, Never> {
        if let t = fetching[b] { return t }
        let doc = docID ?? ""
        let t = Task { [weak self] () -> Data? in
            let d = try? await API.shared.data("/api/tts?doc=\(API.enc(doc))&b=\(b)")
            if let self, self.docID == doc {
                self.fetching[b] = nil
                if let d { self.cache[b] = d }
                if self.cache.count > 8 { for k in self.cache.keys where abs(k - b) > 6 { self.cache[k] = nil } }
            }
            return d
        }
        fetching[b] = t
        return t
    }

    private func mark() {
        reader?.markSpeaking(blocks.indices.contains(index) ? blocks[index] : nil, follow: playing)
    }

    // MARK: the reading time

    private func startBeats() {
        beatTimer?.invalidate()
        beatTimer = Timer.scheduledTimer(withTimeInterval: 15, repeats: true) { [weak self] _ in
            MainActor.assumeIsolated {
                guard let self, self.playing, !self.waiting, let id = self.docID else { return }
                Task { try? await API.shared.send("POST", "/api/read/beat", ["doc_id": id, "seconds": 15, "at": Int(Date().timeIntervalSince1970)]) }
            }
        }
    }

    // MARK: the keyboard's play/pause and skip keys, and Now Playing

    private func remote() {
        guard !remoteReady else { return }
        remoteReady = true
        let c = MPRemoteCommandCenter.shared()
        func on(_ cmd: MPRemoteCommand, _ f: @escaping @MainActor (Speaker) -> Void) {
            cmd.isEnabled = true
            cmd.addTarget { [weak self] _ in
                guard let self else { return .commandFailed }
                MainActor.assumeIsolated { f(self) }
                return .success
            }
        }
        on(c.togglePlayPauseCommand) { $0.toggle() }
        on(c.playCommand) { $0.resume() }
        on(c.pauseCommand) { $0.pause() }
        on(c.nextTrackCommand) { $0.skip(1) }
        on(c.previousTrackCommand) { $0.skip(-1) }
    }

    private func nowPlaying() {
        MPNowPlayingInfoCenter.default().nowPlayingInfo = [
            MPMediaItemPropertyTitle: title,
            MPMediaItemPropertyArtist: "Paragraph \(min(index + 1, blocks.count)) of \(blocks.count)",
            MPNowPlayingInfoPropertyPlaybackRate: playing ? Double(rate) : 0,
        ]
        MPNowPlayingInfoCenter.default().playbackState = playing ? .playing : .paused
    }

    /// AVAudioPlayer's delegate, kept apart from the observable model.
    private final class Ended: NSObject, AVAudioPlayerDelegate {
        var done: ((AVAudioPlayer) -> Void)?
        func audioPlayerDidFinishPlaying(_ p: AVAudioPlayer, successfully flag: Bool) { done?(p) }
    }
}

/// The player at the bottom of the window while an article is read aloud.
struct SpeakerBar: View {
    @Environment(AppModel.self) private var model
    private let s = Speaker.shared

    var body: some View {
        HStack(spacing: 14) {
            VStack(alignment: .leading, spacing: 2) {
                Text(s.title).font(.callout.weight(.semibold)).lineLimit(1)
                Text(s.waiting ? "Getting the paragraph ready…" : "Paragraph \(min(s.index + 1, s.blocks.count)) of \(s.blocks.count)")
                    .font(.caption).foregroundStyle(.secondary).monospacedDigit()
            }
            .frame(maxWidth: 240, alignment: .leading)
            Button { s.skip(-1) } label: { Image(systemName: "backward.fill") }.help("The paragraph before")
            Button { s.toggle() } label: { Image(systemName: s.playing ? "pause.fill" : "play.fill").font(.title3).frame(width: 22) }
                .help(s.playing ? "Pause" : "Listen")
            Button { s.skip(1) } label: { Image(systemName: "forward.fill") }.help("The next paragraph")
            Menu {
                ForEach([0.75, 1, 1.25, 1.5, 1.75, 2], id: \.self) { r in
                    Button { s.rate = Float(r) } label: {
                        if abs(Double(s.rate) - r) < 0.01 { Label(speed(r), systemImage: "checkmark") } else { Text(speed(r)) }
                    }
                }
            } label: { Text(speed(Double(s.rate))).monospacedDigit() }
            .menuStyle(.borderlessButton)
            .fixedSize()
            Button { s.stop() } label: { Image(systemName: "xmark") }.help("Stop reading aloud")
        }
        .buttonStyle(.borderless)
        .padding(.horizontal, 18)
        .padding(.vertical, 10)
        .glassEffect(.regular, in: Capsule())
    }

    private func speed(_ r: Double) -> String { r == 1 ? "1×" : String(format: "%g×", r) }
}
