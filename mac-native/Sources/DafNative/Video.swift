import AppKit
import AVFoundation
import AVKit
import MediaPlayer
import SwiftUI
import WebKit

/// A video or an episode, as the page's: the player above the transcript, which follows along as it
/// plays; a timestamp plays from there; Clip 30s highlights the last 30 seconds.
/// - YouTube: its private-mode player (youtube-nocookie) in a web view. With no transcript yet,
///   YouTube's captions or a transcription on the server.
/// - A reel (social.py): Daf's own copy of the video, standing up, in AVPlayer (/api/media/<id>).
/// - A podcast episode (episodes.py): its audio in AVPlayer, with −15 and +30, the speed and the
///   chapters. Where you stop goes to Daf in stretches (/api/podcasts/position), for AntennaPod.
@MainActor
@Observable
final class VideoPlayer {
    enum Kind { case youtube, reel, episode }
    let kind: Kind
    let ytID: String
    var playing = false
    var time: Double = 0
    var duration: Double = 0
    var follow = true
    /// An episode's speed, kept for the next one, as the page keeps it.
    var rate: Double = 1
    /// A reel's shape, width over height, once its video says: Instagram's feed has square and wide ones too.
    var aspect: Double?
    @ObservationIgnored weak var web: WKWebView?
    @ObservationIgnored private(set) var av: AVPlayer?
    @ObservationIgnored private var timer: Timer?
    @ObservationIgnored var onTick: ((Double, Bool) -> Void)?
    /// An episode: its doc (for the stretches), what Now Playing shows, and where to start once
    /// the audio is ready (and whether to play from there).
    @ObservationIgnored var docID: String?
    @ObservationIgnored var nowPlaying: (title: String, artist: String)?
    @ObservationIgnored var startAt: Double?
    @ObservationIgnored var startPlaying = false
    @ObservationIgnored private var seg: Double?
    @ObservationIgnored private var last: Double = 0
    @ObservationIgnored private var lastTick = Date()
    @ObservationIgnored private var remote: [(MPRemoteCommand, Any)] = []
    private static weak var current: VideoPlayer?
    /// For the self-test: the stretches sent, in whole seconds.
    @ObservationIgnored private(set) var stretches: [(Int, Int)] = []

    static let rates: [Double] = [1, 1.2, 1.4, 1.6, 1.8, 2, 0.8]

    init(ytID: String) {
        kind = .youtube
        self.ytID = ytID
    }

    /// A reel's video or an episode's audio: from Daf with the sign-in, or from the podcast's own server.
    init(media: String, kind: Kind) {
        self.kind = kind
        ytID = ""
        let url = API.shared.url(media)
        var opts: [String: Any] = [:]
        if url.host == API.shared.base.host, let jar = HTTPCookieStorage.shared.cookies(for: url) { opts[AVURLAssetHTTPCookiesKey] = jar }
        let p = AVPlayer(playerItem: AVPlayerItem(asset: AVURLAsset(url: url, options: opts)))
        if kind == .episode {
            let r = UserDefaults.standard.double(forKey: "podRate")
            rate = r > 0 ? r : 1
            p.defaultRate = Float(rate)
        }
        av = p
    }

    /// The video's id in a YouTube or Invidious address.
    static func id(_ url: String?) -> String? {
        guard let u = url, let r = u.range(of: "(?:v=|youtu\\.be/|/shorts/|/embed/)([A-Za-z0-9_-]{11})", options: .regularExpression) else { return nil }
        return String(u[r].suffix(11))
    }

