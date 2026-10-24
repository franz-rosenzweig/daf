/* Ink: writing on an article with a pen (an S Pen, an Apple Pencil), as in a paper book's margins.
   The pen, the highlighter and the eraser, in the text and beside it. Over words the highlighter
   makes a highlight, as selecting them does (it's in Highlights and the review); anywhere else it
   leaves a marker's stroke. The pen's button (or an eraser end) erases while it's held. Fingers
   still scroll and select, and a hand resting on the screen while the pen writes doesn't scroll.
   With the tools put away the pen is a finger again. Each stroke keeps its paragraph and the letter
   it started on (daf/ink.py), so it stays with its words when the type size or the column changes.
   Nothing shows until a pen has touched the screen on this device. */
(function(){
'use strict';
const C = window.DafCore, H = C.HL;
const { api, toast, esc } = C;
const NS = 'http://www.w3.org/2000/svg';
const store = { get(k, d){ try { const v = localStorage.getItem('daf.ink.' + k); return v == null ? d : JSON.parse(v); } catch(e){ return d; } },
                set(k, v){ try { localStorage.setItem('daf.ink.' + k, JSON.stringify(v)); } catch(e){} } };
// 'ink' is the text's own colour, so it's light on a dark theme. The highlighter's are the highlights'.
const PENS = { ink: 'Black', blue: 'Blue', red: 'Red', green: 'Green' };
const MARKERS = { yellow: 'Yellow', green: 'Green', blue: 'Blue', pink: 'Pink', purple: 'Purple' };
const SIZES = { pen: [1.6, 2.6, 4.2], marker: [14, 20, 28] };
const K = {
  doc: null, strokes: [], geo: new Map(), done: [], undone: [], q: { doc: null, add: new Map(), remove: new Set() },
  tool: store.get('tool', 'pen'), pen: store.get('pen', 'ink'), size: store.get('size', { pen: 1, marker: 1 }),
  on: store.get('on', true), seen: store.get('seen', false), margin: store.get('margin', false),
  layer: null, wrap: null, body: null, pal: null, live: null, near: 0, lastPen: 0, penUp: 0, armed: false,
};
const marker = () => (H && H.color()) || 'yellow';     // Daf's highlight colour: one choice for both
const setMarker = c => { try { localStorage.setItem('daf.hlColor', JSON.stringify(c)); } catch(e){} };
const live = () => !!(K.layer && K.layer.isConnected);
const writing = () => K.on && live();
const r1 = v => Math.round(v * 10) / 10;
const newId = () => { const b = new Uint8Array(10); crypto.getRandomValues(b); return 'k' + Array.from(b, x => x.toString(16).padStart(2, '0')).join(''); };
const sizeOf = tool => SIZES[tool][K.size[tool] != null ? K.size[tool] : 1] || SIZES[tool][1];

const IC = {
  pen: '<svg width="20" height="20" viewBox="0 0 20 20" aria-hidden="true"><path d="M4 16l.9-3.6 8.4-8.4a1.9 1.9 0 0 1 2.7 2.7l-8.4 8.4z" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/><path d="M12.2 5.1l2.7 2.7" stroke="currentColor" stroke-width="1.6"/></svg>',
  marker: '<svg width="20" height="20" viewBox="0 0 20 20" aria-hidden="true"><path d="M3.5 16.5h13" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" opacity=".35"/><path d="M5 12.5 12.5 5l2.5 2.5L7.5 15H5z" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/></svg>',
  eraser: '<svg width="20" height="20" viewBox="0 0 20 20" aria-hidden="true"><path d="M7.8 16 3.6 11.8a1.4 1.4 0 0 1 0-2l6.3-6.3a1.4 1.4 0 0 1 2 0l4.2 4.2a1.4 1.4 0 0 1 0 2L10 16z" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/><path d="M6.6 8.8l4.6 4.6M7.8 16h8.7" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg>',
  undo: '<svg width="20" height="20" viewBox="0 0 20 20" aria-hidden="true"><path d="M7.5 4.5 4 8l3.5 3.5" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/><path d="M4.5 8H12a4 4 0 0 1 0 8H9" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/></svg>',
  redo: '<svg width="20" height="20" viewBox="0 0 20 20" aria-hidden="true"><path d="M12.5 4.5 16 8l-3.5 3.5" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/><path d="M15.5 8H8a4 4 0 0 0 0 8h3" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/></svg>',
  margin: '<svg width="20" height="20" viewBox="0 0 20 20" aria-hidden="true"><rect x="2.5" y="3.5" width="15" height="13" rx="2" fill="none" stroke="currentColor" stroke-width="1.5"/><path d="M5.5 7h4.5M5.5 10h4.5M5.5 13h3" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/><path d="M12.6 7.2c1.5.4.2 1.6 1.6 2s.1 1.7 1.4 2.3" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/></svg>',
  away: '<svg width="20" height="20" viewBox="0 0 20 20" aria-hidden="true"><path d="M7.5 5l5 5-5 5" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>',
};

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
// A stroke as it's kept: its place, and its points from where it started (k=1: as written).
function make(L){
  const [x0, y0] = L.pts[0], el = blockNear(x0, y0); if (!el) return null;
  const br = el.getBoundingClientRect();
  const at = { b: idx(el), q: el.textContent.trim().slice(0, 40), w: r1(br.width), h: r1(br.height), f: fontOf(el) };
  const ch = x0 >= br.left && x0 <= br.right && y0 >= br.top - 4 && y0 <= br.bottom + 4 ? charAt(el, x0, y0) : null;
  if (ch) { at.c = ch.c; at.x = r1(x0 - ch.r.left); at.y = r1(y0 - ch.r.top); }
  else { at.x = r1(x0 - br.left); at.y = r1(y0 - br.top); }
  return { id: newId(), tool: L.tool, color: L.tool === 'marker' ? marker() : K.pen, size: sizeOf(L.tool), at,
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
const width = (tool, size, p) => tool === 'marker' ? size : size * (0.55 + 0.9 * p);
// A pen stroke's outline, thicker where it was pressed harder, with round ends.
function outline(P, size){
  const q = [];
  for (const p of P) {                                    // smoothed a little toward each new point
    const l = q[q.length - 1];
    if (l && Math.hypot(p[0] - l[0], p[1] - l[1]) < 0.5) continue;
    q.push(l ? [l[0] + (p[0] - l[0]) * 0.65, l[1] + (p[1] - l[1]) * 0.65, p[2]] : p.slice());
  }
  const last = P[P.length - 1]; if (q.length > 1) q.push(last.slice());
  const n = q.length, rad = i => width('pen', size, q[i][2]) / 2 * (n > 6 ? Math.min(1, 0.55 + 0.15 * Math.min(i, n - 1 - i)) : 1);
  if (n === 1 || (n === 2 && Math.hypot(q[1][0] - q[0][0], q[1][1] - q[0][1]) < 1)) {
    const r = rad(0), [x, y] = q[0];
    return 'M' + r1(x - r) + ' ' + r1(y) + 'a' + r1(r) + ' ' + r1(r) + ' 0 1 0 ' + r1(2 * r) + ' 0a' + r1(r) + ' ' + r1(r) + ' 0 1 0 ' + r1(-2 * r) + ' 0Z';
  }
  const Lf = [], Rt = [];
  for (let i = 0; i < n; i++) {
    const a = q[Math.max(0, i - 1)], b = q[Math.min(n - 1, i + 1)];
    let tx = b[0] - a[0], ty = b[1] - a[1]; const m = Math.hypot(tx, ty) || 1; tx /= m; ty /= m;
    const r = rad(i);
    Lf.push([q[i][0] - ty * r, q[i][1] + tx * r]); Rt.push([q[i][0] + ty * r, q[i][1] - tx * r]);
  }
  const pt = p => r1(p[0]) + ' ' + r1(p[1]);
  const side = S => { let d = ''; for (let i = 1; i < S.length - 1; i++) d += 'Q' + pt(S[i]) + ' ' + pt([(S[i][0] + S[i + 1][0]) / 2, (S[i][1] + S[i + 1][1]) / 2]); return d + 'L' + pt(S[S.length - 1]); };
  const re = rad(n - 1), rs = rad(0);
  return 'M' + pt(Lf[0]) + side(Lf) + 'A' + r1(re) + ' ' + r1(re) + ' 0 0 0 ' + pt(Rt[n - 1]) + side(Rt.slice().reverse()) + 'A' + r1(rs) + ' ' + r1(rs) + ' 0 0 0 ' + pt(Lf[0]) + 'Z';
}
function line(P){
  if (P.length === 1) return 'M' + r1(P[0][0]) + ' ' + r1(P[0][1]) + 'l0.1 0';
  let d = 'M' + r1(P[0][0]) + ' ' + r1(P[0][1]);
  for (let i = 1; i < P.length - 1; i++) d += 'Q' + r1(P[i][0]) + ' ' + r1(P[i][1]) + ' ' + r1((P[i][0] + P[i + 1][0]) / 2) + ' ' + r1((P[i][1] + P[i + 1][1]) / 2);
  const z = P[P.length - 1]; return d + 'L' + r1(z[0]) + ' ' + r1(z[1]);
}
function draw(s, Lr){
  Lr = Lr || K.layer.getBoundingClientRect();
  const o = place(s, Lr); if (!o) return;
  const [ox, oy, k] = o, pts = s.pts.map(p => [ox + p[0] * k, oy + p[1] * k, p[2]]), size = s.size * k;
  const el = document.createElementNS(NS, 'path');
  el.setAttribute('class', s.tool + ' c-' + s.color); el.dataset.k = s.id;
  if (s.tool === 'marker') { el.setAttribute('d', line(pts)); el.setAttribute('stroke-width', r1(size)); K.gm.appendChild(el); }
  else { el.setAttribute('d', outline(pts, size)); K.gp.appendChild(el); }
  let x1 = Infinity, y1 = Infinity, x2 = -Infinity, y2 = -Infinity;
  for (const p of pts) { if (p[0] < x1) x1 = p[0]; if (p[0] > x2) x2 = p[0]; if (p[1] < y1) y1 = p[1]; if (p[1] > y2) y2 = p[1]; }
  K.geo.set(s.id, { pts, r: s.tool === 'marker' ? size / 2 : size * 0.72, box: [x1, y1, x2, y2] });
}
function render(){
  if (!live()) return;
  K.geo.clear(); K.gm.textContent = ''; K.gp.textContent = '';
  const Lr = K.layer.getBoundingClientRect(); K.cache = new Map();
  for (const s of K.strokes) { try { draw(s, Lr); } catch(e){} }
  K.cache = null;
}
const later = () => { cancelAnimationFrame(K.raf); K.raf = requestAnimationFrame(render); };
function unpaint(id){ K.geo.delete(id); const el = K.layer && K.layer.querySelector('[data-k="' + id + '"]'); if (el) el.remove(); }

// The stroke being written, on a canvas over the window: drawn as fast as the pen moves.
function wet(L, p){
  let cv = K.cv;
  if (!cv || !cv.isConnected) { cv = K.cv = document.createElement('canvas'); cv.className = 'inkwet'; cv.setAttribute('aria-hidden', 'true'); document.body.appendChild(cv); }
  if (!L.ctx) {
    const dpr = window.devicePixelRatio || 1, w = window.innerWidth, h = window.innerHeight;
    if (cv.width !== Math.round(w * dpr) || cv.height !== Math.round(h * dpr)) { cv.width = Math.round(w * dpr); cv.height = Math.round(h * dpr); cv.style.width = w + 'px'; cv.style.height = h + 'px'; }
    L.ctx = cv.getContext('2d', { desynchronized: true });
    L.ctx.setTransform(dpr, 0, 0, dpr, 0, 0); L.ctx.clearRect(0, 0, w, h);
    L.ctx.lineCap = 'round'; L.ctx.lineJoin = 'round'; L.ctx.strokeStyle = colorOf(L.tool);
    cv.style.opacity = L.tool === 'marker' ? '0.38' : '1'; cv.hidden = false;
  }
  const a = L.pts[L.pts.length - 2] || p;
  L.ctx.lineWidth = width(L.tool, L.size, p[2]);
  L.ctx.beginPath(); L.ctx.moveTo(a[0], a[1]); L.ctx.lineTo(p[0] + (a === p ? 0.01 : 0), p[1]); L.ctx.stroke();
}
function dry(){ if (K.cv) { const c = K.cv.getContext('2d'); c.save(); c.setTransform(1, 0, 0, 1, 0, 0); c.clearRect(0, 0, K.cv.width, K.cv.height); c.restore(); K.cv.hidden = true; } }
function colorOf(tool){
  const probe = document.createElementNS(NS, 'path'); probe.setAttribute('class', tool + ' c-' + (tool === 'marker' ? marker() : K.pen));
  K.gp.appendChild(probe); const cs = getComputedStyle(probe), c = tool === 'marker' ? cs.stroke : cs.fill; probe.remove();
  return c && c !== 'none' ? c : '#333';
}

/* ---------- the pen ---------- */
const SKIP = 'input, textarea, select, [contenteditable="true"], .inkpal, .inkpop, #selbar, .menu, .modal';
function mine(e){
  if (e.pointerType !== 'pen' || !writing()) return false;
  const t = e.target;
  return t instanceof Element && K.wrap.contains(t) && !t.closest(SKIP);
}
function feed(e){
  const L = K.live, evs = e.getCoalescedEvents ? e.getCoalescedEvents() : [];
  for (const v of (evs.length ? evs : [e])) {
    const p = [v.clientX, v.clientY, v.pressure > 0 ? Math.min(1, v.pressure) : 0.5], last = L.pts[L.pts.length - 1];
    if (last && Math.hypot(p[0] - last[0], p[1] - last[1]) < 0.7) continue;
    L.pts.push(p);
    if (!L.moved && Math.hypot(p[0] - L.x0, p[1] - L.y0) > 6) L.moved = true;
    if (L.tool === 'eraser') eraseAt(p[0], p[1]); else wet(L, p);
  }
}
function down(e){
  if (e.pointerType === 'pen') { K.lastPen = Date.now(); if (!K.seen) { K.seen = true; store.set('seen', true); arm(); drawPal(); } }
  if (!mine(e)) return;
  e.preventDefault(); e.stopPropagation();
  closePop();
  // The pen's button (2 when it's held) or an eraser end (32) erases, whatever tool is chosen.
  const erase = K.tool === 'eraser' || !!(e.buttons & 34) || e.button === 2 || e.button === 5;
  const tool = erase ? 'eraser' : K.tool;
  K.live = { id: e.pointerId, tool, size: tool === 'eraser' ? 0 : sizeOf(tool), pts: [], t0: Date.now(), x0: e.clientX, y0: e.clientY, moved: false, erased: [], hls: new Set() };
  try { K.wrap.setPointerCapture(e.pointerId); } catch(_){}
  feed(e);
}
function move(e){
  if (e.pointerType === 'pen') K.near = Date.now();
  if (!K.live || e.pointerId !== K.live.id) return;
  e.preventDefault(); feed(e);
}
function up(e){
  if (!K.live || e.pointerId !== K.live.id) return;
  const L = K.live; K.live = null; K.penUp = Date.now(); K.near = Date.now();
  e.preventDefault(); dry();
  if (!live()) return;
  if (!L.moved && Date.now() - L.t0 < 450) { if (L.tool !== 'eraser') tap(L.x0, L.y0); return; }
  if (L.tool === 'eraser') { erased(L); return; }
  if (e.type === 'pointercancel' && L.pts.length < 3) return;
  if (L.tool === 'marker' && toHighlight(L)) return;
  const s = make(L); if (!s) return;
  K.strokes.push(s); draw(s); act({ add: [s] });
}
// A tap with the pen is a tap: on a link, a picture, a highlight, a timestamp.
function tap(x, y){
  const el = document.elementFromPoint(x, y); if (!el) return;
  K.tapping = true;
  try { el.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, view: window, clientX: x, clientY: y, detail: 1 })); } finally { K.tapping = false; }
}

/* ---------- the eraser ---------- */
function near(pts, x, y, r){
  for (let i = 0; i < pts.length; i++) {
    const a = pts[i], b = pts[i + 1] || a, dx = b[0] - a[0], dy = b[1] - a[1], l = dx * dx + dy * dy;
    const t = l ? Math.max(0, Math.min(1, ((x - a[0]) * dx + (y - a[1]) * dy) / l)) : 0;
    if (Math.hypot(x - a[0] - t * dx, y - a[1] - t * dy) <= r) return true;
  }
  return false;
}
function eraseAt(x, y){
  const Lr = K.layer.getBoundingClientRect(), px = x - Lr.left, py = y - Lr.top, R = 9;
  for (const [id, g] of K.geo) {
    const b = g.box, m = R + g.r;
    if (px < b[0] - m || px > b[2] + m || py < b[1] - m || py > b[3] + m || !near(g.pts, px, py, m)) continue;
    const s = K.strokes.find(t => t.id === id); if (!s) continue;
    K.strokes = K.strokes.filter(t => t !== s); unpaint(id); K.live.erased.push(s);
  }
  const el = document.elementFromPoint(x, y), mk = el && el.closest && el.closest('#docbody mark[data-h]');
  if (mk) K.live.hls.add(mk.dataset.h);
}
async function erased(L){
  const a = {};
  if (L.erased.length) a.del = L.erased;
  if (L.hls.size && C.Reader) {
    // Highlights the eraser went over go too; Undo brings them back.
    a.unhl = [];
    for (const id of L.hls) { const back = await C.Reader.removeHl(id, true); if (back) a.unhl.push({ id, back }); }
    if (!a.unhl.length) delete a.unhl;
  }
  if (a.del || a.unhl) act(a);
}

/* ---------- the highlighter over words ---------- */
// Along a line: the words between its ends. Down several lines: from where it started to where
// it stopped, as a selection would be. A ring drawn round something stays a marker's ring.
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
  const color = marker();
  C.Reader.highlight(info, false, true).then(h => { if (h) act({ hl: { id: h.id, info, color } }); });
  return true;
}

