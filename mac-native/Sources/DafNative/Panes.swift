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

