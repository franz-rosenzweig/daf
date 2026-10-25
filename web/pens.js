/* The pens: the pen in the hand, for writing on an article (ink.js) or a book (book.js) with a pen,
   an S Pen or an Apple Pencil. As Samsung Notes has them, and as Moshe's handwriting does (its
   engine/src/ink.js and lib/ink-tools: the same kinds, sizes and colours, so the two feel alike):
   seven kinds of pen, each keeping its own size (1 to 100), colour and opacity; the highlighter; an
   eraser that takes whole strokes or only what it passes over; favourite pens; the colours used last.

   The S Pen's button pressed with the pen just over the glass opens the round menu: the pen in the
   middle (tap it for the other kinds), its size on the left, its colour on the right, Undo and Redo
   above, the favourite pens below. Held while writing, the button erases. A line, circle, rectangle
   or triangle held still for a moment at its end comes out clean. Fingers scroll and select; only the
   pen writes, and a hand resting on the screen while the pen is near doesn't scroll. With the tools
   put away the pen is a finger again. Nothing shows until a pen has touched the screen on this device.

   A surface is where the strokes go and are kept (an article's text, a book's pages). This file is
   the pen in the hand, the stroke being written, and the tools; each surface says where a stroke
   belongs, draws the ones it has, and takes away what the eraser passes over. */
