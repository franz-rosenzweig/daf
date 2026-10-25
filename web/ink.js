/* Ink on an article: what's written on it with a pen (the pens themselves are pens.js), in the text
   and beside it, as in a paper book's margins. Over words the highlighter makes a highlight, as
   selecting them does (it's in Highlights and the review); anywhere else it leaves its stroke.
   Each stroke keeps its paragraph and the letter it started on (daf/ink.py), so it stays with its
   words when the type size or the column changes; a note in the margin keeps its distance from the
   column's edge. Margin moves the column over to leave room on the right. */
(function(){
'use strict';
const C = window.DafCore, Pens = C.Pens;
const { api, toast } = C;
const NS = 'http://www.w3.org/2000/svg';
const store = { get(k, d){ try { const v = localStorage.getItem('daf.ink.' + k); return v == null ? d : JSON.parse(v); } catch(e){ return d; } },
                set(k, v){ try { localStorage.setItem('daf.ink.' + k, JSON.stringify(v)); } catch(e){} } };
const K = {
  doc: null, strokes: [], geo: new Map(), done: [], undone: [], q: { doc: null, add: new Map(), remove: new Set() },
  margin: store.get('margin', false), mOn: false, layer: null, svg: null, wrap: null, body: null,
};
const live = () => !!(K.svg && K.svg.isConnected);
const r1 = v => Math.round(v * 10) / 10;
const newId = () => { const b = new Uint8Array(10); crypto.getRandomValues(b); return 'k' + Array.from(b, x => x.toString(16).padStart(2, '0')).join(''); };

/* ---------- where a stroke goes ---------- */
const blocks = () => K.body ? [...K.body.querySelectorAll('[data-i], figure[data-img]')] : [];
const idx = el => el.dataset.i != null ? +el.dataset.i : +el.dataset.img;
const fontOf = el => { const m = K.cache && K.cache.get(el); if (m) return m; const f = parseFloat(getComputedStyle(el).fontSize) || 16; if (K.cache) K.cache.set(el, f); return f; };
// The paragraph a point is in or beside: the one it's level with, else the nearest above or below.
function blockNear(x, y){
  let best = null, bd = Infinity;
  for (const el of blocks()) {
    const r = el.getBoundingClientRect(); if (!r.height) continue;
    const d = y < r.top ? r.top - y : y > r.bottom ? y - r.bottom : 0;
    if (d < bd) { bd = d; best = el; if (!d) break; }
  }
  return best;
}
// A stroke's paragraph: by its number, unless the text there has changed (a fuller copy of the page).
function findBlock(at){
  const el = K.body.querySelector('[data-i="' + at.b + '"], figure[data-img="' + at.b + '"]');
  if (!at.q || (el && el.textContent.trim().startsWith(at.q))) return el;
  return blocks().find(x => x.textContent.trim().startsWith(at.q)) || el;
}
function caret(x, y){
  if (document.caretPositionFromPoint) { const p = document.caretPositionFromPoint(x, y); return p && { node: p.offsetNode, off: p.offset }; }
  if (document.caretRangeFromPoint) { const r = document.caretRangeFromPoint(x, y); return r && { node: r.startContainer, off: r.startOffset }; }
  return null;
}
// The box of a paragraph's letter number c (counted as highlights count, in textContent).
function charRect(el, c){
  const w = document.createTreeWalker(el, NodeFilter.SHOW_TEXT); let n, pos = 0;
  while ((n = w.nextNode())) {
    const len = n.data.length;
    if (c < pos + len) {
      const r = document.createRange(); r.setStart(n, c - pos); r.setEnd(n, c - pos + 1);
      const q = r.getClientRects()[0] || r.getBoundingClientRect();
      return q && (q.width || q.height) ? q : null;
    }
    pos += len;
  }
  return null;
}
// The letter a point is on or beside, if there's one within a line of it.
function charAt(el, x, y){
  const p = caret(x, y); if (!p || p.node.nodeType !== 3 || !el.contains(p.node)) return null;
  const pre = document.createRange(); pre.selectNodeContents(el); pre.setEnd(p.node, p.off);
  let c = pre.toString().length, r = charRect(el, c);
  const before = c > 0 ? charRect(el, c - 1) : null;
  if (before && (!r || (x <= before.right && y >= before.top && y <= before.bottom))) { c--; r = before; }
  if (!r || y < r.top - r.height || y > r.bottom + r.height) return null;
  return { c, r };
}
// A stroke as it's kept: the pen it was written with, its place, and its points from where it
// started (as written: k = 1).
function make(L){
  const [x0, y0] = L.pts[0], el = blockNear(x0, y0); if (!el) return null;
  const br = el.getBoundingClientRect(), b = L.brush;
  const at = { b: idx(el), q: el.textContent.trim().slice(0, 40), w: r1(br.width), h: r1(br.height), f: fontOf(el) };
  const ch = x0 >= br.left && x0 <= br.right && y0 >= br.top - 4 && y0 <= br.bottom + 4 ? charAt(el, x0, y0) : null;
  if (ch) { at.c = ch.c; at.x = r1(x0 - ch.r.left); at.y = r1(y0 - ch.r.top); }
  else { at.x = r1(x0 - br.left); at.y = r1(y0 - br.top); }
  return { id: newId(), v: 2, tool: b.pen, color: b.color, size: r1(b.w), o: Math.round(b.opacity * 100) / 100, at,
           pts: L.pts.map(p => [r1(p[0] - x0), r1(p[1] - y0), Math.round(p[2] * 100) / 100]) };
}
// Where a stroke's first point is now, in the layer, and how much bigger the type is than it was.
// On a letter it goes with the letter. Elsewhere in its paragraph it keeps its share of the
// paragraph's width and height; beside the column it keeps its distance from the column's edge.
function place(s, Lr){
  const a = s.at || {}, el = findBlock(a); if (!el) return null;
  const k = fontOf(el) / (a.f || 16);
  let x = null, y = null;
  if (a.c != null) { const r = charRect(el, a.c); if (r) { x = r.left + a.x * k; y = r.top + a.y * k; } }
  if (x == null) {
    const br = el.getBoundingClientRect(), w = a.w || br.width, h = a.h || br.height;
    x = a.x < 0 ? br.left + a.x * k : a.x > w ? br.right + (a.x - w) * k : br.left + a.x * br.width / w;
    y = a.y < 0 ? br.top + a.y * k : a.y > h ? br.bottom + (a.y - h) * k : br.top + a.y * br.height / h;
  }
  return [x - Lr.left, y - Lr.top, k];
}

/* ---------- drawing ---------- */
function draw(s, Lr){
  Lr = Lr || K.svg.getBoundingClientRect();
  const o = place(s, Lr); if (!o) return;
  const [ox, oy, k] = o, pts = s.pts.map(p => [ox + p[0] * k, oy + p[1] * k, p[2]]);
  K.layer.add(s, pts, k);
  let x1 = Infinity, y1 = Infinity, x2 = -Infinity, y2 = -Infinity;
  for (const p of pts) { if (p[0] < x1) x1 = p[0]; if (p[0] > x2) x2 = p[0]; if (p[1] < y1) y1 = p[1]; if (p[1] > y2) y2 = p[1]; }
  K.geo.set(s.id, { pts, r: (s.size || 2.5) * k / 2, box: [x1, y1, x2, y2] });
}
function render(){
  if (!live()) return;
  K.geo.clear(); K.layer.clear();
  K.layer.hl.style.mixBlendMode = document.documentElement.dataset.mode === 'dark' ? 'screen' : 'multiply';
  const Lr = K.svg.getBoundingClientRect(); K.cache = new Map();
  for (const s of K.strokes) { try { draw(s, Lr); } catch(e){} }
  K.cache = null;
}
const later = () => { cancelAnimationFrame(K.raf); K.raf = requestAnimationFrame(render); };
function unpaint(id){ K.geo.delete(id); if (K.layer) K.layer.remove(id); }
function paint(s){ if (live()) draw(s); }

/* ---------- the eraser ---------- */
function near(pts, x, y, r){
  for (let i = 0; i < pts.length; i++) {
    const a = pts[i], b = pts[i + 1] || a, dx = b[0] - a[0], dy = b[1] - a[1], l = dx * dx + dy * dy;
    const t = l ? Math.max(0, Math.min(1, ((x - a[0]) * dx + (y - a[1]) * dy) / l)) : 0;
    if (Math.hypot(x - a[0] - t * dx, y - a[1] - t * dy) <= r) return true;
  }
  return false;
}
// Whole strokes, or only what's within r of (x, y): the stroke breaks there, into strokes of its own.
function erase(x, y, mode, r, L){
  const Lr = K.svg.getBoundingClientRect(), px = x - Lr.left, py = y - Lr.top;
  for (const [id, g] of [...K.geo]) {
    const b = g.box, m = r + g.r;
    if (px < b[0] - m || px > b[2] + m || py < b[1] - m || py > b[3] + m || !near(g.pts, px, py, m)) continue;
    const s = K.strokes.find(t => t.id === id); if (!s) continue;
    K.strokes = K.strokes.filter(t => t !== s); unpaint(id);
    // a piece made a moment ago by this same eraser just goes; what was there before is kept for Undo
    const mine = L.added.indexOf(s);
    if (mine >= 0) L.added.splice(mine, 1); else L.erased.push(s);
    if (mode !== 'area') continue;
    let run = [];
    const flush = () => { if (run.length >= 2) { const piece = Object.assign({}, s, { id: newId(), pts: run }); K.strokes.push(piece); L.added.push(piece); draw(piece, Lr); } run = []; };
    g.pts.forEach((p, i) => { if (Math.hypot(p[0] - px, p[1] - py) <= m) flush(); else run.push(s.pts[i]); });
    flush();
  }
  const el = document.elementFromPoint(x, y), mk = el && el.closest && el.closest('#docbody mark[data-h]');
  if (mk) L.hls.add(mk.dataset.h);
}
async function erased(L){
  const a = {};
  if (L.erased.length) a.del = L.erased;
  if (L.added.length) a.add = L.added;
  if (L.hls.size && C.Reader) {
    // Highlights the eraser went over go too; Undo brings them back.
    a.unhl = [];
    for (const id of L.hls) { const back = await C.Reader.removeHl(id, true); if (back) a.unhl.push({ id, back }); }
    if (!a.unhl.length) delete a.unhl;
  }
  if (a.del || a.add || a.unhl) act(a);
}
function eraseAll(){ if (!K.strokes.length) return; const all = K.strokes.slice(); K.strokes = []; render(); act({ del: all }); toast('Everything written here is erased. Undo brings it back.'); }

/* ---------- the highlighter over words ---------- */
// Along a line: the words between its ends. Down several lines: from where it started to where
// it stopped, as a selection would be. A ring drawn round something stays a stroke.
function toHighlight(L){
  if (!C.Reader || !L.pts.length) return false;
  const P = L.pts, s = P[0], z = P[P.length - 1];
  const el = blockNear(s[0], s[1]); if (!el || !el.matches('[data-i]')) return false;
  const br = el.getBoundingClientRect(); if (s[0] < br.left - 8 || s[0] > br.right + 8) return false;
  let x1 = Infinity, x2 = -Infinity, y1 = Infinity, y2 = -Infinity;
  for (const p of P) { x1 = Math.min(x1, p[0]); x2 = Math.max(x2, p[0]); y1 = Math.min(y1, p[1]); y2 = Math.max(y2, p[1]); }
  const lh = parseFloat(getComputedStyle(el).lineHeight) || fontOf(el) * 1.6;
  const tall = y2 - y1 > 1.6 * lh;
  if (tall && Math.hypot(z[0] - s[0], z[1] - s[1]) < 0.35 * Math.max(x2 - x1, y2 - y1)) return false;
  let a, b;
  if (!tall) { const ys = P.map(p => p[1]).sort((m, n) => m - n), y = ys[ys.length >> 1]; a = caret(x1 + 2, y); b = caret(x2 - 2, y); }
  else { a = caret(s[0], s[1]); b = caret(z[0], z[1]); }
  if (!a || !b || !K.body.contains(a.node) || !K.body.contains(b.node)) return false;
  const r = document.createRange();
  try {
    r.setStart(a.node, a.off); r.setEnd(a.node, a.off);
    const r2 = document.createRange(); r2.setStart(b.node, b.off);
    if (r.compareBoundaryPoints(Range.START_TO_START, r2) <= 0) r.setEnd(b.node, b.off); else { r.setStart(b.node, b.off); r.setEnd(a.node, a.off); }
  } catch(e){ return false; }
  const sel = window.getSelection(); sel.removeAllRanges(); sel.addRange(r);
  const info = C.Reader.getSel();
  if (!info) { sel.removeAllRanges(); return false; }
  const color = L.brush.color;
  C.Reader.highlight(info, false, true).then(h => { if (h) act({ hl: { id: h.id, info, color } }); });
  return true;
}

/* ---------- undo, and sending ---------- */
function act(a){ K.done.push(a); if (K.done.length > 200) K.done.shift(); K.undone = []; apply(a, false); Pens.redraw(); }
// Does what a records (back = false) or takes it back (true); a highlight's own way for those.
async function apply(a, back, again){
  const add = back ? a.del : a.add, rm = back ? a.add : a.del;
  if (again || back) {
    if (rm) { const ids = new Set(rm.map(s => s.id)); K.strokes = K.strokes.filter(s => !ids.has(s.id)); rm.forEach(s => unpaint(s.id)); }
    if (add) add.forEach(s => { if (!K.strokes.some(t => t.id === s.id)) { K.strokes.push(s); paint(s); } });
  }
  send(add || [], rm || []);
  if (K.doc) K.doc.ink = K.strokes;
  if (a.hl && (back || again) && C.Reader) {
    if (back) await C.Reader.removeHl(a.hl.id, true);
    else { try { localStorage.setItem('daf.hlColor', JSON.stringify(a.hl.color)); } catch(e){} const h = await C.Reader.highlight(a.hl.info, false, true); if (h) a.hl.id = h.id; }
  }
  if (a.unhl && (back || again) && C.Reader) {
    for (const u of a.unhl) {
      if (back) await u.back();
      else { const b2 = await C.Reader.removeHl(u.id, true); if (b2) u.back = b2; }
    }
  }
}
function undo(){ const a = K.done.pop(); if (!a) return; K.undone.push(a); apply(a, true); Pens.redraw(); }
function redo(){ const a = K.undone.pop(); if (!a) return; K.done.push(a); apply(a, false, true); Pens.redraw(); }
function send(add, rm){
  if (!K.doc || (!add.length && !rm.length)) return;
  if (K.q.doc && K.q.doc !== K.doc) flush();
  K.q.doc = K.doc;
  for (const s of add) { K.q.remove.delete(s.id); K.q.add.set(s.id, s); }
  for (const s of rm) { K.q.add.delete(s.id); K.q.remove.add(s.id); }
  clearTimeout(K.qT); K.qT = setTimeout(flush, 1200);
}
// What's been written in the last moment goes in one request; offline it waits in the outbox.
async function flush(){
  clearTimeout(K.qT);
  const d = K.q.doc; if (!d || (!K.q.add.size && !K.q.remove.size)) return;
  const body = { add: [...K.q.add.values()], remove: [...K.q.remove] };
  K.q = { doc: null, add: new Map(), remove: new Set() };
  try {
    const r = await api('/api/docs/' + encodeURIComponent(d.id) + '/ink', { method: 'POST', body: JSON.stringify(body) });
    if (r && r.saved_as && C.Reader) C.Reader.moved(d, r.saved_as);
    else if (r && r.save_error) toast('Written on, but the page wasn’t saved to the Library: ' + r.save_error);
  } catch(e){ toast(e.message); }
}

// The column moves over to leave room on the right (on a screen wide enough for it).
function setMargin(on){ K.mOn = !!on; if (K.wrap) K.wrap.classList.toggle('inkmargin', K.mOn && window.innerWidth >= 700); later(); }

/* ---------- the article, as a surface for the pens ---------- */
const surface = {
  live,
  takes: el => !!K.wrap && K.wrap.contains(el),
  off: () => [0, 0],
  stroke(L){ const s = make(L); if (!s) return; K.strokes.push(s); draw(s); act({ add: [s] }); },
  erase, erased, eraseAll,
  highlight: toHighlight,
  palHost: () => (K.wrap && K.wrap.closest('.rv')) || document.body,
  canUndo: () => K.done.length > 0, canRedo: () => K.undone.length > 0, undo, redo,
  extras: () => window.innerWidth >= 700 ? [{ k: 'margin', label: 'Room to write in the margin', on: K.mOn }] : [],
  extra(k){ if (k === 'margin') { const on = !K.mOn; K.margin = on; store.set('margin', on); setMargin(on); } },
};

/* ---------- an article opens ---------- */
function open(d){
  flush();
  if (K.ro) K.ro.disconnect();
  const body = document.getElementById('docbody');
  K.doc = d; K.done = []; K.undone = []; K.svg = null; K.body = body;
  if (!body || !d) { Pens.use(null); return; }
  // What's waiting in the outbox (written offline) is shown as if it had gone.
  let list = (d.ink || []).slice();
  const path = '/api/docs/' + encodeURIComponent(d.id) + '/ink';
  for (const x of C.outbox.get()) {
    if (x.path !== path || !x.body) continue;
    for (const s of x.body.add || []) if (!list.some(t => t.id === s.id)) list.push(s);
    const rm = new Set(x.body.remove || []); list = list.filter(t => !rm.has(t.id));
  }
  K.strokes = d.ink = list;
  K.wrap = body.closest('.docwrap') || body.parentNode;
  K.wrap.classList.add('inkable');
  const svg = K.svg = document.createElementNS(NS, 'svg'); svg.setAttribute('class', 'inklayer'); svg.setAttribute('aria-hidden', 'true');
  K.layer = Pens.layer(svg, document.documentElement.dataset.mode === 'dark');
  K.wrap.appendChild(svg);
  const inMargin = list.some(s => s.at && s.at.c == null && (s.at.x > s.at.w || s.at.x < -24));
  setMargin((K.margin && Pens.seen()) || inMargin);
  K.ro = new ResizeObserver(later); K.ro.observe(body); K.ro.observe(K.wrap);
  Pens.use(surface);
  render();
}
Pens.listen(document, surface);
document.addEventListener('visibilitychange', () => { if (document.visibilityState === 'hidden') flush(); });
window.addEventListener('pagehide', flush);
window.addEventListener('resize', () => { if (live()) { setMargin(K.mOn); Pens.redraw(); } });
window.addEventListener('daf-theme', later);                 // the text's colour and the highlighter's blend

C.Ink = { open, flush, undo, redo, state: () => Object.assign(Pens.state(), { strokes: K.strokes.length, margin: !!(K.wrap && K.wrap.classList.contains('inkmargin')), queued: K.q.add.size + K.q.remove.size, done: K.done.length }) };
})();
