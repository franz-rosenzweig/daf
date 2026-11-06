import AppKit
import AVFoundation
import MediaPlayer
import SwiftUI

/// The player (web/player.js): one for everything that plays, docked along the bottom of the window,
/// so it keeps playing wherever you go in Daf. A click on it opens the whole player: the picture, the
/// time to scrub, the speed, a sleep timer (in minutes, or at the end of the chapter), the chapters,
/// and Go to It.
///
/// Two kinds of thing play here:
/// - media (play): an episode's audio, or an audiobook's files one after another as one long track
///   (Audiobookshelf). The item hears what happens (save), so the page that started it can come and go.
/// - read-aloud (Speaker): an article or a book read a paragraph at a time. The bar shows it and its
///   buttons are Speaker's; starting one stops the other.
@MainActor
@Observable
final class Player {
    static let shared = Player()

    struct Track { let url: String; let start: Double; let dur: Double }
    struct Chapter: Hashable { let t: Double; let title: String }
    /// What the item playing hears, as the page's save does.
    enum Event { case play(Double), pause(Double), seek(from: Double, to: Double), tick(Double), ended(Double), stop(Double) }

    /// Something to play: an episode, one of Audiobookshelf's recordings, or an audiobook.
    final class Item {
        let id: String
        let kind: String
        let title: String
        let sub: String
        let art: String?
        let tracks: [Track]
        let duration: Double
        let chapters: [Chapter]
        /// Where Go to It goes: "#read/<doc>", "#book/<id>", "#podcasts/abs/<item>".
        let open: String?
        /// An episode's page (it can change once, when it's saved to the Library) and its audio.
        var doc: String?
        var audio: String?
        var back: Double = 15
        var fwd: Double = 30
        var save: (@MainActor (Event) -> Void)?

        init(id: String, kind: String, title: String, sub: String, art: String?, tracks: [Track], duration: Double, chapters: [Chapter], open: String?) {
            self.id = id; self.kind = kind; self.title = title; self.sub = sub; self.art = art
            self.tracks = tracks.isEmpty ? [Track(url: "", start: 0, dur: duration)] : tracks
            self.duration = duration; self.chapters = chapters; self.open = open
        }
    }

    private(set) var cur: Item?
    private(set) var playing = false
    private(set) var time: Double = 0
    /// The whole length: an audiobook's files end to end, else the item's or the file's own.
    private(set) var total: Double = 0
    private(set) var rate: Double = { let r = UserDefaults.standard.double(forKey: "podRate"); return r > 0 ? r : 1 }()
    private(set) var sleepAt: Date?
    private(set) var sleepEnd = false
    /// For the self-test: no sound (the app's own player, never the Mac's volume), and the stretches episodes sent.
    @ObservationIgnored var muted = false { didSet { av?.isMuted = muted } }
    @ObservationIgnored private(set) var sent: [(Int, Int)] = []

    static let rates: [Double] = [1, 1.2, 1.4, 1.6, 1.8, 2, 0.8]

    @ObservationIgnored private var av: AVPlayer?
    @ObservationIgnored private var track = -1
    @ObservationIgnored private var timer: Timer?
    @ObservationIgnored private var lastTick = Date.distantPast
    @ObservationIgnored private var endWatch: NSObjectProtocol?
    /// Where to go once the file is ready, and whether to play from there.
    @ObservationIgnored private var pending: (at: Double, play: Bool)?
    @ObservationIgnored private var remoteReady = false
    @ObservationIgnored private var artwork: MPMediaItemArtwork?

    private init() {}

    var on: Bool { cur != nil }
    func `is`(_ id: String) -> Bool { cur?.id == id }
    /// Something plays here: media, or something read aloud.
    var any: Bool { cur != nil || Speaker.shared.on }

    /// The chapter playing at t.
    func chapter(at t: Double) -> Int? {
        guard let chs = cur?.chapters else { return nil }
        return chs.lastIndex { $0.t <= t + 0.5 }
    }

    // MARK: playing

