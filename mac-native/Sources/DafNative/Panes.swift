import PDFKit
import SwiftUI
import WebKit

/// Books, manga and videos stay Daf's own pages for now: the page's reader in a web view inside
/// the native window, signed in with the app's cookie, without the page's sidebar (the window has
/// its own). The page counts its reading time and keeps its place itself, as in a browser.
struct WebPane: NSViewRepresentable {
    let route: String           // "#ebook/cal:45"

    static let hideChrome = """
    (() => { const s = document.createElement('style');
      s.textContent = '.app:not(.loggedout){grid-template-columns:minmax(0,1fr)!important} .app:not(.loggedout) > .side{display:none!important} .mobbar{display:none!important}';
      (document.head || document.documentElement).appendChild(s); })();
    """

    func makeNSView(context: Context) -> WKWebView {
        let config = WKWebViewConfiguration()
        config.websiteDataStore = .default()
        config.userContentController.addUserScript(WKUserScript(source: Self.hideChrome, injectionTime: .atDocumentEnd, forMainFrameOnly: true))
        config.preferences.isElementFullscreenEnabled = true
        let web = WKWebView(frame: .zero, configuration: config)
        web.allowsBackForwardNavigationGestures = false
        web.setValue(false, forKey: "drawsBackground")
        load(web)
        return web
    }

    func updateNSView(_ web: WKWebView, context: Context) {
        if web.url?.fragment.map({ "#" + $0 }) != route, !(web.url?.absoluteString.hasSuffix(route) ?? false) { load(web) }
    }

    private func load(_ web: WKWebView) {
        let target = URL(string: API.shared.base.absoluteString + "/" + route)!
        Task { @MainActor in
            if let c = API.shared.cookie { await web.configuration.websiteDataStore.httpCookieStore.setCookie(c) }
            web.load(URLRequest(url: target))
        }
    }
}

/// A PDF as printed, in Apple's own PDF view. One already open comes back at once when SwiftUI
/// makes the view again (a list refreshing beside it), instead of being fetched again.
struct PDFPane: View {
    let id: String
    @State private var document: PDFDocument?
    @State private var error: String?
    @MainActor static var kept: [String: PDFDocument] = [:]

    init(id: String) {
        self.id = id
        _document = State(initialValue: Self.kept[id])
    }

    var body: some View {
        Group {
            if let document { PDFKitView(document: document) }
            else if let error { ContentUnavailableView("The PDF didn't open", systemImage: "doc.richtext", description: Text(error)) }
            else { ProgressView().frame(maxWidth: .infinity, maxHeight: .infinity) }
        }
        .task(id: id) {
            if let d = Self.kept[id] { document = d; return }
            do {
                let data = try await API.shared.data("/api/docs/\(API.enc(id))/pdf")
                guard let d = PDFDocument(data: data) else { throw APIError(status: 0, message: "That isn't a PDF Daf can show.") }
                if Self.kept.count > 6 { Self.kept.removeAll() }
                Self.kept[id] = d
                document = d
            } catch is CancellationError {
            } catch let e as URLError where e.code == .cancelled {
            } catch { self.error = error.localizedDescription }
        }
    }
}

struct PDFKitView: NSViewRepresentable {
    let document: PDFDocument
    func makeNSView(context: Context) -> PDFView {
        let v = PDFView()
        v.autoScales = true
        v.displayMode = .singlePageContinuous
        v.displaysPageBreaks = true
        v.backgroundColor = .windowBackgroundColor
        v.document = document
        return v
    }
    func updateNSView(_ v: PDFView, context: Context) {
        if v.document !== document { v.document = document }
    }
}
