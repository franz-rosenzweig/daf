/* Daf book reader: EPUB (and MOBI/AZW3/FB2) from Calibre, rendered by foliate-js, inside
   Daf's reading view. Contents, bookmarks and search on the left, Info / Ask on the right, the
   Notebook beside it (sketchbook.js, its highlights on its pages), highlights anchored by CFI, the Kindle's highlights placed by KOReader's own position,
   the position kept on the server so phone and desktop agree, and time with a book open counting
   toward the hour. */
import { makeBook } from './vendor/foliate-js/view.js';
import * as CFI from './vendor/foliate-js/epubcfi.js';
import { FootnoteHandler } from './vendor/foliate-js/footnotes.js';

const C = window.DafCore, { api, esc, toast, $, $$, I, epochDate } = C, H = C.HL;
const store = { get(k, d){ try { const v = localStorage.getItem('daf.' + k); return v == null ? d : JSON.parse(v); } catch(e){ return d; } }, set(k, v){ try { localStorage.setItem('daf.' + k, JSON.stringify(v)); } catch(e){} } };
const B = { id: null, d: null, view: null, loc: null, byCfi: new Map(), kindleByCfi: new Map(), panel: 'info', panelOpen: store.get('bookPanel', true), tocOpen: store.get('bookToc', true),
  sel: null, lastActive: Date.now(), saveT: null, searching: false, chrome: true, opened: 0, flash: null, temp: new Set(), touch: false };
const isRtlText = t => /[֐-׿]/.test(t || '');
const ICON = {
  toc: '<svg width="18" height="18" viewBox="0 0 20 20" aria-hidden="true"><path d="M4 5.5h12M4 10h12M4 14.5h8" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/></svg>',
  panel: '<svg width="18" height="18" viewBox="0 0 20 20" aria-hidden="true"><rect x="3" y="4" width="14" height="12" rx="2.5" fill="none" stroke="currentColor" stroke-width="1.6"/><path d="M12.5 4v12" stroke="currentColor" stroke-width="1.6"/></svg>',
  search: '<svg width="16" height="16" viewBox="0 0 20 20" aria-hidden="true"><circle cx="8.5" cy="8.5" r="5" fill="none" stroke="currentColor" stroke-width="1.8"/><path d="M12.5 12.5l4 4" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>',
  more: '<svg width="18" height="18" viewBox="0 0 20 20" aria-hidden="true"><circle cx="5" cy="10" r="1.5" fill="currentColor"/><circle cx="10" cy="10" r="1.5" fill="currentColor"/><circle cx="15" cy="10" r="1.5" fill="currentColor"/></svg>',
  mark: on => '<svg width="18" height="18" viewBox="0 0 20 20" aria-hidden="true"><path d="M6 3.5h8v13l-4-3-4 3z" fill="' + (on ? 'currentColor' : 'none') + '" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/></svg>',
  menu: '<svg width="18" height="18" viewBox="0 0 20 20" aria-hidden="true"><path d="M4 6h12M4 10h12M4 14h12" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>',
  x: '<svg width="16" height="16" viewBox="0 0 20 20" aria-hidden="true"><path d="M5 5l10 10M15 5 5 15" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>',
  pen: '<svg width="18" height="18" viewBox="0 0 20 20" aria-hidden="true"><path d="M12.5 4.5l3 3L8 15H5v-3z" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/></svg>',
  listen: '<svg width="18" height="18" viewBox="0 0 20 20" aria-hidden="true"><path d="M4 13.5v-3a6 6 0 0 1 12 0v3" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/><rect x="3" y="12" width="3.5" height="5" rx="1.2" fill="none" stroke="currentColor" stroke-width="1.6"/><rect x="13.5" y="12" width="3.5" height="5" rx="1.2" fill="none" stroke="currentColor" stroke-width="1.6"/></svg>',
  ask: '<svg width="18" height="18" viewBox="0 0 20 20" aria-hidden="true"><path d="M4 5h12v8H9l-3.5 3v-3H4z" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/></svg>',
  focus: '<svg width="18" height="18" viewBox="0 0 20 20" aria-hidden="true"><path d="M4 8V4h4M16 8V4h-4M4 12v4h4M16 12v4h-4" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg>',
};
// The room the book has: the window, less the Sketchbook beside it or under it (sketchbook.js).
// what's left for the page: less the Notebook (or Side by side) on the right (the margin, study.js, only
// makes it one page at a time: applyBookType)
const room = () => C.Sketch ? C.Sketch.room() : { w: window.innerWidth, h: window.innerHeight };
const fmtMins = m => { m = Math.max(0, Math.round(m || 0)); return m >= 60 ? Math.floor(m / 60) + ' h ' + (m % 60) + ' min' : m + ' min'; };
const xpIndex = xp => { const m = /DocFragment\[(\d+)\]/.exec(xp || ''); return m ? +m[1] - 1 : null; };

/* ---------- typography inside the book ---------- */
const FONTS = {
  serif: "'Source Serif 4', 'Frank Ruhl Libre', Georgia, serif",
  literata: "'Literata', 'Frank Ruhl Libre', Georgia, serif",
  frank: "'Frank Ruhl Libre', 'Source Serif 4', Georgia, serif",
  atkinson: "'Atkinson Hyperlegible', 'Figtree', system-ui, sans-serif",
  sans: "'Figtree', system-ui, -apple-system, sans-serif",
  book: null,
};
// Every typeface Daf has (themes.js), your own too; the book's pages load Daf's copies of them.
const fontFor = id => id === 'book' ? null : C.Themes ? C.Themes.stack(id) : FONTS[id] || FONTS.serif;
const fontCSS = () => "@import url('" + location.origin + "/fonts/fonts.css');\n" + (C.Themes ? C.Themes.userFontCSS(true) : '');
function bookCSS(){
  const t = C.typeFor ? C.typeFor(B.id) : store.get('type', {}), cs = getComputedStyle(document.documentElement);
  const v = n => cs.getPropertyValue(n).trim();
  const font = fontFor(t.font || 'serif');
  const size = t.size || 20, lh = t.spacing || 1.6;
  const dark = H.isDark();
  return [fontCSS(), `
    html { color: ${v('--read-fg') || v('--fg')} !important; background: ${v('--bg')} !important; color-scheme: ${dark ? 'dark' : 'light'}; font-size: ${size}px !important; }
    body { color: inherit !important; background: transparent !important; font-size: 1rem !important; }
    ${font ? `body, p, li, blockquote, dd, dt, div, span, td, th, h1, h2, h3, h4, h5, h6, a, em, i, b, strong, cite { font-family: ${font} !important; }` : ''}
    p, li, blockquote, dd { line-height: ${lh} !important; text-align: ${t.justify ? 'justify' : 'start'}; hyphens: auto; -webkit-hyphens: auto; widows: 2; orphans: 2; }
    a:link, a:visited { color: ${v('--accent')} !important; }
    ${dark ? 'img, svg { filter: brightness(.9); } * { border-color: ' + v('--line-2') + ' !important; }' : ''}
    pre { white-space: pre-wrap !important; }
    ::selection { background: ${v('--hl-yellow')}; }
    .daf-speaking { background: ${v('--speak')} !important; border-radius: 4px; box-shadow: 0 0 0 4px ${v('--speak')}; }
    ::highlight(daf-speaking) { background-color: ${v('--speak-line')}; }
    ${H.hlCSS()}
    aside[epub|type~="footnote"], aside[epub|type~="endnote"], aside[epub|type~="rearnote"] { display: none; }
    ${(t.flow || 'paginated') === 'scrolled' ? 'body { padding-bottom: 72px !important; }   /* room under the last line for Next */' : ''}
    ${B.scans ? B.scans.css() : ''}
    @namespace epub "http://www.idpf.org/2007/ops";
  `];
}
function applyBookType(){
  const v = B.view; if (!v || !v.renderer) return;
  const t = C.typeFor ? C.typeFor(B.id) : store.get('type', {});
  const flow = t.flow || 'paginated';  // pages, as Apple Books has them; Aa → Scroll for one long column
  v.renderer.setAttribute('flow', flow);
  v.renderer.setAttribute('max-inline-size', Math.round((t.measure || 38) * 16 * ((t.size || 20) / 20)) + 'px');
  v.renderer.setAttribute('max-column-count', flow === 'paginated' && room().w >= 1180 && room().w > room().h && !(C.Margin && C.Margin.active()) ? '2' : '1');   // two pages, as a book opens
  v.renderer.setAttribute('gap', '6%');
  v.renderer.setAttribute('margin', room().w < 760 ? '24px' : '40px');
  if (B.scans) B.scans.layout();   // a book of scanned pages: a page a picture, as big as fits (scans.js)
  v.renderer.setStyles?.(bookCSS());
  document.body.dataset.flow = flow;
}
window.addEventListener('daf-type', () => { applyBookType(); setTimeout(redrawAll, 120); });

/* ---------- open ---------- */
async function openBook(id, at){
  cleanup();
  B.id = id; B.loc = null; B.forget = false; B.pageKey = null; B.pagesNew = new Set(); B.byCfi = new Map(); B.kindleByCfi = new Map(); B.sel = null; B.opened = Date.now(); B.offeredNext = false; B.offeredEnd = false; B.temp = new Set();
  H.active = ACT;
  wake(true);
  document.body.dataset.view = 'ebook';
  $('#main').innerHTML = '<div class="progress"><i id="rprog"></i></div><div class="rv ebook"><div class="top" id="btop"><a class="ib" href="#books" aria-label="Back">' + I.back + '</a></div>' +
    '<div class="rvgrid notoc" id="bgrid"><nav class="toc btoc" id="btoc" aria-label="Contents"></nav>' +
    '<div class="docwrap bookwrap"><div id="bnotice"></div><div class="bookstage" id="bstage"><div class="bookload mute">Opening the book…</div></div><div class="bookfoot" id="bfoot"></div>' +
    '<div class="bctl" id="bctl"><input type="range" id="bslide" min="0" max="1000" value="0" aria-label="Where you are in the book"><div class="bctlrow"><span id="bslidet" class="mute"></span>' +
    '<button class="round bmenu" data-bk="pmenu" aria-label="Reading menu">' + ICON.menu + '</button></div></div></div>' +
    '<aside class="rpanel" id="bpanel"></aside></div><div class="bscrim" data-bk="closesheets"></div></div>';
  // the bar's own height (a theme's frame makes it a little more than 56 px): the page and its status
  // bar fit under it, with or without the Sketchbook below
  if (window.ResizeObserver) { if (B.topObs) B.topObs.disconnect(); B.topObs = new ResizeObserver(() => { const t = $('#btop'); if (t && t.offsetHeight) document.documentElement.style.setProperty('--btop', t.offsetHeight + 'px'); }); B.topObs.observe($('#btop')); }
  // The file starts coming at once, beside the book's details: from the device when it's been
  // opened before (sw.js), else from Daf.
  const fileUrl = '/api/ebooks/' + encodeURIComponent(id) + '/file', fileStop = new AbortController();
  const fileP = fetch(fileUrl, { credentials: 'same-origin', signal: fileStop.signal });
  fileP.catch(() => {});
  let d;
  try { d = await api('/api/ebooks/' + encodeURIComponent(id)); }
  catch(e){ $('#bstage').innerHTML = '<div class="placeholder">' + esc(e.message) + ' <a href="#book/' + encodeURIComponent(id) + '">Back to the book</a></div>'; return; }
  if (B.id !== id) return;
  // A book Calibre has only as a PDF: its pages as printed, in the PDF view (pdfview.js)
  if (d.format === 'PDF') { fileStop.abort(); location.replace('#pdf/book/' + encodeURIComponent(id) + (at && at.startsWith('hl:') ? '/' + at : '')); return; }
  B.d = d;
  if (C.Sound) C.Sound.open(id);
  inkLoad(d);
  d.highlights.forEach(h => { h.source = 'epub'; B.byCfi.set(h.pos.cfi, h); });
  d.other_highlights.forEach(h => { h.sec = xpIndex(h.xp); });
  drawTop(); drawPanel();
  let file;
  try {
    let r = await fileP;
    if (!r.ok) throw new Error('The file didn’t come (' + r.status + ')');
    let blob = await r.blob();
    // The copy kept here is a different size from Calibre's: the book changed, so it comes again.
    if (d.size && blob.size !== d.size && navigator.onLine) {
      const again = await fetch(fileUrl, { credentials: 'same-origin', cache: 'reload' }).catch(() => null);
      if (again && again.ok) blob = await again.blob();
    }
    file = new File([blob], 'book.' + (d.format === 'KEPUB' ? 'epub' : (d.format || 'epub').toLowerCase()), { type: blob.type });
  } catch(e){ $('#bstage').innerHTML = '<div class="placeholder">' + esc(e.message) + '</div>'; return; }
  if (B.id !== id) return;
  const view = document.createElement('foliate-view');
  view.id = 'fv';
  $('#bstage').innerHTML = ''; $('#bstage').append(view);
  B.view = view;
  // a book of scanned pages is found before foliate opens it: its progress goes a page at a time (scans.js)
  try { const book = await makeBook(file), scans = C.Scans && await C.Scans.detect(book, id); if (B.id === id) B.scans = scans; await view.open(book); }
  catch(e){ $('#bstage').innerHTML = '<div class="placeholder">This file wouldn’t open: ' + esc(e.message || String(e)) + '</div>'; return; }
  if (B.id !== id) { view.close?.(); return; }
  if (B.scans) B.scans.attach(view);
  view.addEventListener('load', onSectionLoad);
  view.addEventListener('relocate', onRelocate);
  view.renderer.addEventListener('relocate', e => alongMoved(e.detail.reason));
  C.PageTurn && C.PageTurn.attach(view);    // Aa → Page turn: None, Slide or Curl (pageturn.js)
  view.addEventListener('create-overlay', e => {
    const { index } = e.detail;
    for (const h of d.highlights) if (h.index === index) view.addAnnotation({ value: h.pos.cfi });
    markKindle(index);
    inkSection(index);
    if (C.Margin) C.Margin.draw();
  });
  view.addEventListener('draw-annotation', e => {
    const { draw, annotation, range } = e.detail, v = annotation.value;
    if (INK.by.has(v)) { draw(inkDraw, { cfi: v, range }); return; }
    const h = B.kindleByCfi.get(v) || B.byCfi.get(v);
    const o = { range, color: (h && h.color) || 'yellow', note: !!(h && (h.user_note || h.note)), flash: B.flash === v, soft: !h && B.temp.has(v) };
    o.under = underWords(v, range, H.hlName(o.color, o));
    draw(H.draw, o);
  });
  // A highlight taken away (or drawn again in another colour) takes its colour from under the words too.
  const deleteAnnotation = view.deleteAnnotation.bind(view);
  view.deleteAnnotation = a => { offWords(a && a.value); return deleteAnnotation(a); };
  view.addEventListener('show-annotation', e => {
    const v = e.detail.value, k = B.kindleByCfi.get(v), h = k || B.byCfi.get(v); if (!h) return;
    const doc = e.detail.range.startContainer.ownerDocument;
    if (doc.getSelection && !doc.getSelection().isCollapsed) return;   // a new selection over it wins
    H.show(H.hlBar(h, { kindle: !!k }), rectFor(doc, e.detail.range), { h, cfi: v, kindle: !!k });
  });
  view.addEventListener('external-link', e => { e.preventDefault(); window.open(e.detail.href_, '_blank', 'noopener'); });
  view.addEventListener('link', e => footnotes.handle(view.book, e)?.catch(err => console.warn('footnote', err)));
  for (const h of d.highlights) { try { h.index = view.resolveNavigation(h.pos.cfi)?.index; } catch(err){ h.index = null; } }
  try { B.secFrac = view.getSectionFractions(); } catch(e){ B.secFrac = []; }
  try { B.marks = chapterMarks(); } catch(e){ B.marks = []; }
  applyBookType();
  drawToc();
  Pens.use(INKSURF);
  TOCAT.clear(); SECDOC.clear();
  if (C.Sketch) C.Sketch.attach({ item: 'book:' + id, kind: 'book', view, panel: { open: t => openPanel(t), close: closePanel, shown: panelShown }, resized: () => { applyBookType(); if (C.Margin) C.Margin.draw(); }, highlights: notebookHls, go: jumpTo });   // the Notebook beside it (sketchbook.js)
  if (C.Margin) C.Margin.attach({ item: 'book:' + id, host: () => B.id === id ? $('#bstage') : null, places: marginPlaces, open: marginOpen, relayout: applyBookType, ok: () => !B.scans,
    pageW: () => (parseFloat(B.view && B.view.renderer.getAttribute('max-inline-size')) || 600) * 1.12 + 72 });   // the margin (study.js)
  // Where to start: a highlight we were sent to, else the newest of here / this device / the Kindle.
  const local = store.get('bookpos.' + id, null);
  const server = d.position;
  const mine = [server, local].filter(Boolean).sort((a, b) => (b.updated || b.at || 0) - (a.updated || a.at || 0))[0];
  const target = at && at.startsWith('hl:') ? findHl(at.slice(3)) : null;
  // q:<words>: a passage found by its words (the Recovery page's readings and prayers).
  const words = at && at.startsWith('q:') ? decodeURIComponent(at.slice(2)) : null;
  const first = target ? (target.pos && target.pos.cfi) || (target.sec != null && view.book.sections[target.sec] ? target.sec : null) : words ? null : at;
  try {
    if (first != null) await view.init({ lastLocation: first });
    else if (mine && mine.cfi) await view.init({ lastLocation: mine.cfi });
    else await view.init({ showTextStart: true });
  } catch(e){ await view.init({ showTextStart: true }).catch(() => {}); }
  if (target) await jumpTo(target);
  else if (at && at.startsWith('hl:')) toast('That highlight isn’t in this book any more');
  else if (words) await goToWords(words);
  if (!at && mine && (mine.fraction || 0) > 0.01) toast('Picked up at ' + Math.round(mine.fraction * 100) + '%' + (mine.chapter ? ' · ' + mine.chapter : ''));
  if (!at) offerKindle(mine);
  window.dispatchEvent(new CustomEvent('daf-book-open', { detail: { id, mine, at } }));   // its audiobook, and the audiobook's place (audiobooks.js)
  if (PHONE()) setTimeout(hideChrome, 600);
}
// The highlights' colours under the words: one CSS highlight per colour in each chapter's page. False where the browser
// has no CSS highlights (H.draw then paints the colour over the words, as before).
const UNDER = new Map(); // annotation → { set, range }
function underWords(v, range, name){
  offWords(v);
  const win = range && range.startContainer && range.startContainer.ownerDocument.defaultView;
  const reg = win && win.CSS && win.CSS.highlights; if (!reg || !win.Highlight) return false;
  let set = reg.get(name); if (!set) { set = new win.Highlight(); reg.set(name, set); }
  set.add(range); UNDER.set(v, { set, range });
  return true;
}
function offWords(v){ const u = UNDER.get(v); if (u) { u.set.delete(u.range); UNDER.delete(v); } }
function findHl(id){ return B.d && (B.d.highlights.find(h => h.id === id) || B.d.other_highlights.find(h => h.id === id)); }