    /// Plays an item from `at` (or goes on with it, when it's the one playing).
    func play(_ item: Item, at: Double = 0, start: Bool = true) {
        if let c = cur, c.id == item.id {
            if at > 0 { seek(at) }
            if start, !playing { toggle() }
            return
        }
        if Speaker.shared.on { Speaker.shared.stop() }      // read-aloud stops for it
        stop(quiet: true)
        cur = item
        track = -1
        sleepAt = nil
        sleepEnd = false
        artwork = nil
        let last = item.tracks[item.tracks.count - 1]
        total = item.tracks.count > 1 && last.dur > 0 ? last.start + last.dur : item.duration
        remote()
        load(at, play: start)
        timer?.invalidate()
        timer = Timer.scheduledTimer(withTimeInterval: 0.5, repeats: true) { [weak self] _ in MainActor.assumeIsolated { self?.poll() } }
        nowPlaying()
        loadArtwork(item)
    }

    /// To time t: the file it falls in, and the place in that file.
    private func load(_ t: Double, play: Bool) {
        guard let it = cur else { return }
        let ts = it.tracks
        var i = 0
        while i < ts.count - 1 && ts[i + 1].start <= t { i += 1 }
        let off = max(0, t - ts[i].start)
        time = t
        if i != track || av == nil {
            track = i
            let p = av ?? AVPlayer()
            let item = Self.playerItem(ts[i].url)
            if let w = endWatch { NotificationCenter.default.removeObserver(w) }
            endWatch = NotificationCenter.default.addObserver(forName: .AVPlayerItemDidPlayToEndTime, object: item, queue: .main) { [weak self] _ in
                MainActor.assumeIsolated { self?.didEnd() }
            }
            p.replaceCurrentItem(with: item)
            p.isMuted = muted
            p.defaultRate = Float(rate)
            av = p
            pending = (off, play)
        } else {
            av?.seek(to: CMTime(seconds: off, preferredTimescale: 600), toleranceBefore: .zero, toleranceAfter: .zero)
            if play { av?.play() }
        }
    }

    /// A file from Daf with the sign-in, or from the podcast's own server.
    static func playerItem(_ path: String) -> AVPlayerItem {
        let url = API.shared.url(path)
        var opts: [String: Any] = [:]
        if url.host == API.shared.base.host, let jar = HTTPCookieStorage.shared.cookies(for: url) { opts[AVURLAssetHTTPCookiesKey] = jar }
        return AVPlayerItem(asset: AVURLAsset(url: url, options: opts))
    }

    private func poll() {
        guard let it = cur, let p = av else { return }
        if let item = p.currentItem {
            if item.status == .failed {
                AppModel.shared.say("That didn't play: " + (item.error?.localizedDescription ?? "the file didn't come"))
                stop()
                return
            }
            if item.status == .readyToPlay, let pd = pending {
                pending = nil
                p.seek(to: CMTime(seconds: pd.at, preferredTimescale: 600), toleranceBefore: .zero, toleranceAfter: .zero)
                if pd.play { p.play() }
            }
            if it.tracks.count == 1, it.duration <= 0, total <= 0, item.duration.isNumeric, item.duration.seconds > 0 { total = item.duration.seconds }
        }
        let start = it.tracks[max(0, track)].start
        let ct = p.currentTime().seconds
        let now = start + (pending?.at ?? (ct.isFinite ? max(0, ct) : 0))
        let on = pending?.play ?? (p.timeControlStatus != .paused)
        time = now
        if on != playing {
            playing = on
            it.save?(on ? .play(now) : .pause(now))
            lastTick = Date()
            nowPlaying()
        }
        if on, Date().timeIntervalSince(lastTick) >= 15 { lastTick = Date(); it.save?(.tick(now)); nowPlaying() }
        if let s = sleepAt, Date() >= s { sleepAt = nil; p.pause(); AppModel.shared.say("Sleep timer: stopped") }
        if sleepEnd, let k = chapter(at: now), k + 1 < it.chapters.count, now >= it.chapters[k + 1].t - 0.3 {
            sleepEnd = false
            p.pause()
            AppModel.shared.say("Sleep timer: the end of the chapter")
        }
    }

