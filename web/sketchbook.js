/* The Sketchbook: pages beside whatever is open (a book, an article, a video, a podcast episode, a
   PDF, a manga volume) to write and draw on with the pen, type on, and say things into. Kept on the
   server (daf/sketchbook.py), in the vault as a note of its own in the Ink plugin's format
   (sketchvault.py), and, for a book, on the Kindle.

   Sideways it's a panel on the right whose width you drag; upright, a sheet from the bottom you pull
   to the height you want, or flip to the top. The reader beside it gets the rest of the screen. The
   page is in a frame of its own, so the pens (pens.js) take it as a surface as they take a book's
   pages: the pen writes, a finger scrolls, the S Pen's button opens the round menu, the lasso reads
   handwriting into text.

   A page is blocks one under another, as Ink has them in a note: typed text, handwriting on ruled
   lines (an Ink writing block, INK_W units across, drawn to the page's width), drawings, and
   pictures you can write on. Writing under the last block starts a new handwriting block; writing
   on near the bottom of one makes it longer. A tap with a finger (or a click) under everything types
   there; on typed text, it's typed into; on a block, the block's bar (move it, type under it, delete
   it). A tap with the pen is a dot. Handwriting is read as text a moment after the pen rests (pens.js's
   reader), for the note's search and the Kindle.

   A book has a tab a chapter, following where you are, and General; a manga series a tab a volume;
   anything else one page. A video's typed notes and new handwriting carry its time. The camera puts
   the manga page or the PDF page (or the part of it a box is dragged round) on the page, to write
   over. The microphone records, and the server writes down what was said.

   The pens' tools belong to the surface the pen is over: the Sketchbook's on its page, the book's or
   the article's on theirs. Changes go in one request a moment after they're made; offline they wait
   in the outbox, and the page shows them as if they'd gone. */