    var html: String {
        """
        <!doctype html><html><head><meta charset="utf-8"><style>html,body{margin:0;height:100%;background:#000;overflow:hidden}#p{position:absolute;inset:0;width:100%;height:100%}</style></head>
        <body><div id="p"></div><script src="https://www.youtube.com/iframe_api"></script><script>
        var player = null;
        function onYouTubeIframeAPIReady(){ player = new YT.Player('p', { videoId: '\(ytID)', host: 'https://www.youtube-nocookie.com', width: '100%', height: '100%',
          playerVars: { rel: 0, modestbranding: 1, playsinline: 1 } }); }
        function dafState(){ try { return [player.getCurrentTime() || 0, player.getPlayerState() === 1 ? 1 : 0]; } catch(e){ return [0, 0]; } }
        function dafSeek(t){ try { player.seekTo(t, true); player.playVideo(); } catch(e){} }
        function dafToggle(){ try { player.getPlayerState() === 1 ? player.pauseVideo() : player.playVideo(); } catch(e){} }
        </script></body></html>
        """
    }

    func start() {
        timer?.invalidate()
        timer = Timer.scheduledTimer(withTimeInterval: 0.5, repeats: true) { [weak self] _ in MainActor.assumeIsolated { self?.poll() } }
        if kind == .episode { commands(true) }
    }

    /// Closed: the stretch played so far goes now, and a reel or an episode stops playing.
    func stop() {
        timer?.invalidate()
        timer = nil
        if let s = seg { send(s, time); seg = nil }
        av?.pause()
        if kind == .episode { commands(false) }
    }

    private func poll() {
        guard let p = av else { pollWeb(); return }
        if let item = p.currentItem, item.status == .readyToPlay {
            if duration == 0, item.duration.isNumeric, item.duration.seconds > 0 { duration = item.duration.seconds }
            let size = item.presentationSize
            if aspect == nil, kind == .reel, size.width > 0, size.height > 0 { aspect = size.width / size.height }
            if let at = startAt {
                startAt = nil
                p.seek(to: CMTime(seconds: at, preferredTimescale: 600), toleranceBefore: .zero, toleranceAfter: .zero)
                time = at
                last = at
                lastTick = Date()
                if startPlaying { p.play() }
                return
            }
        }
        let t = p.currentTime().seconds, now = t.isFinite ? max(0, t) : 0
        let on = p.timeControlStatus != .paused
        if kind == .episode { track(now, on) }
        time = now
        if on != playing {
            playing = on
            showNowPlaying()
        }
        onTick?(now, on)
    }

    private func pollWeb() {
        web?.evaluateJavaScript("dafState()") { [weak self] r, _ in
            MainActor.assumeIsolated {
                guard let self, let v = r as? [Any], v.count == 2 else { return }
                self.time = (v[0] as? NSNumber)?.doubleValue ?? 0
                self.playing = ((v[1] as? NSNumber)?.intValue ?? 0) == 1
                self.onTick?(self.time, self.playing)
            }
        }
    }

    /// Where you stop goes to AntennaPod in stretches, as the page sends them: on a pause, on a jump,
    /// every two minutes, and when the episode closes.
    private func track(_ now: Double, _ on: Bool) {
        let gap = Date().timeIntervalSince(lastTick)
        lastTick = Date()
        let expected = last + (playing ? gap * Double(max(av?.rate ?? 1, 0.5)) : 0)
        if let s = seg, abs(now - expected) > 3 {           // a jump on the player's bar: the stretch ends where it was
            send(s, last)
            seg = on ? now : nil
        } else if on && !playing {
            seg = now
        } else if !on, playing, let s = seg {
            send(s, now)
            seg = nil
        } else if on, let s = seg, now - s >= 120 {
            send(s, now)
            seg = now
        }
        last = now
    }

    private func send(_ from: Double, _ to: Double) {
        guard let doc = docID else { return }
        let a = Int(from), b = Int(to)
        guard b > a else { return }
        stretches.append((a, b))
        var body: [String: Any] = ["doc": doc, "started": a, "position": b]
        if duration > 0 { body["total"] = Int(duration.rounded()) }
        Task { _ = try? await API.shared.send("POST", "/api/podcasts/position", body) }
    }

