/* Daf book reader: EPUB (and MOBI/AZW3/FB2) from Calibre, rendered by foliate-js, inside
   Daf's reading view. Contents, bookmarks and search on the left, Info / Notebook / Ask on the
   right, highlights anchored by CFI, the Kindle's highlights placed by KOReader's own position,
   the position kept on the server so phone and desktop agree, and time with a book open counting
   toward the hour. */
import './vendor/foliate-js/view.js';
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
};
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
    aside[epub|type~="footnote"], aside[epub|type~="endnote"], aside[epub|type~="rearnote"] { display: none; }
    ${(t.flow || 'scrolled') === 'scrolled' ? 'body { padding-bottom: 72px !important; }   /* room under the last line for Next */' : ''}
    @namespace epub "http://www.idpf.org/2007/ops";
  `];
}
function applyBookType(){
  const v = B.view; if (!v || !v.renderer) return;
  const t = C.typeFor ? C.typeFor(B.id) : store.get('type', {});
  const flow = t.flow || 'scrolled';   // like the feeds; Aa → Layout → Pages for page turns
  v.renderer.setAttribute('flow', flow);
  v.renderer.setAttribute('max-inline-size', Math.round((t.measure || 38) * 16 * ((t.size || 20) / 20)) + 'px');
  v.renderer.setAttribute('max-column-count', flow === 'paginated' && window.innerWidth >= 1280 && !B.panelOpen ? '2' : '1');
  v.renderer.setAttribute('gap', '6%');
  v.renderer.setAttribute('margin', window.innerWidth < 760 ? '24px' : '40px');
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
    '<div class="rvgrid' + (B.tocOpen && window.innerWidth > 1000 ? '' : ' notoc') + (B.panelOpen && window.innerWidth > 1000 ? ' withpanel' : '') + '" id="bgrid"><nav class="toc btoc" id="btoc" aria-label="Contents"></nav>' +
    '<div class="docwrap bookwrap"><div id="bnotice"></div><div class="bookstage" id="bstage"><div class="bookload mute">Opening the book…</div></div><div class="bookfoot" id="bfoot"></div></div>' +
    '<aside class="rpanel" id="bpanel"></aside></div></div>';
  // The file starts coming at once, beside the book's details: from the device when it's been
  // opened before (sw.js), else from Daf.
  const fileUrl = '/api/ebooks/' + encodeURIComponent(id) + '/file';
  const fileP = fetch(fileUrl, { credentials: 'same-origin' });
  fileP.catch(() => {});
  let d;
  try { d = await api('/api/ebooks/' + encodeURIComponent(id)); }
  catch(e){ $('#bstage').innerHTML = '<div class="placeholder">' + esc(e.message) + ' <a href="#book/' + encodeURIComponent(id) + '">Back to the book</a></div>'; return; }
  if (B.id !== id) return;
  B.d = d;
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
  try { await view.open(file); }
  catch(e){ $('#bstage').innerHTML = '<div class="placeholder">This file wouldn’t open: ' + esc(e.message || String(e)) + '</div>'; return; }
  if (B.id !== id) { view.close?.(); return; }
  view.addEventListener('load', onSectionLoad);
  view.addEventListener('relocate', onRelocate);
  view.addEventListener('create-overlay', e => {
    const { index } = e.detail;
    for (const h of d.highlights) if (h.index === index) view.addAnnotation({ value: h.pos.cfi });
    markKindle(index);
    inkSection(index);
  });
  view.addEventListener('draw-annotation', e => {
    const { draw, annotation, range } = e.detail, v = annotation.value;
    if (INK.by.has(v)) { draw(inkDraw, { cfi: v, range }); return; }
    const h = B.kindleByCfi.get(v) || B.byCfi.get(v);
    draw(H.draw, { range, color: (h && h.color) || 'yellow', note: !!(h && (h.user_note || h.note)), flash: B.flash === v, soft: !h && B.temp.has(v) });
  });
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
  applyBookType();
  drawToc();
  Pens.use(INKSURF);
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
}
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
  if (!B.view) return;
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
  Object.assign(T, { on: true, playing: true, els, i: start, index: c.index });
  if (!C.Voices.cur) C.Voices.load().then(() => { if (T.on) drawPlayer(); });
  drawPlayer(); playPara();
}
// Another voice chosen while it reads: the paragraph starts again in it.
window.addEventListener('daf-voice', () => { const T = B.tts; T.cache = null; if (T.on) playPara(); });
async function playPara(){
  const T = B.tts; if (!T.on) return;
  if (T.sleepAt && Date.now() > T.sleepAt) { stopListen(); toast('Sleep timer: stopped reading'); return; }
  if (T.i >= T.els.length) {             // end of the section: on to the next one
    const next = (T.index ?? 0) + 1;
    if (!B.view.book.sections[next]) { stopListen(); return; }
    await B.view.goTo(next).catch(() => {});
    const c = B.view.renderer.getContents()[0]; if (!c) { stopListen(); return; }
    T.els = paragraphs(c.doc); T.i = 0; T.index = c.index;
    if (!T.els.length) { T.i = 0; T.els = []; return playPara(); }
  }
  const el = T.els[T.i];
  T.els.forEach(x => x.classList.remove('daf-speaking')); el.classList.add('daf-speaking');
  try { const rg = el.ownerDocument.createRange(); rg.selectNodeContents(el); B.view.renderer.scrollToAnchor?.(rg); } catch(e){}
  B.lastActive = Date.now();
  try {
    const url = T.cache && T.cache.i === T.i && T.cache.index === T.index ? T.cache.url : await speech(el.textContent.replace(/\s+/g, ' ').trim());
    if (!T.on) return;
    if (T.audio) T.audio.pause();
    T.audio = new Audio(url); T.audio.playbackRate = T.rate;
    if (T.unfollow) T.unfollow();
    T.unfollow = H.follow(T.audio, el);
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
  const p = $('#bplayer'); if (p) p.remove();
  if (B.loc) onRelocate({ detail: B.loc });
}
function drawPlayer(){
  const T = B.tts; if (!T.on) return;
  let p = $('#bplayer');
  if (!p) { p = document.createElement('div'); p.id = 'bplayer'; p.className = 'bplayer'; $('#bfoot').replaceChildren(p); }
  const left = T.sleepAt ? Math.max(0, Math.round((T.sleepAt - Date.now()) / 60000)) : 0;
  p.innerHTML = '<button class="btn sm" data-bt="prev" aria-label="Previous paragraph">‹ ¶</button><button class="round" data-bt="play" aria-label="' + (T.playing ? 'Pause' : 'Play') + '">' + (T.playing ? '❚❚' : '▶') + '</button><button class="btn sm" data-bt="next" aria-label="Next paragraph">¶ ›</button>' +
    '<button class="btn sm" data-bt="rate">' + T.rate + '×</button><button class="btn sm" data-bt="voice" aria-label="Voice: ' + esc(C.Voices.cur ? C.Voices.label(C.Voices.cur) : 'choose one') + '">' + esc(C.Voices.cur ? C.Voices.name(C.Voices.cur) : 'Voice') + '</button><button class="btn sm" data-bt="sleep">' + (T.sleepAt ? 'Sleep in ' + left + ' min' : 'Sleep timer') + '</button><span class="spacer"></span><span class="mute tiny">Kokoro · counts as reading</span><button class="ib" data-bt="stop" aria-label="Stop">×</button>';
}
function cleanup(){
  inkFlush();
  if (B.tts && B.tts.on) stopListen();
  closeNote(); wake(false); H.hide();
  if (B.view) { try { savePosition(true); } catch(e){} try { B.view.close(); } catch(e){} B.view.remove(); }
  B.view = null; B.id = null; B.d = null;
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
  const active = () => { B.lastActive = Date.now(); };
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
    if (window.innerWidth >= 1000 && !(C.Focus && C.Focus.on())) return;
    // the sides turn the page, in Scroll too (a screen at a time, then on into the next chapter);
    // not when the tap was on a highlight and opened its bar
    const fx = (doc.defaultView.frameElement.getBoundingClientRect().left + ev.clientX) / window.innerWidth;
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
function toggleChrome(){ if (C.Focus && C.Focus.on()) { C.Focus.bar(); return; } B.chrome = !B.chrome; document.body.classList.toggle('bookbare', !B.chrome); }

// Pages for page goals: a page counts once it has been on screen for five seconds, the way
// KOReader counts the Kindle's. The printed page when the book has one, else foliate's location.
function notePage(l){
  const key = l.pageItem && l.pageItem.label ? 'p' + l.pageItem.label : l.location && l.location.current != null ? 'l' + l.location.current : null;
  const now = Date.now();
  if (B.pageKey && B.pageKey !== key && now - (B.pageAt || now) >= 5000) (B.pagesNew = B.pagesNew || new Set()).add(B.pageKey);
  if (B.pageKey !== key) { B.pageKey = key; B.pageAt = now; }
}
function onRelocate(e){
  const l = e.detail; B.loc = l; notePage(l); drawNextChapter(l);
  followBar();
  if (B.forget && Date.now() - (B.forgetAt || 0) > 2000) B.forget = false;   // reading on after Forget: the place counts again
  const pct = Math.round((l.fraction || 0) * 100);
  const p = $('#rprog'); if (p) p.style.width = pct + '%';
  const ch = l.tocItem?.label || '';
  const f = $('#bfoot');
  if (f && !B.tts.on && !f.querySelector('#bjump')) f.innerHTML = '<span class="bch"' + (isRtlText(ch) ? ' dir="rtl"' : '') + '>' + esc(ch) + '</span><span class="spacer"></span>' +
    (l.time ? (l.time.section > 0.5 ? '<span class="mute">' + fmtMins(l.time.section) + ' left in the chapter</span>' : '') + '<span class="mute bleft"> · ' + fmtMins(l.time.total) + ' left in the book</span>' : '') +
    (l.pageItem && l.pageItem.label ? '<span class="mute bpage" title="The printed book’s page"> · p. ' + esc(l.pageItem.label) + '</span>' : '') +
    '<button class="bpct" data-bk="jump" title="Go to a percent">' + pct + '%</button>';
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
  if (B.panel === 'info' && B.panelOpen) drawPanelInfoProgress();
}
function savePosition(now){
  const l = B.loc, id = B.id; if (!l || !l.cfi || !id || B.forget) return;
  const body = { cfi: l.cfi, fraction: l.fraction || 0, chapter: l.tocItem?.label || null };
  store.set('bookpos.' + id, { ...body, at: Math.floor(Date.now() / 1000) });
  if (now && B.pageKey && Date.now() - (B.pageAt || 0) >= 5000) (B.pagesNew = B.pagesNew || new Set()).add(B.pageKey);
  if (B.pagesNew && B.pagesNew.size) { body.pages = [...B.pagesNew]; B.pagesNew = new Set(); }
  // offline (or Daf down), the place waits in the outbox with its time, so a newer one from the Kindle still wins
  const path = '/api/ebooks/' + encodeURIComponent(id) + '/position', late = () => C.outbox && C.outbox.add(path, { method: 'PUT', body: JSON.stringify(body) });
  if (C.outbox && C.outbox.get().length) { late(); C.outbox.flush(); return; }
  fetch(path, { method: 'PUT', credentials: 'same-origin', keepalive: !!now, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ...body, at: Math.floor(Date.now() / 1000) }) })
    .then(r => { if (r.status >= 500) late(); }, late);
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
function drawTop(){
  const d = B.d;
  $('#btop').innerHTML = '<a class="ib" href="#book/' + encodeURIComponent(d.id) + '" aria-label="Back to the book">' + I.back + '</a>' +
    '<button class="ib' + (B.tocOpen && window.innerWidth > 1000 ? ' on' : '') + '" data-bk="toc" title="Contents and search' + C.Keys.tip('book', 'toc') + '" aria-label="Contents">' + ICON.toc + '</button>' +
    '<button class="ib aa" data-bk="aa" aria-label="Typography and theme">Aa</button>' +

    '<span class="btitle-top mute">' + esc(String(d.title || '').split(/:\s/)[0]) + '</span><span class="spacer"></span>' +
    '<button class="ib" data-bk="bookmark" title="Bookmark this page' + C.Keys.tip('book', 'bookmark') + '" aria-label="Bookmark">' + ICON.mark(!!markHere()) + '</button>' +
    '<button class="btn sm" data-bk="listen" title="Read aloud from here">Listen</button>' +
    '<button class="ib" data-bk="more" title="More" aria-label="More">' + ICON.more + '</button>' +
    (C.Focus ? C.Focus.button('book') : '') +
    '<button class="ib' + (B.panelOpen && window.innerWidth > 1000 ? ' on' : '') + '" data-bk="panel" aria-label="Show or hide the side panel">' + ICON.panel + '</button>';
}
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
function drawPanel(){
  const p = $('#bpanel'); if (!p || !B.d) return;
  const d = B.d, all = allHighlights(), n = all.length;
  p.innerHTML = '<div class="ptabs" role="tablist">' + [['info', 'Info'], ['notebook', 'Notebook <span class="c">' + n + '</span>'], ['ask', 'Ask']].map(t => '<button class="ptab' + (B.panel === t[0] ? ' on' : '') + '" data-bpt="' + t[0] + '" role="tab">' + t[1] + '</button>').join('') + '</div><div id="bpbody"></div>';
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
      '<div class="mr"><span>Highlights</span><span>' + n + (n ? ' <button class="linkbtn" data-bpt="notebook">See them</button>' : '') + '</span></div>' +
      (d.series ? '<div class="mr"><span>Series</span><span>' + esc(d.series.name) + (d.series.index ? ' #' + (+d.series.index) : '') + (d.series.next ? '<br><a href="#ebook/' + encodeURIComponent(d.series.next.id) + '">Next: ' + esc(d.series.next.title) + '</a>' : '') + '</span></div>' : '') +
      (d.kindle ? '<div class="mr"><span>Kindle</span><span>p. ' + d.kindle.page + ' of ' + d.kindle.total + ' · ' + epochDate(d.kindle.at) + ' <button class="linkbtn" data-bk="kindle">Go there</button></span></div>' : '') +
      '</div>' + (d.vault_path ? '<span class="tiny mute">Highlights go to <code>' + esc(d.vault_path) + '</code></span>' : '<span class="tiny mute">Your first highlight here makes this book a vault note.</span>') + '</div>';
    drawPanelInfoProgress();
  } else if (B.panel === 'notebook') {
    let h = '<div class="nbhead"><span class="mute tiny">' + (n ? n + ' highlight' + (n === 1 ? '' : 's') + ', in reading order' : '') + '</span><span class="spacer"></span>' +
      (n ? '<a class="linkbtn tiny" href="/api/highlights/export?fmt=md&book=' + encodeURIComponent(d.id) + '" download>Export</a>' : '') + '</div>';
    if (!n) h += '<p class="mute">' + (H.auto() ? 'Select a passage and it’s highlighted. Hold Alt (⌥) to select without highlighting.' : 'Select text, then Highlight.') + ' Highlights here join your daily review and the book’s vault note.</p>';
    let chapter = null;
    H.rowOpts = { chapter: false, date: false };
    for (const x of all) {
      if (x.chapter && x.chapter !== chapter) { chapter = x.chapter; h += '<div class="nbch">' + esc(chapter) + '</div>'; }
      h += H.row(x, H.rowOpts);
    }
    b.innerHTML = '<div class="nbook">' + h + '</div>';
    // Open at the highlights near where you are.
    const here = B.loc ? B.loc.fraction || 0 : 0, near = all.find(x => x._k >= here - 0.002);
    if (near && here > 0.02) { const row = $('.hrow[data-h="' + CSS.escape(near.id) + '"]'); if (row) row.scrollIntoView({ block: 'start' }); }
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
    if (!quiet) H.show(H.hlBar(merged[0]), s.rect, { h: merged[0], cfi: merged[0].pos.cfi }); return null;
  }
  if (merged.length) { try { cfi = B.view.getCFI(s.index, range); text = range.toString().trim(); } catch(e){ merged.length = 0; } }
  const chapter = B.loc?.tocItem?.label || null, fraction = B.loc ? B.loc.fraction : null;
  try {
    const color = merged.find(m => m.color)?.color || H.color();
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
      if (B.panelOpen && B.panel === 'notebook') drawPanel();
    }
    const tab = $('[data-bpt="notebook"] .c'); if (tab) tab.textContent = allHighlights().length;
    return h;
  } catch(e){ toast(e.message); return null; }
}
function openNote(h){
  B.panel = 'notebook'; openPanel();
  setTimeout(() => { const row = $('.hrow[data-h="' + CSS.escape(h.id) + '"]'); if (!row) return; row.scrollIntoView({ block: 'center' }); const n = row.querySelector('[data-hra="note"]'); if (n) n.click(); }, 60);
}
// quiet: no Undo toast (the pen's eraser has its own Undo); either way it answers with the way back.
async function removeHighlight(id, quiet){
  const h = B.d.highlights.find(x => x.id === id); if (!h) return null;
  await api('/api/highlights/' + encodeURIComponent(id), { method: 'DELETE' });
  B.d.highlights = B.d.highlights.filter(x => x.id !== id); B.byCfi.delete(h.pos.cfi);
  try { await B.view.deleteAnnotation({ value: h.pos.cfi }); } catch(e){}
  drawPanel();
  const back = async () => {
    await api('/api/highlights/' + encodeURIComponent(id) + '/restore', { method: 'POST' });
    if (!B.d) return;
    B.d.highlights.push(h); B.byCfi.set(h.pos.cfi, h);
    try { await B.view.addAnnotation({ value: h.pos.cfi }); } catch(e){}
    drawPanel();
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
  const el = o.range.startContainer.nodeType === 1 ? o.range.startContainer : o.range.startContainer.parentElement;
  const f = parseFloat(win.getComputedStyle(el).fontSize) || 16;
  const layer = Pens.layer(g, lightText(win.getComputedStyle(doc.body).color));
  for (const s of list) {
    const k = f / (s.at.f || 16), x0 = r.left + s.at.x * k, y0 = r.top + s.at.y * k;
    const pts = s.pts.map(p => [x0 + p[0] * k, y0 + p[1] * k, p[2]]);
    layer.add(s, pts, k);
    let x1 = Infinity, y1 = Infinity, x2 = -Infinity, y2 = -Infinity;
    for (const p of pts) { if (p[0] < x1) x1 = p[0]; if (p[0] > x2) x2 = p[0]; if (p[1] < y1) y1 = p[1]; if (p[1] > y2) y2 = p[1]; }
    INK.geo.set(s.id, { pts, r: (s.size || 2.5) * k / 2, box: [x1, y1, x2, y2], doc });
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
  const range = letterAt(doc, x0, y0); if (!range) return;
  let cfi; try { cfi = B.view.getCFI(index, range); } catch(e){ return; }
  const r = range.getClientRects()[0] || range.getBoundingClientRect();
  const f = parseFloat(doc.defaultView.getComputedStyle(range.startContainer.parentElement).fontSize) || 16, b = L.brush;
  const s = { id: inkId(), v: 2, tool: b.pen, color: b.color, size: r1(b.w), o: Math.round(b.opacity * 100) / 100,
    at: { cfi, s: index, f, x: r1(x0 - r.left), y: r1(y0 - r.top) }, pts: L.pts.map(p => [r1(p[0] - wx), r1(p[1] - wy), Math.round(p[2] * 100) / 100]) };
  inkAdd([s]); inkAct({ add: [s] });
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
    if (px < b[0] - m || px > b[2] + m || py < b[1] - m || py > b[3] + m || !inkNear(g.pts, px, py, m)) continue;
    const s = inkAll().find(t => t.id === id); if (!s) { INK.geo.delete(id); continue; }
    const mine = L.added.indexOf(s);
    if (mine >= 0) L.added.splice(mine, 1); else L.erased.push(s);
    const pieces = [];
    if (mode === 'area') {
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
  snapRange(range);
  const text = range.toString().trim(); if (text.replace(/\s/g, '').length < 2) return false;
  let cfi; try { cfi = B.view.getCFI(index, range); } catch(e){ return false; }
  const block = range.startContainer.parentElement?.closest('p, li, blockquote, div') || range.startContainer.parentElement;
  B.sel = { doc, index, range, text, cfi, rect: rectFor(doc, range), sentence: block ? block.textContent : text };
  highlightSel(false, true).then(h => { if (h) inkAct({ hl: h.id }); });
  return true;
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
const INKSURF = {
  live: () => !!(B.view && B.d && document.body.dataset.view === 'ebook'),
  takes: (el, doc) => doc !== document,
  off: doc => { const r = frameOf(doc); return r ? [r.left, r.top] : [0, 0]; },
  stroke: inkStroke, erase: inkErase, erased: inkErased, eraseAll: inkEraseAll, highlight: inkHighlight,
  palHost: () => document.querySelector('.rv.ebook') || document.body,
  canUndo: () => INK.done.length > 0, canRedo: () => INK.undone.length > 0, undo: inkUndo, redo: inkRedo,
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
function openPanel(){
  B.panelOpen = true; store.set('bookPanel', true);
  const g = $('#bgrid'); if (g) g.classList.add('withpanel');
  if (window.innerWidth <= 1000) document.body.classList.add('bpanelsheet');
  drawPanel(); drawTop(); applyBookType();
}
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
  notebook: ctx => { H.hide(); B.panel = 'notebook'; openPanel(); setTimeout(() => H.flash($('.hrow[data-h="' + CSS.escape(ctx.h.id) + '"]')), 60); },
  changed: h => { const cfi = h.pos && h.pos.cfi || h.cfi; if (cfi && B.view) B.view.addAnnotation({ value: cfi }).catch(() => {}); if (B.panel === 'notebook' && B.panelOpen) drawPanel(); },
  deselect: () => { B.sel && B.sel.doc.getSelection()?.removeAllRanges(); },
  meta: () => ({ title: B.d && B.d.title, author: B.d && B.d.author }),
};
window.addEventListener('daf-hl-changed', e => { if (C.S.route[0] === 'ebook' && B.d) { const h = findHl(e.detail.id); if (h) { Object.assign(h, e.detail); ACT.changed(h); } } });

/* ---------- more menu, keys ---------- */
function openMore(anchor){
  const p = $('#pop'), r = anchor.getBoundingClientRect();
  p.innerHTML = '<div class="menu">' +
    '<button data-bm="start">Go to the beginning</button>' +
    '<button data-bm="kindle"' + (B.d.kindle ? '' : ' disabled') + '>Go to the Kindle’s page</button>' +
    '<button data-bm="mark">' + (markHere() ? 'Remove the bookmark' : 'Bookmark this page') + '<span class="kbd">b</span></button>' +
    '<button data-bm="book">Book page, notes and nightstand</button>' +
    '<a href="/api/highlights/export?fmt=md&book=' + encodeURIComponent(B.d.id) + '" download>Export highlights (Markdown)</a>' +
    '<a href="/api/ebooks/' + encodeURIComponent(B.d.id) + '/file" download>Download the file</a>' +
    '<button data-bm="auto"><span><span class="ck">' + (H.auto() ? '✓' : '') + '</span>Auto highlight</span></button>' +
    '<button data-bm="keys">Keyboard shortcuts<span class="kbd">?</span></button>' +
    '<button data-bm="reset">Forget my place in Daf</button>' +
    (phoneKeeps() ? '<button data-bm="offline" disabled>Keep on this device</button>' : '') + '</div>';
  p.hidden = false; p.style.left = Math.max(8, Math.min(window.innerWidth - 280, r.right - 260)) + 'px'; p.style.top = (r.bottom + 8) + 'px';
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
  if (tag === 'input' || tag === 'textarea') { if (e.key === 'Escape') e.target.blur(); return; }
  if (e.metaKey || e.ctrlKey || e.altKey) return;
  if (!$('#modal').hidden) return;
  const k = e.key, is = a => C.Keys.is(e, 'book', a), paged = document.body.dataset.flow === 'paginated';
  if (is('next') || (k === ' ' && paged && !e.shiftKey)) { e.preventDefault(); B.view.goRight(); }
  else if (is('prev') || (k === ' ' && e.shiftKey && paged)) { e.preventDefault(); B.view.goLeft(); }
  else if (is('highlight') && B.sel && H.ctx && H.ctx.kind === 'sel') highlightSel(false);
  else if (is('note') && B.sel && H.ctx && H.ctx.kind === 'sel') highlightSel(true);
  else if (is('bookmark')) toggleMark();
  else if (is('toc')) click('toc');
  else if (is('listen')) click('listen');
  else if (k === '?') showKeys();
  else if (is('search')) { e.preventDefault(); if (!B.tocOpen) click('toc'); setTimeout(() => $('#bq') && $('#bq').focus(), 30); }
  else if (is('panel')) click('panel');
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
  const bk = t.closest('[data-bk]');
  if (bk) {
    const a = bk.dataset.bk;
    if (a === 'nextch') { bk.hidden = true; B.view.next(); return; }
    if (a === 'toc') {
      if (window.innerWidth <= 1000) { document.body.classList.toggle('btocsheet'); return; }
      B.tocOpen = !B.tocOpen; store.set('bookToc', B.tocOpen); $('#bgrid').classList.toggle('notoc', !B.tocOpen); drawTop(); applyBookType();
    } else if (a === 'panel') {
      if (window.innerWidth <= 1000) { document.body.classList.toggle('bpanelsheet'); if (document.body.classList.contains('bpanelsheet')) drawPanel(); return; }
      B.panelOpen = !B.panelOpen; store.set('bookPanel', B.panelOpen); $('#bgrid').classList.toggle('withpanel', B.panelOpen); drawTop(); applyBookType(); if (B.panelOpen) drawPanel();
    } else if (a === 'aa') { C.openAa && C.openAa(bk, { book: true }); }
    else if (a === 'more') openMore(bk);
    else if (a === 'bookmark') toggleMark();
    else if (a === 'kindle' && B.d.kindle) { $('#bnotice').innerHTML = ''; await B.view.goToFraction(B.d.kindle.fraction); toast('At the Kindle’s page, about ' + Math.round(B.d.kindle.fraction * 100) + '% in'); }
    else if (a === 'nokindle') $('#bnotice').innerHTML = '';
    else if (a === 'hcdone') { bk.closest('.bnotice').remove(); C.HC.finish(B.d.id, B.d.title); }
    else if (a === 'hcno') bk.closest('.bnotice').remove();
    else if (a === 'listen') { if (B.tts.on) stopListen(); else startListen(); }
    else if (a === 'closenote') closeNote();
    else if (a === 'jump') {
      const f = $('#bfoot'); f.innerHTML = '<span class="mute">Go to</span><input id="bjump" class="field" inputmode="decimal" placeholder="45" style="width:80px"><span class="mute">%</span><span class="spacer"></span><button class="btn sm" data-bk="jumpcancel">Cancel</button>';
      $('#bjump').focus();
    } else if (a === 'jumpcancel') { $('#bfoot').innerHTML = ''; if (B.loc) onRelocate({ detail: B.loc }); }
    else if (a === 'ask') { const q = $('#bask').value.trim(); if (q) { $('#bask').value = ''; ask(q, null); } }
    return;
  }
  const bt = t.closest('[data-bt]');
  if (bt) {
    const T = B.tts, a = bt.dataset.bt;
    if (a === 'play') { T.playing = !T.playing; if (T.audio) T.playing ? T.audio.play() : T.audio.pause(); drawPlayer(); }
    else if (a === 'next') { T.i++; T.cache = null; playPara(); }
    else if (a === 'prev') { T.i = Math.max(0, T.i - 1); T.cache = null; playPara(); }
    else if (a === 'voice') C.Voices.menu(bt);
    else if (a === 'rate') { T.rate = T.rate >= 2 ? 0.75 : Math.round((T.rate + 0.25) * 100) / 100; if (T.audio) T.audio.playbackRate = T.rate; drawPlayer(); }
    else if (a === 'sleep') { const steps = [0, 15, 30, 45, 60], cur = T.sleepAt ? Math.round((T.sleepAt - Date.now()) / 60000) : 0; const nx = steps.find(m => m > cur + 1) || 0; T.sleepAt = nx ? Date.now() + nx * 60000 : 0; drawPlayer(); }
    else if (a === 'stop') stopListen();
    return;
  }
  if (!t.closest('#fnote') && $('#fnote') && !$('#fnote').hidden) closeNote();
  const pt = t.closest('[data-bpt]'); if (pt) { B.panel = pt.dataset.bpt; drawPanel(); return; }
  const ti = t.closest('#btoc [data-href]'); if (ti) { e.preventDefault(); await B.view.goTo(ti.dataset.href).catch(() => {}); document.body.classList.remove('btocsheet'); return; }
  const sr = t.closest('#bres [data-cfi]'); if (sr) { e.preventDefault(); await B.view.goTo(sr.dataset.cfi).catch(() => {}); document.body.classList.remove('btocsheet'); return; }
  const gm = t.closest('[data-gomark]'); if (gm) { e.preventDefault(); await B.view.goTo(gm.dataset.gomark).catch(() => {}); document.body.classList.remove('btocsheet'); return; }
  const bm = t.closest('[data-bm]');
  if (bm) {
    $('#pop').hidden = true;
    const a = bm.dataset.bm;
    if (a === 'start') await B.view.goToTextStart().catch(() => {});
    else if (a === 'kindle' && B.d.kindle) await B.view.goToFraction(B.d.kindle.fraction);
    else if (a === 'mark') toggleMark();
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
  const v = parseFloat(e.target.value); if (isNaN(v)) return;
  $('#bfoot').innerHTML = ''; B.view.goToFraction(Math.max(0, Math.min(100, v)) / 100).catch(() => {});
});
let qT = null;
document.addEventListener('input', e => { if (e.target.id === 'bq') { clearTimeout(qT); qT = setTimeout(() => runSearch(e.target.value), 300); } });

/* ---------- reading time ---------- */
setInterval(() => {
  const reading = C.S.route[0] === 'ebook' && B.view && B.d && !document.hidden && Date.now() - B.lastActive < 120000;
  if (reading) C.sendBeat({ book_id: B.d.id, seconds: 15, at: Math.floor(Date.now() / 1000) });
  const c = $('#bcounting'); if (c) c.classList.toggle('off', !reading);
}, 15000);
document.addEventListener('visibilitychange', () => { if (document.hidden && B.view) savePosition(true); });
window.addEventListener('pagehide', () => { if (B.view) savePosition(true); });
window.addEventListener('resize', () => { clearTimeout(B.rsT); B.rsT = setTimeout(applyBookType, 200); });
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
window.dispatchEvent(new Event('daf-ebook-ready'));