(function(){
'use strict';
const C = window.DafCore, Pens = C.Pens;
const { api, esc, toast } = C;
const NS = 'http://www.w3.org/2000/svg';
const INK_W = 2000, LINE = 150;                  // an Ink writing block: its width and its ruled lines, in its units
const READING = ['read', 'ebook', 'pdf', 'mread'];
const store = { get(k, d){ try { const v = localStorage.getItem('daf.sketch.' + k); return v == null ? d : JSON.parse(v); } catch(e){ return d; } },
                set(k, v){ try { localStorage.setItem('daf.sketch.' + k, JSON.stringify(v)); } catch(e){} } };
const r1 = v => Math.round(v * 10) / 10, r2 = v => Math.round(v * 100) / 100;
const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
const newId = p => { const b = new Uint8Array(10); crypto.getRandomValues(b); return p + Array.from(b, x => x.toString(16).padStart(2, '0')).join(''); };
const stampOf = t => { t = Math.floor(t || 0); const h = Math.floor(t / 3600), m = Math.floor(t % 3600 / 60), s = String(t % 60).padStart(2, '0'); return h ? h + ':' + String(m).padStart(2, '0') + ':' + s : m + ':' + s; };
const IC = {
  book: '<svg width="18" height="18" viewBox="0 0 20 20" aria-hidden="true"><path d="M4.5 3.5h8l3 3v10h-11z" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/><path d="M7 13.2l.5-2 4.4-4.4a1.1 1.1 0 0 1 1.5 1.5L9 12.7z" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round"/></svg>',
  text: '<svg width="20" height="20" viewBox="0 0 20 20" aria-hidden="true"><path d="M4.5 5.5V4h11v1.5M10 4v12M7.5 16h5" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  textBelow: '<svg width="18" height="18" viewBox="0 0 20 20" aria-hidden="true"><path d="M4 3.5h9M8.5 3.5v8M14.5 10v7M11 13.5h7" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  mic: '<svg width="20" height="20" viewBox="0 0 20 20" aria-hidden="true"><rect x="7.5" y="2.5" width="5" height="9.5" rx="2.5" fill="none" stroke="currentColor" stroke-width="1.6"/><path d="M4.5 9.5a5.5 5.5 0 0 0 11 0M10 15v2.5" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg>',
  stop: '<svg width="20" height="20" viewBox="0 0 20 20" aria-hidden="true"><rect x="5.5" y="5.5" width="9" height="9" rx="2" fill="currentColor"/></svg>',
  shot: '<svg width="20" height="20" viewBox="0 0 20 20" aria-hidden="true"><path d="M3 7.5a1.5 1.5 0 0 1 1.5-1.5h2l1.2-1.8h4.6L13.5 6h2A1.5 1.5 0 0 1 17 7.5v7a1.5 1.5 0 0 1-1.5 1.5h-11A1.5 1.5 0 0 1 3 14.5z" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/><circle cx="10" cy="11" r="2.8" fill="none" stroke="currentColor" stroke-width="1.6"/></svg>',
  time: '<svg width="20" height="20" viewBox="0 0 20 20" aria-hidden="true"><circle cx="10" cy="10" r="6.8" fill="none" stroke="currentColor" stroke-width="1.6"/><path d="M10 6.2V10l2.6 1.8" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  undo: '<svg width="20" height="20" viewBox="0 0 20 20" aria-hidden="true"><path d="M7.5 4.5 4 8l3.5 3.5" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/><path d="M4.5 8H12a4 4 0 0 1 0 8H9" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/></svg>',
  redo: '<svg width="20" height="20" viewBox="0 0 20 20" aria-hidden="true"><path d="M12.5 4.5 16 8l-3.5 3.5" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/><path d="M15.5 8H8a4 4 0 0 0 0 8h3" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/></svg>',
  up: '<svg width="18" height="18" viewBox="0 0 20 20" aria-hidden="true"><path d="M5.5 12.5 10 8l4.5 4.5" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  down: '<svg width="18" height="18" viewBox="0 0 20 20" aria-hidden="true"><path d="M5.5 7.5 10 12l4.5-4.5" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  toTop: '<svg width="20" height="20" viewBox="0 0 20 20" aria-hidden="true"><path d="M4 4.5h12M10 16V8M6.5 11.5 10 8l3.5 3.5" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  toBottom: '<svg width="20" height="20" viewBox="0 0 20 20" aria-hidden="true"><path d="M4 15.5h12M10 4v8M6.5 8.5 10 12l3.5-3.5" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  close: '<svg width="18" height="18" viewBox="0 0 20 20" aria-hidden="true"><path d="M5 5l10 10M15 5L5 15" stroke="currentColor" stroke-width="1.9" stroke-linecap="round"/></svg>',
  trash: '<svg width="17" height="17" viewBox="0 0 20 20" aria-hidden="true"><path d="M4 6h12M8 6V4.5h4V6M5.5 6l.8 10h7.4l.8-10" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>',
};

const S = {
  ctx: null,              // the reader beside it: {item, kind, here(), view, shots(), time(), seek(t), resized()}
  shown: false, mode: 'side', el: null, frame: null, doc: null, page: null,
  tab: '', follow: true, here: null, tabs: [], vault: null, meta: {},
  pages: new Map(),       // item + "\n" + tab → its blocks and strokes, as loaded
  geo: new Map(),         // a stroke's id → {pts (page px), r, box, el}
  boxes: [],              // the blocks as laid out: {b, el, top, h, k, ox, oy}; the end: {end: true, top, h, k}
  layers: new Map(),      // a block's id → its strokes' layer (pens.js)
  done: [], undone: [], q: null, prev: null,
  editing: null, editEnd: 0, picked: null, rec: null, timeOn: store.get('time', true),
  reading: new Map(),     // a handwriting block's id → when to read it again
};
const key = tab => S.ctx ? S.ctx.item + '\n' + (tab == null ? S.tab : tab) : '';
const cur = () => S.pages.get(key()) || [];
const setCur = list => S.pages.set(key(), list);
const live = () => !!(S.shown && S.ctx && S.page && S.page.isConnected);
const dark = () => document.documentElement.dataset.mode === 'dark';
const blocksOf = ms => ms.filter(m => m.kind !== 'stroke').sort((a, b) => (a.ord || 0) - (b.ord || 0) || (a.id < b.id ? -1 : 1));
const strokesOf = (ms, id) => ms.filter(m => m.kind === 'stroke' && m.blk === id);
const byId = id => cur().find(m => m.id === id);

/* ---------- where it sits ---------- */
// Sideways (and wide enough): beside the reader on the right. Upright: a sheet below it, or above.
// (While typing, the keyboard's shorter window doesn't count: the tablet hasn't turned.)
const sideways = () => innerWidth > (S.editing && S.fullH && innerWidth === S.fullW ? Math.max(innerHeight, S.fullH) : innerHeight) && innerWidth >= 640;
function sizes(){
  if (sideways()) return { mode: 'side', w: Math.round(clamp(innerWidth * store.get('w', 0.4), 300, Math.max(300, innerWidth - 320))) };
  // the keyboard up while typing in it (the app's window shrinks): most of what's left
  const typing = S.editing && S.fullH && innerHeight < S.fullH * 0.8;
  const h = typing ? innerHeight - 110 : Math.round(clamp(innerHeight * store.get('h', 0.42), 170, Math.max(170, innerHeight - 180)));
  return { mode: store.get('top', false) ? 'top' : 'bottom', h };
}
function place(){
  const r = document.documentElement, z = sizes();
  S.mode = z.mode;
  if (!S.editing || innerWidth !== S.fullW) { S.fullH = innerHeight; S.fullW = innerWidth; }
  r.classList.toggle('skopen', S.shown);
  r.classList.toggle('skside', S.shown && z.mode === 'side');
  r.classList.toggle('skbottom', S.shown && z.mode === 'bottom');
  r.classList.toggle('sktop', S.shown && z.mode === 'top');
  r.style.setProperty('--skr', (S.shown && z.mode === 'side' ? z.w : 0) + 'px');
  r.style.setProperty('--skb', (S.shown && z.mode === 'bottom' ? z.h : 0) + 'px');
  r.style.setProperty('--skt', (S.shown && z.mode === 'top' ? z.h : 0) + 'px');
}
// What's left for the reader (for the readers that lay out by the window's size).
function room(){
  const cs = getComputedStyle(document.documentElement), px = n => parseFloat(cs.getPropertyValue(n)) || 0;
  const t = px('--skt'), b = px('--skb'), r = px('--skr');
  return { x: 0, y: t, w: innerWidth - r, h: innerHeight - t - b };
}
// The reader beside it lays out again once it has more or less room.
let relayT = 0;
function relayout(){
  clearTimeout(relayT);
  relayT = setTimeout(() => { window.dispatchEvent(new Event('resize')); if (S.ctx && S.ctx.resized) try { S.ctx.resized(); } catch(e){} }, 60);
}

/* ---------- the panel ---------- */
function build(){
  if (S.el) return;
  const el = S.el = document.createElement('aside');
  el.className = 'skb'; el.id = 'skb'; el.setAttribute('aria-label', 'Sketchbook'); el.hidden = true;
  el.innerHTML = '<div class="skgrip" role="separator" aria-label="Resize the Sketchbook"><i></i></div>' +
    '<div class="skhead"><div class="sktabs" role="tablist" aria-label="Pages"></div><div class="sktools"><span class="skpens"></span><span class="skown"></span></div></div>' +
    '<div class="skbody"><iframe class="skframe" title="Sketchbook page"></iframe></div>';
  document.body.appendChild(el);
  el.addEventListener('click', onHead);
  // the head's buttons leave the typing where it is (a tap there doesn't end it)
  el.addEventListener('mousedown', e => { if (e.target.closest('.skhead button')) e.preventDefault(); });
  grip(el.querySelector('.skgrip'));
  S.frame = el.querySelector('.skframe');
  frame();
}
// The page's own document: Daf's styles and the theme, the page, and the pens listening.
function frame(){
  const d = S.doc = S.frame.contentDocument;
  const links = [...document.querySelectorAll('link[rel="stylesheet"]')].map(l => '<link rel="stylesheet" href="' + esc(l.href) + '">').join('');
  d.open();
  d.write('<!doctype html><html class="skframe"><head><meta charset="utf-8">' + links + '</head><body class="skdoc"><div class="skpage"></div></body></html>');
  d.close();
  S.page = d.querySelector('.skpage');
  theme();
  Pens.listen(d, surface);
  d.addEventListener('click', onPage);
  d.addEventListener('pointerdown', e => {
    if (e.pointerType === 'pen') toSketch();
    if (S.picked && !e.target.closest('.skbar, .skb-picked')) unpick();
  }, true);
  d.addEventListener('pointermove', e => { if (e.pointerType === 'pen') toSketch(); }, true);
  d.addEventListener('keydown', e => {
    if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'z' && !e.target.closest('textarea')) { e.preventDefault(); e.shiftKey ? redo() : undo(); }
    else if (e.key === 'Escape' && S.picked) unpick();
  });
  new S.frame.contentWindow.ResizeObserver(() => later()).observe(d.documentElement);
}
function theme(){
  if (!S.doc) return;
  const a = document.documentElement, b = S.doc.documentElement;
  b.style.cssText = a.style.cssText;
  for (const k of ['mode', 'theme', 'font']) { if (a.dataset[k] != null) b.dataset[k] = a.dataset[k]; else delete b.dataset[k]; }
}
// The edge it's dragged by: its width beside the reader, or its height as a sheet (pulled down to
// nothing, it closes).
function grip(g){
  let drag = null;
  g.addEventListener('pointerdown', e => {
    e.preventDefault();
    drag = { id: e.pointerId, moved: false };
    try { g.setPointerCapture(e.pointerId); } catch(_){}
    document.documentElement.classList.add('skdrag');
  });
  g.addEventListener('pointermove', e => {
    if (!drag || e.pointerId !== drag.id) return;
    drag.moved = true;
    if (S.mode === 'side') store.set('w', clamp((innerWidth - e.clientX) / innerWidth, 0.2, 0.8));
    else {
      const h = S.mode === 'top' ? e.clientY : innerHeight - e.clientY;
      drag.gone = h < 110;
      store.set('h', clamp(h / innerHeight, 0.18, 0.85));
    }
    place();
  });
  const up = e => {
    if (!drag || e.pointerId !== drag.id) return;
    const d = drag; drag = null;
    document.documentElement.classList.remove('skdrag');
    if (d.gone) { store.set('h', 0.42); hide(); return; }
    if (d.moved) relayout();
  };
  g.addEventListener('pointerup', up);
  g.addEventListener('pointercancel', up);
}

/* ---------- the head: tabs and tools ---------- */
function tabList(){
  const ts = S.tabs.map(t => Object.assign({}, t));
  const add = t => { if (t && !ts.some(x => x.tab === t.tab)) ts.push(Object.assign({ n: 0 }, t)); };
  add({ tab: '', title: 'General' });
  add(S.here);
  add(S.tab ? { tab: S.tab, title: S.meta.title, pos: S.meta.pos } : null);
  return ts.sort((a, b) => (a.tab !== '') - (b.tab !== '') || (a.pos != null ? a.pos : 2) - (b.pos != null ? b.pos : 2));
}
function drawTabs(){
  if (!S.el || !S.ctx) return;
  const box = S.el.querySelector('.sktabs'), many = S.ctx.kind === 'book' || S.ctx.kind === 'manga';
  box.hidden = !many;
  if (!many) return;
  box.innerHTML = tabList().map(t => '<button role="tab" class="sktab' + (S.here && t.tab === S.here.tab ? ' here' : '') + '" data-sktab="' + esc(t.tab) + '" aria-selected="' + (t.tab === S.tab) + '"' +
    (t.tab && /[֐-׿]/.test(t.title || '') ? ' dir="rtl"' : '') + '>' + esc(t.tab ? (t.title || 'Chapter') : 'General') + '</button>').join('');
  const on = box.querySelector('[aria-selected="true"]');
  if (on) on.scrollIntoView({ block: 'nearest', inline: 'nearest' });
}
const canRecord = () => !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia && window.MediaRecorder);
function drawTools(){
  if (!S.el || !S.ctx) return;
  const ctx = S.ctx, mine = !Pens.seen();         // no pen on this device: no pens' tools, so Undo and Redo are here
  const b = (k, label, icon, on, dis, cls) => '<button class="ib' + (cls ? ' ' + cls : '') + '" data-sk="' + k + '" title="' + label + '" aria-label="' + label + '"' +
    (on != null ? ' aria-pressed="' + !!on + '"' : '') + (dis ? ' disabled' : '') + '>' + icon + '</button>';
  const rec = S.rec ? '<span class="skrec">' + stampOf((Date.now() - S.rec.at) / 1000) + '</span>' : '';
  S.el.querySelector('.skown').innerHTML = b('text', 'Type', IC.text) +
    (canRecord() ? b('mic', S.rec ? 'Stop' : S.hearing ? 'Writing it down' : 'Dictate', (S.rec ? IC.stop : IC.mic) + rec, !!S.rec, S.hearing, S.rec ? 'skon' : S.hearing ? 'skbusy' : '') : '') +
    (ctx.shots ? b('shot', 'Take the page', IC.shot) : '') + (ctx.time ? b('time', 'Time', IC.time, S.timeOn) : '') +
    (mine ? b('undo', 'Undo', IC.undo, null, !S.done.length) + b('redo', 'Redo', IC.redo, null, !S.undone.length) : '') +
    '<span class="spacer"></span>' + (S.mode !== 'side' ? b('flip', S.mode === 'top' ? 'Move to the bottom' : 'Move to the top', S.mode === 'top' ? IC.toBottom : IC.toTop) : '') +
    b('close', 'Close the Sketchbook', IC.close);
}
function onHead(e){
  const t = e.target.closest('[data-sktab], [data-sk]'); if (!t) return;
  if (t.dataset.sktab != null) { const tab = t.dataset.sktab, x = tabList().find(y => y.tab === tab); S.follow = !!(S.here && tab === S.here.tab); show1(tab, x); return; }
  const k = t.dataset.sk;
  if (k === 'close') hide();
  else if (k === 'text') typeAt(null);
  else if (k === 'mic') dictate();
  else if (k === 'shot') shoot();
  else if (k === 'time') { S.timeOn = !S.timeOn; store.set('time', S.timeOn); drawTools(); }
  else if (k === 'undo') undo();
  else if (k === 'redo') redo();
  else if (k === 'flip') { store.set('top', S.mode !== 'top'); place(); drawTools(); relayout(); }
}