/* ---------- undo, and sending ---------- */
function act(a){ K.done.push(a); if (K.done.length > 200) K.done.shift(); K.undone = []; apply(a, false); drawPal(); }
// Does what a records (back = false) or takes it back (true); a highlight's own way for those.
async function apply(a, back, again){
  const add = back ? a.del : a.add, rm = back ? a.add : a.del;
  if (again || back) {
    if (rm) { const ids = new Set(rm.map(s => s.id)); K.strokes = K.strokes.filter(s => !ids.has(s.id)); rm.forEach(s => unpaint(s.id)); }
    if (add) { const Lr = K.layer.getBoundingClientRect(); add.forEach(s => { if (!K.strokes.some(t => t.id === s.id)) { K.strokes.push(s); draw(s, Lr); } }); }
  }
  send(add || [], rm || []);
  if (K.doc) K.doc.ink = K.strokes;
  if (a.hl && (back || again) && C.Reader) {
    if (back) await C.Reader.removeHl(a.hl.id, true);
    else { setMarker(a.hl.color); const h = await C.Reader.highlight(a.hl.info, false, true); if (h) a.hl.id = h.id; }
  }
  if (a.unhl && (back || again) && C.Reader) {
    for (const u of a.unhl) {
      if (back) await u.back();
      else { const b2 = await C.Reader.removeHl(u.id, true); if (b2) u.back = b2; }
    }
  }
}
function undo(){ const a = K.done.pop(); if (!a) return; K.undone.push(a); apply(a, true); drawPal(); }
function redo(){ const a = K.undone.pop(); if (!a) return; K.done.push(a); apply(a, false, true); drawPal(); }
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