    /// A file came to its end: an audiobook's next one, or the end of it all.
    private func didEnd() {
        guard let it = cur else { return }
        if track < it.tracks.count - 1 { load(it.tracks[track + 1].start, play: true); return }
        playing = false
        sleepEnd = false
        it.save?(.ended(time))
        nowPlaying()
    }

    /// A time picked (the slider, a chapter, a timestamp, back or ahead): it plays from there if it was playing.
    func seek(_ t: Double) {
        guard let it = cur else { return }
        let to = max(0, total > 1 ? min(t, total - 0.5) : t)
        it.save?(.seek(from: time, to: to))
        load(to, play: playing)
        nowPlaying()
    }

    func skip(_ d: Double) { seek(time + d) }

    func toggle() {
        guard cur != nil, let p = av else { return }
        if pending != nil { pending!.play.toggle(); return }
        if p.timeControlStatus == .paused { p.play() } else { p.pause() }
    }

    func pause() { if playing { toggle() } }

    /// Stopped: where it was goes to the item, and the bar goes. quiet: another is about to take its place.
    func stop(quiet: Bool = false) {
        guard let it = cur else { return }
        it.save?(.stop(time))
        av?.pause()
        av?.replaceCurrentItem(with: nil)
        if let w = endWatch { NotificationCenter.default.removeObserver(w); endWatch = nil }
        timer?.invalidate()
        timer = nil
        cur = nil
        playing = false
        pending = nil
        track = -1
        sleepAt = nil
        sleepEnd = false
        if !quiet {
            MPNowPlayingInfoCenter.default().nowPlayingInfo = nil
            MPNowPlayingInfoCenter.default().playbackState = .stopped
        }
    }

    // MARK: speed and sleep

    func setRate(_ r: Double) {
        rate = r
        UserDefaults.standard.set(r, forKey: "podRate")
        av?.defaultRate = Float(r)
        if let p = av, p.timeControlStatus != .paused { p.rate = Float(r) }
        nowPlaying()
    }

    /// The next speed: 1×, 1.2× and so on to 2×, then 0.8×.
    func nextRate() {
        let i = Self.rates.firstIndex { abs($0 - rate) < 0.01 } ?? -1
        setRate(Self.rates[(i + 1) % Self.rates.count])
    }

    static func rateLabel(_ r: Double) -> String {
        (abs(r - r.rounded()) < 0.01 ? String(Int(r.rounded())) : String(format: "%.1f", r)) + "×"
    }

    /// Stops after so many minutes (nil: never).
    func sleep(after minutes: Int?) {
        sleepEnd = false
        sleepAt = minutes.map { Date().addingTimeInterval(TimeInterval($0 * 60)) }
    }

    /// Stops at the end of the chapter playing.
    func sleepAtChapterEnd() {
        sleepAt = nil
        sleepEnd = true
    }

    // MARK: the buttons, wherever they are: the bar, the media keys, Control Center, headphones

    enum Act { case toggle, play, pause, back, ahead, close }

    /// Whichever plays: the media, or what's read aloud (its paragraphs).
    func act(_ a: Act) {
        if let it = cur {
            switch a {
            case .toggle: toggle()
            case .play: if !playing { toggle() }
            case .pause: pause()
            case .back: skip(-it.back)
            case .ahead: skip(it.fwd)
            case .close: stop()
            }
        } else if Speaker.shared.on {
            let s = Speaker.shared
            switch a {
            case .toggle: s.toggle()
            case .play: s.resume()
            case .pause: s.pause()
            case .back: s.skip(-1)
            case .ahead: s.skip(1)
            case .close: s.stop()
            }
        }
    }