/* ---------- a tab's page ---------- */
async function show1(tab, meta){
  flush(); stopEditing(); unpick(); readNow();
  S.tab = tab; S.meta = meta || {}; S.done = []; S.undone = [];
  drawTabs(); drawTools(); Pens.redraw();
  if (S.doc) S.doc.scrollingElement.scrollTop = 0;
  if (!S.pages.has(key())) { setCur([]); render(); await load(tab); }
  else { render(); load(tab); }
}
// What's on a tab: the server's, with what waits in the outbox and what's queued here on top.
async function load(tab){
  const ctx = S.ctx; if (!ctx) return;
  const item = ctx.item, k = key(tab);
  let r = null;
  try { r = await api('/api/sketchbook/' + encodeURIComponent(item) + '?tab=' + encodeURIComponent(tab)); } catch(e){}
  if (S.ctx !== ctx) return;
  if (r) { S.tabs = r.tabs || []; S.vault = r.vault; }
  let list = r ? r.marks : (S.pages.get(k) || []);
  const on = (rm, add) => {
    const gone = new Set(rm); list = list.filter(m => !gone.has(m.id) && !(m.kind === 'stroke' && gone.has(m.blk)));
    for (const m of add) { list = list.filter(y => y.id !== m.id); list.push(m); }
  };
  const path = '/api/sketchbook/' + encodeURIComponent(item);
  for (const x of C.outbox.get()) if (x.path === path && x.body && (x.body.tab || '') === tab) on(x.body.remove || [], x.body.add || []);
  if (S.q && S.q.k === k) on([...S.q.remove], [...S.q.add.values()]);
  // a picture just taken keeps its own copy until the server has it
  const had = new Map((S.pages.get(k) || []).filter(m => m.src).map(m => [m.id, m.src]));
  list.forEach(m => { if (had.has(m.id) && !m.src) m.src = had.get(m.id); });
  S.pages.set(k, list);
  if (tab === S.tab && !S.editing) render();
  drawTabs();
}

/* ---------- drawing the page ---------- */
let laterT = 0;
const later = () => { cancelAnimationFrame(laterT); laterT = requestAnimationFrame(render); };
const picSrc = m => m.src || '/api/sketchbook/img/' + encodeURIComponent(m.file);
const stampHTML = m => m.t != null ? '<button class="skts" data-t="' + m.t + '" dir="ltr">' + stampOf(m.t) + '</button>' : '';
// How a block's units sit on the page: px = (unit − o) × k, from its top left.
function frameOf(b, W, strokes){
  if (b.kind === 'ink' && b.type === 'drawing') {
    let vb = b.vb;
    if (!vb) {
      let x1 = Infinity, y1 = Infinity, x2 = -Infinity, y2 = -Infinity;
      for (const s of strokes) for (const p of s.pts) { x1 = Math.min(x1, p[0]); y1 = Math.min(y1, p[1]); x2 = Math.max(x2, p[0]); y2 = Math.max(y2, p[1]); }
      vb = x1 < Infinity ? [x1 - 16, y1 - 16, x2 - x1 + 32, y2 - y1 + 32] : [0, 0, INK_W, INK_W / 2];
    }
    const k = W / vb[2];
    return { k, ox: vb[0], oy: vb[1], h: vb[3] * k };
  }
  const k = W / INK_W;
  if (b.kind === 'image') return { k, ox: 0, oy: 0, h: (b.h || INK_W) * k };
  let low = 0;
  for (const s of strokes) for (const p of s.pts) low = Math.max(low, p[1] + (s.size || 6) / 2);
  return { k, ox: 0, oy: 0, h: Math.max(3, Math.ceil(low / LINE) + 1) * LINE * k };      // whole lines, one to spare
}
// The page is one size on this screen, as paper is: as wide as the panel first opens beside a book
// (four tenths of the screen's long side), the same upright and sideways. A wider panel leaves room
// around it and the lines stay as they are; only a panel too narrow for it shows it smaller.
// A phone's page is its whole width.
function pageW(room){
  const w = S.fullW || innerWidth, h = S.fullH || innerHeight;
  if (Math.min(w, h) < 600) return room;                 // a phone: all of its width
  return Math.min(room, Math.round(clamp(Math.max(w, h) * 0.4, 300, 720)) - 20);
}
function render(){
  if (!S.page || !S.shown) return;
  const room = S.doc.documentElement.clientWidth - 20; if (room < 50) return;
  const W = pageW(room);
  const ms = cur(), bl = blocksOf(ms), last = bl[bl.length - 1];
  S.W = W; S.page.style.width = W + 'px';
  S.page.classList.toggle('sheet', W < room - 24);
  S.page.style.setProperty('--skl', r2(LINE * W / INK_W) + 'px');
  let h = '';
  const fr = new Map(), ed = S.editing, slot = '<div class="skslot"></div>';
  let slotted = !ed;
  for (const b of bl) {
    if (!slotted && (ed.m.id === b.id || (ed.fresh && (ed.m.ord || 0) < (b.ord || 0)))) { h += slot; slotted = true; if (ed.m.id === b.id) continue; }
    const st = strokesOf(ms, b.id), f = frameOf(b, W, st);
    if (b.kind === 'ink' && b.type === 'writing' && b === last) f.h += LINE * f.k;     // the last one has room to go on
    fr.set(b.id, f);
    if (b.kind === 'text') h += '<div class="skblk sktext' + (b.text ? '' : ' stamp') + '" data-id="' + b.id + '" dir="auto">' + stampHTML(b) + esc(b.text || '') + '</div>';
    else if (b.kind === 'image') h += '<div class="skblk skpic" data-id="' + b.id + '" style="height:' + r1(f.h) + 'px"><img alt="' + esc(b.cap || '') + '" draggable="false" src="' + esc(picSrc(b)) + '">' + (b.cap ? '<span class="skcap">' + esc(b.cap) + '</span>' : '') + '</div>';
    else h += '<div class="skblk skink ' + (b.type === 'drawing' ? 'skdraw' : 'skwrite') + '" data-id="' + b.id + '" style="height:' + r1(f.h) + 'px">' + stampHTML(b) + '</div>';
  }
  // under everything: ruled paper, where writing starts a new handwriting block and a tap types
  if (!slotted) h += slot;
  const lh = LINE * W / INK_W, lines = Math.max(last && last.kind === 'ink' && last.type === 'writing' ? 1 : 3, Math.ceil((S.frame.clientHeight || 0) * 0.35 / lh));
  h += '<div class="skblk skend" style="height:' + r2(lines * lh) + 'px"></div>';
  if (ed && ed.ta.parentNode === S.page) {
    // the text being typed stays put while the rest is laid out around it (taken out of the page,
    // it would lose the keyboard, which is what laying out again when the keyboard comes up did)
    const t = S.doc.createElement('template'); t.innerHTML = h;
    for (const n of [...S.page.childNodes]) if (n !== ed.ta && n !== ed.bar) n.remove();
    const nodes = [...t.content.childNodes], at = nodes.findIndex(n => n.classList && n.classList.contains('skslot'));
    const tail = ed.bar.parentNode === S.page ? ed.bar : null;
    nodes.forEach((n, i) => { if (i < at) S.page.insertBefore(n, ed.ta); else if (i > at) S.page.insertBefore(n, tail); });
    S.page.appendChild(ed.bar);
  } else {
    S.page.innerHTML = h;
    const sl = S.page.querySelector('.skslot');
    if (ed) { sl.replaceWith(ed.ta); S.page.appendChild(ed.bar); } else if (sl) sl.remove();
  }
  // the ruled paper goes down to the bottom of the panel
  const endEl = S.page.lastElementChild && S.page.lastElementChild.classList.contains('skend') ? S.page.lastElementChild : S.page.querySelector('.skend');
  const gap = (S.frame.clientHeight || 0) - 50 - S.page.offsetHeight;
  if (endEl && gap >= lh) endEl.style.height = r2((lines + Math.floor(gap / lh)) * lh) + 'px';
  S.boxes = []; S.geo.clear(); S.layers.clear();
  for (const el of S.page.children) {
    if (!el.classList.contains('skblk')) continue;
    const top = el.offsetTop, bh = el.offsetHeight;
    if (el.classList.contains('skend')) { S.boxes.push({ end: true, el, top, h: bh, k: W / INK_W, ox: 0, oy: 0 }); continue; }
    const b = bl.find(x => x.id === el.dataset.id), f = fr.get(b.id);
    const box = { b, el, top, h: bh, k: f.k, ox: f.ox, oy: f.oy };
    S.boxes.push(box);
    if (b.kind === 'text') continue;
    const svg = S.doc.createElementNS(NS, 'svg');
    svg.setAttribute('class', 'skinkl'); svg.setAttribute('aria-hidden', 'true'); svg.setAttribute('width', W); svg.setAttribute('height', r1(bh));
    el.appendChild(svg);
    // on a picture the ink is dark and the highlighter darkens, as on paper, whatever the theme
    const onPic = b.kind === 'image', layer = Pens.layer(svg, dark() && !onPic);
    layer.hl.style.mixBlendMode = dark() && !onPic ? 'screen' : 'multiply';
    layer.onPic = onPic;
    S.layers.set(b.id, { layer, box });
    for (const s of strokesOf(ms, b.id)) { try { draw(s, box, layer); } catch(e){} }
  }
  if (S.editing) placeEdit();
  if (S.picked) drawPicked();
}
// The blocks moved (the text being typed grew): where they are now, and their strokes with them.
function measure(){
  for (const box of S.boxes) {
    const top = box.el.offsetTop, d = top - box.top; if (!d) continue;
    box.top = top;
    if (box.b) for (const [, g] of S.geo) if (g.blk === box.b.id) { g.pts.forEach(p => { p[1] += d; }); g.box[1] += d; g.box[3] += d; }
  }
}
const asPen = (m, onPic) => ({ id: m.id, v: 2, tool: m.tool, color: onPic && m.color === 'ink' ? '#1e1e1e' : m.color, size: m.size, o: m.o });
function draw(s, box, layer){
  if (!box) { const l = S.layers.get(s.blk); if (!l) return; box = l.box; layer = l.layer; }
  const k = box.k, local = s.pts.map(p => [(p[0] - box.ox) * k, (p[1] - box.oy) * k, p[2]]);
  const el = layer.add(asPen(s, layer.onPic), local, k);
  let x1 = Infinity, y1 = Infinity, x2 = -Infinity, y2 = -Infinity;
  const pts = local.map(p => [p[0], p[1] + box.top, p[2]]);
  for (const p of pts) { if (p[0] < x1) x1 = p[0]; if (p[0] > x2) x2 = p[0]; if (p[1] < y1) y1 = p[1]; if (p[1] > y2) y2 = p[1]; }
  S.geo.set(s.id, { pts, local, r: (s.size || 6) * k / 2, box: [x1, y1, x2, y2], el, blk: s.blk });
}
function unpaint(id){ const g = S.geo.get(id); S.geo.delete(id); if (g && g.el) g.el.remove(); }