/* ---------- the tools ---------- */
function drawPal(){
  if (!K.seen || !live()) { if (K.pal) K.pal.remove(); K.pal = null; return; }
  let p = K.pal;
  if (!p || !p.isConnected) {
    p = K.pal = document.createElement('div'); p.className = 'inkpal'; p.setAttribute('role', 'toolbar'); p.setAttribute('aria-label', 'Pen');
    p.addEventListener('click', onPal);
    (K.wrap.closest('.rv') || document.body).appendChild(p);
  }
  p.classList.toggle('away', !K.on);
  if (!K.on) { p.innerHTML = '<button data-ink="on" title="Write with the pen" aria-label="Write with the pen">' + IC.pen + '</button>'; return; }
  const b = (k, label, on, dis) => '<button data-ink="' + k + '" title="' + label + '" aria-label="' + label + '"' + (on != null ? ' aria-pressed="' + on + '"' : '') + (dis ? ' disabled' : '') + '>' + IC[k] + '</button>';
  const tool = K.tool === 'marker' ? 'marker' : 'pen', c = tool === 'marker' ? marker() : K.pen;
  p.innerHTML = b('pen', 'Pen', K.tool === 'pen') + b('marker', 'Highlighter', K.tool === 'marker') + b('eraser', 'Eraser (or hold the pen’s button)', K.tool === 'eraser') +
    '<span class="sep"></span><button data-ink="pick" title="Colour and size" aria-label="Colour and size" aria-haspopup="true"><span class="dot ' + tool + ' c-' + c + '" style="--s:' + (6 + 4 * (K.size[tool] != null ? K.size[tool] : 1)) + 'px"></span></button>' +
    '<span class="sep"></span>' + b('undo', 'Undo', null, !K.done.length) + b('redo', 'Redo', null, !K.undone.length) +
    '<span class="sep"></span>' + (window.innerWidth >= 700 ? b('margin', 'Room to write in the margin', !!K.mOn) : '') + b('away', 'Put the pen tools away (the pen scrolls and selects)', null);
}
function onPal(e){
  const t = e.target.closest('[data-ink]'); if (!t) return;
  const k = t.dataset.ink;
  if (k === 'pen' || k === 'marker' || k === 'eraser') { K.tool = k; store.set('tool', k); closePop(); }
  else if (k === 'pick') { if (K.popEl) closePop(); else openPop(t); return; }
  else if (k === 'undo') undo();
  else if (k === 'redo') redo();
  else if (k === 'margin') { const on = !K.mOn; K.margin = on; store.set('margin', on); setMargin(on); }
  else if (k === 'away' || k === 'on') { K.on = k === 'on'; store.set('on', K.on); closePop(); }
  drawPal();
}
function openPop(anchor){
  closePop();
  const tool = K.tool === 'marker' ? 'marker' : 'pen', cur = tool === 'marker' ? marker() : K.pen, list = tool === 'marker' ? MARKERS : PENS;
  const sz = K.size[tool] != null ? K.size[tool] : 1;
  const el = K.popEl = document.createElement('div'); el.className = 'inkpop'; el.setAttribute('role', 'dialog'); el.setAttribute('aria-label', tool === 'marker' ? 'Highlighter colour and size' : 'Pen colour and size');
  el.innerHTML = '<div class="row">' + Object.entries(list).map(([c, name]) => '<button data-c="' + c + '" aria-label="' + esc(name) + '" title="' + esc(name) + '" aria-pressed="' + (c === cur) + '"><span class="dot ' + tool + ' c-' + c + '"></span></button>').join('') + '</div>' +
    '<div class="row">' + SIZES[tool].map((s, i) => '<button data-s="' + i + '" aria-label="' + ['Fine', 'Medium', 'Bold'][i] + '" title="' + ['Fine', 'Medium', 'Bold'][i] + '" aria-pressed="' + (i === sz) + '"><span class="dot ' + tool + ' c-' + cur + '" style="--s:' + (6 + 4 * i) + 'px"></span></button>').join('') + '</div>';
  el.addEventListener('click', e => {
    const b = e.target.closest('button'); if (!b) return;
    if (b.dataset.c) { if (tool === 'marker') setMarker(b.dataset.c); else { K.pen = b.dataset.c; store.set('pen', K.pen); } }
    if (b.dataset.s) { K.size = Object.assign({}, K.size, { [tool]: +b.dataset.s }); store.set('size', K.size); }
    closePop(); drawPal();
  });
  document.body.appendChild(el);
  const r = anchor.getBoundingClientRect(), w = el.offsetWidth, h = el.offsetHeight;
  if (window.innerWidth <= 640) { el.style.left = Math.max(8, Math.min(window.innerWidth - w - 8, r.left + r.width / 2 - w / 2)) + 'px'; el.style.top = (r.top - h - 10) + 'px'; }
  else { el.style.left = (r.left - w - 12) + 'px'; el.style.top = Math.max(8, Math.min(window.innerHeight - h - 8, r.top + r.height / 2 - h / 2)) + 'px'; }
  setTimeout(() => document.addEventListener('pointerdown', K.popOff = ev => { if (!ev.target.closest('.inkpop, [data-ink="pick"]')) closePop(); }, true), 0);
}
function closePop(){ if (K.popEl) { K.popEl.remove(); K.popEl = null; } if (K.popOff) { document.removeEventListener('pointerdown', K.popOff, true); K.popOff = null; } }
// The column moves over to leave room on the right (on a screen wide enough for it).
function setMargin(on){ K.mOn = !!on; if (K.wrap) K.wrap.classList.toggle('inkmargin', K.mOn && window.innerWidth >= 700); later(); }