    /// The Mac's media keys and Now Playing, once, for both kinds.
    func remote() {
        guard !remoteReady else { return }
        remoteReady = true
        let c = MPRemoteCommandCenter.shared()
        c.skipBackwardCommand.preferredIntervals = [15]
        c.skipForwardCommand.preferredIntervals = [30]
        func on(_ cmd: MPRemoteCommand, _ a: Act) {
            cmd.isEnabled = true
            cmd.addTarget { [weak self] _ in
                guard let self else { return .commandFailed }
                MainActor.assumeIsolated { self.act(a) }
                return .success
            }
        }
        on(c.togglePlayPauseCommand, .toggle)
        on(c.playCommand, .play)
        on(c.pauseCommand, .pause)
        on(c.skipBackwardCommand, .back)
        on(c.skipForwardCommand, .ahead)
        on(c.previousTrackCommand, .back)
        on(c.nextTrackCommand, .ahead)
        c.changePlaybackPositionCommand.isEnabled = true
        c.changePlaybackPositionCommand.addTarget { [weak self] e in
            guard let self, let e = e as? MPChangePlaybackPositionCommandEvent else { return .commandFailed }
            let t = e.positionTime
            MainActor.assumeIsolated { if self.cur != nil { self.seek(t) } }
            return .success
        }
    }

    private func nowPlaying() {
        guard let it = cur else { return }
        var info: [String: Any] = [MPMediaItemPropertyTitle: it.title, MPMediaItemPropertyArtist: it.sub,
                                   MPNowPlayingInfoPropertyElapsedPlaybackTime: time, MPNowPlayingInfoPropertyPlaybackRate: playing ? rate : 0]
        if total > 0 { info[MPMediaItemPropertyPlaybackDuration] = total }
        if let a = artwork { info[MPMediaItemPropertyArtwork] = a }
        MPNowPlayingInfoCenter.default().nowPlayingInfo = info
        MPNowPlayingInfoCenter.default().playbackState = playing ? .playing : .paused
    }

    private func loadArtwork(_ item: Item) {
        guard let src = item.art else { return }
        Task {
            let url = API.shared.url(src)
            guard let (d, _) = try? await URLSession.shared.data(from: url), let img = NSImage(data: d), cur?.id == item.id else { return }
            nonisolated(unsafe) let picture = img
            artwork = MPMediaItemArtwork(boundsSize: picture.size) { _ in picture }
            nowPlaying()
        }
    }
}

// MARK: what plays

extension Player {
    /// An episode (episodes.py) as the player takes it: where you stop goes to Daf in stretches (on a
    /// pause, on a jump, every two minutes, when it stops), and AntennaPod picks them up at its next sync.
    static func episode(doc: String, title: String, source: String?, episode e: J) -> Item {
        let it = Item(id: "ep:" + doc, kind: "episode", title: title, sub: e.s("podcast") ?? source ?? "", art: e.s("image"),
                      tracks: [Track(url: e.s("audio") ?? "", start: 0, dur: e.d("duration") ?? 0)], duration: e.d("duration") ?? 0,
                      chapters: e.a("chapters").map { Chapter(t: $0.d("t") ?? 0, title: $0.s("title") ?? "") }, open: "#read/" + API.enc(doc))
        it.doc = doc
        it.audio = e.s("audio")
        var seg: Double?
        it.save = { [weak it] ev in
            @MainActor func post(_ from: Double, _ to: Double) {
                let a = Int(from), b = Int(to)
                guard b > a, let doc = it?.doc else { return }
                Player.shared.sent.append((a, b))
                var body: [String: Any] = ["doc": doc, "started": a, "position": b]
                if Player.shared.total > 0 { body["total"] = Int(Player.shared.total.rounded()) }
                Task { _ = try? await API.shared.send("POST", "/api/podcasts/position", body) }
            }
            switch ev {
            case .play(let at): seg = at
            case .seek(let from, let to):
                if let s = seg { post(s, from) }
                seg = Player.shared.playing ? to : nil
            case .tick(let at):
                if let s = seg, at - s >= 120 { post(s, at); seg = at }
            case .pause(let at), .ended(let at), .stop(let at):
                if let s = seg { post(s, at); seg = nil }
            }
        }
        return it
    }