/* ---------- the page as the pens' surface ---------- */
const frameOff = () => { const r = S.frame.getBoundingClientRect(); return [r.left, r.top]; };
// A point in the window → on the page (px from its top left).
function onPageAt(x, y){ const [fx, fy] = frameOff(), p = S.page.getBoundingClientRect(); return [x - fx - p.left, y - fy - p.top]; }
// The block a point on the page is in (or the paper under everything).
function boxAt(py){ return S.boxes.find(b => py >= b.top && py < b.top + b.h) || (py >= 0 && S.boxes[S.boxes.length - 1]) || null; }
function near(pts, x, y, r){
  for (let i = 0; i < pts.length; i++) {
    const a = pts[i], b = pts[i + 1] || a, dx = b[0] - a[0], dy = b[1] - a[1], l = dx * dx + dy * dy;
    const t = l ? Math.max(0, Math.min(1, ((x - a[0]) * dx + (y - a[1]) * dy) / l)) : 0;
    if (Math.hypot(x - a[0] - t * dx, y - a[1] - t * dy) <= r) return true;
  }
  return false;
}
function inside(poly, x, y){
  let c = false;
  for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
    const a = poly[i], b = poly[j];
    if ((a[1] > y) !== (b[1] > y) && x < (b[0] - a[0]) * (y - a[1]) / (b[1] - a[1]) + a[0]) c = !c;
  }
  return c;
}
const lastOrd = () => { const bl = blocksOf(cur()); return bl.length ? (bl[bl.length - 1].ord || 0) : 0; };
function ordAfter(b){
  const bl = blocksOf(cur()), i = bl.findIndex(x => x.id === b.id), next = bl[i + 1];
  return next ? ((b.ord || 0) + (next.ord || 0)) / 2 : (b.ord || 0) + 1;
}
function timeNow(){
  const ctx = S.ctx; if (!S.timeOn || !ctx || !ctx.time) return null;
  let t = 0; try { t = ctx.time() || 0; } catch(e){}
  return t > 0 ? r1(t) : null;
}
// Points on the page (px) into a block's units: the block the first one is in, or a new handwriting
// block under everything. Returns [the block (new: not on the page yet), points].
function intoBlock(pts){
  const box = boxAt(pts[0][1]); if (!box) return null;
  let b = box.b, fresh = null;
  if (box.end) {
    const bl = blocksOf(cur()), last = bl[bl.length - 1];
    if (last && last.kind === 'ink' && last.type === 'writing') b = last;
    else {
      fresh = b = { id: newId('b'), kind: 'ink', type: 'writing', ord: lastOrd() + 1 };
      const t = timeNow(); if (t != null) b.t = t;
    }
  }
  if (b.kind === 'text') return null;
  const at = fresh ? { top: box.top, k: box.k, ox: 0, oy: 0 } : (S.boxes.find(x => x.b && x.b.id === b.id) || box);
  return [b, fresh, pts.map(p => [r1((p[0]) / at.k + at.ox), r1((p[1] - at.top) / at.k + at.oy), r2(p[2])]), at.k];
}
function strokeFrom(L){
  const b = L.brush, here = L.pts.map(p => { const q = onPageAt(p[0], p[1]); return [q[0], q[1], p[2]]; });
  const got = intoBlock(here); if (!got) return null;
  const [blk, fresh, pts, k] = got;
  const s = { id: newId('k'), kind: 'stroke', blk: blk.id, tool: b.pen, color: b.color, size: r1(b.w / k), o: r2(b.opacity), pts };
  if (L.snapped) s.sh = 1;
  return { s, fresh };
}
function addStroke(s, fresh){
  setCur(cur().concat(fresh ? [fresh, s] : [s]));
  if (fresh) { render(); act({ add: [fresh, s] }); }
  else {
    const b = byId(s.blk), l = S.layers.get(s.blk), bl = blocksOf(cur());
    const need = b && b.kind === 'ink' && b.type === 'writing' ? frameOf(b, S.W, strokesOf(cur(), s.blk)).h + (bl[bl.length - 1] === b ? LINE * S.W / INK_W : 0) : 0;
    if (!l || need > l.box.h + 1) render(); else draw(s);
    act({ add: [s] });
  }
  readSoon(s.blk);
}
const surface = {
  live,
  takes: (el, doc) => doc === S.doc && !!el.closest && !el.closest('.skbar, .sktext, textarea'),
  off: () => frameOff(),
  stroke(L){
    if (!L.pts.length || !L.brush) return;
    const got = strokeFrom(L); if (got) addStroke(got.s, got.fresh);
  },
  erase(x, y, mode, r, L){
    const [px, py] = onPageAt(x, y);
    for (const [id, g] of [...S.geo]) {
      const b = g.box, m = r + g.r;
      if (px < b[0] - m || px > b[2] + m || py < b[1] - m || py > b[3] + m || !near(g.pts, px, py, m)) continue;
      const s = byId(id); if (!s) continue;
      setCur(cur().filter(t => t !== s)); unpaint(id);
      const mine = L.added.indexOf(s);
      if (mine >= 0) L.added.splice(mine, 1); else L.erased.push(s);
      if (mode !== 'area') continue;
      let run = [];
      const cut = () => { if (run.length >= 2) { const piece = Object.assign({}, s, { id: newId('k'), pts: run }); setCur(cur().concat(piece)); L.added.push(piece); draw(piece); } run = []; };
      g.pts.forEach((q, i) => { if (Math.hypot(q[0] - px, q[1] - py) <= m) cut(); else run.push(s.pts[i]); });
      cut();
    }
  },
  erased(L){
    if (!L.erased.length && !L.added.length) return;
    // a handwriting block with nothing left on it goes too
    const ms = cur(), emptied = [...new Set(L.erased.map(s => s.blk))].map(byId).filter(b => b && b.kind === 'ink' && !strokesOf(ms, b.id).length);
    if (emptied.length) setCur(ms.filter(m => !emptied.includes(m)));
    act({ del: L.erased.concat(emptied), add: L.added });
    render();
    [...new Set(L.erased.concat(L.added).map(s => s.blk))].forEach(readSoon);
  },
  eraseAll(){
    const ms = cur(), gone = ms.filter(m => m.kind === 'stroke' || (m.kind === 'ink'));
    if (!gone.length) return;
    setCur(ms.filter(m => !gone.includes(m))); render(); act({ del: gone });
    toast('Everything written on this page is erased. Undo brings it back.');
  },
  highlight: () => false,
  palHost: () => S.el.querySelector('.skpens'),
  canUndo: () => S.done.length > 0, canRedo: () => S.undone.length > 0, undo: () => undo(), redo: () => redo(),
  extras: () => [], extra(){},
  select(loop){
    const poly = loop.map(q => onPageAt(q[0], q[1]));
    return cur().filter(m => { const g = m.kind === 'stroke' && S.geo.get(m.id); return g && g.pts.filter(q => inside(poly, q[0], q[1])).length >= g.pts.length * 0.6; });
  },
  mark(list, on){ for (const s of list) { const g = S.geo.get(s.id); if (g && g.el) g.el.classList.toggle('held', !!on); } },
  // handwriting read as text: typed text where it was (its block, if nothing's left on it; else under it)
  typed(list, text){ replaceWithText(list, text, true); },
  // a note on it: the text under its block, the handwriting staying
  noteOnPassage(list, text){ replaceWithText(list, text, false); },
  remove(list){
    const ids = new Set(list.map(s => s.id)), ms = cur().filter(m => !ids.has(m.id));
    const emptied = [...new Set(list.map(s => s.blk))].map(byId).filter(b => b && b.kind === 'ink' && !strokesOf(ms, b.id).length);
    setCur(ms.filter(m => !emptied.includes(m))); render(); act({ del: list.concat(emptied) });
  },
  all: () => cur().filter(m => m.kind === 'stroke' && Pens.writingOf(asPen(m)) && !m.sh && S.geo.has(m.id)),
  inkOf: list => list.map(s => (S.geo.get(s.id) || {}).pts).filter(Boolean),
};
function replaceWithText(list, text, instead){
  const blk = byId(list[0] && list[0].blk); if (!blk) return;
  const ids = new Set(list.map(s => s.id));
  let ms = cur(), del = [];
  if (instead) { ms = ms.filter(m => !ids.has(m.id)); del = list.slice(); }
  const left = strokesOf(ms, blk.id).length, t = { id: newId('t'), kind: 'text', text, ord: ordAfter(blk) };
  if (instead && !left && blk.kind === 'ink') { t.ord = blk.ord; if (blk.t != null) t.t = blk.t; ms = ms.filter(m => m !== blk); del.push(blk); }
  setCur(ms.concat(t)); render(); act({ add: [t], del });
}
// The pens' tools follow the pen: over the page, the Sketchbook's; over the reader, the reader's.
function toSketch(){ const s = Pens.surface(); if (s === surface || !live()) return; if (s) S.prev = s; Pens.use(surface); drawTools(); }
function toReader(e){
  if (e.pointerType !== 'pen' || !S.shown || Pens.surface() !== surface) return;
  const t = e.target;
  if (t && t.closest && t.closest('#skb, .inkpop, .inkpal, .penround, .penheld, .readout, .skshot')) return;
  if (S.prev && S.prev.live && S.prev.live()) { Pens.use(S.prev); drawTools(); }
}
function watchDoc(doc){
  if (!doc || doc.__dafSketch) return;
  doc.__dafSketch = true;
  doc.addEventListener('pointerdown', toReader, true);
  doc.addEventListener('pointermove', toReader, true);
}
watchDoc(document);