/* ---------- an article opens ---------- */
function open(d){
  flush();
  if (K.ro) K.ro.disconnect();
  const body = document.getElementById('docbody');
  K.doc = d; K.done = []; K.undone = []; K.layer = null; K.body = body;
  if (!body || !d) { drawPal(); return; }
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
  const svg = K.layer = document.createElementNS(NS, 'svg'); svg.setAttribute('class', 'inklayer'); svg.setAttribute('aria-hidden', 'true');
  K.gm = document.createElementNS(NS, 'g'); K.gm.setAttribute('class', 'mk'); K.gp = document.createElementNS(NS, 'g');
  svg.append(K.gm, K.gp); K.wrap.appendChild(svg);
  const inMargin = list.some(s => s.at && s.at.c == null && (s.at.x > s.at.w || s.at.x < -24));
  setMargin((K.margin && K.seen) || inMargin);
  K.ro = new ResizeObserver(later); K.ro.observe(body); K.ro.observe(K.wrap);
  drawPal(); render();
}

// Only on a device a pen has touched: the touch listeners can't be passive, so a browser waits
// for them before it scrolls.
function arm(){
  if (K.armed) return; K.armed = true;
  const stylus = e => [...e.changedTouches].some(t => t.touchType === 'stylus');
  document.addEventListener('touchstart', e => {
    if (!writing()) return;
    if (stylus(e)) { if (K.live) e.preventDefault(); return; }
    if (K.live || Date.now() - K.near < 350) e.preventDefault();        // a hand on the screen while the pen writes
  }, { capture: true, passive: false });
  document.addEventListener('touchmove', e => { if (writing() && K.live) e.preventDefault(); }, { capture: true, passive: false });
}
document.addEventListener('pointerdown', down, true);
document.addEventListener('pointermove', move, true);
document.addEventListener('pointerup', up, true);
document.addEventListener('pointercancel', up, true);
// A pen that's just written doesn't also click what it wrote on (a mouse-like pen sends one), nor
// open a menu with its button.
document.addEventListener('click', e => { if (e.isTrusted && !K.tapping && Date.now() - K.penUp < 500 && mine({ pointerType: 'pen', target: e.target })) { e.preventDefault(); e.stopPropagation(); } }, true);
document.addEventListener('contextmenu', e => { if (Date.now() - K.lastPen < 800 && writing()) e.preventDefault(); }, true);
document.addEventListener('visibilitychange', () => { if (document.visibilityState === 'hidden') flush(); });
window.addEventListener('pagehide', flush);
window.addEventListener('resize', () => { if (live()) { setMargin(K.mOn); drawPal(); } });
if (K.seen) arm();

C.Ink = { open, flush, undo, redo, state: () => ({ strokes: K.strokes.length, tool: K.tool, on: K.on, seen: K.seen, margin: !!(K.wrap && K.wrap.classList.contains('inkmargin')), queued: K.q.add.size + K.q.remove.size, done: K.done.length }) };
})();
