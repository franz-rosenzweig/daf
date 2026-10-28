using System.Text.Json;
using Daf.Core;

namespace Daf;

/// <summary>What the window puts in the page before the page's own scripts run (WebView2's document-created scripts).</summary>
static class Scripts
{
    /// <summary>What this shell answers (docs/SHELL.md §2); anything else, the page does as a browser would.</summary>
    public static readonly string[] Caps = ["share", "download", "openExternal", "alerts", "fullscreen", "offline", "bars"];

    /// <summary>
    /// window.dafShell over WebView2's web messages, the shell's own keys, and the mouse's
    /// Back and Forward buttons: in Daf's own pages only (<paramref name="origins"/>: the
    /// live site and the copy), and only in the top frame, so a frame inside the page (a
    /// video) can't call the app. On the copy there is no service worker: the copy is
    /// already the page kept on this PC, and a worker's own requests would pass the window by.
    /// </summary>
    public static string Shell(IEnumerable<string> origins) => $$"""
        (() => {
          const ours = {{JsonSerializer.Serialize(origins)}};
          const wv = window.chrome && window.chrome.webview;
          if (window.top !== window || !wv || !ours.includes(location.origin)) return;
          const post = (m) => wv.postMessage(m);

          // window.dafShell (docs/SHELL.md §2): each call a message, its promise settled by the reply
          let next = 1;
          const waiting = new Map();
          const call = (op, args) => new Promise((resolve, reject) => {
            const id = next++;
            waiting.set(id, { resolve, reject });
            post({ channel: 'shell', id, op, args: args || {} });
          });
          const caps = {{JsonSerializer.Serialize(Caps)}};
          const s = (v) => v == null ? '' : String(v);
          window.dafShell = Object.freeze({
            platform: 'windows', version: {{J.Quote(App.Version)}},
            can: (op) => caps.includes(op),
            share: (a) => call('share', { text: s(a && a.text), url: s(a && a.url), png: s(a && a.png), name: s(a && a.name) }),
            download: (a) => call('download', typeof a === 'string' ? { url: a } : { name: s(a && a.name), mime: s(a && a.mime), base64: s(a && a.base64) }),
            openExternal: (u) => call('openExternal', { url: s(u) }),
            // notifications for new posts in the feeds set to notify
            alerts: () => call('alerts', {}),
            // the manga reader's Full screen: the window's own, left again with the reader
            fullscreen: () => call('fullscreen', {}),
            // what's kept on this PC: {op: 'list' | 'has' | 'keep' | 'doc' | 'manga' | 'sync', id?, on?, size?}
            offline: (a) => call('offline', { op: s(a && a.op) || 'list', id: s(a && a.id), on: !(a && a.on === false), size: +(a && a.size) || 0 }),
            // the title bar and its menus in the theme's colour: {bg: '#rrggbb', dark}
            bars: (a) => call('bars', { bg: s(a && a.bg), dark: !!(a && a.dark) }),
          });
          wv.addEventListener('message', (e) => {
            const m = e.data;
            if (!m || typeof m !== 'object' || m.channel !== 'shell') return;
            const w = waiting.get(m.id);
            if (!w) return;
            waiting.delete(m.id);
            if (m.error !== undefined) w.reject(new Error(m.error)); else w.resolve(m.ok);
          });

          // The shell's own keys, once the page has had them and left them alone (Ctrl+K and
          // Daf's single letters stay the page's). AltGr is Ctrl+Alt on many keyboards and
          // types letters, so it never counts.
          const views = ['today', 'review', 'library', 'feed', 'highlights', 'books', 'stats'];
          const shellKey = (e) => {
            if (e.getModifierState && e.getModifierState('AltGraph')) return null;
            const ctrl = e.ctrlKey && !e.altKey && !e.metaKey, plain = !e.ctrlKey && !e.altKey && !e.metaKey && !e.shiftKey;
            if (plain && e.key === 'F11') return 'fullScreen';
            if (plain && e.key === 'F5') return 'reload';
            if (e.altKey && !e.ctrlKey && !e.shiftKey && e.key === 'ArrowLeft') return 'back';
            if (e.altKey && !e.ctrlKey && !e.shiftKey && e.key === 'ArrowRight') return 'forward';
            if (e.key === 'BrowserBack') return 'back';
            if (e.key === 'BrowserForward') return 'forward';
            if (!ctrl) return null;
            const d = /^Digit([1-7])$/.exec(e.code);
            if (d && !e.shiftKey) return 'go:' + views[+d[1] - 1];
            if (e.shiftKey) return { KeyS: 'saveLink', KeyP: 'paper', KeyE: 'export' }[e.code] || null;
            return { KeyN: 'newWindow', KeyW: 'close', KeyO: 'add', KeyR: 'reload', Comma: 'settings', BracketLeft: 'back', BracketRight: 'forward' }[e.code] || null;
          };
          window.addEventListener('keydown', (e) => {
            const what = shellKey(e);
            if (!what) return;
            setTimeout(() => { if (!e.defaultPrevented) post({ channel: 'key', what }); }, 0);
          }, true);
          // The mouse's Back and Forward buttons: through the page's Back (dafBack), not the browser's
          for (const type of ['mousedown', 'mouseup', 'auxclick']) {
            window.addEventListener(type, (e) => {
              if (e.button !== 3 && e.button !== 4) return;
              e.preventDefault();
              if (type === 'mouseup') post({ channel: 'key', what: e.button === 3 ? 'back' : 'forward' });
            }, true);
          }

          if (location.origin === {{J.Quote(Address.CopyOrigin)}}) {
            const none = Object.freeze({
              controller: null, ready: new Promise(() => {}),
              register: () => Promise.reject(new DOMException('The copy on this PC has no service worker', 'NotSupportedError')),
              getRegistration: () => Promise.resolve(undefined), getRegistrations: () => Promise.resolve([]),
              addEventListener() {}, removeEventListener() {},
            });
            try { Object.defineProperty(Navigator.prototype, 'serviceWorker', { configurable: true, get: () => none }); } catch (e) {}
          }
        })();
        """;

    /// <summary>
    /// Run first in the copy's page: the live page's settings (its theme, type and reader
    /// settings). A snapshot newer than the one the copy last took replaces what's there; otherwise only what's missing is added.
    /// </summary>
    public static string Seed(string json, long at) => $$"""
        if (location.origin === {{J.Quote(Address.CopyOrigin)}}) {
          try {
            const s = {{json}}, at = {{at}}, newer = +(localStorage.getItem('daf.shell.seeded') || 0) < at;
            for (const k in s) if (newer || localStorage.getItem(k) === null) localStorage.setItem(k, s[k]);
            if (newer) localStorage.setItem('daf.shell.seeded', String(at));
          } catch (e) {}
        }
        """;

    /// <summary>The live page's localStorage, but not its outbox, which goes from where it was made.</summary>
    public const string Snapshot = "JSON.stringify(Object.fromEntries(Object.entries(localStorage).filter(([k]) => k !== 'daf.outbox' && k !== 'daf.shell.seeded')))";
}
