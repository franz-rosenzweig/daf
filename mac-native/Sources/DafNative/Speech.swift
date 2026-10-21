import AVFoundation
import MediaPlayer
import SwiftUI

/// Something that can be read aloud a paragraph at a time: an article (ReaderModel) or a book
/// (BookModel). Paragraphs are numbers of its own choosing, in reading order.
@MainActor
protocol Listenable: AnyObject {
    /// What's being read ("fr:…" for an article, "book:cal:45" for a book).
    var listenKey: String { get }
    var listenTitle: String { get }
    func paragraphs() -> [Int]
    /// The paragraph a place is in, or the one at the top of the window.
    func paragraph(at place: Int?) -> Int?
    func speech(_ p: Int) async -> Data?
    func mark(_ p: Int?, follow: Bool)
    /// Fifteen seconds of listening, counted as reading.
    func listened()
    /// At the end: on to what comes next (a book's next chapter). False when there's nothing more.
    func advance() -> Bool
}

/// Read aloud, as the page does it: each paragraph's speech from Daf (Kokoro, in the voice in
/// Settings), one after another, the next ones fetched while this one plays; the paragraph marked
/// and kept in view; the keyboard's play/pause and skip keys work; the listening counts as reading.
@MainActor
@Observable
final class Speaker {
    static let shared = Speaker()

    private(set) var key: String?
    private(set) var title = ""
    private(set) var paragraphs: [Int] = []
    private(set) var index = 0
    private(set) var playing = false
    /// Daf is still making this paragraph's speech.
    private(set) var waiting = false
    var rate: Float = (UserDefaults.standard.object(forKey: "ttsRate") as? NSNumber)?.floatValue ?? 1 {
        didSet { UserDefaults.standard.set(rate, forKey: "ttsRate"); player?.rate = rate }
    }
    /// The sleep timer: reading stops at this time.
    private(set) var sleepAt: Date?
    /// The voices Daf's Kokoro has, and the one in Settings.
    private(set) var voices: [String] = []
    private(set) var voice = ""
    /// The self-test listens with the sound off (the app's own player, never the Mac's volume).
    @ObservationIgnored var volume: Float = 1
    /// For the self-test: paragraphs that started.
    @ObservationIgnored private(set) var started = 0

    var on: Bool { key != nil }
    /// Kept for the reader that shows the article: the doc's id (or nil for a book).
    var docID: String? { key.flatMap { $0.hasPrefix("book:") ? nil : $0 } }

    @ObservationIgnored private var player: AVAudioPlayer?
    @ObservationIgnored private let ended = Ended()
    @ObservationIgnored private var cache: [Int: Data] = [:]
    @ObservationIgnored private var fetching: [Int: Task<Data?, Never>] = [:]
    @ObservationIgnored private weak var source: Listenable?
    @ObservationIgnored private var beatTimer: Timer?
    @ObservationIgnored private var remoteReady = false
    @ObservationIgnored private var failures = 0
    @ObservationIgnored private var generation = 0

    private init() {
        ended.done = { [weak self] p in MainActor.assumeIsolated { if p === self?.player { self?.skip(1) } } }
    }

    /// Starts reading: from a place in it, or from the top of the window.
    func start(_ s: Listenable, at place: Int? = nil) {
        stop()
        source = s
        key = s.listenKey
        title = s.listenTitle
        load(from: s.paragraph(at: place))
        remote()
        startBeats()
        playing = true
        Task { await playCurrent() }
    }

    private func load(from p: Int?) {
        guard let s = source else { return }
        paragraphs = s.paragraphs()
        cache = [:]
        fetching.values.forEach { $0.cancel() }
        fetching = [:]
        generation += 1
        index = p.flatMap { p in paragraphs.firstIndex { $0 >= p } } ?? 0
    }

    /// The reader for the same thing again (a new window): marks and follows from there.
    func attach(_ s: Listenable) {
        guard s.listenKey == key else { return }
        source = s
        mark()
    }

    func toggle() { playing ? pause() : resume() }

    /// Stops reading after so many minutes (nil: never).
    func sleep(after minutes: Int?) {
        sleepAt = minutes.map { Date().addingTimeInterval(TimeInterval($0 * 60)) }
        AppModel.shared.say(minutes.map { "Reading stops in \($0) minutes" } ?? "No sleep timer")
    }

    func loadVoices() async {
        guard voices.isEmpty else { return }
        voice = (try? await API.shared.json("/api/settings"))?.s("tts_voice") ?? "af_heart"
        voices = ((try? await API.shared.json("/api/voices"))?.strings("voices") ?? []).filter { $0.range(of: "^[ab][fm]_[a-z]+$", options: .regularExpression) != nil }
            .sorted { (PrefsView.kinds.firstIndex(of: String($0.prefix(2))) ?? 9, $0) < (PrefsView.kinds.firstIndex(of: String($1.prefix(2))) ?? 9, $1) }
    }