    /// An episode from a list (the Podcasts page): its page made if it has none yet, from where the
    /// last play anywhere stopped, or paused when it's the one playing. Its page's id, or nil.
    @discardableResult
    func playEpisode(audio: String, found: J? = nil) async -> String? {
        do {
            if let f = found { _ = try await API.shared.send("POST", "/api/podcasts/open", ["audio": audio, "found": f.raw]) }
            let r = try await API.shared.json("/api/podcasts/play?audio=" + API.enc(audio))
            guard let id = r.s("id"), let ep = r.o("episode") else { return nil }
            if self.is("ep:" + id) { toggle(); return id }
            let pos = ep.o("position"), dur = ep.d("duration") ?? 0
            let at = pos?.d("t").flatMap { $0 > 15 && (dur == 0 || $0 < dur - 30) ? $0 : nil } ?? 0
            play(Self.episode(doc: id, title: r.s("title") ?? "", source: r.s("source"), episode: ep), at: at)
            return id
        } catch {
            AppModel.shared.error = error.localizedDescription
            return nil
        }
    }

    static func absKey(_ item: String, _ episode: String? = nil) -> String { "abs:" + item + (episode.map { ":" + $0 } ?? "") }

    /// One of Audiobookshelf's audiobooks or recordings (absapi.py): every file as one track, its chapters,
    /// and where you are back to ABS as you listen (its playback session): on a pause, on a jump, every
    /// minute while it plays, and when it stops. So ABS and its apps go on where Daf left off.
    static func absItem(_ p: J) -> Item {
        let item = p.s("item") ?? "", ep = p.s("episode")
        let open = p.s("book").map { "#book/" + API.enc($0) } ?? (ep != nil ? "#podcasts/abs/" + API.enc(item) : "#podcasts/audiobooks")
        let it = Item(id: absKey(item, ep), kind: p.s("kind") ?? "audiobook", title: p.s("title") ?? "", sub: p.s("sub") ?? "", art: p.s("art"),
                      tracks: p.a("tracks").map { Track(url: $0.s("url") ?? "", start: $0.d("start") ?? 0, dur: $0.d("dur") ?? 0) },
                      duration: p.d("duration") ?? 0, chapters: p.a("chapters").map { Chapter(t: $0.d("t") ?? 0, title: $0.s("title") ?? "") }, open: open)
        var since: Date?, sentAt = Date.distantPast
        it.save = { ev in
            @MainActor func post(_ at: Double, end: Bool = false) {
                let now = Date(), listened = since.map { now.timeIntervalSince($0) } ?? 0
                since = Player.shared.playing && !end ? now : nil
                sentAt = now
                var body: [String: Any] = ["item": item, "episode": ep ?? NSNull(), "at": max(0, at), "listened": listened, "end": end]
                let d = Player.shared.total > 0 ? Player.shared.total : (p.d("duration") ?? 0)
                if d > 0 { body["duration"] = d }
                Task { _ = try? await API.shared.send("POST", "/api/abs/progress", body) }
            }
            switch ev {
            case .play: since = Date()
            case .tick(let at): if Date().timeIntervalSince(sentAt) > 60 { post(at) }
            case .seek(_, let to): post(to)
            case .pause(let at): post(at)
            case .ended(let at), .stop(let at): post(at, end: true)
            }
            NotificationCenter.default.post(name: Player.absPlace, object: nil)
        }
        return it
    }

    /// Where you are in a recording or an audiobook changed: the lists that show it ask again.
    static let absPlace = Notification.Name("daf.absPlace")

    /// Plays an audiobook or a recording (or goes on with it, if it's the one playing), from `at` or where ABS has you.
    func playABS(_ item: String, episode: String? = nil, at: Double? = nil) async {
        let id = Self.absKey(item, episode)
        if self.is(id) {
            if let at { seek(at); if !playing { toggle() } } else { toggle() }
            return
        }
        do {
            let p = try await API.shared.json("/api/abs/play/" + API.enc(item) + (episode.map { "?episode=" + API.enc($0) } ?? ""))
            play(Self.absItem(p), at: at ?? p.d("at") ?? 0)
        } catch { AppModel.shared.error = error.localizedDescription }
    }

