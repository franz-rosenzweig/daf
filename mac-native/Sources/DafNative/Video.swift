import AppKit
import SwiftUI
import WebKit

/// A video, as the page's: YouTube's private-mode player (youtube-nocookie) above its transcript,
/// which follows along as it plays; a timestamp plays from there; Clip 30s highlights the last 30
/// seconds. With no transcript yet: YouTube's captions, or a transcription on the server.
@MainActor
@Observable
final class VideoPlayer {
    let ytID: String
    var playing = false
    var time: Double = 0
    var follow = true
    @ObservationIgnored weak var web: WKWebView?
    @ObservationIgnored private var timer: Timer?
    @ObservationIgnored var onTick: ((Double, Bool) -> Void)?

    init(ytID: String) { self.ytID = ytID }

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
        </script></body></html>
        """
    }

    func start() {
        timer?.invalidate()
        timer = Timer.scheduledTimer(withTimeInterval: 0.5, repeats: true) { [weak self] _ in MainActor.assumeIsolated { self?.poll() } }
    }

    func stop() { timer?.invalidate(); timer = nil }

    private func poll() {
        web?.evaluateJavaScript("dafState()") { [weak self] r, _ in
            MainActor.assumeIsolated {
                guard let self, let v = r as? [Any], v.count == 2 else { return }
                self.time = (v[0] as? NSNumber)?.doubleValue ?? 0
                self.playing = ((v[1] as? NSNumber)?.intValue ?? 0) == 1
                self.onTick?(self.time, self.playing)
            }
        }
    }

    func seek(_ t: Double) { web?.evaluateJavaScript("dafSeek(\(t))") }

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

/// A video's page: the player and its bar above the transcript (or the way to get one).
struct VideoArticle: View {
    @Environment(AppModel.self) private var app
    let model: ReaderModel
    @State private var asked: String?

    var body: some View {
        VStack(spacing: 0) {
            if let v = model.video {
                YouTubeView(player: v)
                    .aspectRatio(16 / 9, contentMode: .fit)
                    .frame(maxWidth: 760, maxHeight: 420)
                    .frame(maxWidth: .infinity)
                    .background(Color.black)
                HStack(spacing: 14) {
                    Button { Task { await model.clip(30) } } label: { Label("Clip 30s", systemImage: "scissors") }
                        .help("Highlight the last 30 seconds (C)")
                    Toggle("Follow Along", isOn: Binding(get: { v.follow }, set: { v.follow = $0 }))
                    Text(VideoPlayer.clock(v.time)).monospacedDigit().foregroundStyle(.secondary)
                    Spacer()
                    Link("Watch on Invidious", destination: URL(string: "https://yt.tiresia.xyz/watch?v=" + v.ytID)!).font(.callout)
                }
                .controlSize(.small)
                .padding(.horizontal, 16).padding(.vertical, 8)
                Divider()
            }
            if model.doc?.list("blocks").isEmpty ?? true {
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
            } else {
                ArticleReader(model: model)
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
