/* Daf inside a native shell (docs/SHELL.md): the page's half of the contract.
   Nothing here runs in a browser: it starts only when the user agent names a shell. */
(() => {
'use strict';
const ua = / Daf\/([\w.]+) \((macOS|Android) shell\)/.exec(navigator.userAgent);
if (!ua) return;
const mac = ua[2] === 'macOS', root = document.documentElement;
root.classList.add('shell', mac ? 'shell-mac' : 'shell-android');

const $ = s => document.querySelector(s);
const C = () => window.DafCore;
const shell = () => window.dafShell;
const can = op => !!(shell() && shell().can && shell().can(op));
const view = () => (document.body && document.body.dataset.view) || ((C() && C().S.route) || [])[0] || '';
const shown = s => { const e = $(s); return !!e && !e.hidden; };
const press = s => { const e = $(s); if (!e) return false; e.click(); return true; };
// A key as if pressed on the page, for commands the page only has a key for.
const volume = dir => { window.dispatchEvent(new CustomEvent('daf-volume', { detail: { dir } })); return true; };
const key = (k, o) => { document.body.dispatchEvent(new KeyboardEvent('keydown', Object.assign({ key: k, bubbles: true, cancelable: true }, o))); return true; };
// One of the page's own [data-act] buttons, without one on screen.
const act = name => { const b = document.createElement('button'); b.hidden = true; b.dataset.act = name; document.body.appendChild(b); b.click(); b.remove(); return true; };
const waitFor = (s, ms) => new Promise(ok => { const t0 = Date.now(); const tick = () => { const e = $(s); if (e || Date.now() - t0 > ms) ok(e); else setTimeout(tick, 100); }; tick(); });
const b64 = blob => new Promise((ok, no) => { const r = new FileReader(); r.onload = () => ok(String(r.result).split(',')[1] || ''); r.onerror = () => no(r.error); r.readAsDataURL(blob); });

/* ---------- the look (Mac) ---------- */
// No title bar: the page runs to the top of the window, as Moshe's does (Ulysses' way, and
// macOS 26's). The traffic lights sit in the sidebar's top row (Window.swift: 20 pt in,
// centred in 56 pt), level with the views' top bars; the row holds them and a round sidebar
// button, and stays put when the sidebar scrolls. With the sidebar hidden (⌃⌘S) they sit at
// the start of the view's bar. The sidebar's edge and the reader's panels are dragged to size.
const pref = (k, d) => { try { const v = localStorage.getItem('daf.shell.' + k); return v == null ? d : v; } catch (e) { return d; } };
const keep = (k, v) => { try { localStorage.setItem('daf.shell.' + k, v); } catch (e) {} };
if (mac) {
  ['sidew', 'tocw', 'panelw'].forEach(k => { const v = pref(k, null); if (v) root.style.setProperty('--daf-' + k, v + 'px'); });
  if (pref('noside', '') === '1') root.classList.add('shell-noside');
  const css = document.createElement('style');
  css.textContent = [
    'html.shell-mac .app{grid-template-columns:var(--daf-sidew,232px) minmax(0,1fr)}',
    'html.shell-mac .brand{height:56px;padding:0;box-sizing:border-box;position:sticky;top:0;z-index:3;background:var(--side);flex:none}',
    'html.shell-mac .brand b{display:none}',
    'html.shell-mac.shell-noside .app:not(.loggedout){grid-template-columns:minmax(0,1fr)}',
    'html.shell-mac.shell-noside .app:not(.loggedout) .side{display:none}',
    'html.shell-mac.shell-noside .top{padding-left:132px}',
    'html.shell-mac.shell-fullscreen.shell-noside .top{padding-left:64px}',
    '#dafSideBtn{position:fixed;top:12px;left:calc(var(--daf-sidew,232px) - 46px);z-index:50;width:32px;height:32px;border-radius:50%;border:0;padding:0;display:grid;place-items:center;background:color-mix(in srgb,var(--fg) 7%,transparent);color:var(--fg-2);cursor:default}',
    '#dafSideBtn:hover{background:color-mix(in srgb,var(--fg) 13%,transparent);color:var(--fg)}',
    'html.shell-noside #dafSideBtn{left:86px} html.shell-fullscreen.shell-noside #dafSideBtn{left:16px}',
    '.app.loggedout ~ #dafSideBtn, .scrim:not([hidden]) ~ #dafSideBtn{display:none}',
    'html.shell-edge, html.shell-edge *, html.shell-sizing, html.shell-sizing *{cursor:col-resize!important}',
    'html.shell-sizing, html.shell-sizing *{user-select:none!important}',
    '@media (min-width:1001px){',
    ' html.shell-mac .rvgrid{grid-template-columns:var(--daf-tocw,220px) minmax(0,1fr) 0}',
    ' html.shell-mac .rvgrid.notoc{grid-template-columns:0 minmax(0,1fr) 0}',
    ' html.shell-mac .rvgrid.withpanel{grid-template-columns:var(--daf-tocw,220px) minmax(0,1fr) var(--daf-panelw,330px)}',
    // the manga reader covers the window: its top bar makes room for the traffic lights, as Daf's bars do
    'html.shell-mac .mtop{min-height:56px;box-sizing:border-box;padding-left:84px}',
    ' html.shell-mac .rvgrid.notoc.withpanel{grid-template-columns:0 minmax(0,1fr) var(--daf-panelw,330px)}',
    '}',
  ].join('\n');
  (document.head || root).appendChild(css);

  const btn = document.createElement('button');
  btn.id = 'dafSideBtn';
  btn.innerHTML = '<svg width="17" height="17" viewBox="0 0 20 20" aria-hidden="true"><rect x="2.5" y="3.5" width="15" height="13" rx="2.5" fill="none" stroke="currentColor" stroke-width="1.6"/><path d="M8 3.5v13" stroke="currentColor" stroke-width="1.6"/></svg>';
  const label = () => { const t = root.classList.contains('shell-noside') ? 'Show the sidebar (⌃⌘S)' : 'Hide the sidebar (⌃⌘S)'; btn.title = t; btn.setAttribute('aria-label', t); };
  label();
  btn.addEventListener('click', () => window.dafCommand('sidebar'));
  const place = () => { if (document.body && !btn.isConnected) document.body.appendChild(btn); };
  if (document.body) place(); else document.addEventListener('DOMContentLoaded', place);
  window.__dafSideLabel = label;
}
const toggleSide = () => {
  const off = root.classList.toggle('shell-noside');
  keep('noside', off ? '1' : '');
  if (window.__dafSideLabel) window.__dafSideLabel();
  return true;
};

// The panels' edges: the sidebar's right edge, and in an article or a book the contents'
// right edge and the side panel's left edge. A press within 4 px of one drags it; the
// width is kept for next time.
if (mac) {
  const rect = el => el && el.offsetWidth ? el.getBoundingClientRect() : null;
  const edges = () => {
    const out = [], side = rect($('.app:not(.loggedout) .side')), grid = $('.rvgrid');
    if (side) out.push({ x: side.right, top: side.top, bottom: side.bottom, v: 'sidew', min: 180, max: 380, w0: side.width, dir: 1 });
    if (grid && innerWidth > 1000) {
      const toc = !grid.classList.contains('notoc') && rect(grid.querySelector(':scope > .toc, :scope > .btoc'));
      if (toc) out.push({ x: toc.right, top: toc.top, bottom: toc.bottom, v: 'tocw', min: 160, max: 420, w0: toc.width, dir: 1 });
      const panel = grid.classList.contains('withpanel') && rect(grid.querySelector(':scope > .rpanel'));
      if (panel) out.push({ x: panel.left, top: panel.top, bottom: panel.bottom, v: 'panelw', min: 260, max: 600, w0: panel.width, dir: -1 });
    }
    return out;
  };
  const near = e => edges().find(g => Math.abs(e.clientX - g.x) <= 4 && e.clientY >= g.top && e.clientY <= g.bottom);
  let sizing = null;
  window.addEventListener('pointermove', e => {
    if (sizing) {
      // from where the press began, so the edge stays under the pointer
      const w = Math.round(Math.max(sizing.min, Math.min(sizing.max, sizing.w0 + sizing.dir * (e.clientX - sizing.x0))));
      root.style.setProperty('--daf-' + sizing.v, w + 'px');
      sizing.last = w;
      return;
    }
    root.classList.toggle('shell-edge', !!near(e));
  }, true);
  window.addEventListener('pointerdown', e => {
    if (e.button !== 0) return;
    const g = near(e);
    if (!g) return;
    e.preventDefault(); e.stopImmediatePropagation();
    sizing = Object.assign(g, { x0: e.clientX });
    root.classList.add('shell-sizing');
    try { root.setPointerCapture(e.pointerId); } catch (err) {}
  }, true);
  const done = () => {
    if (!sizing) return;
    if (sizing.last) keep(sizing.v, sizing.last);
    sizing = null;
    root.classList.remove('shell-sizing', 'shell-edge');
    window.dispatchEvent(new Event('resize'));          // the book reader lays its pages out again
  };
  window.addEventListener('pointerup', done, true);
  window.addEventListener('pointercancel', done, true);
}

/* ---------- back ---------- */
// Daf's own history in this window, so Back knows when there's nowhere to go.
const hist = [location.hash];
window.addEventListener('hashchange', () => {
  const h = location.hash;
  if (hist.length > 1 && hist[hist.length - 2] === h) hist.pop();
  else if (hist[hist.length - 1] !== h) hist.push(h);
  if (hist.length > 200) hist.shift();
});
// Whatever is in front: search, a dialog, a popover, the highlight bar, a sheet.
function closeFront(){
  if (shown('#palette')) { $('#palette').hidden = true; if ($('#modal').hidden) $('#scrim').hidden = true; return true; }
  if (shown('#modal')) { C().closeModal(); return true; }
  if (shown('#pop')) { $('#pop').hidden = true; return true; }
  if (shown('#selbar') && C().HL) { C().HL.hide(); return true; }
  const b = document.body.classList;
  if (b.contains('btocsheet') || b.contains('bpanelsheet')) { b.remove('btocsheet', 'bpanelsheet'); return true; }
  if (sheetPanel()) { press('#rtop [data-ract=panel]'); return true; }
  const side = $('#side'); if (side && side.classList.contains('open')) { side.classList.remove('open'); return true; }
  return false;
}
// the article's side panel, when the window is narrow enough that it's a sheet over the text
function sheetPanel(){ return innerWidth <= 1180 && view() === 'read' && !!$('.rvgrid.withpanel'); }
const closeAll = () => { for (let i = 0; i < 6 && closeFront(); i++); };
const front = () => shown('#palette') || shown('#modal') || shown('#pop') || shown('#selbar') ||
  document.body.classList.contains('btocsheet') || document.body.classList.contains('bpanelsheet') || sheetPanel();
window.dafBack = () => {
  if (closeFront()) return true;
  if (manga()) return key('Escape');      // the manga reader: its end panel, its bar, then the reader itself
  if (hist.length > 1) { history.back(); return true; }
  return false;
};

/* ---------- commands, for the shell's menus ---------- */
const GO = ['today', 'review', 'library', 'feed', 'highlights', 'books', 'stats', 'torah', 'paper', 'prefs'];
const art = () => view() === 'read', book = () => view() === 'ebook', manga = () => view() === 'mread';
const list = () => ['library', 'feed', 'view'].includes(view());
// A key as it's bound now (Preferences → Keyboard, keys.js), so the menus follow a changed shortcut.
const bound = (scope, a, k) => { const K = C() && C().Keys; return (K && K.keys(scope, a)[0]) || k; };
const CMD = {
  back: () => window.dafBack(),
  search: () => shown('#palette') || key('k', { metaKey: true, ctrlKey: !mac }),
  toc: () => book() ? press('[data-bk="toc"]') : art() && !!$('.rvgrid') && key(bound('article', 'toc', '[')),
  panel: () => book() ? press('[data-bk="panel"]') : art() && press('[data-ract="panel"]'),
  aa: () => book() ? press('[data-bk="aa"]') : art() && press('[data-ract="aa"]'),
  listen: () => book() ? press('[data-bk="listen"]') : art() && press('[data-ract="listen"]'),
  highlight: () => (art() || book()) && key(bound(art() ? 'article' : 'book', 'highlight', 'h')),
  note: () => (art() || book()) && key(bound(art() ? 'article' : 'book', 'note', 'n')),
  bookmark: () => book() && press('[data-bk="bookmark"]'),
  // In the manga reader, Android's next/prev are its volume keys: the reader's own event, so its
  // "Volume keys: turn pages / inverted / off" setting holds; the Mac's menu items turn the page.
  next: () => manga() ? (mac ? key(bound('manga', 'next', 'PageDown')) : volume(1)) : book() ? key(bound('book', 'next', 'ArrowRight')) : art() && key(bound('article', 'next', 'j')),
  prev: () => manga() ? (mac ? key(bound('manga', 'prev', 'PageUp')) : volume(-1)) : book() ? key(bound('book', 'prev', 'ArrowLeft')) : art() && key(bound('article', 'prev', 'k')),
  keys: () => (art() || book()) && key('?'),
  paper: () => { closeAll(); return act('paper'); },
  add: () => { closeAll(); return act('add'); },
  nextdoc: () => art() && !!$('[data-ract="nextdoc"]:not([disabled])') && press('[data-ract="nextdoc"]'),
  prevdoc: () => art() && !!$('[data-ract="prevdoc"]:not([disabled])') && press('[data-ract="prevdoc"]'),
  star: () => art() ? press('[data-dact="star"]') : ['library', 'feed'].includes(view()) && key(bound('list', 'star', 'f')),
  // an article, or the selected row of a list (or the rows picked with x)
  delete: () => (art() || list()) && key(bound(art() ? 'article' : 'list', 'delete', 'd')),
  undo: () => (art() || list()) && key(bound(art() ? 'article' : 'list', 'undo', 'z')),
  tag: () => (art() || list()) && key(bound(art() ? 'article' : 'list', 'tag', 't')),
  feedback: () => { closeAll(); const F = C() && C().Feedback; if (F) F.open(); return !!F; },
  sidebar: () => mac && toggleSide(),
  // read-aloud's own buttons, for the lock screen, the headphones and the menus
  'listen:play': () => listenBtn('Play'),
  'listen:pause': () => listenBtn('Pause'),
  'listen:next': () => press('[data-tts="next"], [data-bt="next"]'),
  'listen:prev': () => press('[data-tts="prev"], [data-bt="prev"]'),
  'listen:stop': () => press('[data-tts="close"], [data-bt="stop"]'),
  export: () => {
    closeAll();
    if (view() !== 'highlights') location.hash = 'highlights';
    waitFor('[data-act="hlexport"]', 5000).then(b => { if (b) b.click(); });
    return true;
  },
};
// Play or Pause, only if that's what the player's button would do now.
function listenBtn(want){
  const b = $('[data-tts="play"], [data-bt="play"]');
  if (!b) return false;
  if (b.getAttribute('aria-label') === want) b.click();
  return true;
}
window.dafCommand = name => {
  if (!C() || !document.body) return false;
  name = String(name || '');
  // go:<a page of Daf>: the sidebar's places, or a deeper one ("library/starred", "prefs/goals")
  if (name.startsWith('go:') && (GO.includes(name.slice(3)) || /^(library|feed|books|book|ebook|read|prefs|review|paper)\/[\w%:.\/-]+$/.test(name.slice(3)))) {
    closeAll(); location.hash = name.slice(3); return true;
  }
  const f = CMD[name];
  return f ? !!f() : false;
};
window.dafState = () => {
  const c = C(), S = c && c.S, d = S && S.data, v = view(), a = v === 'read', b = v === 'ebook';
  const h = $('#main h1');
  return {
    route: v, title: h ? h.textContent.trim() : document.title,
    signedIn: !!(S && S.user) && !$('#app').classList.contains('loggedout'),
    minutes: d ? Math.floor(d.counted) : null, goal: (d && d.goal) || 60,
    reader: a ? 'article' : b ? 'book' : null,
    listening: shown('#player'),
    starred: a && !!$('[data-dact="star"].on'),
    sidebar: !root.classList.contains('shell-noside'),
    canBack: front() || hist.length > 1,
    // the keys bound now (Preferences → Keyboard), so the Reader menu shows them: '' for none
    keys: (() => {
      const K = c && c.Keys, sc = a ? 'article' : b ? 'book' : list() ? 'list' : '', o = {};
      if (K && sc) for (const x of ['highlight', 'note', 'bookmark', 'star', 'tag', 'delete', 'next', 'prev', 'nextdoc', 'prevdoc']) o[x] = K.keys(sc, x)[0] || '';
      return o;
    })(),
    can: {
      toc: b ? !!$('[data-bk="toc"]') : a && !!$('.rvgrid'),
      panel: b ? !!$('[data-bk="panel"]') : a && !!$('[data-ract="panel"]'),
      aa: b ? !!$('[data-bk="aa"]') : a && !!$('[data-ract="aa"]'),
      listen: b ? !!$('[data-bk="listen"]') : a && !!$('[data-ract="listen"]'),
      highlight: a || b, note: a || b, next: a || b, prev: a || b,
      bookmark: b && !!$('[data-bk="bookmark"]'),
      nextdoc: a && !!$('[data-ract="nextdoc"]:not([disabled])'),
      prevdoc: a && !!$('[data-ract="prevdoc"]:not([disabled])'),
      star: a ? !!$('[data-dact="star"]') : v === 'library',
      delete: a || list(), undo: a || list(), tag: a || list(),
      export: !!(S && S.user),
    },
  };
};

/* ---------- Android: window.dafShell over the app's message port ---------- */
// The Mac defines dafShell before the page runs. Android hands the page a message port
// after each load (Shell.java); calls made before it arrives wait for it. Only a port
// from the app itself counts: its message has no source window, where a frame's would.
if (!mac && !window.dafShell) {
  let port = null, seq = 0;
  const waiting = new Map(), queue = [];
  const send = m => { if (port) port.postMessage(JSON.stringify(m)); else queue.push(m); };
  window.addEventListener('message', e => {
    if (e.data !== 'daf-shell' || e.source !== null || !e.ports || !e.ports[0]) return;
    port = e.ports[0];
    port.onmessage = m => {
      let r; try { r = JSON.parse(m.data); } catch (err) { return; }
      const w = waiting.get(r.id); if (!w) return;
      waiting.delete(r.id);
      if (r.ok) w[0](r.value); else w[1](new Error(r.error || 'The app said no'));
    };
    queue.splice(0).forEach(send);
  });
  const call = (op, args) => new Promise((ok, no) => { const id = ++seq; waiting.set(id, [ok, no]); send({ id, op, args: args || {} }); });
  const caps = ['share', 'download', 'openExternal', 'haptic', 'media', 'offline', 'screen', 'alerts', 'bars', 'reading'];
  const s = v => v == null ? '' : String(v);
  window.dafShell = Object.freeze({
    platform: 'android', version: ua[1],
    haptic: kind => call('haptic', { kind: s(kind) }),
    media: a => call('media', { state: s(a && a.state), title: s(a && a.title), sub: s(a && a.sub) }),
    can: op => caps.includes(op),
    share: a => call('share', { text: s(a && a.text), url: s(a && a.url), png: s(a && a.png), name: s(a && a.name) }),
    download: a => call('download', typeof a === 'string' ? { url: a } : { name: s(a && a.name), mime: s(a && a.mime), base64: s(a && a.base64) }),
    openExternal: u => call('openExternal', { url: s(u) }),
    // notifications for new posts in the feeds set to notify: asks once, then the app looks for them
    alerts: () => call('alerts', {}),
    // the whole screen and kept on, for the manga reader
    screen: a => call('screen', { immersive: !!(a && a.immersive), awake: !!(a && a.awake) }),
    // the status and navigation bars behind the theme's background: {bg: '#rrggbb', dark}
    bars: a => call('bars', { bg: s(a && a.bg), dark: !!(a && a.dark) }),
    // what a reader wants from the phone: {volumeKeys (they turn pages), ownMenu (Daf's bar answers a selection)}
    reading: a => call('reading', { volumeKeys: !!(a && a.volumeKeys), ownMenu: !!(a && a.ownMenu) }),
    // books on the phone: {op: 'list' | 'has' | 'keep' | 'sync', id?, on?}
    // and manga volumes: {op: 'manga', id, size (the long side this screen's reader asks for), on}
    offline: a => call('offline', { op: s(a && a.op) || 'list', id: s(a && a.id), on: !(a && a.on === false), size: +(a && a.size) || 0 }),
  });
}

/* ---------- the shell's share sheet, behind the page's own Share buttons ---------- */
// hl.js's Share as image asks navigator.share for a PNG; a WebView's own is no help.
if (can('share')) {
  const one = d => d && d.files && d.files.length === 1 && d.files[0].type === 'image/png';
  Object.defineProperty(navigator, 'canShare', { configurable: true, value: d => !!d && (one(d) || ((!d.files || !d.files.length) && !!(d.url || d.text))) });
  Object.defineProperty(navigator, 'share', { configurable: true, value: async d => {
    d = d || {};
    const png = one(d) ? await b64(d.files[0]) : undefined;
    const ok = await shell().share({ text: d.text, url: d.url, png, name: png ? d.files[0].name : undefined });
    if (!ok) throw new DOMException('Share canceled', 'AbortError');
  } });
}

/* ---------- Android: a tap felt in the hand, as native apps answer ---------- */
// Keep in the review confirms, Less often and Never again reject; a tab or a highlight ticks.
if (!mac) document.addEventListener('click', e => {
  if (!can('haptic') || !e.target.closest) return;
  const t = e.target.closest('[data-act="rkeep"], [data-act="rless"], [data-act="rnever"], .mobbar .mb, #selbar [data-hb]');
  if (!t) return;
  const kind = t.dataset.act === 'rkeep' ? 'confirm' : (t.dataset.act === 'rless' || t.dataset.act === 'rnever') ? 'reject' : 'tick';
  shell().haptic(kind).catch(() => {});
}, true);

/* ---------- Android: the manga reader takes the whole screen ---------- */
// While a manga is open (#mread) the app hides the status and navigation bars (a swipe from the edge
// shows them for a moment) and keeps the screen on; the reader turns pages by touch on its own.
if (!mac) {
  let was = null;
  const look = () => {
    const on = view() === 'mread';
    if (on === was || !can('screen')) return;
    was = on;
    shell().screen({ immersive: on, awake: on }).catch(() => { was = null; });
  };
  const watch = () => { new MutationObserver(look).observe(document.body, { attributes: true, attributeFilter: ['data-view'] }); look(); };
  if (document.body) watch(); else document.addEventListener('DOMContentLoaded', watch);
}

/* ---------- Android: the status and navigation bars in the theme's colours ---------- */
// themes.js says when the theme changes ('daf-theme'); at load the page's own --bg says. Any CSS
// colour goes, so it's drawn on a canvas and read back as #rrggbb.
if (!mac) {
  const hex = c => {
    try {
      const x = document.createElement('canvas').getContext('2d');
      x.fillStyle = c; x.fillRect(0, 0, 1, 1);
      return '#' + [...x.getImageData(0, 0, 1, 1).data.slice(0, 3)].map(v => v.toString(16).padStart(2, '0')).join('');
    } catch (e) { return ''; }
  };
  let said = '';
  const paint = (bg, dark) => {
    const now = bg && hex(bg) + (dark ? ' dark' : '');
    if (!now || now === said || !can('bars')) return;
    said = now;
    shell().bars({ bg: now.split(' ')[0], dark: !!dark }).catch(() => { said = ''; });
  };
  window.addEventListener('daf-theme', e => paint(e.detail && e.detail.bg, e.detail && e.detail.dark));
  const first = () => paint(getComputedStyle(root).getPropertyValue('--bg').trim(), root.dataset.mode === 'dark');
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', first); else first();
}

/* ---------- Android: the volume keys and the text menu, in a reader ---------- */
// volumeKeys: a book's come from Preferences → Reader → "Volume buttons turn pages" (this device,
// off unless switched on), a manga's from the manga reader's own Volume keys. The app still leaves
// them to the volume while anything plays. ownMenu: an article or a book is open and nothing
// editable has focus, so Daf's own bar answers a selection and the app keeps Android's text menu
// empty (note boxes keep Paste).
if (!mac) {
  let said = '';
  const tell = () => {
    if (!can('reading') || !document.body) return;
    const v = view(), ae = document.activeElement, c = C();
    const editing = !!ae && (ae.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(ae.tagName));
    const book = (() => { try { return localStorage.getItem('daf.volumeKeys') === 'true'; } catch (e) { return false; } })();
    const now = { volumeKeys: v === 'mread' ? !!(c && c.Manga && c.Manga.volumeKeys && c.Manga.volumeKeys()) : v === 'ebook' && book,
      ownMenu: (v === 'read' || v === 'ebook') && !editing };
    const k = JSON.stringify(now);
    if (k === said) return;
    said = k;
    shell().reading(now).catch(() => { said = ''; });
  };
  const soon = () => setTimeout(tell, 0);
  window.addEventListener('daf-reading', soon);
  window.addEventListener('hashchange', soon);
  document.addEventListener('focusin', soon);
  document.addEventListener('focusout', soon);
  const watch = () => { new MutationObserver(soon).observe(document.body, { attributes: true, attributeFilter: ['data-view'] }); tell(); };
  if (document.body) watch(); else document.addEventListener('DOMContentLoaded', watch);
}

/* ---------- Android: read-aloud with the screen off ---------- */
// What the page's player is doing goes to the app (Listen.java), which keeps it playing behind
// the lock screen and shows its controls there; they press the page's own buttons.
if (!mac) {
  let said = '', soon = 0;
  const tell = () => {
    clearTimeout(soon);
    soon = setTimeout(() => {
      if (!can('media') || !document.body) return;
      const ap = $('#player:not([hidden])'), bp = $('#bplayer'), btn = $('[data-tts="play"], [data-bt="play"]');
      const state = !(ap || bp) ? 'stopped' : btn && btn.getAttribute('aria-label') === 'Pause' ? 'playing' : 'paused';
      const title = ap ? (($('#player .pt b') || {}).textContent || '') : ((window.dafState && dafState().title) || 'Daf');
      const sub = ap ? (($('#player .pt .mute') || {}).textContent || '') : 'Read aloud by Kokoro';
      const now = JSON.stringify({ state, title, sub });
      if (now === said || (state === 'stopped' && !said)) return;
      said = state === 'stopped' ? '' : now;
      shell().media({ state, title, sub }).catch(() => {});
    }, 250);
  };
  const watch = () => new MutationObserver(tell).observe(document.body, { subtree: true, childList: true, attributes: true, attributeFilter: ['hidden', 'aria-label'] });
  if (document.body) watch(); else document.addEventListener('DOMContentLoaded', watch);
}

/* ---------- Android: blob downloads, which its WebView can't save ---------- */
if (!mac) document.addEventListener('click', async e => {
  const a = e.target.closest && e.target.closest('a[download][href^="blob:"]');
  if (!a || !can('download')) return;
  e.preventDefault();
  const blob = await fetch(a.href).then(r => r.blob());
  shell().download({ name: a.getAttribute('download') || 'Daf', mime: blob.type, base64: await b64(blob) });
}, true);

/* ---------- the Mac: the empty part of a top bar moves the window ---------- */
if (mac) {
  const post = m => { try { window.webkit.messageHandlers.dafWindow.postMessage(m); } catch (e) {} };
  const CONTROL = 'button, a, input, select, textarea, [contenteditable], [role=button], [role=radio], [role=tab], label, kbd, .seg, .tabs, .ring';
  // The manga reader covers the whole window and takes every press for its pages: there the window
  // moves from the empty part of the reader's own top bar, or, with its bars away, from the top
  // 28 points, where a title bar would be. Those presses are the window's, not the reader's (no
  // page turn, no zoom of the page on a double click).
  const readerBar = e => view() === 'mread' && !!e.target && !!e.target.closest && !e.target.closest(CONTROL) && !e.target.closest('.msheet') &&
    (!!e.target.closest('.mtop') || e.clientY < 28);
  ['pointerdown', 'pointerup', 'click', 'dblclick'].forEach(type => window.addEventListener(type, e => {
    if (e.button > 0 || !readerBar(e)) return;
    e.stopPropagation();
  }, true));
  window.addEventListener('mousedown', e => {
    if (e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
    const t = e.target;
    if (!t || !t.closest || t.closest(CONTROL)) return;
    if (!(t.closest('.top, .brand') || (t.closest('.side') && e.clientY < 56) || readerBar(e))) return;
    post(e.detail >= 2 ? 'zoom' : 'drag');
  }, true);
}
})();