    /// Another voice: the paragraph starts again in it.
    func use(voice v: String) async {
        try? await API.shared.send("PUT", "/api/settings", ["tts_voice": v])
        voice = v
        cache = [:]
        fetching.values.forEach { $0.cancel() }
        fetching = [:]
        generation += 1
        player?.stop()
        player = nil
        if playing { Task { await playCurrent() } }
    }

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
        if index >= paragraphs.count {
            guard let s = source, s.advance() else { return finished() }
            load(from: nil)                       // a book's next chapter
        }
        if playing { Task { await playCurrent() } } else { mark() }
    }

    func stop() {
        player?.stop()
        player = nil
        playing = false
        waiting = false
        source?.mark(nil, follow: false)
        source = nil
        key = nil
        paragraphs = []
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
        guard on, paragraphs.indices.contains(index) else { return finished() }
        let p = paragraphs[index], gen = generation
        waiting = true
        mark()
        let data = await speech(p)
        guard gen == generation, paragraphs.indices.contains(index), paragraphs[index] == p, playing, player == nil else { return }  // moved on meanwhile
        waiting = false
        guard let data, let a = try? AVAudioPlayer(data: data) else {
            failures += 1
            if failures >= 2 { stop(); AppModel.shared.say("Kokoro isn't answering, so reading aloud stopped"); return }
            AppModel.shared.say("Kokoro didn't answer for that paragraph; skipping")
            return skip(1)
        }
        failures = 0
        a.delegate = ended
        a.enableRate = true
        a.rate = rate
        a.volume = volume
        a.prepareToPlay()
        player = a
        a.play()
        started += 1
        nowPlaying()
        for k in 1...2 where paragraphs.indices.contains(index + k) { _ = fetch(paragraphs[index + k]) }
    }

    private func speech(_ p: Int) async -> Data? {
        if let d = cache[p] { return d }
        return await fetch(p).value
    }

    @discardableResult
    private func fetch(_ p: Int) -> Task<Data?, Never> {
        if let t = fetching[p] { return t }
        let gen = generation
        let t = Task { [weak self] () -> Data? in
            guard let s = self?.source else { return nil }
            let d = await s.speech(p)
            if let self, self.generation == gen {
                self.fetching[p] = nil
                if let d { self.cache[p] = d }
                if self.cache.count > 8 { for k in self.cache.keys where abs(k - p) > 20_000 || self.cache.count > 12 { self.cache[k] = nil; break } }
            }
            return d
        }
        fetching[p] = t
        return t
    }

    private func mark() {
        source?.mark(paragraphs.indices.contains(index) ? paragraphs[index] : nil, follow: playing)
    }

    // MARK: the reading time

    private func startBeats() {
        beatTimer?.invalidate()
        beatTimer = Timer.scheduledTimer(withTimeInterval: 15, repeats: true) { [weak self] _ in
            MainActor.assumeIsolated {
                guard let self else { return }
                if let at = self.sleepAt, Date() >= at { self.sleepAt = nil; self.pause(); AppModel.shared.say("Paused by the sleep timer"); return }
                guard self.playing, !self.waiting else { return }
                self.source?.listened()
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
            MPMediaItemPropertyArtist: "Paragraph \(min(index + 1, paragraphs.count)) of \(paragraphs.count)",
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

// MARK: an article read aloud

extension ReaderModel: Listenable {
    var listenKey: String { id }
    var listenTitle: String { title }

    func paragraphs() -> [Int] {
        (doc?.list("blocks") ?? []).enumerated().compactMap { i, any in
            guard let b = J(any) else { return nil }
            let t = b.s("t") ?? "p"
            return t != "img" && t != "pg" && !(b.s("x") ?? "").trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ? i : nil
        }
    }

    func paragraph(at place: Int?) -> Int? { place.flatMap { block(at: $0) } ?? firstVisibleBlock() }

    func speech(_ p: Int) async -> Data? { try? await API.shared.data("/api/tts?doc=\(API.enc(id))&b=\(p)") }

    func mark(_ p: Int?, follow: Bool) { markSpeaking(p, follow: follow) }

    func listened() { beat() }

    func advance() -> Bool { false }
}

/// The player at the bottom of a window while something is read aloud.
struct SpeakerBar: View {
    private let s = Speaker.shared

    var body: some View {
        HStack(spacing: 14) {
            VStack(alignment: .leading, spacing: 2) {
                Text(s.title).font(.callout.weight(.semibold)).lineLimit(1)
                Text(s.waiting ? "Getting the paragraph ready…" : "Paragraph \(min(s.index + 1, s.paragraphs.count)) of \(s.paragraphs.count)")
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
            Menu {
                ForEach(s.voices, id: \.self) { v in
                    Button { Task { await s.use(voice: v) } } label: {
                        if v == s.voice { Label(PrefsView.voiceName(v), systemImage: "checkmark") } else { Text(PrefsView.voiceName(v)) }
                    }
                }
            } label: { Text(s.voice.isEmpty ? "Voice" : PrefsView.voiceName(s.voice).components(separatedBy: " · ").first ?? "Voice") }
            .menuStyle(.borderlessButton)
            .fixedSize()
            .task { await s.loadVoices() }
            Menu {
                Button("No Sleep Timer") { s.sleep(after: nil) }
                ForEach([15, 30, 45, 60], id: \.self) { n in Button("In \(n) Minutes") { s.sleep(after: n) } }
            } label: { Image(systemName: s.sleepAt == nil ? "moon.zzz" : "moon.zzz.fill") }
            .menuStyle(.borderlessButton)
            .fixedSize()
            .help(s.sleepAt.map { "Reading stops at " + $0.formatted(date: .omitted, time: .shortened) } ?? "The sleep timer")
            Button { s.stop() } label: { Image(systemName: "xmark") }.help("Stop reading aloud")
        }
        .buttonStyle(.borderless)
        .padding(.horizontal, 18)
        .padding(.vertical, 10)
        .glassEffect(.regular, in: Capsule())
    }

    private func speed(_ r: Double) -> String { r == 1 ? "1×" : String(format: "%g×", r) }
}