    /// A time picked (a timestamp, a chapter, −15 or +30) plays from there; the slider only moves it.
    func seek(_ t: Double, play: Bool = true) {
        guard let p = av else { web?.evaluateJavaScript("dafSeek(\(t))"); return }
        if let s = seg { send(s, time) }
        seg = nil
        let to = max(0, duration > 1 ? min(t, duration - 1) : t)
        p.seek(to: CMTime(seconds: to, preferredTimescale: 600), toleranceBefore: .zero, toleranceAfter: .zero)
        time = to
        last = to
        lastTick = Date()
        if p.timeControlStatus != .paused { seg = to } else if play { p.play() }
    }

    func skip(_ s: Double) { seek(max(0, time + s)) }

    func toggle() {
        guard let p = av else { web?.evaluateJavaScript("dafToggle()"); return }
        if p.timeControlStatus == .paused { p.play() } else { p.pause() }
    }

    /// The next speed: 1×, 1.2× and so on to 2×, then 0.8×.
    func nextRate() {
        let i = Self.rates.firstIndex { abs($0 - rate) < 0.01 } ?? -1
        rate = Self.rates[(i + 1) % Self.rates.count]
        UserDefaults.standard.set(rate, forKey: "podRate")
        av?.defaultRate = Float(rate)
        if let p = av, p.timeControlStatus != .paused { p.rate = Float(rate) }
        showNowPlaying()
    }

    static func rateLabel(_ r: Double) -> String {
        (abs(r - r.rounded()) < 0.01 ? String(Int(r.rounded())) : String(format: "%.1f", r)) + "×"
    }

    // MARK: the Mac's media keys and Now Playing

    private func showNowPlaying() {
        guard kind == .episode, let np = nowPlaying, Self.current === self else { return }
        var info: [String: Any] = [MPMediaItemPropertyTitle: np.title, MPMediaItemPropertyArtist: np.artist,
                                   MPNowPlayingInfoPropertyElapsedPlaybackTime: time, MPNowPlayingInfoPropertyPlaybackRate: playing ? rate : 0]
        if duration > 0 { info[MPMediaItemPropertyPlaybackDuration] = duration }
        MPNowPlayingInfoCenter.default().nowPlayingInfo = info
        MPNowPlayingInfoCenter.default().playbackState = playing ? .playing : .paused
    }

    /// Play and pause, back 15 seconds and ahead 30, from the keyboard's media keys and Control Center.
    private func commands(_ on: Bool) {
        for (cmd, target) in remote { cmd.removeTarget(target) }
        remote = []
        guard on else {
            if Self.current === self {
                Self.current = nil
                MPNowPlayingInfoCenter.default().nowPlayingInfo = nil
                MPNowPlayingInfoCenter.default().playbackState = .stopped
            }
            return
        }
        Self.current = self
        let c = MPRemoteCommandCenter.shared()
        c.skipBackwardCommand.preferredIntervals = [15]
        c.skipForwardCommand.preferredIntervals = [30]
        let acts: [(MPRemoteCommand, @MainActor (VideoPlayer) -> Void)] = [
            (c.togglePlayPauseCommand, { $0.toggle() }), (c.playCommand, { $0.av?.play() }), (c.pauseCommand, { $0.av?.pause() }),
            (c.skipBackwardCommand, { $0.skip(-15) }), (c.skipForwardCommand, { $0.skip(30) }),
        ]
        for (cmd, act) in acts {
            cmd.isEnabled = true
            let target = cmd.addTarget { [weak self] _ in
                Task { @MainActor in if let self, Self.current === self { act(self) } }
                return .success
            }
            remote.append((cmd, target))
        }
        showNowPlaying()
    }

    static func clock(_ t: Double) -> String {
        let s = Int(t), h = s / 3600, m = (s % 3600) / 60
        return h > 0 ? String(format: "%d:%02d:%02d", h, m, s % 60) : String(format: "%d:%02d", m, s % 60)
    }
}

/// The player itself, in a web view with Daf's address as its page (YouTube's embeds want one).
struct YouTubeView: NSViewRepresentable {
    let player: VideoPlayer