/* ---------- handwriting read as text ---------- */
// A moment after the pen rests on a handwriting block, pens.js's reader reads it (English with Grape
// on any device, Hebrew in the Android app), for the vault's search and the Kindle. Not undone with
// the strokes: it only follows them.
function readSoon(id){
  const b = byId(id); if (!b || b.kind !== 'ink' || b.type !== 'writing') return;
  S.reading.set(id, S.ctx.item + '\n' + S.tab);
  clearTimeout(S.readT); S.readT = setTimeout(readNow, 2500);
}
async function readNow(){
  clearTimeout(S.readT);
  const todo = [...S.reading]; S.reading.clear();
  for (const [id, k] of todo) {
    const list = S.pages.get(k) || [], b = list.find(m => m.id === id); if (!b) continue;
    const st = strokesOf(list, id).filter(s => Pens.writingOf(asPen(s)) && !s.sh);
    let text = '';
    if (st.length) {
      let lang = 'en'; try { lang = JSON.parse(localStorage.getItem('daf.pens.readLang') || '"en"'); } catch(e){}
      if (!Pens.languages().includes(lang)) lang = 'en';
      const k = (S.W || 400) / INK_W;
      try { text = (await Pens.readInk(st.map(s => s.pts.map(p => [p[0] * k, p[1] * k, p[2]])), lang)).join('\n').trim(); } catch(e){ continue; }
    }
    if ((b.transcript || '') === text) continue;
    const n = Object.assign({}, b); if (text) n.transcript = text; else delete n.transcript;
    S.pages.set(k, (S.pages.get(k) || []).map(m => m.id === id ? n : m));
    sendTo(k, [n], []);
  }
}

/* ---------- undo, and sending ---------- */
function act(a){ S.done.push(a); if (S.done.length > 200) S.done.shift(); S.undone = []; apply(a, false); }
// Does what a records (back = false) or takes it back (true). The page shows it already the first time.
function apply(a, back, again){
  const add = (back ? a.del : a.add) || [], rm = (back ? a.add : a.del) || [];
  if (back || again) {
    const ids = new Set(rm.map(m => m.id));
    let list = cur().filter(m => !ids.has(m.id));
    for (const m of add) { list = list.filter(y => y.id !== m.id); list.push(m); }
    setCur(list); render();
    [...new Set(add.concat(rm).map(m => m.kind === 'stroke' ? m.blk : m.id))].forEach(readSoon);
  }
  sendTo(key(), add, rm.map(m => m.id));
  Pens.redraw(); drawTools();
}
function undo(){ stopEditing(); const a = S.done.pop(); if (!a) return; S.undone.push(a); apply(a, true); }
function redo(){ stopEditing(); const a = S.undone.pop(); if (!a) return; S.done.push(a); apply(a, false, true); }
// A tab's changes in one request, a moment after the last; taken away first, so an edit undone
// ends as it was.
function sendTo(k, add, rm){
  if (!S.ctx || (!add.length && !rm.length)) return;
  const [item, tab] = k.split('\n');
  if (S.q && S.q.k !== k) flush();
  const meta = tab === S.tab ? S.meta : (tabList().find(t => t.tab === tab) || {});
  if (!S.q) S.q = { k, item, tab, title: tab ? (meta.title || null) : null, pos: tab ? meta.pos : null, add: new Map(), remove: new Set() };
  for (const id of rm) { S.q.add.delete(id); S.q.remove.add(id); }
  for (const m of add) { S.q.remove.delete(m.id); S.q.add.set(m.id, m); }
  clearTimeout(S.qT); S.qT = setTimeout(flush, 1200);
}
const sent = m => { const o = Object.assign({}, m); delete o.updated; if (o.file) delete o.src; return o; };
async function flush(){
  clearTimeout(S.qT);
  const q = S.q; S.q = null;
  if (!q || (!q.add.size && !q.remove.size)) return;
  const body = { tab: q.tab, title: q.title, pos: q.pos != null ? q.pos : undefined, add: [...q.add.values()].map(sent), remove: [...q.remove], at: Math.floor(Date.now() / 1000) };
  try {
    const r = await api('/api/sketchbook/' + encodeURIComponent(q.item), { method: 'POST', body: JSON.stringify(body) });
    // a picture sent as itself is kept by the server under a name: the page asks for it by that from now on
    if (r && r.files) for (const [id, file] of Object.entries(r.files)) for (const list of S.pages.values()) { const m = list.find(x => x.id === id); if (m) { m.file = file; } }
    if (S.ctx && S.ctx.item === q.item) {
      const has = blocksOf(S.pages.get(q.k) || []).length, i = S.tabs.findIndex(t => t.tab === q.tab);
      if (has && i < 0) S.tabs.push({ tab: q.tab, title: q.title, pos: q.pos, n: has });
      else if (!has && i >= 0 && q.tab) S.tabs.splice(i, 1);
      drawTabs();
    }
  } catch(e){ toast(e.message); }
}