    /// Where in a book's audiobook a place in the book is (the server hears a few seconds to be sure);
    /// asked once for each place, and early, since it takes a few seconds.
    static var starts: [String: Task<J?, Never>] = [:]

    @discardableResult
    static func audioStart(book: String, place: [String: Any]? = nil) -> Task<J?, Never> {
        let k = book + "|" + ((place?["cfi"] as? String) ?? "")
        if let t = starts[k] { return t }
        let body = (place ?? [:]).merging(["exact": true]) { a, _ in a }
        let t = Task { () -> J? in
            let r = J(try? await API.shared.send("POST", "/api/abs/book/" + API.enc(book) + "/start", body))
            if r == nil { starts[k] = nil }
            return r
        }
        starts[k] = t
        return t
    }

    /// A book's audiobook from where I'm reading (a place in the book, or the book's kept place).
    func listen(book: String, item: String, place: [String: Any]? = nil) async {
        let note = Task { try? await Task.sleep(nanoseconds: 400_000_000); if !Task.isCancelled { AppModel.shared.say("Finding the place in the audiobook…") } }
        let r = await Self.audioStart(book: book, place: place).value
        note.cancel()
        guard let r, let t = r.d("t") else { AppModel.shared.say("The place in the audiobook didn't come"); return }
        await playABS(item, at: t)
        AppModel.shared.say("From " + (r.s("chapter").map { $0 + ", " } ?? "") + Self.hm(t) + " in")
    }

    static func clock(_ t: Double) -> String {
        let s = Int(max(0, t)), h = s / 3600, m = (s % 3600) / 60
        return h > 0 ? String(format: "%d:%02d:%02d", h, m, s % 60) : String(format: "%d:%02d", m, s % 60)
    }

    /// "2h 5m", "40m".
    static func hm(_ t: Double) -> String {
        let s = Int(max(0, t.rounded())), h = s / 3600, m = (s % 3600) / 60
        return h > 0 ? "\(h)h \(m)m" : "\(m)m"
    }
}

// MARK: the bar, and the whole player

/// Along the bottom while something plays: its picture and title (a click opens the whole player),
/// back, play or pause, ahead, and stop; a line under it for how far.
struct PlayerBar: View {
    private let p = Player.shared
    private let s = Speaker.shared
    @State private var big = false

    var body: some View {
        let media = p.cur != nil
        let on = media ? p.playing : s.playing
        HStack(spacing: 12) {
            Button { big.toggle() } label: {
                HStack(spacing: 10) {
                    PlayerArt(src: media ? p.cur?.art : nil, size: 34, corner: 7)
                    VStack(alignment: .leading, spacing: 1) {
                        Text(media ? p.cur?.title ?? "" : s.title).font(.callout.weight(.semibold)).lineLimit(1)
                        Text(media ? p.cur?.sub ?? "" : s.waiting ? "Getting the paragraph ready…" : "Paragraph \(min(s.index + 1, s.paragraphs.count)) of \(s.paragraphs.count)")
                            .font(.caption).foregroundStyle(.secondary).lineLimit(1).monospacedDigit()
                    }
                    .frame(maxWidth: 240, alignment: .leading)
                }
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .help("Open the player")
            .popover(isPresented: $big, arrowEdge: .top) { WholePlayer(close: { big = false }) }
            Button { p.act(.back) } label: { Image(systemName: media ? "gobackward.15" : "backward.fill") }
                .help(media ? "Back 15 seconds" : "The paragraph before")
            Button { p.act(.toggle) } label: { Image(systemName: on ? "pause.fill" : "play.fill").font(.title3).frame(width: 22) }
                .help(on ? "Pause" : "Play")
            Button { p.act(.ahead) } label: { Image(systemName: media ? "goforward.30" : "forward.fill") }
                .help(media ? "Ahead 30 seconds" : "The next paragraph")
            Button { p.act(.close) } label: { Image(systemName: "xmark") }.help("Stop")
        }
        .buttonStyle(.borderless)
        .padding(.horizontal, 18)
        .padding(.vertical, 10)
        .overlay(alignment: .bottomLeading) {
            GeometryReader { g in
                let f = media ? (p.total > 0 ? p.time / p.total : 0) : (s.paragraphs.isEmpty ? 0 : Double(min(s.index + 1, s.paragraphs.count)) / Double(s.paragraphs.count))
                Capsule().fill(Theme.shared.accent.opacity(0.8)).frame(width: max(0, min(1, f)) * (g.size.width - 36), height: 2)
                    .offset(x: 18, y: g.size.height - 4)
            }
            .allowsHitTesting(false)
        }
        .glassEffect(.regular, in: Capsule())
    }
}

/// The whole player: the picture, the title and the chapter, where it is (to scrub), the buttons, the
/// speed, the sleep timer, the chapters, the voice (read aloud), Go to It and Stop.
struct WholePlayer: View {
    let close: () -> Void
    private let p = Player.shared
    private let s = Speaker.shared
    @State private var dragging: Double?

