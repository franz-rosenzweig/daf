/* Study: two more ways to lay out a reader (study.css).

   Margin (books and articles): the page moves over and a margin opens beside it. Level with each
   highlight on the page there's a line in its colour, and beside the line its note and what's written
   under it in the Notebook. A tap on one opens that highlight, as a tap on the words does. A reader
   hands over where its highlights are (attach), and the margin is drawn again when the page turns or
   they change. The Notebook takes the same room, so one closes the other. A screen too narrow for both
   the page and a margin (a phone, one half of Side by side) has none.

   Side by side: a second Daf on the right half of the window (the same app, at ?pane=1, so it's the
   whole reader: highlights, the Notebook, Aa), reading something else. The reader in the window keeps
   the left half (the Notebook's room on the right, sketchbook.js reserve). Its reading time counts for
   the side touched last, so the same minutes never count twice. */
(() => {
const C = window.DafCore, { api, esc, $ } = C;
const root = document.documentElement;
const PANE = root.classList.contains('pane');
const ls = { get(k, d){ try { const v = localStorage.getItem('daf.' + k); return v == null ? d : JSON.parse(v); } catch(e){ return d; } },
  set(k, v){ try { localStorage.setItem('daf.' + k, JSON.stringify(v)); } catch(e){} } };
const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
const READING = ['read', 'ebook', 'pdf', 'mread'];
const reading = () => READING.includes(document.body.dataset.view);
const roomW = () => C.Sketch ? C.Sketch.room().w : innerWidth;

/* ---------- Margin ---------- */
// ctx: {item (book:… | doc:…), host() (the element the margin goes in: a book's stage, an article's text),
// places() (the highlights on the page: [{id, color, note, top, h}], top from the host's top), pageW() (a
// book's page as wide as its text needs),
// open(id, el) (that highlight's bar, by el), relayout() (the reader lays out again, for a book)}
const M = { ctx: null, words: null, wordsFor: null, shown: false, t: 0 };
const can = () => !PANE && roomW() >= 760;
const active = () => !!M.ctx && !!ls.get('margin', false) && can() && !(C.Sketch && C.Sketch.open()) && (!M.ctx.ok || M.ctx.ok());
const width = () => Math.round(clamp(roomW() * 0.24, 200, 320));

function mount(host){
  let col = host.querySelector(':scope > .mgcol');
  if (!col) { col = document.createElement('div'); col.className = 'mgcol'; host.appendChild(col); }
  host.classList.add('mghost'); root.classList.add('mgopen');
  const mw = width();
  host.style.setProperty('--mgw', mw + 'px');
  // a book's page as wide as its text, and the margin right beside it, the two in the middle
  if (M.ctx.pageW) {
    const W = host.clientWidth, pw = Math.max(240, Math.min(W - mw, Math.round(M.ctx.pageW())));
    host.style.setProperty('--mgv', pw + 'px');
    host.style.setProperty('--mgx', Math.max(0, Math.round((W - pw - mw) / 2)) + 'px');
  }
  // a page that grows (its pictures come in) or narrows: the places again
  if (M.ro && M.roHost !== host) { M.ro.disconnect(); M.ro = null; }
  if (!M.ro && window.ResizeObserver) { M.ro = new ResizeObserver(() => requestAnimationFrame(draw)); M.ro.observe(host); M.roHost = host; }
  return col;
}
function unmount(){
  if (M.ro) { M.ro.disconnect(); M.ro = null; }
  root.classList.remove('mgopen');
  document.querySelectorAll('.mghost').forEach(h => { h.classList.remove('mghost'); ['--mgw', '--mgv', '--mgx'].forEach(k => h.style.removeProperty(k)); });
  document.querySelectorAll('.mgcol').forEach(c => c.remove());
}
// What's written in the Notebook under each highlight: the typed words and the handwriting as it was read.
async function loadWords(){
  const item = M.ctx.item; M.wordsFor = item;
  let r; try { r = await api('/api/sketchbook/' + encodeURIComponent(item) + '/all'); } catch(e){ return; }
  if (!M.ctx || M.ctx.item !== item) return;
  const W = new Map();
  for (const t of r.tabs || []) for (const b of t.blocks || []) {
    const w = (b.kind === 'text' ? b.text : b.kind === 'ink' ? b.transcript : '') || '';
    if (b.hl && w.trim()) { if (!W.has(b.hl)) W.set(b.hl, []); W.get(b.hl).push(w.trim()); }
  }
  M.words = W; draw();
}
function draw(){ clearTimeout(M.t); M.t = setTimeout(drawNow, 40); }
function drawNow(){
  if (!active()) {
    if (M.shown) { M.shown = false; unmount(); if (M.ctx && M.ctx.relayout) M.ctx.relayout(); }
    return;
  }
  const host = M.ctx.host(); if (!host) return;
  const was = M.shown; M.shown = true;
  const col = mount(host);
  if (!was) { M.wordsFor = null; if (M.ctx.relayout) M.ctx.relayout(); }
  if (M.wordsFor !== M.ctx.item) loadWords();
  requestAnimationFrame(() => paint(col));
}
function paint(col){
  if (!M.ctx || !col.isConnected) return;
  let ps; try { ps = M.ctx.places() || []; } catch(e){ ps = []; }
  ps.sort((a, b) => a.top - b.top);
  const W = M.words || new Map(), c = p => 'var(--hl-' + esc(p.color || 'yellow') + '-line)';
  col.innerHTML = ps.map(p => '<button class="mgl" data-mg="' + esc(p.id) + '" style="top:' + Math.round(p.top) + 'px;height:' + Math.round(clamp(p.h, 16, 2000)) + 'px;--c:' + c(p) + '" aria-label="Highlight"></button>').join('') +
    ps.map(p => {
      const note = (p.note || '').trim(), words = W.get(p.id) || [];
      if (!note && !words.length) return '';
      return '<button class="mgn" data-mg="' + esc(p.id) + '" data-top="' + Math.round(p.top) + '" style="--c:' + c(p) + '">' +
        (note ? '<span class="mgnote"' + (/[֐-׿]/.test(note) ? ' dir="rtl"' : '') + '>' + esc(note) + '</span>' : '') +
        words.map(w => '<span class="mgw"' + (/[֐-׿]/.test(w) ? ' dir="rtl"' : '') + '>' + esc(w) + '</span>').join('') + '</button>';
    }).join('');
  // the notes start level with their words, and one that would run into the one above it goes under it
  let below = -Infinity;
  col.querySelectorAll('.mgn').forEach(n => { const t = Math.max(+n.dataset.top, below + 8); n.style.top = t + 'px'; below = t + n.offsetHeight; });
}
document.addEventListener('click', e => {
  const b = e.target.closest && e.target.closest('.mgcol [data-mg]'); if (!b || !M.ctx) return;
  e.preventDefault(); e.stopPropagation();
  M.ctx.open(b.dataset.mg, b);
});
function attach(ctx){ M.ctx = ctx; M.words = null; M.wordsFor = null; M.shown = !!document.querySelector('.mgcol') && M.shown; draw(); }
function detach(){ if (M.shown) unmount(); M.shown = false; M.ctx = null; }
function toggle(){
  const on = !ls.get('margin', false);
  ls.set('margin', on);
  if (on && C.Sketch && C.Sketch.open()) C.Sketch.hide();
  if (on && SP.el) closeSplit();
  drawNow();
}
C.Margin = { attach, detach, draw, toggle, can, active, on: () => !!ls.get('margin', false) };
// the highlights changed (each reader tells the Notebook): the margin too
if (C.Sketch) { const was = C.Sketch.hlChanged; C.Sketch.hlChanged = (...a) => { const r = was(...a); draw(); return r; }; }
window.addEventListener('daf-hl-changed', draw);
window.addEventListener('resize', draw);
window.addEventListener('daf-type', draw);

/* ---------- Side by side ---------- */
const SP = { el: null, w: 0 };
function openSplit(hash){
  if (C.Sketch && C.Sketch.open()) C.Sketch.hide();
  if (!SP.el) {
    SP.el = document.createElement('div'); SP.el.className = 'sbs';
    SP.el.innerHTML = '<iframe title="Side by side" allow="clipboard-write; autoplay"></iframe>';
    document.body.appendChild(SP.el);
  }
  SP.el.querySelector('iframe').src = '/?pane=1' + hash;
  root.classList.add('sbsopen');
  ls.set('split.touch.main', Date.now());
  SP.w = Math.round(innerWidth / 2);
  if (C.Sketch && C.Sketch.reserve) C.Sketch.reserve(SP.w);
  buttons(); draw();
}
function closeSplit(){
  if (!SP.el) return;
  SP.el.remove(); SP.el = null;
  root.classList.remove('sbsopen');
  if (C.Sketch && C.Sketch.reserve) C.Sketch.reserve(0);
  buttons(); draw();
}
const buttons = () => document.querySelectorAll('[data-sbs]').forEach(b => b.classList.toggle('on', !!SP.el));
// (reserve lays the readers out again, with a resize of its own: only a new width is passed on)
window.addEventListener('resize', () => { const w = Math.round(innerWidth / 2); if (SP.el && w !== SP.w && C.Sketch && C.Sketch.reserve) { SP.w = w; C.Sketch.reserve(w); } });
window.addEventListener('message', e => {
  if (e.origin !== location.origin || !e.data || typeof e.data !== 'object') return;
  if (e.data.daf === 'sbs-close') closeSplit();
});
// the window's reader closed (a list, Today): the other side goes with it
const watch = () => new MutationObserver(() => { if (!reading()) { if (SP.el) closeSplit(); if (M.ctx) detach(); } }).observe(document.body, { attributes: true, attributeFilter: ['data-view'] });
if (document.body) watch(); else document.addEventListener('DOMContentLoaded', watch);

// What to read beside it: what's being read now, then anything in Daf by its title.
function pick(){
  const sheet = $('#modal'); $('#scrim').hidden = false; sheet.hidden = false; sheet.classList.remove('wide');
  sheet.innerHTML = '<h2>Side by side</h2><input class="field" id="sbsq" placeholder="Search Daf" autocomplete="off"><div id="sbsres" class="sbsres"></div>' +
    '<div class="sbsbtns"><span class="spacer"></span><button class="btn" data-act="close">Cancel</button></div>';
  $('#sbsres').innerHTML = nowRows();
  setTimeout(() => $('#sbsq') && $('#sbsq').focus(), 30);
}
function nowRows(){
  const d = C.S && C.S.data, here = C.curBook && C.curBook();
  const now = d ? [...(d.nightstand || []), d.offstand].filter(b => b && b.id && b.id !== here) : [];
  return now.length ? '<div class="sbsh">Reading now</div>' + now.map(b => row('ebook', b.id, 'book', b.title, b.author)).join('') : '';
}
const KIND = { book: 'Book', article: 'Article', video: 'Video', torah: 'Torah', podcast: 'Episode' };
const row = (route, id, kind, title, by) => '<button class="sbsrow" data-sbs-go="#' + route + '/' + encodeURIComponent(id) + '"><b' + (/[֐-׿]/.test(title || '') ? ' dir="rtl"' : '') + '>' + esc(title || 'Untitled') + '</b><span class="mute tiny">' + esc([KIND[kind] || '', by || ''].filter(Boolean).join(' · ')) + '</span></button>';
let qT = 0;
document.addEventListener('input', e => {
  if (e.target.id !== 'sbsq') return;
  clearTimeout(qT);
  const q = e.target.value.trim();
  qT = setTimeout(async () => {
    const box = $('#sbsres'); if (!box) return;
    if (q.length < 2) { if (!q) box.innerHTML = nowRows(); return; }
    let r; try { r = await api('/api/search?q=' + encodeURIComponent(q)); } catch(err){ box.textContent = err.message; return; }
    const rows = (r.books || []).map(b => row('ebook', b.id, 'book', b.title, b.author)).concat((r.docs || []).map(x => row('read', x.id, x.kind, x.title, x.source)));
    box.innerHTML = rows.length ? rows.join('') : '<p class="mute tiny">Nothing in Daf</p>';
  }, 220);
});
document.addEventListener('click', e => {
  const g = e.target.closest && e.target.closest('[data-sbs-go]'); if (!g) return;
  e.preventDefault();
  $('#modal').hidden = true; $('#scrim').hidden = true;
  openSplit(g.dataset.sbsGo);
});
function toggleSplit(){ if (SP.el) closeSplit(); else pick(); }

// Reading time: in Side by side, the side touched last is the one being read.
let wrote = 0;
const touch = () => { if (!PANE && !SP.el) return; const n = Date.now(); if (n - wrote < 3000) return; wrote = n; ls.set('split.touch.' + (PANE ? 'pane' : 'main'), n); };
['pointerdown', 'keydown', 'wheel', 'touchstart'].forEach(ev => document.addEventListener(ev, touch, { passive: true, capture: true }));
const mine = () => {
  if (!PANE && !SP.el) return true;
  const me = ls.get('split.touch.' + (PANE ? 'pane' : 'main'), 0), other = ls.get('split.touch.' + (PANE ? 'main' : 'pane'), 0);
  return PANE ? me > other : me >= other;
};
C.Split = { open: () => !!SP.el, can: () => !PANE && innerWidth >= 760, toggle: toggleSplit, close: closeSplit, mine, pane: PANE };

/* ---------- inside the right half ---------- */
// The reader's Back closes this side; nothing here plays the book's sound (the window's reader has it).
if (PANE) {
  C.Sound = null;
  const X = '<svg width="20" height="20" viewBox="0 0 20 20" aria-hidden="true"><path d="M5.5 5.5l9 9M14.5 5.5l-9 9" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>';
  const backs = () => document.querySelectorAll('#main .top [aria-label="Back"]');
  new MutationObserver(() => backs().forEach(b => { if (b.dataset.sbsx) return; b.dataset.sbsx = '1'; b.innerHTML = X; b.setAttribute('aria-label', 'Close'); b.title = 'Close'; }))
    .observe(document.getElementById('main'), { childList: true, subtree: true });
  document.addEventListener('click', e => {
    const b = e.target.closest && e.target.closest('[data-sbsx]'); if (!b) return;
    e.preventDefault(); e.stopPropagation();
    try { parent.postMessage({ daf: 'sbs-close' }, location.origin); } catch(err){}
  }, true);
}
})();