/* ---------- where a highlight is, and going there ---------- */
const squash = t => (t || '').toLowerCase().replace(/[\s­]+/g, ' ').replace(/[“”"‘’']/g, "'").trim();
function textIndex(doc){
  // The section's text, whitespace-squashed and lower-cased, with a map back to (node, offset).
  if (doc.__dafIdx) return doc.__dafIdx;
  const walker = doc.createTreeWalker(doc.body, NodeFilter.SHOW_TEXT);
  let text = '', map = [], node, space = true; const start = new Map();
  while ((node = walker.nextNode())) {
    const v = node.nodeValue;
    for (let i = 0; i < v.length; i++) {
      let ch = v[i];
      if (/[\s­]/.test(ch)) { if (space) continue; ch = ' '; space = true; } else space = false;
      if ('“”"‘’'.includes(ch)) ch = "'";
      if (!start.has(node)) start.set(node, map.length);
      text += ch.toLowerCase(); map.push([node, i]);
    }
  }
  return (doc.__dafIdx = { text, map, start });
}
// KOReader's xpointer, e.g. /body/DocFragment[46]/body/div[2]/p[5]/text().174: follow the elements.
function xpElement(doc, xp){
  const m = /DocFragment\[\d+\](\/.*)$/.exec(xp || ''); if (!m) return null;
  let node = doc.documentElement;
  for (const st of m[1].replace(/\.\d+$/, '').split('/').filter(Boolean)) {
    const sm = /^([A-Za-z][\w:.-]*)(?:\[(\d+)\])?$/.exec(st); if (!sm) break;
    const next = [...node.children].filter(c => c.localName.toLowerCase() === sm[1].toLowerCase())[(+sm[2] || 1) - 1];
    if (!next) break; node = next;
  }
  return node === doc.documentElement ? null : node;
}
function indexIn(idx, doc, el){
  const w = doc.createTreeWalker(el, NodeFilter.SHOW_TEXT); let n;
  while ((n = w.nextNode())) if (idx.start.has(n)) return idx.start.get(n);
  return null;
}
// A range for these words in one section, starting the search at `from` if we know roughly where.
function placeText(doc, text, from){
  const idx = textIndex(doc), words = squash(text).split(' ').filter(Boolean); if (!words.length) return null;
  const head = words.slice(0, Math.min(8, words.length)).join(' '), tail = words.slice(-6).join(' ');
  let a = from != null ? idx.text.indexOf(head, Math.max(0, from - 40)) : -1;
  if (a < 0 || (from != null && a - from > 6000)) a = idx.text.indexOf(head);
  if (a < 0) return null;
  let b = words.length <= 8 ? a + head.length : idx.text.indexOf(tail, a);
  if (b < 0 || b - a > text.length * 2 + 200) b = a + Math.min(text.length, head.length); else if (words.length > 8) b += tail.length;
  const s = idx.map[a], e = idx.map[Math.min(b, idx.map.length) - 1]; if (!s || !e) return null;
  const r = doc.createRange(); r.setStart(s[0], s[1]); r.setEnd(e[0], e[1] + 1);
  return r;
}
// The Kindle's highlights, drawn like Daf's own wherever this edition has the same words.
function markKindle(index){
  const list = (B.d && B.d.other_highlights || []).filter(h => h.text && h.text.length > 3 && !h.cfi && (h.source === 'kindle' ? (h.sec === index || h.sec == null || h.miss) : false));
  if (!list.length || !B.view) return;
  const c = B.view.renderer.getContents().find(x => x.index === index); if (!c) return;
  for (const h of list) {
    let from = null;
    if (h.sec === index && h.xp) { const el = xpElement(c.doc, h.xp); if (el) from = indexIn(textIndex(c.doc), c.doc, el); }
    const r = placeText(c.doc, h.text, from);
    if (!r) { if (h.sec === index) h.miss = true; continue; }
    try {
      const cfi = B.view.getCFI(index, r);
      h.cfi = cfi; h.index = index; B.kindleByCfi.set(cfi, h);
      B.view.addAnnotation({ value: cfi });
    } catch(err){}
  }
}
async function goToWords(words){
  const cfi = await findText(words);
  if (cfi) { await B.view.goTo(cfi).catch(() => {}); centerIt(); } else toast('That passage isn’t in this copy');
}
async function findText(text){
  const words = (text || '').replace(/\s+/g, ' ').trim().split(' '), mid = Math.floor(words.length / 2);
  const tries = [words.slice(0, 7), words.slice(Math.max(0, mid - 3), mid + 4), words.slice(-7)].map(w => w.join(' ')).filter((q, i, a) => q.length > 10 && a.indexOf(q) === i);
  try {
    for (const q of tries) {
      for await (const r of B.view.search({ query: q })) {
        if (r === 'done') break;
        const cfi = r.subitems ? r.subitems[0]?.cfi : r.cfi;
        if (cfi) { B.view.clearSearch(); return cfi; }
      }
    }
  } catch(e){}
  B.view.clearSearch();
  return null;
}
function centerIt(){ if (document.body.dataset.flow === 'scrolled') { try { B.view.renderer.scrollBy(-Math.round(window.innerHeight * 0.28), 0); } catch(e){} } }
async function flashCfi(cfi, temp){
  if (temp) B.temp.add(cfi);
  B.flash = cfi; await B.view.addAnnotation({ value: cfi }).catch(() => {});
  setTimeout(async () => { if (B.flash === cfi) B.flash = null; if (temp) { B.temp.delete(cfi); B.view && B.view.deleteAnnotation({ value: cfi }).catch(() => {}); } else B.view && B.view.addAnnotation({ value: cfi }).catch(() => {}); }, 1900);
}
async function jumpTo(h){
  if (!B.view) return;
  H.hide(); document.body.classList.remove('bpanelsheet', 'btocsheet');
  if (h.pos && h.pos.cfi) { await B.view.goTo(h.pos.cfi).catch(() => {}); centerIt(); flashCfi(h.pos.cfi); return; }
  if (h.source === 'kindle') {
    if (!h.cfi && h.sec != null && B.view.book.sections[h.sec]) { await B.view.goTo(h.sec).catch(() => {}); }
    if (!h.cfi) { const cfi = await findText(h.text); if (cfi) { h.miss = true; await B.view.goTo(cfi).catch(() => {}); } }
    if (h.cfi) { await B.view.goTo(h.cfi).catch(() => {}); centerIt(); flashCfi(h.cfi); return; }
  } else {
    // Audiobook bookmarks and paper pages: find their words in the book.
    toast('Finding it in the book…');
    const cfi = await findText(h.text);
    if (cfi) {
      await B.view.goTo(cfi).catch(() => {});
      const c = B.view.renderer.getContents().find(x => x.index === B.view.resolveNavigation(cfi)?.index);
      const r = c && placeText(c.doc, h.text, null);
      let full = cfi; try { if (r) full = B.view.getCFI(c.index, r); } catch(e){}
      centerIt(); flashCfi(full, true); $('#toast').hidden = true; return;
    }
  }
  const k = B.d.kindle;
  if (h.page && k && k.total) { await B.view.goToFraction(Math.min(1, h.page / k.total)); toast('The exact words aren’t in this edition. This is about where page ' + h.page + ' falls.'); }
  else toast('Couldn’t find that passage in this edition');
}
function redrawAll(){
  if (!B.view || !B.view.renderer) return;   // (the look can change before the book has opened)
  const loaded = new Set(B.view.renderer.getContents().map(c => c.index));
  for (const h of B.d ? B.d.highlights : []) if (loaded.has(h.index)) B.view.addAnnotation({ value: h.pos.cfi }).catch(() => {});
  for (const [cfi, h] of B.kindleByCfi) if (loaded.has(h.index)) B.view.addAnnotation({ value: cfi }).catch(() => {});
  for (const i of loaded) inkSection(i);
}

/* ---------- footnotes: shown in a popover by the link, not by jumping away ---------- */
const footnotes = new FootnoteHandler();
footnotes.addEventListener('before-render', e => {
  const { view } = e.detail;
  view.addEventListener('link', ev => { ev.preventDefault(); const href = ev.detail.href; closeNote(); B.view.goTo(href).catch(() => {}); });
  view.renderer.setAttribute('flow', 'scrolled');
  view.renderer.setAttribute('margin', '0px');
  view.renderer.setAttribute('gap', '5%');
  view.renderer.setStyles?.(bookCSS());
  const box = $('#fnote') || Object.assign(document.createElement('div'), { id: 'fnote', className: 'fnote' });
  box.innerHTML = '<div class="fnh"><span class="mute tiny" id="fnkind">Note</span><button class="ib" data-bk="closenote" aria-label="Close">×</button></div>';
  box.append(view); box.hidden = true; document.body.append(box);
});
footnotes.addEventListener('render', e => {
  const { type } = e.detail, box = $('#fnote'); if (!box) return;
  $('#fnkind').textContent = { footnote: 'Footnote', endnote: 'Endnote', biblioentry: 'Reference', definition: 'Definition' }[type] || 'Note';
  box.hidden = false;
  const a = B.lastLink; let x = window.innerWidth / 2, y = window.innerHeight / 3;
  if (a) { const r = rectFor(a.ownerDocument, (() => { const rg = a.ownerDocument.createRange(); rg.selectNode(a); return rg; })()); x = r.left; y = r.bottom; }
  const w = Math.min(420, window.innerWidth - 24);
  box.style.width = w + 'px';
  box.style.left = Math.max(12, Math.min(window.innerWidth - w - 12, x - w / 2)) + 'px';
  box.style.top = (y + 260 < window.innerHeight ? y + 10 : Math.max(12, y - 280)) + 'px';
});
function closeNote(){ const b = $('#fnote'); if (b) b.remove(); }

/* ---------- keep the screen awake while a book is open ---------- */
async function wake(on){
  try {
    if (on && 'wakeLock' in navigator && !document.hidden) { B.lock = await navigator.wakeLock.request('screen'); }
    else if (!on && B.lock) { await B.lock.release(); B.lock = null; }
  } catch(e){}
}
document.addEventListener('visibilitychange', () => { if (!document.hidden && B.view) wake(true); });

/* ---------- Listen: Kokoro reads the book a paragraph at a time ---------- */
// It shows in Daf's player (player.js) and reads on when you leave the book: its paragraphs are kept,
// and the next chapter comes from the book itself (T.book), not the page on screen. Back in the same
// book, the paragraph it's reading is marked again; the player's Go to it opens the book there.
B.tts = { on: false, playing: false, els: [], i: 0, audio: null, rate: 1, sleepAt: 0, index: null };
const BLOCKS = 'p, li, blockquote, h1, h2, h3, h4, h5, h6, dd, dt, figcaption, pre';
function paragraphs(doc){
  return [...doc.body.querySelectorAll(BLOCKS)].filter(el => !el.querySelector(BLOCKS) && el.textContent.trim().length > 1 && !el.closest('aside'));
}
async function speech(text){
  const r = await fetch('/api/tts/text', { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(C.Voices.cur ? { text, voice: C.Voices.cur } : { text }) });
  if (!r.ok) throw new Error('Kokoro didn’t answer');
  return URL.createObjectURL(await r.blob());
}
async function startListen(){
  const T = B.tts, c = B.view && B.view.renderer.getContents()[0]; if (!c) return;
  const els = paragraphs(c.doc); if (!els.length) { toast('Nothing to read on this page'); return; }
  let start = 0; const vis = B.loc && B.loc.range;
  if (vis) { const k = els.findIndex(el => { try { return vis.intersectsNode(el); } catch(e){ return false; } }); if (k >= 0) start = k; }
  Object.assign(T, { on: true, playing: true, els, i: start, index: c.index, bookId: B.id, book: B.view.book, title: (B.d && B.d.title) || 'Book',
    art: B.d && B.d.has_cover ? '/api/cover/' + encodeURIComponent(B.id) : '' });
  if (!C.Voices.cur) C.Voices.load().then(() => { if (T.on) drawPlayer(); });
  drawPlayer(); playPara();
}
// Another voice chosen while it reads: the paragraph starts again in it.
window.addEventListener('daf-voice', () => { const T = B.tts; T.cache = null; if (T.on) playPara(); });
const here = () => B.view && B.id === B.tts.bookId;      // the book being read aloud is the one on screen
// A paragraph on the page now (a chapter read from the book itself, or a page that's gone, has no window).
const onPage = el => !!(el && el.isConnected && el.ownerDocument.defaultView);
async function playPara(){
  const T = B.tts; if (!T.on) return;
  if (T.sleepAt && Date.now() > T.sleepAt) { stopListen(); toast('Sleep timer: stopped reading'); return; }
  if (T.i >= T.els.length) {             // end of the section: on to the next one
    const next = (T.index ?? 0) + 1;
    if (!T.book.sections[next]) { stopListen(); return; }
    if (here()) {
      await B.view.goTo(next).catch(() => {});
      const c = B.view.renderer.getContents()[0]; if (!c) { stopListen(); return; }
      T.els = paragraphs(c.doc); T.index = c.index;
    } else {                              // away from the book: the chapter from the book itself
      const doc = await Promise.resolve(T.book.sections[next].createDocument()).catch(() => null);
      T.els = doc && doc.body ? paragraphs(doc) : []; T.index = next;
    }
    T.i = 0;
    if (!T.els.length) { T.i = 0; T.els = []; return playPara(); }
  }
  const el = T.els[T.i];
  T.els.forEach(x => x.classList.remove('daf-speaking')); el.classList.add('daf-speaking');
  if (here() && onPage(el)) { try { const rg = el.ownerDocument.createRange(); rg.selectNodeContents(el); B.view.renderer.scrollToAnchor?.(rg); } catch(e){} }
  B.lastActive = Date.now();
  try {
    const url = T.cache && T.cache.i === T.i && T.cache.index === T.index ? T.cache.url : await speech(el.textContent.replace(/\s+/g, ' ').trim());
    if (!T.on) return;
    if (T.audio) T.audio.pause();
    T.audio = new Audio(url); T.audio.playbackRate = T.rate;
    if (T.unfollow) T.unfollow();
    T.unfollow = here() && onPage(el) ? H.follow(T.audio, el) : null;
    T.audio.onended = () => { T.i++; playPara(); };
    T.audio.onerror = () => { T.i++; playPara(); };
    if (T.playing) await T.audio.play();
    const nx = T.els[T.i + 1];                // fetch the next paragraph while this one plays
    if (nx) speech(nx.textContent.replace(/\s+/g, ' ').trim()).then(u => { T.cache = { i: T.i + 1, index: T.index, url: u }; }).catch(() => {});
  } catch(e){ toast(e.message); stopListen(); }
  drawPlayer();
}
function stopListen(){
  const T = B.tts; T.on = false; T.playing = false;
  if (T.unfollow) { T.unfollow(); T.unfollow = null; }
  if (T.audio) { T.audio.pause(); T.audio = null; }
  T.els.forEach(x => x.classList.remove('daf-speaking'));
  C.Player.clear('btts:' + T.bookId); T.book = null;
  if (B.loc) onRelocate({ detail: B.loc });
}
function drawPlayer(){
  const T = B.tts; if (!T.on) return;
  const left = T.sleepAt ? Math.max(0, Math.round((T.sleepAt - Date.now()) / 60000)) : 0;
  C.Player.drive({ id: 'btts:' + T.bookId, title: T.title, sub: 'Read aloud by Kokoro', art: T.art, open: '#ebook/' + encodeURIComponent(T.bookId),
    playing: T.playing, at: T.i, of: T.els.length, rate: T.rate, sleep: left, voice: C.Voices.cur ? C.Voices.name(C.Voices.cur) : 'Voice',
    act: {
      play: () => { T.playing = !T.playing; if (T.audio) T.playing ? T.audio.play().catch(() => {}) : T.audio.pause(); drawPlayer(); },
      next: () => { T.i++; T.cache = null; playPara(); },
      prev: () => { T.i = Math.max(0, T.i - 1); T.cache = null; playPara(); },
      close: stopListen,
      voice: b => C.Voices.menu(b),
      rate: () => { T.rate = T.rate >= 2 ? 0.75 : Math.round((T.rate + 0.25) * 100) / 100; if (T.audio) T.audio.playbackRate = T.rate; drawPlayer(); },
      sleep: () => { const steps = [0, 15, 30, 45, 60], cur = T.sleepAt ? Math.round((T.sleepAt - Date.now()) / 60000) : 0; const nx = steps.find(m => m > cur + 1) || 0; T.sleepAt = nx ? Date.now() + nx * 60000 : 0; drawPlayer(); },
      open: () => { if (here()) goToSpeaking(); else { T.goThere = true; location.hash = 'ebook/' + encodeURIComponent(T.bookId); } },
    } });
}
// The page with the paragraph it's reading.
function goToSpeaking(){
  const T = B.tts; if (!T.on || !here()) return;
  const el = T.els[T.i];
  if (onPage(el)) { try { const rg = el.ownerDocument.createRange(); rg.selectNodeContents(el); B.view.renderer.scrollToAnchor?.(rg); } catch(e){} }
  else B.view.goTo(T.index).catch(() => {});
}
/* ---------- Listen with the real audiobook (readalong.py) ---------- */
// A book whose audiobook has been prepared (its page: Prepare the audiobook) is read by its own
// narrator instead of Kokoro: Listen plays the audiobook in Daf's player from the page, the sentence
// being read is marked the way Kokoro's is, and the page turns with it. A tap on a sentence while it
// plays takes the audiobook there.
// The server's map (GET /api/abs/book/<id>/along) is a point every few seconds, (second, word of the
// book), and each section's first word. The page counts a section's words the way the server does
// (secWords), so a point is a word in the chapter on screen; the sentence around it is hl.js's.
// It's the player's audiobook all along (audiobooks.js): pausing, the speed, the sleep timer and
// Audiobookshelf's place work as for any audiobook, it plays on when the book is closed, and the
// page follows again when the book is opened while it plays. Its time is Audiobookshelf's listening
// time, so the reading beat (below) stops while it reads.
const AL = B.along = { on: false, book: null, item: null, map: null, el: null, S: null, k: -1, w: -1, hold: 0, mine: 0, busy: false };
const alongMaps = {};
const ub = (a, x) => { let lo = 0, hi = a.length; while (lo < hi) { const m = (lo + hi) >> 1; if (a[m] <= x) lo = m + 1; else hi = m; } return lo; };   // how many are ≤ x
const alongOn = () => AL.on && C.Player.is('abs:' + AL.item);
const alongHere = () => alongOn() && !!B.view && B.id === AL.book;
const alongReady = id => { const x = C.Audiobooks && C.Audiobooks.book[id || B.id]; return !!(x && x.item && x.along && x.along.state === 'ready'); };
const listening = () => B.tts.on || (alongOn() && B.id === AL.book);
function alongMap(id){
  if (!alongMaps[id]) alongMaps[id] = api('/api/abs/book/' + encodeURIComponent(id) + '/along').then(m => { m.s0 = m.secs.map(x => x[0]); return m; }).catch(e => { delete alongMaps[id]; throw e; });
  return alongMaps[id];
}
// A section's words, counted as audiomap.py counts them: the body's text in order (not scripts or
// styles), a block's end ending a word, and a word any run of letters, digits and apostrophes.
const SECW = new WeakMap(), BREAKS = /^(p|div|li|h[1-6]|br|blockquote|tr)$/;
function secWords(doc){
  let s = SECW.get(doc); if (s) return s;
  const nodes = [], at = []; let text = '';
  (function walk(el){
    const skip = el.localName === 'script' || el.localName === 'style';
    for (let n = el.firstChild; n; n = n.nextSibling) {
      if (n.nodeType === 3) { if (!skip) { nodes.push(n); at.push(text.length); text += n.data; } }
      else if (n.nodeType === 1) walk(n);
    }
    if (BREAKS.test(el.localName)) text += ' ';
  })(doc.body);
  const ws = []; for (const m of text.matchAll(/[\p{L}\p{N}_’']+/gu)) ws.push(m.index);
  s = { nodes, at, ws, n: ws.length }; SECW.set(doc, s); return s;
}
const wordPlace = (s, w) => { const c = s.ws[Math.max(0, Math.min(s.n - 1, w))], i = Math.max(0, ub(s.at, c) - 1); return [s.nodes[i], c - s.at[i]]; };
const placeWord = (s, node, off) => { const i = s.nodes.indexOf(node); return i < 0 ? -1 : Math.max(0, ub(s.ws, s.at[i] + off) - 1); };
// The word being read at a second: between two points, as far into the words as into the time. -1
// where the recording isn't the book (credits, music, a part that wasn't found): nothing is marked.
function alongWord(M, t){
  const k = ub(M.t, t) - 1; if (k < 0) return -1;
  const dt = k + 1 < M.t.length ? M.t[k + 1] - M.t[k] : 1e9, dw = k + 1 < M.t.length ? M.w[k + 1] - M.w[k] : 0;
  if (dw > 0 && dt < 30 && dw / dt < 8) return M.w[k] + Math.floor((t - M.t[k]) / dt * dw);
  return t - M.t[k] < 8 ? M.w[k] : -1;
}
// The second a word is read at; a word the recording doesn't have: the next one it does (null if that's far).
function alongTime(M, w){
  if (!M.byW) { M.byW = M.w.map((_, i) => i).sort((a, b) => M.w[a] - M.w[b] || a - b); M.ws = M.byW.map(i => M.w[i]); }
  const j = ub(M.ws, w) - 1, next = i => (i < M.byW.length && M.ws[i] - w < 4000 ? M.t[M.byW[i]] : null);
  if (j < 0) return next(0);
  const k = M.byW[j], dw = k + 1 < M.w.length ? M.w[k + 1] - M.w[k] : 0, dt = dw > 0 ? M.t[k + 1] - M.t[k] : 0;
  if (dw > 0 && w < M.w[k + 1] && dt < 30 && dw / dt < 8) return M.t[k] + (w - M.w[k]) / dw * dt;
  return w - M.w[k] < 30 ? M.t[k] + (w - M.w[k]) / 2.6 : next(j + 1);
}
// A place in a chapter on screen → the audiobook's second.
function alongAt(doc, index, node, off){
  const M = AL.map, s = secWords(doc), sec = M && M.secs[index]; if (!sec || !sec[1] || !s.n) return null;
  let w = placeWord(s, node, off); if (w < 0) return null;
  if (s.n !== sec[1]) w = Math.round(w * sec[1] / s.n);          // (the browser read the file a little differently)
  return alongTime(M, sec[0] + Math.min(w, sec[1] - 1));
}
// Is a place in the chapter on the page being shown? (Pages: its column. Scroll: its lines, clear of the bar below.)
function onScreen(r){
  const rc = [...r.getClientRects()].find(x => x.width > 0 && x.height > 0), f = r.startContainer.ownerDocument.defaultView.frameElement;
  if (!rc || !f || !B.view) return true;
  const fr = f.getBoundingClientRect(), st = B.view.getBoundingClientRect(), x = fr.left + rc.left + rc.width / 2, y = fr.top + rc.top;
  return x >= st.left && x <= st.right && y >= st.top && y + rc.height <= st.bottom - (document.body.dataset.flow === 'scrolled' ? 70 : 0);
}
function alongUnmark(){
  if (AL.el) AL.el.classList.remove('daf-speaking');
  if (AL.S) AL.S.clear();
  AL.el = null; AL.S = null; AL.k = -1; AL.w = -1;
}
// Every quarter second while it plays (player.js's daf-player-time): mark the sentence, turn the page.
async function alongTick(t){
  if (!alongHere() || AL.busy) return;
  const M = AL.map, w = alongWord(M, t + 0.25);                  // a touch ahead: the eye leads the voice
  if (w < 0) { alongUnmark(); return; }
  if (w === AL.w) return;
  const si = Math.max(0, ub(M.s0, w) - 1), c = B.view.renderer.getContents()[0]; if (!c) return;
  const follow = Date.now() > AL.hold;
  if (c.index !== si) {                                          // it's in another chapter now
    alongUnmark(); if (!follow) return;
    AL.busy = true; AL.mine = Date.now();
    try { await B.view.goTo(si); } catch(e){} finally { AL.busy = false; AL.mine = Date.now(); }
    return;
  }
  const s = secWords(c.doc), sec = M.secs[si]; if (!s.n) return;
  const [node, off] = wordPlace(s, s.n === sec[1] ? w - sec[0] : Math.round((w - sec[0]) * s.n / Math.max(1, sec[1])));
  const el = (node.parentElement && node.parentElement.closest(BLOCKS)) || node.parentElement;
  AL.w = w;
  if (el !== AL.el) { alongUnmark(); AL.w = w; AL.el = el; el.classList.add('daf-speaking'); AL.S = H.sentences(el); }
  const k = AL.S ? AL.S.of(node, off) : -1;
  if (k !== AL.k) { AL.k = k; if (AL.S) { if (AL.S.n > 1 && k >= 0) AL.S.mark(k); else AL.S.clear(); } }
  if (!follow) return;
  const r = c.doc.createRange(); r.setStart(node, off); r.setEnd(node, Math.min(node.data.length, off + 1));
  if (!onScreen(r)) { AL.mine = Date.now(); try { await B.view.renderer.scrollToAnchor?.(r); centerIt(); } catch(e){} AL.mine = Date.now(); }
}
// A page turned by hand while it reads: the page stays where it was put for a while (to look back, or to
// tap a sentence there), then follows again. foliate says why it moved; "anchor" is a page put somewhere,
// as this does.
function alongMoved(reason){
  if (!alongHere() || AL.busy || reason === 'anchor' || Date.now() - AL.mine < 1500) return;
  AL.hold = Date.now() + 12000;
}
// Listen, with the audiobook: from the page's first words. False when it can't (then Kokoro reads).
// fromPage false (the reader's Listen, and opening the book): when the audiobook is playing already,
// the page goes to the narrator instead of the narrator to the page.
async function startAlong(fromPage = true){
  const id = B.id, x = C.Audiobooks && C.Audiobooks.book[id]; if (!id || !x || !x.item) return false;
  let M; try { M = await alongMap(id); } catch(e){ return false; }
  if (B.id !== id || !B.view) return true;
  if (B.tts.on) stopListen();
  alongUnmark();
  Object.assign(AL, { on: true, book: id, item: x.item, map: M, hold: 0, busy: false });
  showChrome();                                                  // the player comes up with the bar
  if (!fromPage && C.Player.is('abs:' + x.item) && C.Player.playing()) { alongTick(C.Player.time()); if (B.loc) onRelocate({ detail: B.loc }); return true; }
  $$('#bnotice .abnotice').forEach(n => n.remove());             // ("Go there?": it's where it'll be)
  let t = null; const c = B.view.renderer.getContents()[0], vis = B.loc && B.loc.range;
  if (c && vis && vis.startContainer.ownerDocument === c.doc) {
    let n = vis.startContainer, o = vis.startOffset;
    if (n.nodeType !== 3) { const tw = c.doc.createTreeWalker(c.doc.body, 4); tw.currentNode = n.childNodes[o] || n; n = tw.currentNode.nodeType === 3 ? tw.currentNode : tw.nextNode(); o = 0; }
    if (n) t = alongAt(c.doc, c.index, n, o);
  }
  const was = C.Player.is('abs:' + x.item);
  try {
    if (t == null) t = (await api('/api/abs/book/' + encodeURIComponent(id) + '/start', { method: 'POST', body: JSON.stringify(Object.assign({ exact: true }, C.BookPlace.here() || {})) })).t;
    await C.Audiobooks.play(x.item, null, Math.max(0, t - 0.3));
    if (was && !C.Player.playing()) C.Player.toggle();
  } catch(e){ AL.on = false; toast(e.message); return true; }
  if (B.loc) onRelocate({ detail: B.loc });
  return true;
}
function stopAlong(){
  const mine = alongOn();
  alongUnmark(); AL.on = false;
  if (mine) C.Player.stop();
  if (B.loc && B.view) onRelocate({ detail: B.loc });
}
// A tap on a sentence while it plays: the audiobook goes there. → true when the tap was that.
function alongTap(doc, index, ev){
  if (!alongHere() || !C.Player.playing()) return false;
  let node, off;
  if (doc.caretPositionFromPoint) { const p = doc.caretPositionFromPoint(ev.clientX, ev.clientY); if (p) { node = p.offsetNode; off = p.offset; } }
  else if (doc.caretRangeFromPoint) { const r = doc.caretRangeFromPoint(ev.clientX, ev.clientY); if (r) { node = r.startContainer; off = r.startOffset; } }
  if (!node || node.nodeType !== 3 || !node.data.trim()) return false;
  const r = doc.createRange(); r.setStart(node, Math.max(0, off - 1)); r.setEnd(node, Math.min(node.data.length, off + 1));
  const rc = r.getBoundingClientRect();                          // on the words, not the margin beside them
  if (ev.clientX < rc.left - 24 || ev.clientX > rc.right + 24 || ev.clientY < rc.top - 6 || ev.clientY > rc.bottom + 6) return false;
  const el = node.parentElement && node.parentElement.closest(BLOCKS), S = el && H.sentences(el), k = S ? S.of(node, off) : -1;
  if (k >= 0) [node, off] = S.first(k);                          // from the sentence's first word
  const t = alongAt(doc, index, node, off); if (t == null) return false;
  setTimeout(() => { if (H.visible()) return; AL.hold = 0; C.Player.seek(Math.max(0, t - 0.3)); }, 0);   // (not when the tap opened a highlight's bar)
  return true;
}
window.addEventListener('daf-player-time', e => { if (AL.on && e.detail.id === 'abs:' + AL.item) alongTick(e.detail.t); });
window.addEventListener('daf-player', e => { if (AL.on && e.detail.id !== 'abs:' + AL.item) { alongUnmark(); AL.on = false; if (B.loc && B.view) onRelocate({ detail: B.loc }); } });
// Listen: the audiobook when it's prepared (unless the voice is preferred: Themes & Settings), else Kokoro.
async function toggleListen(){
  if (alongOn() && B.id === AL.book) { stopAlong(); return; }
  if (B.tts.on) { stopListen(); return; }
  if (alongReady() && store.get('bookListen', 'audiobook') !== 'voice' && await startAlong(false)) return;
  startListen();
}
C.BookAlong = {
  on: id => alongOn() && AL.book === id,
  start: () => startAlong(true),                                 // The audiobook from here
  follow: () => startAlong(false),                               // the book opened while its audiobook plays
  // Themes & Settings (reader.js openAa): what Listen reads with, for a book whose audiobook is prepared
  aa: () => { if (!alongReady()) return ''; const v = store.get('bookListen', 'audiobook');
    return '<div class="sbset blisten"><div class="stepper"><span>Listen</span><div class="seg">' + [['audiobook', 'Audiobook'], ['voice', 'Voice']].map(o => '<button class="' + (v === o[0] ? 'on' : '') + '" data-blisten="' + o[0] + '">' + o[1] + '</button>').join('') + '</div></div></div>'; },
};

function cleanup(){
  inkFlush();
  alongUnmark();
  if (B.tts && B.tts.on && B.tts.unfollow) { B.tts.unfollow(); B.tts.unfollow = null; }   // it reads on, off the page
  closeNote(); wake(false); H.hide(); pagesStop();
  if (C.Sound) C.Sound.closed();
  if (B.view) { try { savePosition(true); } catch(e){} try { B.view.close(); } catch(e){} B.view.remove(); }
  if (B.scans) B.scans.close();
  B.view = null; B.id = null; B.d = null; B.scans = null;
  if (H.active === ACT) H.active = null;
  delete document.body.dataset.flow;
}

function offerKindle(mine){
  const d = B.d, k = d && d.kindle; if (!k || k.fraction == null) return;
  const here = mine ? (mine.fraction || 0) : 0, newer = !mine || k.at > (mine.updated || mine.at || 0);
  if (!newer || Math.abs(k.fraction - here) < 0.01) return;
  $('#bnotice').innerHTML = '<div class="bnotice">On the Kindle you’re at page ' + k.page + ' of ' + k.total + ' (' + Math.round(k.fraction * 100) + '%), ' + epochDate(k.at) + '. <button class="btn sm" data-bk="kindle">Go there</button><button class="btn sm" data-bk="nokindle">Stay here</button></div>';
}

/* ---------- each section as it loads ---------- */
function onSectionLoad(e){
  const { doc, index } = e.detail;
  Pens.listen(doc, INKSURF);
  if (alongHere()) { alongUnmark(); setTimeout(() => alongTick(C.Player.time()), 80); }    // the audiobook's sentence, in this chapter
  const T = B.tts;
  if (T.on && T.bookId === B.id && index === T.index && !onPage(T.els[0])) {   // back in the book it's reading: mark its paragraph here
    T.els = paragraphs(doc); const el = T.els[T.i];
    if (el) { el.classList.add('daf-speaking'); if (T.audio) { if (T.unfollow) T.unfollow(); T.unfollow = H.follow(T.audio, el); } }
    if (T.goThere) { T.goThere = false; setTimeout(goToSpeaking, 50); }
  } else if (T.on && T.goThere === true && T.bookId === B.id) { T.goThere = 'chapter'; B.view.goTo(T.index).catch(() => {}); }   // then the paragraph, above
  const active = () => { B.lastActive = Date.now(); if (C.Sound) C.Sound.wake(); };
  ['pointerdown', 'keydown', 'wheel', 'touchstart', 'scroll'].forEach(ev => doc.addEventListener(ev, active, { passive: true }));
  doc.addEventListener('keydown', onKey);
  doc.addEventListener('click', ev => { const a = ev.target.closest('a[href]'); if (a) B.lastLink = a; else closeNote(); }, true);
  doc.addEventListener('pointerdown', ev => { B.touch = ev.pointerType === 'touch'; if (ev.pointerType !== 'touch') H.hide(); });
  doc.addEventListener('pointerup', ev => setTimeout(() => checkSelection(doc, index, ev), 20));
  doc.addEventListener('selectionchange', () => {
    clearTimeout(B.selT);
    B.selT = setTimeout(() => {
      const s = doc.getSelection();
      if (!s || s.isCollapsed) { if (H.ctx && H.ctx.kind === 'sel') H.hide(); }
      else if (B.touch) checkSelection(doc, index, { pointerType: 'touch' });   // phones: handles moved, no pointerup
    }, B.touch ? 500 : 200);
  });
  // A tap on the page closes an open menu (Aa, …) and does only that; the page is its own frame,
  // so the page's own outside-click never hears it. The same for the highlight bar and selected
  // words: the tap that puts them away doesn't turn the page too.
  doc.addEventListener('pointerdown', () => {
    const p = $('#pop'); B.dismissed = !p.hidden; if (B.dismissed) p.hidden = true;
    B.tapBar = H.visible() ? H.ctx : undefined; B.tapSel = !doc.getSelection()?.isCollapsed;
  }, true);
  doc.addEventListener('click', ev => {
    const bar = B.tapBar, sel = B.tapSel; B.tapBar = undefined; B.tapSel = false;
    if (B.dismissed) { B.dismissed = false; return; }
    if (ev.target.closest('a[href]') || !doc.getSelection()?.isCollapsed) return;
    // (foliate shows a tapped highlight's bar from its own click: a new bar stays)
    if (bar !== undefined || sel) { setTimeout(() => { if (H.ctx === bar) H.hide(); }, 0); return; }
    if (alongTap(doc, index, ev)) return;                // the audiobook goes to the sentence tapped
    if (room().w >= 1000 && !(C.Focus && C.Focus.on())) return;
    // the sides turn the page, in Scroll too (a screen at a time, then on into the next chapter);
    // not when the tap was on a highlight and opened its bar
    const fx = (doc.defaultView.frameElement.getBoundingClientRect().left + ev.clientX) / room().w;
    setTimeout(() => {
      if (H.visible()) return;
      if (fx < 0.28) B.view.goLeft(); else if (fx > 0.72) B.view.goRight(); else toggleChrome();
    }, 0);
  });
  // Scroll: a sideways swipe turns too (Pages has foliate's own)
  doc.addEventListener('touchstart', ev => { const t = ev.touches[0]; B.swipe = ev.touches.length === 1 ? { x: t.clientX, y: t.clientY, at: ev.timeStamp } : null; }, { passive: true });
  doc.addEventListener('touchend', ev => {
    const s = B.swipe; B.swipe = null;
    if (!s || document.body.dataset.flow === 'paginated' || !doc.getSelection()?.isCollapsed) return;
    const t = ev.changedTouches[0], dx = t.clientX - s.x, dy = t.clientY - s.y;
    if (ev.timeStamp - s.at > 700 || Math.abs(dx) < 70 || Math.abs(dx) < 2.2 * Math.abs(dy)) return;
    if (dx < 0) B.view.goRight(); else B.view.goLeft();
  }, { passive: true });
}
// The page moved under the bar: a selection's bar goes with the words, a highlight's goes away.
function followBar(){
  if (!H.visible() || Date.now() - (H.shownAt || 0) < 400) return;
  if (H.ctx && H.ctx.kind === 'sel' && B.sel && B.sel.doc.getSelection && !B.sel.doc.getSelection().isCollapsed) {
    try { B.sel.rect = rectFor(B.sel.doc, B.sel.range); H.place(B.sel.rect); } catch(e){ H.hide(); }
  } else H.hide();
}
// Scroll shows a chapter at a time: at its end, the way on to the next one.
function drawNextChapter(l){
  let b = $('#bnext');
  const r = B.view && B.view.renderer, atEnd = document.body.dataset.flow !== 'paginated' && r && r.viewSize - r.end < 4 && (l.fraction || 0) < 0.999;
  if (!atEnd) { if (b) b.hidden = true; return; }
  const flat = [], walk = xs => (xs || []).forEach(x => { flat.push(x); walk(x.subitems); });
  walk(B.view.book.toc);
  const i = flat.findIndex(x => l.tocItem && x.href === l.tocItem.href), next = i >= 0 ? flat[i + 1] : null;
  if (!b) { $('#bstage').insertAdjacentHTML('beforeend', '<button class="bnext" id="bnext" data-bk="nextch"></button>'); b = $('#bnext'); }
  b.innerHTML = '<span class="mute">Next</span><b' + (next && isRtlText(next.label) ? ' dir="rtl"' : '') + '>' + esc(next ? (next.label || '').trim() : 'Go on') + '</b><span aria-hidden="true">›</span>';
  b.hidden = false;
}
// (in focus mode, the bar comes and goes instead: focus.js)
function toggleChrome(){ if (C.Focus && C.Focus.on()) { C.Focus.bar(); return; } if (B.chrome) { B.chrome = false; document.body.classList.add('bookbare'); } else showChrome(); }

// Pages for page goals: a page counts once it has been on screen for five seconds, the way
// KOReader counts the Kindle's. The printed page when the book has one, else foliate's location.
// Two scanned pages side by side (scans.js) are both read.
const addPages = key => key.split('\n').forEach(k => (B.pagesNew = B.pagesNew || new Set()).add(k));
function notePage(l){
  const key = l.pageItem && l.pageItem.label ? (l.pageItem.pages || [l.pageItem.label]).map(p => 'p' + p).join('\n') : l.location && l.location.current != null ? 'l' + l.location.current : null;
  const now = Date.now();
  if (B.pageKey && B.pageKey !== key && now - (B.pageAt || now) >= 5000) addPages(B.pageKey);
  if (B.pageKey !== key) { B.pageKey = key; B.pageAt = now; }
}
function onRelocate(e){
  const l = e.detail; B.loc = l; notePage(l); drawNextChapter(l);
  if (Date.now() - B.opened > 2500) hideChrome();
  followBar();
  if (B.forget && Date.now() - (B.forgetAt || 0) > 2000) B.forget = false;   // reading on after Forget: the place counts again
  const pct = Math.round((l.fraction || 0) * 100);
  const p = $('#rprog'); if (p) p.style.width = pct + '%';
  const sl = $('#bslide'); if (sl && !B.sliding) sl.value = Math.round((l.fraction || 0) * 1000);
  const st = $('#bslidet'); if (st && !B.sliding) st.textContent = (l.time && l.time.section > 0.5 ? fmtMins(l.time.section) + ' left in the chapter · ' : '') + pct + '%';
  drawStatus(); measurePages();
  if (B.d && (l.fraction || 0) > 0.985 && !B.offeredEnd && !B.d.private && C.HC) {
    // The end: offer to mark it read on Hardcover, if it's on your shelves and not Read yet.
    B.offeredEnd = true; const id = B.d.id, title = B.d.title;
    api('/api/hardcover/book/' + encodeURIComponent(id)).then(s => {
      if (!s.on_shelf || s.status_id === 3 || B.id !== id) return;
      const n = document.createElement('div'); n.className = 'bnotice';
      n.innerHTML = 'The end. Mark it read on Hardcover? <button class="btn sm primary" data-bk="hcdone">Finished</button><button class="btn sm" data-bk="hcno">Not now</button>';
      $('#bnotice').append(n);
    }).catch(() => {});
  }
  if (B.d && B.d.series && B.d.series.next && (l.fraction || 0) > 0.985 && !B.offeredNext) {
    B.offeredNext = true;
    $('#bnotice').innerHTML = '<div class="bnotice">Next in ' + esc(B.d.series.name) + ': <b>' + esc(B.d.series.next.title) + '</b> <a class="btn sm primary" href="#ebook/' + encodeURIComponent(B.d.series.next.id) + '">Start it</a><button class="btn sm" data-bk="nokindle">Not now</button></div>';
  }
  $$('#btoc [data-href]').forEach(a => a.classList.toggle('on', !!(l.tocItem && a.dataset.href === l.tocItem.href)));
  const on = $('#btoc .on'); if (on && !B.searching) { const r = on.getBoundingClientRect(), t = $('#btoc').getBoundingClientRect(); if (r.top < t.top + 40 || r.bottom > t.bottom - 20) on.scrollIntoView({ block: 'center' }); }
  const mk = $('[data-bk="bookmark"]'); if (mk) { const m = markHere(); mk.classList.toggle('on', !!m); mk.innerHTML = ICON.mark(!!m); mk.title = m ? 'Remove the bookmark (b)' : 'Bookmark this page (b)'; }
  clearTimeout(B.saveT); B.saveT = setTimeout(() => savePosition(), 1500);
  if (C.Sound) C.Sound.moved(C.BookPlace.here());     // Sound: the scene on this page (sound.js)
  if (C.Margin) C.Margin.draw();
  if (B.panel === 'info' && panelShown()) drawPanelInfoProgress();
}
function savePosition(now){
  const l = B.loc, id = B.id; if (!l || !l.cfi || !id || B.forget) return;
  const body = { cfi: l.cfi, fraction: l.fraction || 0, chapter: l.tocItem?.label || null };
  store.set('bookpos.' + id, { ...body, at: Math.floor(Date.now() / 1000) });
  if (now && B.pageKey && Date.now() - (B.pageAt || 0) >= 5000) addPages(B.pageKey);
  if (B.pagesNew && B.pagesNew.size) { body.pages = [...B.pagesNew]; B.pagesNew = new Set(); }
  // offline (or Daf down), the place waits in the outbox with its time, so a newer one from the Kindle still wins
  const path = '/api/ebooks/' + encodeURIComponent(id) + '/position', late = () => C.outbox && C.outbox.add(path, { method: 'PUT', body: JSON.stringify(body) });
  if (C.outbox && C.outbox.get().length) { late(); C.outbox.flush(); return; }
  fetch(path, { method: 'PUT', credentials: 'same-origin', keepalive: !!now, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ...body, at: Math.floor(Date.now() / 1000) }) })
    .then(r => { if (r.status >= 500) late(); }, late);
}

/* ---------- the status bar under the page, as KOReader has it ---------- */
// What's under the page, as in KOReader: the things you pick (Themes & Settings → Status bar) in your
// order, one at a time with a tap on the bar going on to the next (KOReader's way, and Apple Books'
// page number and pages left), or all at once; beside them a thin line of the book with its chapters
// marked. It stays while you read, in focus mode too, and it's the same for every book.
const SB_ITEMS = [['page', 'Page'], ['chpage', 'Page in chapter'], ['chleft', 'Pages left in chapter'], ['bookleft', 'Pages left in book'],
  ['pct', 'Percent'], ['chtime', 'Time left in chapter'], ['booktime', 'Time left in book'], ['chapter', 'Chapter'], ['title', 'Book title'],
  ['clock', 'Clock'], ['battery', 'Battery']];
// KOReader's defaults, in its order: the page, the clock, the pages left in the chapter, the battery, the
// percent, and the time left in the book and in the chapter, one at a time, beside the book's line.
const SB_DEF = { show: 'one', bar: 'book', items: ['page', 'clock', 'chleft', 'battery', 'pct', 'booktime', 'chtime'] };
const sbGet = () => { const s = Object.assign({}, SB_DEF, store.get('statusBar', {})); s.items = (s.items || []).filter(k => SB_ITEMS.some(i => i[0] === k)); return s; };
const plural = (n, w) => n + ' ' + w + (n === 1 ? '' : 's');
const bookRtl = () => !!B.view && (B.view.book.dir || (B.view.language && B.view.language.direction)) === 'rtl';

// The battery, where the browser tells it (Chrome and the Android app; Safari doesn't). A computer
// that's plugged in and full, or has none, shows nothing.
const BATT = { b: null };
if (navigator.getBattery) navigator.getBattery().then(b => { BATT.b = b; ['levelchange', 'chargingchange'].forEach(ev => b.addEventListener(ev, () => drawStatus())); }).catch(() => {});
const battery = () => { const b = BATT.b; return !b || (b.charging && b.level >= 1) ? null : b; };
const battIcon = lv => '<svg class="bsbatt" width="17" height="9" viewBox="0 0 17 9" aria-hidden="true"><rect x=".5" y=".5" width="14" height="8" rx="2" fill="none" stroke="currentColor"/><rect x="15.3" y="3" width="1.4" height="3" rx=".6" fill="currentColor"/><rect x="2" y="2" width="' + Math.max(1, 11 * lv).toFixed(1) + '" height="5" rx="1" fill="currentColor"/></svg>';

// Pages as KOReader numbers them: the printed book's page when the EPUB has its page list, else the
// pages as they are on this screen, through the whole book. A page is a column, so two pages side by
// side are two pages, and in Scroll a page is a screen's height. foliate lays out only the chapter
// that's open, so a second, hidden paginator lays out the others the same way, one at a time while you
// read; the counts are kept on this device for this layout (the type, Pages or Scroll, the window's
// size). Until they're in, the other chapters are reckoned from their size.
const PG = { run: 0, key: null, counts: null, partial: null, el: null, t: 0, sec: null };
const colsOf = (r, doc) => { const cs = doc.defaultView.getComputedStyle(doc.documentElement), w = parseFloat(cs.columnWidth) + (parseFloat(cs.columnGap) || 0); return w > 0 ? Math.max(1, Math.round(r.size / w)) : 1; };
const rtlDoc = doc => doc.body.dir === 'rtl' || doc.documentElement.dir === 'rtl' || doc.defaultView.getComputedStyle(doc.body).direction === 'rtl';
// The pages a chapter's document makes in a paginator (the main one or the hidden one), measured as foliate does.
function pagesIn(r, doc){
  if (r.scrolled) return Math.max(1, Math.ceil((r.viewSize - 1) / r.size));
  const step = r.size / colsOf(r, doc), root = doc.documentElement.getBoundingClientRect(), range = doc.createRange();
  range.selectNodeContents(doc.body);
  const c = range.getBoundingClientRect(), size = (rtlDoc(doc) ? root.right - c.right : c.left - root.left) + c.width;
  return Math.max(1, Math.ceil((size - 1) / step));
}
// The chapter that's open: its pages, the first and the last of them on the screen.
function secNow(){
  const r = B.view.renderer, c = r.getContents()[0]; if (!c || !c.doc || !c.doc.body || !r.size) return null;
  const P = PG.sec, n = P && P.doc === c.doc && P.size === r.size && P.vs === r.viewSize ? P.n : pagesIn(r, c.doc);
  PG.sec = { doc: c.doc, size: r.size, vs: r.viewSize, n };
  const cols = r.scrolled ? 1 : colsOf(r, c.doc), at = r.scrolled ? Math.ceil((r.end - 1) / r.size) : (r.page - 1) * cols + 1;
  const first = Math.max(1, Math.min(n, at));
  return { index: c.index, n, at: first, last: Math.min(n, first + cols - 1), cols };
}
// Where you are in pages: cur (to: the second of two side by side) and total (labels, for a printed page),
// the pages left after the screen, and the chapter's (sec).
function pageNow(l){
  const v = B.view, list = v.book.pageList;
  if (v.isFixedLayout) { const i = l.section ? l.section.current : 0, n = l.section ? l.section.total : 0; return n ? { cur: i + 1, total: n, left: n - i - 1 } : null; }
  const s = secNow(), o = { sec: s };
  // A scanned book: the pages by the numbers printed on them (scans.js)
  if (B.scans && B.scans.count && l.pageItem && l.pageItem.pages) {
    const ps = l.pageItem.pages, total = B.scans.count(), last = +ps[ps.length - 1];
    return Object.assign(o, { cur: ps[0], to: ps.length > 1 ? ps[ps.length - 1] : undefined, total, left: Math.max(0, total - last), printed: true });
  }
  if (list && list.length) {
    // the book's last page is its highest number (a list can end out of order), else its last label
    if (B.plFor !== list) { B.plFor = list; B.plMax = Math.max(...list.map(p => /^\d+$/.test(p.label) ? +p.label : 0)); }
    const i = l.pageItem ? list.indexOf(l.pageItem) : -1, cur = i >= 0 ? String(l.pageItem.label) : null;
    if (i >= 0) Object.assign(o, { cur, total: B.plMax || list[list.length - 1].label, left: B.plMax && /^\d+$/.test(cur) ? Math.max(0, B.plMax - +cur) : list.length - 1 - i, printed: true });
    return o;
  }
  if (!s) return o;
  const n = sectionPages(s);
  const before = n.slice(0, s.index).reduce((a, b) => a + b, 0), total = n.reduce((a, b) => a + b, 0);
  return Object.assign(o, { cur: before + s.at, to: before + s.last, total, left: total - before - s.last });
}
// Every chapter's pages: counted, or reckoned at the bytes per page of those counted so far.
function sectionPages(s){
  const secs = B.view.book.sections, c = PG.counts || PG.partial || [];
  let bytes = 0, pages = 0;
  c.forEach((k, i) => { if (k && secs[i] && secs[i].size) { bytes += secs[i].size; pages += k; } });
  if (pages < 8 && secs[s.index] && secs[s.index].size > 3000) { bytes += secs[s.index].size; pages += s.n; }
  const bpp = pages ? bytes / pages : 2000;
  return secs.map((x, i) => i === s.index ? s.n : c[i] != null ? c[i] : x.linear === 'no' ? 0 : Math.max(1, Math.round((x.size || 0) / bpp)));
}
const pagesKey = () => {
  const r = B.view.renderer, t = C.typeFor ? C.typeFor(B.id) : store.get('type', {}), b = $('#bstage').getBoundingClientRect();
  return ['1', B.d && B.d.size, r.getAttribute('flow'), t.font || 'serif', t.size || 20, t.spacing || 1.6, t.measure || 38, t.justify ? 1 : 0, r.getAttribute('max-column-count'), Math.round(b.width), Math.round(b.height)].join('|');
};
// Only when a page number or the pages left in the book are on the bar, and the book has no printed pages.
const wantPages = () => { const s = sbGet(), v = B.view; return !!v && !v.isFixedLayout && !(v.book.pageList && v.book.pageList.length) && s.show !== 'off' && s.items.some(k => k === 'page' || k === 'bookleft'); };
function measurePages(){
  if (!wantPages() || !$('#bstage')) return;
  const key = pagesKey(); if (key === PG.key) return;
  PG.key = key; PG.partial = null; PG.counts = store.get('pages.' + B.id, {})[key] || null;
  const run = ++PG.run; clearTimeout(PG.t);
  if (!PG.counts) PG.t = setTimeout(() => countPages(run, key), 1500);   // once the page has settled
}
const settled = doc => Promise.race([new Promise(r => setTimeout(r, 2500)), Promise.all([doc.fonts && doc.fonts.ready,
  ...[...doc.images].filter(i => !i.complete).map(i => new Promise(r => { i.addEventListener('load', r, { once: true }); i.addEventListener('error', r, { once: true }); }))])]);
const idle = () => new Promise(r => window.requestIdleCallback ? requestIdleCallback(() => r(), { timeout: 400 }) : setTimeout(r, 30));
async function countPages(run, key){
  const v = B.view, id = B.id, live = () => run === PG.run && B.view === v;
  if (!v || !live()) return;
  let p = PG.el;
  if (!p) {
    p = PG.el = document.createElement('foliate-paginator');
    p.className = 'bmeasure'; p.setAttribute('aria-hidden', 'true');
    $('#bstage').append(p); p.open(v.book);
    // the language's direction, as foliate's view gives its own pages
    p.addEventListener('load', e => { const d = e.detail.doc, lang = v.language || {}; if (!lang.isCJK && lang.direction) d.documentElement.dir ||= lang.direction; });
  }
  for (const a of ['flow', 'max-inline-size', 'max-column-count', 'gap', 'margin']) p.setAttribute(a, v.renderer.getAttribute(a));
  p.setStyles(bookCSS());
  const secs = v.book.sections, counts = [];
  PG.partial = counts;
  for (let i = 0; i < secs.length; i++) {
    if (secs[i].linear === 'no') { counts.push(0); continue; }
    try {
      await p.goTo({ index: i, anchor: 0 });
      const c = p.getContents()[0], doc = c && c.doc;
      let n = 0;
      if (doc && doc.body) {
        // laying it out is what asks for its fonts: until they've come, count again
        await settled(doc); n = pagesIn(p, doc);
        for (let k = 0; k < 4 && doc.fonts && doc.fonts.status === 'loading'; k++) { await settled(doc); n = pagesIn(p, doc); }
      }
      if (!live()) return;
      counts.push(n);
    } catch(e){ if (!live()) return; counts.push(0); }
    await idle();
    if (!live()) return;
  }
  PG.counts = counts; PG.partial = null;
  const kept = store.get('pages.' + id, {}); kept[key] = counts;
  Object.keys(kept).slice(0, -4).forEach(k => delete kept[k]);     // the last four layouts (the tablet turned, the desk)
  store.set('pages.' + id, kept);
  drawStatus();
}
function pagesStop(){
  PG.run++; clearTimeout(PG.t); PG.key = null; PG.counts = PG.partial = PG.sec = null;
  if (PG.el) { try { PG.el.destroy(); } catch(e){} PG.el.remove(); PG.el = null; }
}
// Where the chapters start, for the marks on the line: each entry of the contents that starts its own
// part of the book (a chapter's sections inside it share its mark), never two marks at one place.
function chapterMarks(){
  const v = B.view, fr = B.secFrac || [], at = new Set();
  const walk = xs => (xs || []).forEach(x => { try { const r = v.resolveNavigation(x.href); if (r && r.index > 0) at.add(r.index); } catch(e){} walk(x.subitems); });
  walk(v.book.toc);
  return [...at].map(i => fr[i]).filter(f => f > 0.002 && f < 0.998).sort((a, b) => a - b).filter((f, i, a) => !i || f - a[i - 1] > 0.01);
}

function sbText(k, l, P){
  if (k === 'page') return P && P.cur != null ? esc(P.cur + (P.to > P.cur ? '–' + P.to : '') + ' of ' + P.total) : '';
  if (k === 'chpage') return P && P.sec ? P.sec.at + (P.sec.last > P.sec.at ? '–' + P.sec.last : '') + ' of ' + P.sec.n + ' in the chapter' : '';
  if (k === 'chleft') { if (!P || !P.sec) return ''; const n = P.sec.n - P.sec.last; return n > 0 ? plural(n, 'page') + ' left in the chapter' : 'Last page in the chapter'; }
  if (k === 'bookleft') return P && P.left != null ? (P.left > 0 ? plural(P.left, 'page') + ' left in the book' : 'Last page') : '';
  if (k === 'pct') return Math.round((l.fraction || 0) * 100) + '%';
  if (k === 'chtime') return l.time ? (l.time.section < 0.5 ? 'Under a minute' : fmtMins(l.time.section)) + ' left in the chapter' : '';
  if (k === 'booktime') return l.time ? (l.time.total < 0.5 ? 'Under a minute' : fmtMins(l.time.total)) + ' left in the book' : '';
  if (k === 'chapter') return esc((l.tocItem && l.tocItem.label || '').trim());
  if (k === 'title') return B.d ? esc(String(B.d.title || '').split(/:\s/)[0]) : '';
  if (k === 'clock') return new Date().toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
  if (k === 'battery') { const b = battery(); return b ? battIcon(b.level) + Math.round(b.level * 100) + '%' : ''; }
  return '';
}
// The line: the book (with its chapters marked), or the chapter you're in.
function sbLine(kind, l, P){
  const fr = B.secFrac || [], i = l.section ? l.section.current : 0;
  let x = l.fraction || 0, marks = B.marks || [];
  if (kind === 'chapter') { marks = []; x = P && P.sec ? P.sec.last / P.sec.n : fr[i + 1] > fr[i] ? (x - fr[i]) / (fr[i + 1] - fr[i]) : 0; }
  x = Math.max(0, Math.min(1, x));
  return '<div class="bsbar" aria-hidden="true"><i style="width:' + (x * 100).toFixed(2) + '%"></i>' +
    marks.map(m => '<b' + (m <= x ? ' class="on"' : '') + ' style="inset-inline-start:' + (m * 100).toFixed(2) + '%"></b>').join('') + '</div>';
}
function drawStatus(){
  const f = $('#bfoot'), l = B.loc; if (!f || !B.view || !l) return;
  if (f.querySelector('#bjump')) return;                    // Go to… has the footer for now
  const s = sbGet(); f.classList.toggle('bsoff', s.show === 'off');
  if (s.show === 'off') { f.innerHTML = ''; return; }
  let P = null; try { P = pageNow(l); } catch(e){}
  let items = s.items.map(k => [k, sbText(k, l, P)]).filter(x => x[1]);
  if (s.show === 'one' && items.length) {
    // the one you're on, or the next that has something to say (no battery here, a page before the first printed one)
    const at = Math.max(0, s.items.indexOf(store.get('statusBarAt', s.items[0])));
    items = [items.find(x => s.items.indexOf(x[0]) >= at) || items[0]];
  }
  // as wide as the text on the page (both pages when there are two), the line ending where the words begin
  const r = B.view.renderer, c = r.getContents && r.getContents()[0];
  let w = 0; try { w = r.scrolled ? parseFloat(r.getAttribute('max-inline-size')) : r.size - parseFloat(c.doc.defaultView.getComputedStyle(c.doc.documentElement).columnGap || 0); } catch(e){}
  const line = s.bar !== 'off' ? sbLine(s.bar, l, P) : '';
  f.innerHTML = '<div class="bsrow" data-bk="status"><div class="bsin' + (line ? '' : ' noline') + '"' + (bookRtl() ? ' dir="rtl"' : '') + (w > 100 ? ' style="max-width:' + Math.round(w) + 'px"' : '') + '>' + line +
    (items.length ? '<div class="bsitems">' + items.map(x => '<span dir="auto" data-sbi="' + x[0] + '"' + (x[0] === 'page' && P && P.printed ? ' title="The printed book’s page"' : '') + '>' + x[1] + '</span>').join('<i aria-hidden="true">·</i>') + '</div>' : '') + '</div></div>';
  // more than fits (a title cut short): the line gives way to the words
  const it = f.querySelector('.bsitems');
  if (line && it && [it, ...it.children].some(x => x.scrollWidth > x.clientWidth + 1)) f.querySelector('.bsin').classList.add('tight');
}
// A tap on the bar: the next thing (one at a time), else the settings. A long press opens them too.
function tapStatus(){
  const s = sbGet(), l = B.loc;
  if (s.show !== 'one' || s.items.length < 2 || !l) { openStatusAa(); return; }
  let P = null; try { P = pageNow(l); } catch(e){}
  const cur = $('#bfoot [data-sbi]'), i = s.items.indexOf(cur ? cur.dataset.sbi : s.items[0]);
  for (let j = 1; j < s.items.length; j++) { const k = s.items[(i + j) % s.items.length]; if (sbText(k, l, P)) { store.set('statusBarAt', k); break; } }
  drawStatus();
}
function openStatusAa(){ B.aaFromBar = true; if (C.openAa) C.openAa($('#bfoot .bsitems') || $('#bfoot .bsrow') || $('[data-bk="aa"]'), { book: true, open: 'bar' }); }
// Themes & Settings → Status bar (reader.js openAa): Off, one at a time or all at once; the line; and the
// things on it, those shown first in their order (a tap takes one off, or puts it at the end).
function statusAa(open){
  const s = sbGet(), name = k => SB_ITEMS.find(i => i[0] === k)[1];
  const seg = (k, list) => '<div class="seg">' + list.map(o => '<button class="' + (s[k] === o[0] ? 'on' : '') + '" data-sb="' + k + '" data-v="' + o[0] + '">' + o[1] + '</button>').join('') + '</div>';
  const chip = (k, on) => '<button class="chip' + (on ? ' on' : '') + '" data-sb="item" data-v="' + k + '" aria-pressed="' + on + '">' + name(k) + '</button>';
  return '<details class="aamore2 sbset"' + (open ? ' open' : '') + ' data-aasec="bar"><summary><span>Status bar</span><span class="aaval">' + { one: 'One at a time', all: 'All at once', off: 'Off' }[s.show] + '</span></summary>' +
    seg('show', [['off', 'Off'], ['one', 'One at a time'], ['all', 'All at once']]) +
    '<div class="stepper"><span>Progress bar</span>' + seg('bar', [['off', 'Off'], ['book', 'Book'], ['chapter', 'Chapter']]) + '</div>' +
    '<div class="sbchips">' + s.items.map(k => chip(k, true)).join('') + SB_ITEMS.filter(i => !s.items.includes(i[0])).map(i => chip(i[0], false)).join('') + '</div></details>';
}
C.StatusBar = { aa: statusAa };
document.addEventListener('contextmenu', e => { if (C.S.route[0] === 'ebook' && e.target.closest && e.target.closest('.bsrow')) { e.preventDefault(); openStatusAa(); } });
// The clock and the battery move on while the page stays.
setInterval(() => { if (C.S.route[0] === 'ebook' && B.view && !document.hidden && sbGet().items.some(k => k === 'clock' || k === 'battery')) drawStatus(); }, 15000);

// Go to a page (the printed one, or the screen's) or a percent ("45%"), from the … menu, in the footer.
function openJump(){
  const f = $('#bfoot'); if (!f) return;
  f.innerHTML = '<span class="mute">Go to</span><input id="bjump" class="field" inputmode="decimal" placeholder="120 or 45%" autocomplete="off"><span class="spacer"></span><button class="btn sm" data-bk="jumpcancel">Cancel</button>';
  if (PHONE()) { B.chrome = false; document.body.classList.add('bookbare'); }     // the slider would sit over it
  $('#bjump').focus();
}
function closeJump(){ const f = $('#bfoot'); if (f) f.innerHTML = ''; drawStatus(); }
async function goJump(raw){
  const s = String(raw || '').trim(), v = parseFloat(s.replace(',', '.')), list = B.view.book.pageList, l = B.loc;
  closeJump();
  if (!s) return;
  if (!/%$/.test(s)) {
    const it = list && list.length && list.find(p => String(p.label).toLowerCase() === s.toLowerCase());
    if (it) { await B.view.goTo(it.href).catch(() => {}); return; }
    if (!isNaN(v) && v >= 1 && !(list && list.length) && l) {
      if (B.view.isFixedLayout) { await B.view.goTo(Math.min(B.view.book.sections.length, Math.round(v)) - 1).catch(() => {}); return; }
      const sn = secNow(), n = sn && sectionPages(sn);
      if (n) {
        let p = Math.min(Math.round(v), n.reduce((a, b) => a + b, 0)), i = 0;
        while (i < n.length - 1 && p > n[i]) p -= n[i++];
        // that chapter's screen with the page on it (foliate's anchor is a fraction of the chapter's screens)
        const screens = Math.max(1, Math.ceil(n[i] / (sn.cols || 1))), at = Math.floor((p - 1) / (sn.cols || 1));
        await B.view.renderer.goTo({ index: i, anchor: screens > 1 ? at / (screens - 1) : 0 }).catch(() => {});
        return;
      }
    }
  }
  if (!isNaN(v)) await B.view.goToFraction(Math.max(0, Math.min(100, v)) / 100).catch(() => {});
}

/* ---------- bookmarks ---------- */
function markHere(){
  const l = B.loc; if (!l || !l.cfi || !B.d) return null;
  try { const a = CFI.collapse(l.cfi), b = CFI.collapse(l.cfi, true); return (B.d.bookmarks || []).find(m => CFI.compare(m.cfi, a) >= 0 && CFI.compare(m.cfi, b) <= 0) || null; }
  catch(e){ return null; }
}
async function toggleMark(){
  const l = B.loc; if (!l || !l.cfi) return;
  const here = markHere();
  try {
    if (here) {
      await api('/api/ebooks/' + encodeURIComponent(B.d.id) + '/bookmarks/' + encodeURIComponent(here.id), { method: 'DELETE' });
      B.d.bookmarks = B.d.bookmarks.filter(m => m !== here); toast('Bookmark removed');
    } else {
      const cfi = CFI.collapse(l.cfi), excerpt = (() => { try { return l.range.toString().replace(/\s+/g, ' ').trim().slice(0, 140); } catch(e){ return ''; } })();
      const r = await api('/api/ebooks/' + encodeURIComponent(B.d.id) + '/bookmarks', { method: 'POST', body: JSON.stringify({ cfi, fraction: l.fraction, chapter: l.tocItem?.label || null, excerpt }) });
      (B.d.bookmarks = B.d.bookmarks || []).push({ id: r.id, cfi, fraction: l.fraction, chapter: l.tocItem?.label || null, excerpt, created: Date.now() / 1000 });
      B.d.bookmarks.sort((a, b) => (a.fraction || 0) - (b.fraction || 0)); toast('Bookmarked · in Contents');
    }
  } catch(e){ toast(e.message); return; }
  onRelocate({ detail: B.loc }); drawMarks();
}
function drawMarks(){
  const box = $('#bmarks'); if (!box || !B.d) return;
  const ms = B.d.bookmarks || [];
  box.innerHTML = ms.length ? '<div class="tochead">Bookmarks</div>' + ms.map(m => '<a class="tocit bmk" href="#" data-gomark="' + esc(m.cfi) + '"><span>' + esc(m.chapter || 'Bookmark') + ' <span class="mute tiny">' + Math.round((m.fraction || 0) * 100) + '%</span></span>' + (m.excerpt ? '<span class="mute tiny bex">' + esc(m.excerpt) + '</span>' : '') + '</a>').join('') : '';
}

/* ---------- top bar, contents, panel ---------- */
// The bar, as Apple Books has it: back and Contents, the title, then Aa, Search and the bookmark; Listen, the
// notebook, Ask and focus mode are in the … menu. It fades once you turn a page (chrome below).
function drawTop(){
  const d = B.d, tip = a => C.Keys.tip('book', a);
  if (PHONE()) {
    $('#btop').innerHTML = '<a class="ib bclose" href="#book/' + encodeURIComponent(d.id) + '" aria-label="Close the book">' + ICON.x + '</a>' +
      '<div class="btitle2"' + (isRtlText(d.title) ? ' dir="rtl"' : '') + '><b>' + esc(String(d.title || '').split(/:\s/)[0]) + '</b><span>' + esc(d.author || '') + '</span></div>' + (C.Sketch ? C.Sketch.button() : '<span class="bgap"></span>');
    return;
  }
  $('#btop').innerHTML = '<a class="ib" href="#book/' + encodeURIComponent(d.id) + '" aria-label="Back to the book">' + I.back + '</a>' +
    '<button class="ib" data-bk="toc" title="Contents' + tip('toc') + '" aria-label="Contents">' + ICON.toc + '</button>' +
    '<span class="btitle-top mute"' + (isRtlText(d.title) ? ' dir="rtl"' : '') + '>' + esc(String(d.title || '').split(/:\s/)[0]) + '</span>' +
    '<button class="ib aa" data-bk="aa" title="Themes and settings" aria-label="Themes and settings">Aa</button>' +
    '<button class="ib" data-bk="search" title="Search the book' + tip('search') + '" aria-label="Search the book">' + ICON.search + '</button>' +
    '<button class="ib" data-bk="bookmark" title="Bookmark this page' + tip('bookmark') + '" aria-label="Bookmark">' + ICON.mark(!!markHere()) + '</button>' + (C.Sketch ? C.Sketch.button() : '') + (C.Sound ? C.Sound.button() : '') +
    '<button class="ib" data-bk="more" title="More" aria-label="More">' + ICON.more + '</button>';
}
const PHONE = () => matchMedia('(max-width:700px)').matches;
// One tap on a phone: everything the bar holds elsewhere, in one menu above the round button.
function openPhoneMenu(anchor){
  const p = $('#pop'), r = anchor.getBoundingClientRect(), n = allHighlights().length;
  const row = (a, label, icon, extra) => '<button data-pm="' + a + '"><span>' + label + '</span>' + (extra || '') + icon + '</button>';
  p.innerHTML = '<div class="menu pmenu">' +
    row('toc', 'Contents', ICON.toc) + row('notebook', 'Notebook', ICON.pen, n ? '<span class="pmc">' + n + '</span>' : '') + row('info', 'About this book', ICON.panel) + row('search', 'Search Book', ICON.search) +
    row('aa', 'Themes &amp; Settings', '<b class="pmaa">Aa</b>') + row('listen', listening() ? 'Stop listening' : 'Listen', ICON.listen) + (C.Sound ? row('sound', 'Sound', C.Sound.icon, C.Sound.mode === 'book' ? '<span class="pmc">✓</span>' : '') : '') + row('ask', 'Ask about this book', ICON.ask) +
    '<div class="pmrow"><button data-pm="mark" aria-label="' + (markHere() ? 'Remove the bookmark' : 'Bookmark this page') + '">' + ICON.mark(!!markHere()) + '</button>' +
    (C.Focus ? '<button data-pm="focus" aria-label="Focus mode">' + ICON.focus + '</button>' : '') + '<button data-pm="more" aria-label="More">' + ICON.more + '</button></div></div>';
  p.hidden = false; p.style.left = Math.max(8, window.innerWidth - 272) + 'px'; p.style.top = Math.max(8, r.top - p.offsetHeight - 12) + 'px';
}
// The bar and the footer: there when the book opens, while a menu, a sheet or Listen is up, and when the
// pointer comes to the top or the bottom; gone once you turn a page. A tap in the middle of the page on
// a touch screen brings them or puts them away.
function showChrome(){ B.chrome = true; document.body.classList.remove('bookbare'); }
function hideChrome(){
  if ((C.Focus && C.Focus.on()) || !B.view) return;
  if (!$('#pop').hidden || document.body.classList.contains('btocsheet') || panelShown() || H.visible() || (B.tts && B.tts.on) || (alongOn() && B.id === AL.book) || $('#bjump')) return;
  B.chrome = false; document.body.classList.add('bookbare');
}
document.addEventListener('mousemove', e => {
  if (C.S.route[0] !== 'ebook' || B.chrome) return;
  if (e.clientY < 64 || e.clientY > window.innerHeight - 52) showChrome();
}, { passive: true });
function tocHTML(items, depth){
  return (items || []).map(it => '<a class="tocit d' + Math.min(depth, 3) + '" href="#" data-href="' + esc(it.href || '') + '"' + (isRtlText(it.label) ? ' dir="rtl"' : '') + '>' + esc((it.label || '').trim() || '—') + '</a>' + (it.subitems ? tocHTML(it.subitems, depth + 1) : '')).join('');
}
function drawToc(){
  const t = $('#btoc'); if (!t || !B.view) return;
  const book = B.view.book;
  t.innerHTML = '<div class="bsearch"><span class="ic">' + ICON.search + '</span><input id="bq" placeholder="Search in the book" autocomplete="off"' + (B.d && B.d.language === 'heb' ? ' dir="auto"' : '') + '></div>' +
    '<div id="btocl"><div id="bmarks"></div><div class="tochead">Contents</div>' + (book.toc && book.toc.length ? tocHTML(book.toc, 0) : '<p class="mute tiny">This book has no table of contents.</p>') + '</div><div id="bres" hidden></div>';
  drawMarks();
}
async function runSearch(q){
  const res = $('#bres'), list = $('#btocl'); if (!res || !B.view) return;
  B.view.clearSearch();
  if (!q || q.trim().length < 2) { B.searching = false; res.hidden = true; list.hidden = false; return; }
  B.searching = true; res.hidden = false; list.hidden = true;
  res.innerHTML = '<p class="mute tiny">Searching…</p>';
  const token = (B.searchToken = (B.searchToken || 0) + 1);
  let html = '', n = 0;
  for await (const r of B.view.search({ query: q.trim() })) {
    if (token !== B.searchToken) return;
    if (r === 'done') break;
    if (r.subitems) {
      html += '<div class="tochead">' + esc(r.label || '') + '</div>' + r.subitems.slice(0, 30).map(s => { n++; return '<a class="sres" href="#" data-cfi="' + esc(s.cfi) + '">' + esc(s.excerpt.pre.slice(-40)) + '<mark>' + esc(s.excerpt.match) + '</mark>' + esc(s.excerpt.post.slice(0, 60)) + '</a>'; }).join('');
      res.innerHTML = '<p class="mute tiny">' + n + ' found</p>' + html;
    }
    if (n > 300) break;
  }
  if (token === B.searchToken) res.innerHTML = (n ? '<p class="mute tiny">' + n + ' found</p>' : '<p class="mute tiny">Not in this book.</p>') + html;
}

// Every highlight in this book, in reading order: Daf's, the Kindle's, audiobook and paper ones.
function allHighlights(){
  const d = B.d, fr = B.secFrac || [];
  const href = h => '#ebook/' + encodeURIComponent(d.id) + '/hl:' + encodeURIComponent(h.id);
  const out = d.highlights.map(h => Object.assign(h, { open: href(h), _k: h.pos.fraction ?? 0 }));
  for (const h of d.other_highlights) out.push(Object.assign(h, { open: href(h), _k: h.sec != null && fr[h.sec] != null ? fr[h.sec] + (h.page || 0) * 1e-7 : (h.page && d.kindle && d.kindle.total ? h.page / d.kindle.total : 2) }));
  return out.sort((a, b) => a._k - b._k);
}
// The highlights for the Notebook (sketchbook.js): each with the contents' entry it's under, so it's a
// card on its chapter's page, in reading order (highlights on one page by their place on it).
const TOCAT = new Map(), SECDOC = new Map();   // a highlight's id → its contents entry; a section → its document, made once
async function tocItemOf(h){
  if (TOCAT.has(h.id)) return TOCAT.get(h.id);
  const v = B.view; let it = null;
  try {
    const cfi = (h.pos && h.pos.cfi) || h.cfi;
    if (cfi) {
      const at = v.resolveNavigation(cfi), shown = v.renderer.getContents().find(c => c.index === at.index);
      let doc = shown && shown.doc;
      if (!doc) { if (!SECDOC.has(at.index)) SECDOC.set(at.index, Promise.resolve(v.book.sections[at.index].createDocument())); doc = await SECDOC.get(at.index); }
      const r = at.anchor(doc);
      it = v.getProgressOf(at.index, r && r.comparePoint ? r : null).tocItem;
    } else {
      let i = h.sec;
      if (i == null && h._k != null && h._k <= 1) { const fr = B.secFrac || []; i = 0; while (i + 1 < fr.length && fr[i + 1] <= h._k) i++; }
      if (i != null) it = v.getProgressOf(i).tocItem;
    }
  } catch(e){}
  TOCAT.set(h.id, it || null);
  return it || null;
}
async function notebookHls(){
  if (!B.d || !B.view) return [];
  const cf = x => (x.pos && x.pos.cfi) || x.cfi;
  const all = allHighlights().slice().sort((a, b) => (a._k - b._k) || (cf(a) && cf(b) ? CFI.compare(cf(a), cf(b)) : 0));
  const out = [];
  let prev = null, tie = 0;
  for (const h of all) {
    tie = prev != null && h._k === prev ? tie + 1 : 0; prev = h._k;
    out.push({ id: h.id, text: h.text, color: h.color || 'yellow', key: (h._k || 0) + tie * 1e-7, where: H.where(h), note: h.user_note || '', raw: h, tocItem: await tocItemOf(h) });
  }
  return out;
}
function drawPanel(){
  const p = $('#bpanel'); if (!p || !B.d) return;
  if (B.panel === 'notebook') B.panel = 'info';      // the Notebook is its own now (sketchbook.js)
  const d = B.d, all = allHighlights(), n = all.length;
  p.innerHTML = '<div class="ptabs" role="tablist">' + (C.Sketch ? [['notebook', 'Notebook']] : []).concat([['info', 'Info'], ['ask', 'Ask']]).map(t => '<button class="ptab' + (B.panel === t[0] ? ' on' : '') + '" data-bpt="' + t[0] + '" role="tab">' + t[1] + '</button>').join('') + '</div><div id="bpbody"></div>';
  const b = $('#bpbody');
  if (B.panel === 'info') {
    b.innerHTML = '<div class="binfo">' + (d.has_cover ? '<img class="bcover" src="/api/cover/' + encodeURIComponent(d.id) + '" alt="">' : '') +
      '<b class="bt">' + esc(d.title) + '</b><span class="mute">' + esc(d.author || '') + '</span>' +
      (d.description ? '<p class="bdesc">' + esc(d.description.slice(0, 700)) + (d.description.length > 700 ? '…' : '') + '</p>' : '') +
      '<div class="bmeta"><div class="mh">Metadata</div>' +
      '<div class="mr"><span>Type</span><span>' + esc(d.format || '') + '</span></div>' +
      (d.year ? '<div class="mr"><span>Published</span><span>' + esc(d.year) + '</span></div>' : '') +
      (d.language ? '<div class="mr"><span>Language</span><span>' + esc({ eng: 'English', heb: 'Hebrew', deu: 'German', fra: 'French' }[d.language] || d.language) + '</span></div>' : '') +
      '<div class="mr"><span>Progress</span><span id="bprog">—</span></div>' +
      '<div class="mr"><span>Read here</span><span>' + fmtMins(d.minutes_here) + '</span></div>' +
      '<div class="mr"><span>Highlights</span><span>' + n + (n ? ' <button class="linkbtn" data-bk="nblist">See them</button>' : '') + '</span></div>' +
      (d.series ? '<div class="mr"><span>Series</span><span>' + esc(d.series.name) + (d.series.index ? ' #' + (+d.series.index) : '') + (d.series.next ? '<br><a href="#ebook/' + encodeURIComponent(d.series.next.id) + '">Next: ' + esc(d.series.next.title) + '</a>' : '') + '</span></div>' : '') +
      (d.kindle ? '<div class="mr"><span>Kindle</span><span>p. ' + d.kindle.page + ' of ' + d.kindle.total + ' · ' + epochDate(d.kindle.at) + ' <button class="linkbtn" data-bk="kindle">Go there</button></span></div>' : '') +
      '</div>' + (d.vault_path ? '<span class="tiny mute">Highlights go to <code>' + esc(d.vault_path) + '</code></span>' : '<span class="tiny mute">Your first highlight here makes this book a vault note.</span>') + '</div>';
    drawPanelInfoProgress();
  } else {
    const chips = (B.d && B.d.questions) || [];      // Preferences → AI
    b.innerHTML = '<div class="askbox">' + (chips.length ? '<div style="display:flex;gap:6px;flex-wrap:wrap">' + chips.map(q => '<button class="chip" data-bkq="' + esc(q) + '">' + esc(q) + '</button>').join('') + '</div>' : '') +
      '<textarea class="field" id="bask" rows="3" placeholder="Ask about where you are: a word, a name you’ve forgotten, an argument…"></textarea><div style="display:flex;justify-content:flex-end"><button class="btn primary sm" data-bk="ask">Ask</button></div></div><div id="banswers"></div>';
  }
}
function drawPanelInfoProgress(){
  const el = $('#bprog'), l = B.loc; if (!el || !l) return;
  el.textContent = Math.round((l.fraction || 0) * 100) + '%' + (l.time ? ' (' + fmtMins(l.time.total) + ' left)' : '');
}

/* ---------- selection, highlights ---------- */
// The highlights on the page, for the margin (study.js): each one's top and height on the stage, level with
// its words (the part of it on this page, in a book laid out as pages).
function marginPlaces(){
  const v = B.view, stage = $('#bstage'), fv = $('#fv'); if (!v || !B.d || !stage || !fv) return [];
  const sr = stage.getBoundingClientRect(), vr = fv.getBoundingClientRect(), shown = new Map();
  try { for (const c of v.renderer.getContents()) shown.set(c.index, c.doc); } catch(e){ return []; }
  const out = [];
  for (const h of allHighlights()) {
    const cfi = (h.pos && h.pos.cfi) || h.cfi; if (!cfi) continue;
    let at, range; try { at = v.resolveNavigation(cfi); } catch(e){ continue; }
    const doc = at && shown.get(at.index); if (!doc) continue;
    try { range = at.anchor(doc); } catch(e){ continue; }
    if (!range || !range.getClientRects) continue;
    const fr = doc.defaultView.frameElement.getBoundingClientRect();
    const rs = [...range.getClientRects()].map(r => ({ l: fr.left + r.left, r: fr.left + r.right, t: fr.top + r.top, b: fr.top + r.bottom }))
      .filter(r => r.b > r.t && r.r > vr.left + 1 && r.l < vr.right - 1 && r.b > vr.top && r.t < vr.bottom);
    if (!rs.length) continue;
    const t = Math.min(...rs.map(r => r.t)), b = Math.max(...rs.map(r => r.b));
    out.push({ id: h.id, color: h.color || 'yellow', note: h.user_note || h.note || '', top: t - sr.top, h: b - t });
  }
  return out;
}
function marginOpen(id, el){
  const h = findHl(id); if (!h) return;
  const cfi = (h.pos && h.pos.cfi) || h.cfi, kindle = !!(cfi && B.kindleByCfi.get(cfi) === h), r = el.getBoundingClientRect();
  H.show(H.hlBar(h, { kindle }), { left: r.left, top: r.top, bottom: r.bottom, right: r.right, width: r.width, height: r.height }, { h, cfi, kindle });
}
function rectFor(doc, range){
  const fr = doc.defaultView.frameElement.getBoundingClientRect(), r = range.getBoundingClientRect();
  return { left: fr.left + r.left, top: fr.top + r.top, bottom: fr.top + r.bottom, right: fr.left + r.right, width: r.width, height: r.height };
}
// Whole words only, like Readwise: a selection that starts or ends mid-word grows to the word.
function snapRange(r){
  const sc = r.startContainer, ec = r.endContainer;
  if (sc.nodeType === 3) { const t = sc.nodeValue; let o = r.startOffset; while (o > 0 && H.isWord(t[o - 1]) && H.isWord(t[o])) o--; while (o < t.length && /\s/.test(t[o]) && !(sc === ec && o >= r.endOffset)) o++; r.setStart(sc, o); }
  if (ec.nodeType === 3) { const t = ec.nodeValue; let o = r.endOffset; while (o < t.length && H.isWord(t[o - 1]) && H.isWord(t[o])) o++; while (o > 0 && /\s/.test(t[o - 1]) && !(sc === ec && o <= r.startOffset)) o--; r.setEnd(ec, o); }
  return r;
}
function checkSelection(doc, index, ev){
  const sel = doc.getSelection(); if (!sel || sel.isCollapsed || !sel.rangeCount) return;
  const range = snapRange(sel.getRangeAt(0).cloneRange()), text = range.toString().trim(); if (text.length < 2) return;
  if (B.sel && B.sel.doc === doc && B.sel.text === text && H.visible()) return;
  let cfi; try { cfi = B.view.getCFI(index, range); } catch(e){ return; }
  const block = range.startContainer.parentElement?.closest('p, li, blockquote, div') || range.startContainer.parentElement;
  B.sel = { doc, index, range, text, cfi, rect: rectFor(doc, range), sentence: block ? block.textContent : text };
  const word = !/\s/.test(text);
  if (H.auto() && !word && !(ev && ev.altKey) && !(ev && ev.pointerType === 'touch')) { highlightSel(false); return; }
  try { sel.removeAllRanges(); sel.addRange(range); } catch(e){}
  H.show(H.selBar({ text }), B.sel.rect, { kind: 'sel', text });
}
const before = (doc, n1, o1, n2, o2) => { const r = doc.createRange(); r.setStart(n1, o1); r.collapse(true); return r.comparePoint(n2, o2) === 1; };
async function highlightSel(withNote, quiet){
  const s = B.sel; if (!s || !B.d) return null;
  H.hide();
  // Overlapping highlights merge into one, as in Readwise; their notes and tags come along.
  const range = s.range.cloneRange(), merged = [];
  for (const h of B.d.highlights) {
    if (h.index !== s.index) continue;
    let r2; try { r2 = B.view.resolveCFI(h.pos.cfi).anchor(s.doc); } catch(e){ continue; }
    if (!r2 || !r2.startContainer) continue;
    const overlap = before(s.doc, range.startContainer, range.startOffset, r2.endContainer, r2.endOffset) && before(s.doc, r2.startContainer, r2.startOffset, range.endContainer, range.endOffset);
    if (!overlap) continue;
    if (before(s.doc, r2.startContainer, r2.startOffset, range.startContainer, range.startOffset)) range.setStart(r2.startContainer, r2.startOffset);
    if (before(s.doc, range.endContainer, range.endOffset, r2.endContainer, r2.endOffset)) range.setEnd(r2.endContainer, r2.endOffset);
    merged.push(h);
  }
  let cfi = s.cfi, text = s.text;
  if (merged.length === 1 && merged[0].pos.cfi === (() => { try { return B.view.getCFI(s.index, range); } catch(e){ return null; } })()) {
    s.doc.getSelection()?.removeAllRanges(); B.sel = null;   // the selection was inside a highlight: show that one
    if (!quiet) H.show(H.hlBar(merged[0]), s.rect, { h: merged[0], cfi: merged[0].pos.cfi }); return merged[0];
  }
  if (merged.length) { try { cfi = B.view.getCFI(s.index, range); text = range.toString().trim(); } catch(e){ merged.length = 0; } }
  const chapter = B.loc?.tocItem?.label || null, fraction = B.loc ? B.loc.fraction : null;
  try {
    const color = merged.find(m => m.color)?.color || s.color || H.color();
    const r = await api('/api/ebooks/' + encodeURIComponent(B.d.id) + '/highlights', { method: 'POST', body: JSON.stringify({ cfi, text, chapter, fraction, color, replaces: merged.map(m => m.id) }) });
    for (const m of merged) { B.byCfi.delete(m.pos.cfi); B.view.deleteAnnotation({ value: m.pos.cfi }).catch(() => {}); }
    const notes = merged.map(m => m.user_note).filter(Boolean), tags = [...new Set(merged.flatMap(m => m.tags || []))];
    const h = { id: r.id, text, chapter, pos: { cfi, fraction }, user_note: notes.join('\n\n') || null, index: s.index, created: Date.now() / 1000, color, source: 'epub', tags, fav: merged.some(m => m.fav) };
    B.d.highlights = B.d.highlights.filter(x => x.id !== h.id && !merged.includes(x)).concat(h);
    B.byCfi.set(cfi, h);
    s.doc.getSelection()?.removeAllRanges(); B.sel = null;
    await B.view.addAnnotation({ value: cfi });
    if (withNote) openNote(h);
    else {
      const rr = (() => { try { return rectFor(s.doc, range); } catch(e){ return s.rect; } })();
      if (!quiet) H.show(H.hlBar(h), rr, { h, cfi });
    }
    if (C.Sketch) C.Sketch.hlChanged(h.id);          // its card, on the Notebook's page
    return h;
  } catch(e){ toast(e.message); return null; }
}
// A note on a highlight: its row in the Notebook's list, typing in its note.
function openNote(h){ if (C.Sketch) C.Sketch.reveal({ hl: h.id, note: true }); }
// The Notebook (sketchbook.js), from the menus and the key: open or closed; at a highlight, its card.
function notebook(id){ if (!C.Sketch) return; if (id) C.Sketch.reveal({ hl: id }); else if (C.Sketch.open()) C.Sketch.hide(); else C.Sketch.tab('notebook'); }
// quiet: no Undo toast (the pen's eraser has its own Undo); either way it answers with the way back.
async function removeHighlight(id, quiet){
  const h = B.d.highlights.find(x => x.id === id); if (!h) return null;
  await api('/api/highlights/' + encodeURIComponent(id), { method: 'DELETE' });
  B.d.highlights = B.d.highlights.filter(x => x.id !== id); B.byCfi.delete(h.pos.cfi);
  try { await B.view.deleteAnnotation({ value: h.pos.cfi }); } catch(e){}
  drawPanel(); if (C.Sketch) C.Sketch.hlChanged();
  const back = async () => {
    await api('/api/highlights/' + encodeURIComponent(id) + '/restore', { method: 'POST' });
    if (!B.d) return;
    B.d.highlights.push(h); B.byCfi.set(h.pos.cfi, h);
    try { await B.view.addAnnotation({ value: h.pos.cfi }); } catch(e){}
    drawPanel(); if (C.Sketch) C.Sketch.hlChanged();
  };
  if (!quiet) H.undo('Highlight deleted', back);
  return back;
}

/* ---------- ink: writing on the pages with a pen (the pens are pens.js; ink.py keeps it) ---------- */
// Each stroke keeps the letter it started on, as a CFI in its chapter, and where it sat beside it,
// so it goes with its words when the type or the page changes. It's drawn on foliate's overlay of
// the chapter, as the highlights are; the strokes that start on the same letter are drawn together.
const Pens = C.Pens, NS = 'http://www.w3.org/2000/svg';
const INK = { by: new Map(), geo: new Map(), done: [], undone: [], q: { book: null, add: new Map(), remove: new Set() } };
const r1 = v => Math.round(v * 10) / 10;
const inkId = () => { const b = new Uint8Array(10); crypto.getRandomValues(b); return 'k' + Array.from(b, x => x.toString(16).padStart(2, '0')).join(''); };
const inkGroup = cfi => { let g = INK.by.get(cfi); if (!g) INK.by.set(cfi, g = []); return g; };
const secOf = doc => { const c = B.view && B.view.renderer.getContents().find(x => x.doc === doc); return c ? c.index : null; };
const frameOf = doc => { try { return doc.defaultView.frameElement.getBoundingClientRect(); } catch(e){ return null; } };
const lightText = c => { const m = /(\d+)\D+(\d+)\D+(\d+)/.exec(c || ''); return !!m && (+m[1] + +m[2] + +m[3]) / 3 > 140; };
function inkLoad(d){
  INK.by = new Map(); INK.geo = new Map(); INK.done = []; INK.undone = [];
  // what's waiting in the outbox (written offline) is shown as if it had gone
  let list = (d.ink || []).slice();
  const path = '/api/ebooks/' + encodeURIComponent(d.id) + '/ink';
  for (const x of C.outbox.get()) {
    if (x.path !== path || !x.body) continue;
    for (const s of x.body.add || []) if (!list.some(t => t.id === s.id)) list.push(s);
    const rm = new Set(x.body.remove || []); list = list.filter(t => !rm.has(t.id));
  }
  d.ink = list;
  for (const s of list) if (s.at && s.at.cfi) inkGroup(s.at.cfi).push(s);
}
// A chapter's overlay is there: its strokes on it.
function inkSection(index){ for (const [cfi, g] of INK.by) if (g.length && g[0].at.s === index) B.view.addAnnotation({ value: cfi }).catch(() => {}); }
function inkRedraw(cfis){ for (const cfi of cfis) { const g = INK.by.get(cfi); if (g && g.length) B.view.addAnnotation({ value: cfi }).catch(() => {}); else { INK.by.delete(cfi); B.view.deleteAnnotation({ value: cfi }).catch(() => {}); } } }
// foliate's draw: the strokes on one letter, from that letter's box (rects, in the chapter's frame).
function inkDraw(rects, o){
  const g = document.createElementNS(NS, 'g'), list = INK.by.get(o.cfi) || [], r = rects[0];
  if (!r || !list.length) return g;
  const doc = o.range.startContainer.ownerDocument, win = doc.defaultView;
  const f = fontAt(doc, o.range);
  const layer = Pens.layer(g, lightText(win.getComputedStyle(doc.body).color));
  for (const s of list) {
    const k = f / (s.at.f || 16), x0 = r.left + s.at.x * k, y0 = r.top + s.at.y * k;
    const pts = s.pts.map(p => [x0 + p[0] * k, y0 + p[1] * k, p[2]]);
    const el = layer.add(s, pts, k);
    if (Pens.kindOf(s) === 'text') {     // typed: its box
      const n = String(s.text || '').split('\n').length, fs = (s.fs || 16) * k;
      INK.geo.set(s.id, { pts, r: 0, box: [x0, y0, x0 + (s.w || 120) * k, y0 + n * fs * 1.3 + fs * 0.3], doc, text: true, el });
      continue;
    }
    let x1 = Infinity, y1 = Infinity, x2 = -Infinity, y2 = -Infinity;
    for (const p of pts) { if (p[0] < x1) x1 = p[0]; if (p[0] > x2) x2 = p[0]; if (p[1] < y1) y1 = p[1]; if (p[1] > y2) y2 = p[1]; }
    INK.geo.set(s.id, { pts, r: (s.size || 2.5) * k / 2, box: [x1, y1, x2, y2], doc, el });
  }
  return g;
}
function caretIn(doc, x, y){
  if (doc.caretPositionFromPoint) { const p = doc.caretPositionFromPoint(x, y); return p && { node: p.offsetNode, off: p.offset }; }
  if (doc.caretRangeFromPoint) { const r = doc.caretRangeFromPoint(x, y); return r && { node: r.startContainer, off: r.startOffset }; }
  return null;
}
// The letter at (or nearest) a point in a chapter's frame, as a range of one letter.
function letterAt(doc, x, y){
  const p = caretIn(doc, x, y); if (!p || !p.node) return null;
  let node = p.node, off = p.off;
  if (node.nodeType !== 3) {
    const w = doc.createTreeWalker(node, NodeFilter.SHOW_TEXT); let t;
    while ((t = w.nextNode()) && !t.data.trim());
    if (!t) return null; node = t; off = 0;
  }
  if (!node.data.length) return null;
  off = Math.min(off, node.data.length - 1);
  const r = doc.createRange(); r.setStart(node, off); r.setEnd(node, off + 1);
  return r;
}
// Where a stroke is kept: the letter at the point, or, where there's none (a picture with no
// words in it), the nearest letter before it in the text (else after it), which foliate can find again.
function placeAt(doc, x, y){
  const r = letterAt(doc, x, y); if (r) return r;
  const w = doc.createTreeWalker(doc.body, NodeFilter.SHOW_TEXT), from = doc.elementFromPoint(x, y) || doc.body;
  w.currentNode = from;
  let t = w.previousNode(); while (t && !t.data.trim()) t = w.previousNode();
  if (!t) { w.currentNode = from; t = w.nextNode(); while (t && !t.data.trim()) t = w.nextNode(); }
  if (!t) return null;
  const off = Math.max(0, t.data.trimEnd().length - 1), rr = doc.createRange(); rr.setStart(t, off); rr.setEnd(t, off + 1);
  return rr;
}
const fontAt = (doc, range) => { const n = range.startContainer, el = n.nodeType === 1 ? (n.childNodes[range.startOffset] || n) : n.parentElement; return parseFloat(doc.defaultView.getComputedStyle(el.nodeType === 1 ? el : el.parentElement).fontSize) || 16; };
function inkAdd(list){ const cfis = new Set(); for (const s of list) { inkGroup(s.at.cfi).push(s); cfis.add(s.at.cfi); } inkRedraw(cfis); }
function inkTake(list){
  const ids = new Set(list.map(s => s.id)), cfis = new Set(list.map(s => s.at.cfi));
  for (const cfi of cfis) { const g = INK.by.get(cfi); if (g) INK.by.set(cfi, g.filter(s => !ids.has(s.id))); }
  for (const id of ids) INK.geo.delete(id);
  inkRedraw(cfis);
}
const inkAll = () => [...INK.by.values()].flat();
function inkStroke(L){
  const doc = L.doc, index = secOf(doc), fr = frameOf(doc); if (index == null || !fr) return;
  const [wx, wy] = L.pts[0], x0 = wx - fr.left, y0 = wy - fr.top;
  const range = placeAt(doc, x0, y0); if (!range) return;
  let cfi; try { cfi = B.view.getCFI(index, range); } catch(e){ return; }
  const r = range.getClientRects()[0] || range.getBoundingClientRect();
  const f = fontAt(doc, range), b = L.brush;
  const s = { id: inkId(), v: 2, tool: b.pen, color: b.color, size: r1(b.w), o: Math.round(b.opacity * 100) / 100,
    at: { cfi, s: index, f, x: r1(x0 - r.left), y: r1(y0 - r.top) }, pts: L.pts.map(p => [r1(p[0] - wx), r1(p[1] - wy), Math.round(p[2] * 100) / 100]) };
  if (L.snapped) s.sh = 1;           // a clean shape, which isn't read as writing
  inkAdd([s]); inkAct({ add: [s] });
  return s;
}
function inkNear(pts, x, y, r){
  for (let i = 0; i < pts.length; i++) {
    const a = pts[i], b = pts[i + 1] || a, dx = b[0] - a[0], dy = b[1] - a[1], l = dx * dx + dy * dy;
    const t = l ? Math.max(0, Math.min(1, ((x - a[0]) * dx + (y - a[1]) * dy) / l)) : 0;
    if (Math.hypot(x - a[0] - t * dx, y - a[1] - t * dy) <= r) return true;
  }
  return false;
}
// Whole strokes, or only what's within r of (x, y) (in the window); and the highlights it passes over.
function inkErase(x, y, mode, r, L){
  for (const [id, g] of [...INK.geo]) {
    const fr = frameOf(g.doc); if (!fr) { INK.geo.delete(id); continue; }
    const px = x - fr.left, py = y - fr.top, b = g.box, m = r + g.r;
    if (px < b[0] - m || px > b[2] + m || py < b[1] - m || py > b[3] + m || (!g.text && !inkNear(g.pts, px, py, m))) continue;
    const s = inkAll().find(t => t.id === id); if (!s) { INK.geo.delete(id); continue; }
    const mine = L.added.indexOf(s);
    if (mine >= 0) L.added.splice(mine, 1); else L.erased.push(s);
    const pieces = [];
    if (mode === 'area' && !g.text) {
      let run = [];
      const flush = () => { if (run.length >= 2) pieces.push(Object.assign({}, s, { id: inkId(), pts: run })); run = []; };
      g.pts.forEach((p, i) => { if (Math.hypot(p[0] - px, p[1] - py) <= m) flush(); else run.push(s.pts[i]); });
      flush();
    }
    inkTake([s]);
    if (pieces.length) { L.added.push(...pieces); inkAdd(pieces); }
  }
  if (!L.hlr) {   // the highlights on the pages now, once a stroke, in the window
    L.hlr = [];
    for (const c of B.view.renderer.getContents()) {
      const fr = frameOf(c.doc); if (!fr) continue;
      for (const h of B.d.highlights) {
        if (h.index !== c.index) continue;
        try { const rg = B.view.resolveCFI(h.pos.cfi).anchor(c.doc); for (const q of rg.getClientRects()) L.hlr.push({ id: h.id, l: fr.left + q.left, t: fr.top + q.top, r: fr.left + q.right, b: fr.top + q.bottom }); } catch(e){}
      }
    }
  }
  for (const q of L.hlr) if (x >= q.l && x <= q.r && y >= q.t && y <= q.b) L.hls.add(q.id);
}
async function inkErased(L){
  const a = {};
  if (L.erased.length) a.del = L.erased;
  if (L.added.length) a.add = L.added;
  if (L.hls.size) {
    a.unhl = [];
    for (const id of L.hls) { const back = await removeHighlight(id, true); if (back) a.unhl.push({ id, back }); }
    if (!a.unhl.length) delete a.unhl;
  }
  if (a.del || a.add || a.unhl) inkAct(a);
}
// Everything written in the chapter that's open.
function inkEraseAll(){
  const at = B.loc && B.loc.section != null ? B.loc.section.current : null;
  const list = inkAll().filter(s => at == null || s.at.s === at); if (!list.length) return;
  inkTake(list); inkAct({ del: list }); toast('Everything written in this chapter is erased. Undo brings it back.');
}
// The highlighter along a line (or down a few) makes a highlight of the words, as selecting them does.
function inkHighlight(L){
  const doc = L.doc, index = secOf(doc), fr = frameOf(doc); if (index == null || !fr) return false;
  const P = L.pts.map(p => [p[0] - fr.left, p[1] - fr.top]), s = P[0], z = P[P.length - 1];
  let x1 = Infinity, x2 = -Infinity, y1 = Infinity, y2 = -Infinity;
  for (const p of P) { x1 = Math.min(x1, p[0]); x2 = Math.max(x2, p[0]); y1 = Math.min(y1, p[1]); y2 = Math.max(y2, p[1]); }
  const first = letterAt(doc, s[0], s[1]); if (!first) return false;
  const el = first.startContainer.parentElement, cs = doc.defaultView.getComputedStyle(el);
  const lh = parseFloat(cs.lineHeight) || (parseFloat(cs.fontSize) || 16) * 1.5, tall = y2 - y1 > 1.6 * lh;
  if (tall && Math.hypot(z[0] - s[0], z[1] - s[1]) < 0.35 * Math.max(x2 - x1, y2 - y1)) return false;
  let a, b;
  if (!tall) { const ys = P.map(p => p[1]).sort((m, n) => m - n), y = ys[ys.length >> 1]; a = caretIn(doc, x1 + 2, y); b = caretIn(doc, x2 - 2, y); }
  else { a = caretIn(doc, s[0], s[1]); b = caretIn(doc, z[0], z[1]); }
  if (!a || !b || !a.node || !b.node) return false;
  const range = doc.createRange();
  try {
    range.setStart(a.node, a.off); range.setEnd(a.node, a.off);
    if (before(doc, a.node, a.off, b.node, b.off)) range.setEnd(b.node, b.off); else { range.setStart(b.node, b.off); range.setEnd(a.node, a.off); }
  } catch(e){ return false; }
  if (!inkSel(doc, index, range)) return false;
  highlightSel(false, true).then(h => { if (h) inkAct({ hl: h.id }); });
  return true;
}
// A range on a chapter's page made the selection, in whole words, as if it had been selected.
function inkSel(doc, index, range, color){
  snapRange(range);
  const text = range.toString().trim(); if (text.replace(/\s/g, '').length < 2) return false;
  let cfi; try { cfi = B.view.getCFI(index, range); } catch(e){ return false; }
  const block = range.startContainer.parentElement?.closest('p, li, blockquote, div') || range.startContainer.parentElement;
  B.sel = { doc, index, range, text, cfi, rect: rectFor(doc, range), sentence: block ? block.textContent : text, color };
  return true;
}
// An underline written with the pen (underline.js): its words highlighted in its colour, in the
// strokes' place. Answers with the way back (the toast's Undo), which brings the ink back.
async function inkUnderline(doc, range, color, strokes){
  const index = secOf(doc), had = new Set((B.d ? B.d.highlights : []).map(h => h.id));
  if (index == null || !strokes.every(s => inkAll().includes(s)) || !inkSel(doc, index, range, color)) return null;
  const h = await highlightSel(false, true); if (!h) return null;
  inkTake(strokes);
  const a = had.has(h.id) ? { del: strokes } : { del: strokes, hl: h.id };     // words highlighted already keep their highlight
  inkAct(a);
  return () => { const i = INK.done.indexOf(a); if (i < 0) return; INK.done.splice(i, 1); INK.undone.push(a); inkApply(a, true); Pens.redraw(); };
}
function inkAct(a){ INK.done.push(a); if (INK.done.length > 200) INK.done.shift(); INK.undone = []; inkApply(a, false); Pens.redraw(); }
// Does what a records (back = false) or takes it back (true); a highlight's own way for those.
async function inkApply(a, back, again){
  const add = back ? a.del : a.add, rm = back ? a.add : a.del;
  if (again || back) { if (rm) inkTake(rm); if (add) inkAdd(add.filter(s => !inkAll().some(t => t.id === s.id))); }
  inkSend(add || [], rm || []);
  if (B.d) B.d.ink = inkAll();
  if (a.hl && (back || again)) {
    if (back) a.hlBack = await removeHighlight(a.hl, true);
    else if (a.hlBack) await a.hlBack();
  }
  if (a.unhl && (back || again)) {
    for (const u of a.unhl) { if (back) await u.back(); else { const b2 = await removeHighlight(u.id, true); if (b2) u.back = b2; } }
  }
}
function inkUndo(){ const a = INK.done.pop(); if (!a) return; INK.undone.push(a); inkApply(a, true); Pens.redraw(); }
function inkRedo(){ const a = INK.undone.pop(); if (!a) return; INK.done.push(a); inkApply(a, false, true); Pens.redraw(); }
function inkSend(add, rm){
  if (!B.d || (!add.length && !rm.length)) return;
  if (INK.q.book && INK.q.book !== B.d.id) inkFlush();
  INK.q.book = B.d.id;
  for (const s of add) { INK.q.remove.delete(s.id); INK.q.add.set(s.id, s); }
  for (const s of rm) { INK.q.add.delete(s.id); INK.q.remove.add(s.id); }
  clearTimeout(INK.qT); INK.qT = setTimeout(inkFlush, 1200);
}
// What's been written in the last moment goes in one request; offline it waits in the outbox.
async function inkFlush(){
  clearTimeout(INK.qT);
  const id = INK.q.book; if (!id || (!INK.q.add.size && !INK.q.remove.size)) return;
  const body = { add: [...INK.q.add.values()], remove: [...INK.q.remove] };
  INK.q = { book: null, add: new Map(), remove: new Set() };
  try { await api('/api/ebooks/' + encodeURIComponent(id) + '/ink', { method: 'POST', body: JSON.stringify(body) }); } catch(e){ toast(e.message); }
}
// Handwriting read as text (pens.js's lasso): what's inside its loop, marked; typed text in its
// place; a note on the passage beside it.
function inkInside(poly, x, y){
  let c = false;
  for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
    const a = poly[i], b = poly[j];
    if ((a[1] > y) !== (b[1] > y) && x < (b[0] - a[0]) * (y - a[1]) / (b[1] - a[1]) + a[0]) c = !c;
  }
  return c;
}
function inkSelect(loop){
  return inkAll().filter(s => {
    const g = INK.geo.get(s.id), fr = g && frameOf(g.doc); if (!fr) return false;
    const poly = loop.map(p => [p[0] - fr.left, p[1] - fr.top]);
    if (g.text) return inkInside(poly, (g.box[0] + g.box[2]) / 2, (g.box[1] + g.box[3]) / 2);
    return g.pts.filter(p => inkInside(poly, p[0], p[1])).length >= g.pts.length * 0.6;
  });
}
function inkMark(list, on){ for (const s of list) { const g = INK.geo.get(s.id); if (g && g.el) g.el.classList.toggle('held', !!on); } }
// Their box in their chapter's frame, and that chapter.
function inkBox(list){
  let x1 = Infinity, y1 = Infinity, x2 = -Infinity, y2 = -Infinity, doc = null;
  for (const s of list) { const g = INK.geo.get(s.id); if (!g) continue; doc = doc || g.doc; x1 = Math.min(x1, g.box[0]); y1 = Math.min(y1, g.box[1]); x2 = Math.max(x2, g.box[2]); y2 = Math.max(y2, g.box[3]); }
  return { x1, y1, x2, y2, doc };
}
function inkTyped(list, text){
  const b = inkBox(list), doc = b.doc, index = doc && secOf(doc); if (index == null) throw new Error('That page has gone; turn back to it.');
  const range = placeAt(doc, b.x1, b.y1); if (!range) throw new Error('There are no words here to keep it by.');
  const cfi = B.view.getCFI(index, range), r = range.getClientRects()[0] || range.getBoundingClientRect();
  const f = fontAt(doc, range), lines = text.split('\n').length;
  const first = list.find(Pens.writingOf) || list[0];
  const t = { id: inkId(), v: 2, tool: 'text', text, fs: Math.round(Math.max(12, Math.min(30, (b.y2 - b.y1) / lines * 0.62))), w: r1(Math.max(60, b.x2 - b.x1)),
    color: first.color || 'ink', size: 1, o: 1, at: { cfi, s: index, f, x: r1(b.x1 - r.left), y: r1(b.y1 - r.top) }, pts: [[0, 0, 0.5]] };
  inkTake(list); inkAdd([t]); inkAct({ add: [t], del: list });
}
async function inkNote(list, text){
  const b = inkBox(list), doc = b.doc, index = doc && secOf(doc); if (index == null) throw new Error('That page has gone; turn back to it.');
  const letter = letterAt(doc, (b.x1 + b.x2) / 2, (b.y1 + b.y2) / 2); if (!letter) throw new Error('There’s no passage beside it to keep the note with.');
  const block = letter.startContainer.parentElement.closest('p, li, blockquote, dd, td, h1, h2, h3, h4, div') || letter.startContainer.parentElement;
  // the sentence round that letter (a short paragraph whole)
  const full = block.textContent, pre = doc.createRange(); pre.selectNodeContents(block); pre.setEnd(letter.startContainer, letter.startOffset);
  const at = pre.toString().length; let s = 0, e = full.length;
  if (full.length > 280) {
    const ends = /[.!?…:;](?:["”’)\]]*)\s+/g; let m;
    while ((m = ends.exec(full))) { const end = m.index + m[0].length; if (end <= at) s = end; else { e = end; break; } }
  }
  const pos = c => { const w = doc.createTreeWalker(block, NodeFilter.SHOW_TEXT); let n, sum = 0; while ((n = w.nextNode())) { if (c <= sum + n.data.length) return [n, c - sum]; sum += n.data.length; } return null; };
  const a = pos(s), z = pos(e); if (!a || !z) throw new Error('That passage couldn’t be found.');
  const range = doc.createRange(); range.setStart(a[0], a[1]); range.setEnd(z[0], z[1]); snapRange(range);
  const words = range.toString().trim(); if (words.length < 2) throw new Error('There’s no passage beside it to keep the note with.');
  B.sel = { doc, index, range, text: words, cfi: B.view.getCFI(index, range), rect: rectFor(doc, range), sentence: full };
  const h = await highlightSel(false, true); if (!h) throw new Error('That passage couldn’t be highlighted.');
  const note = [h.user_note, text].filter(x => (x || '').trim()).join('\n\n');
  await api('/api/highlights/' + encodeURIComponent(h.id) + '/note', { method: 'PUT', body: JSON.stringify({ note }) });
  h.user_note = note;
  try { await B.view.addAnnotation({ value: h.pos.cfi }); } catch(e){}
  drawPanel(); if (C.Sketch) C.Sketch.hlChanged();
}
const INKSURF = {
  live: () => !!(B.view && B.d && document.body.dataset.view === 'ebook'),
  takes: (el, doc) => doc !== document,
  off: doc => { const r = frameOf(doc); return r ? [r.left, r.top] : [0, 0]; },
  stroke: inkStroke, erase: inkErase, erased: inkErased, eraseAll: inkEraseAll, highlight: inkHighlight, underline: inkUnderline,
  palHost: () => document.querySelector('.rv.ebook') || document.body,
  canUndo: () => INK.done.length > 0, canRedo: () => INK.undone.length > 0, undo: inkUndo, redo: inkRedo,
  select: inkSelect, mark: inkMark, typed: inkTyped, noteOnPassage: inkNote,
  remove: list => { inkTake(list); inkAct({ del: list }); },
  all: () => inkAll().filter(s => Pens.writingOf(s) && INK.geo.has(s.id)),
  inkOf: list => list.map(s => (INK.geo.get(s.id) || {}).pts).filter(Boolean),
};
document.addEventListener('visibilitychange', () => { if (document.visibilityState === 'hidden') inkFlush(); });
window.addEventListener('pagehide', inkFlush);
// For the checks (android/check.py, the browser's): what's written, and a line of text on the page now, in the window.
C.BookInk = {
  state: () => Object.assign(Pens.state(), { strokes: inkAll().length, drawn: INK.geo.size, done: INK.done.length, queued: INK.q.add.size + INK.q.remove.size, highlights: B.d ? B.d.highlights.length : 0 }),
  line(){
    for (const c of (B.view ? B.view.renderer.getContents() : [])) {
      const fr = frameOf(c.doc); if (!fr) continue;
      const w = c.doc.createTreeWalker(c.doc.body, NodeFilter.SHOW_TEXT); let n;
      while ((n = w.nextNode())) {
        if (n.data.trim().length < 60) continue;
        const r0 = c.doc.createRange(); r0.selectNodeContents(n);
        const q = [...r0.getClientRects()].map(r => ({ l: fr.left + r.left, t: fr.top + r.top, r: fr.left + r.right, b: fr.top + r.bottom })).find(r => r.l >= 0 && r.r <= window.innerWidth && r.r - r.l > 200 && r.t > 90 && r.b < window.innerHeight - 140);
        if (q) { const lh = parseFloat(c.doc.defaultView.getComputedStyle(n.parentElement).lineHeight) || 24; return Object.assign(q, { lh }); }
      }
    }
    return null;
  },
};
function openPanel(tab){
  if (tab) B.panel = tab;
  if (C.Focus && C.Focus.on()) { drawPanel(); C.Focus.panel(true); return; }   // focus mode has its own drawers (focus.js)
  document.body.classList.remove('btocsheet'); document.body.classList.add('bpanelsheet');
  showChrome(); drawPanel();
  if (C.Sketch) C.Sketch.panelChanged(B.panel);      // the Notebook is the panel's other tab: it makes way
}
const panelShown = () => document.body.classList.contains('bpanelsheet');
function closePanel(){ document.body.classList.remove('bpanelsheet'); if (C.Sketch) C.Sketch.panelChanged(); }
function openToc(){ if (C.Focus && C.Focus.on()) { C.Focus.toc(true); return; } document.body.classList.remove('bpanelsheet'); document.body.classList.add('btocsheet'); showChrome(); }
function contextText(){
  try { return (B.loc && B.loc.range ? B.loc.range.toString() : '').slice(0, 6000); } catch(e){ return ''; }
}
async function ask(q, quote){
  B.panel = 'ask'; openPanel();
  const box = $('#banswers'); if (!box) return;
  const item = document.createElement('div'); item.className = 'ans';
  item.innerHTML = (quote ? '<q>' + esc(quote.slice(0, 300)) + '</q>' : '') + '<b>' + esc(q) + '</b><p class="mute">Thinking…</p>';
  box.prepend(item);
  try {
    const r = await api('/api/ebooks/' + encodeURIComponent(B.d.id) + '/ask', { method: 'POST', body: JSON.stringify({ q, quote, context: contextText() }) });
    item.querySelector('p').outerHTML = '<div class="answer">' + esc(r.a).replace(/\*\*(.+?)\*\*/g, '<b>$1</b>').replace(/\n\n/g, '</p><p>').replace(/\n/g, '<br>') + '</div>';
  } catch(e){ item.querySelector('p').textContent = e.message; }
}
// What the highlight toolbar does here.
const ACT = {
  hl: () => highlightSel(false),
  note: ctx => ctx.h ? (H.hide(), openNote(ctx.h)) : highlightSel(true),
  define: () => { const s = B.sel; if (s && C.lookup) { H.hide(); C.lookup({ text: s.text, rect: s.rect }, s.sentence, false); } },
  translate: () => { const s = B.sel; if (s && C.lookup) { H.hide(); C.lookup({ text: s.text, rect: s.rect }, s.sentence, true); } },
  ask: ctx => { H.hide(); ask('What does this passage mean here?', ctx.h ? ctx.h.text : ctx.text); },
  rm: ctx => { H.hide(); return removeHighlight(ctx.h.id); },
  notebook: ctx => { H.hide(); notebook(ctx.h.id); },
  changed: h => { const cfi = h.pos && h.pos.cfi || h.cfi; if (cfi && B.view) B.view.addAnnotation({ value: cfi }).catch(() => {}); },
  deselect: () => { B.sel && B.sel.doc.getSelection()?.removeAllRanges(); },
  meta: () => ({ title: B.d && B.d.title, author: B.d && B.d.author }),
};
window.addEventListener('daf-hl-changed', e => { if (C.S.route[0] === 'ebook' && B.d) { const h = findHl(e.detail.id); if (h) { Object.assign(h, e.detail); ACT.changed(h); } } });

/* ---------- more menu, keys ---------- */
function openMore(anchor){
  const p = $('#pop'), r = anchor.getBoundingClientRect();
  p.innerHTML = '<div class="menu">' +
    '<button data-bm="listen">' + (listening() ? 'Stop listening' : 'Listen from here') + '<span class="kbd">' + esc(C.Keys.label ? C.Keys.label('book', 'listen') : 'l') + '</span></button>' +
    (C.Audiobooks ? C.Audiobooks.menu(B.d.id) : '') +
    '<button data-bm="notebook">Notebook<span class="kbd">' + esc(C.Keys.label ? C.Keys.label('book', 'panel') : ']') + '</span></button>' +
    (C.Margin && C.Margin.can() && !B.scans ? '<button data-bm="margin">' + (C.Margin.active() ? 'Hide the margin' : 'Margin') + '</button>' : '') +
    (C.Split && C.Split.can() ? '<button data-bm="sbs">' + (C.Split.open() ? 'Close side by side' : 'Side by side') + '</button>' : '') +
    '<button data-bm="info">About this book</button>' +
    '<button data-bm="ask">Ask about this book</button>' +
    (C.Focus ? '<button data-bm="focus">' + (C.Focus.on() ? 'Leave focus mode' : 'Focus mode') + '<span class="kbd">' + esc(C.Keys.label ? C.Keys.label('book', 'focus') : 'f') + '</span></button>' : '') + '<hr>' +
    '<button data-bm="start">Go to the beginning</button>' +
    '<button data-bm="goto">Go to a page or a percent</button>' +
    '<button data-bm="kindle"' + (B.d.kindle ? '' : ' disabled') + '>Go to the Kindle’s page</button>' +
    '<button data-bm="mark">' + (markHere() ? 'Remove the bookmark' : 'Bookmark this page') + '<span class="kbd">b</span></button>' +
    (B.scans ? '<button data-bm="pairs">Pair the pages the other way</button>' : '') +
    '<button data-bm="book">Book page, notes and nightstand</button>' +
    '<a href="/api/highlights/export?fmt=md&book=' + encodeURIComponent(B.d.id) + '" download>Export highlights (Markdown)</a>' +
    '<a href="/api/ebooks/' + encodeURIComponent(B.d.id) + '/file" download>Download the file</a>' +
    '<button data-bm="auto"><span><span class="ck">' + (H.auto() ? '✓' : '') + '</span>Auto highlight</span></button>' +
    '<button data-bm="keys">Keyboard shortcuts<span class="kbd">?</span></button>' +
    '<button data-bm="reset">Forget my place in Daf</button>' +
    (phoneKeeps() ? '<button data-bm="offline" disabled>Keep on this device</button>' : '') + '</div>';
  p.hidden = false; p.style.left = Math.max(8, Math.min(window.innerWidth - 280, r.right - 260)) + 'px';
  p.style.top = (r.bottom + 8 + p.offsetHeight > window.innerHeight ? Math.max(8, r.top - p.offsetHeight - 10) : r.bottom + 8) + 'px';
  // the apps keep books for reading with no network; this one, for good, or not
  if (phoneKeeps()) dafShell.offline({ op: 'list' }).then(l => {
    const b = $('#pop [data-bm="offline"]'), x = (l.books || []).find(k => k.id === B.d.id); if (!b) return;
    b.disabled = false; b.dataset.on = x && x.kept ? '1' : '';
    b.textContent = x && x.kept ? 'Remove from this device' : 'Keep on this device';
  }).catch(() => {});
}
const phoneKeeps = () => !!(window.dafShell && dafShell.can && dafShell.can('offline'));
function showKeys(){ C.Keys.sheet('book'); }
function onKey(e){
  if (C.S.route[0] !== 'ebook' || !B.view) return;
  const tag = (e.target.tagName || '').toLowerCase();
  if (tag === 'input' || tag === 'textarea') { if (e.key === 'Escape') { if (e.target.id === 'bjump') closeJump(); else e.target.blur(); } return; }
  if (e.metaKey || e.ctrlKey || e.altKey) return;
  if (!$('#modal').hidden) return;
  const k = e.key, is = a => C.Keys.is(e, 'book', a), paged = document.body.dataset.flow === 'paginated';
  if (is('next') || (k === ' ' && paged && !e.shiftKey)) { e.preventDefault(); B.view.goRight(); }
  else if (is('prev') || (k === ' ' && e.shiftKey && paged)) { e.preventDefault(); B.view.goLeft(); }
  else if (is('highlight') && B.sel && H.ctx && H.ctx.kind === 'sel') highlightSel(false);
  else if (is('note') && B.sel && H.ctx && H.ctx.kind === 'sel') highlightSel(true);
  else if (is('bookmark')) toggleMark();
  else if (is('toc')) click('toc');
  else if (is('listen')) toggleListen();          // (it's in the … menu, not a button on the bar)
  else if (k === '?') showKeys();
  else if (is('search')) { e.preventDefault(); openToc(); setTimeout(() => $('#bq') && $('#bq').focus(), 30); }
  else if (is('panel')) { if (C.Sketch) C.Sketch.togglePanel(); }
  else if (is('focus') && C.Focus) C.Focus.toggle();
  else if (k === 'Escape' && C.Focus && C.Focus.escape()) {}
  else if (k === 'Escape') { if (H.visible()) H.hide(); else if (!$('#pop').hidden) $('#pop').hidden = true; else location.hash = '#book/' + encodeURIComponent(B.d.id); }
  B.lastActive = Date.now();
}
function click(what){ const b = $('[data-bk="' + what + '"]'); if (b) b.click(); }
document.addEventListener('keydown', onKey);
document.addEventListener('pointerdown', () => { B.lastActive = Date.now(); }, { passive: true });

document.addEventListener('click', async e => {
  if (C.S.route[0] !== 'ebook') return;
  const t = e.target;
  const bq = t.closest('[data-bkq]'); if (bq) { ask(bq.dataset.bkq, null); return; }
  const sb = t.closest('[data-sb]');
  if (sb) {          // Themes & Settings → Status bar
    const s = sbGet(), k = sb.dataset.sb, v = sb.dataset.v;
    if (k === 'item') s.items = s.items.includes(v) ? s.items.filter(x => x !== v) : s.items.concat(v);
    else s[k] = v;
    store.set('statusBar', s); drawStatus(); measurePages();
    if (C.openAa) C.openAa((B.aaFromBar && ($('#bfoot .bsitems') || $('#bfoot .bsrow'))) || $('[data-bk="aa"]') || sb, { book: true });
    return;
  }
  const bl = t.closest('[data-blisten]');
  if (bl) {          // Themes & Settings → Listen: the audiobook, or the voice
    store.set('bookListen', bl.dataset.blisten);
    if (C.openAa) C.openAa((B.aaFromBar && ($('#bfoot .bsitems') || $('#bfoot .bsrow'))) || $('[data-bk="aa"]') || bl, { book: true });
    return;
  }
  const bk = t.closest('[data-bk]');
  if (bk) {
    const a = bk.dataset.bk;
    if (a === 'nextch') { bk.hidden = true; B.view.next(); return; }
    if (a === 'toc') { if (C.Focus && C.Focus.on()) C.Focus.toc(); else if (document.body.classList.contains('btocsheet')) document.body.classList.remove('btocsheet'); else openToc(); }
    else if (a === 'search') { openToc(); setTimeout(() => $('#bq') && $('#bq').focus(), 30); }
    else if (a === 'panel') { if (C.Focus && C.Focus.on()) { drawPanel(); C.Focus.panel(); } else if (panelShown()) closePanel(); else openPanel(); }
    else if (a === 'closesheets') { document.body.classList.remove('btocsheet'); if (panelShown()) closePanel(); }
    else if (a === 'nblist') { if (C.Focus && C.Focus.on()) C.Focus.panel(false); document.body.classList.remove('bpanelsheet'); if (C.Sketch) C.Sketch.list(); }
    else if (a === 'pmenu') { if (!$('#pop').hidden && $('#pop .pmenu')) $('#pop').hidden = true; else openPhoneMenu(bk); }
    else if (a === 'aa') { showChrome(); B.aaFromBar = false; C.openAa && C.openAa(bk, { book: true }); }
    else if (a === 'status') tapStatus();
    else if (a === 'more') openMore(bk);
    else if (a === 'sound' && C.Sound) C.Sound.menu(bk);
    else if (a === 'bookmark') toggleMark();
    else if (a === 'kindle' && B.d.kindle) { $('#bnotice').innerHTML = ''; await B.view.goToFraction(B.d.kindle.fraction); toast('At the Kindle’s page, about ' + Math.round(B.d.kindle.fraction * 100) + '% in'); }
    else if (a === 'nokindle') $('#bnotice').innerHTML = '';
    else if (a === 'hcdone') { bk.closest('.bnotice').remove(); C.HC.finish(B.d.id, B.d.title); }
    else if (a === 'hcno') bk.closest('.bnotice').remove();
    else if (a === 'listen') toggleListen();
    else if (a === 'closenote') closeNote();
    else if (a === 'jumpcancel') closeJump();
    else if (a === 'ask') { const q = $('#bask').value.trim(); if (q) { $('#bask').value = ''; ask(q, null); } }
    return;
  }
  if (!t.closest('#fnote') && $('#fnote') && !$('#fnote').hidden) closeNote();
  const pt = t.closest('[data-bpt]'); if (pt) { if (pt.dataset.bpt === 'notebook') { C.Sketch.tab('notebook'); return; } B.panel = pt.dataset.bpt; drawPanel(); if (C.Sketch) C.Sketch.panelChanged(B.panel); return; }
  const ti = t.closest('#btoc [data-href]'); if (ti) { e.preventDefault(); await B.view.goTo(ti.dataset.href).catch(() => {}); document.body.classList.remove('btocsheet'); return; }
  const sr = t.closest('#bres [data-cfi]'); if (sr) { e.preventDefault(); await B.view.goTo(sr.dataset.cfi).catch(() => {}); document.body.classList.remove('btocsheet'); return; }
  const gm = t.closest('[data-gomark]'); if (gm) { e.preventDefault(); await B.view.goTo(gm.dataset.gomark).catch(() => {}); document.body.classList.remove('btocsheet'); return; }
  const pm = t.closest('[data-pm]');
  if (pm) {
    const a = pm.dataset.pm, anchor = $('[data-bk="pmenu"]'); $('#pop').hidden = true;
    if (a === 'toc') openToc();
    else if (a === 'search') { openToc(); setTimeout(() => $('#bq') && $('#bq').focus(), 30); }
    else if (a === 'notebook') notebook();
    else if (a === 'info' || a === 'ask') openPanel(a);
    else if (a === 'aa') C.openAa && C.openAa(anchor || pm, { book: true });
    else if (a === 'listen') toggleListen();
    else if (a === 'mark') toggleMark();
    else if (a === 'focus' && C.Focus) C.Focus.toggle();
    else if (a === 'sound' && C.Sound) C.Sound.menu(anchor || pm);
    else if (a === 'more') openMore(anchor || pm);
    return;
  }
  const bm = t.closest('[data-bm]');
  if (bm) {
    $('#pop').hidden = true;
    const a = bm.dataset.bm;
    if (a === 'listen') toggleListen();
    else if (a === 'notebook') notebook();
    else if (a === 'margin' && C.Margin) C.Margin.toggle();
    else if (a === 'sbs' && C.Split) C.Split.toggle();
    else if (a === 'info' || a === 'ask') openPanel(a);
    else if (a === 'focus' && C.Focus) C.Focus.toggle();
    else if (a === 'start') await B.view.goToTextStart().catch(() => {});
    else if (a === 'goto') openJump();
    else if (a === 'kindle' && B.d.kindle) await B.view.goToFraction(B.d.kindle.fraction);
    else if (a === 'mark') toggleMark();
    else if (a === 'pairs' && B.scans) B.scans.pairs();
    else if (a === 'book') location.hash = '#book/' + encodeURIComponent(B.d.id);
    else if (a === 'auto') { H.setAuto(!H.auto()); toast(H.auto() ? 'Auto highlight on: selecting a passage highlights it' : 'Auto highlight off'); }
    else if (a === 'keys') showKeys();
    else if (a === 'reset') {
      // Forgotten on the server too, and not saved again as the book closes (savePosition checks B.forget).
      B.forget = true; B.forgetAt = Date.now(); store.set('bookpos.' + B.d.id, null);
      api('/api/ebooks/' + encodeURIComponent(B.d.id) + '/position', { method: 'DELETE' }).then(() => toast('Daf forgot your place in this book'), err => toast(err.message));
    }
    else if (a === 'offline' && phoneKeeps()) {
      const on = !bm.dataset.on; toast(on ? 'Keeping it on this device…' : 'Removing it from this device…');
      dafShell.offline({ op: 'keep', id: B.d.id, on }).then(() => toast(on ? 'On this device, also with no network' : 'Removed from this device'), err => toast(err.message));
    }
    return;
  }
  if (!t.closest('#selbar') && !t.closest('#pop')) H.hide();
});
document.addEventListener('keydown', e => {
  if (e.target.id !== 'bjump' || e.key !== 'Enter') return;
  goJump(e.target.value);
});
let qT = null;
document.addEventListener('input', e => { if (e.target.id === 'bq') { clearTimeout(qT); qT = setTimeout(() => runSearch(e.target.value), 300); } });

/* ---------- reading time ---------- */
setInterval(() => {
  // (not while the audiobook reads it: that hour is Audiobookshelf's listening time already)
  const reading = C.S.route[0] === 'ebook' && B.view && B.d && !document.hidden && Date.now() - B.lastActive < 120000 && !(alongHere() && C.Player.playing()) && (!C.Split || C.Split.mine());
  if (reading) C.sendBeat({ book_id: B.d.id, seconds: 15, at: Math.floor(Date.now() / 1000) });
  const c = $('#bcounting'); if (c) c.classList.toggle('off', !reading);
}, 15000);
document.addEventListener('visibilitychange', () => { if (document.hidden && B.view) savePosition(true); });
window.addEventListener('pagehide', () => { if (B.view) savePosition(true); });
window.addEventListener('resize', () => { clearTimeout(B.rsT); B.rsT = setTimeout(() => { applyBookType(); if (B.d && $('#btop')) drawTop(); }, 200); });
// The phone's slider: drag to anywhere in the book.
document.addEventListener('input', e => { if (e.target.id !== 'bslide') return; B.sliding = true; const st = $('#bslidet'); if (st) st.textContent = Math.round(e.target.value / 10) + '%'; });
document.addEventListener('change', e => { if (e.target.id !== 'bslide' || !B.view) return; B.view.goToFraction(e.target.value / 1000).catch(() => {}).finally(() => { B.sliding = false; }); });
window.addEventListener('hashchange', () => { if (!location.hash.startsWith('#ebook/')) { cleanup(); document.body.classList.remove('btocsheet', 'bpanelsheet', 'bookbare'); } });

C.views.ebook = args => {
  const id = decodeURIComponent(args[0] || ''), at = args[1] ? decodeURIComponent(args.slice(1).join('/')) : null;
  if (B.id === id && B.view) {
    H.active = ACT;
    if (at && at.startsWith('hl:')) { const h = findHl(at.slice(3)); if (h) return jumpTo(h); }
    else if (at && at.startsWith('q:')) return goToWords(decodeURIComponent(at.slice(2)));
    else if (at) return B.view.goTo(at).catch(() => {});
    return;
  }
  return openBook(id, at);
};
C.curBook = () => (C.S.route[0] === 'ebook' ? B.id : null);
// For the audiobook beside the book (audiobooks.js): the page you're on, and going to a place by its words.
C.BookPlace = {
  here: () => B.id && B.loc ? { cfi: B.loc.cfi, fraction: B.loc.fraction || 0, text: B.loc.range ? String(B.loc.range).slice(0, 600) : '' } : null,
  go: async (words, fraction) => {
    const cfi = words ? await findText(words) : null;
    if (cfi) { await B.view.goTo(cfi).catch(() => {}); centerIt(); } else if (fraction >= 0) await B.view.goToFraction(fraction).catch(() => {});
  },
};
window.dispatchEvent(new Event('daf-ebook-ready'));