    var body: some View {
        let media = p.cur != nil
        let on = media ? p.playing : s.playing
        VStack(spacing: 14) {
            PlayerArt(src: media ? p.cur?.art : nil, size: 200, corner: 14)
            VStack(spacing: 3) {
                Text(media ? p.cur?.title ?? "" : s.title).font(.headline).multilineTextAlignment(.center).lineLimit(3)
                Text(media ? p.cur?.sub ?? "" : "Read aloud").font(.callout).foregroundStyle(.secondary).lineLimit(1)
                if media, let k = p.chapter(at: dragging ?? p.time), let c = p.cur?.chapters[k] {
                    Text(c.title).font(.caption).foregroundStyle(.secondary).lineLimit(1)
                }
            }
            if media {
                VStack(spacing: 2) {
                    Slider(value: Binding(get: { dragging ?? p.time }, set: { dragging = $0 }), in: 0...max(1, p.total), onEditingChanged: { editing in
                        if !editing, let t = dragging { p.seek(t); dragging = nil }
                    })
                    .disabled(p.total == 0)
                    HStack {
                        Text(Player.clock(dragging ?? p.time))
                        Spacer()
                        Text(p.total > 0 ? "−" + Player.clock(max(0, p.total - (dragging ?? p.time)) / max(0.5, p.rate)) : "")
                    }
                    .font(.caption).monospacedDigit().foregroundStyle(.secondary)
                }
            } else {
                Text("¶ \(min(s.index + 1, s.paragraphs.count)) of \(s.paragraphs.count)").font(.caption).monospacedDigit().foregroundStyle(.secondary)
            }
            HStack(spacing: 26) {
                Button { p.act(.back) } label: { Image(systemName: media ? "gobackward.15" : "backward.fill").font(.title2) }
                    .help(media ? "Back 15 seconds" : "The paragraph before")
                Button { p.act(.toggle) } label: { Image(systemName: on ? "pause.circle.fill" : "play.circle.fill").font(.system(size: 44)) }
                    .help(on ? "Pause" : "Play")
                Button { p.act(.ahead) } label: { Image(systemName: media ? "goforward.30" : "forward.fill").font(.title2) }
                    .help(media ? "Ahead 30 seconds" : "The next paragraph")
            }
            .buttonStyle(.borderless)
            HStack(spacing: 8) {
                if media { mediaMenus } else { speechMenus }
            }
            .controlSize(.small)
            HStack {
                if let r = route {
                    Button("Go to It") { close(); AppModel.shared.goTo(r) }
                }
                Spacer()
                Button("Stop") { close(); p.act(.close) }
            }
            .controlSize(.small)
        }
        .padding(20)
        .frame(width: 320)
    }

    /// Where Go to It goes: the media's page, or what's read aloud.
    private var route: String? {
        if let it = p.cur { return it.open }
        guard let k = s.key else { return nil }
        return k.hasPrefix("book:") ? "#ebook/" + API.enc(String(k.dropFirst(5))) : "#read/" + API.enc(k)
    }

