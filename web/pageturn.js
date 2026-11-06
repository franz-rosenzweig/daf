/* Page turns for a book in Pages (Aa → Page turn): None, the next page is simply there, as it always
   was; Slide, the page slides away and the next comes in beside it; Curl, the page lifts at its
   corner and turns over like paper with the next one underneath (on a two-page spread the right page
   turns onto the left, and a Hebrew book turns the other way).

   Taps, keys, the volume buttons and swipes all come here through the view's goLeft and goRight
   (book.js), one turn each and in the order they came: a turn asked for while one is moving sends
   that one straight to its end first, so none is lost and none counts twice. A swipe holds the page
   under the finger and lets it go on over or fall back when the finger lifts.

   The page that moves is a picture the browser takes of it (a view transition), so the page coming is
   already the real one underneath, and the browser moves the picture itself. Where there are no view
   transitions, Slide is foliate's own slide and Curl is Slide. With reduced motion asked for, the
   pages just turn. */
(() => {
'use strict';
const C = window.DafCore;
const PT = C.PageTurn = {};
const root = document.documentElement, $ = s => document.querySelector(s);
const VT = typeof document.startViewTransition === 'function';
const still = matchMedia('(prefers-reduced-motion: reduce)');
const MS = { slide: 300, curl: 560 };
let S = null;     // the open book: { view, r: foliate's paginator, go: its own turns, q: turns waiting, busy, cur: the one moving }

// What Aa says on this device (the same for every book), and whether it applies now.
PT.choice = () => { const t = C.typeFor ? C.typeFor() : {}; return t.turn === 'slide' || t.turn === 'curl' ? t.turn : 'none'; };
const mode = () => still.matches || document.body.dataset.flow !== 'paginated' ? 'none' : PT.choice();
// Ours to draw; else foliate's own (its swipe that follows the finger, its slide where there's no view transition).
const ours = () => VT && mode() !== 'none';

PT.attach = view => {
  const r = view.renderer;
  if (!r || r.localName !== 'foliate-paginator') return;
  PT.detach();
  S = { view, r, go: { left: view.goLeft.bind(view), right: view.goRight.bind(view) }, q: [], busy: false, cur: null, index: null };
  view.goLeft = () => ask('left');
  view.goRight = () => ask('right');
  // foliate's swipe drags the page and settles it; with Slide and Curl the finger is ours instead
  const scrollBy = r.scrollBy.bind(r), snap = r.snap.bind(r);
  r.scrollBy = (dx, dy) => { if (!ours()) scrollBy(dx, dy); };
  r.snap = (vx, vy) => { if (!ours()) snap(vx, vy); };
  const s = S;
  r.addEventListener('relocate', e => { s.index = e.detail.index; });
  view.addEventListener('load', e => fingers(e.detail.doc, s));
  fingers(r, s);
  native();
};
// The book closed: nothing left to turn.
PT.detach = () => {
  if (S) { const q = S.q; S.q = []; q.forEach(t => t.done && t.done()); if (S.cur) S.cur.hurry = true; }
  S = null; done();
};
// Without view transitions, Slide is foliate's: it slides when it has `animated`.
function native(){ if (S) S.r.toggleAttribute('animated', !VT && mode() !== 'none'); }
window.addEventListener('daf-type', native);
window.addEventListener('hashchange', () => { if (S && !location.hash.startsWith('#ebook/')) PT.detach(); });
// turned sideways mid-turn: the page's shapes are for the old size, so it goes straight to its end
window.addEventListener('resize', () => { if (S && S.cur) S.cur.hurry = true; });

/* ---------- one turn at a time, every one of them ---------- */
function ask(side, drag){
  if (!S) return Promise.resolve();
  const c = S.cur; if (c && (!c.drag || c.drag.up)) c.hurry = true;     // the one moving goes straight to its end
  // (a key held down repeats faster than pages turn: past a few waiting, the repeats aren't kept)
  if (!drag && S.q.length >= 3) return Promise.resolve();
  return new Promise(ok => { S.q.push({ side, drag, done: ok }); pump(); });
}
async function pump(){
  const s = S;
  if (!s || s.busy) return;
  s.busy = true;
  while (s.q.length) {
    const t = s.q.shift();
    try { await turn(s, t); } catch(e){ console.warn('page turn', e); }
    t.done();
    if (s !== S) return;              // the book closed meanwhile
  }
  s.busy = false;
}
// Something open over the page (a menu, a sheet, focus mode's bar) would be covered while it moves:
// the page just turns then.
const covered = () => !$('#pop').hidden || !$('#modal').hidden || root.classList.contains('fbar') ||
  document.body.classList.contains('btocsheet') || document.body.classList.contains('bpanelsheet');

async function turn(s, t){
  const r = s.r, kind = mode(), rtl = s.view.book.dir === 'rtl', fwd = (t.side === 'right') !== rtl, stage = $('#bstage');
  if (!ours() || document.hidden || covered() || !stage || vertical(r)) return s.go[t.side]();
  if (fwd ? r.atEnd : r.atStart) return;                      // nothing on that side
  const box = stage.getBoundingClientRect(), cross = fwd ? r.page + 1 >= r.pages - 1 : r.page - 1 <= 0;
  // into the next chapter the page under the finger goes away with its chapter: that swipe just turns
  if (cross) t.drag = null;
  Object.assign(t, { kind, fwd, rtl, W: box.width, H: box.height, S: spread(r) ? box.width / 2 : 0, top: !!(t.drag && t.drag.top) });
  t.p = fwd ? 0 : 1;                                           // how far over the page is: 0 lying as it was, 1 turned
  t.D = cornerAt(t, t.p);
  s.cur = t;
  root.classList.add('ptturn');
  paint(t);
  let turned = Promise.resolve(), moved = false;
  const vt = document.startViewTransition(() => {
    if (kind === 'curl') fx(t, box);
    const from = s.index, there = new Promise(ok => {
      const on = e => { if (!cross || e.detail.index !== from) { moved = true; r.removeEventListener('relocate', on); ok(); } };
      r.addEventListener('relocate', on);
      setTimeout(() => { r.removeEventListener('relocate', on); ok(); }, 3500);
      turned = s.go[t.side]();
      turned.then(() => { r.removeEventListener('relocate', on); ok(); });
    });
    return there;
  });
  let hold = null;
  try {
    await vt.ready;
    if (moved && S === s) {
      // a view transition lasts while something on it moves: this does, until the page is down
      hold = root.animate([{ opacity: 1 }, { opacity: 1 }], { duration: 60000, pseudoElement: '::view-transition-group(dafpage)' });
      t.live = true; paint(t);
      if (t.drag) await follow(s, t);
      else await tween(t, fwd ? 1 : 0, MS[kind]);
    }
  } catch(e){}
  t.live = false;
  try { vt.skipTransition(); } catch(e){}
  await vt.finished.catch(() => {});
  if (hold) hold.cancel();
  if (s.cur === t) { s.cur = null; done(); }
  await turned;
  if (t.back) await t.back;           // a swipe let go short of turning: the book turned back under it
}
function done(){ root.classList.remove('ptturn'); write(''); const f = $('#ptfx'); if (f) f.remove(); }
const vertical = r => { const c = r.getContents()[0]; return !!c && /^vertical/.test(getComputedStyle(c.doc.documentElement).writingMode || ''); };
// Two pages side by side: foliate's columns, two to the screen.
function spread(r){
  const c = r.getContents()[0]; if (!c) return false;
  const st = getComputedStyle(c.doc.documentElement), w = parseFloat(st.columnWidth), g = parseFloat(st.columnGap) || 0;
  return w > 0 && Math.round(r.size / (w + g)) >= 2;
}

/* ---------- moving it: in time, or with the finger ---------- */
const ease = x => x < .5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2;
const out = x => 1 - Math.pow(1 - x, 3);
// From where it is to `to` (1 turned over, 0 lying flat): the whole way in `ms`, part of it in less.
function tween(t, to, ms){
  const p0 = t.p, D0 = t.D, start = performance.now(), D1 = cornerAt(t, to);
  ms *= Math.max(.4, Math.min(1, Math.abs(to - p0) * (t.drag ? 1.5 : 1)));
  return new Promise(ok => {
    const step = now => {
      const k = t.hurry || !t.live ? 1 : Math.min(1, (now - start) / ms), e = t.drag ? out(k) : ease(k);
      t.p = p0 + (to - p0) * e;
      // in time the corner goes round over the spine; let go of, it goes straight from where the finger left it
      t.D = t.drag ? [D0[0] + (D1[0] - D0[0]) * e, D0[1] + (D1[1] - D0[1]) * e] : cornerAt(t, t.p);
      paint(t);
      if (k < 1) requestAnimationFrame(step); else ok();
    };
    requestAnimationFrame(step);
  });
}
// The finger: the page follows it until it lifts, then goes on over if it went far enough or was
// flicked, or falls back and the book turns back under it.
async function follow(s, t){
  const d = t.drag;
  await new Promise(ok => { d.on = () => { if (t.live) { place(t, d); paint(t); } }; d.lift = ok; d.on(); if (d.up) ok(); });
  // (forward the page goes on to 1, back it comes down to 0)
  const v = t.rtl ? -d.v : d.v, go = t.fwd ? t.p > .3 || v < -.3 : t.p < .7 || v > .3;
  await tween(t, go === t.fwd ? 1 : 0, MS[t.kind]);
  if (!go) t.back = s.go[t.side === 'left' ? 'right' : 'left']();
}
// Where the finger puts the page: dx along the book (< 0 toward its spine), dy down the page.
function place(t, d){
  const dx = t.rtl ? -d.dx : d.dx, dy = t.top ? -d.dy : d.dy, span = t.W - t.S;
  if (t.kind === 'slide') { t.p = Math.max(0, Math.min(1, (t.fwd ? 0 : 1) - dx / t.W)); return; }
  // the corner moves twice as fast as the finger, so the fold stays under it
  t.D = clampD(t, [(t.fwd ? t.W : 2 * t.S - t.W) + 2 * dx, t.H + Math.min(0, dy) * .6]);
  t.p = Math.max(0, Math.min(1, (t.W - t.D[0]) / (2 * span)));
}

/* ---------- the finger on the page ---------- */
// On each chapter's page (its own frame) and on foliate's margins: a sideways drag in Pages turns.
function fingers(target, s){
  let f = null;
  const win = target.defaultView || window;
  // where the finger is on the screen: the chapter's frame moves as its page turns under the finger
  const xy = e => { const a = e.changedTouches[0], fr = win.frameElement, b = fr ? fr.getBoundingClientRect() : { left: 0, top: 0 }; return [b.left + a.clientX, b.top + a.clientY]; };
  target.addEventListener('touchstart', e => {
    f = null;
    if (S !== s || e.touches.length !== 1 || !ours()) return;
    const [x, y] = xy(e);
    f = { x, y };
  }, { passive: true });
  target.addEventListener('touchmove', e => {
    if (!f || S !== s) return;
    if (e.touches.length !== 1) { up(f, true); f = null; return; }
    const [x, y] = xy(e), now = e.timeStamp;
    if (!f.d) {
      const dx = x - f.x, dy = y - f.y;
      if (Math.abs(dx) < 14 || Math.abs(dx) < 1.3 * Math.abs(dy)) return;
      const sel = target.getSelection && target.getSelection(); if (sel && !sel.isCollapsed) { f = null; return; }
      const box = $('#bstage').getBoundingClientRect();
      f.d = { dx: 0, dy: 0, v: 0, top: f.y - box.top < box.height / 2, on: () => {}, at: now, lx: x };
      ask(dx < 0 ? 'right' : 'left', f.d);
    }
    const d = f.d;
    d.v = (x - d.lx) / Math.max(8, now - d.at); d.lx = x; d.at = now;
    d.dx = x - f.x; d.dy = y - f.y;
    cancelAnimationFrame(d.raf); d.raf = requestAnimationFrame(() => d.on());
  }, { passive: true });
  target.addEventListener('touchend', () => { if (f) up(f, false); f = null; }, { passive: true });
  target.addEventListener('touchcancel', () => { if (f) up(f, true); f = null; }, { passive: true });
  function up(f, cancel){
    const d = f.d; if (!d || d.up) return;
    d.up = true; cancelAnimationFrame(d.raf);
    if (cancel) { d.v = 0; d.dx = 0; d.dy = 0; }
    if (d.lift) d.lift();
    // the click a lifted finger can still make isn't a tap on the page
    const stop = ev => { ev.stopPropagation(); ev.preventDefault(); };
    win.addEventListener('click', stop, true); setTimeout(() => win.removeEventListener('click', stop, true), 400);
  }
}

/* ---------- drawing it ---------- */
// The transition's pictures take their shapes from one small style sheet, written each frame.
function write(css){
  let st = document.getElementById('ptstyle');
  if (!st) { st = document.createElement('style'); st.id = 'ptstyle'; document.head.appendChild(st); }
  if (st.textContent !== css) st.textContent = css;
}
const OLD = '::view-transition-old(dafpage)', NEW = '::view-transition-new(dafpage)';
const px = v => v.toFixed(1) + 'px';
function paint(t){
  if (t.kind === 'slide') {
    // the page going and the page coming, side by side; turning back is the same backwards
    const m = t.rtl ? -1 : 1, [going, coming] = t.fwd ? [OLD, NEW] : [NEW, OLD];
    write(going + '{transform:translateX(' + px(-t.p * t.W * m) + ')}' + coming + '{transform:translateX(' + px((1 - t.p) * t.W * m) + ')}');
    return;
  }
  const g = fold(t, t.D), path = shape(t, g.Q) + shape(t, g.F);
  // The page that lies flat is on top: forward the one going, back the one coming. It's cut away
  // where it has lifted, and where its turned part lies over it, so the other page shows under the
  // flap: on a spread that's the left page the flap becomes as it lands.
  write((t.fwd ? OLD : NEW) + '{z-index:2;clip-path:' + (path ? 'path(evenodd,"' + path + '")' : 'inset(50%)') + '}' + (t.fwd ? NEW : OLD) + '{z-index:1}');
  const el = $('#ptfx'); if (!el) return;
  const [flap, shade] = el.children;
  if (!g.F.length) { flap.style.clipPath = shade.style.clipPath = 'inset(50%)'; return; }
  // the flap: the back of the page, lit where it bends, a little darker toward its edge
  const a = along(t, g.M, [-g.n[0], -g.n[1]]), w = g.w;
  flap.style.clipPath = poly(t, g.F);
  // (no blurred shadow under it: blurring a picture that size every frame is too slow on a tablet)
  flap.style.background = 'linear-gradient(' + a.deg + 'deg,var(--pt-bend) ' + px(a.t) + ',var(--pt-paper) ' + px(a.t + Math.min(28, w * .3)) + ',var(--pt-paper) ' + px(a.t + w * .6) + ',var(--pt-edge) ' + px(a.t + w - 2) + ',var(--pt-rim) ' + px(a.t + w) + ')';
  flap.style.opacity = t.S ? String(Math.max(0, Math.min(1, (1 - t.p) / .22))) : '1';
  // the shadow the lifted page casts on the one under it, along the fold: none while it's barely
  // lifted, and gone again as it lies down on the other side
  const b = along(t, g.M, g.n), reach = Math.min(48, Math.max(10, w * .35)), dark = .3 * Math.min(1, w / 60, (1 - t.p) / .25);
  shade.style.clipPath = poly(t, g.P);
  shade.style.background = 'linear-gradient(' + b.deg + 'deg,rgba(0,0,0,' + dark.toFixed(3) + ') ' + px(b.t) + ',rgba(0,0,0,0) ' + px(b.t + reach) + ')';
}
// The flap and its shadow: one more picture over the page (its own name in the transition), made as
// the page turns and gone after.
function fx(t, box){
  let el = $('#ptfx'); if (el) el.remove();
  el = document.createElement('div'); el.id = 'ptfx';
  el.style.cssText = 'left:' + px(box.left) + ';top:' + px(box.top) + ';width:' + px(box.width) + ';height:' + px(box.height);
  el.innerHTML = '<i></i><i></i>';
  document.body.appendChild(el);
  paint(t);
}

/* ---------- the curl's geometry ---------- */
// Worked in the book's own frame: the spine at S (0 for a single page, the middle of a spread), the
// page that turns from S to W, its corner C at the bottom right. The corner goes to D, and the fold
// is the line halfway between them. A Hebrew book is the same mirrored, a page taken by its top
// corner the same upside down (scr).
const sub = (a, b) => [a[0] - b[0], a[1] - b[1]], dot = (a, b) => a[0] * b[0] + a[1] * b[1];
// The corner on its way over, in time: round over the spine and down on the other side.
function cornerAt(t, p){
  const a = t.W - t.S, th = Math.PI * p;
  return [t.S + a * Math.cos(th), t.H - Math.min(t.H * .3, a * .6) * Math.sin(th)];
}
// Paper doesn't stretch: the corner gets no further from either end of the spine than it was.
function clampD(t, D){
  for (const [A, R] of [[[t.S, t.H], t.W - t.S], [[t.S, 0], Math.hypot(t.W - t.S, t.H)]]) {
    const v = sub(D, A), l = Math.hypot(v[0], v[1]); if (l > R) D = [A[0] + v[0] * R / l, A[1] + v[1] * R / l];
  }
  return [D[0], Math.min(t.H, D[1])];
}
// The part of a convex polygon on one side of the line through m across n (keep 1: the side n points to).
function cut(pg, n, m, keep){
  const res = [], s = q => keep * dot(sub(q, m), n);
  for (let i = 0; i < pg.length; i++) {
    const a = pg[i], b = pg[(i + 1) % pg.length], sa = s(a), sb = s(b);
    if (sa >= 0) res.push(a);
    if ((sa >= 0) !== (sb >= 0)) { const k = sa / (sa - sb); res.push([a[0] + (b[0] - a[0]) * k, a[1] + (b[1] - a[1]) * k]); }
  }
  return res;
}
// Q: what still lies flat; P: what has lifted (the page under it shows there); F: the lifted part
// folded over, lying on Q; w: how far the fold is from the corner.
function fold(t, D){
  const Cn = [t.W, t.H], v = sub(Cn, D), l = Math.hypot(v[0], v[1]), box = [[0, 0], [t.W, 0], [t.W, t.H], [0, t.H]];
  if (l < .5) return { Q: box, P: [], F: [], n: [1, 0], M: Cn, w: 0 };
  const n = [v[0] / l, v[1] / l], M = [(Cn[0] + D[0]) / 2, (Cn[1] + D[1]) / 2];
  const P = cut(box, n, M, 1), Q = cut(box, n, M, -1);
  const F = P.map(q => { const k = 2 * dot(sub(q, M), n); return [q[0] - k * n[0], q[1] - k * n[1]]; });
  return { Q, P, F, n, M, w: Math.max(0, ...P.map(q => dot(sub(q, M), n))) };
}
// The book's frame to the screen's (the stage's own pixels).
const scr = (t, q) => [t.rtl ? t.W - q[0] : q[0], t.top ? t.H - q[1] : q[1]];
const shape = (t, pg) => pg.length > 2 ? 'M' + pg.map(q => scr(t, q).map(v => v.toFixed(1)).join(' ')).join('L') + 'Z' : '';
const poly = (t, pg) => pg.length > 2 ? 'polygon(' + pg.map(q => scr(t, q).map(px).join(' ')).join(',') + ')' : 'inset(50%)';
// A linear-gradient running along u (in the book's frame), and where the line through m falls on it.
function along(t, m, u){
  const us = [t.rtl ? -u[0] : u[0], t.top ? -u[1] : u[1]], ms = scr(t, m), rad = Math.atan2(us[0], -us[1]);
  const L = Math.abs(t.W * Math.sin(rad)) + Math.abs(t.H * Math.cos(rad));
  return { deg: (rad * 180 / Math.PI).toFixed(2), t: (ms[0] - t.W / 2) * us[0] + (ms[1] - t.H / 2) * us[1] + L / 2 };
}
})();
