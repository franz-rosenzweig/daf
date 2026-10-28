/* Daf web app: Today, Review, Highlights, Books, paper minutes, sources, preferences. */
(function(){
'use strict';
const $ = (s, r) => (r || document).querySelector(s);
const $$ = (s, r) => Array.from((r || document).querySelectorAll(s));
const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const MONTHS = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
const DAYS = ['Sunday','Monday','Tuesday','Wednesday','Thursday','Friday','Saturday'];
const parseDay = s => { const [y, m, d] = s.split('-').map(Number); return new Date(y, m - 1, d); };
const isoOf = d => d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0');
const longDate = s => { const d = parseDay(s); return DAYS[d.getDay()] + ', ' + ['January','February','March','April','May','June','July','August','September','October','November','December'][d.getMonth()] + ' ' + d.getDate(); };
const shortDate = s => { const d = parseDay(s); return MONTHS[d.getMonth()] + ' ' + d.getDate(); };
const epochDate = t => { if (!t) return ''; const d = new Date(t * 1000); return MONTHS[d.getMonth()] + ' ' + d.getDate() + (d.getFullYear() !== new Date().getFullYear() ? ', ' + d.getFullYear() : ''); };
const ago = ts => { if (!ts) return 'never'; const d = Date.now() / 1000 - ts; if (d < 3600) return Math.max(1, Math.round(d / 60)) + ' min ago'; if (d < 172800) return Math.round(d / 3600) + ' h ago'; return Math.round(d / 86400) + ' days ago'; };
const shortTitle = t => String(t || '').split(/:\s| \(/)[0];
const lsGet = (k, d) => { try { const v = localStorage.getItem('daf.' + k); return v == null ? d : JSON.parse(v); } catch(e){ return d; } };
const lsSet = (k, v) => { try { localStorage.setItem('daf.' + k, JSON.stringify(v)); } catch(e){} };

const I = {
  camera:'<svg width="18" height="18" viewBox="0 0 20 20" aria-hidden="true"><path d="M3 6.5h3l1.5-2h5l1.5 2h3v9H3z" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/><circle cx="10" cy="10.5" r="3" fill="none" stroke="currentColor" stroke-width="1.6"/></svg>',
  torah:'<svg width="18" height="18" viewBox="0 0 20 20" aria-hidden="true"><path d="M4 3.5v13M16 3.5v13" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/><path d="M6 5h8v10H6z" fill="none" stroke="currentColor" stroke-width="1.4"/><path d="M8 8h4M8 10.5h4M8 13h2.5" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/></svg>',
  today:'<svg width="18" height="18" viewBox="0 0 20 20" aria-hidden="true"><circle cx="10" cy="10" r="7.3" fill="none" stroke="currentColor" stroke-width="2"/><circle cx="10" cy="10" r="2.3" fill="currentColor"/></svg>',
  review:'<svg width="18" height="18" viewBox="0 0 20 20" aria-hidden="true"><path d="M4 4.5h12v9H8l-4 3z" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"/></svg>',
  hl:'<svg width="18" height="18" viewBox="0 0 20 20" aria-hidden="true"><path d="M11.5 3.5l5 5-7 7H4.5v-5z" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/><path d="M3 17.5h14" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg>',
  books:'<svg width="18" height="18" viewBox="0 0 20 20" aria-hidden="true"><path d="M4 4.5c2-1 4-1 6 .5v11c-2-1.5-4-1.5-6-.5zM16 4.5c-2-1-4-1-6 .5v11c2-1.5 4-1.5 6-.5z" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/></svg>',
  sources:'<svg width="18" height="18" viewBox="0 0 20 20" aria-hidden="true"><circle cx="5" cy="5" r="2" fill="none" stroke="currentColor" stroke-width="1.7"/><circle cx="15" cy="5" r="2" fill="none" stroke="currentColor" stroke-width="1.7"/><circle cx="10" cy="15" r="2" fill="none" stroke="currentColor" stroke-width="1.7"/><path d="M6.4 6.6l2.4 6.6M13.6 6.6l-2.4 6.6" stroke="currentColor" stroke-width="1.7"/></svg>',
  prefs:'<svg width="18" height="18" viewBox="0 0 20 20" aria-hidden="true"><circle cx="10" cy="10" r="2.6" fill="none" stroke="currentColor" stroke-width="1.6"/><path d="M10 2.5v2.2M10 15.3v2.2M2.5 10h2.2M15.3 10h2.2M4.7 4.7l1.6 1.6M13.7 13.7l1.6 1.6M4.7 15.3l1.6-1.6M13.7 6.3l1.6-1.6" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg>',
  paper:'<svg width="18" height="18" viewBox="0 0 20 20" aria-hidden="true"><path d="M5 3.5h7l3 3v10H5z" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/><path d="M10 9v5M7.5 11.5h5" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg>',
  moon:'<svg width="18" height="18" viewBox="0 0 20 20" aria-hidden="true"><path d="M15 12.5A6.5 6.5 0 0 1 7.5 4a6.5 6.5 0 1 0 8.6 7.6c-.35.33-.72.63-1.1.9z" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/></svg>',
  sync:'<svg width="16" height="16" viewBox="0 0 20 20" aria-hidden="true"><path d="M16 10a6 6 0 0 1-10.4 4.1M4 10a6 6 0 0 1 10.4-4.1M14.5 2.5v3.5H11M5.5 17.5V14H9" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  back:'<svg width="16" height="16" viewBox="0 0 20 20" aria-hidden="true"><path d="M12 4l-6 6 6 6" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>'
};

const S = { route: [], data: null, y29: null, timer: null, rev: null, revIdx: 0, revNote: false, hlq: '', hlPrivate: false, booksAll: false,
  hlSource: '', hlColor: '', hlTag: '', hlFav: false, hlSort: 'recent', hlOpen: new Set() };
const route = () => (location.hash || '#today').slice(1).split('/');

async function api(path, opts){
  const o = Object.assign({ headers:{ 'Content-Type':'application/json' }, credentials:'same-origin' }, opts || {});
  const late = o.method && o.method !== 'GET' && OUTBOX.test(path);
  // Each write that can wait carries its own id (X-Daf-Op): sent again after an answer that never came, the server answers it once.
  if (late) o.headers = Object.assign({}, o.headers, { 'X-Daf-Op': o.headers['X-Daf-Op'] || opId() });
  if (late && outbox.get().length) { const a = outbox.add(path, o); outbox.flush(); return a; }   // after what's waiting, in order
  if (late && !navigator.onLine) return outbox.add(path, o);                                     // no network: straight to the outbox
  // A connection that's there but doesn't answer (a weak signal) holds a write at most six seconds;
  // then it waits in the outbox, and its id keeps it from counting twice if the first one got through.
  let r, timer;
  if (late && !o.signal) { const ctl = new AbortController(); o.signal = ctl.signal; timer = setTimeout(() => ctl.abort(), 6000); }
  try { r = await fetch(path, o); clearTimeout(timer); }
  catch(e){
    clearTimeout(timer);
    if (late) return outbox.add(path, o);
    if (!navigator.onLine || e instanceof TypeError) throw new Error('No connection: this needs Daf on the server. Try again when you’re back online.');
    throw e;
  }
  if (r.status === 401 && path !== '/api/login') { renderLogin(); throw new Error('signed out'); }
  if (!r.ok) { let m = r.statusText; try { m = (await r.json()).detail || m; } catch(e){} noteErr((o.method || 'GET') + ' ' + path.split('?')[0] + ' → ' + r.status + ' ' + m); throw new Error(m); }
  return r.json();
}
// What went wrong lately (failed calls, script errors), for Send feedback (feedback.js).
const ERRS = [];
function noteErr(x){ ERRS.push(new Date().toISOString().slice(11, 19) + ' ' + String(x).slice(0, 300)); if (ERRS.length > 20) ERRS.shift(); }
window.addEventListener('error', e => noteErr((e.message || 'error') + (e.filename ? ' at ' + e.filename.split('/').pop() + ':' + e.lineno : '')));
window.addEventListener('unhandledrejection', e => noteErr('unhandled: ' + ((e.reason && e.reason.message) || e.reason)));
/* ---------- writes made offline ---------- */
// Without a signal (a book on a plane), a book's place, its highlights and their notes, colours and
// tags, bookmarks, and a manga's page and reading time wait here, in order, and go when the network is back, with the time they were
// made. Highlight and bookmark ids are the server's own (a hash of the book and the place), so what's
// made offline keeps its id and can be changed again before it's sent.
// Articles too: their highlights (the id is the server's own hash, as for books), status, progress,
// star, note, tags and title; reading time; the daily review and cards; paper minutes; reading notes.
const OUTBOX = /^\/api\/(ebooks\/[^/?]+\/(position|highlights|bookmarks(\/[^/?]+)?|ink)|highlights\/[^/?]+(\/(color|note|fav|tags|restore))?|manga\/books\/[^/?]+\/progress|manga\/beat|docs\/[^/?]+\/(highlights|status|progress|star|note|tags|meta|ink)|docs\/bulk|read\/beat|review\/[^/?]+|cards\/[^/?]+\/grade|paper|notes|feedback|tips|books\/[^/?]+\/review)$/;
// The day of a moment in Daf's own time zone (home_tz), as the server counts it, whatever this device is set to.
const dayIn = at => { const tz = (S.data && S.data.settings && S.data.settings.home_tz) || (S.settings && S.settings.home_tz);
  try { return new Intl.DateTimeFormat('en-CA', { timeZone: tz || undefined, year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date(at * 1000)); } catch(e){ return isoOf(new Date(at * 1000)); } };
const opId = () => { const b = new Uint8Array(12); crypto.getRandomValues(b); return 'op' + Array.from(b, x => x.toString(16).padStart(2, '0')).join(''); };
const outbox = {
  get(){ try { return JSON.parse(localStorage.getItem('daf.outbox') || '[]'); } catch(e){ return []; } },
  set(q){ try { localStorage.setItem('daf.outbox', JSON.stringify(q.slice(-1000))); } catch(e){} },
  add(path, o){
    const q = outbox.get(), body = o.body ? JSON.parse(o.body) : null;
    const item = { path, method: o.method, body, at: Math.floor(Date.now() / 1000), op: (o.headers && o.headers['X-Daf-Op']) || opId() };
    if (path === '/api/paper' && body && !body.date && S.data) body.date = S.data.today;     // paper minutes are for the day they were logged
    if (/\/position$/.test(path)) {     // only the newest place counts, but the pages seen add up
      const old = q.find(x => x.path === path);
      if (old) { if (item.body) item.body.pages = [...new Set([...(old.body && old.body.pages || []), ...(item.body.pages || [])])]; q.splice(q.indexOf(old), 1); }
    }
    q.push(item); outbox.set(q);
    if (!outbox.told && !navigator.onLine) { outbox.told = true; toast('Kept on this device until it’s back online'); }
    outbox.changed();
    const m = /^\/api\/ebooks\/([^/]+)\/(highlights|bookmarks)$/.exec(path);
    if (m && o.method === 'POST' && body && body.cfi) {
      const h = sha1(decodeURIComponent(m[1]) + '|' + String(body.cfi).slice(0, 2000));
      return { id: m[2] === 'highlights' ? 'e' + h.slice(0, 16) : 'm' + h.slice(0, 15), queued: true };
    }
    // What the pages would have had back, so they carry on as if it had gone.
    const d = /^\/api\/docs\/([^/]+)\/highlights$/.exec(path);
    if (d && body) {   // reader.add_highlight's id: the doc, the block and start, the words
      const nb = v => v == null ? 'None' : String(v);
      return { id: 'd' + sha1(decodeURIComponent(d[1]) + '|' + nb(body.b) + '|' + nb(body.s) + '|' + String(body.text || '').trim()).slice(0, 16), queued: true };
    }
    if (path === '/api/docs/bulk') return { done: (body && body.ids) || [], failed: [], queued: true };
    if (/\/meta$/.test(path) && body) return { title: body.title, author: body.author, queued: true };
    if (path === '/api/paper') return { date: (body && body.date) || (S.data && S.data.today), queued: true };
    if (path === '/api/notes') return { vault: 'later', queued: true };
    return { ok: true, queued: true };
  },
  // Minutes read on this device that haven't reached the server: Today counts them.
  pending(day){
    let sec = 0; const by = {};
    for (const x of outbox.get()) {
      if (!/\/(read|manga)\/beat$/.test(x.path) || !x.body) continue;
      const at = x.body.at || x.at;
      if (day && dayIn(at) !== day) continue;
      const src = /manga/.test(x.path) ? 'manga' : x.body.book_id ? 'ebook' : 'article';
      sec += x.body.seconds || 0; by[src] = (by[src] || 0) + (x.body.seconds || 0);
    }
    return { min: sec / 60, by: Object.fromEntries(Object.entries(by).map(([k, v]) => [k, v / 60])) };
  },
  changed(){ clearTimeout(outbox.drawT); outbox.drawT = setTimeout(drawSyncPill, 50); },
  // Sends what waits, in order. It reads the stored queue afresh for each one and takes out only
  // what it sent (by its op id), so a write queued while it works (still reading, still
  // highlighting) stays in the queue instead of being written over by an old copy.
  async flush(){
    if (outbox.busy || !navigator.onLine || !outbox.get().length) return;
    outbox.busy = true; let sent = 0, stuck = 0;
    const drop = x => outbox.set(outbox.get().filter(y => y.op !== x.op));
    try {
      for (;;) {
        const x = outbox.get()[0]; if (!x) break; let r;
        try { r = await fetch(x.path, { method: x.method, credentials: 'same-origin', headers: Object.assign({ 'Content-Type': 'application/json' }, x.op ? { 'X-Daf-Op': x.op } : {}),
                                        body: x.body ? JSON.stringify(Object.assign({}, x.body, { at: x.body.at || x.at })) : undefined }); }
        catch(e){ break; }                                  // still offline
        if (r.status === 401 || r.status === 503 || r.status === 502) break;   // signed out, or Daf or a service is down: later
        if (r.status >= 500) {
          // One Daf keeps failing on mustn't hold up everything after it: after five tries it's
          // set aside (daf.outbox.stuck) and the rest go on.
          const q = outbox.get(), it = q.find(y => y.op === x.op); if (!it) continue;
          it.tries = (it.tries || 0) + 1; noteErr('outbox ' + x.method + ' ' + x.path + ' → ' + r.status + ' (try ' + it.tries + ')');
          if (it.tries < 5) { outbox.set(q); break; }
          try { const s = JSON.parse(localStorage.getItem('daf.outbox.stuck') || '[]'); s.push(it); localStorage.setItem('daf.outbox.stuck', JSON.stringify(s.slice(-100))); } catch(e){}
          drop(x); stuck++; continue;
        }
        drop(x); sent++;                                    // sent, or refused for good
      }
    } finally { outbox.busy = false; outbox.changed(); }
    if (stuck) toast(stuck === 1 ? 'One change Daf kept refusing was set aside; Send feedback includes it' : stuck + ' changes Daf kept refusing were set aside');
    if (sent && !outbox.get().length) { outbox.told = false; toast('Sent what you did offline'); if (S.route && S.route[0] === 'today') load(); }
  }
};
window.addEventListener('online', () => { outbox.flush(); outbox.changed(); });
window.addEventListener('offline', () => outbox.changed());
// Keep the next days readable with no network, in a browser or the Mac app (the service worker
// keeps what's fetched here): what /api/offline/plan names, every six hours, on a connection that
// doesn't ask to save data. Daf for Android keeps it natively instead.
async function keepOffline(force){
  if (!navigator.onLine || !('serviceWorker' in navigator) || (navigator.connection && navigator.connection.saveData)) return;
  if (window.dafShell && dafShell.can && dafShell.can('offline')) return;
  let last = 0; try { last = +localStorage.getItem('daf.keptAt') || 0; } catch(e){}
  if (!force && Date.now() - last < 6 * 3600e3) return;
  let plan; try { plan = await api('/api/offline/plan'); } catch(e){ return; }
  const urls = plan.urls.concat(plan.docs.map(id => '/api/docs/' + encodeURIComponent(id) + '?prefetch=1'), plan.ebooks.map(id => '/api/ebooks/' + encodeURIComponent(id) + '/file'), plan.images);
  let i = 0;
  const one = async () => { while (i < urls.length && navigator.onLine) { const u = urls[i++]; try { await fetch(u, { credentials: 'same-origin' }); } catch(e){} } };
  await Promise.all([one(), one(), one()]);
  try { localStorage.setItem('daf.keptAt', String(Date.now())); } catch(e){}
}
setTimeout(() => keepOffline(), 20000);
setInterval(() => keepOffline(), 3600e3);
// The menus ready before you open them: the lists and pages the offline plan names, fetched quietly a
// few seconds after Daf opens and every ten minutes while it's in front, so the first tap on each draws
// from the device (swr). Cheap: a few dozen small reads, three at a time.
async function warm(){
  if (!navigator.onLine || document.hidden || !S.user || (navigator.connection && navigator.connection.saveData)) return;
  let last = 0; try { last = +localStorage.getItem('daf.warmAt') || 0; } catch(e){}
  if (Date.now() - last < 10 * 60e3) return;
  try { localStorage.setItem('daf.warmAt', String(Date.now())); } catch(e){}
  let plan; try { plan = await api('/api/offline/plan'); } catch(e){ return; }
  const urls = plan.urls.filter(u => !/^\/api\/(fonts|ebooks\/)/.test(u)), own = !(navigator.serviceWorker && navigator.serviceWorker.controller);
  let i = 0;
  const one = async () => { while (i < urls.length && navigator.onLine) { const u = urls[i++];
    try { const d = await api(u); if (own && window.caches) (await caches.open(DATA_CACHE)).put(new URL(u, location.href).href, new Response(JSON.stringify(d), { headers: { 'Content-Type': 'application/json' } })); } catch(e){} } };
  await Promise.all([one(), one(), one()]);
}
setTimeout(warm, 4000);
setInterval(warm, 60e3);
document.addEventListener('visibilitychange', () => { if (!document.hidden) setTimeout(warm, 1500); });

// "Offline · 3 waiting": what this device holds for the server. A tap sends it now.
function drawSyncPill(){
  let el = $('#syncpill');
  const n = outbox.get().length, off = !navigator.onLine;
  if (!n && !off) { if (el) el.hidden = true; return; }
  if (!el) { el = document.createElement('button'); el.id = 'syncpill'; el.className = 'syncpill'; el.addEventListener('click', () => { outbox.flush(); toast(navigator.onLine ? 'Sending…' : 'No connection yet: it goes by itself when there is'); }); document.body.appendChild(el); }
  el.hidden = false; el.classList.toggle('off', off);
  el.textContent = (off ? 'Offline' : 'Not yet synced') + (n ? ' · ' + n + ' waiting' : '');
  el.title = n ? 'Saved on this device; it goes to the server when the connection is back' : 'No connection: what you do is kept on this device';
}
document.addEventListener('visibilitychange', () => { if (!document.hidden) outbox.flush(); });
setTimeout(() => outbox.flush(), 2500);
setInterval(() => outbox.flush(), 60000);
// SHA-1, for the ids the server would give (crypto.subtle needs https; the tailnet address isn't)
function sha1(str){
  const b = new TextEncoder().encode(str), n = ((b.length + 8) >> 6) + 1, w = new Uint32Array(n * 16);
  for (let i = 0; i < b.length; i++) w[i >> 2] |= b[i] << (24 - (i % 4) * 8);
  w[b.length >> 2] |= 0x80 << (24 - (b.length % 4) * 8); w[n * 16 - 1] = b.length * 8;
  let [h0, h1, h2, h3, h4] = [0x67452301, 0xefcdab89, 0x98badcfe, 0x10325476, 0xc3d2e1f0];
  const x = new Uint32Array(80), rol = (v, k) => (v << k) | (v >>> (32 - k));
  for (let i = 0; i < n * 16; i += 16) {
    for (let t = 0; t < 80; t++) x[t] = t < 16 ? w[i + t] : rol(x[t - 3] ^ x[t - 8] ^ x[t - 14] ^ x[t - 16], 1);
    let [a, bb, c, d, e] = [h0, h1, h2, h3, h4];
    for (let t = 0; t < 80; t++) {
      const f = t < 20 ? (bb & c) | (~bb & d) : t < 40 ? bb ^ c ^ d : t < 60 ? (bb & c) | (bb & d) | (c & d) : bb ^ c ^ d;
      const k = t < 20 ? 0x5a827999 : t < 40 ? 0x6ed9eba1 : t < 60 ? 0x8f1bbcdc : 0xca62c1d6;
      const tmp = (rol(a, 5) + f + e + k + x[t]) >>> 0; e = d; d = c; c = rol(bb, 30) >>> 0; bb = a; a = tmp;
    }
    h0 = (h0 + a) >>> 0; h1 = (h1 + bb) >>> 0; h2 = (h2 + c) >>> 0; h3 = (h3 + d) >>> 0; h4 = (h4 + e) >>> 0;
  }
  return [h0, h1, h2, h3, h4].map(v => v.toString(16).padStart(8, '0')).join('');
}
function toast(msg){ const t = $('#toast'); t.textContent = msg; t.hidden = false; clearTimeout(toast._t); toast._t = setTimeout(() => { t.hidden = true; }, 3800); }

function ring(size, stroke, minutes, goal){
  const r = (size - stroke) / 2, c = 2 * Math.PI * r, f = Math.min(1, minutes / goal);
  return '<svg class="ring" width="' + size + '" height="' + size + '" viewBox="0 0 ' + size + ' ' + size + '" role="img" aria-label="' + Math.floor(minutes) + ' of ' + goal + ' minutes">' +
    '<circle cx="' + size/2 + '" cy="' + size/2 + '" r="' + r + '" fill="none" stroke="var(--active)" stroke-width="' + stroke + '"/>' +
    '<circle cx="' + size/2 + '" cy="' + size/2 + '" r="' + r + '" fill="none" stroke="var(--accent)" stroke-width="' + stroke + '" stroke-linecap="round" stroke-dasharray="' + (f * c).toFixed(1) + ' ' + c.toFixed(1) + '" transform="rotate(-90 ' + size/2 + ' ' + size/2 + ')"/>' +
    '<text x="50%" y="50%" dy=".35em" text-anchor="middle" font-size="' + Math.round(size / 3.6) + '" font-weight="700">' + Math.floor(minutes) + '</text></svg>';
}
// Shades relative to that day's goal (with an hour a day: 60, 30, 15 and 1 minutes).
function level(m, t){ t = t || 60; return m >= t ? 'l4' : m >= t / 2 ? 'l3' : m >= t / 4 ? 'l2' : m >= 1 ? 'l1' : ''; }
const atWord = goal => window.DafCore && window.DafCore.Goals ? window.DafCore.Goals.atWord(goal) : 'at the hour';
function yearGrid(g, label){
  const lead = (g.weekday + 1) % 7;
  let cells = '';
  for (let i = 0; i < lead; i++) cells += '<i class="x"></i>';
  const start = parseDay(g.start);
  g.days.forEach((m, i) => {
    const d = new Date(start); d.setDate(start.getDate() + i);
    const cls = [level(m, g.targets && g.targets[i]), i === g.today_index ? 'today' : '', g.today_index != null && i > g.today_index ? 'future' : ''].join(' ').trim();
    cells += '<i class="' + cls + '" title="' + shortDate(isoOf(d)) + ': ' + Math.round(m) + ' min"></i>';
  });
  return '<div class="yearwrap"><div class="year" role="img" aria-label="' + esc(label) + '">' + cells + '</div></div>';
}
const legendFor = goal => '<div class="legend"><span>none</span><i style="background:var(--active)"></i><i style="background:var(--g1)"></i><i style="background:var(--g2)"></i><i style="background:var(--g3)"></i><i style="background:var(--g4)"></i><span>' + (+goal === 60 ? 'an hour or more' : 'the day’s goal or more') + '</span></div>';
const legend = legendFor(60);
function cover(b, cls){
  if (b && b.has_cover) return '<img class="' + (cls || 'cv') + '" src="/api/cover/' + encodeURIComponent(b.id) + '" alt="" loading="lazy">';
  const hue = [...String(b && b.title || '')].reduce((h, c) => (h * 31 + c.charCodeAt(0)) % 360, 7);
  return '<span class="' + (cls || 'cv') + ' tile" style="background:hsl(' + hue + ' 32% 42%)">' + esc(shortTitle(b && b.title)) + '</span>';
}
function bar(p){ return '<span class="pbar"><i style="width:' + Math.max(0, Math.min(100, p || 0)) + '%"></i></span>'; }

/* ---------- sidebar ---------- */
// The sidebar as a strip of icons (style.css, html.rail): from phone width up to 1100 (a tablet in
// portrait), and on the reading screens up to 1400 (a tablet in landscape), where the page needs the room.
const READING = new Set(['read', 'ebook', 'pdf']);
function railMode(){
  const w = window.innerWidth, v = (S.route || [])[0];
  const on = w > 780 && (w < 1100 || (w < 1400 && READING.has(v)));
  document.documentElement.classList.toggle('rail', on);
  if (!on) { const sd = $('#side'); if (sd && sd.classList.contains('open') && w > 780) sd.classList.remove('open'); }
}
window.addEventListener('resize', () => { clearTimeout(railMode.t); railMode.t = setTimeout(railMode, 120); });
function renderSide(){
  const v = S.route[0];
  const n = (key, label, icon, extra) => '<button class="nv' + (v === key || (key === 'books' && v === 'book') ? ' on' : '') + '" data-go="' + key + '">' + icon + '<span>' + label + '</span>' + (extra || '') + '</button>';
  const d = S.data;
  const mins = d ? (d.main && !(d.main.kind === 'minutes' && d.main.period === 'day') ? d.main.done + '/' + d.main.target : Math.floor(d.counted) + '/' + Math.round(d.goal || 60)) : '';
  const rv = d && d.review ? (d.review.total - d.review.done) + (d.cards_due || 0) : '';
  const mob = (key, label, icon, hash) => '<button class="mb' + (v === key || (key === 'library' && v === 'books') ? ' on' : '') + '" data-go="' + (hash || key) + '">' + icon + '<span>' + label + '</span></button>';
  const mobbar = '<div class="mobbar">' + mob('today', 'Today', I.today) + mob('review', 'Review', I.review) + mob('feed', 'Feed', '<svg width="18" height="18" viewBox="0 0 20 20" aria-hidden="true"><path d="M4.5 15.5h.01M4.5 10a5.5 5.5 0 0 1 5.5 5.5M4.5 4.5a11 11 0 0 1 11 11" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>') +
    mob('library', 'Library', I.books, 'library') + '<button class="mb' + (window.DafCore && window.DafCore.Tips && window.DafCore.Tips.unseen() ? ' hasnew' : '') + '" data-act="more"><svg width="18" height="18" viewBox="0 0 20 20" aria-hidden="true"><path d="M3.5 6h13M3.5 10h13M3.5 14h13" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg><span>More</span></button></div>';
  $('#side').innerHTML = mobbar + '<div class="navfull"><div class="brand"><button class="railbtn" data-act="rail" aria-label="Show the sidebar" title="Show the sidebar"><svg width="20" height="20" viewBox="0 0 20 20" aria-hidden="true"><path d="M3.5 6h13M3.5 10h13M3.5 14h13" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg></button><b>Daf</b></div><div class="nav">' +
    n('today', 'Today', I.today, '<span class="ct">' + mins + '</span>') +
    n('review', 'Review', I.review, '<span class="ct">' + (rv || (rv === 0 ? '✓' : '')) + '</span>') +
    n('stats', 'Stats', '<svg width="18" height="18" viewBox="0 0 20 20" aria-hidden="true"><path d="M4 16V9M8.7 16V4M13.3 16v-5M18 16H2" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>', d && d.streak && d.streak.goal ? '<span class="ct" title="Days in a row ' + atWord(d.goal) + '">' + d.streak.goal + '</span>' : '') +
    (window.DafCore && window.DafCore.navSearch ? window.DafCore.navSearch() : '') + '</div>' +
    (window.DafCore && window.DafCore.navExtra ? window.DafCore.navExtra(v, n) : '<div class="nav">' + n('highlights', 'Highlights', I.hl) + n('books', 'Books', I.books) + '</div>') +
    '<div class="nav" style="margin-top:8px">' +
    '<button class="nv" data-act="paper">' + I.paper + '<span>Log paper</span></button>' +
    n('paper', 'Paper pages', I.camera) +
    n('sources', 'Sources', I.sources) + n('prefs', 'Preferences', I.prefs) + (window.DafCore && window.DafCore.Tips ? window.DafCore.Tips.navItem() : '') + '</div>' +
    '<div class="sidefoot">Year 30 began October 9, 2026. One hour a day.</div></div>';
  // On a tablet the sidebar is a strip of icons: each one says what it is.
  $$('#side .navfull .nv').forEach(b => { const t = b.querySelector('span'); if (t && !b.title) { b.title = t.textContent.trim(); b.setAttribute('aria-label', b.title); } });
}

/* ---------- today ---------- */
function bookRow(b, extra){
  return '<a class="brow" href="#book/' + encodeURIComponent(b.id) + '">' + cover(b, 'cv sm') + '<span class="bt"><b>' + esc(shortTitle(b.title)) + '</b><span class="mute tiny">' + esc(b.author || '') + '</span>' +
    (b.progress != null ? '<span class="tiny mute">' + bar(b.progress) + ' ' + Math.round(b.progress) + '% · ' + esc(b.progress_note || '') + '</span>' : '') +
    (b.audio_note ? '<span class="tiny mute">Audiobook · ' + esc(b.audio_note) + '</span>' : '') + (extra || '') + '</span></a>';
}
function renderToday(){
  let d = S.data; if (!d) { $('#main').innerHTML = '<div class="page mute">Loading…</div>'; return; }
  // Minutes read on this device that haven't reached the server yet (offline) count already.
  const pend = d.date === d.today ? outbox.pending(d.today) : { min: 0, by: {} };
  if (pend.min > 0.1) {
    const M2 = Object.assign({}, d.minutes); let add = 0;
    for (const [k, v] of Object.entries(pend.by)) { M2[k] = (M2[k] || 0) + v; if (d.settings.count[k]) add += v; }
    d = Object.assign({}, d, { minutes: M2, counted: d.counted + add, pendingMin: add });
  }
  const isToday = d.date === d.today, set = d.settings, M = d.minutes;
  const dayN = d.year30.today_index != null ? d.year30.today_index + 1 : null;
  const srcRows = ['kindle','ebook','manga','audio','article','paper','video','podcast'].filter(k => set.count[k] || M[k] > 0)
    .map(k => '<span' + (set.count[k] ? '' : ' class="off"') + '>' + esc(d.labels[k]) + (set.count[k] ? '' : ' · not counted') + '</span><span class="num' + (set.count[k] ? '' : ' off') + '">' + Math.round(M[k]) + ' min</span>').join('');
  const sess = d.sessions.filter(s => s.minutes >= 0.5);
  const sessHTML = sess.length ? sess.map(s => '<div class="si"><span class="w">' + esc(s.start || '') + '</span><span class="t">' + esc(shortTitle(s.title)) + (s.counted ? '' : '<span class="pill">not counted</span>') + (s.note ? ' <span class="mute tiny" style="font-weight:400">· ' + esc(s.note) + '</span>' : '') + '</span><span class="w">' + Math.max(1, Math.round(s.minutes)) + ' min · ' + esc(s.label) + '</span></div>').join('')
    : '<p class="mute" style="margin:0">Nothing yet' + (isToday ? ' today' : '') + '. Kindle reading arrives when the Kindle sleeps or closes a book; audiobooks every five minutes.</p>';
  const maxW = Math.max(60, ...d.week.map(w => w.minutes));
  const week = d.week.map(w => '<div class="wk' + (w.date === d.today ? ' today' : '') + '"><span class="m">' + (w.minutes >= 1 ? Math.round(w.minutes) : '') + '</span><div class="bar' + (w.minutes >= (w.target || 60) ? ' goal' : '') + '" style="height:' + Math.max(3, Math.round(w.minutes / maxW * 82)) + 'px" title="' + shortDate(w.date) + ': ' + Math.round(w.minutes) + ' min"></div><span class="d">' + DAYS[parseDay(w.date).getDay()].slice(0, 3) + '</span></div>').join('');
  const y = d.year30, fresh = d.fresh || {}, kin = (fresh.kindle && fresh.kindle.last) || {};
  const freshLine = 'Kindle: newest page ' + ago(kin.plugin || kin.koinsight) + (kin.plugin ? ' (Daf plugin)' : ' (KoInsight)') + ' · Audiobookshelf checked ' + ago(fresh.audiobookshelf && fresh.audiobookshelf.checked) + ' · updates every five minutes';
  const rv = d.review || {};
  let h = '<div class="top"><h1>Today</h1><span class="spacer"></span><button class="btn sm" data-act="refresh" aria-label="Sync now">' + I.sync + '</button><button class="btn sm primary" data-act="paper">Log paper</button></div><div class="page">';
  h += '<div class="hello"><h1><span style="color:var(--accent)">' + I.today.replace('width="18" height="18"', 'width="30" height="30"') + '</span>' + (isToday ? 'Today' : esc(longDate(d.date))) + '</h1><p class="mute">' + esc(longDate(d.date)) + (dayN && isToday ? ' · Year 30, day ' + dayN : '') + (isToday && d.streak && d.streak.any > 1 ? ' · ' + (d.streak.goal > 1 ? d.streak.goal + ' days in a row ' + atWord(d.goal) : d.streak.any + ' days in a row reading') : '') + '</p></div>';
  if (d.shabbat && isToday) h += '<div class="notice"><span style="color:var(--accent)">' + I.moon + '</span><span>' + (new Date().getDay() === 5 ? 'Shabbat is coming. <a href="#torah">This week’s parasha</a> is on the Torah shelf. ' : 'Shabbat. ') + 'Paper counts: log it here after havdalah, or send Ezer <b>shabbat 60</b>.</span></div>';
  if (isToday && window.DafCore.HC) h += window.DafCore.HC.todayNotice(d);
  if (d.offstand) h += '<div class="notice"><span style="color:var(--accent)">' + I.books + '</span><span style="flex:1">You’ve been reading <b>' + esc(shortTitle(d.offstand.title)) + '</b>, and it isn’t on the nightstand.</span><span style="display:flex;gap:6px;flex-wrap:wrap"><a class="btn sm" href="#books">Swap it in</a><button class="btn sm" data-act="notstand" data-id="' + esc(d.offstand.id) + '">Just browsing</button></span></div>';
  const GL = window.DafCore.Goals;
  h += '<div class="todaygrid">' + (GL ? GL.ringCard(d, ring, srcRows) : '<section class="card" aria-label="Minutes"><div class="ringrow">' + ring(118, 11, d.counted, d.goal) + '<div><div style="font-size:20px;font-weight:700">of ' + d.goal + ' minutes</div><div class="mute tiny">' + (d.counted >= d.goal ? 'That’s the hour.' : Math.ceil(d.goal - d.counted) + ' to go') + '</div></div></div><div class="rows">' + srcRows + '</div></section>') +
    '<section class="card" aria-label="Sittings"><h2>Sittings</h2><div class="sess">' + sessHTML + '</div></section></div>';
  if (rv.total) {
    // The day's review, up top on a phone like Readwise's: the first book's cover, how many, and one button.
    const f = rv.first, left = rv.total - rv.done, cards = d.cards_due || 0, done = left <= 0 && !cards;
    const books = (rv.books || []).map(t => shortTitle(t));
    h += '<section class="card revhero' + (done ? ' done' : '') + '"><div class="rhart">' + (done ? '<span class="rhcheck">' + RIC.check + '</span>' : f ? cover({ id:f.book_id, title:f.title, has_cover:(f.book_id || '').startsWith('cal:') }, 'cv rh') : '') + '</div>' +
      '<div class="rhtext"><h2>Daily Review</h2><span class="mute">' + (done ? 'Done for today' + (rv.streak && rv.streak.days > 1 ? ' · ' + rv.streak.days + ' days in a row' : '') : rv.total + ' highlight' + (rv.total === 1 ? '' : 's') + (books.length ? ' from ' + esc(books[0]) + (books.length > 1 ? ' and more' : '') : '') + (cards ? ' · ' + cards + ' flashcard' + (cards > 1 ? 's' : '') : '')) + '</span>' +
      (f && !done ? '<q class="rhq">' + window.DafCore.HL.quote(f.text) + '</q>' : '') + '</div>' +
      (done ? '<a class="btn rpill" href="#review/more">Review more</a>' : '<a class="btn primary rpill" href="#review">' + (rv.done ? 'Continue · ' + left + ' left' : 'Review') + '</a>') + '</section>';
  }
  if (isToday && d.on_this_day && d.on_this_day.length) h += '<section class="card"><div class="cardh"><h2>On this day</h2><a class="tiny" href="#stats">Stats</a></div>' +
    d.on_this_day.map(x => '<div class="hlc"><q' + (x.open ? ' class="go" data-open="' + esc(x.open) + '" role="link" tabindex="0" title="Open at this spot"' : '') + '>' + window.DafCore.HL.quote(x.text) + '</q><div class="meta tiny mute">' + esc(shortTitle(x.title)) + ' · ' + x.year + '</div></div>').join('') + '</section>';
  const stand = d.nightstand.length ? d.nightstand : d.nightstand_suggested;
  if (stand.length) h += '<section class="card"><div class="cardh"><h2>Nightstand</h2><a class="tiny" href="#books">' + (d.nightstand.length ? 'Change' : 'Suggested from what you read lately · choose your three') + '</a></div><div class="brows">' + stand.map(b => bookRow(b)).join('') + '</div></section>';
  h += '<section class="card" aria-label="This week"><h2>This week</h2><div class="week">' + week + '</div></section>';
  h += '<section class="card" aria-label="Year 30"><div class="cardh"><h2>Year 30</h2><span class="mute tiny">October 9, 2026 to October 8, 2027</span></div>' +
    '<div class="stats"><span><b>' + y.total_hours + ' h</b><span class="mute tiny">of ' + Math.round((y.targets || []).reduce((a, b) => a + b, 0) / 60 || 365) + '</span></span><span><b>' + y.days_read + '</b><span class="mute tiny">days read</span></span><span><b>' + y.days_goal + '</b><span class="mute tiny">days ' + atWord(d.goal) + '</span></span><span><b>' + (dayN || 0) + '</b><span class="mute tiny">days in</span></span></div>' +
    yearGrid(y, 'Year 30') + legendFor(d.goal) + '</section>';
  h += '<section class="card" aria-label="Year 29" id="y29"><div class="cardh"><h2 style="color:var(--fg-2)">Year 29</h2><span class="mute tiny">October 9, 2025 to October 8, 2026</span></div>' + (S.y29 ? y29Body(S.y29) : '<span class="mute">Loading…</span>') + '</section>';
  h += '<p class="mute tiny" style="margin:0">' + esc(freshLine) + '</p></div>';
  $('#main').innerHTML = h;
  if (GL) GL.celebrate(d);
}
function y29Body(g){
  return '<div class="stats"><span><b>' + g.total_hours + ' h</b><span class="mute tiny">read</span></span><span><b>' + g.days_read + '</b><span class="mute tiny">days read</span></span><span><b>' + g.days_goal + '</b><span class="mute tiny">days at the goal</span></span></div>' + yearGrid(g, 'Year 29');
}

/* ---------- review ---------- */
async function renderReview(args){
  args = args || [];
  $('#main').innerHTML = '<div class="top"><h1>' + (args[0] ? 'Review' : 'Daily review') + '</h1></div><div class="review"><span class="mute">Loading…</span></div>';
  // A themed review (a tag, favorites, a color), apart from the daily five.
  const q = args[0] === 'tag' ? 'tag=' + encodeURIComponent(decodeURIComponent(args[1] || '')) : args[0] === 'fav' ? 'fav=1' : args[0] === 'book' ? 'n=30&book=' + encodeURIComponent(decodeURIComponent(args.slice(1).join('/'))) : args[0] === 'filter' ? 'n=30&' + decodeURIComponent(args.slice(1).join('/')) : args[0] === 'color' ? 'color=' + encodeURIComponent(args[1] || '') : args[0] === 'more' ? 'n=10' : null;
  // Today's review by its date, so the one kept for offline tomorrow is tomorrow's, not today's.
  S.rev = await api(q ? '/api/review/themed?' + q : '/api/review?day=' + dayIn(Math.floor(Date.now() / 1000)));
  // Flashcards that are due come after the day's highlights.
  if (!q) { try { S.rev.items = S.rev.items.concat((await api('/api/cards/due')).items.map(c => Object.assign(c, { card: true }))); } catch(e){} }
  S.revIdx = S.rev.items.findIndex(i => !i.action); if (S.revIdx < 0) S.revIdx = S.rev.items.length;
  S.revNote = false; S.revShow = false; drawReview();
}
const RIC = {
  x: '<svg width="22" height="22" viewBox="0 0 20 20" aria-hidden="true"><path d="M5.5 5.5l9 9M14.5 5.5l-9 9" stroke="currentColor" stroke-width="1.9" stroke-linecap="round"/></svg>',
  check: '<svg width="24" height="24" viewBox="0 0 20 20" aria-hidden="true"><path d="M4.5 10.5l3.5 3.5 7.5-8" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  clock: '<svg width="21" height="21" viewBox="0 0 20 20" aria-hidden="true"><circle cx="10" cy="10" r="6.8" fill="none" stroke="currentColor" stroke-width="1.7"/><path d="M10 6.2V10l2.6 1.8" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/></svg>',
  card: '<svg width="21" height="21" viewBox="0 0 20 20" aria-hidden="true"><rect x="3.5" y="5" width="13" height="10" rx="2" fill="none" stroke="currentColor" stroke-width="1.7"/><path d="M7 10h6" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-dasharray="2 2"/></svg>',
  close: '<svg width="18" height="18" viewBox="0 0 20 20" aria-hidden="true"><path d="M5.5 5.5l9 9M14.5 5.5l-9 9" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>',
};
const DAYN = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
function streakRow(st){
  if (!st) return '';
  return '<div class="rstreak"><div class="rsh"><b>Review streak</b><span>' + st.days + ' day' + (st.days === 1 ? '' : 's') + '</span></div><div class="rsdays">' +
    st.week.map(w => '<span class="rsd' + (w.done ? ' done' : '') + '"><i>' + DAYN[parseDay(w.date).getDay()] + '</i><b>' + (w.done ? RIC.check : '') + '</b></span>').join('') + '</div></div>';
}
function drawReview(){
  const R = S.rev, items = R.items, i = S.revIdx, cur = items[i];
  let h = '<div class="rtop"><a class="ib" href="#today" aria-label="Close the review">' + RIC.close + '</a><div class="rtitle"><b>' + (R.theme ? esc(R.theme) : 'Daily Review') + '</b>' +
    '<div class="rprog" aria-hidden="true">' + items.map((x, j) => '<i class="' + (x.action ? 'done' : j === i ? 'cur' : '') + '"></i>').join('') + '</div></div>' +
    '<span class="mute tiny rkeys">' + (cur && cur.card ? 'space · 1 2 3 4' : ['keep', 'less', 'note', 'never', 'open', 'fav'].map(a => window.DafCore.Keys ? window.DafCore.Keys.keys('review', a)[0] : '').filter(Boolean).map(k => window.DafCore.Keys.name(k)).join(' · ')) + '</span></div><div class="review">';
  if (!items.length) h += '<div class="rcard"><p class="mute" style="margin:0">No highlights to review yet.</p></div>';
  else if (i >= items.length) {
    const kept = items.filter(x => !x.card && (x.action === 'keep' || x.action === 'note')).length, less = items.filter(x => x.action === 'less').length, nc = items.filter(x => x.card && !x.again).length;
    const st = R.streak && !R.theme ? Object.assign({}, R.streak, { days: Math.max(R.streak.days, 1), week: R.streak.week.map((w, k, a) => k === a.length - 1 ? Object.assign({}, w, { done: true }) : w) }) : null;
    h += '<div class="rcard rdone"><div class="rdonemark">' + RIC.check + '</div><div class="rdh">' + (R.theme ? 'Done with ' + esc(R.theme) : 'Great job') + '</div>' +
      '<p class="mute" style="margin:0;text-align:center">' + kept + ' kept' + (less ? ', ' + less + ' less often' : '') + (nc ? ', ' + nc + ' flashcard' + (nc > 1 ? 's' : '') : '') + '. Kept highlights come back in a few days, then less and less often.</p>' +
      streakRow(st) +
      '<div class="rdacts">' + (R.theme ? '<button class="btn primary rpill" data-act="revagain">Another round</button>' : '<a class="btn primary rpill" href="#today">Done</a>') +
      '<a class="rmore" href="#review/more">Review more highlights →</a></div></div>';
  } else if (cur.card) {
    const x = cur, H = window.DafCore.HL, show = S.revShow;
    h += '<div class="rcard ccard" id="rc">' + reviewSource(x, 'Flashcard' + (x.reps ? '' : ', new')) +
      '<div class="cfront"' + (/[֐-׿]/.test(x.front) ? ' dir="rtl"' : '') + '>' + H.renderFront(x, show) + '</div>' +
      (show && x.kind === 'qa' ? '<div class="cback">' + esc(x.back || '') + '</div>' : '') + '</div>' +
      (show ? '<div class="cgrades">' + [['again', 'Again', 'today'], ['hard', 'Hard', 'soon'], ['good', 'Good', 'later'], ['easy', 'Easy', 'much later']].map((g, k) => '<button class="btn' + (g[0] === 'good' ? ' primary' : '') + '" data-grade="' + g[0] + '">' + g[1] + '<span>' + g[2] + ' · ' + (k + 1) + '</span></button>').join('') + '</div>'
        : '<div class="rbar"><button class="btn primary rpill wide" data-act="cshow">Show the answer</button></div>');
  } else {
    const x = cur, H = window.DafCore.HL; H.reg.set(x.id, x);
    h += '<div class="rcard" id="rc" data-h="' + esc(x.id) + '" data-color="' + esc(x.color || 'yellow') + '">' + reviewSource(x, x.reviews ? 'Seen ' + x.reviews + '×' : 'First time') +
      '<q' + (/[֐-׿]/.test(x.text) ? ' dir="rtl"' : '') + '>' + H.quote(x.text) + '</q>' +
      (x.note ? '<div class="kindlenote"><span class="mute tiny">Your note on the Kindle</span><span>' + esc(x.note) + '</span></div>' : '') +
      (S.revNote ? '<textarea class="field" id="rnote" rows="3" placeholder="A thought, for the vault note" aria-label="Note">' + esc(x.user_note || '') + '</textarea><div style="display:flex;justify-content:flex-end;gap:8px"><button class="btn sm" data-act="rnotecancel">Cancel</button><button class="btn sm primary" data-act="rnote">Save note</button></div>'
        : (x.user_note ? '<div class="kindlenote"><span class="mute tiny">Your note in Daf</span><span>' + esc(x.user_note) + '</span></div>' : '')) +
      ((x.tags || []).length ? '<div class="htags rtags">' + x.tags.map(t => '<span>#' + esc(t) + '</span>').join('') + '</div>' : '') +
      '<div class="rtools">' + (x.open ? '<a class="hb" href="' + esc(x.open) + '" data-tip="Open at this spot (o)">' + H.IC.open + '</a>' : '') +
      '<button class="hb" data-act="rnote" data-tip="Note (n)">' + H.IC.note + '</button><button class="hb" data-hra="tag" data-tip="Tags">' + H.IC.tag + '</button>' +
      '<button class="hb' + (x.fav ? ' on' : '') + '" data-hra="fav" data-tip="' + (x.fav ? 'Unfavorite' : 'Favorite') + ' (f)">' + H.IC.heart + '</button>' +
      '<button class="hb" data-act="rshare" data-tip="Share as image">' + H.IC.share + '</button><button class="hb" data-act="rcopy" data-tip="Copy">' + H.IC.copy + '</button></div></div>' +
      '<div class="rbar">' +
      '<button class="rb" data-act="rnever" aria-label="Never again (x)"><span class="rbc">' + RIC.x + '</span><span>Never</span></button>' +
      '<button class="rb" data-act="rcard" aria-label="Make a flashcard"><span class="rbc">' + RIC.card + '</span><span>Flashcard</span></button>' +
      '<button class="rb" data-act="rless" aria-label="Less often (l)"><span class="rbc">' + RIC.clock + '</span><span>Less</span></button>' +
      '<button class="rb keep" data-act="rkeep" aria-label="Keep (k)"><span class="rbc">' + RIC.check + '</span><span>Keep</span></button></div>';
  }
  $('#main').innerHTML = h + '</div>';
  if (S.revNote) { const t = $('#rnote'); t.focus(); t.setSelectionRange(t.value.length, t.value.length); }
  swipeable($('#rc'));
}
function reviewSource(x, extra){
  return '<a class="rsrc" href="' + esc(x.open || '#book/' + encodeURIComponent(x.book_id || '')) + '">' + cover({ id:x.book_id, title:x.title, has_cover:(x.book_id || '').startsWith('cal:') }, 'cv sm') +
    '<span style="display:flex;flex-direction:column;gap:2px;min-width:0"><b>' + esc(shortTitle(x.title)) + '</b><span class="mute tiny">' + esc([x.author, x.chapter].filter(Boolean).join(' · ')) + '</span></span><span class="spacer"></span><span class="mute tiny">' + esc(extra || '') + '</span></a>';
}
// Swipe a review card: right keeps it, left shows it less often (a flashcard: right Good, left Again).
function swipeable(el){
  if (!el || !matchMedia('(pointer: coarse)').matches) return;
  let x0 = null, y0 = 0, dx = 0, locked = null;
  el.addEventListener('touchstart', e => { if (e.target.closest('textarea, input, a, button')) return; x0 = e.touches[0].clientX; y0 = e.touches[0].clientY; dx = 0; locked = null; el.style.transition = 'none'; }, { passive: true });
  el.addEventListener('touchmove', e => {
    if (x0 == null) return;
    dx = e.touches[0].clientX - x0; const dy = e.touches[0].clientY - y0;
    if (locked == null && (Math.abs(dx) > 8 || Math.abs(dy) > 8)) locked = Math.abs(dx) > Math.abs(dy);
    if (!locked) return;
    el.style.transform = 'translateX(' + dx + 'px) rotate(' + (dx / 40) + 'deg)';
    el.classList.toggle('lean-keep', dx > 60); el.classList.toggle('lean-less', dx < -60);
  }, { passive: true });
  el.addEventListener('touchend', () => {
    if (x0 == null) return; x0 = null; el.style.transition = '';
    if (locked && Math.abs(dx) > 90) {
      const right = dx > 0, cur = S.rev.items[S.revIdx];
      el.style.transform = 'translateX(' + (right ? 120 : -120) + 'vw) rotate(' + (right ? 12 : -12) + 'deg)';
      try { window.dafShell && window.dafShell.haptic && window.dafShell.haptic('confirm'); } catch(e){}
      setTimeout(() => { if (cur && cur.card) { if (!S.revShow) { S.revShow = true; drawReview(); return; } cardGrade(right ? 'good' : 'again'); } else reviewAct(right ? 'keep' : 'less'); }, 160);
    } else { el.style.transform = ''; el.classList.remove('lean-keep', 'lean-less'); }
  });
}
async function cardGrade(g){
  const x = S.rev && S.rev.items[S.revIdx]; if (!x || !x.card) return;
  try { await api('/api/cards/' + encodeURIComponent(x.id) + '/grade', { method:'POST', body:JSON.stringify({ grade:g }) }); }
  catch(e){ toast(e.message); return; }
  x.action = g; S.revIdx++; S.revShow = false;
  if (g === 'again') S.rev.items.push(Object.assign({}, x, { action:null, again:true, reps:(x.reps || 0) + 1 }));   // once more before you're done
  drawReview(); load(true);
}
async function reviewAct(action){
  const x = S.rev && S.rev.items[S.revIdx]; if (!x) return;
  const body = { action };
  if (action === 'note') { body.note = ($('#rnote') || {}).value || ''; if (!body.note.trim()) { S.revNote = false; drawReview(); return; } x.user_note = body.note; }
  try { await api('/api/review/' + encodeURIComponent(x.id), { method:'POST', body:JSON.stringify(body) }); }
  catch(e){ toast(e.message); return; }
  x.action = action; S.revNote = false; S.revIdx++;
  if (action === 'never') toast('It won’t come up in review again. It stays in Highlights and the vault.');
  if (action === 'note') { toast('Note saved to the vault'); window.DafCore.HL.noteTags(x, x.user_note).catch(() => {}); }
  drawReview(); load(true);
}

/* ---------- highlights ---------- */
const HL_SOURCES = [['', 'All'], ['kindle', 'Kindle'], ['daf', 'Made in Daf'], ['articles', 'Articles'], ['audio', 'Audiobooks'], ['paper', 'Paper'], ['readwise', 'Readwise']];
function hlQuery(){
  const q = new URLSearchParams();
  if (S.hlq) q.set('q', S.hlq); if (S.hlPrivate) q.set('private', '1'); if (S.hlSource) q.set('source', S.hlSource);
  if (S.hlColor) q.set('color', S.hlColor); if (S.hlTag) q.set('tag', S.hlTag); if (S.hlFav) q.set('fav', '1');
  return q;
}
async function renderHighlights(){
  $('#main').innerHTML = '<div class="top"><h1>Highlights</h1><span class="spacer"></span><input class="field" id="hlq" type="search" placeholder="Search highlights, notes, tags" value="' + esc(S.hlq) + '" style="max-width:280px;min-height:36px" aria-label="Search highlights"><button class="btn sm" data-act="hlreview" title="A review of what the filters show">Review these</button><button class="btn sm" data-act="hlexport">Export</button></div><div class="page" id="hlbody"><span class="mute">Loading…</span></div>';
  await drawHighlights();
}
async function drawHighlights(){
  const q = hlQuery(); q.set('sort', S.hlSort);
  const r = await swr('/api/highlights?' + q.toString());
  const body = $('#hlbody'); if (!body) return;
  const C = window.DafCore, H = C.HL;
  let h = '<div class="hlfilters"><div class="chips" role="radiogroup" aria-label="Where from">' + HL_SOURCES.map(x => '<button class="chip' + (S.hlSource === x[0] ? ' on' : '') + '" data-hlsrc="' + x[0] + '" role="radio" aria-checked="' + (S.hlSource === x[0]) + '">' + x[1] + '</button>').join('') + '</div>' +
    '<div class="hlf2"><span class="hlcolors" aria-label="Color">' + HL_COLORS.map(c => '<button class="cdot' + (S.hlColor === c ? ' on' : '') + '" data-hlcolor="' + c + '" aria-label="Only ' + c + '" title="Only ' + c + '" style="--c:var(--hl-' + c + '-line)"></button>').join('') + '</span>' +
    (r.tags.length || S.hlTag ? '<select class="field sm" id="hltag" aria-label="Tag"><option value="">All tags</option>' + r.tags.concat(S.hlTag && !r.tags.includes(S.hlTag) ? [S.hlTag] : []).map(t => '<option value="' + esc(t) + '"' + (t === S.hlTag ? ' selected' : '') + '>#' + esc(t) + '</option>').join('') + '</select>' : '') +
    '<button class="chip' + (S.hlFav ? ' on' : '') + '" data-act="hlfav">' + H.IC.heart + ' Favorites</button>' +
    '<select class="field sm" id="hlsort" aria-label="Order"><option value="recent"' + (S.hlSort === 'recent' ? ' selected' : '') + '>Newest</option><option value="book"' + (S.hlSort === 'book' ? ' selected' : '') + '>By book, in reading order</option><option value="oldest"' + (S.hlSort === 'oldest' ? ' selected' : '') + '>Oldest</option></select></div></div>';
  h += '<div class="hlhead"><span class="mute">' + r.count + ' highlight' + (r.count === 1 ? '' : 's') + ' · ' + r.books + ' ' + (r.books === 1 ? 'book or article' : 'books and articles') + ' · ' + r.notes + ' with notes' +
    (S.hlColor || S.hlTag || S.hlFav || S.hlSource || S.hlq ? ' · <button class="linkbtn" data-act="hlclear">Clear filters</button>' : '') +
    (S.hlTag || S.hlFav || S.hlColor ? ' · <a href="#review/' + (S.hlTag ? 'tag/' + encodeURIComponent(S.hlTag) : S.hlFav ? 'fav' : 'color/' + S.hlColor) + '">Review ' + (S.hlTag ? '#' + esc(S.hlTag) : S.hlFav ? 'favorites' : 'the ' + S.hlColor + ' ones') + '</a>' : '') + '</span><label class="tiny mute" style="display:flex;gap:8px;align-items:center"><input type="checkbox" id="hlpriv"' + (S.hlPrivate ? ' checked' : '') + '> Show private books</label></div>';
  const few = S.hlSort === 'recent' && !S.hlq && !S.hlTag && !S.hlColor && !S.hlFav;
  H.rowOpts = {};
  h += r.groups.map(g => {
    const all = !few || S.hlOpen.has(g.book_id), items = all ? g.items : g.items.slice(0, 5);
    const first = g.items[0], href = first && first.open && first.open.startsWith('#ebook/') ? '#ebook/' + encodeURIComponent(g.book_id) : first && first.open && first.open.startsWith('#read/') ? '#read/' + encodeURIComponent(g.book_id) : '#book/' + encodeURIComponent(g.book_id);
    return '<section class="card hlgroup"><div class="cardh"><a href="#book/' + encodeURIComponent(g.book_id) + '" class="gtitle">' + cover({ id:g.book_id, title:g.title, has_cover:g.has_cover }, 'cv sm') + '<span class="gt"><b>' + esc(shortTitle(g.title)) + '</b><span class="mute tiny">' + esc(g.author || '') + (g.author ? ' · ' : '') + g.items.length + ' highlight' + (g.items.length === 1 ? '' : 's') + '</span></span></a>' +
      '<span class="gacts"><a class="btn sm" href="' + href + '">' + (href.startsWith('#ebook/') ? 'Read in Daf' : href.startsWith('#read/') ? 'Open' : 'Book page') + '</a></span></div>' +
      '<div class="hrows">' + items.map(x => H.row(x)).join('') + '</div>' +
      (items.length < g.items.length ? '<button class="linkbtn tiny" data-act="hlmore" data-id="' + esc(g.book_id) + '">Show all ' + g.items.length + '</button>' : '') + '</section>';
  }).join('');
  if (!r.groups.length) h += '<p class="mute">Nothing matches.</p>';
  body.innerHTML = h;
}
function exportMenu(anchor, extra){
  const q = extra || hlQuery(), p = $('#pop'), r = anchor.getBoundingClientRect();
  p.onclick = p.oninput = p.onkeydown = null;
  p.innerHTML = '<div class="menu">' + [['md', 'Markdown, by book'], ['csv', 'CSV (spreadsheet)'], ['json', 'JSON']].map(f => { const qq = new URLSearchParams(q); qq.set('fmt', f[0]); return '<a href="/api/highlights/export?' + qq.toString() + '" download>' + f[1] + '</a>'; }).join('') +
    '<span class="mhint" style="padding-left:10px">Exports what the filters show now.</span>' +
    '<a href="/api/cards/export" download>Flashcards for Anki</a><span class="mhint" style="padding-left:10px">Every card, as a file Anki imports (File → Import).</span></div>';
  p.hidden = false; p.style.left = Math.max(8, Math.min(window.innerWidth - 260, r.right - 240)) + 'px'; p.style.top = (r.bottom + 8) + 'px';
}
// Five highlight colors; the last one used is the next default.
const HL_COLORS = ['yellow', 'green', 'blue', 'pink', 'purple'];
function colorDots(id, cur){
  return '<span class="cdots">' + HL_COLORS.map(c => '<button class="cdot' + ((cur || 'yellow') === c ? ' on' : '') + '" data-sel="color" data-h="' + esc(id) + '" data-c="' + c + '" aria-label="' + c + '" style="--c:var(--hl-' + c + '-line)"></button>').join('') + '</span>';
}
function hlCard(x){ return window.DafCore.HL.row(x); }

/* ---------- books ---------- */
async function renderBooks(){
  $('#main').innerHTML = '<div class="top"><h1>Books</h1><span class="spacer"></span><button class="btn sm primary" data-act="addbook">Add a book</button></div><div class="page"><span class="mute">Loading…</span></div>';
  const r = await swr('/api/books');
  S.books = r;
  const stand = r.nightstand.length ? r.nightstand : [];
  let h = '<section class="card"><div class="cardh"><h2>Nightstand</h2><span class="mute tiny">Three books. ' + r.marked_reading + ' notes in the vault say “reading”.</span></div>';
  const readBtn = b => b.readable ? '<a class="btn sm primary" href="#ebook/' + encodeURIComponent(b.id) + '">Read</a> ' : '';
  if (stand.length) h += '<div class="brows">' + stand.map(b => bookRow(b, '<span class="tiny rowacts">' + readBtn(b) + '<button class="linkbtn" data-act="standoff" data-id="' + esc(b.id) + '">Take off the nightstand</button></span>')).join('') + '</div>';
  else h += '<p class="mute" style="margin:0">Nothing chosen yet. Suggested from what you read lately:</p><div class="brows">' + r.suggested.map(b => bookRow(b)).join('') + '</div><button class="btn primary" data-act="standuse" style="align-self:flex-start">Use these three</button>';
  h += '</section><section class="card" id="shelfsec"><h2>Shelves</h2><span class="mute">Loading…</span></section><section class="card" id="hcwant"><div class="cardh"><h2>Want to read</h2><span class="mute tiny">Asking Hardcover…</span></div></section>';
  const others = S.booksAll ? r.others : r.others.slice(0, 24);
  h += '<section class="card"><div class="cardh"><h2>Opened lately</h2><span class="mute tiny">Newest first' + (r.manga ? ' · <a href="#manga">manga is on its own page</a>' : '') + '</span></div><div class="bgrid">' + others.map(b => '<div class="bcell">' + bookRow(b, b.highlights ? '<span class="tiny mute">' + b.highlights + ' highlights</span>' : '') +
    '<button class="btn sm" data-act="standon" data-id="' + esc(b.id) + '"' + (stand.length >= 3 ? ' data-full="1"' : '') + '>Put on the nightstand</button></div>').join('') + '</div>' +
    (r.others.length > 24 && !S.booksAll ? '<button class="btn" data-act="booksall" style="align-self:flex-start">Show all ' + r.others.length + '</button>' : '') + '</section>';
  h += '<section class="card"><div class="cardh"><h2>Your library</h2><span class="mute tiny">Calibre · opens in Daf’s reader</span></div><input class="field" id="libq" placeholder="Search by title or author" autocomplete="off"><div class="libgrid" id="libgrid"><span class="mute">Loading…</span></div></section>';
  $('#main .page').innerHTML = h;
  if (window.DafCore.HC) window.DafCore.HC.shelf($('#hcwant'));
  if (window.DafCore.Shelves) window.DafCore.Shelves.section();
  drawLibrary('');
}
async function drawLibrary(q){
  const r = await api('/api/ebooks?q=' + encodeURIComponent(q));
  const g = $('#libgrid'); if (!g) return;
  const list = q ? r.books : r.books.slice(0, S.libAll ? 999 : 30);
  g.innerHTML = list.length ? list.map(b => {
    const f = b.daf_fraction != null ? b.daf_fraction * 100 : b.progress;
    return '<a class="libcard" href="#ebook/' + encodeURIComponent(b.id) + '" title="' + esc(b.title) + '">' + cover(b, 'cv lib') + '<b>' + esc(shortTitle(b.title)) + '</b><span class="mute tiny">' + esc(b.author || '') + '</span>' + (f ? '<span class="tiny mute">' + bar(f) + ' ' + Math.round(f) + '%</span>' : '') + '</a>';
  }).join('') : '<p class="mute">Nothing by that name in Calibre.</p>';
  if (!q && !S.libAll && r.books.length > 30) g.insertAdjacentHTML('beforeend', '<button class="btn" data-act="liball">Show all ' + r.books.length + '</button>');
}
async function setStand(ids){ await api('/api/nightstand', { method:'PUT', body:JSON.stringify({ ids }) }); load(true); }
function askSwap(newId){
  const r = S.books; const stand = r.nightstand;
  $('#scrim').hidden = false; const m = $('#modal'); m.hidden = false;
  m.innerHTML = '<h2>Which one steps off?</h2><p class="mute" style="margin:0">The nightstand holds three. The one you take off stays in your library and your vault.</p><div class="brows">' +
    stand.map(b => '<button class="swap" data-act="swap" data-out="' + esc(b.id) + '" data-in="' + esc(newId) + '">' + cover(b, 'cv xs') + '<span>' + esc(shortTitle(b.title)) + '</span></button>').join('') + '</div><div style="display:flex;justify-content:flex-end"><button class="btn" data-act="close">Cancel</button></div>';
}

// A book's reading, BookOrbit-style: time across sources, sittings, pace, the last 30 days, and when it'll be done.
function bookStats(st){
  const h = m => m >= 60 ? (Math.round(m / 6) / 10) + ' h' : m + ' min';
  const src = { kindle: 'Kindle', ebook: 'Daf', audio: 'audiobook' };
  const parts = Object.entries(st.by_source).filter(([, m]) => m >= 1).map(([k, m]) => h(m) + ' ' + (src[k] || k));
  const max = Math.max(10, ...st.last30);
  const bars = st.last30.map((m, i) => '<i style="height:' + (m >= 0.5 ? Math.max(3, Math.round(m / max * 40)) : 1) + 'px" class="' + (m >= 0.5 ? 'on' : '') + '" title="' + (m >= 0.5 ? Math.round(m) + ' min' : 'nothing') + (i === 29 ? ' today' : '') + '"></i>').join('');
  let left = '';
  if (st.minutes_left) left = '<span><b>' + h(st.minutes_left) + '</b><span class="mute tiny">left' + (st.finish ? ', done around ' + shortDate(st.finish) : '') + '</span></span>';
  return '<section class="card bstats"><div class="cardh"><h2>Reading</h2><span class="mute tiny">Since ' + ['January','February','March','April','May','June','July','August','September','October','November','December'][parseDay(st.first).getMonth()] + ' ' + parseDay(st.first).getFullYear() + '</span></div>' +
    '<div class="stats"><span><b>' + h(st.minutes) + '</b><span class="mute tiny">' + esc(parts.join(' · ') || 'read') + '</span></span><span><b>' + st.sittings + '</b><span class="mute tiny">sittings on ' + st.days + ' day' + (st.days === 1 ? '' : 's') + '</span></span>' +
    (st.pages_per_hour ? '<span><b>' + st.pages_per_hour + '</b><span class="mute tiny">Kindle pages an hour</span></span>' : '') + left + '</div>' +
    '<div class="b30" role="img" aria-label="The last 30 days">' + bars + '</div><span class="tiny mute">The last 30 days' + (st.recent_per_day ? ' · about ' + st.recent_per_day + ' minutes a day lately' : '') + '</span></section>';
}
async function renderBook(id, hl){
  $('#main').innerHTML = '<div class="top"><a class="btn sm" href="#books">' + I.back + '</a><h1>Book</h1></div><div class="page"><span class="mute">Loading…</span></div>';
  const b = await api('/api/books/' + encodeURIComponent(id));
  let h = '<div class="bookhead">' + cover(b, 'cv lg') + '<div style="display:flex;flex-direction:column;gap:8px;min-width:0;flex:1 1 280px"><h1 class="btitle">' + esc(b.title) + '</h1><span class="mute">' + esc(b.author || '') + '</span>' +
    (b.progress != null ? '<span>' + bar(b.progress) + ' ' + Math.round(b.progress) + '% on the Kindle · ' + esc(b.progress_note || '') + '</span>' : '') +
    (b.audio_note ? '<span class="mute">Audiobook: ' + esc(b.audio_note) + '</span>' : '') +
    '<span class="mute tiny">' + [b.minutes_kindle && !b.stats ? Math.round(b.minutes_kindle / 60 * 10) / 10 + ' h read on the Kindle' : '', b.last_read ? 'last opened ' + epochDate(b.last_read) : ''].filter(Boolean).join(' · ') + '</span>' +
    '<div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:4px">' + (b.readable ? '<a class="btn primary" href="#ebook/' + encodeURIComponent(b.id) + '">' + (b.daf_position ? 'Continue in Daf · ' + Math.round((b.daf_position.fraction || 0) * 100) + '%' : 'Read in Daf') + '</a>' : '') + (b.kind === 'book' ? (b.on_nightstand ? '<button class="btn" data-act="standoff" data-id="' + esc(b.id) + '">Take off the nightstand</button>' : '<button class="btn primary" data-act="standon" data-id="' + esc(b.id) + '">Put on the nightstand</button>') : '') +
    (b.url ? '<a class="btn" href="' + esc(b.url) + '" target="_blank" rel="noopener">Open original</a>' : '') + '</div>' +
    (b.vault_path ? '<span class="tiny mute">Vault: <code>' + esc(b.vault_path) + '</code></span>' : '<span class="tiny mute">No vault note for this book yet; notes stay in Daf until there is one.</span>') + '</div></div>';
  if (b.stats) h += bookStats(b.stats);
  if (window.DafCore.AddBook) h += window.DafCore.AddBook.sections(b);
  if (b.kind === 'book') h += '<section class="card" id="bshelves"></section>';
  if (b.kind === 'book' && !b.private) h += '<section class="card hcsec" id="hcsec"><div class="cardh"><h2>Hardcover</h2></div><span class="mute tiny">Asking Hardcover…</span></section>';
  h += '<section class="card"><div class="cardh"><h2>A note on this book</h2></div><div style="display:flex;gap:8px;flex-wrap:wrap"><input class="field" id="bnote" placeholder="A thought while reading" style="flex:1 1 260px"><button class="btn primary" data-act="booknote" data-id="' + esc(b.id) + '">Save</button></div>' +
    (b.notes.length ? '<div class="sess">' + b.notes.map(n => '<div class="nrow"><span class="mute tiny">' + epochDate(n.created) + (n.page ? ' · page ' + n.page : '') + ' · ' + (n.source === 'voice' ? 'voice note' : 'note') + '</span><span>' + esc(n.text) + '</span></div>').join('') + '</div>' : '') + '</section>';
  if (b.bookmarks.length) h += '<section class="card"><div class="cardh"><h2>Audiobook bookmarks</h2></div>' + b.bookmarks.map(m => '<div class="nrow"><span class="mute tiny num">' + Math.floor(m.at / 3600) + ':' + String(Math.floor(m.at % 3600 / 60)).padStart(2, '0') + ':' + String(Math.floor(m.at % 60)).padStart(2, '0') + '</span><span>' + esc(m.title) + '</span></div>').join('') + '<span class="mute tiny">Daf transcribes the minute before each bookmark into a highlight.</span></section>';
  const H = window.DafCore.HL, hls = b.highlights.slice().sort((a, c) => a.order - c.order);
  let ch = null; H.rowOpts = { chapter: false };
  h += '<section class="card"><div class="cardh"><h2>Highlights</h2><span class="mute tiny">' + hls.length + (hls.length ? ', in reading order' : '') + '</span>' +
    (hls.length ? '<span class="spacer"></span>' + (b.private ? '' : '<a class="btn sm" href="#review/book/' + encodeURIComponent(b.id) + '">Review these</a>') + '<button class="btn sm" data-act="bookexport" data-id="' + esc(b.id) + '">Export</button>' : '') + '</div>' +
    (hls.length && !b.private ? '<div class="prow brfreq"><div class="d"><b>In the daily review</b><span>' + ({ more: 'This book comes up more often.', less: 'This book comes up less often.', never: 'This book stays out of the daily review. Its highlights are still here.', normal: 'Like any other book.' }[b.review_freq] || '') + '</span></div>' +
      '<div class="seg" role="radiogroup" aria-label="How often">' + [['more','More'],['normal','As usual'],['less','Less'],['never','Never']].map(x => '<button type="button" role="radio" aria-checked="' + (b.review_freq === x[0]) + '" class="' + (b.review_freq === x[0] ? 'on' : '') + '" data-act="bookfreq" data-id="' + esc(b.id) + '" data-f="' + x[0] + '">' + x[1] + '</button>').join('') + '</div></div>' : '') +
    (hls.length ? '<div class="hrows">' + hls.map(x => { let o = ''; if (x.chapter && x.chapter !== ch) { ch = x.chapter; o = '<div class="nbch">' + esc(ch) + '</div>'; } return o + H.row(x, H.rowOpts); }).join('') + '</div>' : '<p class="mute" style="margin:0">None yet.</p>') + '</section>';
  $('#main .page').innerHTML = h;
  if ($('#hcsec') && window.DafCore.HC) window.DafCore.HC.section(b.id);
  if ($('#bshelves') && window.DafCore.Shelves) window.DafCore.Shelves.forBook(b).catch(() => {});
  if (hl) setTimeout(() => H.flash($('.hrow[data-h="' + CSS.escape(hl) + '"]')), 80);
}

/* ---------- sources & prefs ---------- */
async function renderSources(){
  $('#main').innerHTML = '<div class="top"><h1>Sources</h1><span class="spacer"></span><button class="btn sm" data-act="refresh">' + I.sync + ' Sync now</button></div><div class="page"><span class="mute">Checking…</span></div>';
  const r = await api('/api/sources');
  const USE = { 'Kindle':'reading time', 'KoInsight':'Kindle history', 'Audiobookshelf':'listening, bookmarks', 'Obsidian vault':'notes', 'Calibre':'books, covers',
    'Karakeep':'Library', 'FreshRSS':'Feed', 'Kokoro voice':'read-aloud', 'Sefaria':'Torah shelf', 'AntennaPod':'podcasts', 'Transcripts':'videos, clips, pages', 'Host tools':'Ask, transcripts' };
  $('#main .page').innerHTML = '<section class="card"><div class="srcs">' + r.checks.map(c =>
    '<div class="src"><span class="dot' + (c.ok ? '' : ' bad') + '" aria-label="' + (c.ok ? 'Working' : 'Not working') + '"></span><b>' + esc(c.name) + '</b><span class="dt mute">' + esc(c.detail) + '</span><span class="mute tiny">' + esc(USE[c.name] || '') + '</span></div>'
  ).join('') + '</div></section><p class="mute tiny" style="margin:0">Daf only reads these. In the vault it writes the reading log, a “From Daf” section at the end of book notes, and notes for what you highlight or write a note on in Daf, with the full text (Reference/clippings, youtube, podcasts, instagram, torah). Nothing else.</p>';
}
/* ---------- read-aloud voices (Kokoro on the server) ---------- */
// Kokoro's voice names start with two letters for the accent and whose voice it is (af_heart: an
// American woman's). Only the English ones read English well. Each group goes clearest first, by
// Kokoro's own ratings.
const VKIND = { af: 'American woman', am: 'American man', bf: 'British woman', bm: 'British man' };
const VORDER = ['af_heart', 'af_bella', 'af_nicole', 'af_aoede', 'af_kore', 'af_sarah', 'af_alloy', 'af_nova', 'af_sky', 'af_jessica', 'af_river',
  'am_fenrir', 'am_michael', 'am_puck', 'am_echo', 'am_eric', 'am_liam', 'am_onyx', 'am_adam', 'am_santa',
  'bf_emma', 'bf_isabella', 'bf_alice', 'bf_lily', 'bm_fable', 'bm_george', 'bm_lewis', 'bm_daniel'];
const VSAMPLE = 'This is how I would sound, reading to you.';
const Voices = {
  cur: null, all: null, sampleAudio: null,
  name: id => { const m = /^[ab][fm]_([a-z]+)$/.exec(id || ''); return m ? m[1][0].toUpperCase() + m[1].slice(1) : String(id || ''); },
  kind: id => VKIND[String(id || '').slice(0, 2)] || '',
  label: id => Voices.name(id) + (Voices.kind(id) ? ' · ' + Voices.kind(id) : ''),
  async load(){
    if (!Voices.cur) { try { Voices.cur = (S.settings && S.settings.tts_voice) || (await api('/api/settings')).tts_voice || 'af_heart'; } catch(e){ Voices.cur = 'af_heart'; } }
    if (!Voices.all) {
      let v = []; try { v = (await api('/api/voices')).voices.filter(x => /^[ab][fm]_[a-z]+$/.test(x)); } catch(e){}
      const rank = x => { const i = VORDER.indexOf(x); return i < 0 ? 999 : i; };
      if (v.length) Voices.all = v.sort((a, b) => Object.keys(VKIND).indexOf(a.slice(0, 2)) - Object.keys(VKIND).indexOf(b.slice(0, 2)) || rank(a) - rank(b) || a.localeCompare(b));
    }
    return Voices.all || [];
  },
  async set(id){
    await api('/api/settings', { method:'PUT', body:JSON.stringify({ tts_voice:id }) });
    Voices.cur = id; if (S.settings) S.settings.tts_voice = id;
    window.dispatchEvent(new CustomEvent('daf-voice', { detail: { id } }));
  },
  async hear(id, btn){
    if (Voices.sampleAudio) Voices.sampleAudio.pause();
    if (btn) btn.classList.add('busy');
    try {
      const r = await fetch('/api/tts/text', { method:'POST', credentials:'same-origin', headers:{ 'Content-Type':'application/json' }, body:JSON.stringify({ text:VSAMPLE, voice:id }) });
      if (!r.ok) throw new Error('Kokoro didn’t answer');
      Voices.sampleAudio = new Audio(URL.createObjectURL(await r.blob())); await Voices.sampleAudio.play();
    } catch(e){ toast(e.message); }
    finally { if (btn) btn.classList.remove('busy'); }
  },
  // The list, from the read-aloud bar: a voice's name picks it, ▶ plays a line in it.
  async menu(anchor){
    const p = $('#pop'), all = await Voices.load();
    if (!all.length) { toast('Kokoro isn’t answering on the server'); return; }
    let group = '';
    p.onclick = p.oninput = p.onkeydown = null;
    p.innerHTML = '<span class="lbl">Read-aloud voice</span><div class="vlist">' + all.map(id => {
      const g = VKIND[id.slice(0, 2)], head = g !== group ? '<span class="facegrp">' + esc((group = g)) + '</span>' : '';
      return head + '<div class="vrow' + (id === Voices.cur ? ' on' : '') + '"><button class="vpick" data-vpick="' + esc(id) + '"><span class="ck">' + (id === Voices.cur ? '✓' : '') + '</span>' + esc(Voices.name(id)) + '</button>' +
        '<button class="ib vhear" data-vhear="' + esc(id) + '" aria-label="Hear ' + esc(Voices.name(id)) + '">▶</button></div>';
    }).join('') + '</div>';
    p.hidden = false;
    const r = anchor.getBoundingClientRect(), h = Math.min(p.offsetHeight, window.innerHeight * 0.6);
    p.style.left = Math.max(8, Math.min(window.innerWidth - p.offsetWidth - 8, r.left + r.width / 2 - p.offsetWidth / 2)) + 'px';
    p.style.top = (r.top - h - 8 > 8 ? r.top - h - 8 : Math.min(window.innerHeight - h - 8, r.bottom + 8)) + 'px';
    const on = p.querySelector('.vrow.on'); if (on) on.scrollIntoView({ block: 'center' });
    p.onclick = async e => {
      const hb = e.target.closest('[data-vhear]'); if (hb) { Voices.hear(hb.dataset.vhear, hb); return; }
      const pk = e.target.closest('[data-vpick]'); if (!pk) return;
      p.hidden = true; p.onclick = null;
      try { await Voices.set(pk.dataset.vpick); toast('Reading in ' + Voices.label(pk.dataset.vpick)); } catch(err){ toast(err.message); }
    };
  },
};

document.addEventListener('click', e => { const b = e.target.closest('#ttshear'); if (b) Voices.hear($('#ttsvoice').value, b); });

// How long the Feed keeps unread items in Unseen (settings feed_expire_days; 3650 is "never").
const FEED_WINDOWS = [[7, 'a week'], [14, '2 weeks'], [21, '3 weeks'], [30, 'a month'], [60, '2 months'], [90, '3 months'], [180, '6 months'], [365, 'a year'], [3650, 'never']];

async function renderPrefs(){
  const s = await api('/api/settings');
  S.settings = s;
  const sw = (k, label, desc, locked) => '<div class="prow"><div class="d"><b>' + label + '</b><span>' + desc + '</span></div><input type="checkbox" class="sw" id="c-' + k + '" data-count="' + k + '"' + (s.count[k] ? ' checked' : '') + (locked ? ' disabled' : '') + ' aria-label="' + esc(label) + '"></div>';
  let zones = []; try { zones = Intl.supportedValuesOf('timeZone'); } catch(e) {} if (zones.indexOf('UTC') < 0) zones.unshift('UTC'); if (s.home_tz && zones.indexOf(s.home_tz) < 0) zones.push(s.home_tz);
  $('#main').innerHTML = '<div class="top"><h1>Preferences</h1></div><div class="page"><section class="card" id="goalscard"><h2>Goals</h2><span class="mute">Loading…</span></section><section class="card" id="appearcard"></section><section class="card" id="countcard"><h2>What counts toward the goal</h2><div>' +
    sw('kindle','Books on the Kindle','KOReader reading time') + sw('manga','Manga in Daf','Time in Daf’s manga reader') + sw('audio','Audiobooks','Listening time from Audiobookshelf') + sw('article','Articles in Daf','Time with an article open in Daf') +
    sw('paper','Paper books','Minutes you log here or with Ezer') + sw('video','Videos','Time with a video open in Daf') + sw('podcast','Podcasts','Never counted', true) + '</div></section>' +
    '<section class="card" id="reviewcard"><h2>Daily review</h2><div class="prow"><div class="d"><b>Highlights per day</b><span>Ezer sends the first one in the morning. Takes effect tomorrow.</span></div><select class="field" id="revsize" style="width:auto">' + [3,5,8,12].map(n => '<option' + (n === s.review_size ? ' selected' : '') + '>' + n + '</option>').join('') + '</select></div></section>' +
    '<section class="card" id="readercard"><h2>Reader</h2><div class="prow"><div class="d"><b>Read-aloud voice</b><span>Kokoro on the server. The voice button in the read-aloud bar changes it too, with a line in each voice.</span></div><select class="field" id="ttsvoice" style="width:auto"><option value="' + esc(s.tts_voice || 'af_heart') + '">' + esc(Voices.label(s.tts_voice || 'af_heart')) + '</option></select><button class="btn sm" id="ttshear">Hear it</button></div>' +
    '<div class="prow"><div class="d"><b>Read-aloud speed</b></div><select class="field" id="ttsspeed" style="width:auto">' + [0.9, 1, 1.1, 1.25, 1.5].map(n => '<option value="' + n + '"' + (n === (s.tts_speed || 1) ? ' selected' : '') + '>' + n + '×</option>').join('') + '</select></div>' +
    (document.documentElement.classList.contains('shell-android') ? '<div class="prow"><div class="d"><b>Volume buttons turn pages</b><span>In books and manga. While music or read-aloud plays they change the volume. On this device.</span></div><input type="checkbox" class="sw" id="volkeys"' + (lsGet('volumeKeys', false) ? ' checked' : '') + ' aria-label="Volume buttons turn pages"></div>' : '') +
    '<div class="prow"><div class="d"><b>After Done or Later, open the next one</b><span>In an article, archiving it or moving it to Later opens the next item in the list instead of going back to the list. On this device.</span></div><input type="checkbox" class="sw" id="autoadv"' + (lsGet('autoAdvance', false) ? ' checked' : '') + ' aria-label="Open the next one"></div>' +
    '<div class="prow"><div class="d"><b>The Feed lets go after</b><span>Unseen items older than this move to Seen, so the Feed never becomes a pile. A longer time brings back the unread ones FreshRSS still has.</span></div><select class="field" id="expire" style="width:auto">' + FEED_WINDOWS.concat(FEED_WINDOWS.some(w => w[0] === (s.feed_expire_days || 30)) ? [] : [[s.feed_expire_days, s.feed_expire_days + ' days']]).map(w => '<option value="' + w[0] + '"' + (w[0] === (s.feed_expire_days || 30) ? ' selected' : '') + '>' + w[1] + '</option>').join('') + '</select></div></section>' +
    '<section class="card" id="dayscard"><h2>Days</h2><div class="prow"><div class="d"><b>Home time zone</b><span>Decides when a day starts and ends. Switch it when you travel.</span></div><select class="field" id="tz" style="width:auto">' + zones.map(z => '<option' + (z === s.home_tz ? ' selected' : '') + '>' + esc(z) + '</option>').join('') + '</select></div></section>' +
    '<section class="card" id="phonecard"><h2>Phone</h2><span class="mute">Loading…</span></section>' +
    '<section class="card" id="podcard"><h2>Podcasts</h2><span class="mute">Loading…</span></section>' +
    '<section class="card" id="hccard"><h2>Hardcover</h2><span class="mute">Loading…</span></section>' +
    '<section class="card" id="nlcard"><h2>Newsletters</h2><span class="mute">Loading…</span></section>' +
    '<section class="card" id="digestcard"><h2>Morning email</h2><span class="mute">Loading…</span></section>' +
    '<section class="card" id="igcard"><h2>Instagram</h2><span class="mute">Loading…</span></section>' +
    '<section class="card" id="alcard"><h2>AniList</h2><span class="mute">Loading…</span></section>' +
    '<section class="card" id="aicard"><h2>AI</h2><span class="mute">Loading…</span></section>' +
    '<section class="card" id="keyscard"><h2>Keyboard</h2></section>' +
    '<section class="card" id="importcard"><h2>Import</h2><span class="mute">Loading…</span></section>' +
    '<section class="card" id="fbcard"><h2>Feedback</h2><span class="mute">Loading…</span></section>' +
    '<section class="card" id="tagscard"><h2>Library tags</h2><span class="mute">Loading…</span></section>' +
    '<section class="card" id="tipscard"><h2>Tips</h2><span class="mute">Loading…</span></section>' +
    '<section class="card" id="acctcard"><h2>Account</h2>' +
    '<form id="acctf" class="acct"><div class="prow"><div class="d"><b>Username</b><span>You sign in as <b>' + esc(S.user || '') + '</b>.</span></div><input class="field" id="au" autocomplete="username" autocapitalize="none" spellcheck="false" value="' + esc(S.user || '') + '"></div>' +
    '<div class="prow"><div class="d"><b>New password</b><span>Optional. At least 10 characters. Changing it signs out every other browser.</span></div><input class="field" id="anp" type="password" autocomplete="new-password"></div>' +
    '<div class="prow"><div class="d"><b>Current password</b><span>Needed for either change.</span></div><input class="field" id="acp" type="password" autocomplete="current-password" required></div>' +
    '<div style="display:flex;justify-content:flex-end"><button class="btn primary" type="submit">Save</button></div></form>' +
    '<div class="prow"><div class="d"><b>Other browsers</b><span>Signs out every browser except this one. The Kindle, the phone, the apps and AntennaPod use their own tokens and stay connected.</span></div><button class="btn sm" data-act="signoutothers">Sign them out</button></div>' +
    '<div id="devlist"></div>' +
    '<div class="prow"><div class="d"><b>Sign out</b><span>On this device</span></div><button class="btn sm" data-act="logout">Sign out</button></div></section></div>';
  organizePrefs();
}
// Preferences in groups, each under its heading and a line, and a list of them to go to: beside the
// cards on a wide screen, a row across the top on a narrow one. The one being read is marked.
const PREF_GROUPS = [
  ['Reading', [['goalscard', 'Goals'], ['countcard', 'What counts'], ['reviewcard', 'Daily review'], ['readercard', 'Reader'], ['dayscard', 'Days']]],
  ['Look', [['appearcard', 'Appearance'], ['keyscard', 'Keyboard']]],
  ['Connections', [['phonecard', 'Phone'], ['podcard', 'Podcasts'], ['hccard', 'Hardcover'], ['nlcard', 'Newsletters'], ['digestcard', 'Morning email'], ['igcard', 'Instagram'], ['alcard', 'AniList']]],
  ['AI', [['aicard', 'AI']]],
  ['Library', [['tagscard', 'Library tags'], ['importcard', 'Import']]],
  ['Help', [['tipscard', 'Tips'], ['fbcard', 'Feedback']]],
  ['Account', [['acctcard', 'Account']]],
];
function organizePrefs(){
  const page = $('#main .page'); if (!page) return;
  page.classList.add('prefspage');
  const placed = new Set(); let nav = '';
  for (const [group, cards] of PREF_GROUPS) {
    const here = cards.filter(([id]) => $('#' + id)); if (!here.length) continue;
    const head = document.createElement('div'); head.className = 'pgroup'; head.textContent = group;
    page.appendChild(head);
    for (const [id] of here) { page.appendChild($('#' + id)); placed.add(id); }
    nav += '<div class="pnavg">' + esc(group) + '</div>' + here.map(([id, label]) => '<button data-pjump="' + id + '">' + esc(label) + '</button>').join('');
  }
  // a card that's in no group yet keeps its place at the end
  [...page.querySelectorAll(':scope > .card')].filter(c => !placed.has(c.id)).forEach(c => page.appendChild(c));
  const grid = document.createElement('div'); grid.className = 'prefsgrid';
  page.parentNode.insertBefore(grid, page);
  grid.innerHTML = '<nav class="prefsnav" aria-label="Preferences">' + nav + '</nav>';
  grid.appendChild(page);
  const main = $('#main'), links = [...grid.querySelectorAll('[data-pjump]')];
  grid.querySelector('.prefsnav').addEventListener('click', e => {
    const b = e.target.closest('[data-pjump]'); if (!b) return;
    const c = $('#' + b.dataset.pjump); if (c) c.scrollIntoView({ block: 'start', behavior: 'smooth' });
  });
  const mark = () => {
    if (!grid.isConnected) { main.removeEventListener('scroll', mark); return; }
    const top = main.getBoundingClientRect().top + 130;
    let cur = links[0];
    for (const l of links) { const c = $('#' + l.dataset.pjump); if (c && c.getBoundingClientRect().top <= top) cur = l; }
    links.forEach(l => l.classList.toggle('on', l === cur));
    if (cur && innerWidth < 900) { const nv = cur.parentNode; if (cur.offsetLeft < nv.scrollLeft || cur.offsetLeft + cur.offsetWidth > nv.scrollLeft + nv.clientWidth) nv.scrollTo({ left: cur.offsetLeft - 16, behavior: 'smooth' }); }
  };
  main.addEventListener('scroll', mark, { passive: true }); mark();
}
async function drawDevices(token){
  const box = $('#devlist'); if (!box) return;
  const p = await api('/api/phone');
  const label = { kindle:'The Kindle (Daf plugin)', phone:'The phone (Tasker and the widget)', mac:'Daf for Mac', android:'Daf for Android', windows:'Daf for Windows', safari:'Safari extension (connected by Daf for Mac)' };
  const seen = d => 'Connected ' + epochDate(d.created) + (d.last_seen ? ', last used ' + ago(d.last_seen) : ', not used yet'), br = p.devices.find(d => d.name === 'browser');
  box.innerHTML = '<div class="prow"><div class="d"><b>Connected devices</b><span>Each has its own token. Disconnecting one stops it until it connects again.</span></div></div>' +
    p.devices.filter(d => d.name !== 'browser').map(d => '<div class="prow sub"><div class="d"><b>' + esc(label[d.name] || (/^android-./.test(d.name) ? 'Daf for Android · ' + d.name.slice(8).toUpperCase() : /^windows-./.test(d.name) ? 'Daf for Windows · ' + d.name.slice(8).toUpperCase() : d.name)) + '</b><span>' + seen(d) + '</span></div>' +
      '<button class="btn sm" data-act="devoff" data-name="' + esc(d.name) + '">Disconnect</button></div>').join('') +
    // The browser extension (extension/): a token for the device "browser", shown once, pasted into its options.
    '<div class="prow sub"><div class="d"><b>Browser extension</b><span>' + (br ? seen(br) + '. A new token replaces it.' : 'Highlight on any web page and keep it in Daf. Make a token and paste it into the extension’s options.') +
      ' Download it for <a href="/api/extension/daf-extension.zip" download>Chrome or Arc</a> or <a href="/api/extension/daf-extension.xpi" download>Firefox or Zen</a>.</span></div>' +
    '<button class="btn sm" id="brtoken">' + (br ? 'New token' : 'Make a token') + '</button>' + (br ? '<button class="btn sm" data-act="devoff" data-name="browser">Disconnect</button>' : '') + '</div>' +
    (token ? '<div class="kindlenote"><span class="mute tiny">Paste it into the extension’s options now; Daf only shows it once.</span><code class="tok">' + esc(token) + '</code></div>' : '');
  $('#brtoken').onclick = () => api('/api/devices', { method:'POST', body:JSON.stringify({ name:'browser' }) }).then(r => drawDevices(r.token), e => toast(e.message));
}
// Newsletters: senders found in the Proton mailbox (read-only); the ticked ones come into Library → Emails.
async function drawNewsletters(fresh){
  const card = $('#nlcard'); if (!card) return;
  let r;
  try { r = fresh ? Object.assign(await api('/api/newsletters'), await api('/api/newsletters/scan', { method:'POST' })) : await api('/api/newsletters'); }
  catch(e){ card.innerHTML = '<h2>Newsletters</h2><p class="mute" style="margin:0">' + esc(e.message) + '</p>'; return; }
  if (!r.configured) { card.innerHTML = '<h2>Newsletters</h2><p class="mute" style="margin:0">Needs Proton Mail Bridge on the server (the office agent’s PROTON_USER and PROTON_BRIDGE_PASSWORD).</p>'; return; }
  const chosen = new Set(r.chosen || []);
  const row = s => '<label class="nlrow"><input type="checkbox" data-nl="' + esc(s.address) + '"' + (chosen.has(s.address) ? ' checked' : '') + '><span><b>' + esc(s.name) + '</b> <span class="mute tiny">' + esc(s.address) + ' · ' + s.count + ' in 45 days</span><span class="mute tiny nlsub">' + esc(s.last_subject || '') + '</span></span></label>';
  const likely = r.senders.filter(s => s.likely || chosen.has(s.address)), rest = r.senders.filter(s => !s.likely && !chosen.has(s.address));
  card.innerHTML = '<div class="cardh"><h2>Newsletters</h2><button class="linkbtn tiny" data-act="nlscan">Look again</button></div>' +
    '<p class="mute" style="margin:0">Daf reads your Proton mail through Bridge without marking anything read or moving it. Tick the senders whose emails belong in Daf, and their issues come into Library → Emails' + (r.count ? ' (' + r.count + ' so far)' : '') + '. Substack ones may already be in the Feed.</p>' +
    '<input class="field sm" id="nlq" placeholder="Find a sender" autocomplete="off" style="width:100%">' +
    '<div class="nllist" id="nllist">' + likely.map(row).join('') + '</div>' +
    (rest.length ? '<details class="nlmore"><summary class="mute tiny">Other mail with an unsubscribe link (' + rest.length + ')</summary><div class="nllist">' + rest.map(row).join('') + '</div></details>' : '') +
    '<div style="display:flex;justify-content:flex-end;gap:8px;align-items:center"><span class="mute tiny" id="nlstatus"></span><button class="btn primary sm" data-act="nlsave">Save</button></div>';
}
async function drawPod(token){
  const card = $('#podcard'); if (!card) return;
  const p = await api('/api/podcasts');
  const base = ((S.settings || {}).public_url || location.origin).replace(/\/$/, '');
  card.innerHTML = '<h2>Podcasts (AntennaPod)</h2>' +
    '<div class="prow"><div class="d"><b>Sync</b><span>' + (p.last_sync ? 'Last sync ' + ago(p.last_sync) + ', ' + p.subs.length + ' subscriptions.' : 'Not connected yet.') + ' Listening shows on Today but never counts toward the hour.</span></div><button class="btn sm" data-act="podtoken">' + (p.device ? 'New password' : 'Make a password') + '</button></div>' +
    (token ? '<div class="kindlenote"><span class="mute tiny">The AntennaPod password. Daf only shows it once.</span><code class="tok">' + esc(token) + '</code></div>' : '') +
    '<details class="steps"' + (token ? ' open' : '') + '><summary>Set up AntennaPod</summary><ol>' +
    '<li>AntennaPod → Settings → <b>Synchronization</b> → <b>gpodder.net</b>.</li>' +
    '<li>Server: <code>' + esc(base) + '</code> (AntennaPod may insist on https; then use the secure address once it exists). Username: <code>' + esc(S.user || 'reader') + '</code>. Password: the one above.</li>' +
    '<li>Pick or create the device <b>AntennaPod</b>, and let it sync.</li>' +
    '<li>To clip: in an episode, <b>Share → with position</b>, send it to Ezer. The minute before that point comes back transcribed, and lands in Highlights and the vault.</li></ol></details>';
}
async function drawPhone(token){
  const card = $('#phonecard'); if (!card) return;
  const p = await api('/api/phone');
  const s = S.settings || {};
  const phoneDev = p.devices.find(d => d.name === 'phone');
  const n = p.nudges;
  const base = (s.public_url || location.origin).replace(/\/$/, '');
  let h = '<h2>Phone</h2>';
  h += '<div class="prow"><div class="d"><b>The evening nudge</b><span>' + (n.shown ? n.shown + ' shown this week, ' + n.followed + ' followed by reading within 30 minutes.' : 'Nothing shown this week yet.') + '</span></div></div>';
  h += '<div class="prow"><div class="d"><b>Phone token</b><span>' + (phoneDev ? 'Made ' + epochDate(phoneDev.created) + (phoneDev.last_seen ? ', last used ' + ago(phoneDev.last_seen) : '') + '. A new one replaces it.' : 'For Tasker and the widget.') + '</span></div><button class="btn sm" data-act="phonetoken">' + (phoneDev ? 'New token' : 'Make a token') + '</button></div>';
  if (token) h += '<div class="kindlenote"><span class="mute tiny">Copy it now; Daf only shows it once.</span><code class="tok">' + esc(token) + '</code></div>';
  h += '<details class="steps"' + (token ? ' open' : '') + '><summary>Set up the nudge in Tasker</summary><ol>' +
    '<li><b>Profiles → + → Application</b>: tick Instagram, Reddit, X and Discord, then back. Long-press the profile → <b>Add → Time</b>, from 21:00 to 03:00.</li>' +
    '<li>New task, call it <b>Daf nudge</b>. Add <b>Net → HTTP Request</b>: Method <code>GET</code>, URL <code>' + esc(base) + '/api/phone/nudge</code>, Headers <code>Authorization:Bearer ' + esc(token || 'YOUR-TOKEN') + '</code>, and tick <b>Structure Output</b>.</li>' +
    '<li>Add <b>Task → If</b> <code>%http_data.show</code> <b>~</b> <code>true</code>.</li>' +
    '<li>Add <b>Alert → Notify</b>: Title <code>%http_data.title</code>, Text <code>%http_data.text</code>. Under Actions, add <b>Net → Browse URL</b> <code>%http_data.url</code> so tapping it opens Daf.</li>' +
    '<li>Add <b>Task → End If</b>. Daf decides the rest: at most one nudge every 25 minutes, none once the hour is done.</li></ol></details>';
  h += '<div class="prow"><div class="d"><b>Install Daf as an app</b><span>' + (s.public_url ? 'Open ' + esc(s.public_url) + ' on the phone, then the browser menu → Install app. “Save to Daf” then shows up in the share menu.' : 'Needs HTTPS. Run <code>sudo tailscale set --operator=lander</code> on the server once, and Daf gets a secure address on your tailnet.') + '</span></div></div>';
  if (p.inbox.length) h += '<div class="prow"><div class="d"><b>Shared to Daf</b><span>' + p.inbox.slice(0, 5).map(x => esc(x.title || x.url)).join(' · ') + '</span></div></div>';
  card.innerHTML = h;
}
function renderLogin(){
  clearInterval(S.timer);
  $('#app').classList.add('loggedout');
  $('#side').innerHTML = '';
  $('#main').innerHTML = '<div class="login"><form id="loginf"><h1>Daf</h1><p class="mute" style="margin:0">One hour a day, Year 30.</p><label for="lu" class="mute tiny">Username</label><input class="field" id="lu" type="text" autocomplete="username" autocapitalize="none" autocorrect="off" spellcheck="false" required><label for="pw" class="mute tiny">Password</label><input class="field" id="pw" type="password" autocomplete="current-password" required><button class="btn primary" type="submit">Sign in</button><p class="mute tiny" id="loginerr" style="margin:0"></p></form></div>';
  $('#lu').focus();
}

/* ---------- paper ---------- */
function openPaper(){
  const d = S.data;
  const sat = (() => { const t = d ? parseDay(d.today) : new Date(); const back = (t.getDay() + 1) % 7; const s = new Date(t); s.setDate(t.getDate() - back); return s; })();
  const def = d && d.shabbat && new Date().getDay() === 6 ? 'shabbat' : 'today';
  $('#scrim').hidden = false; const m = $('#modal'); m.hidden = false;
  m.innerHTML = '<h2>Log paper minutes</h2><label for="pmin" class="mute tiny">Minutes</label><input class="field" id="pmin" type="number" inputmode="numeric" min="1" max="720" value="30">' +
    '<div class="quick">' + [15,30,45,60,90].map(n => '<button class="btn sm" type="button" data-min="' + n + '">' + n + '</button>').join('') + '</div>' +
    '<span class="mute tiny">Which day</span><div class="seg" role="radiogroup">' + [['today','Today'],['yesterday','Yesterday'],['shabbat','Shabbat, ' + MONTHS[sat.getMonth()] + ' ' + sat.getDate()]].map(x => '<button type="button" role="radio" data-day="' + x[0] + '" class="' + (x[0] === def ? 'on' : '') + '" aria-checked="' + (x[0] === def) + '">' + esc(x[1]) + '</button>').join('') + '</div>' +
    '<label for="ppages" class="mute tiny">Pages (optional, for a page goal)</label><input class="field" id="ppages" type="number" inputmode="numeric" min="0" max="2000" placeholder="0">' +
    '<label for="pnote" class="mute tiny">Note (optional)</label><input class="field" id="pnote" placeholder="What you read">' +
    '<div style="display:flex;gap:8px;justify-content:flex-end"><button class="btn" data-act="close">Cancel</button><button class="btn primary" data-act="savepaper">Log it</button></div>' +
    '<span class="mute tiny">Goes into Reference/reading/Reading Log ' + (d ? d.today.slice(0, 4) : '') + '.md in the vault.</span>';
  const i = $('#pmin'); i.focus(); i.select();
}
function closeModal(){ const m = $('#modal'); m.hidden = true; $('#scrim').hidden = true; m.classList.remove('wide', 'sheet'); m.onclick = m.onkeydown = null; }

/* ---------- what's kept here first ---------- */
// A page's data, the copy kept on this device at once (the service worker's cache, which this also
// fills), then the network's: if that brings something new, the page is drawn again, in place, unless
// you've started doing something on it. Through the public address each read costs a few hundred
// milliseconds; this way a page appears at once and catches up a moment later.
const DATA_CACHE = 'daf-data-v1';
async function swr(path){
  const url = new URL(path, location.href).href;
  if (S.swrPaths) S.swrPaths.add(path);
  let kept = null;
  try { if (window.caches) { const m = await (await caches.open(DATA_CACHE)).match(url); if (m) kept = await m.json(); } } catch(e){}
  const fresh = api(path).then(d => {
    try { if (window.caches) caches.open(DATA_CACHE).then(c => c.put(url, new Response(JSON.stringify(d), { headers: { 'Content-Type': 'application/json' } }))); } catch(e){}
    return d;
  });
  if (!kept) return fresh;
  fresh.then(d => { if (JSON.stringify(d) !== JSON.stringify(kept)) window.dispatchEvent(new CustomEvent('daf-fresh', { detail: { path, data: d } })); }).catch(() => {});
  return kept;
}
['pointerdown', 'keydown', 'input'].forEach(ev => document.addEventListener(ev, () => { S.actedAt = Date.now(); }, true));
window.addEventListener('daf-fresh', e => {
  const { path, data } = e.detail;
  if (path === '/api/today') { S.data = data; renderSide(); if (S.route[0] === 'today' && !busy()) renderToday(); return; }
  if (!S.swrPaths || !S.swrPaths.has(path) || busy()) return;     // another page now, or you're in the middle of something
  const y = $('#main').scrollTop; show(true);
  requestAnimationFrame(() => setTimeout(() => { $('#main').scrollTop = y; }, 60));
});
// In the middle of something: a menu, a sheet, the highlight bar, a field, or a tap since it was drawn.
const busy = () => !$('#modal').hidden || !$('#pop').hidden || ($('#selbar') && !$('#selbar').hidden) || ($('#palette') && !$('#palette').hidden) ||
  /^(input|textarea|select)$/i.test((document.activeElement || {}).tagName || '') || (S.actedAt && S.actedAt > S.shownAt);

/* ---------- routing & loading ---------- */
async function load(quiet){
  try {
    S.data = await swr('/api/today');
    if (window.DafCore.Themes) window.DafCore.Themes.fromSettings(S.data.settings);    // the theme chosen on another device
    if (window.DafCore.Keys) window.DafCore.Keys.set(S.data.settings.keys);             // and the keys
    renderSide();
    if (S.route[0] === 'today' && !quiet) renderToday();
    if (!S.y29) { S.y29 = await api('/api/year/29'); if (S.route[0] === 'today' && !quiet) renderToday(); }
  } catch(e) { if (e.message !== 'signed out') toast(e.message); }
}
function show(quiet){
  if (!quiet) S.navs = (S.navs || 0) + 1;     // pages shown since Daf loaded: is there a Daf page to go back to? (leaveDoc in reader.js)
  S.swrPaths = new Set(); S.shownAt = Date.now(); S.actedAt = 0;
  const m = $('#main'); if (!quiet) { m.classList.add('enter'); clearTimeout(S.enterT); S.enterT = setTimeout(() => m.classList.remove('enter'), 1500); }
  S.route = route(); renderSide();
  const v = S.route[0];
  const run = p => p.catch(e => { if (e.message !== 'signed out') toast(e.message); });
  if (v === 'review') run(renderReview(S.route.slice(1)));
  else if (v === 'highlights') run(renderHighlights());
  else if (v === 'books') run(renderBooks());
  else if (v === 'book') { const last = S.route[S.route.length - 1] || '', hl = last.startsWith('hl:') && S.route.length > 2 ? decodeURIComponent(last.slice(3)) : null; run(renderBook(decodeURIComponent(S.route.slice(1, hl ? -1 : undefined).join('/')), hl)); }
  else if (v === 'sources') run(renderSources());
  else if (v === 'prefs') run(renderPrefs().then(() => { if (window.DafCore.Themes) { window.DafCore.Themes.section($('#appearcard')); if (S.route[1] === 'appearance') $('#appearcard').scrollIntoView({ block: 'start' }); }
    if (window.DafCore.Goals) window.DafCore.Goals.prefs().then(() => { if (S.route[1] === 'goals') { const g = $('#goalscard'); if (g) g.scrollIntoView({ block: 'start' }); } }); drawPhone(); drawPod(); drawDevices(); if (window.DafCore.HC) window.DafCore.HC.prefs($('#hccard')); drawNewsletters(); prefsMore(); Voices.cur = (S.settings && S.settings.tts_voice) || 'af_heart'; return Voices.load(); }).then(all => { const sel = $('#ttsvoice'); if (sel && all.length) { const cur = sel.value; sel.innerHTML = all.map(x => '<option value="' + esc(x) + '"' + (x === cur ? ' selected' : '') + '>' + esc(Voices.label(x)) + '</option>').join(''); } }));
  else if (window.DafCore.views[v]) run(Promise.resolve(window.DafCore.views[v](S.route.slice(1))));
  else if (v === 'ebook') { window.addEventListener('daf-ebook-ready', show, { once:true }); return; }   // the reader module is still loading
  else if (v === 'pdf') { window.addEventListener('daf-pdf-ready', show, { once:true }); return; }       // so is the PDF view
  else if (!window.DafCore.views[v]) { S.route = ['today']; renderToday(); if (S.goalsChanged) { S.goalsChanged = false; load(); } }
  if (!quiet) $('#main').scrollTop = 0;
  document.body.dataset.view = S.route[0];
  railMode();
}

// The cards from their own files, and #prefs/<card> scrolls to one.
function prefsMore(){
  const D = window.DafCore, cards = { keys: [D.Keys, 'keyscard'], ai: [D.AI, 'aicard'], digest: [D.Digest, 'digestcard'], import: [D.Imports, 'importcard'], feedback: [D.Feedback, 'fbcard'], tags: [D.TagMan, 'tagscard'], tips: [D.Tips, 'tipscard'], instagram: [D.Social, 'igcard'], anilist: [D.AniList, 'alcard'] };
  for (const [name, [mod, id]] of Object.entries(cards)) {
    const card = $('#' + id); if (!mod || !card) continue;
    // The cards above it are still loading and push it down: once more after they've come.
    Promise.resolve(mod.prefs(card)).then(() => { if (S.route[1] === name) { card.scrollIntoView({ block: 'start' }); setTimeout(() => { if (S.route[1] === name) card.scrollIntoView({ block: 'start' }); }, 900); } }).catch(e => { card.innerHTML = '<h2>' + esc(card.querySelector('h2') ? card.querySelector('h2').textContent : '') + '</h2><p class="mute">' + esc(e.message) + '</p>'; });
  }
}
let noteTimers = {};
document.addEventListener('input', e => {
  const t = e.target;
  if (t.id === 'hlq') { S.hlq = t.value; clearTimeout(S.hlqT); S.hlqT = setTimeout(() => drawHighlights().catch(err => toast(err.message)), 250); }
  if (t.dataset.note) {
    const id = t.dataset.note; clearTimeout(noteTimers[id]);
    noteTimers[id] = setTimeout(async () => { try { await api('/api/highlights/' + encodeURIComponent(id) + '/note', { method:'PUT', body:JSON.stringify({ note:t.value }) }); toast(t.value.trim() ? 'Note saved to the vault' : 'Note removed'); } catch(err){ toast(err.message); } }, 900);
  }
});
// What the popover held when this click began. A menu opened by this same click, from any script,
// stays open; one that was already open closes when you click elsewhere (reader.js).
// The menu (#pop) closes on a click outside it (reader.js), on a tap in a book's page (book.js: the
// page is its own frame), and on its own button again: Aa, …, as menus do.
const popKey = t => { const b = t && t.closest && t.closest('[data-bk],[data-ract],[data-act]'); return b && !b.closest('#pop') ? ['bk', 'ract', 'act'].map(k => b.dataset[k] || '').join('|') : null; };
document.addEventListener('click', e => {
  const p = $('#pop'), k = popKey(e.target);
  if (!p.hidden && k && k === S.popKey) { p.hidden = true; S.popKey = null; e.stopPropagation(); e.preventDefault(); return; }
  S.popAtClick = p.hidden ? null : p.innerHTML;
  const before = S.popAtClick;
  setTimeout(() => { if (p.hidden) S.popKey = null; else if (k && p.innerHTML !== before) S.popKey = k; }, 0);
}, true);
document.addEventListener('click', async e => {
  const go = e.target.closest('[data-go]');
  if (go){ $('#side').classList.remove('open'); location.hash = go.dataset.go; return; }
  const more = e.target.closest('[data-act="more"],[data-act="rail"]'); if (more){ $('#side').classList.toggle('open'); return; }
  // Outside the sheet or the tablet's drawer, or on the drawer's shade (the sidebar element itself), closes it.
  if ($('#side').classList.contains('open') && (!e.target.closest('#side') || e.target.id === 'side')) $('#side').classList.remove('open');
  const q = e.target.closest('[data-min]'); if (q){ $('#pmin').value = q.dataset.min; return; }
  const hs = e.target.closest('[data-hlsrc]'); if (hs){ S.hlSource = hs.dataset.hlsrc; drawHighlights(); return; }
  const hc = e.target.closest('[data-hlcolor]'); if (hc){ S.hlColor = S.hlColor === hc.dataset.hlcolor ? '' : hc.dataset.hlcolor; drawHighlights(); return; }
  const gr = e.target.closest('[data-grade]'); if (gr){ cardGrade(gr.dataset.grade); return; }
  const qo = e.target.closest('q[data-open]'); if (qo && !window.getSelection().toString()){ location.hash = qo.dataset.open.slice(1); return; }
  const dy = e.target.closest('[data-day]'); if (dy){ dy.parentNode.querySelectorAll('button').forEach(b => { b.classList.toggle('on', b === dy); b.setAttribute('aria-checked', b === dy); }); return; }
  const a = e.target.closest('[data-act]'); if (!a) return;
  const act = a.dataset.act;
  try {
    if (act === 'paper') openPaper();
    else if (act === 'close') closeModal();
    else if (act === 'bookfreq'){ await api('/api/books/' + encodeURIComponent(a.dataset.id) + '/review', { method:'PUT', body:JSON.stringify({ freq: a.dataset.f }) }); toast({ more:'More often in the daily review', normal:'As usual in the daily review', less:'Less often in the daily review', never:'Out of the daily review' }[a.dataset.f]); renderBook(a.dataset.id); }
    else if (act === 'refresh'){ a.disabled = true; await api('/api/sync', { method:'POST' }); await load(); if (S.route[0] === 'sources') await renderSources(); toast('Synced'); a.disabled = false; }
    else if (act === 'savepaper'){
      const minutes = parseInt($('#pmin').value, 10); const day = ($('#modal .seg .on') || {}).dataset; const note = $('#pnote').value.trim();
      if (!(minutes >= 1 && minutes <= 720)) { toast('Minutes should be between 1 and 720'); return; }
      const pages = parseInt($('#ppages').value, 10) || 0;
      if (pages < 0 || pages > 2000) { toast('Pages should be between 0 and 2000'); return; }
      const body = { minutes, note, pages };
      if (day && day.day === 'shabbat') { body.shabbat = true; if (!note) body.note = 'Shabbat'; }
      if (day && day.day === 'yesterday') { const t = parseDay(S.data.today); t.setDate(t.getDate() - 1); body.date = isoOf(t); }
      a.disabled = true;
      const r = await api('/api/paper', { method:'POST', body:JSON.stringify(body) }); closeModal(); toast('Logged ' + minutes + ' min for ' + shortDate(r.date)); await load();
    }
    else if (act === 'logout'){ await api('/api/logout', { method:'POST' }); renderLogin(); }
    else if (act === 'signoutothers'){ if (!confirm('Sign out every other browser?')) return; await api('/api/account/signout-others', { method:'POST' }); toast('Every other browser is signed out'); }
    else if (act === 'rkeep') reviewAct('keep');
    else if (act === 'rless') reviewAct('less');
    else if (act === 'rnote'){ if (S.revNote) reviewAct('note'); else { S.revNote = true; drawReview(); } }
    else if (act === 'rnotecancel'){ S.revNote = false; drawReview(); }
    else if (act === 'standuse'){ await setStand(S.books.suggested.map(b => b.id)); toast('Nightstand set'); renderBooks(); }
    else if (act === 'standoff'){ const ids = (S.data.nightstand || []).map(b => b.id).filter(i => i !== a.dataset.id); await setStand(ids); toast('Off the nightstand'); show(); }
    else if (act === 'standon'){
      const ids = (S.data.nightstand || []).map(b => b.id);
      if (ids.length >= 3) { if (!S.books) S.books = await api('/api/books'); askSwap(a.dataset.id); return; }
      await setStand(ids.concat([a.dataset.id])); toast('On the nightstand'); show();
    }
    else if (act === 'swap'){ const ids = (S.data.nightstand || []).map(b => b.id).map(i => i === a.dataset.out ? a.dataset.in : i); await setStand(ids); closeModal(); toast('Swapped'); show(); }
    else if (act === 'notstand'){ await api('/api/nightstand', { method:'PUT', body:JSON.stringify({ ids:(S.data.nightstand || []).map(b => b.id), not_nightstand:a.dataset.id }) }); await load(); }
    else if (act === 'booksall'){ S.booksAll = true; renderBooks(); }
    else if (act === 'liball'){ S.libAll = true; drawLibrary(''); }
    else if (act === 'hlexport') exportMenu(a);
    else if (act === 'hlreview') { const q = hlQuery(); q.delete('private'); location.hash = 'review/filter/' + encodeURIComponent(q.toString()); }
    else if (act === 'bookexport') { const q = new URLSearchParams(); q.set('book', a.dataset.id); q.set('private', '1'); exportMenu(a, q); }
    else if (act === 'hlfav'){ S.hlFav = !S.hlFav; drawHighlights(); }
    else if (act === 'revagain'){ renderReview(S.route.slice(1)); }
    else if (act === 'hlclear'){ S.hlq = ''; S.hlSource = ''; S.hlColor = ''; S.hlTag = ''; S.hlFav = false; const q = $('#hlq'); if (q) q.value = ''; drawHighlights(); }
    else if (act === 'hlmore'){ S.hlOpen.add(a.dataset.id); drawHighlights(); }
    else if (act === 'rshare'){ const x = S.rev && S.rev.items[S.revIdx]; if (x) window.DafCore.HL.share(x, { title: x.title, author: x.author }); }
    else if (act === 'rnever'){ reviewAct('never'); }
    else if (act === 'rcard'){ const x = S.rev && S.rev.items[S.revIdx]; if (x) window.DafCore.HL.cardEditor(x); }
    else if (act === 'cshow'){ S.revShow = true; drawReview(); }
    else if (act === 'rcopy'){ const x = S.rev && S.rev.items[S.revIdx]; if (x) navigator.clipboard.writeText(x.text).then(() => toast('Copied'), () => {}); }
    else if (act === 'podtoken'){ const r = await api('/api/podcasts/token', { method:'POST' }); await drawPod(r.token); }
    else if (act === 'phonetoken'){ const r = await api('/api/phone/token', { method:'POST' }); await drawPhone(r.token); drawDevices(); }
    else if (act === 'nlscan'){ a.textContent = 'Looking…'; await drawNewsletters(true); }
    else if (act === 'nlsave'){
      const chosen = $$('[data-nl]').filter(x => x.checked).map(x => x.dataset.nl);
      $('#nlstatus').textContent = chosen.length ? 'Bringing in the last month…' : ''; a.disabled = true;
      const r = await api('/api/newsletters', { method:'PUT', body:JSON.stringify({ chosen }) });
      a.disabled = false; $('#nlstatus').textContent = r.error ? r.error : chosen.length ? r.imported + ' new in Library → Emails' : 'No newsletters';
    }
    else if (act === 'devoff'){
      const n = a.dataset.name;
      if (!confirm(n === 'kindle' ? 'Disconnect the Kindle? It stops sending pages and highlights until you make a new token on the server (daf kindle-token kindle) and put it on the Kindle.' : 'Disconnect ' + n + '? It stops until it connects again.')) return;
      await api('/api/devices/' + encodeURIComponent(n), { method:'DELETE' }); toast('Disconnected'); drawDevices(); if (n === 'phone') drawPhone();
    }
    else if (act === 'booknote'){ const v = $('#bnote').value.trim(); if (!v) return; const r = await api('/api/notes', { method:'POST', body:JSON.stringify({ text:v, book_id:a.dataset.id }) }); toast(r.vault === 'written' || r.vault === 'unchanged' ? 'Saved to the vault note' : 'Saved in Daf'); renderBook(a.dataset.id); }
  } catch(err){ if (err.message !== 'signed out') toast(err.message); a.disabled = false; }
});
document.addEventListener('change', async e => {
  const t = e.target;
  try {
    if (t.dataset.count){ await api('/api/settings', { method:'PUT', body:JSON.stringify({ count:{ [t.dataset.count]: t.checked } }) }); S.y29 = null; toast('Saved'); load(); }
    if (t.id === 'tz'){ await api('/api/settings', { method:'PUT', body:JSON.stringify({ home_tz:t.value }) }); S.y29 = null; toast('Days now follow ' + t.value); load(); }
    if (t.id === 'ttsvoice'){ await Voices.set(t.value); toast('Reading in ' + Voices.label(t.value)); }
    if (t.id === 'volkeys'){ lsSet('volumeKeys', t.checked); window.dispatchEvent(new Event('daf-reading')); toast(t.checked ? 'The volume buttons turn pages, unless something is playing' : 'The volume buttons only change the volume'); }
    if (t.id === 'ttsspeed'){ await api('/api/settings', { method:'PUT', body:JSON.stringify({ tts_speed:parseFloat(t.value) }) }); toast('Read-aloud at ' + t.value + '×'); }
    if (t.id === 'expire'){ await api('/api/settings', { method:'PUT', body:JSON.stringify({ feed_expire_days:parseInt(t.value, 10) }) }); const w = FEED_WINDOWS.find(x => x[0] === +t.value); toast(+t.value === 3650 ? 'The Feed keeps unread items until you read them' : 'The Feed lets go after ' + (w ? w[1] : t.value + ' days') + (+t.value > 30 ? '. Older unread items come in on the next sync.' : '')); }
    if (t.id === 'revsize'){ await api('/api/settings', { method:'PUT', body:JSON.stringify({ review_size:parseInt(t.value, 10) }) }); toast('From tomorrow: ' + t.value + ' a day'); }
    if (t.id === 'hlpriv'){ S.hlPrivate = t.checked; drawHighlights(); }
    if (t.id === 'autoadv'){ lsSet('autoAdvance', t.checked); toast(t.checked ? 'Done and Later open the next item' : 'Done and Later go back to the list'); }
    if (t.id === 'hltag'){ S.hlTag = t.value; drawHighlights(); }
    if (t.id === 'hlsort'){ S.hlSort = t.value; drawHighlights(); }
  } catch(err){ toast(err.message); }
});
let libT = null;
document.addEventListener('input', e => { if (e.target.id !== 'nlq') return; const q = e.target.value.toLowerCase(); $$('.nlrow').forEach(r => { r.hidden = q && !r.textContent.toLowerCase().includes(q); }); const d = $('.nlmore'); if (d && q) d.open = true; });
document.addEventListener('input', e => { if (e.target.id === 'libq') { clearTimeout(libT); libT = setTimeout(() => drawLibrary(e.target.value.trim()), 200); } });
document.addEventListener('submit', async e => {
  if (e.target.id !== 'acctf') return; e.preventDefault();
  const u = $('#au').value.trim().toLowerCase(), np = $('#anp').value, cp = $('#acp').value;
  if (u === (S.user || '') && !np) { toast('Nothing to change'); return; }
  try {
    const r = await api('/api/account', { method:'POST', body:JSON.stringify({ current:cp, user:u !== S.user ? u : '', password:np }) });
    S.user = r.user; toast(r.signed_out_others ? 'Saved. Other browsers are signed out.' : 'Saved'); renderPrefs().then(() => { drawPhone(); drawPod(); drawDevices(); });
  } catch(err){ toast(err.message); }
});
document.addEventListener('submit', async e => {
  if (e.target.id !== 'loginf') return; e.preventDefault();
  try { await api('/api/login', { method:'POST', body:JSON.stringify({ user:$('#lu').value, password:$('#pw').value }) }); $('#app').classList.remove('loggedout'); start(); }
  catch(err){ $('#loginerr').textContent = err.message; }
});
document.addEventListener('keydown', e => {
  const tag = (e.target.tagName || '').toLowerCase(), typing = tag === 'input' || tag === 'textarea' || tag === 'select';
  // A sheet in front takes the keys: Esc closes it and nothing else (not the article behind it too),
  // and no shortcut reaches the list or article under it. keys.js's own capture comes first.
  if (!$('#modal').hidden){ if (e.key === 'Escape') { closeModal(); e.stopImmediatePropagation(); } else if (!typing) e.stopImmediatePropagation(); if (e.key === 'Enter' && tag === 'input' && $('[data-act="savepaper"]')) { e.preventDefault(); $('[data-act="savepaper"]').click(); } return; }
  const look = $('#lookpop'); if (look && !look.hidden && e.key === 'Escape') { look.hidden = true; e.stopImmediatePropagation(); return; }
  if (S.route[0] === 'review' && S.rev && S.rev.items[S.revIdx] && S.rev.items[S.revIdx].card && !typing){
    if (e.metaKey || e.ctrlKey || e.altKey) return;
    if (!S.revShow && (e.key === ' ' || e.key === 'Enter')) { e.preventDefault(); S.revShow = true; drawReview(); }
    else if (S.revShow && '1234'.includes(e.key)) cardGrade(['again', 'hard', 'good', 'easy'][+e.key - 1]);
    return;
  }
  // Pages without shortcuts of their own still answer ?: the ones that work everywhere.
  if (!typing && e.key === '?' && !e.metaKey && !e.ctrlKey && !e.altKey && window.DafCore.Keys &&
      ['today', 'highlights', 'books', 'book', 'stats', 'prefs', 'sources', 'torah', 'recovery', 'podcasts', 'paper', 'manga', 'shelves', 'shelf'].includes(S.route[0])) {
    e.preventDefault(); window.DafCore.Keys.sheet('general'); return;
  }
  if (S.route[0] === 'review'){
    if (typing){ if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) { e.preventDefault(); reviewAct('note'); } if (e.key === 'Escape') { S.revNote = false; drawReview(); } return; }
    if (e.metaKey || e.ctrlKey || e.altKey) return;
    const is = a => window.DafCore.Keys.is(e, 'review', a);
    if (is('keep')) reviewAct('keep');
    else if (is('less')) reviewAct('less');
    else if (is('note')) { e.preventDefault(); S.revNote = true; drawReview(); }
    else if (is('open')) { const x = S.rev && S.rev.items[S.revIdx]; if (x && x.open) location.hash = x.open.slice(1); }
    else if (is('never')) reviewAct('never');
    else if (is('fav')) { const b = $('.rcard [data-hra="fav"]'); if (b) b.click(); }
    else if (e.key === '?') { e.preventDefault(); window.DafCore.Keys.sheet('review'); }
  }
});
$('#scrim').addEventListener('click', closeModal);
/* ---------- a newer Daf ---------- */
// The apps keep their window for days, so a page can outlive an update by a long way (the service
// worker has the new files, but this page runs the old ones). The page asks which version is live
// a little after it starts and every half hour; a newer one loads the next time you go somewhere
// outside a reader, or when you come back to Daf after a while away, unless something is playing
// or half typed. The place in the address stays.
const MYVER = (document.querySelector('meta[name="daf-version"]') || {}).content || '';
let awayAt = 0, freshing = false;
const settled = () => !['read', 'ebook', 'mread', 'paper'].includes(route()[0]) && !busy() && !document.body.classList.contains('playing') && !$('#bplayer');
function newer(now){
  if (!MYVER || !navigator.onLine) return;
  if (S.stale) { if (now && settled()) fresh(); return; }
  fetch('/api/health', { cache: 'no-store', credentials: 'same-origin' }).then(r => r.json()).then(h => {
    if (!h || !h.version || h.version === MYVER) return;
    S.stale = true;
    if (now && settled()) fresh();
  }).catch(() => {});
}
// The service worker takes the new files first (a new one installs and takes over), then the page reloads onto them.
function fresh(){
  if (freshing) return; freshing = true;
  const go = () => location.reload();
  const sw = navigator.serviceWorker;
  if (!sw || !sw.controller) { go(); return; }
  let done = false; const once = () => { if (!done) { done = true; go(); } };
  sw.addEventListener('controllerchange', once);
  setTimeout(once, 15000);
  sw.getRegistration().then(r => r ? r.update().then(() => { if (!r.installing && !r.waiting) once(); }) : once()).catch(once);
}
document.addEventListener('visibilitychange', () => {
  if (document.hidden) { awayAt = Date.now(); return; }
  if (awayAt && Date.now() - awayAt > 30000) newer(true);
});
setTimeout(() => newer(false), 8000);
setInterval(() => { if (!document.hidden) newer(false); }, 30 * 60000);
window.addEventListener('hashchange', () => { show(); if (S.stale && settled()) fresh(); });

window.DafCore = { api, swr, outbox, keepOffline, errs: ERRS, esc, toast, $, $$, epochDate, ago, shortTitle, shortDate, cover, bar, ring, bookRow, I, S, renderSide, load, closeModal, hlCard, colorDots, HL_COLORS, drawHighlights: () => drawHighlights(), views: {}, navExtra: null, Voices };
window.addEventListener('daf-hl-changed', () => { if (S.route[0] === 'review' && S.rev) drawReview(); });

async function start(){
  const me = await fetch('/api/me', { credentials:'same-origin' }).then(r => r.json()).catch(() => ({}));
  if (!me.signed_in) { renderLogin(); return; }
  // AniList's sign-in coming back (anilist.py), when an older offline copy of Daf answered /anilist
  if (/access_token=/.test(location.hash)) {
    const p = new URLSearchParams(location.hash.slice(1));
    history.replaceState(null, '', '/#prefs/anilist');
    try { await api('/api/anilist/token', { method: 'POST', body: JSON.stringify({ access_token: p.get('access_token'), expires_in: p.get('expires_in') }) }); }
    catch(e){ toast('AniList: ' + e.message); }
  }
  S.user = me.user;
  S.route = route(); renderSide(); show(); await load();
  clearInterval(S.timer);
  S.timer = setInterval(() => { if (!document.hidden && S.route[0] === 'today') load(); }, 60000);
}
if ('serviceWorker' in navigator) navigator.serviceWorker.register('/sw.js').catch(() => {});
start();
})();