    @ViewBuilder private var mediaMenus: some View {
        Menu {
            ForEach(Player.rates, id: \.self) { r in
                Button { p.setRate(r) } label: { if abs(p.rate - r) < 0.01 { Label(Player.rateLabel(r), systemImage: "checkmark") } else { Text(Player.rateLabel(r)) } }
            }
        } label: { Text(Player.rateLabel(p.rate)).monospacedDigit() }
        .fixedSize()
        .help("Speed")
        Menu {
            Button("No Sleep Timer") { p.sleep(after: nil) }
            ForEach([15, 30, 45, 60], id: \.self) { n in Button("In \(n) Minutes") { p.sleep(after: n) } }
            if !(p.cur?.chapters.isEmpty ?? true) { Button("At the End of the Chapter") { p.sleepAtChapterEnd() } }
        } label: { Text(sleepLabel) }
        .fixedSize()
        if let chs = p.cur?.chapters, !chs.isEmpty {
            let k = p.chapter(at: p.time)
            Menu {
                ForEach(Array(chs.enumerated()), id: \.offset) { i, c in
                    Button { p.seek(c.t) } label: {
                        let t = Player.clock(c.t) + "  " + c.title
                        if i == k { Label(t, systemImage: "checkmark") } else { Text(t) }
                    }
                }
            } label: { Text("Chapters") }
            .fixedSize()
        }
    }

    private var sleepLabel: String {
        if p.sleepEnd { return "Sleep: End of Chapter" }
        if let at = p.sleepAt { return "Sleep in \(max(1, Int((at.timeIntervalSinceNow / 60).rounded()))) min" }
        return "Sleep Timer"
    }

    @ViewBuilder private var speechMenus: some View {
        Menu {
            ForEach([0.75, 1, 1.25, 1.5, 1.75, 2], id: \.self) { r in
                Button { s.rate = Float(r) } label: { if abs(Double(s.rate) - r) < 0.01 { Label(speed(r), systemImage: "checkmark") } else { Text(speed(r)) } }
            }
        } label: { Text(speed(Double(s.rate))).monospacedDigit() }
        .fixedSize()
        .help("Speed")
        Menu {
            ForEach(s.voices, id: \.self) { v in
                Button { Task { await s.use(voice: v) } } label: {
                    if v == s.voice { Label(PrefsView.voiceName(v), systemImage: "checkmark") } else { Text(PrefsView.voiceName(v)) }
                }
            }
        } label: { Text(s.voice.isEmpty ? "Voice" : PrefsView.voiceName(s.voice).components(separatedBy: " · ").first ?? "Voice") }
        .fixedSize()
        .task { await s.loadVoices() }
        Menu {
            Button("No Sleep Timer") { s.sleep(after: nil) }
            ForEach([15, 30, 45, 60], id: \.self) { n in Button("In \(n) Minutes") { s.sleep(after: n) } }
        } label: { Text(s.sleepAt.map { "Sleep at " + $0.formatted(date: .omitted, time: .shortened) } ?? "Sleep Timer") }
        .fixedSize()
    }

    private func speed(_ r: Double) -> String { r == 1 ? "1×" : String(format: "%g×", r) }
}

/// A picture to play, or the waveform where there's none (or it doesn't come).
struct PlayerArt: View {
    let src: String?
    let size: CGFloat
    var corner: CGFloat = 8

    var body: some View {
        AsyncImage(url: src.map { API.shared.url($0) }) { ph in
            if let i = ph.image { i.resizable().scaledToFill() } else { wave }
        }
        .frame(width: size, height: size)
        .clipShape(RoundedRectangle(cornerRadius: corner))
    }

    private var wave: some View {
        ZStack {
            Theme.shared.accent.opacity(0.14)
            Image(systemName: "waveform").font(.system(size: size * 0.4)).foregroundStyle(Theme.shared.accent)
        }
    }
}