    func makeNSView(context: Context) -> WKWebView {
        let config = WKWebViewConfiguration()
        config.preferences.isElementFullscreenEnabled = true
        config.mediaTypesRequiringUserActionForPlayback = []
        let web = WKWebView(frame: .zero, configuration: config)
        web.setValue(false, forKey: "drawsBackground")
        web.loadHTMLString(player.html, baseURL: API.shared.base)
        player.web = web
        player.start()
        return web
    }

    func updateNSView(_ web: WKWebView, context: Context) {}

    static func dismantleNSView(_ web: WKWebView, coordinator: ()) { web.loadHTMLString("", baseURL: nil) }
}

/// A reel's video or an episode's audio, in AVKit's player with its own bar.
struct MediaView: NSViewRepresentable {
    let player: VideoPlayer

    func makeNSView(context: Context) -> AVPlayerView {
        let v = AVPlayerView()
        v.player = player.av
        v.controlsStyle = .inline
        v.videoGravity = .resizeAspect
        v.showsFullScreenToggleButton = player.kind == .reel
        v.allowsPictureInPicturePlayback = player.kind == .reel
        player.start()
        return v
    }

    func updateNSView(_ v: AVPlayerView, context: Context) {}

    static func dismantleNSView(_ v: AVPlayerView, coordinator: ()) { v.player = nil }
}

/// An episode's own bar, in the theme's colours: play and pause, where it is, and the rest to go.
struct AudioBar: View {
    let player: VideoPlayer
    /// Where the slider is while it's dragged; the audio goes there when it's let go.
    @State private var dragging: Double?

    var body: some View {
        HStack(spacing: 12) {
            Button { player.toggle() } label: {
                Image(systemName: player.playing ? "pause.fill" : "play.fill").font(.title2).frame(width: 28, height: 28)
            }
            .buttonStyle(.borderless)
            .help(player.playing ? "Pause (P)" : "Play (P)")
            Text(VideoPlayer.clock(dragging ?? player.time)).monospacedDigit().foregroundStyle(.secondary)
            Slider(value: Binding(get: { dragging ?? player.time }, set: { dragging = $0 }), in: 0...max(1, player.duration), onEditingChanged: { editing in
                if !editing, let t = dragging {
                    player.seek(t, play: false)
                    dragging = nil
                }
            })
            .disabled(player.duration == 0)
            Text(player.duration > 0 ? "−" + VideoPlayer.clock(max(0, player.duration - (dragging ?? player.time))) : "–:––")
                .monospacedDigit().foregroundStyle(.secondary)
        }
        .onAppear { player.start() }
    }
}

/// A video's or an episode's page: the player and its bar above the transcript (or the way to get one).
struct VideoArticle: View {
    @Environment(AppModel.self) private var app
    let model: ReaderModel
    @State private var asked: String?
    /// An episode's transcript once asked for here (Transcribe, Try Again), before the doc says so.
    @State private var podtr: J?

    private var doc: J? { model.doc }
    private var episode: J? { doc?.o("episode") }
    private var isReel: Bool { doc?.b("reel") ?? false }

    var body: some View {
        GeometryReader { g in
            VStack(spacing: 0) {
                if let v = model.video {
                    switch v.kind {
                    case .youtube: youtubeHead(v)
                    case .reel: reelHead(v, tall: min(600, max(240, g.size.height * 0.62)))
                    case .episode: episodeHead(v)
                    }
                    Divider()
                } else if isReel {
                    reelWaiting(tall: min(420, max(200, g.size.height * 0.45)))
                    Divider()
                }
                if doc?.list("blocks").isEmpty ?? true {
                    if isReel { Spacer() } else if episode != nil {
                        Text("Nothing to read yet. The transcript shows here once there is one.")
                            .foregroundStyle(.secondary)
                            .frame(maxWidth: .infinity, maxHeight: .infinity)
                    } else { noTranscript }
                } else {
                    ArticleReader(model: model)
                }
            }
        }
        .task(id: model.id) { await watch() }
    }

