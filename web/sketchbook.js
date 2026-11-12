/* The Notebook: pages beside whatever is open (a book, an article, a video, a podcast episode, a
   PDF, a manga volume) to write and draw on with the pen, type on, and say things into, with the
   highlights on them. Kept on the server (daf/sketchbook.py: it was the Sketchbook, and is still
   called that in the code), in the vault as a note of its own in the Ink plugin's format
   (sketchvault.py), and, for a book, on the Kindle.

   One Notebook, two ways to look at it. Pages: a chapter's page, its highlights on it as cards in
   reading order (from the highlights themselves, which stay highlights), and what's written, typed
   and drawn above them and under each one; a highlight made while reading lands on the page in its
   place, and a tap on a card goes to it in the book. List: everything in it, the highlights with
   what's written under them (the handwriting as it was read), searchable. The head: General, the
   chapter (it follows where you are; a tap picks another), Pages or List, and close.

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

   A book has a page a chapter, following where you are, and General; a manga series a page a
   volume; anything else one page. A block written under a card keeps the highlight's id (hl) and
   where it was (hat), so it stays under it, and where the card was if the highlight goes; blocks
   written before there were cards stay above them. A video's typed notes and new handwriting carry its time. The camera puts
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
  panel: '<svg width="17" height="17" viewBox="0 0 20 20" aria-hidden="true"><rect x="3" y="4" width="14" height="12" rx="2" fill="none" stroke="currentColor" stroke-width="1.6"/><path d="M12.5 4v12" stroke="currentColor" stroke-width="1.6"/></svg>',
  close: '<svg width="18" height="18" viewBox="0 0 20 20" aria-hidden="true"><path d="M5 5l10 10M15 5L5 15" stroke="currentColor" stroke-width="1.9" stroke-linecap="round"/></svg>',
  trash: '<svg width="17" height="17" viewBox="0 0 20 20" aria-hidden="true"><path d="M4 6h12M8 6V4.5h4V6M5.5 6l.8 10h7.4l.8-10" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  chev: '<svg width="12" height="12" viewBox="0 0 20 20" aria-hidden="true"><path d="M5.5 7.5 10 12l4.5-4.5" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  pen: '<svg width="14" height="14" viewBox="0 0 20 20" aria-hidden="true"><path d="M4 16l1-4 8.5-8.5a1.8 1.8 0 0 1 2.5 2.5L7.5 14.5z" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"/></svg>',
  mark: '<svg width="14" height="14" viewBox="0 0 20 20" aria-hidden="true"><path d="M4 15.5h12" stroke="currentColor" stroke-width="2" stroke-linecap="round"/><path d="M6 12l1.5-5 6-3 1.5 3-4.5 5z" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/></svg>',
  search: '<svg width="16" height="16" viewBox="0 0 20 20" aria-hidden="true"><circle cx="8.5" cy="8.5" r="5" fill="none" stroke="currentColor" stroke-width="1.8"/><path d="M12.5 12.5l4 4" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>',
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
  view: store.get('view', 'pages') === 'list' ? 'list' : 'pages',
  hls: [],                // the item's highlights: {id, text, color, key (reading order), tab, where, note, raw}
  groups: [],             // the page as laid out: [{id ('' above the cards, else a highlight's), key, card, blocks}]
  picking: false, focusHl: null, chs: null,
  all: null, lq: '', chip: 'all',   // the list: every page's blocks, what's searched, which chip
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
// A phone's sheet is most of the screen; a tablet's, a little over half of it, until it's pulled.
const phone = () => Math.min(S.fullW || innerWidth, S.fullH || innerHeight) < 600;
const sheetH = () => phone() ? 0.6 : 0.56;
function sizes(){
  if (sideways()) { const m = paperW() + 2; return { mode: 'side', w: Math.round(clamp(innerWidth * store.get('w', 0.4), m, Math.max(m, innerWidth - 320))) }; }
  // the keyboard up while typing in it (the app's window shrinks): most of what's left
  const typing = S.editing && S.fullH && innerHeight < S.fullH * 0.8;
  const h = typing ? innerHeight - 110 : Math.round(clamp(innerHeight * store.get('h', sheetH()), 170, Math.max(170, innerHeight - (phone() ? 90 : 180))));
  return { mode: store.get('top', false) ? 'top' : 'bottom', h };
}
function place(){
  const r = document.documentElement, z = sizes();
  S.mode = z.mode;
  if (!S.editing || innerWidth !== S.fullW) { S.fullH = innerHeight; S.fullW = innerWidth; }
  r.classList.toggle('skopen', S.shown || S.extra > 0);
  r.classList.toggle('skside', S.shown && z.mode === 'side');
  r.classList.toggle('skbottom', S.shown && z.mode === 'bottom');
  r.classList.toggle('sktop', S.shown && z.mode === 'top');
  r.style.setProperty('--skr', ((S.shown && z.mode === 'side' ? z.w : 0) + (S.extra || 0)) + 'px');
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
  el.className = 'skb'; el.id = 'skb'; el.setAttribute('aria-label', 'Notebook'); el.hidden = true;
  el.innerHTML = '<div class="skgrip" role="separator" aria-label="Resize the Notebook"><i></i></div>' +
    '<div class="ptabs skptabs" role="tablist" hidden>' + PTABS.map(t => '<button class="ptab' + (t[0] === 'notebook' ? ' on' : '') + '" data-skpt="' + t[0] + '" role="tab">' + t[1] + '</button>').join('') + '</div>' +
    '<div class="skhead"><div class="skwhere"></div><span class="spacer"></span>' +
      '<div class="skseg" role="tablist" aria-label="Notebook"><button role="tab" data-skv="pages">Pages</button><button role="tab" data-skv="list">List</button></div>' +
      '<span class="skhb"></span><div class="skpick" role="listbox" aria-label="Chapters" hidden></div></div>' +
    '<div class="skbody"><iframe class="skframe" title="Notebook page"></iframe>' +
      '<div class="sklist" hidden><div class="sklhead"><label class="sklq"><span class="ic">' + IC.search + '</span><input type="search" placeholder="Search" aria-label="Search the Notebook" autocomplete="off" dir="auto"></label><div class="sklchips"></div></div><div class="sklrows"></div></div>' +
      '<div class="sktools"><span class="skpens"></span><span class="skown"></span></div></div>';
  document.body.appendChild(el);
  el.addEventListener('click', onHead);
  // the head's buttons leave the typing where it is (a tap there doesn't end it)
  el.addEventListener('mousedown', e => { if (e.target.closest('.skhead button, .sktools button')) e.preventDefault(); });
  el.querySelector('.sklq input').addEventListener('input', e => { S.lq = e.target.value; drawRows(); });
  el.querySelector('.sklist').addEventListener('click', onList);
  el.querySelector('.sklist').addEventListener('focusout', () => setTimeout(() => { if (S.listStale && !typingInList()) { S.listStale = false; drawRows(); } }, 400));
  document.addEventListener('pointerdown', e => { if (S.picking && !e.target.closest('.skpick, [data-skch]')) { S.picking = false; drawHead(); } }, true);
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
    if (S.mode === 'side') {                      // (never narrower than the page; pushed well past it, it closes)
      const w = innerWidth - e.clientX;
      drag.gone = w < paperW() * 0.55;
      if (!drag.gone) store.set('w', clamp(w / innerWidth, 0.2, 0.8));
    }
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
    if (d.gone) { if (S.mode !== 'side') store.set('h', sheetH()); hide(); return; }
    if (d.moved) relayout();
  };
  g.addEventListener('pointerup', up);
  g.addEventListener('pointercancel', up);
}

/* ---------- the head: General, the chapter, Pages or List ---------- */
const many = () => !!S.ctx && (S.ctx.kind === 'book' || S.ctx.kind === 'manga');
const rtl = t => /[֐-׿]/.test(t || '') ? ' dir="rtl"' : '';
// The pages there are: General, the chapters (a book's every one, from its contents; a manga series'
// volumes with something on them), where you are, and the one open.
function tabList(){
  const ts = (S.ctx && S.ctx.kind === 'book' && S.ctx.view ? bookChapters(S.ctx.view) : []).map(t => Object.assign({}, t));
  const add = t => { if (t && !ts.some(x => x.tab === t.tab)) ts.push(Object.assign({}, t)); };
  for (const t of S.tabs) add(t);
  add({ tab: '', title: 'General' });
  add(S.here);
  add(S.tab ? { tab: S.tab, title: S.meta.title, pos: S.meta.pos } : null);
  const n = new Map(S.tabs.map(t => [t.tab, t.n || 0])), h = new Map();
  for (const x of S.hls) h.set(x.tab || '', (h.get(x.tab || '') || 0) + 1);
  return ts.map(t => Object.assign(t, { n: n.get(t.tab) || 0, h: h.get(t.tab) || 0 }))
    .sort((a, b) => (a.tab !== '') - (b.tab !== '') || (a.pos != null ? a.pos : 2) - (b.pos != null ? b.pos : 2));
}
// The chapter the second button names: the one open, else where you are.
function chapterShown(){
  if (S.tab) return { tab: S.tab, title: S.meta.title, pos: S.meta.pos };
  if (S.here) return S.here;
  return tabList().find(t => t.tab) || null;
}
function drawHead(){
  if (!S.el || !S.ctx) return;
  const w = S.el.querySelector('.skwhere'), pick = S.el.querySelector('.skpick');
  w.hidden = !many();
  if (many()) {
    const ch = chapterShown(), gen = !S.tab;
    w.innerHTML = '<button class="skwh' + (gen ? ' on' : '') + '" data-sktab="" aria-pressed="' + gen + '">General</button>' +
      (ch ? '<button class="skwh skch' + (gen ? '' : ' on') + (S.here && ch.tab === S.here.tab ? ' here' : '') + '" data-skch aria-haspopup="listbox" aria-expanded="' + S.picking + '"' + rtl(ch.title) + '>' +
        '<span class="t">' + esc(ch.title || 'Chapter') + '</span><i class="dot"></i>' + IC.chev + '</button>' : '');
  }
  S.el.querySelectorAll('[data-skv]').forEach(b => b.setAttribute('aria-selected', String(b.dataset.skv === S.view)));
  const b = (k, label, icon) => '<button class="ib" data-sk="' + k + '" title="' + label + '" aria-label="' + label + '">' + icon + '</button>';
  S.el.querySelector('.skhb').innerHTML = (S.mode !== 'side' && !phone() ? b('flip', S.mode === 'top' ? 'Move to the bottom' : 'Move to the top', S.mode === 'top' ? IC.toBottom : IC.toTop) : '') + b('close', 'Close the Notebook', IC.close);
  const was = !pick.hidden;
  pick.hidden = !(S.picking && many());
  if (!pick.hidden && !was) {                       // (drawn when it opens, not again while it's open)
    pick.innerHTML = tabList().filter(t => t.tab).map(t => '<button role="option" data-sktab="' + esc(t.tab) + '" aria-selected="' + (t.tab === S.tab) + '"' + (S.here && t.tab === S.here.tab ? ' class="here"' : '') + '>' +
      '<span class="t"' + rtl(t.title) + '>' + esc(t.title || 'Chapter') + '</span><i class="dot"></i><span class="n">' + (t.h ? '<span>' + IC.mark + t.h + '</span>' : '') + (t.n ? '<span>' + IC.pen + '</span>' : '') + '</span></button>').join('');
    const on = pick.querySelector('[aria-selected="true"]') || pick.querySelector('.here');
    if (on) on.scrollIntoView({ block: 'center' });
  }
}
const drawTabs = drawHead;
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
    (mine ? b('undo', 'Undo', IC.undo, null, !S.done.length) + b('redo', 'Redo', IC.redo, null, !S.undone.length) : '');
  drawHead();
}
function onHead(e){
  const pt = e.target.closest('[data-skpt]'); if (pt) { panelTab(pt.dataset.skpt); return; }
  const t = e.target.closest('[data-sktab], [data-sk], [data-skch], [data-skv]'); if (!t) return;
  if (t.dataset.skv) { setView(t.dataset.skv); return; }
  if (t.dataset.skch != null) {
    const ch = chapterShown();
    if ((!S.tab || S.view === 'list') && ch && !S.picking) { S.picking = false; S.follow = !!(S.here && ch.tab === S.here.tab); if (S.view === 'list') setView('pages'); show1(ch.tab, ch); }
    else { S.picking = !S.picking; drawHead(); }
    return;
  }
  if (t.dataset.sktab != null) {
    const tab = t.dataset.sktab, x = tabList().find(y => y.tab === tab);
    S.picking = false; S.follow = !!(S.here && tab === S.here.tab);
    if (S.view === 'list') { S.view = 'pages'; setView('pages'); }
    show1(tab, x); return;
  }
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
// Pages or List.
function setView(v){
  v = v === 'list' ? 'list' : 'pages';
  if (v === 'list') { stopEditing(); unpick(); }
  S.view = v; store.set('view', v); S.picking = false;
  if (!S.el) return;
  S.el.classList.toggle('sklisting', v === 'list');
  S.el.querySelector('.sklist').hidden = v !== 'list';
  if (v === 'list') { S.all = S.all || []; drawList(); loadAll(); } else render();
  drawHead();
}

/* ---------- a tab's page ---------- */
async function show1(tab, meta){
  flush(); stopEditing(); unpick(); readNow();
  S.tab = tab; S.meta = meta || {}; S.done = []; S.undone = []; S.picking = false;
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
// around it and the lines stay as they are, and the panel's edge stops at the page's width, so the
// lines never change size as it's dragged. A phone's page is its whole width.
// (with a mouse the page is narrower, so the Notebook can be pushed further to the side: the pen is the tablet's)
function paperW(){ return Math.round(clamp(Math.max(S.fullW || innerWidth, S.fullH || innerHeight) * (matchMedia('(pointer: coarse)').matches ? 0.4 : 0.27), 300, 720)); }
function pageW(room){
  const w = S.fullW || innerWidth, h = S.fullH || innerHeight;
  if (Math.min(w, h) < 600) return room;                 // a phone: all of its width
  return Math.min(room, paperW() - 20);
}
// The page's highlights, as cards: this chapter's (an article's, all of them), in reading order.
const cardsHere = () => S.ctx && S.ctx.highlights ? S.hls.filter(h => (h.tab || '') === S.tab).sort((a, b) => a.key - b.key) : [];
// The page's blocks with the cards: first what's above every card (written before there were any),
// then each card with what's written under it. A block whose highlight is gone stays where its card was.
function grouped(bl){
  const top = { id: '', key: -Infinity, card: null, blocks: [] }, gs = [top], by = new Map();
  for (const h of cardsHere()) { const g = { id: h.id, key: h.key, card: h, blocks: [] }; by.set(h.id, g); gs.push(g); }
  for (const b of bl) {
    let g = top;
    if (b.hl) {
      g = by.get(b.hl);
      if (!g) { g = { id: b.hl, key: b.hat != null ? b.hat : Infinity, card: null, blocks: [] }; by.set(b.hl, g); gs.push(g); }
    }
    g.blocks.push(b);
  }
  return gs.sort((a, b) => (a.key - b.key) || 0);
}
// What a block written at the end of a group (or under a block in it) keeps of where it is.
const anchorOf = g => !g || !g.id ? {} : Object.assign({ hl: g.id }, isFinite(g.key) ? { hat: g.key } : {});
const real = b => !(S.editing && S.editing.fresh && S.editing.m.id === b.id);
const seq = () => S.groups.flatMap(g => g.blocks.filter(real));
const groupOf = id => S.groups.find(g => g.id === id) || null;
const lastGroup = () => S.groups[S.groups.length - 1] || null;
const ordBetween = (p, n) => { const a = p ? p.ord || 0 : null, z = n ? n.ord || 0 : null; return a != null && z != null ? (z > a ? (a + z) / 2 : a + 0.001) : a != null ? a + 1 : z != null ? z - 1 : 1; };
// The place for a new block at the end of a group: after everything before it, before what's after.
function ordEnd(g){
  const gs = S.groups, i = Math.max(0, gs.indexOf(g));
  let p = null, n = null;
  for (let j = i; j >= 0 && !p; j--) { const bs = gs[j].blocks.filter(real); if (bs.length) p = bs[bs.length - 1]; }
  for (let j = i + 1; j < gs.length && !n; j++) { const bs = gs[j].blocks.filter(real); if (bs.length) n = bs[0]; }
  return ordBetween(p, n);
}
const quote = t => C.HL && C.HL.quote ? C.HL.quote(t) : esc(t);
function cardHTML(h){
  const t = String(h.text || '').replace(/[^\S\n]*\n(?:[^\S\n]*\n)+/g, '\n').trim();
  return '<div class="skblk skcard" data-hl="' + esc(h.id) + '" data-color="' + esc(h.color || 'yellow') + '" role="link" tabindex="0">' +
    '<div class="skcq"><span class="skq"' + rtl(t) + '>' + quote(t) + '</span>' + (h.note ? '<span class="sknote" dir="auto">' + esc(h.note) + '</span>' : '') +
    (h.where ? '<span class="skwh2">' + esc(h.where) + '</span>' : '') + '</div></div>';
}
function render(){
  if (!S.page || !S.shown || S.view !== 'pages') return;
  const room = S.doc.documentElement.clientWidth - 20; if (room < 50) return;
  const W = pageW(room);
  const ms = cur(), bl = blocksOf(ms), ed = S.editing;
  if (ed && ed.fresh && !bl.some(b => b.id === ed.m.id)) bl.push(ed.m);      // the text being typed, in its place
  const gs = S.groups = grouped(blocksOf(bl)), cards = gs.some(g => g.card);
  const shown = gs.filter(g => g.card || g.blocks.length || (!g.id && !cards));
  const lastG = shown[shown.length - 1], last = lastG.blocks.filter(real).slice(-1)[0];
  S.W = W; S.page.style.width = W + 'px';
  S.page.classList.toggle('sheet', W < room - 24);
  S.page.style.setProperty('--skl', r2(LINE * W / INK_W) + 'px');
  let h = '';
  const fr = new Map(), slot = '<div class="skslot"></div>', lh = LINE * W / INK_W;
  for (const g of shown) {
    if (g.card) h += cardHTML(g.card);
    for (const b of g.blocks) {
      if (ed && ed.m.id === b.id) { h += slot; continue; }
      const st = strokesOf(ms, b.id), f = frameOf(b, W, st);
      if (b.kind === 'ink' && b.type === 'writing' && b === last) f.h += LINE * f.k;     // the last one has room to go on
      fr.set(b.id, f);
      if (b.kind === 'text') h += '<div class="skblk sktext' + (b.text ? '' : ' stamp') + '" data-id="' + b.id + '" dir="auto">' + stampHTML(b) + esc(b.text || '') + '</div>';
      else if (b.kind === 'image') h += '<div class="skblk skpic" data-id="' + b.id + '" style="height:' + r1(f.h) + 'px"><img alt="' + esc(b.cap || '') + '" draggable="false" src="' + esc(picSrc(b)) + '">' + (b.cap ? '<span class="skcap">' + esc(b.cap) + '</span>' : '') + '</div>';
      else h += '<div class="skblk skink ' + (b.type === 'drawing' ? 'skdraw' : 'skwrite') + '" data-id="' + b.id + '" style="height:' + r1(f.h) + 'px">' + stampHTML(b) + '</div>';
    }
    // under each card's notes, a line or two to write on (writing there goes on with its last handwriting)
    if (g !== lastG) { const wl = g.blocks.length && g.blocks[g.blocks.length - 1].kind === 'ink' && g.blocks[g.blocks.length - 1].type === 'writing'; h += '<div class="skblk skend skgap" data-g="' + esc(g.id) + '" style="height:' + r2((wl ? 1 : 2) * lh) + 'px"></div>'; }
  }
  // under everything: ruled paper, where writing starts a new handwriting block and a tap types
  const lines = Math.max(last && last.kind === 'ink' && last.type === 'writing' ? 1 : 3, Math.ceil((S.frame.clientHeight || 0) * 0.35 / lh));
  h += '<div class="skblk skend" data-g="' + esc(lastG.id) + '" style="height:' + r2(lines * lh) + 'px"></div>';
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
  const ends = S.page.querySelectorAll('.skend:not(.skgap)'), endEl = ends[ends.length - 1];
  const gap = (S.frame.clientHeight || 0) - 50 - S.page.offsetHeight;
  if (endEl && gap >= lh) endEl.style.height = r2((lines + Math.floor(gap / lh)) * lh) + 'px';
  S.boxes = []; S.geo.clear(); S.layers.clear();
  for (const el of S.page.children) {
    if (!el.classList.contains('skblk')) continue;
    const top = el.offsetTop, bh = el.offsetHeight;
    if (el.classList.contains('skend')) { S.boxes.push({ end: true, g: el.dataset.g || '', el, top, h: bh, k: W / INK_W, ox: 0, oy: 0 }); continue; }
    if (el.classList.contains('skcard')) { S.boxes.push({ card: el.dataset.hl, el, top, h: bh }); continue; }
    const b = bl.find(x => x.id === el.dataset.id), f = b && fr.get(b.id); if (!f) continue;
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
  if (S.focusHl) focusCard();
}
// A card gone to (from the book, the list, a highlight just made): in view, and lit a moment.
function focusCard(){
  const id = S.focusHl; if (!id || !S.page || S.view !== 'pages') return;
  const el = [...S.page.querySelectorAll('.skcard')].find(x => x.dataset.hl === id); if (!el) return;
  S.focusHl = null;
  el.scrollIntoView({ block: 'center' });
  el.classList.add('flash'); setTimeout(() => el.classList.remove('flash'), 1800);
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
function boxAt(py){
  const at = S.boxes.find(b => py >= b.top && py < b.top + b.h); if (at) return at;
  const above = S.boxes.filter(b => b.top <= py);
  return above.length ? (py >= 0 ? above[above.length - 1] : S.boxes[0]) : S.boxes[0] || null;
}
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
// The place right under a block (in its group, with what it keeps of where it is: anchor()).
function ordAfter(b){
  const s = seq(), i = s.findIndex(x => x.id === b.id);
  return i < 0 ? (b.ord || 0) + 1 : ordBetween(b, s[i + 1]);
}
const anchor = b => b && b.hl ? Object.assign({ hl: b.hl }, b.hat != null ? { hat: b.hat } : {}) : {};
function timeNow(){
  const ctx = S.ctx; if (!S.timeOn || !ctx || !ctx.time) return null;
  let t = 0; try { t = ctx.time() || 0; } catch(e){}
  return t > 0 ? r1(t) : null;
}
// Points on the page (px) into a block's units: the block the first one is in, or a new handwriting
// block under everything. Returns [the block (new: not on the page yet), points].
function intoBlock(pts){
  const box = boxAt(pts[0][1]); if (!box || box.card) return null;
  let b = box.b, fresh = null;
  if (box.end) {                       // under a card's notes, or under everything: its last handwriting, or new
    const g = groupOf(box.g) || lastGroup(), last = g ? g.blocks.filter(real).slice(-1)[0] : null;
    if (last && last.kind === 'ink' && last.type === 'writing') b = last;
    else {
      fresh = b = Object.assign({ id: newId('b'), kind: 'ink', type: 'writing', ord: ordEnd(g) }, anchorOf(g));
      const t = timeNow(); if (t != null) b.t = t;
    }
  }
  if (!b || b.kind === 'text') return null;
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
  takes: (el, doc) => doc === S.doc && !!el.closest && !el.closest('.skbar, .sktext, .skcard, textarea'),
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
  const left = strokesOf(ms, blk.id).length, t = Object.assign({ id: newId('t'), kind: 'text', text, ord: ordAfter(blk) }, anchor(blk));
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
  const card = t.closest('.skcard');
  if (card) { goTo(card.dataset.hl); return; }   // a highlight's card: to it, in the book
  const el = t.closest('.skblk'), b = el && el.dataset.id ? byId(el.dataset.id) : null;
  if (!e.isTrusted) {                       // the pen's tap (pens.js): typed text to type in; anywhere else a dot
    if (b && b.kind === 'text') edit(b, e); else dot(e.clientX, e.clientY);
    return;
  }
  if (Date.now() - S.editEnd < 350) return;  // the tap that ends typing only ends it
  if (b && b.kind === 'text') { edit(b, e); return; }
  if (b) { if (S.picked === b.id) unpick(); else pick(b.id); return; }
  if (S.picked) { unpick(); return; }
  typeAt(null, null, el && el.classList.contains('skend') ? groupOf(el.dataset.g || '') : null);   // a new text there
}
function goTo(id){
  const ctx = S.ctx, h = S.hls.find(x => x.id === id); if (!ctx || !h || !ctx.go) return;
  stopEditing(); unpick();
  if (S.mode !== 'side' && phone()) hide(true);   // a phone's sheet covers the book: out of the way
  ctx.go(h.raw || h);
}
function dot(cx, cy){
  const b = Pens.brush(); if (!b || !Pens.on()) return;
  const p = S.page.getBoundingClientRect(), x = cx - p.left, y = cy - p.top;
  const got = intoBlock([[x, y, 0.5], [x + 0.3, y, 0.5]]); if (!got) return;
  const [blk, fresh, pts, k] = got;
  addStroke({ id: newId('k'), kind: 'stroke', blk: blk.id, tool: b.pen, color: b.color, size: r1(b.w / k), o: r2(b.opacity), pts }, fresh);
}
// A new text: under a block (after), at the end of a card's notes (g), or at the end of the page.
function typeAt(after, words, g){
  if (S.editing && !after && !g) { if (words) { putText(words); return; } S.editing.ta.focus(); return; }
  stopEditing(); unpick();
  if (!after) g = g || lastGroup();
  const m = Object.assign({ id: newId('t'), kind: 'text', text: words || '', ord: after ? ordAfter(after) : ordEnd(g) }, after ? anchor(after) : anchorOf(g));
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
  // within its group, past its neighbour; the first under a card up over the card, the last down under the next
  const gs = S.groups, gi = gs.findIndex(g => g.blocks.some(x => x.id === b.id)), bs = gi < 0 ? [] : gs[gi].blocks.filter(real);
  const i = bs.findIndex(x => x.id === b.id), o = bs[k === 'up' ? i - 1 : i + 1];
  if (!o) {
    const to = gs[gi + (k === 'up' ? -1 : 1)]; if (!to) return;
    const nb = Object.assign({}, b); delete nb.hl; delete nb.hat; Object.assign(nb, anchorOf(to));
    setCur(cur().map(m => m.id === b.id ? nb : m)); render(); act({ add: [nb], del: [b] });
  } else {
    const nb = Object.assign({}, b, { ord: o.ord }), no = Object.assign({}, o, { ord: b.ord });
    if (nb.ord === no.ord) { nb.ord = k === 'up' ? o.ord - 0.5 : o.ord + 0.5; }
    setCur(cur().map(m => m.id === b.id ? nb : m.id === o.id ? no : m)); render(); act({ add: [nb, no], del: [b, o] });
  }
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
  const g = lastGroup();
  const m = { id: newId('i'), kind: 'image', ord: ordEnd(g), ...anchorOf(g), h: r1(INK_W * box.height / box.width), src,
              cap: nums.length ? (nums.length > 1 ? 'pp. ' + nums[0] + '–' + nums[nums.length - 1] : 'p. ' + nums[0]) : '' };
  setCur(cur().concat(m)); render(); act({ add: [m] });
  const el = S.page.querySelector('.skblk[data-id="' + m.id + '"]'); if (el) el.scrollIntoView({ block: 'center' });
}

/* ---------- a book: the chapter where you are ---------- */
// The chapter a place is in: the contents' entry at the top level, or one down when the top level is
// a few parts holding the chapters.
const tocLevel = toc => toc.length <= 8 && toc.filter(t => t.subitems && t.subitems.length).length >= toc.length / 2 ? 1 : 0;
function chapterOf(view, tocItem){
  const toc = (view && view.book && view.book.toc) || [];
  if (!tocItem || !toc.length) return null;
  const level = tocLevel(toc), path = [];
  const find = (items, depth, same) => { for (const it of items) { path[depth] = it; if (same(it)) { path.length = depth + 1; return true; } if (it.subitems && find(it.subitems, depth + 1, same)) return true; } return false; };
  if (!find(toc, 0, it => it === tocItem) && !find(toc, 0, it => it.href && it.href === tocItem.href)) return null;
  return chapterEntry(view, path[Math.min(level, path.length - 1)]);
}
function chapterEntry(view, it){
  let pos = null;
  try { const at = view.resolveNavigation(it.href), fr = view.getSectionFractions(); if (at && fr) pos = r2(fr[at.index] || 0); } catch(e){}
  return { tab: 'c:' + String(it.href || it.label).slice(0, 400), title: String(it.label || '').trim() || 'A chapter', pos };
}
// Every chapter in the book, at the level chapterOf counts as one (once per book).
function bookChapters(view){
  if (S.chs && S.chs.view === view) return S.chs.list;
  const toc = (view && view.book && view.book.toc) || [], level = tocLevel(toc);
  const items = level ? toc.flatMap(t => t.subitems && t.subitems.length ? t.subitems : [t]) : toc;
  const seen = new Set(), list = [];
  // (two entries at one address are one page: it's named by the later, the chapter after a part's title)
  for (const it of items) { const c = chapterEntry(view, it); if (!seen.has(c.tab)) { seen.add(c.tab); list.push(c); } else list.find(x => x.tab === c.tab).title = c.title; }
  if (list.length) S.chs = { view, list };
  return list;
}
function relocated(d){
  const ctx = S.ctx; if (!ctx || !ctx.view) return;
  const h = chapterOf(ctx.view, d && d.tocItem);
  if (!h || (S.here && S.here.tab === h.tab)) return;
  S.here = h;
  if (S.follow && S.tab !== h.tab && !S.editing) show1(h.tab, h); else drawTabs();
}

/* ---------- the highlights ---------- */
// The reader's highlights (ctx.highlights(): {id, text, color, key, tab or tocItem, where, note, raw}),
// a book's each on its chapter's page.
async function loadHls(){
  const ctx = S.ctx; if (!ctx) return;
  let list = [];
  if (ctx.highlights) { try { list = (await ctx.highlights()) || []; } catch(e){ list = S.hls; } }
  if (S.ctx !== ctx) return;
  for (const h of list) if (h.tab == null) { const c = h.tocItem && ctx.view ? chapterOf(ctx.view, h.tocItem) : null; h.tab = c ? c.tab : ''; }
  S.hls = list;
  if (!S.shown) return;
  if (S.view === 'list') { if (typingInList()) S.listStale = true; else drawRows(); } else if (!S.editing) render();
  drawHead();
}
// A note being typed in the list: its row isn't drawn again under the typing (each pause saves it, and
// the reader then tells the Notebook its highlights changed); the list catches up once the typing ends.
const typingInList = () => { const a = document.activeElement; return !!(a && S.el && a.closest('.sklrows') && a.matches('textarea, input, [contenteditable]')); };
// A highlight made, changed or taken away in the reader: the cards again; one just made, shown on its page.
let hlT = 0;
function hlChanged(id){
  clearTimeout(hlT);
  hlT = setTimeout(async () => {
    const had = new Set(S.hls.map(h => h.id));
    await loadHls();
    const h = id && !had.has(id) ? S.hls.find(x => x.id === id) : null;
    if (h && S.shown && S.view === 'pages' && (h.tab || '') === S.tab) { S.focusHl = h.id; focusCard(); }
  }, 120);
}
// Opened at a highlight: its card on its page (note: its row in the list, typing its note).
async function reveal(o){
  o = o || {};
  if (!S.ctx) return;
  if (!S.hls.some(h => h.id === o.hl)) await loadHls();
  const h = S.hls.find(x => x.id === o.hl);
  if (o.note || o.view === 'list') { S.view = 'list'; if (!S.shown) show(); else setView('list'); if (h) { S.lq = ''; S.chip = 'all'; listTo(h.id, o.note); } return; }
  if (S.view !== 'pages') { S.view = 'pages'; if (S.shown) setView('pages'); }
  if (!S.shown) show();
  if (!h) return;
  S.focusHl = h.id;
  if ((h.tab || '') !== S.tab) { const m = tabList().find(t => t.tab === h.tab) || { tab: h.tab }; S.follow = !!(S.here && h.tab === S.here.tab); await show1(h.tab || '', m); S.focusHl = h.id; }
  focusCard();
}

/* ---------- the list: everything in it ---------- */
const words = b => b.kind === 'text' ? (b.text || '').trim() : (b.transcript || '').trim();
async function loadAll(){
  const ctx = S.ctx; if (!ctx) return;
  flush();
  let r = null;
  try { r = await api('/api/sketchbook/' + encodeURIComponent(ctx.item) + '/all'); } catch(e){}
  if (S.ctx !== ctx) return;
  if (r) S.all = r.tabs || [];
  drawRows();
}
// The pages, with what's here and not on the server yet on top.
function pagesNow(){
  const by = new Map((S.all || []).map(t => [t.tab, Object.assign({}, t)]));
  for (const [k, list] of S.pages) {
    const [item, tab] = k.split('\n'); if (!S.ctx || item !== S.ctx.item) continue;
    const t = by.get(tab) || { tab, title: (tabList().find(x => x.tab === tab) || {}).title, pos: null };
    t.blocks = blocksOf(list).map(b => b.kind === 'text' ? b : Object.assign({}, b, { n: strokesOf(list, b.id).length }));
    by.set(tab, t);
  }
  return by;
}
function drawList(){
  if (!S.el) return;
  const chips = [['all', 'All'], ['hl', 'Highlights' + (S.hls.length ? ' ' + S.hls.length : '')], ['notes', 'With notes']];
  S.el.querySelector('.sklchips').innerHTML = !S.ctx || !S.ctx.highlights ? '' : chips.map(c => '<button class="chip' + (S.chip === c[0] ? ' on' : '') + '" data-skchip="' + c[0] + '" aria-pressed="' + (S.chip === c[0]) + '">' + esc(c[1]) + '</button>').join('');
  const q = S.el.querySelector('.sklq input'); if (q.value !== S.lq) q.value = S.lq;
  drawRows();
}
function drawRows(){
  const box = S.el && S.el.querySelector('.sklrows'); if (!box || S.view !== 'list' || !S.ctx) return;
  const H = C.HL, pages = pagesNow(), q = S.lq.trim().toLowerCase(), chip = S.ctx.highlights ? S.chip : 'all';
  const has = t => !q || t.toLowerCase().includes(q);
  const known = new Map(tabList().map(t => [t.tab, t]));
  // the sections: General, then the chapters in reading order (an article: one)
  const tabs = new Map();
  const sec = tab => { if (!tabs.has(tab)) { const k = known.get(tab) || pages.get(tab) || {}; tabs.set(tab, { tab, title: tab ? k.title || 'Chapter' : 'General', pos: k.pos, hls: [], blocks: [] }); } return tabs.get(tab); };
  if (many()) sec('');
  for (const h of S.hls) sec(many() ? h.tab || '' : '').hls.push(h);
  for (const [tab, t] of pages) if ((t.blocks || []).length) sec(many() ? tab : '').blocks.push(...t.blocks);
  const order = [...tabs.values()].sort((a, b) => (a.tab !== '') - (b.tab !== '') || ((a.pos != null ? a.pos : a.hls.length ? Math.min(...a.hls.map(h => h.key)) : 2) - (b.pos != null ? b.pos : b.hls.length ? Math.min(...b.hls.map(h => h.key)) : 2)) || 0);
  const pen = b => b.kind === 'text' ? '<div class="sklt" dir="auto">' + esc(b.text || '') + '</div>' :
    words(b) ? '<div class="sklw" dir="auto">' + IC.pen + '<span>' + esc(words(b)) + '</span></div>' :
    '<div class="sklw mute">' + IC.pen + '<span>' + (b.kind === 'image' ? esc(b.cap || '') : '') + '</span></div>';
  let html = '', n = 0;
  H.rowOpts = { chapter: false, date: false };
  for (const s of order) {
    const ids = new Set(s.hls.map(h => h.id)), under = new Map();
    const loose = s.blocks.filter(b => { if (b.hl && ids.has(b.hl)) { (under.get(b.hl) || under.set(b.hl, []).get(b.hl)).push(b); return false; } return true; });
    let part = '';
    // what's on the page by itself (above the cards, or under one that's gone)
    if (chip !== 'hl' && loose.length && has(loose.map(words).join(' '))) {
      part += '<article class="hrow skpg" data-sktab2="' + esc(s.tab) + '"><div class="sklpen">' + loose.map(pen).join('') + '</div></article>'; n++;
    }
    for (const h of s.hls.slice().sort((a, b) => a.key - b.key)) {
      const notes = under.get(h.id) || [];
      if (chip === 'notes' && !notes.length && !(h.note || '').trim()) continue;
      if (!has([h.text, h.note || ''].concat(notes.map(words)).join(' '))) continue;
      const x = Object.assign({}, h.raw || h); delete x.open;
      let row = H.row(x, H.rowOpts);
      if (notes.length) row = row.replace('<div class="hmeta">', '<div class="sklpen">' + notes.map(pen).join('') + '</div><div class="hmeta">');
      part += row; n++;
    }
    if (part) html += (many() ? '<div class="sklsec"' + rtl(s.title) + '>' + esc(s.title) + '</div>' : '') + part;
  }
  box.innerHTML = html || '<p class="mute sklnone">' + (q ? 'Nothing found' : 'Nothing here yet') + '</p>';
}
// The list at a highlight's row (and its note open to type in).
function listTo(id, note){
  drawList();
  const row = [...S.el.querySelectorAll('.sklrows .hrow')].find(r => r.dataset.h === id); if (!row) return;
  row.scrollIntoView({ block: 'center' });
  if (note) { const n = row.querySelector('[data-hra="note"]'); if (n) n.click(); }
  else if (C.HL && C.HL.flash) C.HL.flash(row);
}
function onList(e){
  const c = e.target.closest('[data-skchip]');
  if (c) { S.chip = c.dataset.skchip; drawList(); return; }
  if (e.target.closest('.hacts, .hnote, a, textarea, input')) return;
  if (window.getSelection && String(window.getSelection())) return;
  const pg = e.target.closest('.skpg');
  if (pg) { const tab = pg.dataset.sktab2 || ''; S.follow = !!(S.here && tab === S.here.tab); setView('pages'); show1(tab, tabList().find(t => t.tab === tab)); return; }
  const row = e.target.closest('.hrow[data-h]');
  if (row) reveal({ hl: row.dataset.h });
}
window.addEventListener('daf-hl-changed', () => { if (S.shown && S.ctx) { if (S.view === 'list' && document.activeElement && document.activeElement.closest('.sklist')) return; hlChanged(); } });

/* ---------- opening and closing ---------- */
const openKey = () => 'open.' + (S.ctx ? S.ctx.kind : 'doc');
function show(){
  if (!S.ctx) return;
  if (S.extra && C.Split) C.Split.close();     // Side by side has this room (study.js)
  const p = S.ctx.panel; if (p && p.shown()) p.close();        // one tab of the side panel at a time
  build();
  S.el.querySelector('.skptabs').hidden = !p;
  if (p) store.set('ptab', 'notebook');
  S.shown = true; S.el.hidden = false;
  place(); theme();
  const s = Pens.surface(); if (s && s !== surface) S.prev = s;
  Pens.use(surface);
  drawTools();
  if (!S.pages.has(key())) setCur([]);
  setView(S.view); load(S.tab); loadHls();
  store.set(openKey(), true);
  buttons(); relayout();
}
function hide(keep){
  if (!S.shown) return;
  stopEditing(); unpick(); readNow(); flush();
  if (S.rec) S.rec.r.stop();
  S.picking = false;
  S.shown = false; if (S.el) S.el.hidden = true;
  place();
  if (Pens.surface() === surface) Pens.use(S.prev && S.prev.live && S.prev.live() ? S.prev : null);
  if (!keep && S.ctx) store.set(openKey(), false);
  buttons(); relayout();
}
function toggle(){ if (S.shown) hide(); else show(); }
// The side panel's tabs: the Notebook, then a reader's own Info and Ask (it hands them over as
// ctx.panel: {open(tab), close(), shown()}). One is open at a time; the bar's one button opens the last.
const PTABS = [['notebook', 'Notebook'], ['info', 'Info'], ['ask', 'Ask']];
function panelTab(t){
  const p = S.ctx && S.ctx.panel;
  if (t === 'notebook' || !p) { show(); return; }
  if (S.shown) hide();
  p.open(t); store.set('ptab', t); buttons();
}
function togglePanel(){
  const p = S.ctx && S.ctx.panel;
  if (!p) { toggle(); return; }
  if (S.shown) hide();
  else if (p.shown()) { p.close(); buttons(); }
  else panelTab(store.get('ptab', 'notebook'));
}
// a reader opened or closed its Info or Ask by itself (its ⋯, a key): the Notebook makes way, the button follows
function panelChanged(t){
  const p = S.ctx && S.ctx.panel;
  if (p && p.shown()) { if (S.shown) hide(); if (t) store.set('ptab', t); }
  buttons();
}
// Room kept on the right for something else beside the reader (Side by side, study.js), as the
// Notebook's own is: the readers lay out in what's left (room()).
function reserve(px){ S.extra = Math.max(0, Math.round(px || 0)); place(); relayout(); }
function buttons(){
  const on = S.shown || !!(S.ctx && S.ctx.panel && S.ctx.panel.shown());
  document.querySelectorAll('[data-sketch]').forEach(b => { b.setAttribute('aria-pressed', String(on)); b.classList.toggle('on', on); });
}
// A reader opened something: the Notebook is for that now, and comes up if it was up last time.
// ctx: {item, kind (book | doc | pdf | manga), here() (where you are: {tab, title, pos}), view (a book's
// foliate view), shots() (what the camera can take), time() and seek(t) (a video's), resized(),
// highlights() (its highlights, for the cards: see loadHls) and go(highlight) (to one, in the reader)}.
function attach(ctx){
  if (!ctx || !ctx.item) return;
  stopEditing(); unpick(); readNow(); flush();
  if (S.off) { S.off(); S.off = null; }
  const same = S.ctx && S.ctx.item === ctx.item;
  S.ctx = ctx;
  const s = Pens.surface(); if (s && s !== surface) S.prev = s;
  if (!same) { S.tabs = []; S.pages = new Map(); S.vault = null; S.hls = []; S.all = null; S.chs = null; S.lq = ''; S.picking = false; }
  S.done = []; S.undone = []; S.follow = true;
  S.here = ctx.here ? ctx.here() : null;
  S.tab = S.here ? S.here.tab : ''; S.meta = S.here || {};
  if (ctx.view) {
    const on = e => relocated(e.detail), loaded = e => watchDoc(e.detail && e.detail.doc);
    ctx.view.addEventListener('relocate', on); ctx.view.addEventListener('load', loaded);
    try { for (const c of ctx.view.renderer.getContents()) watchDoc(c.doc); } catch(e){}
    S.off = () => { ctx.view.removeEventListener('relocate', on); ctx.view.removeEventListener('load', loaded); };
  }
  if (store.get(openKey(), false)) { if (S.shown) { place(); show1(S.tab, S.meta); Pens.use(surface); drawTools(); relayout(); loadHls(); if (S.view === 'list') loadAll(); } else show(); }
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
// A book's and an article's is the side panel's (the Notebook, Info and Ask); a PDF's and manga's, the Notebook's.
function button(kind){
  const side = !kind, label = side ? 'Side panel' : 'Notebook', on = S.shown || !!(side && S.ctx && S.ctx.panel && S.ctx.panel.shown());
  const cls = kind === 'manga' ? 'mic' : 'ib';
  return '<button class="' + cls + (on ? ' on' : '') + '" data-sketch aria-pressed="' + on + '" title="' + label + '" aria-label="' + label + '">' + (side ? IC.panel : IC.book) + '</button>';
}
document.addEventListener('click', e => { const b = e.target.closest && e.target.closest('[data-sketch]'); if (!b) return; e.preventDefault(); togglePanel(); });
// Gone from the readers (a list, Today): it goes, and comes back with the next one opened.
const watchView = () => new MutationObserver(() => { if (S.ctx && !READING.includes(document.body.dataset.view)) detach(); }).observe(document.body, { attributes: true, attributeFilter: ['data-view'] });
if (document.body) watchView(); else document.addEventListener('DOMContentLoaded', watchView);
window.addEventListener('resize', () => { if (!S.shown) return; const was = S.mode; place(); if (was !== S.mode) { drawTools(); relayout(); } later(); });
window.addEventListener('daf-theme', () => { theme(); later(); });
document.addEventListener('visibilitychange', () => { if (document.visibilityState === 'hidden') { readNow(); flush(); } else if (S.shown && S.ctx) load(S.tab); });
window.addEventListener('pagehide', flush);
window.addEventListener('online', () => { if (S.shown && S.ctx) setTimeout(() => load(S.tab), 3000); });

C.Sketch = { attach, detach, button, toggle, togglePanel, tab: panelTab, panelChanged, show, hide, room, reserve, open: () => S.shown, flush, reveal, hlChanged,
  list: () => reveal({ view: 'list' }),
  state: () => ({ shown: S.shown, mode: S.mode, view: S.view, item: S.ctx && S.ctx.item, tab: S.tab, here: S.here, tabs: tabList().map(t => t.tab),
    cards: cardsHere().map(h => h.id), groups: S.groups.map(g => (g.card ? 'card' : g.id ? 'gone' : 'top') + ':' + g.blocks.length), hls: S.hls.length,
    blocks: blocksOf(cur()).map(b => b.kind + (b.type ? ':' + b.type : '') + ':' + strokesOf(cur(), b.id).length + (b.transcript ? ':' + b.transcript : '')),
    editing: !!S.editing, picked: S.picked, queued: S.q ? S.q.add.size + S.q.remove.size : 0, done: S.done.length, surface: Pens.surface() === surface }) };
})();
