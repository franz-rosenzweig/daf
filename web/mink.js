/* Ink on manga: what's drawn on a page with a pen in the manga reader (mreader.js), the pens being
   pens.js. Each stroke keeps its page's number and its points and width in thousandths of the
   page's width, from its top left corner, so it stays on the drawing however the page is shown:
   zoomed, fitted to the screen, its width or its height, alone or beside its pair, split in halves,
   in a long strip, its borders cropped or not. Each picture of a page on screen has a layer over it
   (an SVG in the page's own units) that moves with it.
   The volume's strokes come with it (daf/ink.py keeps them), go back in one request a moment after
   they're drawn or erased, wait in the outbox offline, and show on every device. Fingers still turn,
   scroll and zoom; only the pen draws, and a hand on the glass while the pen is near does nothing.
   Underlines don't become highlights here: there are no words to highlight. */
(function(){
'use strict';
const C = window.DafCore, Pens = C.Pens, M = C.Manga || (C.Manga = {});
const { api, toast } = C;
const NS = 'http://www.w3.org/2000/svg';
const INK = '#1e1e1e';                       // 'ink' on a page of a manga: the page's own black
const K = { book: null, strokes: [], ver: new Map(), done: [], undone: [], q: { book: null, add: new Map(), remove: new Set() }, crops: new Map(), raf: 0, prev: null };
const r1 = v => Math.round(v * 10) / 10;
const newId = () => { const b = new Uint8Array(10); crypto.getRandomValues(b); return 'k' + Array.from(b, x => x.toString(16).padStart(2, '0')).join(''); };
const RD = () => (M.reader && M.reader()) || null;
const live = () => { const r = RD(); return !!(r && K.book && r.book.id === K.book && r.el.isConnected); };
const onPage = n => K.strokes.filter(s => s.at && s.at.pg === n + 1);
const bump = n => K.ver.set(n, (K.ver.get(n) || 0) + 1);

/* ---------- where a page is ---------- */
// The pictures of pages on screen (a page, or half of one), and each one's page (from 0).
const pictures = () => { const r = RD(); return r ? [...r.el.querySelectorAll('#mstage .mpg[data-n], #mstage .mhalf')] : []; };
const numOf = el => +(el.dataset.n != null ? el.dataset.n : el.closest('[data-n]').dataset.n);
const halfOf = el => el.classList.contains('mhalf') ? (/^right/.test(el.style.backgroundPosition) ? 'R' : 'L') : null;
const seen = el => { const r = el.getBoundingClientRect(); return r.width > 0 && r.right > 0 && r.left < innerWidth && r.bottom > 0 && r.top < innerHeight; };
// object-position as fractions (Chrome says "100% 50%"; keywords to be sure)
function anchor(v){
  const k = { left: 0, top: 0, center: 0.5, right: 1, bottom: 1 };
  const [a, b] = String(v || '50% 50%').split(/\s+/);
  const f = x => x in k ? k[x] : /%$/.test(x || '') ? parseFloat(x) / 100 : 0.5;
  return [f(a), f(b == null ? 'center' : b)];
}
// A page's box from its picture's box (l, t, w, h: in the window, or in the picture's parent): the
// picture fitted inside a bigger box where object-fit says, a half made whole, cropped borders
// put back. → { pic: where the picture is, l, t: the page's corner, u: pixels to a thousandth of its width }
function boxOf(el, win){
  const n = numOf(el), p = (RD().book.pages || [])[n] || {}, crop = RD().p.crop ? K.crops.get(n) : null, c = Array.isArray(crop) ? crop : [0, 0, 1, 1];
  let l, t, w, h;
  if (win) { const r = el.getBoundingClientRect(); l = r.left; t = r.top; w = r.width; h = r.height; }
  else { l = el.offsetLeft; t = el.offsetTop; w = el.offsetWidth; h = el.offsetHeight; }
  if (el.tagName === 'IMG') {
    const cs = getComputedStyle(el);
    if (cs.objectFit === 'contain' && w && h) {
      const ar = el.naturalWidth && el.naturalHeight ? el.naturalHeight / el.naturalWidth : p.w && p.h ? (p.h * (c[3] - c[1])) / (p.w * (c[2] - c[0])) : h / w;
      let pw = w, ph = w * ar; if (ph > h) { ph = h; pw = h / ar; }
      const [fx, fy] = anchor(cs.objectPosition);
      l += (w - pw) * fx; t += (h - ph) * fy; w = pw; h = ph;
    }
  }
  const pic = { l, t, w, h }, side = halfOf(el);
  if (side) { if (side === 'R') l -= w; w *= 2; }                // the half shown, and the page it's half of
  const pw = w / (c[2] - c[0]), ph = h / (c[3] - c[1]);
  return { pic, l: l - c[0] * pw, t: t - c[1] * ph, u: pw / 1000, clip: !!side || c[0] > 0 || c[1] > 0 || c[2] < 1 || c[3] < 1 };
}
// The page a pen came down on: the picture under it, or in the margin round the pages, the nearest one.
function pictureAt(x, y){
  const hit = document.elementFromPoint(x, y), el = hit && hit.closest && hit.closest('#mstage .mpg[data-n], #mstage .mhalf');
  if (el) return el;
  let best = null, bd = Infinity;
  for (const e of pictures().filter(seen)) {
    const b = e.getBoundingClientRect(), d = Math.hypot(Math.max(0, b.left - x, x - b.right), Math.max(0, b.top - y, y - b.bottom));
    if (d < bd) { bd = d; best = e; }
  }
  return best;
}
// With Crop borders on, where each page's cropped picture sits on the whole page (the server notes it).
function cropOf(n){
  if (K.crops.has(n)) return;
  const book = K.book; K.crops.set(n, 'asking');
  api('/api/manga/books/' + encodeURIComponent(book) + '/crop/' + (n + 1)).then(r => {
    if (K.book !== book) return;
    K.crops.set(n, Array.isArray(r && r.box) ? r.box : [0, 0, 1, 1]); bump(n); later();
  }, () => { if (K.book === book) K.crops.delete(n); });     // offline: asked again next time
}
const cropReady = n => !RD().p.crop || Array.isArray(K.crops.get(n));

/* ---------- drawing ---------- */
// Each picture's layer: an SVG over it, in the page's units, its strokes drawn on it.
function drawOn(el){
  const n = numOf(el), list = onPage(n);
  let o = el.__mink;
  if (!list.length || !cropReady(n)) { if (!list.length && o) { o.svg.remove(); el.__mink = null; } if (RD().p.crop) cropOf(n); return; }
  if (!o || !o.svg.isConnected) {
    const svg = document.createElementNS(NS, 'svg'); svg.setAttribute('class', 'minklayer'); svg.setAttribute('aria-hidden', 'true'); svg.setAttribute('preserveAspectRatio', 'none');
    el.after(svg);
    o = el.__mink = { svg, layer: Pens.layer(svg, false, INK), ver: -1, els: new Map() };
  }
  const b = boxOf(el, false), u = b.u || 1, pic = b.pic;
  Object.assign(o.svg.style, { left: pic.l + 'px', top: pic.t + 'px', width: pic.w + 'px', height: pic.h + 'px', overflow: b.clip ? 'hidden' : 'visible' });
  o.svg.setAttribute('viewBox', [r1((pic.l - b.l) / u), r1((pic.t - b.t) / u), r1(pic.w / u), r1(pic.h / u)].join(' '));
  const v = K.ver.get(n) || 0;
  if (o.ver === v) return;
  o.ver = v; o.layer.clear(); o.els.clear();
  for (const s of list) { try { o.els.set(s.id, o.layer.add(s, s.pts, 1)); } catch(e){} }
}
function sync(){
  K.raf = 0;
  if (!live()) return;
  for (const el of pictures()) drawOn(el);
}
const later = () => { if (!K.raf) K.raf = requestAnimationFrame(sync); };

/* ---------- a stroke drawn, erased ---------- */
// A stroke as it's kept: the pen, its page's number, its points and width in the page's units.
function make(L, el){
  const b = boxOf(el, true), u = b.u || 1, br = L.brush;
  const s = { id: newId(), v: 2, tool: br.pen, color: br.color, size: r1(br.w / u), o: Math.round(br.opacity * 100) / 100, at: { pg: numOf(el) + 1 },
              pts: L.pts.map(p => [r1((p[0] - b.l) / u), r1((p[1] - b.t) / u), Math.round(p[2] * 100) / 100]) };
  if (L.snapped) s.sh = 1;
  return s;
}
function stroke(L){
  const el = pictureAt(L.pts[0][0], L.pts[0][1]); if (!el) return;
  const n = numOf(el), add = () => { const s = make(L, el); K.strokes.push(s); bump(n); later(); act({ add: [s] }); return s; };
  if (cropReady(n)) return add();
  cropOf(n);                                            // its crop isn't known yet: the stroke waits for it
  const wait = setInterval(() => {
    if (!live()) { clearInterval(wait); return; }
    if (Array.isArray(K.crops.get(n))) { clearInterval(wait); add(); }
    else if (!K.crops.has(n)) { clearInterval(wait); K.crops.set(n, [0, 0, 1, 1]); add(); K.crops.delete(n); }   // offline: as if uncropped
  }, 80);
}
function near(pts, x, y, r){
  for (let i = 0; i < pts.length; i++) {
    const a = pts[i], b = pts[i + 1] || a, dx = b[0] - a[0], dy = b[1] - a[1], l = dx * dx + dy * dy;
    const t = l ? Math.max(0, Math.min(1, ((x - a[0]) * dx + (y - a[1]) * dy) / l)) : 0;
    if (Math.hypot(x - a[0] - t * dx, y - a[1] - t * dy) <= r) return true;
  }
  return false;
}
const textBox = s => { const n = String(s.text || '').split('\n').length, fs = s.fs || 16, p = s.pts[0]; return [p[0], p[1], p[0] + (s.w || 120), p[1] + n * fs * 1.3 + fs * 0.3]; };
// Whole strokes, or only what's within r of (x, y) (in the window): the stroke breaks there.
function erase(x, y, mode, r, L){
  for (const el of pictures().filter(seen)) {
    const b = boxOf(el, true), u = b.u || 1, px = (x - b.l) / u, py = (y - b.t) / u, n = numOf(el);
    if (b.clip && (x < b.pic.l || x > b.pic.l + b.pic.w || y < b.pic.t || y > b.pic.t + b.pic.h)) continue;   // not on the half or the cropped page shown
    for (const s of onPage(n)) {
      const m = r / u + (s.size || 2.5) / 2, text = Pens.kindOf(s) === 'text';
      if (text) { const q = textBox(s); if (px < q[0] - m || px > q[2] + m || py < q[1] - m || py > q[3] + m) continue; }
      else if (!near(s.pts, px, py, m)) continue;
      K.strokes = K.strokes.filter(t => t !== s); bump(n);
      const mine = L.added.indexOf(s);
      if (mine >= 0) L.added.splice(mine, 1); else L.erased.push(s);
      if (mode !== 'area' || text) continue;
      let run = [];
      const flush = () => { if (run.length >= 2) { const piece = Object.assign({}, s, { id: newId(), pts: run }); K.strokes.push(piece); L.added.push(piece); } run = []; };
      s.pts.forEach(p => { if (Math.hypot(p[0] - px, p[1] - py) <= m) flush(); else run.push(p); });
      flush();
    }
  }
  later();
}
function erased(L){ const a = {}; if (L.erased.length) a.del = L.erased; if (L.added.length) a.add = L.added; if (a.del || a.add) act(a); }
// Everything drawn on the pages in front of you.
function eraseAll(){
  const ns = new Set(pictures().filter(seen).map(numOf)), list = K.strokes.filter(s => ns.has(s.at.pg - 1)); if (!list.length) return;
  take(list); act({ del: list });
  toast((ns.size > 1 ? 'Everything drawn on these pages is erased.' : 'Everything drawn on this page is erased.') + ' Undo brings it back.');
}
function take(list){ const ids = new Set(list.map(s => s.id)); K.strokes = K.strokes.filter(s => !ids.has(s.id)); list.forEach(s => bump(s.at.pg - 1)); later(); }

/* ---------- the lasso ---------- */
function inside(poly, x, y){
  let c = false;
  for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
    const a = poly[i], b = poly[j];
    if ((a[1] > y) !== (b[1] > y) && x < (b[0] - a[0]) * (y - a[1]) / (b[1] - a[1]) + a[0]) c = !c;
  }
  return c;
}
// The strokes the lasso went round, on the pages in front of you (most of their points inside its loop).
function select(loop){
  const out = [];
  for (const el of pictures().filter(seen)) {
    const b = boxOf(el, true), u = b.u || 1, poly = loop.map(p => [(p[0] - b.l) / u, (p[1] - b.t) / u]);
    for (const s of onPage(numOf(el))) {
      if (out.includes(s)) continue;
      if (Pens.kindOf(s) === 'text') { const q = textBox(s); if (inside(poly, (q[0] + q[2]) / 2, (q[1] + q[3]) / 2)) out.push(s); }
      else if (s.pts.filter(p => inside(poly, p[0], p[1])).length >= s.pts.length * 0.6) out.push(s);
    }
  }
  return out;
}
function mark(list, on){ for (const el of pictures()) { const o = el.__mink; if (!o) continue; for (const s of list) { const e = o.els.get(s.id); if (e) e.classList.toggle('held', !!on); } } }
// Their points in the window, for the handwriting reader.
function inkOf(list){
  const out = [];
  for (const s of list) {
    const el = pictures().filter(seen).find(e => numOf(e) === s.at.pg - 1); if (!el) continue;
    const b = boxOf(el, true);
    out.push(s.pts.map(p => [b.l + p[0] * b.u, b.t + p[1] * b.u, p[2]]));
  }
  return out;
}
// The handwriting swapped for typed text saying the same, where it began, about its size.
function typed(list, text){
  const pg = list[0].at.pg; let x1 = Infinity, y1 = Infinity, x2 = -Infinity, y2 = -Infinity;
  for (const s of list) for (const p of (Pens.kindOf(s) === 'text' ? [textBox(s).slice(0, 2), textBox(s).slice(2)] : s.pts)) { x1 = Math.min(x1, p[0]); y1 = Math.min(y1, p[1]); x2 = Math.max(x2, p[0]); y2 = Math.max(y2, p[1]); }
  const lines = text.split('\n').length, first = list.find(Pens.writingOf) || list[0];
  const t = { id: newId(), v: 2, tool: 'text', text, fs: r1(Math.max(8, Math.min(110, (y2 - y1) / lines * 0.62))), w: r1(Math.max(40, x2 - x1)), color: first.color || 'ink', size: 1, o: 1, at: { pg }, pts: [[r1(x1), r1(y1), 0.5]] };
  take(list); K.strokes.push(t); bump(pg - 1); later();
  act({ add: [t], del: list });
}

/* ---------- undo, and sending ---------- */
function act(a){ K.done.push(a); if (K.done.length > 200) K.done.shift(); K.undone = []; apply(a, false); Pens.redraw(); }
function apply(a, back, again){
  const add = back ? a.del : a.add, rm = back ? a.add : a.del;
  if (again || back) {
    if (rm) take(rm);
    if (add) for (const s of add) if (!K.strokes.some(t => t.id === s.id)) { K.strokes.push(s); bump(s.at.pg - 1); }
    later();
  }
  send(add || [], rm || []);
}
function undo(){ const a = K.done.pop(); if (!a) return; K.undone.push(a); apply(a, true); Pens.redraw(); }
function redo(){ const a = K.undone.pop(); if (!a) return; K.done.push(a); apply(a, false, true); Pens.redraw(); }
function send(add, rm){
  if (!K.book || (!add.length && !rm.length)) return;
  if (K.q.book && K.q.book !== K.book) flush();
  K.q.book = K.book;
  for (const s of add) { K.q.remove.delete(s.id); K.q.add.set(s.id, s); }
  for (const s of rm) { K.q.add.delete(s.id); K.q.remove.add(s.id); }
  clearTimeout(K.qT); K.qT = setTimeout(flush, 1200);
}
// What's been drawn in the last moment goes in one request; offline it waits in the outbox.
async function flush(){
  clearTimeout(K.qT);
  const id = K.q.book; if (!id || (!K.q.add.size && !K.q.remove.size)) return;
  const body = { add: [...K.q.add.values()], remove: [...K.q.remove] };
  K.q = { book: null, add: new Map(), remove: new Set() };
  try { await api('/api/manga/books/' + encodeURIComponent(id) + '/ink', { method: 'POST', body: JSON.stringify(body) }); } catch(e){ toast(e.message); }
}

/* ---------- the reader, as a surface for the pens ---------- */
const surface = {
  live,
  takes: (el, doc) => doc === document && !!el.closest('#mreader #mstage') && !el.closest('.mcard2, .mstripend'),
  off: () => [0, 0],
  palm: true,
  ink: () => INK,
  tap: (x, y) => { const r = RD(); if (r && r.tapAt) r.tapAt(x, y); },
  stroke, erase, erased, eraseAll,
  palHost: () => { const r = RD(); return r ? r.el : document.body; },
  canUndo: () => K.done.length > 0, canRedo: () => K.undone.length > 0, undo, redo,
  select, mark, typed, inkOf,
  remove: list => { take(list); act({ del: list }); },
  all: () => { const ns = new Set(pictures().filter(seen).map(numOf)); return K.strokes.filter(s => ns.has(s.at.pg - 1) && Pens.writingOf(s)); },
};
Pens.listen(document, surface);

// The pages change under the layers (a page turned, the mode, a pinch in the strip, a picture come):
// the layers follow.
let mo = null, ro = null;
const PEN = '<svg viewBox="0 0 20 20" aria-hidden="true"><path d="M4 16l.9-3.6 8.4-8.4a1.9 1.9 0 0 1 2.7 2.7l-8.4 8.4z" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/><path d="M12.2 5.1l2.7 2.7" stroke="currentColor" stroke-width="1.6"/></svg>';
M.ink = {
  open(r){
    flush();
    K.book = r.book.id; K.done = []; K.undone = []; K.crops = new Map(); K.ver = new Map();
    // what's waiting in the outbox (drawn offline) is shown as if it had gone
    let list = (r.book.ink || []).slice();
    const path = '/api/manga/books/' + encodeURIComponent(r.book.id) + '/ink';
    for (const x of C.outbox.get()) {
      if (x.path !== path || !x.body) continue;
      for (const s of x.body.add || []) if (!list.some(t => t.id === s.id)) list.push(s);
      const rm = new Set(x.body.remove || []); list = list.filter(t => !rm.has(t.id));
    }
    K.strokes = list.filter(s => s.at && s.at.pg);
    const prev = Pens.surface(); if (prev !== surface) K.prev = prev;
    Pens.use(surface);
    const st = r.el.querySelector('#mstage');
    if (mo) mo.disconnect(); if (ro) ro.disconnect();
    ro = new ResizeObserver(later);
    const PIC = '.mpg[data-n], .mhalf', each = (n, f) => { if (n.nodeType !== 1) return; if (n.matches(PIC)) f(n); n.querySelectorAll(PIC).forEach(f); };
    mo = new MutationObserver(ms => {
      for (const m of ms) m.removedNodes.forEach(n => each(n, el => ro.unobserve(el)));
      for (const el of pictures()) if (!el.__minkSeen) { el.__minkSeen = true; ro.observe(el); }
      later();
    });
    mo.observe(st, { childList: true, subtree: true });
    ro.observe(st);
    for (const el of pictures()) { el.__minkSeen = true; ro.observe(el); }
    r.el.addEventListener('load', later, true);          // a picture come: its size, for object-fit
    // a tap on the pen's tools is theirs, not the reader's (it would turn the page)
    r.el.addEventListener('pointerdown', e => { if (e.target.closest && e.target.closest('.inkpal')) e.stopPropagation(); }, true);
    later();
  },
  close(){
    flush();
    if (mo) mo.disconnect(); if (ro) ro.disconnect(); mo = ro = null;
    K.book = null; K.strokes = [];
    const prev = K.prev; K.prev = null;
    Pens.use(prev && prev.live() ? prev : null);
  },
  // The pens on the bar, once a pen has touched this device: the tools out, or put away.
  button: () => Pens.seen() ? '<button class="mic' + (Pens.on() ? ' on' : '') + '" data-mr="pens" aria-label="Pens" aria-pressed="' + Pens.on() + '" title="Pens">' + PEN + '</button>' : '',
  toggle(){
    Pens.turn(!Pens.on());
    const b = document.querySelector('#mreader .mtop [data-mr="pens"]');
    if (b) { b.classList.toggle('on', Pens.on()); b.setAttribute('aria-pressed', Pens.on()); }
  },
  state: () => ({ book: K.book, strokes: K.strokes.length, done: K.done.length, queued: K.q.add.size + K.q.remove.size, layers: pictures().filter(el => el.__mink && el.__mink.svg.isConnected).length }),
};
document.addEventListener('visibilitychange', () => { if (document.visibilityState === 'hidden') flush(); });
window.addEventListener('pagehide', flush);
})();