    // MARK: YouTube

    private func youtubeHead(_ v: VideoPlayer) -> some View {
        VStack(spacing: 0) {
            YouTubeView(player: v)
                .aspectRatio(16 / 9, contentMode: .fit)
                .frame(maxWidth: 760, maxHeight: 420)
                .frame(maxWidth: .infinity)
                .background(Color.black)
            HStack(spacing: 14) {
                clipButton
                followToggle(v)
                Text(VideoPlayer.clock(v.time)).monospacedDigit().foregroundStyle(.secondary)
                Spacer()
                Link("Watch on Invidious", destination: URL(string: "https://yt.tiresia.xyz/watch?v=" + v.ytID)!).font(.callout)
            }
            .controlSize(.small)
            .padding(.horizontal, 16).padding(.vertical, 8)
        }
    }

    private var noTranscript: some View {
        VStack(spacing: 12) {
            Text(asked ?? "No transcript yet.").foregroundStyle(.secondary)
            if asked == nil {
                HStack {
                    Button("Get YouTube's Captions") { Task { await transcript(whisper: false) } }
                    Button("Transcribe on the Server (Slow)") { Task { await transcript(whisper: true) } }
                }
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    // MARK: a reel

    private func reelHead(_ v: VideoPlayer, tall: CGFloat) -> some View {
        VStack(spacing: 0) {
            MediaView(player: v)
                .aspectRatio(v.aspect ?? 9 / 16, contentMode: .fit)
                .frame(maxWidth: 760, maxHeight: tall)
                .frame(maxWidth: .infinity)
                .background(Color.black)
            HStack(spacing: 14) {
                clipButton
                followToggle(v)
                Spacer()
                instagramLink
            }
            .controlSize(.small)
            .padding(.horizontal, 16).padding(.vertical, 8)
        }
    }

    /// No video yet: on its way from Instagram, or why not (and where to sign in again).
    private func reelWaiting(tall: CGFloat) -> some View {
        let err = doc?.s("content_error")
        return VStack(spacing: 0) {
            VStack(spacing: 12) {
                Text(doc?.b("preparing") == true ? "Getting the reel from Instagram. It plays here in a moment." : err ?? "Daf doesn't have this video yet.")
                    .multilineTextAlignment(.center)
                    .foregroundStyle(.white.opacity(0.85))
                if err?.contains("sign in again") == true {
                    Button("Instagram in Settings…") { app.openSettings(tab: "connections", at: "instagram") }
                }
            }
            .padding(24)
            .frame(width: tall * 9 / 16, height: tall)
            .frame(maxWidth: .infinity)
            .background(Color.black)
            HStack { Spacer(); instagramLink }
                .controlSize(.small)
                .padding(.horizontal, 16).padding(.vertical, 8)
        }
    }

    @ViewBuilder private var instagramLink: some View {
        if let u = doc?.s("url").flatMap(URL.init(string:)) { Link("Open on Instagram", destination: u).font(.callout) }
    }

    // MARK: an episode

    private func episodeHead(_ v: VideoPlayer) -> some View {
        let chapters = episode?.a("chapters") ?? []
        return VStack(alignment: .leading, spacing: 10) {
            HStack(spacing: 12) {
                if let img = episode?.s("image") {
                    AsyncImage(url: API.shared.url(img)) { p in
                        if let i = p.image { i.resizable().scaledToFill() } else { Color.secondary.opacity(0.15) }
                    }
                    .frame(width: 56, height: 56)
                    .clipShape(RoundedRectangle(cornerRadius: 10))
                }
                AudioBar(player: v)
            }
            HStack(spacing: 10) {
                Button("−15") { v.skip(-15) }.help("Back 15 seconds (←)")
                Button("+30") { v.skip(30) }.help("Ahead 30 seconds (→)")
                Button(VideoPlayer.rateLabel(v.rate)) { v.nextRate() }.help("Speed")
                clipButton
                followToggle(v)
                if !chapters.isEmpty {
                    Menu("Chapters") {
                        ForEach(Array(chapters.enumerated()), id: \.offset) { _, c in
                            Button(VideoPlayer.clock(c.d("t") ?? 0) + "  " + (c.s("title") ?? "")) { v.seek(c.d("t") ?? 0) }
                        }
                    }
                    .fixedSize()
                }
                transcriptState
                Spacer()
                if let feed = episode?.s("feed") {
                    Button(episode?.s("podcast") ?? "The Show") { app.showPodcast(feed) }
                        .buttonStyle(.link)
                        .lineLimit(1)
                        .help("The show's episodes")
                }
            }
            .controlSize(.small)
        }
        .padding(.horizontal, 16).padding(.vertical, 10)
        .frame(maxWidth: 820)
        .frame(maxWidth: .infinity)
    }

    /// The transcript: being made, failed (and Try Again), or Transcribe.
    @ViewBuilder private var transcriptState: some View {
        let st = podtr ?? episode?.o("transcript")
        switch st?.s("status") {
        case "done": EmptyView()
        case "queued", "running": Text("Transcribing…").foregroundStyle(.secondary)
        case "failed":
            Text("No transcript: " + (st?.s("error") ?? "")).foregroundStyle(.secondary).lineLimit(1).help(st?.s("error") ?? "")
            Button("Try Again") { Task { await transcribe() } }
        default: Button("Transcribe") { Task { await transcribe() } }
        }
    }

    private func transcribe() async {
        do {
            let r = J(try await API.shared.send("POST", "/api/podcasts/transcribe", ["doc": model.id]))
            let queued: J = J(["status": "queued"])
            if r?.s("status") == "done" { podtr = nil; await model.load() } else { podtr = queued }
        } catch { app.error = error.localizedDescription }
    }

    // MARK: shared

    private var clipButton: some View {
        Button { Task { await model.clip(30) } } label: { Label("Clip 30s", systemImage: "scissors") }
            .help("Highlight the last 30 seconds (C)")
    }

    private func followToggle(_ v: VideoPlayer) -> some View {
        Toggle("Follow Along", isOn: Binding(get: { v.follow }, set: { v.follow = $0 }))
    }

    /// What's on its way, looked for every five seconds as the page does: a reel coming from
    /// Instagram, an episode's transcript.
    private func watch() async {
        while !Task.isCancelled {
            try? await Task.sleep(nanoseconds: 5_000_000_000)
            guard !Task.isCancelled else { return }
            let reelComing = isReel && doc?.b("preparing") == true
            let tr = (podtr ?? episode?.o("transcript"))?.s("status")
            let trComing = episode != nil && (tr == "queued" || tr == "running")
            guard reelComing || trComing, let st = try? await API.shared.json("/api/docs/\(API.enc(model.id))/transcript") else { continue }
            if let p = st.o("podtr") {
                if st.b("ready") { podtr = nil; await model.load() } else if p.s("status") == "failed" { podtr = p }
            } else if st.b("ready") || ["done", "failed"].contains(st.o("reel")?.s("status") ?? "") {
                await model.load()
            }
        }
    }

    /// Ask for the transcript, then look every five seconds until it's there.
    private func transcript(whisper: Bool) async {
        do {
            try await API.shared.send("POST", "/api/docs/\(API.enc(model.id))/transcript", ["whisper": whisper])
            asked = whisper ? "Transcribing on the server. It shows up here when it's done." : "Asking YouTube for its captions…"
            for _ in 0..<120 {
                try? await Task.sleep(nanoseconds: 5_000_000_000)
                if let st = try? await API.shared.json("/api/docs/\(API.enc(model.id))/transcript"), st.b("ready") {
                    await model.load()
                    asked = nil
                    return
                }
            }
        } catch { app.error = error.localizedDescription }
    }
}