/* ---------- typing ---------- */
function onPage(e){
  const t = e.target;
  const st = t.closest('.skts');
  if (st) { e.preventDefault(); if (S.ctx && S.ctx.seek) S.ctx.seek(+st.dataset.t); return; }
  if (t.closest('.skbar, textarea')) return;
  const el = t.closest('.skblk'), b = el && el.dataset.id ? byId(el.dataset.id) : null;
  if (!e.isTrusted) {                       // the pen's tap (pens.js): typed text to type in; anywhere else a dot
    if (b && b.kind === 'text') edit(b, e); else dot(e.clientX, e.clientY);
    return;
  }
  if (Date.now() - S.editEnd < 350) return;  // the tap that ends typing only ends it
  if (b && b.kind === 'text') { edit(b, e); return; }
  if (b) { if (S.picked === b.id) unpick(); else pick(b.id); return; }
  if (S.picked) { unpick(); return; }
  typeAt(null);                             // under everything: a new text there
}
function dot(cx, cy){
  const b = Pens.brush(); if (!b || !Pens.on()) return;
  const p = S.page.getBoundingClientRect(), x = cx - p.left, y = cy - p.top;
  const got = intoBlock([[x, y, 0.5], [x + 0.3, y, 0.5]]); if (!got) return;
  const [blk, fresh, pts, k] = got;
  addStroke({ id: newId('k'), kind: 'stroke', blk: blk.id, tool: b.pen, color: b.color, size: r1(b.w / k), o: r2(b.opacity), pts }, fresh);
}
// A new text: under a block (after), or at the end of the page.
function typeAt(after, words){
  if (S.editing && !after) { if (words) { putText(words); return; } S.editing.ta.focus(); return; }
  stopEditing(); unpick();
  const m = { id: newId('t'), kind: 'text', text: words || '', ord: after ? ordAfter(after) : lastOrd() + 1 };
  const t = timeNow(); if (t != null) m.t = t;
  edit(m, null, true);
}
function placeEdit(){
  const ed = S.editing; if (!ed) return;
  ed.ta.style.height = 'auto'; ed.ta.style.height = ed.ta.scrollHeight + 'px';
  ed.bar.style.top = r1(Math.max(0, ed.ta.offsetTop - 40)) + 'px';
  measure();
}
// Typing in a text (fresh: one not on the page yet). A bar above it moves it, or deletes it.
function edit(m, ev, fresh){
  if (!m || !S.doc) return;
  stopEditing(); unpick();
  const d = S.doc, ta = d.createElement('textarea'), bar = d.createElement('div');
  ta.className = 'skedit'; ta.dir = 'auto'; ta.value = m.text || ''; ta.spellcheck = true; ta.setAttribute('aria-label', 'Typed text');
  bar.className = 'skbar'; bar.innerHTML = barHTML(false);
  S.editing = { m, ta, bar, fresh: !!fresh };
  render();
  ta.focus({ preventScroll: true });
  ta.scrollIntoView({ block: 'nearest' });
  const at = ev && caretIn(ev, m);
  ta.setSelectionRange(at != null ? at : ta.value.length, at != null ? at : ta.value.length);
  ta.addEventListener('input', placeEdit);
  ta.addEventListener('blur', () => setTimeout(() => { if (S.editing && S.editing.ta === ta && S.doc.activeElement !== ta) stopEditing(); }, 0));
  ta.addEventListener('keydown', e => { if (e.key === 'Escape') { e.preventDefault(); stopEditing(); } });
  bar.addEventListener('pointerdown', e => e.preventDefault());
  bar.addEventListener('click', e => { const k = e.target.closest('[data-skb]'); if (k) barAct(k.dataset.skb, m.id); });
  if (S.mode !== 'side' && S.fullH) setTimeout(place, 350);     // the keyboard came up: more of the sheet
}
const barHTML = typed => '<button data-skb="up" aria-label="Move up" title="Move up">' + IC.up + '</button><button data-skb="down" aria-label="Move down" title="Move down">' + IC.down + '</button>' +
  (typed ? '<button data-skb="below" aria-label="Type below" title="Type below">' + IC.textBelow + '</button>' : '') + '<button data-skb="del" aria-label="Delete" title="Delete">' + IC.trash + '</button>';
// Where in the text a tap landed (from the text shown under it).
function caretIn(ev, m){
  try {
    const r = S.doc.caretRangeFromPoint ? S.doc.caretRangeFromPoint(ev.clientX, ev.clientY) : null;
    if (!r) return null;
    const el = r.startContainer.parentElement && r.startContainer.parentElement.closest('.sktext'); if (!el) return null;
    const pre = S.doc.createRange(); pre.selectNodeContents(el); pre.setEnd(r.startContainer, r.startOffset);
    const st = el.querySelector('.skts');
    return Math.max(0, Math.min((m.text || '').length, pre.toString().length - (st ? st.textContent.length : 0)));
  } catch(e){ return null; }
}
function stopEditing(){
  const ed = S.editing; if (!ed) return;
  S.editing = null; S.editEnd = Date.now();
  const text = ed.ta.value.replace(/\s+$/, ''), m = ed.m;
  ed.ta.remove(); ed.bar.remove();
  const old = byId(m.id), keep = text || m.t != null;
  if (!old) { if (keep) { const n = Object.assign({}, m, { text }); setCur(cur().concat(n)); render(); act({ add: [n] }); } else render(); }
  else if (!keep) { setCur(cur().filter(x => x.id !== m.id)); render(); act({ del: [old] }); }
  else if (text !== (old.text || '')) { const n = Object.assign({}, old, { text }); setCur(cur().map(x => x.id === m.id ? n : x)); render(); act({ add: [n], del: [old] }); }
  else render();
  if (S.mode !== 'side') setTimeout(place, 350);
}
// Words from elsewhere (dictation): into the text being typed, where its caret is, or a new text at the end.
function putText(words, into){
  const ed = S.editing;
  if (ed && (!into || into.id === ed.m.id)) {
    const ta = ed.ta, at = into && into.at != null ? into.at : ta.selectionStart, v = ta.value;
    const before = v.slice(0, at), after = v.slice(at), sep = before && !/\s$/.test(before) ? ' ' : '';
    ta.value = before + sep + words + (after && !/^\s/.test(after) ? ' ' : '') + after;
    const c = (before + sep + words).length; ta.setSelectionRange(c, c);
    ta.dispatchEvent(new Event('input')); ta.focus();
    return;
  }
  typeAt(null, words);
}