(function(){
'use strict';
const C = window.DafCore, H = C.HL, FH = window.DafFreehand;
const { esc } = C;
const NS = 'http://www.w3.org/2000/svg';
const get = (k, d) => { try { const v = localStorage.getItem('daf.pens.' + k); return v == null ? d : JSON.parse(v); } catch(e){ return d; } };
const put = (k, v) => { try { localStorage.setItem('daf.pens.' + k, JSON.stringify(v)); } catch(e){} };
const old = k => { try { const v = localStorage.getItem('daf.ink.' + k); return v == null ? null : JSON.parse(v); } catch(e){ return null; } };   // round one's
const r1 = v => Math.round(v * 10) / 10;

/* ---------- the pens ---------- */
const KINDS = { fountain: 'Fountain pen', calligraphy: 'Calligraphy pen', pen: 'Pen', pencil: 'Pencil', brush: 'Calligraphy brush', marker: 'Marker', highlighter: 'Highlighter' };
const WRITING = ['fountain', 'calligraphy', 'pen', 'pencil', 'brush', 'marker'];
// 'ink' is the text's own colour (white on a dark page); then Moshe's (Excalidraw's) fifteen.
const COLORS = ['ink', '#1e1e1e', '#868e96', '#ffffff', '#e03131', '#f76707', '#f59f00', '#fcc419', '#2f9e44', '#12b886', '#1971c2', '#4dabf7', '#5f3dc4', '#ae3ec9', '#e64980', '#8d5524'];
const HLS = ['yellow', 'green', 'blue', 'pink', 'purple'];          // the highlighter's: Daf's highlight colours
const HLNAME = { yellow: 'Yellow', green: 'Green', blue: 'Blue', pink: 'Pink', purple: 'Purple' };
// How wide a pen draws for a size from 1 to 100 (Samsung's scale), in pixels: Moshe's widths, whose
// page is 1000 units across a tablet's 800-odd pixels, so the same size looks the same in both.
function across(pen, size){
  const v = Math.max(1, Math.min(100, size)) / 100;
  const w = pen === 'highlighter' ? 6 + v * 54 : pen === 'marker' || pen === 'brush' ? 1.5 + v * v * 48 : 0.6 + Math.pow(v, 1.5) * 30;
  return w * 0.8;
}
const DEF = { fountain: { size: 25, color: 'ink', opacity: 100 }, calligraphy: { size: 35, color: 'ink', opacity: 100 }, pen: { size: 20, color: '#1971c2', opacity: 100 },
  pencil: { size: 25, color: '#495057', opacity: 100 }, brush: { size: 40, color: 'ink', opacity: 100 }, marker: { size: 30, color: '#e03131', opacity: 100 },
  highlighter: { size: 40, color: 'yellow', opacity: 50 } };
const saved = get('tools', null) || {};
const T = {
  tool: saved.tool || ({ marker: 'highlighter', eraser: 'eraser' })[old('tool')] || 'pen',     // pen | highlighter | eraser
  pen: KINDS[saved.pen] && saved.pen !== 'highlighter' ? saved.pen : 'fountain',
  pens: Object.fromEntries(Object.entries(DEF).map(([k, v]) => [k, Object.assign({}, v, (saved.pens || {})[k] || {})])),
  eraser: Object.assign({ mode: 'stroke', size: 24 }, saved.eraser || {}),                       // mode: stroke | area
  favorites: saved.favorites || [],                                                                // [{pen, size, color, opacity}]
  recent: saved.recent || ['ink', '#1971c2', '#e03131'],
};
const P = { on: get('on', old('on') !== false), seen: get('seen', !!old('seen')), surface: null, live: null, near: 0, lastPen: 0, penUp: 0, tapping: false, docs: new Set(), button: false };
let keepT = 0;
const keep = () => { clearTimeout(keepT); keepT = setTimeout(() => put('tools', T), 300); };
// The highlighter's colour is Daf's highlight colour, one choice for both.
const hlColor = () => (H && H.color()) || 'yellow';
const setHl = c => { try { localStorage.setItem('daf.hlColor', JSON.stringify(c)); } catch(e){} };
// The pen in hand, as it writes now: its kind, colour, width (px) and opacity (0 to 1); none for the eraser.
function brush(tool){
  tool = tool || T.tool;
  if (tool === 'eraser') return null;
  const pen = tool === 'highlighter' ? 'highlighter' : T.pen, p = T.pens[pen];
  return { pen, color: pen === 'highlighter' ? hlColor() : p.color, w: across(pen, p.size), opacity: Math.max(0.05, Math.min(1, p.opacity / 100)) };
}
function choose(tool, pen){ T.tool = tool; if (pen && pen !== 'highlighter') T.pen = pen; keep(); redraw(); }
function setColor(c){
  if (T.tool === 'highlighter') setHl(c);
  else { if (T.tool !== 'pen') T.tool = 'pen'; T.pens[T.pen].color = c; used(c); }
  keep(); redraw();
}
function used(c){ if (T.recent[0] === c) return; T.recent = [c, ...T.recent.filter(x => x !== c)].slice(0, 8); keep(); }
function setSize(v){ const k = T.tool === 'eraser' ? null : T.tool === 'highlighter' ? 'highlighter' : T.pen; if (k) T.pens[k].size = v; else T.eraser.size = v; keep(); redraw(); }
function addFavorite(){
  const b = brush(T.tool === 'eraser' ? 'pen' : T.tool); if (!b) return;
  const f = { pen: b.pen, size: T.pens[b.pen].size, color: b.color, opacity: T.pens[b.pen].opacity };
  if (T.favorites.some(x => x.pen === f.pen && x.size === f.size && x.color === f.color && x.opacity === f.opacity)) return;
  T.favorites = [...T.favorites, f].slice(-8); keep(); redraw();
}
function useFavorite(f){
  if (f.pen === 'highlighter') { T.tool = 'highlighter'; setHl(f.color); }
  else { T.tool = 'pen'; T.pen = f.pen; }
  Object.assign(T.pens[f.pen], { size: f.size, opacity: f.opacity }, f.pen === 'highlighter' ? {} : { color: f.color });
  keep(); redraw();
}

/* ---------- strokes drawn ---------- */
const cssVar = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
// A stroke's colour as CSS draws it. 'ink' is the text's colour where it's drawn (a book's page has its own).
function colorOf(c, doc){
  if (!c || c === 'ink') {
    if (doc && doc !== document) { try { const v = getComputedStyle(doc.body).color; if (v) return v; } catch(e){} }
    return cssVar('--read-fg') || cssVar('--fg') || '#1e1e1e';
  }
  if (/^#[0-9a-f]{6}$/i.test(c)) return c;
  if (HLS.includes(c)) return cssVar('--hl-' + c + '-line') || '#efc83a';
  return ({ blue: cssVar('--ink-blue'), red: cssVar('--ink-red'), green: cssVar('--ink-green') })[c] || '#1e1e1e';    // round one's names
}
// What a kept stroke is: its kind, width (px, as written) and opacity. Round one's strokes (no v)
// were 'pen' (a pen) and 'marker' (the highlighter), with their width in size.
const kindOf = s => s.v ? (KINDS[s.tool] ? s.tool : 'pen') : s.tool === 'marker' ? 'highlighter' : 'pen';
const opacityOf = s => s.v ? (s.o != null ? s.o : 1) : s.tool === 'marker' ? 0.38 : 1;
const sine = t => Math.sin(t * Math.PI / 2);
const med = (a, b) => [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2];
function outlinePath(pts){
  if (!pts.length) return '';
  let d = 'M' + r1(pts[0][0]) + ' ' + r1(pts[0][1]) + 'Q';
  for (let i = 0; i < pts.length; i++) { const a = pts[i], m = med(a, pts[(i + 1) % pts.length]); d += r1(a[0]) + ' ' + r1(a[1]) + ' ' + r1(m[0]) + ' ' + r1(m[1]) + ' '; }
  return d.trim() + 'Z';
}
// Each pen's feel: how much the pressure thins it, how smooth, how it starts and ends (Moshe's FEEL).
const FEEL = {
  fountain: w => ({ size: w, thinning: 0.6, smoothing: 0.5, streamline: 0.5, easing: sine }),
  pen: w => ({ size: w, thinning: 0.18, smoothing: 0.6, streamline: 0.5 }),
  pencil: w => ({ size: w, thinning: 0.45, smoothing: 0.5, streamline: 0.45 }),
  brush: w => ({ size: w, thinning: 0.85, smoothing: 0.7, streamline: 0.55, easing: sine, start: { taper: w * 2.5 }, end: { taper: w * 3.5 } }),
  marker: w => ({ size: w, thinning: 0, smoothing: 0.6, streamline: 0.5 }),
  highlighter: w => ({ size: w, thinning: 0, smoothing: 0.6, streamline: 0.6, start: { cap: false }, end: { cap: false } }),
};
function clockwise(poly){
  let a = 0;
  for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) a += (poly[j][0] - poly[i][0]) * (poly[j][1] + poly[i][1]);
  return a < 0 ? poly.slice().reverse() : poly;
}
// The calligraphy pen: a flat nib held at 45°, broad one way and fine the other, with a hairline
// along the middle so the thin strokes never vanish.
function nibPath(points, w){
  const pts = FH.getStrokePoints(points, { size: w, streamline: 0.5, smoothing: 0.5, last: true });
  const hair = outlinePath(clockwise(FH.getStroke(points, { size: Math.max(0.8, w * 0.14), thinning: 0, smoothing: 0.5, streamline: 0.5, last: true })));
  if (pts.length < 2) return hair;
  const a = -Math.PI / 4, ux = Math.cos(a), uy = Math.sin(a), pieces = [];
  let L = [], R = [], side = 0;
  for (const p of pts) {
    const half = w * (0.55 + 0.65 * (p.pressure != null ? p.pressure : 0.5)) / 2;
    const l = [p.point[0] + ux * half, p.point[1] + uy * half], r = [p.point[0] - ux * half, p.point[1] - uy * half];
    const turn = Math.sign(p.vector[0] * uy - p.vector[1] * ux);
    if (turn && side && turn !== side) { L.push(l); R.push(r); pieces.push([...L, ...R.reverse()]); L = []; R = []; }
    if (turn) side = turn;
    L.push(l); R.push(r);
  }
  if (L.length > 1) pieces.push([...L, ...R.reverse()]);
  return pieces.map(poly => outlinePath(clockwise(poly))).join('') + hair;
}
// The shape a stroke fills, its points where they're drawn ([x, y, pressure]).
function shape(pen, pts, w){
  if (!pts.length) return '';
  if (pen === 'calligraphy') return nibPath(pts, w);
  return outlinePath(FH.getStroke(pts, Object.assign({}, (FEEL[pen] || FEEL.pen)(w), { simulatePressure: false, last: true })));
}
const GRAIN = '<filter id="dafgrain" x="0" y="0" width="1" height="1"><feTurbulence type="fractalNoise" baseFrequency="1.6" numOctaves="2" seed="3"/><feColorMatrix values="0 0 0 0 0  0 0 0 0 0  0 0 0 0 0  0 0 0 -2.4 2"/><feComposite in="SourceGraphic" operator="in"/></filter>';
// A layer of strokes in an SVG element (or group): the highlighter's under everything else, one
// group a colour and opacity so overlaps don't darken and the writing above isn't dimmed (Moshe's,
// after Saber); the pencil with its grain.
function layer(svg, dark){
  const doc = svg.ownerDocument, defs = doc.createElementNS(NS, 'defs');
  defs.innerHTML = GRAIN;
  const hl = doc.createElementNS(NS, 'g'), ink = doc.createElementNS(NS, 'g');
  hl.setAttribute('class', 'dafhl'); hl.style.mixBlendMode = dark ? 'screen' : 'multiply';
  svg.append(defs, hl, ink);
  const groups = new Map();
  return {
    svg, hl, ink,
    // s: the stroke; pts: its points where they go; k: how much bigger the type is than when written
    add(s, pts, k){
      const pen = kindOf(s), op = opacityOf(s), el = doc.createElementNS(NS, 'path'), color = colorOf(s.color, doc);
      el.setAttribute('d', shape(pen, pts, (s.size || 2.5) * k));
      el.setAttribute('fill', color); el.dataset.k = s.id;
      if (pen === 'highlighter') {
        const key = color + '|' + r1(op);
        let g = groups.get(key);
        if (!g || !g.isConnected) { g = doc.createElementNS(NS, 'g'); g.setAttribute('opacity', r1(op)); hl.appendChild(g); groups.set(key, g); }
        g.appendChild(el);
      } else {
        if (op < 1) el.setAttribute('fill-opacity', r1(op));
        if (pen === 'pencil') el.setAttribute('filter', 'url(#dafgrain)');
        ink.appendChild(el);
      }
      return el;
    },
    remove(id){ const el = svg.querySelector('[data-k="' + id + '"]'); if (el) el.remove(); },
    clear(){ hl.textContent = ''; ink.textContent = ''; groups.clear(); },
  };
}
// A pen's sample: a short wave written with it (the tools, the round menu).
function sample(pen, color, w, opacity, W, Hh){
  W = W || 34; Hh = Hh || 20;
  const pts = []; for (let i = 0; i <= 14; i++) { const t = i / 14; pts.push([4 + t * (W - 8), Hh / 2 + Math.sin(t * Math.PI * 1.6) * (Hh / 2 - 4), 0.35 + 0.5 * Math.sin(t * Math.PI)]); }
  const c = colorOf(color), pale = /^#f/i.test(c) || c === '#ffffff';
  return '<svg width="' + W + '" height="' + Hh + '" viewBox="0 0 ' + W + ' ' + Hh + '" aria-hidden="true"><defs>' + GRAIN + '</defs><path d="' + shape(pen, pts, Math.min(w, Hh / 2.5)) + '" fill="' + esc(c) + '"' +
    (opacity < 1 ? ' fill-opacity="' + r1(opacity) + '"' : '') + (pen === 'pencil' ? ' filter="url(#dafgrain)"' : '') + (pale ? ' stroke="rgba(0,0,0,.35)" stroke-width=".6"' : '') + '/></svg>';
}

/* ---------- shapes held still, made clean (Moshe's snapShape) ---------- */
function corners(pts, eps){
  if (pts.length < 3) return pts;
  const a = pts[0], b = pts[pts.length - 1], dx = b[0] - a[0], dy = b[1] - a[1], len = Math.hypot(dx, dy);
  let far = 0, at = 0;
  for (let i = 1; i < pts.length - 1; i++) {
    const d = len ? Math.abs(dy * pts[i][0] - dx * pts[i][1] + b[0] * a[1] - b[1] * a[0]) / len : Math.hypot(pts[i][0] - a[0], pts[i][1] - a[1]);
    if (d > far) { far = d; at = i; }
  }
  if (far <= eps) return [a, b];
  return [...corners(pts.slice(0, at + 1), eps).slice(0, -1), ...corners(pts.slice(at), eps)];
}
function along(vs, p, step){
  step = step || 6; const out = [];
  for (let i = 0; i < vs.length - 1; i++) {
    const a = vs[i], b = vs[i + 1], n = Math.max(1, Math.round(Math.hypot(b[0] - a[0], b[1] - a[1]) / step));
    out.push([a[0], a[1], p], [a[0], a[1], p]);
    for (let j = 1; j < n; j++) out.push([a[0] + (b[0] - a[0]) * j / n, a[1] + (b[1] - a[1]) * j / n, p]);
  }
  const z = vs[vs.length - 1]; out.push([z[0], z[1], p], [z[0], z[1], p]);
  return out;
}
function level(a, b){
  const deg = (Math.atan2(b[1] - a[1], b[0] - a[0]) * 180 / Math.PI + 360) % 180;
  if (deg < 7 || deg > 173) return [a, [b[0], a[1]]];
  if (Math.abs(deg - 90) < 7) return [a, [a[0], b[1]]];
  return [a, b];
}
function snapShape(points){
  if (!points || points.length < 4) return null;
  let len = 0;
  for (let i = 1; i < points.length; i++) len += Math.hypot(points[i][0] - points[i - 1][0], points[i][1] - points[i - 1][1]);
  const xs = points.map(q => q[0]), ys = points.map(q => q[1]);
  const x0 = Math.min(...xs), x1 = Math.max(...xs), y0 = Math.min(...ys), y1 = Math.max(...ys), diag = Math.hypot(x1 - x0, y1 - y0);
  if (diag < 24) return null;
  const p = points.reduce((t, q) => t + (q[2] != null ? q[2] : 0.5), 0) / points.length;
  const first = points[0], last = points[points.length - 1], gap = Math.hypot(last[0] - first[0], last[1] - first[1]);
  if (gap / len > 0.9) return along(level(first, last), p);
  if (gap > Math.max(0.3 * diag, 0.18 * len)) return null;                  // open, and not straight: writing
  const c = corners([...points, first], diag * 0.08);
  const v = c.slice(0, -1).filter((q, i, all) => i === 0 || Math.hypot(q[0] - all[i - 1][0], q[1] - all[i - 1][1]) > diag * 0.12);
  const cx = (x0 + x1) / 2, cy = (y0 + y1) / 2, rx = (x1 - x0) / 2, ry = (y1 - y0) / 2;
  const off = points.reduce((t, q) => t + Math.abs(Math.hypot((q[0] - cx) / (rx || 1), (q[1] - cy) / (ry || 1)) - 1), 0) / points.length;
  if (off < 0.12 && (v.length > 4 || v.length < 3 || off < 0.06)) {
    const round = Math.abs(rx - ry) < 0.12 * Math.max(rx, ry), r = (rx + ry) / 2, n = Math.max(32, Math.round(Math.PI * (rx + ry) / 6));
    const start = Math.atan2(first[1] - cy, first[0] - cx);
    return Array.from({ length: n + 1 }, (_, i) => { const a = start + i / n * 2 * Math.PI; return [cx + (round ? r : rx) * Math.cos(a), cy + (round ? r : ry) * Math.sin(a), p]; });
  }
  if (v.length === 3) return along([...v, v[0]], p);
  if (v.length === 4) {
    const square = v.every((q, i) => { const n = v[(i + 1) % 4], d = (Math.atan2(n[1] - q[1], n[0] - q[0]) * 180 / Math.PI + 360) % 90; return d < 12 || d > 78; });
    const quad = square ? [[x0, y0], [x1, y0], [x1, y1], [x0, y1]] : v;
    const k = square ? quad.reduce((best, q, i) => Math.hypot(q[0] - first[0], q[1] - first[1]) < Math.hypot(quad[best][0] - first[0], quad[best][1] - first[1]) ? i : best, 0) : 0;
    const ring = [...quad.slice(k), ...quad.slice(0, k)];
    return along([...ring, ring[0]], p);
  }
  return null;
}

/* ---------- the stroke being written ---------- */
// On a canvas over the window, drawn as the pen moves, in the pen's own shape.
function wet(L){
  let cv = P.cv;
  if (!cv || !cv.isConnected) { cv = P.cv = document.createElement('canvas'); cv.className = 'inkwet'; cv.setAttribute('aria-hidden', 'true'); document.body.appendChild(cv); }
  const dpr = window.devicePixelRatio || 1, w = window.innerWidth, h = window.innerHeight;
  if (cv.width !== Math.round(w * dpr) || cv.height !== Math.round(h * dpr)) { cv.width = Math.round(w * dpr); cv.height = Math.round(h * dpr); cv.style.width = w + 'px'; cv.style.height = h + 'px'; }
  const x = cv.getContext('2d', { desynchronized: true });
  x.setTransform(dpr, 0, 0, dpr, 0, 0); x.clearRect(0, 0, w, h);
  if (!L.brush || !L.pts.length) return;
  cv.hidden = false; cv.style.opacity = r1(L.brush.opacity);
  x.fillStyle = L.wetColor || (L.wetColor = colorOf(L.brush.color, L.doc));
  x.fill(new Path2D(shape(L.brush.pen, L.pts, L.brush.w)));
}
function dry(){ if (P.cv) { const x = P.cv.getContext('2d'); x.setTransform(1, 0, 0, 1, 0, 0); x.clearRect(0, 0, P.cv.width, P.cv.height); P.cv.hidden = true; } }

// The pen's place over the glass: a ring the size of what it'll write (or erase).
function ring(x, y){
  let el = P.ring;
  if (!el || !el.isConnected) { el = P.ring = document.createElement('div'); el.className = 'penring'; el.setAttribute('aria-hidden', 'true'); document.body.appendChild(el); }
  if (x == null) { el.hidden = true; return; }
  const b = brush(), d = Math.max(8, b ? b.w : T.eraser.size);
  el.style.width = el.style.height = d + 'px';
  el.style.transform = 'translate(' + r1(x - d / 2) + 'px,' + r1(y - d / 2) + 'px)';
  el.classList.toggle('erase', !b);
  el.hidden = false;
  clearTimeout(P.ringT); P.ringT = setTimeout(() => { el.hidden = true; }, 700);
}

const SKIP = 'input, textarea, select, [contenteditable="true"], .inkpal, .inkpop, .penround, #selbar, .menu, .modal, #fedges';
const writing = () => P.on && !!(P.surface && P.surface.live());
// A pen down where a surface takes ink. doc: the document the event is in; off: its corner in the window.
function mine(e, doc, surf){
  if (e.pointerType !== 'pen' || !P.on || !surf || !surf.live()) return false;
  const t = e.target;
  return !!(t && t.closest) && !t.closest(SKIP) && surf.takes(t, doc);
}
function seenPen(){ P.lastPen = Date.now(); if (!P.seen) { P.seen = true; put('seen', true); P.docs.forEach(arm); redraw(); } }
function feed(e, off){
  const L = P.live, evs = e.getCoalescedEvents ? e.getCoalescedEvents() : [];
  for (const v of (evs.length ? evs : [e])) {
    const p = [v.clientX + off[0], v.clientY + off[1], v.pressure > 0 ? Math.min(1, v.pressure) : 0.5], last = L.pts[L.pts.length - 1];
    if (last && Math.hypot(p[0] - last[0], p[1] - last[1]) < 0.7) continue;
    if (L.snapped) { L.pts = L.raw; L.snapped = false; }
    L.pts.push(p);
    if (!L.moved && Math.hypot(p[0] - L.x0, p[1] - L.y0) > 6) L.moved = true;
    if (L.tool === 'eraser') L.surf.erase(p[0], p[1], T.eraser.mode, T.eraser.size / 2, L);
  }
  if (L.tool !== 'eraser') {
    wet(L);
    // held still at the end: a clean line, circle, rectangle or triangle
    clearTimeout(L.stillT);
    L.stillT = setTimeout(() => { if (P.live !== L || L.pts.length < 4) return; const s = snapShape(L.pts); if (s) { L.raw = L.pts; L.pts = s; L.snapped = true; wet(L); } }, 600);
  }
}
// Every document the pen writes in listens: the page's own, and a book's pages in their frames.
// surf answers: live(), takes(el, doc), off(doc) → [x, y] of the document's corner in the window,
// and keeps what's written: stroke(L), erase(x, y, mode, r, L), erased(L), highlight(L) → bool.
function listen(doc, surf){
  if (!doc || doc.__dafPens) return;
  doc.__dafPens = true; P.docs.add(doc);
  const off = () => surf.off ? surf.off(doc) : [0, 0];
  doc.addEventListener('pointerdown', e => {
    if (e.pointerType !== 'pen') return;
    seenPen();
    const o = off(), x = e.clientX + o[0], y = e.clientY + o[1];
    // the button pressed with the pen over the glass: the round menu
    if (!(e.buttons & 1) && (e.button === 2 || (e.buttons & 2)) && writing()) { e.preventDefault(); e.stopPropagation(); P.button = true; openRound(x, y); return; }
    if (!mine(e, doc, surf)) return;
    e.preventDefault(); e.stopPropagation();
    closePop(); closeRound(); ring(null);
    // the pen's button held (2) or an eraser end (32) erases, whatever tool is chosen
    const tool = T.tool === 'eraser' || (e.buttons & 34) || e.button === 2 || e.button === 5 ? 'eraser' : T.tool;
    P.live = { id: e.pointerId, surf, doc, tool, brush: tool === 'eraser' ? null : brush(tool), pts: [], t0: Date.now(), x0: x, y0: y, moved: false, erased: [], added: [], hls: new Set() };
    try { (e.target.setPointerCapture ? e.target : doc.documentElement).setPointerCapture(e.pointerId); } catch(_){}
    feed(e, o);
  }, true);
  doc.addEventListener('pointermove', e => {
    if (e.pointerType !== 'pen') return;
    P.near = Date.now();
    const o = off();
    if (P.live && e.pointerId === P.live.id) { e.preventDefault(); feed(e, o); return; }
    // over the glass: the ring, and the button pressed there (when no pointerdown said so)
    const pressed = !!(e.buttons & 2) && !(e.buttons & 1);
    if (pressed && !P.button && writing()) { P.button = true; openRound(e.clientX + o[0], e.clientY + o[1]); }
    else if (!pressed) P.button = false;
    if (writing() && !(e.buttons & 1) && !P.roundEl && e.target && e.target.closest && !e.target.closest(SKIP) && surf.takes(e.target, doc)) ring(e.clientX + o[0], e.clientY + o[1]);
  }, true);
  const up = e => {
    if (e.pointerType === 'pen' && !(e.buttons & 2)) P.button = false;
    const L = P.live; if (!L || e.pointerId !== L.id) return;
    P.live = null; P.penUp = Date.now(); P.near = Date.now(); clearTimeout(L.stillT);
    e.preventDefault(); dry();
    if (!surf.live()) return;
    if (!L.moved && Date.now() - L.t0 < 450) { if (L.tool !== 'eraser') tap(doc, e.clientX, e.clientY); return; }
    if (L.tool === 'eraser') { surf.erased(L); return; }
    if (e.type === 'pointercancel' && L.pts.length < 3) return;
    if (L.tool === 'highlighter' && !L.snapped && surf.highlight && surf.highlight(L)) return;
    if (L.brush && L.brush.pen !== 'highlighter') used(L.brush.color);
    surf.stroke(L);
  };
  doc.addEventListener('pointerup', up, true);
  doc.addEventListener('pointercancel', up, true);
  // a pen that's just written doesn't also click what it wrote on (a mouse-like pen sends one)
  doc.addEventListener('click', e => { if (e.isTrusted && !P.tapping && Date.now() - P.penUp < 500 && writing() && e.target && e.target.closest && !e.target.closest(SKIP) && surf.takes(e.target, doc)) { e.preventDefault(); e.stopPropagation(); } }, true);
  doc.addEventListener('contextmenu', e => { if (Date.now() - P.lastPen < 800 && writing()) e.preventDefault(); }, true);
  if (P.seen) arm(doc);
}
// A tap with the pen is a tap: a link, a picture, a highlight, a timestamp.
function tap(doc, x, y){
  const el = doc.elementFromPoint(x, y); if (!el) return;
  P.tapping = true;
  try { el.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, view: doc.defaultView, clientX: x, clientY: y, detail: 1 })); } finally { P.tapping = false; }
}
// Only on a device a pen has touched: these can't be passive, so the browser waits for them before
// it scrolls. A stylus that's writing doesn't scroll (or turn a book's page); nor does a hand on
// the screen while the pen writes or hovers. In the window's capture phase, so they come first.
function arm(doc){
  if (!doc || doc.__dafArmed || !doc.defaultView) return;
  doc.__dafArmed = true;
  const win = doc.defaultView, stylus = e => [...e.changedTouches].some(t => t.touchType === 'stylus');
  win.addEventListener('touchstart', e => {
    if (!writing()) return;
    if (stylus(e)) { if (P.live) { e.preventDefault(); e.stopImmediatePropagation(); } return; }
    if (P.live || Date.now() - P.near < 350) { e.preventDefault(); e.stopImmediatePropagation(); }
  }, { capture: true, passive: false });
  win.addEventListener('touchmove', e => { if (writing() && P.live) { e.preventDefault(); e.stopImmediatePropagation(); } }, { capture: true, passive: false });
}

