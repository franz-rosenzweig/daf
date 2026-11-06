/* Underlining with the pen highlights the words (the pens are pens.js; an article's ink is ink.js,
   a book's is in book.js). A stroke along a line of text, just under it or through the bottom of
   its letters, is an underline: the words over it are highlighted, as selecting them does, in the
   highlight colour nearest the pen's, so the highlight is in the Notebook, Highlights, the review
   and the vault like any other. A few lines underlined one after another, a moment apart, make one
   highlight. The pen's panel says what an underline does: Highlight (the highlight takes the
   stroke's place, and Undo brings the ink back), Ask (the stroke stays, with a Highlight button by
   it) or Ink (it stays a stroke).
   Anything else the pen writes stays ink: words, rings, arrows, a tick in the margin, a line that's
   part of handwriting. When in doubt, it's ink. */
(function(){
'use strict';
const C = window.DafCore, Pens = C.Pens, H = C.HL;
const WAIT = 750;                 // how long after the pen lifts the next line can still join in (ms)
const U = { burst: null, last: null, ask: null, why: '' };
const mode = () => Pens.T.under || 'highlight';

/* ---------- a line, drawn ---------- */
// The stroke's points every few pixels along it.
function every(pts, step){
  const out = [[pts[0][0], pts[0][1]]]; let left = step;
  for (let i = 1; i < pts.length; i++) {
    let ax = pts[i - 1][0], ay = pts[i - 1][1], d = Math.hypot(pts[i][0] - ax, pts[i][1] - ay);
    const bx = pts[i][0], by = pts[i][1];
    while (d >= left) { const t = left / d; ax += (bx - ax) * t; ay += (by - ay) * t; out.push([ax, ay]); d -= left; left = step; }
    left -= d;
  }
  return out;
}
// A line drawn along: wider than it's tall, one way across (left to right, or right to left under
// Hebrew), and close to straight, though it may wobble or slope a little. The hooks a pen makes as
// it lands and lifts don't count. Null for anything else: writing, a ring, an arrow, a tick.
function flat(pts){
  if (!pts || pts.length < 2) return null;
  let P = every(pts, 3);
  if (P.length > 12) P = P.slice(2, -2);
  if (P.length < 6) return null;
  let x1 = Infinity, x2 = -Infinity, y1 = Infinity, y2 = -Infinity, mx = 0, my = 0;
  for (const p of P) { x1 = Math.min(x1, p[0]); x2 = Math.max(x2, p[0]); y1 = Math.min(y1, p[1]); y2 = Math.max(y2, p[1]); mx += p[0]; my += p[1]; }
  mx /= P.length; my /= P.length;
  const W = x2 - x1; if (W < 24 || W < 3 * (y2 - y1)) return null;
  let sxx = 0, sxy = 0;
  for (const p of P) { sxx += (p[0] - mx) * (p[0] - mx); sxy += (p[0] - mx) * (p[1] - my); }
  const m = sxy / sxx; if (Math.abs(m) > 0.18) return null;                  // steeper than about 10°
  const k = Math.sqrt(1 + m * m); let dev = 0;
  for (const p of P) dev = Math.max(dev, Math.abs(p[1] - my - m * (p[0] - mx)) / k);
  if (dev > Math.min(12, Math.max(5, 3 + W * 0.03))) return null;            // a wave, a loop, letters
  const run = P[P.length - 1][0] - P[0][0], dir = Math.sign(run);
  if (Math.abs(run) < 0.85 * W) return null;                                 // it came back on itself
  let back = 0;
  for (let i = 1; i < P.length; i++) back += Math.max(0, -(P[i][0] - P[i - 1][0]) * dir);
  if (back > 4 + 0.05 * W) return null;
  // up and down as it goes: the humps of handwriting, not a hand's wobble
  const Q = every(P, 8); let travel = 0;
  for (let i = 1; i < Q.length; i++) travel += Math.abs(Q[i][1] - Q[i - 1][1]);
  if (travel > 8 + 0.3 * W) return null;
  return { x1, x2, W, at: x => my + m * (x - mx) };
}

/* ---------- the words over it ---------- */
function caretIn(doc, x, y){
  if (doc.caretPositionFromPoint) { const p = doc.caretPositionFromPoint(x, y); return p && { node: p.offsetNode, off: p.offset }; }
  if (doc.caretRangeFromPoint) { const r = doc.caretRangeFromPoint(x, y); return r && { node: r.startContainer, off: r.startOffset }; }
  return null;
}
// Which of two places in the text comes first: below 0 when p is before q.
function cmp(doc, p, q){ const r = doc.createRange(); r.setStart(p.node, p.off); return -r.comparePoint(q.node, q.off); }
// The box of the letter by a caret on the line looked at (y), nearest x: the one after it, or the
// one before it at the end of a line.
function letterBy(doc, c, x, y){
  const t = c.node.data; let best = null, bd = Infinity;
  for (let o = Math.max(0, c.off - 2); o <= Math.min(t.length - 1, c.off + 1); o++) {
    if (/\s/.test(t[o])) continue;
    const r = doc.createRange(); r.setStart(c.node, o); r.setEnd(c.node, o + 1);
    const q = r.getClientRects()[0]; if (!q || !q.height) continue;
    const d = (y >= q.top && y <= q.bottom ? 0 : 1000) + (x < q.left ? q.left - x : x > q.right ? x - q.right : 0);
    if (d < bd) { bd = d; best = q; }
  }
  return best;
}
// Where a point of the stroke is in the text: on the line it's under, or through the lower half
// of, found by stepping up from the stroke into the line. miss: it's run past the words on that line.
function spot(doc, x, y, f){
  for (const k of [0, 0.25, 0.5, 0.75, 1, 1.25]) {
    const py = y - k * f, c = caretIn(doc, x, py); if (!c || !c.node || c.node.nodeType !== 3) continue;
    let r = letterBy(doc, c, x, py); if (!r) continue;
    if (py < r.top || py > r.bottom) {      // below the page's last line the caret goes to the line's end: ask again in the line
      const m = (r.top + r.bottom) / 2, c2 = caretIn(doc, x, m);
      const r2 = c2 && c2.node && c2.node.nodeType === 3 && letterBy(doc, c2, x, m); if (r2) r = r2;
    }
    if (y < r.top + 0.45 * r.height) continue;            // over this line's top half: it's the line above's
    if (y > r.bottom + 0.9 * r.height) return null;       // well below the line: not under it
    if (x < r.left - 0.4 * f || x > r.right + 0.4 * f) return { miss: true };
    return { x, top: r.top, h: r.height };
  }
  return null;
}
// A word the line only just reaches into (under a third of it) isn't underlined, nor is the comma
// after the word before it.
function edge(doc, p, end){
  const w = H.isWord;
  let node = p.node, t = node.data, o = p.off;
  if (w(t[o - 1]) && w(t[o])) {
    let s = o, e = o;
    while (s > 0 && w(t[s - 1])) s--;
    while (e < t.length && w(t[e])) e++;
    if ((end ? o - s : e - o) < (e - s) / 3) o = end ? s : e;
  }
  // past a link's last letter, it goes on in the text after the link (and the other way at the end)
  const walk = doc.createTreeWalker(doc.body, NodeFilter.SHOW_TEXT);
  for (let i = 0; i < 3; i++) {
    t = node.data;
    if (!end) { while (o < t.length && /[\s,;:.!?…)\]”]/.test(t[o])) o++; if (o < t.length) break; }
    else { while (o > 0 && /[\s(\[“]/.test(t[o - 1])) o--; if (o > 0) break; }
    walk.currentNode = node; const n = end ? walk.previousNode() : walk.nextNode(); if (!n) break;
    node = n; o = end ? n.data.length : 0;
  }
  return { node, off: o };
}
// The words a line drawn in doc (its points in doc's pixels) underlines: where they start and end
// in the text, all on one line of it. Null when it isn't under words.
function words(doc, g, pts){
  const mid = (g.x1 + g.x2) / 2, el = doc.elementFromPoint(mid, g.at(mid) - 6);
  let f = 16; try { f = parseFloat(doc.defaultView.getComputedStyle(el || doc.body).fontSize) || 16; } catch(e){}
  if (g.W < 1.4 * f) return null;                         // shorter than a short word: a dash, a t's bar
  const S = every(pts, Math.max(5, g.W / 60)), hits = [], lines = [];        // every 5 px, or 60 along a long line
  for (const p of S) { const h = spot(doc, p[0], p[1], f); if (h && !h.miss) hits.push(h); }
  for (const h of hits) {
    const c = h.top + h.h / 2; let l = lines.find(l => Math.abs(l.c - c) < h.h * 0.5);
    if (!l) lines.push(l = { c, hits: [] });
    l.hits.push(h);
  }
  // most of it under words, most of those under one line, and sloping less than a line's height
  const best = lines.sort((a, b) => b.hits.length - a.hits.length)[0];
  if (!best || best.hits.length < 3 || hits.length < 0.6 * S.length || best.hits.length < 0.5 * S.length || Math.abs(g.at(g.x2) - g.at(g.x1)) > 1.1 * best.hits[0].h) return null;
  // the words over it on that line, first and last in the text's order (a Hebrew line runs the other way)
  let a = null, z = null;
  for (const h of hits) {
    const c = caretIn(doc, h.x, best.c); if (!c || !c.node || c.node.nodeType !== 3) continue;
    const p = { node: c.node, off: c.off };
    if (!a || cmp(doc, p, a) < 0) a = p;
    if (!z || cmp(doc, p, z) > 0) z = p;
  }
  if (!a) return null;
  a = edge(doc, a, false); z = edge(doc, z, true);
  if (cmp(doc, a, z) >= 0) return null;
  const r = doc.createRange(); r.setStart(a.node, a.off); r.setEnd(z.node, z.off);
  const text = r.toString();
  if (text.replace(/\s/g, '').length < 2 || text.length > 4 * g.W / f + 12) return null;   // far more text than the line is long: not those words
  return { doc, a, z, h: best.hits[0].h };
}

/* ---------- a moment of underlining ---------- */
// How many lines of text there are from p to q (the end of one underline and the start of the next).
function linesFrom(doc, p, q, h){
  const r = doc.createRange(); r.setStart(p.node, p.off); r.setEnd(q.node, q.off);
  const cs = [];
  for (const x of r.getClientRects()) {
    if (x.width < 0.5 || x.height < 0.5) continue;
    if (x.height > 2.2 * h) return Infinity;              // a whole paragraph between them
    const c = (x.top + x.bottom) / 2; if (!cs.some(v => Math.abs(v - c) < x.height * 0.5)) cs.push(c);
  }
  return cs.length;
}
// The next line down (or the rest of the same one) joins what was underlined a moment ago.
function joins(b, w){
  if (b.doc !== w.doc) return false;
  try {
    if (cmp(b.doc, w.a, b.z) >= 0) return linesFrom(b.doc, b.z, w.a, w.h) <= 2;
    if (cmp(b.doc, w.z, b.a) <= 0) return linesFrom(b.doc, w.z, b.a, w.h) <= 2;
  } catch(e){ return false; }
  return true;
}
const boxOf = pts => { let x1 = Infinity, y1 = Infinity, x2 = -Infinity, y2 = -Infinity; for (const p of pts) { x1 = Math.min(x1, p[0]); y1 = Math.min(y1, p[1]); x2 = Math.max(x2, p[0]); y2 = Math.max(y2, p[1]); } return [x1, y1, x2, y2]; };
const gap = (p, q) => Math.max(0, p[0] - q[2], q[0] - p[2], p[1] - q[3], q[1] - p[3]);
const union = (p, q) => [Math.min(p[0], q[0]), Math.min(p[1], q[1]), Math.max(p[2], q[2]), Math.max(p[3], q[3])];

// A pen stroke kept (s, on surf): an underline, or part of one a moment ago, or ink.
function end(L, s, surf){
  const box = boxOf(L.pts), last = U.last, b = U.burst;
  U.last = { t: Date.now(), box, under: false };
  if (mode() === 'ink' || !surf.underline) { U.why = 'ink'; return; }
  const o = surf.off ? surf.off(L.doc) : [0, 0], pts = L.pts.map(p => [p[0] - o[0], p[1] - o[1]]);
  const g = flat(pts);
  let w = null;
  try { w = g && words(L.doc, g, pts); } catch(e){ w = null; }
  // a line that's part of handwriting (a t's bar, a dash) comes just after other writing by it
  if (w && last && !last.under && L.t0 - last.t < 1000 && gap(last.box, box) < 2 * w.h) { w = null; U.why = 'writing'; }
  else if (!w) U.why = g ? 'not under words' : 'not a line';
  if (!w) {
    // writing by what was just underlined (an arrow's head, a mark on it) leaves it all ink
    if (b) { if (gap(b.box, box) < 1.5 * b.h) cancel('writing by it'); else settle(); }
    return;
  }
  U.last.under = true; U.why = 'underline';
  if (b && b.surf === surf && joins(b, w)) {
    if (cmp(w.doc, w.a, b.a) < 0) b.a = w.a;
    if (cmp(w.doc, w.z, b.z) > 0) b.z = w.z;
    b.strokes.push(s); b.box = union(b.box, box); b.lastBox = box;
  } else {
    if (b) settle();
    U.burst = { surf, doc: L.doc, a: w.a, z: w.z, h: w.h, strokes: [s], color: L.brush && L.brush.color, box, lastBox: box };
  }
  const nb = U.burst; clearTimeout(nb.timer); nb.timer = setTimeout(() => ripe(nb), WAIT);
}
function ripe(b){
  if (U.burst !== b) return;
  if (Pens.busy()) { b.timer = setTimeout(() => ripe(b), 150); return; }   // the pen's writing again: see what it is first
  settle();
}
// The moment's over: its words highlighted, or the Highlight button by them.
function settle(){
  const b = U.burst; if (!b) return;
  U.burst = null; clearTimeout(b.timer);
  if (mode() === 'ask') ask(b); else make(b);
}
function cancel(why){ const b = U.burst; if (!b) return; U.burst = null; clearTimeout(b.timer); U.why = why; }
async function make(b){
  if (!b.doc.defaultView) return;                          // its page has gone
  const range = b.doc.createRange();
  try { range.setStart(b.a.node, b.a.off); range.setEnd(b.z.node, b.z.off); } catch(e){ return; }
  const back = await b.surf.underline(b.doc, range, nearest(b.color), b.strokes);
  if (!back) { U.why = 'not highlighted'; return; }
  U.why = 'highlighted';
  H.undo('Highlighted', async () => back());
}

/* ---------- Ask: the Highlight button by it ---------- */
function ask(b){
  unask();
  const el = document.createElement('div'); el.className = 'penheld penask'; el.setAttribute('role', 'toolbar'); el.setAttribute('aria-label', 'Underline');
  el.innerHTML = '<button data-ul="hl">' + H.IC.marker + 'Highlight</button>';
  document.body.appendChild(el);
  const w = el.offsetWidth, h = el.offsetHeight, x = b.lastBox, vh = window.innerHeight;
  el.style.left = Math.max(8, Math.min(window.innerWidth - w - 8, x[2] - w)) + 'px';
  el.style.top = (x[3] + 10 + h < vh - 8 ? x[3] + 10 : Math.max(8, x[1] - h - 10)) + 'px';
  // it goes when the words under it move (a scroll, a page turned), or after a while
  const where = () => { try { const r = b.doc.createRange(); r.setStart(b.a.node, b.a.off); const q = r.getBoundingClientRect(), o = b.surf.off ? b.surf.off(b.doc) : [0, 0]; return Math.round(q.left + o[0]) + ',' + Math.round(q.top + o[1]); } catch(e){ return ''; } };
  const at = where(), t0 = Date.now();
  const watch = setInterval(() => { if (!b.doc.defaultView || where() !== at || Date.now() - t0 > 12000) unask(); }, 250);
  U.ask = { b, el, watch };
  el.addEventListener('click', e => { if (!e.target.closest('[data-ul]')) return; const a = U.ask; unask(); if (a) make(a.b); });
}
function unask(){ const a = U.ask; if (!a) return; U.ask = null; clearInterval(a.watch); a.el.remove(); }

// The highlight colour nearest the pen's: red is pink, orange yellow, teal green; black, grey,
// white or the text's own colour is your highlight colour.
const HUES = { yellow: 47, green: 116, blue: 213, pink: 338, purple: 262 };     // their lines, in the light theme
function nearest(c){
  if (!/^#[0-9a-f]{6}$/i.test(c || '')) return H.color();
  const [r, g, b] = [1, 3, 5].map(i => parseInt(c.slice(i, i + 2), 16) / 255);
  const hi = Math.max(r, g, b), lo = Math.min(r, g, b), d = hi - lo, l = (hi + lo) / 2, s = d ? d / (1 - Math.abs(2 * l - 1)) : 0;
  if (s < 0.25 || l < 0.12 || l > 0.92) return H.color();
  const hue = ((hi === r ? ((g - b) / d) % 6 : hi === g ? (b - r) / d + 2 : (r - g) / d + 4) * 60 + 360) % 360;
  let best = 'yellow', bd = Infinity;
  for (const [k, v] of Object.entries(HUES)) { const x = Math.min(Math.abs(hue - v), 360 - Math.abs(hue - v)); if (x < bd) { bd = x; best = k; } }
  return best;
}

C.Underline = {
  // pens.js: a pointer down in a document the pens listen to, a stroke begun, a pen stroke kept, another surface
  down(e){
    const on = sel => !!(e.target && e.target.closest && e.target.closest(sel));
    if (U.ask && !on('.penask')) unask();
    // a finger on the page may move it: what's waiting is done now (the pen's tools wait, so their Undo takes the stroke)
    if (e.pointerType !== 'pen' && U.burst && !on('.inkpal, .inkpop, .penround')) { if (mode() === 'ask') cancel('touched'); else settle(); }
  },
  start(L){ if (L.tool === 'pen' || !U.burst) return; if (L.tool === 'eraser') cancel('erased'); else settle(); },
  end,
  drop(){ cancel('gone'); unask(); },
  flat, nearest,
  state: () => ({ mode: mode(), pending: U.burst ? U.burst.strokes.length : 0, ask: !!U.ask, why: U.why }),
};
document.addEventListener('keydown', () => unask(), true);
})();