/* ---------- a block's bar: move it, type under it, delete it ---------- */
function pick(id){ stopEditing(); S.picked = id; drawPicked(); }
function unpick(){ S.picked = null; if (!S.page) return; S.page.querySelectorAll('.skbar.picked').forEach(x => x.remove()); S.page.querySelectorAll('.skb-picked').forEach(x => x.classList.remove('skb-picked')); }
function drawPicked(){
  const box = S.boxes.find(x => x.b && x.b.id === S.picked);
  S.page.querySelectorAll('.skbar.picked').forEach(x => x.remove());
  if (!box) { S.picked = null; return; }
  box.el.classList.add('skb-picked');
  const bar = S.doc.createElement('div'); bar.className = 'skbar picked'; bar.innerHTML = barHTML(true);
  bar.style.top = r1(Math.max(0, box.top + 4)) + 'px';
  bar.addEventListener('click', e => { const k = e.target.closest('[data-skb]'); if (k) barAct(k.dataset.skb, box.b.id); });
  S.page.appendChild(bar);
}
function barAct(k, id){
  const ed = S.editing && S.editing.m.id === id ? S.editing : null;
  if (ed) { const text = ed.ta.value; stopEditing(); if (!byId(id)) return; if (k === 'del' && text) { /* emptied below */ } }
  const b = byId(id); if (!b) { unpick(); return; }
  if (k === 'below') { unpick(); typeAt(b); return; }
  if (k === 'del') {
    unpick();
    const gone = [b].concat(strokesOf(cur(), b.id));
    setCur(cur().filter(m => !gone.includes(m))); render(); act({ del: gone });
    return;
  }
  const bl = blocksOf(cur()), i = bl.indexOf(b), j = k === 'up' ? i - 1 : i + 1, o = bl[j];
  if (!o) return;
  const nb = Object.assign({}, b, { ord: o.ord }), no = Object.assign({}, o, { ord: b.ord });
  if (nb.ord === no.ord) { nb.ord = k === 'up' ? o.ord - 0.5 : o.ord + 0.5; }
  setCur(cur().map(m => m.id === b.id ? nb : m.id === o.id ? no : m)); render(); act({ add: [nb, no], del: [b, o] });
  if (b.kind !== 'text') pick(b.id);
  const box = S.boxes.find(x => x.b && x.b.id === b.id); if (box) box.el.scrollIntoView({ block: 'nearest' });
}

/* ---------- dictation ---------- */
async function dictate(){
  if (S.rec) { S.rec.r.stop(); return; }
  if (S.hearing) return;
  const ed = S.editing, into = ed ? { id: ed.m.id, at: ed.ta.selectionStart } : null;
  let stream;
  try { stream = await navigator.mediaDevices.getUserMedia({ audio: true }); }
  catch(e){ toast('Daf can’t use the microphone here' + (e && e.name === 'NotAllowedError' ? '' : ': ' + (e.message || e))); return; }
  const type = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4', 'audio/ogg;codecs=opus'].find(t => MediaRecorder.isTypeSupported && MediaRecorder.isTypeSupported(t)) || '';
  let r;
  try { r = new MediaRecorder(stream, type ? { mimeType: type } : undefined); } catch(e){ stream.getTracks().forEach(t => t.stop()); toast(e.message); return; }
  const parts = [];
  S.rec = { r, at: Date.now(), into };
  r.ondataavailable = e => { if (e.data && e.data.size) parts.push(e.data); };
  r.onstop = async () => {
    stream.getTracks().forEach(t => t.stop());
    clearInterval(S.recT); S.rec = null; S.hearing = true; drawTools();
    const blob = new Blob(parts, { type: r.mimeType || type || 'audio/webm' });
    try {
      const res = await fetch('/api/sketchbook/dictate', { method: 'POST', body: blob, headers: { 'Content-Type': blob.type }, credentials: 'same-origin' });
      let out = null; try { out = await res.json(); } catch(e){}
      if (!res.ok) throw new Error((out && out.detail) || res.statusText || 'It couldn’t be written down');
      if (out.text && out.text.trim()) putText(out.text.trim(), into);
      else toast('Nothing was heard');
    } catch(e){ toast(navigator.onLine ? e.message : 'Dictation needs Daf on the server'); }
    S.hearing = false; drawTools();
  };
  r.start(1000);
  S.recT = setInterval(() => { const x = S.el && S.el.querySelector('.skrec'); if (x && S.rec) x.textContent = stampOf((Date.now() - S.rec.at) / 1000); }, 500);
  drawTools();
}

/* ---------- the page taken (manga, PDF) ---------- */
// Over the reader: drag a box round what to take, or take the whole page.
function shoot(){
  if (!S.ctx || !S.ctx.shots || document.querySelector('.skshot')) return;
  stopEditing();
  const ov = document.createElement('div'); ov.className = 'skshot';
  ov.innerHTML = '<div class="skshotbar"><button class="btn sm primary" data-ss="whole">Whole page</button><button class="btn sm" data-ss="cancel">Cancel</button></div><div class="skshotbox" hidden></div>';
  document.body.appendChild(ov);
  const box = ov.querySelector('.skshotbox'), done = () => { ov.remove(); document.removeEventListener('keydown', esc1, true); };
  const esc1 = e => { if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); done(); } };
  document.addEventListener('keydown', esc1, true);
  let d = null;
  ov.addEventListener('click', e => { const b = e.target.closest('[data-ss]'); if (!b) return; done(); if (b.dataset.ss === 'whole') take(null); });
  ov.addEventListener('pointerdown', e => {
    if (e.target.closest('.skshotbar')) return;
    e.preventDefault(); d = { id: e.pointerId, x: e.clientX, y: e.clientY };
    try { ov.setPointerCapture(e.pointerId); } catch(_){}
  });
  ov.addEventListener('pointermove', e => {
    if (!d || e.pointerId !== d.id) return;
    const x1 = Math.min(d.x, e.clientX), y1 = Math.min(d.y, e.clientY), x2 = Math.max(d.x, e.clientX), y2 = Math.max(d.y, e.clientY);
    d.r = { left: x1, top: y1, right: x2, bottom: y2, width: x2 - x1, height: y2 - y1 };
    const o = ov.getBoundingClientRect();
    Object.assign(box.style, { left: x1 - o.left + 'px', top: y1 - o.top + 'px', width: x2 - x1 + 'px', height: y2 - y1 + 'px' }); box.hidden = false;
  });
  const up = e => { if (!d || e.pointerId !== d.id) return; const r = d.r; d = null; if (r && r.width > 16 && r.height > 16) { done(); take(r); } else box.hidden = true; };
  ov.addEventListener('pointerup', up); ov.addEventListener('pointercancel', up);
}
const meet = (a, b) => { const l = Math.max(a.left, b.left), t = Math.max(a.top, b.top), r = Math.min(a.right, b.right), bt = Math.min(a.bottom, b.bottom); return r > l && bt > t ? { left: l, top: t, right: r, bottom: bt, width: r - l, height: bt - t } : null; };
// Where an element's picture is on the screen, and the part of its picture that is: an image drawn
// to fit its box (object-fit: contain), half of a wide page, a PDF page's canvas.
async function sourceOf(el){
  const r = el.getBoundingClientRect();
  if (el.tagName === 'CANVAS') return el.width ? { img: el, rect: r, sx: 0, sy: 0, sw: el.width, sh: el.height } : null;
  if (el.tagName === 'IMG') {
    if (!el.complete || !el.naturalWidth) return null;
    const nw = el.naturalWidth, nh = el.naturalHeight, cs = getComputedStyle(el);
    let rect = r;
    if (cs.objectFit === 'contain' || cs.objectFit === 'scale-down') {
      const s = Math.min(r.width / nw, r.height / nh), w = nw * s, h = nh * s;
      const pos = (cs.objectPosition || '50% 50%').split(' '), f = v => /left|top/.test(v) ? 0 : /right|bottom/.test(v) ? 1 : /%$/.test(v) ? parseFloat(v) / 100 : 0.5;
      const l = r.left + (r.width - w) * f(pos[0]), t = r.top + (r.height - h) * f(pos[1] || '50%');
      rect = { left: l, top: t, right: l + w, bottom: t + h, width: w, height: h };
    }
    return { img: el, rect, sx: 0, sy: 0, sw: nw, sh: nh };
  }
  const m = /url\(["']?([^"')]+)["']?\)/.exec(getComputedStyle(el).backgroundImage || '');
  if (!m) return null;
  const img = new Image(); img.src = m[1];
  try { await img.decode(); } catch(e){ return null; }
  const right = /100%|right/.test(getComputedStyle(el).backgroundPosition || '');
  return { img, rect: r, sx: right ? img.naturalWidth / 2 : 0, sy: 0, sw: img.naturalWidth / 2, sh: img.naturalHeight };
}
async function take(box){
  const els = (S.ctx && S.ctx.shots ? S.ctx.shots() : []) || [], area = room();
  const view = { left: area.x, top: area.y, right: area.x + area.w, bottom: area.y + area.h, width: area.w, height: area.h };
  let parts = [];
  for (const el of els) { const s = await sourceOf(el); if (!s) continue; const v = meet(s.rect, view); if (v) parts.push(Object.assign(s, { el, seen: v.width * v.height })); }
  if (!box) {                                         // the whole page: what fills the screen most (a spread's two pages)
    const most = Math.max(0, ...parts.map(p => p.seen));
    parts = parts.filter(p => p.seen >= most * 0.6);
    if (!parts.length) { toast('There’s no page here to take'); return; }
    box = parts.map(p => meet(p.rect, view)).reduce((a, b) => ({ left: Math.min(a.left, b.left), top: Math.min(a.top, b.top), right: Math.max(a.right, b.right), bottom: Math.max(a.bottom, b.bottom) }));
    box.width = box.right - box.left; box.height = box.bottom - box.top;
  }
  parts = parts.filter(p => meet(p.rect, box));
  if (!parts.length) { toast('There’s no page there'); return; }
  const dens = Math.max(...parts.map(p => p.sw / p.rect.width)), s = Math.max(0.5, Math.min(dens, 1600 / Math.max(box.width, box.height)));
  const cv = document.createElement('canvas'); cv.width = Math.round(box.width * s); cv.height = Math.round(box.height * s);
  const x = cv.getContext('2d'); x.fillStyle = '#ffffff'; x.fillRect(0, 0, cv.width, cv.height);
  for (const p of parts) {
    const i = meet(p.rect, box), fx = p.sw / p.rect.width, fy = p.sh / p.rect.height;
    try { x.drawImage(p.img, p.sx + (i.left - p.rect.left) * fx, p.sy + (i.top - p.rect.top) * fy, i.width * fx, i.height * fy, (i.left - box.left) * s, (i.top - box.top) * s, i.width * s, i.height * s); } catch(e){}
  }
  let src;
  try { src = cv.toDataURL('image/jpeg', 0.85); } catch(e){ toast('That page can’t be taken'); return; }
  const nums = [...new Set(parts.map(p => { const n = p.el.closest('[data-pg]'); return n ? +n.dataset.pg : p.el.dataset.n != null ? +p.el.dataset.n + 1 : null; }).filter(Boolean))].sort((a, b) => a - b);
  const m = { id: newId('i'), kind: 'image', ord: lastOrd() + 1, h: r1(INK_W * box.height / box.width), src,
              cap: nums.length ? (nums.length > 1 ? 'pp. ' + nums[0] + '–' + nums[nums.length - 1] : 'p. ' + nums[0]) : '' };
  setCur(cur().concat(m)); render(); act({ add: [m] });
  const el = S.page.querySelector('.skblk[data-id="' + m.id + '"]'); if (el) el.scrollIntoView({ block: 'center' });
}