/* ---------- the tools on the screen's edge ---------- */
const IC = {
  pen: '<svg width="20" height="20" viewBox="0 0 20 20" aria-hidden="true"><path d="M4 16l.9-3.6 8.4-8.4a1.9 1.9 0 0 1 2.7 2.7l-8.4 8.4z" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/><path d="M12.2 5.1l2.7 2.7" stroke="currentColor" stroke-width="1.6"/></svg>',
  highlighter: '<svg width="20" height="20" viewBox="0 0 20 20" aria-hidden="true"><path d="M3.5 16.5h13" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" opacity=".35"/><path d="M5 12.5 12.5 5l2.5 2.5L7.5 15H5z" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/></svg>',
  eraser: '<svg width="20" height="20" viewBox="0 0 20 20" aria-hidden="true"><path d="M7.8 16 3.6 11.8a1.4 1.4 0 0 1 0-2l6.3-6.3a1.4 1.4 0 0 1 2 0l4.2 4.2a1.4 1.4 0 0 1 0 2L10 16z" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/><path d="M6.6 8.8l4.6 4.6M7.8 16h8.7" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg>',
  undo: '<svg width="20" height="20" viewBox="0 0 20 20" aria-hidden="true"><path d="M7.5 4.5 4 8l3.5 3.5" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/><path d="M4.5 8H12a4 4 0 0 1 0 8H9" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/></svg>',
  redo: '<svg width="20" height="20" viewBox="0 0 20 20" aria-hidden="true"><path d="M12.5 4.5 16 8l-3.5 3.5" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/><path d="M15.5 8H8a4 4 0 0 0 0 8h3" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/></svg>',
  margin: '<svg width="20" height="20" viewBox="0 0 20 20" aria-hidden="true"><rect x="2.5" y="3.5" width="15" height="13" rx="2" fill="none" stroke="currentColor" stroke-width="1.5"/><path d="M5.5 7h4.5M5.5 10h4.5M5.5 13h3" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/><path d="M12.6 7.2c1.5.4.2 1.6 1.6 2s.1 1.7 1.4 2.3" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/></svg>',
  away: '<svg width="20" height="20" viewBox="0 0 20 20" aria-hidden="true"><path d="M7.5 5l5 5-5 5" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  plus: '<svg width="18" height="18" viewBox="0 0 20 20" aria-hidden="true"><path d="M10 4v12M4 10h12" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>',
};
const dot = (c, s, pale) => '<span class="pdot" style="--c:' + esc(colorOf(c)) + ';--s:' + s + 'px"' + (pale ? ' data-pale' : '') + '></span>';
const isPale = c => { const v = colorOf(c); return v === '#ffffff' || /^#f[0-9a-f]f[0-9a-f]/i.test(v); };
function penButton(){ const b = brush('pen'); return sample(b.pen, b.color, b.w, b.opacity, 28, 20); }
function drawPal(){
  const s = P.surface;
  if (!P.seen || !s || !s.live()) { if (P.pal) P.pal.remove(); P.pal = null; return; }
  let p = P.pal;
  if (!p || !p.isConnected || p.parentNode !== s.palHost()) {
    if (p) p.remove();
    p = P.pal = document.createElement('div'); p.className = 'inkpal'; p.setAttribute('role', 'toolbar'); p.setAttribute('aria-label', 'Pen');
    p.addEventListener('click', onPal);
    s.palHost().appendChild(p);
  }
  p.classList.toggle('away', !P.on);
  if (!P.on) { p.innerHTML = '<button data-ink="on" title="Write with the pen" aria-label="Write with the pen">' + IC.pen + '</button>'; return; }
  const b = (k, label, on, dis, inner) => '<button data-ink="' + k + '" title="' + label + '" aria-label="' + label + '"' + (on != null ? ' aria-pressed="' + on + '"' : '') + (dis ? ' disabled' : '') + '>' + (inner || IC[k]) + '</button>';
  const cur = T.tool === 'highlighter' ? hlColor() : T.pens[T.pen].color;
  const extra = s.extras ? s.extras() : [];
  p.innerHTML = b('pen', KINDS[T.pen] + ' (tap again for its kinds, size and colour)', T.tool === 'pen', false, penButton()) +
    b('highlighter', 'Highlighter (tap again for its colour and size)', T.tool === 'highlighter') + b('eraser', 'Eraser (tap again for how it erases; or hold the pen’s button)', T.tool === 'eraser') +
    '<span class="sep"></span>' + (T.tool === 'eraser' ? '' : b('panel', 'Colour and size', null, false, dot(cur, 18, isPale(cur)))) +
    '<span class="sep"></span>' + b('undo', 'Undo', null, !s.canUndo()) + b('redo', 'Redo', null, !s.canRedo()) +
    (extra.length ? '<span class="sep"></span>' + extra.map(x => b(x.k, x.label, x.on, false, IC[x.k])).join('') : '') +
    b('away', 'Put the pen tools away (the pen scrolls and selects)', null);
}
function onPal(e){
  const t = e.target.closest('[data-ink]'); if (!t) return;
  const k = t.dataset.ink, s = P.surface;
  if (k === 'pen' || k === 'highlighter' || k === 'eraser') {
    if (T.tool === k) { if (P.popEl && P.popFor === k) closePop(); else openPop(t, k); return; }
    choose(k); closePop();
  }
  else if (k === 'panel') { if (P.popEl) closePop(); else openPop(t, T.tool); return; }
  else if (k === 'undo') s && s.undo();
  else if (k === 'redo') s && s.redo();
  else if (k === 'away' || k === 'on') { P.on = k === 'on'; put('on', P.on); closePop(); }
  else if (s && s.extra) s.extra(k);
  redraw();
}
const KIND_ROW = (cur, size) => WRITING.map(k => '<button class="kind" data-kind="' + k + '" aria-pressed="' + (cur === k) + '" title="' + KINDS[k] + '" aria-label="' + KINDS[k] + '">' + sample(k, T.pens[k].color, across(k, Math.max(25, T.pens[k].size)), T.pens[k].opacity / 100, 46, 24) + '<span>' + KINDS[k] + '</span></button>').join('');
// The panel for the tool in hand: the pen's kinds, its size, opacity and colour (any colour), or
// the highlighter's, or how the eraser erases. In the round menu too.
function panelHTML(tool, parts){
  parts = parts || ['kinds', 'size', 'opacity', 'colors', 'fav'];
  let h = '';
  if (tool === 'eraser') {
    h += '<div class="pnrow seg2">' + [['stroke', 'Whole strokes'], ['area', 'What it passes over']].map(m => '<button data-er="' + m[0] + '" aria-pressed="' + (T.eraser.mode === m[0]) + '">' + m[1] + '</button>').join('') + '</div>';
    h += '<label class="pnrow"><span>Size</span><input type="range" min="8" max="80" value="' + T.eraser.size + '" data-set="esize" aria-label="Eraser size"><b>' + T.eraser.size + '</b></label>';
    h += '<div class="pnrow"><button class="linkbtn" data-er="all">Erase everything written here</button></div>';
    return h;
  }
  const pen = tool === 'highlighter' ? 'highlighter' : T.pen, p = T.pens[pen], cur = pen === 'highlighter' ? hlColor() : p.color;
  if (tool !== 'highlighter' && parts.includes('kinds')) h += '<div class="pnrow kinds">' + KIND_ROW(T.pen) + '</div>';
  if (parts.includes('size')) h += '<label class="pnrow"><span>Size</span><input type="range" min="1" max="100" value="' + p.size + '" data-set="size" aria-label="Size"><b>' + p.size + '</b></label>';
  if (parts.includes('opacity')) h += '<label class="pnrow"><span>Opacity</span><input type="range" min="5" max="100" value="' + p.opacity + '" data-set="opacity" aria-label="Opacity"><b>' + p.opacity + '</b></label>';
  if (parts.includes('colors')) {
    const list = pen === 'highlighter' ? HLS : COLORS;
    h += '<div class="pnrow colors">' + list.map(c => '<button data-c="' + c + '" aria-pressed="' + (c === cur) + '" title="' + (HLNAME[c] || (c === 'ink' ? 'The text’s colour' : c)) + '" aria-label="' + (HLNAME[c] || (c === 'ink' ? 'The text’s colour' : 'Colour ' + c)) + '">' + dot(c, 22, isPale(c)) + '</button>').join('') +
      (pen === 'highlighter' ? '' : '<label class="custom" title="Any colour"><input type="color" value="' + (/^#/.test(cur) ? cur : '#1e1e1e') + '" data-set="color" aria-label="Any colour"><span></span></label>') + '</div>';
  }
  if (parts.includes('fav') && tool !== 'eraser') h += '<div class="pnrow"><button class="linkbtn" data-fav="+">' + IC.plus + 'Keep this pen as a favourite</button></div>';
  return h;
}
function wirePanel(el, after){
  el.addEventListener('click', e => {
    const b = e.target.closest('button'); if (!b) return;
    if (b.dataset.kind) choose('pen', b.dataset.kind);
    else if (b.dataset.c) setColor(b.dataset.c);
    else if (b.dataset.er === 'all') { if (P.surface && P.surface.eraseAll) P.surface.eraseAll(); }
    else if (b.dataset.er) { T.eraser.mode = b.dataset.er; keep(); }
    else if (b.dataset.fav === '+') addFavorite();
    else return;
    after();
  });
  el.addEventListener('input', e => {
    const t = e.target, k = t.dataset && t.dataset.set; if (!k) return;
    const out = t.parentNode.querySelector('b'); if (out) out.textContent = t.value;
    if (k === 'size') setSize(+t.value);
    else if (k === 'opacity') { const pen = T.tool === 'highlighter' ? 'highlighter' : T.pen; T.pens[pen].opacity = +t.value; keep(); redraw(); }
    else if (k === 'esize') { T.eraser.size = +t.value; keep(); }
    else if (k === 'color') setColor(t.value);
  });
}
function openPop(anchor, tool){
  closePop();
  const el = P.popEl = document.createElement('div'); P.popFor = tool;
  el.className = 'inkpop'; el.setAttribute('role', 'dialog'); el.setAttribute('aria-label', tool === 'eraser' ? 'The eraser' : tool === 'highlighter' ? 'The highlighter' : 'The pen');
  const fill = () => { el.innerHTML = panelHTML(tool); };
  fill();
  wirePanel(el, () => { fill(); place(); });
  document.body.appendChild(el);
  const place = () => {
    const r = anchor.isConnected ? anchor.getBoundingClientRect() : { left: window.innerWidth - 70, top: window.innerHeight / 2, width: 40, height: 40 };
    const w = el.offsetWidth, h = el.offsetHeight;
    if (window.innerWidth <= 640) { el.style.left = Math.max(8, Math.min(window.innerWidth - w - 8, r.left + r.width / 2 - w / 2)) + 'px'; el.style.top = Math.max(8, r.top - h - 10) + 'px'; }
    else { el.style.left = Math.max(8, r.left - w - 12) + 'px'; el.style.top = Math.max(8, Math.min(window.innerHeight - h - 8, r.top + r.height / 2 - h / 2)) + 'px'; }
  };
  place();
  setTimeout(() => document.addEventListener('pointerdown', P.popOff = ev => { if (!ev.target.closest('.inkpop, .inkpal')) closePop(); }, true), 0);
}
function closePop(){ if (P.popEl) { P.popEl.remove(); P.popEl = null; } if (P.popOff) { document.removeEventListener('pointerdown', P.popOff, true); P.popOff = null; } }

/* ---------- the round menu (the S Pen's button over the glass) ---------- */
// As Samsung Notes lays it out: the pen in hand in the middle (tap it for the kinds), its size on
// the left, its colour on the right, Undo and Redo above, the favourite pens and + below.
function openRound(x, y){
  if (!P.surface || !P.surface.live()) return;
  closeRound(); closePop(); ring(null);
  P.roundAt = Date.now();
  const R = 112, cx = Math.min(Math.max(x, R + 8), window.innerWidth - R - 8), cy = Math.min(Math.max(y, R + 8), window.innerHeight - R - 8);
  const el = P.roundEl = document.createElement('div');
  el.className = 'penround'; el.setAttribute('role', 'menu'); el.setAttribute('aria-label', 'Pens');
  el.style.left = cx + 'px'; el.style.top = cy + 'px';
  const fill = () => {
    const tool = T.tool, b = brush(tool === 'eraser' ? 'pen' : tool), cur = tool === 'highlighter' ? hlColor() : T.pens[T.pen].color;
    const mid = tool === 'eraser' ? IC.eraser : sample(b.pen, b.color, b.w, b.opacity, 56, 34);
    const favs = T.favorites.slice(-3).map((f, i) => '<button class="pr fav" data-pr="fav" data-i="' + (T.favorites.length - Math.min(3, T.favorites.length) + i) + '" title="' + KINDS[f.pen] + '" aria-label="Favourite pen: ' + KINDS[f.pen] + '">' + sample(f.pen, f.color, across(f.pen, f.size), f.opacity / 100, 30, 20) + '</button>').join('');
    const sz = tool === 'eraser' ? T.eraser.size : T.pens[tool === 'highlighter' ? 'highlighter' : T.pen].size;
    el.innerHTML = '<div class="prdisc" aria-hidden="true"></div>' +
      '<button class="pr mid" data-pr="kinds" title="' + (tool === 'eraser' ? 'Eraser' : KINDS[b.pen]) + ': tap for the other pens" aria-label="The pens">' + mid + '</button>' +
      '<button class="pr undo" data-pr="undo" aria-label="Undo" title="Undo"' + (P.surface.canUndo() ? '' : ' disabled') + '>' + IC.undo + '</button>' +
      '<button class="pr redo" data-pr="redo" aria-label="Redo" title="Redo"' + (P.surface.canRedo() ? '' : ' disabled') + '>' + IC.redo + '</button>' +
      '<button class="pr size" data-pr="size" aria-label="Size ' + sz + '" title="Size">' + '<span class="pdot" style="--c:currentColor;--s:' + Math.max(4, Math.min(26, tool === 'eraser' ? sz / 3 : across(b.pen, sz))) + 'px"></span></button>' +
      (tool === 'eraser' ? '<button class="pr color" data-pr="eraser" aria-label="How it erases" title="How it erases">' + IC.eraser + '</button>' : '<button class="pr color" data-pr="color" aria-label="Colour" title="Colour">' + dot(cur, 26, isPale(cur)) + '</button>') +
      '<div class="pr favs">' + favs + '<button class="pr add" data-pr="fav+" aria-label="Keep this pen as a favourite" title="Keep this pen as a favourite">' + IC.plus + '</button></div>' +
      '<div class="prsub" hidden></div>';
  };
  const sub = (what) => {
    const s = el.querySelector('.prsub');
    if (!what || s.dataset.what === what) { s.hidden = true; s.dataset.what = ''; return; }
    s.dataset.what = what;
    if (what === 'kinds') s.innerHTML = '<div class="pnrow kinds">' + KIND_ROW(T.tool === 'pen' ? T.pen : '') +
      '<button class="kind" data-tool="highlighter" aria-pressed="' + (T.tool === 'highlighter') + '">' + sample('highlighter', hlColor(), across('highlighter', T.pens.highlighter.size), T.pens.highlighter.opacity / 100, 46, 24) + '<span>Highlighter</span></button>' +
      '<button class="kind" data-tool="eraser" aria-pressed="' + (T.tool === 'eraser') + '">' + IC.eraser + '<span>Eraser</span></button></div>';
    else if (what === 'color') s.innerHTML = panelHTML(T.tool, ['colors']);
    else if (what === 'size') s.innerHTML = panelHTML(T.tool, T.tool === 'eraser' ? null : ['size', 'opacity']);
    else if (what === 'eraser') s.innerHTML = panelHTML('eraser');
    s.hidden = false;
    // above the ring, or below it near the top of the screen
    const top = cy - R - 12 - s.offsetHeight > 8;
    s.style.top = top ? (-R - 12 - s.offsetHeight) + 'px' : (R + 12) + 'px';
    const w = s.offsetWidth, left = Math.max(8 - cx, Math.min(window.innerWidth - 8 - cx - w, -w / 2));
    s.style.left = left + 'px';
  };
  fill();
  el.addEventListener('click', e => {
    const b = e.target.closest('button'); if (!b) return;
    if (b.dataset.tool) { choose(b.dataset.tool); fill(); return; }
    const k = b.dataset.pr;
    if (k === 'kinds' || k === 'color' || k === 'size' || k === 'eraser') { sub(k); return; }
    if (k === 'undo') { P.surface.undo(); fill(); return; }
    if (k === 'redo') { P.surface.redo(); fill(); return; }
    if (k === 'fav') { useFavorite(T.favorites[+b.dataset.i]); closeRound(); return; }
    if (k === 'fav+') { addFavorite(); fill(); return; }
  });
  wirePanel(el.querySelector('.prsub') ? el : el, () => {});
  el.addEventListener('click', e => { const b = e.target.closest('.prsub button[data-kind], .prsub button[data-c]'); if (b) setTimeout(closeRound, 120); });
  document.body.appendChild(el);
  setTimeout(() => document.addEventListener('pointerdown', P.roundOff = ev => { if (!ev.target.closest('.penround')) closeRound(); }, true), 0);
}
function closeRound(){ if (P.roundEl) { P.roundEl.remove(); P.roundEl = null; } if (P.roundOff) { document.removeEventListener('pointerdown', P.roundOff, true); P.roundOff = null; } }

function redraw(){ drawPal(); }
// The shell's own word that the button was pressed, for a WebView that doesn't say (Android: Shell).
window.dafStylusButton = (x, y) => { seenPen(); if (writing() && Date.now() - (P.roundAt || 0) > 500) openRound(x, y); };
document.addEventListener('keydown', e => { if (e.key === 'Escape' && P.roundEl) { e.preventDefault(); e.stopPropagation(); closeRound(); } }, true);
window.addEventListener('resize', () => { closeRound(); closePop(); });
document.addEventListener('visibilitychange', () => { if (document.visibilityState === 'hidden') { closeRound(); ring(null); } });

C.Pens = {
  T, KINDS, COLORS, HLS, across, brush, colorOf, kindOf, opacityOf, shape, layer, sample, snapShape,
  listen, arm,
  // the surface the tools belong to now (an article, a book), or none
  use(s){ P.surface = s; closePop(); closeRound(); drawPal(); },
  surface: () => P.surface,
  redraw, closeRound, openRound, writing, on: () => P.on, seen: () => P.seen,
  state: () => ({ tool: T.tool, pen: T.pen, on: P.on, seen: P.seen, round: !!P.roundEl, eraser: T.eraser.mode }),
};
})();
