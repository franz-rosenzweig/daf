// Daf's service worker: Daf is kept on this device and answers from here first.
// - The page and its files: this version's set, fetched whole when the version changes (app.py serves
//   this file with VERSION, a fingerprint of everything in web/, and FILES, the page's fingerprinted
//   scripts and styles; webcache.py). The page itself comes from here at once and is checked behind.
// - Pictures (covers, manga thumbnails and pages, feed icons) and book files: from the device once
//   they've been fetched, kept up to a size. A book's file is asked for again only when the page asks
//   for it fresh (book.js, when its size has changed).
// - The pages' data: from the network, and kept for when there is none. The pages draw the kept copy
//   first themselves and catch up (app.js swr).
const VERSION = '__VERSION__';
const SHELL = 'daf-shell-' + VERSION, DATA = 'daf-data-v1', IMG = 'daf-img-v1', BOOKS = 'daf-books-v1';
const FILES = ["__FILES__"];
const LIMIT = { [IMG]: 3000, [BOOKS]: 60 };
// API reads worth having offline. A single doc is stored without its query, so a prefetch
// (?prefetch=1) and a normal open share one copy.
const OFFLINE_API = /^\/api\/(me|settings|today|review|goals|feed\/sources|books|highlights|torah|recovery|stats|home|year\/\d+|docs|docs\/counts|docs\/[^/]+|ebooks|ebooks\/[^/]+|manga|manga\/prefs|manga\/series\/[^/]+|manga\/books\/[^/]+)$/;
const PICTURE = /^\/api\/(cover\/[^/]+|thumb\/[0-9a-f]+\.jpg|manga\/thumb\/[^/]+\/[^/]+|manga\/books\/[^/]+\/pages\/\d+|feed\/icon\/[^/]+)$/;
const BOOK_FILE = /^\/api\/ebooks\/[^/]+\/file$/;
const MANGA_PAGE = /^\/api\/manga\/books\/[^/]+\/pages\/\d+$/;
// Daf for Android keeps books and downloaded volumes itself and answers for them before the network
// (Offline.intercept), so here they pass through instead of being kept twice.
const ANDROID_KEEPS = / \(Android shell\)/.test(self.navigator.userAgent || '');
// A list (the Library, the Feed, Highlights) is also kept under what it is, without its order and
// filters, so offline it opens even when this device sorts it another way than when it was kept.
function listKey(url){
  if (url.pathname !== '/api/docs' && url.pathname !== '/api/highlights') return null;
  const k = new URL(url.origin + url.pathname);
  for (const n of ['where', 'tab', 'kind', 'cat', 'feed']) if (url.searchParams.has(n)) k.searchParams.set(n, url.searchParams.get(n));
  k.searchParams.set('_any', '1');
  return k.toString();
}
self.addEventListener('install', e => {
  // The whole set at once, past the browser's own cache; a file that won't come doesn't stop the rest.
  e.waitUntil(caches.open(SHELL).then(c => Promise.all(FILES.map(f => fetch(f, { cache: 'no-cache', credentials: 'same-origin' })
    .then(r => r.ok ? c.put(f, r) : null).catch(() => null)))).then(() => self.skipWaiting()));
});
self.addEventListener('activate', e => {
  e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => ![SHELL, DATA, IMG, BOOKS].includes(k)).map(k => caches.delete(k)))).then(() => self.clients.claim()));
});
// Kept to a size: the oldest go first (a cache lists what it holds in the order it was put).
let puts = 0;
async function trim(name){
  const c = await caches.open(name), keys = await c.keys(), over = keys.length - LIMIT[name];
  for (let i = 0; i < over; i++) await c.delete(keys[i]);
}
async function keep(name, req, r){
  const c = await caches.open(name); await c.put(req, r);
  if (LIMIT[name] && ++puts % 25 === 0) trim(name).catch(() => {});
}
async function deviceFirst(name, req){
  const c = await caches.open(name), m = await c.match(req);
  if (m) return m;
  const r = await fetch(req);
  if (r.ok && r.status === 200) keep(name, req, r.clone()).catch(() => {});
  return r;
}
self.addEventListener('fetch', e => {
  const req = e.request, url = new URL(req.url);
  if (req.method !== 'GET' || url.origin !== location.origin) return;
  if (url.pathname.startsWith('/api/')) {
    if (ANDROID_KEEPS && (BOOK_FILE.test(url.pathname) || MANGA_PAGE.test(url.pathname))) return;
    if (PICTURE.test(url.pathname)) { e.respondWith(deviceFirst(IMG, req)); return; }
    if (BOOK_FILE.test(url.pathname)) {
      if (req.cache === 'reload' || req.cache === 'no-cache') {
        e.respondWith(fetch(req).then(r => { if (r.ok) keep(BOOKS, url.origin + url.pathname, r.clone()).catch(() => {}); return r; }));
      } else e.respondWith(caches.open(BOOKS).then(c => c.match(url.origin + url.pathname)).then(m => m || fetch(req).then(r => {
        if (r.ok) keep(BOOKS, url.origin + url.pathname, r.clone()).catch(() => {}); return r; })));
      return;
    }
    if (!OFFLINE_API.test(url.pathname)) return;
    const single = /^\/api\/docs\/[^/]+$/.test(url.pathname) && url.pathname !== '/api/docs/counts';
    const key = single ? url.origin + url.pathname : req.url, any = listKey(url);
    e.respondWith(fetch(req).then(r => {
      if (r.ok) { const copy = r.clone(), copy2 = any && r.clone(); caches.open(DATA).then(c => { c.put(key, copy); if (any) c.put(any, copy2); }); }
      return r;
    }).catch(() => caches.open(DATA).then(c => c.match(key).then(m => m || (any && c.match(any)))).then(m => m || Response.error())));
    return;
  }
  if (url.pathname.startsWith('/subscriptions/') || url.pathname === '/share' || url.pathname === '/sw.js' || url.pathname === '/anilist') return;
  // The page: this version's copy at once, and the server's behind it for next time.
  if (req.mode === 'navigate' || url.pathname === '/' || url.pathname === '/index.html') {
    const fresh = fetch('/', { cache: 'no-cache', credentials: 'same-origin' }).then(r => { if (r.ok) caches.open(SHELL).then(c => c.put('/', r.clone())); return r; });
    e.respondWith(caches.open(SHELL).then(c => c.match('/')).then(m => m || fresh).catch(() => fresh));
    e.waitUntil(fresh.catch(() => {}));
    return;
  }
  // Everything else of the page's (scripts, styles, fonts, the readers' libraries): this version's.
  e.respondWith(deviceFirst(SHELL, req).catch(() => caches.match(req, { ignoreSearch: true }).then(m => m || Response.error())));
});