/* ---------- a book: the chapter where you are ---------- */
// The chapter a place is in: the contents' entry at the top level, or one down when the top level is
// a few parts holding the chapters.
function chapterOf(view, tocItem){
  const toc = (view && view.book && view.book.toc) || [];
  if (!tocItem || !toc.length) return null;
  const parts = toc.length <= 8 && toc.filter(t => t.subitems && t.subitems.length).length >= toc.length / 2;
  const level = parts ? 1 : 0, path = [];
  const find = (items, depth) => { for (const it of items) { path[depth] = it; if (it === tocItem || (it.href && it.href === tocItem.href)) { path.length = depth + 1; return true; } if (it.subitems && find(it.subitems, depth + 1)) return true; } return false; };
  if (!find(toc, 0)) return null;
  const it = path[Math.min(level, path.length - 1)];
  let pos = null;
  try { const at = view.resolveNavigation(it.href), fr = view.getSectionFractions(); if (at && fr) pos = r2(fr[at.index] || 0); } catch(e){}
  return { tab: 'c:' + String(it.href || it.label).slice(0, 400), title: String(it.label || '').trim() || 'A chapter', pos };
}
function relocated(d){
  const ctx = S.ctx; if (!ctx || !ctx.view) return;
  const h = chapterOf(ctx.view, d && d.tocItem);
  if (!h || (S.here && S.here.tab === h.tab)) return;
  S.here = h;
  if (S.follow && S.tab !== h.tab && !S.editing) show1(h.tab, h); else drawTabs();
}

/* ---------- opening and closing ---------- */
const openKey = () => 'open.' + (S.ctx ? S.ctx.kind : 'doc');
function show(){
  if (!S.ctx) return;
  build();
  S.shown = true; S.el.hidden = false;
  place(); theme();
  const s = Pens.surface(); if (s && s !== surface) S.prev = s;
  Pens.use(surface);
  drawTabs(); drawTools();
  if (!S.pages.has(key())) { setCur([]); render(); load(S.tab); } else { render(); load(S.tab); }
  store.set(openKey(), true);
  buttons(); relayout();
}
function hide(keep){
  if (!S.shown) return;
  stopEditing(); unpick(); readNow(); flush();
  if (S.rec) S.rec.r.stop();
  S.shown = false; if (S.el) S.el.hidden = true;
  place();
  if (Pens.surface() === surface) Pens.use(S.prev && S.prev.live && S.prev.live() ? S.prev : null);
  if (!keep && S.ctx) store.set(openKey(), false);
  buttons(); relayout();
}
function toggle(){ if (S.shown) hide(); else show(); }
function buttons(){ document.querySelectorAll('[data-sketch]').forEach(b => { b.setAttribute('aria-pressed', String(S.shown)); b.classList.toggle('on', S.shown); }); }
// A reader opened something: the Sketchbook is for that now, and comes up if it was up last time.
// ctx: {item, kind (book | doc | pdf | manga), here() (where you are: {tab, title, pos}), view (a book's
// foliate view), shots() (what the camera can take), time() and seek(t) (a video's), resized()}.
function attach(ctx){
  if (!ctx || !ctx.item) return;
  stopEditing(); unpick(); readNow(); flush();
  if (S.off) { S.off(); S.off = null; }
  const same = S.ctx && S.ctx.item === ctx.item;
  S.ctx = ctx;
  const s = Pens.surface(); if (s && s !== surface) S.prev = s;
  if (!same) { S.tabs = []; S.pages = new Map(); S.vault = null; }
  S.done = []; S.undone = []; S.follow = true;
  S.here = ctx.here ? ctx.here() : null;
  S.tab = S.here ? S.here.tab : ''; S.meta = S.here || {};
  if (ctx.view) {
    const on = e => relocated(e.detail), loaded = e => watchDoc(e.detail && e.detail.doc);
    ctx.view.addEventListener('relocate', on); ctx.view.addEventListener('load', loaded);
    try { for (const c of ctx.view.renderer.getContents()) watchDoc(c.doc); } catch(e){}
    S.off = () => { ctx.view.removeEventListener('relocate', on); ctx.view.removeEventListener('load', loaded); };
  }
  if (store.get(openKey(), false)) { if (S.shown) { place(); show1(S.tab, S.meta); Pens.use(surface); drawTools(); relayout(); } else show(); }
  else if (S.shown) hide(true);
  buttons();
}
function detach(){
  if (!S.ctx) return;
  hide(true);
  if (S.off) { S.off(); S.off = null; }
  S.ctx = null;
}
// The bar's button, in each reader's own kind of button.
function button(kind){
  const label = 'Sketchbook', on = S.shown;
  const cls = kind === 'manga' ? 'mic' : 'ib';
  return '<button class="' + cls + (on ? ' on' : '') + '" data-sketch aria-pressed="' + on + '" title="' + label + '" aria-label="' + label + '">' + IC.book + '</button>';
}
document.addEventListener('click', e => { const b = e.target.closest && e.target.closest('[data-sketch]'); if (!b) return; e.preventDefault(); toggle(); });
// Gone from the readers (a list, Today): it goes, and comes back with the next one opened.
const watchView = () => new MutationObserver(() => { if (S.ctx && !READING.includes(document.body.dataset.view)) detach(); }).observe(document.body, { attributes: true, attributeFilter: ['data-view'] });
if (document.body) watchView(); else document.addEventListener('DOMContentLoaded', watchView);
window.addEventListener('resize', () => { if (!S.shown) return; const was = S.mode; place(); if (was !== S.mode) { drawTools(); relayout(); } later(); });
window.addEventListener('daf-theme', () => { theme(); later(); });
document.addEventListener('visibilitychange', () => { if (document.visibilityState === 'hidden') { readNow(); flush(); } else if (S.shown && S.ctx) load(S.tab); });
window.addEventListener('pagehide', flush);
window.addEventListener('online', () => { if (S.shown && S.ctx) setTimeout(() => load(S.tab), 3000); });

C.Sketch = { attach, detach, button, toggle, show, hide, room, open: () => S.shown, flush,
  state: () => ({ shown: S.shown, mode: S.mode, item: S.ctx && S.ctx.item, tab: S.tab, here: S.here, tabs: tabList().map(t => t.tab),
    blocks: blocksOf(cur()).map(b => b.kind + (b.type ? ':' + b.type : '') + ':' + strokesOf(cur(), b.id).length + (b.transcript ? ':' + b.transcript : '')),
    editing: !!S.editing, picked: S.picked, queued: S.q ? S.q.add.size + S.q.remove.size : 0, done: S.done.length, surface: Pens.surface() === surface }) };
})();
