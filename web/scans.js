/* Books made of pictures of their pages: a scanned book turned into an EPUB (pdftohtml and the
   like), where every page is a picture and there are hardly any words. book.js asks detect() as
   such a book opens, and the book reads like the printed one:
   - each picture is a page of its own, as big as the screen allows, with nothing round it; the
     little spacer pictures between them go;
   - on a screen wider than tall two pages face each other and meet in the middle, the odd pages
     on the right (a cover the same as the book's own cover comes before page 1);
   - the page numbers are the pictures' (after the cover), so a spread counts both of its pages;
   - a double tap or a pinch brings the page up close, to pan round; a tap, a pinch back or Back
     puts it away.
   Pages face each other within a section: foliate shows one section at a time, so a book with a
   page a section has them one at a time, in the middle.
   The book is still foliate's, one CFI-addressed section after another, so its place, its
   progress, the Kindle's page and the time read work as for any other book. Words are what a
   book's progress and time left are measured in, so here a page counts as a page's worth. */
(function(){
'use strict';
const C = window.DafCore;
const store = { get(k, d){ try { const v = localStorage.getItem('daf.' + k); return v == null ? d : JSON.parse(v); } catch(e){ return d; } }, set(k, v){ try { localStorage.setItem('daf.' + k, JSON.stringify(v)); } catch(e){} } };
const XLINK = 'http://www.w3.org/1999/xlink';
const PAGE = 200;        // px: a picture at least this big each way is a page; a smaller one is an ornament or a spacer
const BIG = 16384;       // bytes: a file this size is a picture of a page without looking inside it
const WEIGHT = 1500;     // a page's share of the book, in foliate's units, so its "location" is the page

/* ---------- is it a book of pictures? ---------- */
// A picture's size from the start of its file (PNG, GIF, JPEG, WebP), without drawing it.
function dims(b){
  const u16 = i => b[i] << 8 | b[i + 1], u32 = i => (b[i] << 24 | b[i + 1] << 16 | b[i + 2] << 8 | b[i + 3]) >>> 0;
  if (b[0] === 0x89 && b[1] === 0x50) return [u32(16), u32(20)];
  if (b[0] === 0x47 && b[1] === 0x49) return [b[6] | b[7] << 8, b[8] | b[9] << 8];
  if (b[0] === 0xFF && b[1] === 0xD8) {
    for (let i = 2; i + 9 < b.length;) {
      if (b[i] !== 0xFF || b[i + 1] === 0xFF) { i++; continue; }
      const m = b[i + 1];
      if (m >= 0xC0 && m <= 0xCF && m !== 0xC4 && m !== 0xC8 && m !== 0xCC) return [u16(i + 7), u16(i + 5)];
      i += 2 + u16(i + 2);
    }
    return null;
  }
  if (b[8] === 0x57 && b[9] === 0x45 && b[12] === 0x56) {
    const k = String.fromCharCode(b[15]);
    if (k === 'X') return [1 + (b[24] | b[25] << 8 | b[26] << 16), 1 + (b[27] | b[28] << 8 | b[29] << 16)];
    if (k === 'L') { const n = (b[21] | b[22] << 8 | b[23] << 16 | b[24] << 24) >>> 0; return [(n & 0x3fff) + 1, (n >> 14 & 0x3fff) + 1]; }
    return [(b[26] | b[27] << 8) & 0x3fff, (b[28] | b[29] << 8) & 0x3fff];
  }
  return null;
}
const srcOf = el => el.getAttribute('src') || el.getAttributeNS(XLINK, 'href') || el.getAttribute('href') || '';
// What a picture in the book is: a page, or something small (an ornament; a spacer when tiny).
async function kindOf(book, href){
  const size = (() => { try { return book.getSize(href) || 0; } catch(e){ return 0; } })();
  if (size >= BIG) return { kind: 'page' };
  try {
    const blob = await book.loadBlob(href), d = blob && dims(new Uint8Array(await blob.slice(0, 65536).arrayBuffer()));
    if (d) return { kind: d[0] >= PAGE && d[1] >= PAGE ? 'page' : 'small', tiny: d[0] <= 4 || d[1] <= 4 };
  } catch(e){}
  return { kind: 'small' };
}
// Two pictures that are the same picture, give or take the crop and the compression: an 8×8 grey
// thumbnail of each (the average of 64×64), levelled, a few greys apart on average. The cover and
// a scan's first page come out about 7 apart, two different pages 30 and more.
async function thumb(blob){
  const bm = await createImageBitmap(blob), c = document.createElement('canvas'); c.width = c.height = 64;
  const x = c.getContext('2d', { willReadFrequently: true }); x.imageSmoothingQuality = 'high';
  x.drawImage(bm, 0, 0, 64, 64); if (bm.close) bm.close();
  const d = x.getImageData(0, 0, 64, 64).data, g = new Array(64).fill(0);
  for (let i = 0; i < d.length; i += 4) { const p = i / 4; g[(p >> 9) * 8 + (p % 64 >> 3)] += (d[i] * .3 + d[i + 1] * .59 + d[i + 2] * .11) / 64; }
  const m = g.reduce((a, v) => a + v, 0) / 64;
  return g.map(v => v - m);
}
async function alike(book, a, b){
  try {
    const [x, y] = await Promise.all([a, b].map(async h => thumb(await book.loadBlob(h))));
    return x.reduce((s, v, i) => s + Math.abs(v - y[i]), 0) / x.length < 16;
  } catch(e){ return false; }
}

// The book as foliate has it (before it's open): null unless nearly all of it is pictures of pages.
async function detect(book, id){
  try {
    const R = book.resources;
    if (!R || !R.manifest || !book.sections || (book.rendition && book.rendition.layout === 'pre-paginated')) return null;
    const pics = R.manifest.filter(x => /^image\//.test(x.mediaType || '')).length;
    const linear = book.sections.filter(s => s.linear !== 'no');
    // a book of words with a few pictures goes no further: fewer pictures than chapters, or more
    // text in the files than a few lines of markup a picture
    if (pics < 4 || pics * 2 < linear.length || linear.reduce((a, s) => a + (s.size || 0), 0) > pics * 4000) return null;
    const secs = [], pages = [], kinds = new Map(); let text = 0;
    for (const [i, s] of book.sections.entries()) {
      if (s.linear === 'no' || !s.createDocument) { secs.push(null); continue; }
      const doc = await s.createDocument();
      const list = [];
      for (const el of doc.querySelectorAll('img, image')) {
        const href = s.resolveHref ? s.resolveHref(srcOf(el)) : srcOf(el);
        if (!kinds.has(href)) kinds.set(href, await kindOf(book, href));
        const p = Object.assign({ href }, kinds.get(href));
        if (p.kind === 'page') { p.k = pages.length; pages.push(p); }
        list.push(p);
      }
      const words = ((doc.body || doc.documentElement).textContent || '').replace(/\s+/g, '').length;
      text += words;
      if (text > pics * 150) return null;                            // words already, more than the pictures could be pages of
      secs.push({ pics: list, pages: list.filter(p => p.kind === 'page').length, words });
    }
    // a real page of words is 1500 letters and more: a book under a tenth of that a picture is pictures
    if (pages.length < 4 || text > pages.length * 150) return null;
    // A page's worth of the book each, so the percent goes a page at a time (and not by the size of the files)
    book.sections.forEach((s, i) => { const x = secs[i]; if (x) s.size = x.pages * WEIGHT + x.words; });
    // Page 1 comes after the cover: the book's own cover picture, and a first page that is the same picture.
    const cover = R.cover && R.cover.href;
    let first = 0;
    while (first < pages.length && cover && pages[first].href === cover) first++;
    if (cover && first < pages.length && await alike(book, cover, pages[first].href)) first++;
    return make(book, id, secs, first);
  } catch(e){ console.warn('scans', e); return null; }
}

/* ---------- the pages on the screen ---------- */
// Only in a book of pictures: [data-daf-page] holds one page's picture ([data-daf-pic]), and is a
// page of the columns, a screen high; [data-daf-blank] has an empty page before it, to bring its
// picture to the side of the spread it belongs on; [data-daf-side] is that side. A pixel under the
// screen's height: the page's own height has a fraction a vh rounds up, and then wouldn't fit; and
// each page starts a column, so its anchor (where the contents go) isn't left in that last pixel.
// What's hidden ([data-daf-hide], the spacers) keeps its place with no height: with none at all it
// would seem to be on the first screen, and foliate would take that screen to reach to it.
const CSS_PAGES = `
  html[data-daf-pages] body { margin: 0 !important; padding: 0 !important; }
  [data-daf-page], [data-daf-in] { display: block !important; margin: 0 !important; padding: 0 !important; border: 0 !important; height: auto !important; min-height: 0 !important; max-height: none !important; text-indent: 0 !important; font-size: 0 !important; line-height: 0 !important; text-align: center !important; float: none !important; position: static !important; }
  [data-daf-pic] { display: block !important; margin: 0 !important; padding: 0 !important; border: 0 !important; width: 100% !important; height: calc(100vh - 1px) !important; object-fit: contain; object-position: center; float: none !important; }
  html[data-daf-flow="paginated"] :is([data-daf-page], body > [data-daf-pic]) { break-before: column; }
  html[data-daf-two] [data-daf-blank]::before { content: ''; display: block; height: calc(100vh - 1px); }
  html[data-daf-two] [data-daf-side="l"] img[data-daf-pic] { object-position: right center; }
  html[data-daf-two] [data-daf-side="r"] img[data-daf-pic] { object-position: left center; }
  html[data-daf-flow="scrolled"] [data-daf-pic] { height: auto !important; }
  html[data-daf-flow="scrolled"] [data-daf-page] { margin-bottom: 8px !important; }
  [data-daf-hide] { display: block !important; height: 0 !important; min-height: 0 !important; margin: 0 !important; padding: 0 !important; border: 0 !important; overflow: hidden !important; }
`;

function make(book, id, secs, first){
  const S = { view: null, base: null, docs: new WeakMap(), shift: store.get('scanShift.' + id, 0) ? 1 : 0 };
  const num = k => k - first + 1 - S.shift;      // the page's number: page 1 after the cover
  // The picture's block: up from the picture while the element round it holds nothing else.
  const blockOf = (el, body) => {
    let b = el;
    const only = (p, c) => [...p.querySelectorAll('img, svg, video')].every(m => m === c || c.contains(m)) &&
      (p.textContent || '').replace(/\s+/g, '') === (c.textContent || '').replace(/\s+/g, '');
    while (b.parentElement && b.parentElement !== body && only(b.parentElement, b)) b = b.parentElement;
    return b;
  };
  // Each section as it loads: its pages marked (it has the same pictures in the same order as when
  // detect() read it), the spacers hidden, and the screen laid out for it.
  function load({ doc, index }){
    const sec = secs[index], root = doc.documentElement;
    if (!sec || !sec.pages) { root.removeAttribute('data-daf-pages'); fit(index, doc); return; }
    root.setAttribute('data-daf-pages', '');
    const els = [...doc.querySelectorAll('img, image')], same = els.length === sec.pics.length, list = [];
    els.forEach((el, i) => {
      const p = same ? sec.pics[i] : { kind: el.naturalWidth >= PAGE && el.naturalHeight >= PAGE ? 'page' : 'small', tiny: el.naturalWidth <= 4 || el.naturalHeight <= 4 };
      const pic = el.localName === 'image' ? el.closest('svg') || el : el;
      const block = blockOf(pic, doc.body);
      if (p.kind !== 'page') { if (p.tiny && block !== doc.body) block.setAttribute('data-daf-hide', ''); return; }
      pic.setAttribute('data-daf-pic', '');
      if (pic.localName === 'svg') pic.setAttribute('preserveAspectRatio', 'xMidYMid meet');
      if (block !== pic) { block.setAttribute('data-daf-page', ''); for (let a = pic.parentElement; a && a !== block; a = a.parentElement) a.setAttribute('data-daf-in', ''); }
      list.push({ el: block, pic, k: same ? p.k : null });
    });
    // numbered from where detect() counted them; pictures it didn't see go on from the one before
    list.forEach((b, i) => { if (b.k == null) b.k = i ? list[i - 1].k + 1 : 0; });
    // what's left between the pages with nothing in it (an empty paragraph, a line break) would be a page of its own
    for (const el of doc.body.children)
      if (!el.hasAttribute('data-daf-page') && !el.querySelector('[data-daf-page], [data-daf-pic], img, svg, video') && !el.hasAttribute('data-daf-pic') && !(el.textContent || '').trim()) el.setAttribute('data-daf-hide', '');
    S.docs.set(doc, list);
    wire(doc);
    fit(index, doc);
  }
  // Which side of the spread each page goes on (its number: odd on the right), and the empty page
  // before one that would otherwise come on the wrong side.
  function sides(doc, two){
    const list = S.docs.get(doc); if (!list) return;
    const rtl = doc.defaultView.getComputedStyle(doc.body).direction === 'rtl';
    let col = 0;
    for (const b of list) {
      b.el.removeAttribute('data-daf-blank');
      const n = num(b.k), can = b.el !== b.pic;
      if (two && can && (col & 1) !== (n & 1)) { b.el.setAttribute('data-daf-blank', ''); col++; }
      // the first column of a spread is the left one, or the right one in a right-to-left book
      b.side = !two ? 'c' : ((col & 1) === 0) !== rtl ? 'l' : 'r';
      if (can) b.el.setAttribute('data-daf-side', b.side);
      if (b.pic.localName === 'svg') b.pic.setAttribute('preserveAspectRatio', (b.side === 'l' ? 'xMax' : b.side === 'r' ? 'xMin' : 'xMid') + 'YMid meet');
      col++;
    }
  }
  // The section's own layout: no margins and no gap round the pages, and two columns only where
  // two pages can face each other (a section of one picture has it alone, in the middle). Only the
  // paginator's custom properties change here, which need no new layout (a section is still loading).
  function fit(index, doc){
    const r = S.view && S.view.renderer; if (!r || !S.base) return;
    const sec = secs[index], set = (k, v) => { if (r.getAttribute(k) !== v) r.setAttribute(k, v); };
    if (!sec || !sec.pages) { for (const k in S.base) if (S.base[k] != null) set(k, S.base[k]); return; }
    const flow = r.getAttribute('flow') || 'paginated', box = r.getBoundingClientRect();
    const two = flow !== 'scrolled' && (box.width || innerWidth) > (box.height || innerHeight) && sec.pages > 1;
    set('margin', '0px'); set('gap', '0%'); set('max-column-count', two ? '2' : '1');
    if (doc) {
      doc.documentElement.dataset.dafFlow = flow;
      doc.documentElement.toggleAttribute('data-daf-two', two);
      sides(doc, two);
    }
  }
  const api = {
    // Before book.js's own listeners, so the place it hears about has the page numbers in it.
    attach(view){
      S.view = view;
      view.addEventListener('load', e => load(e.detail));
      view.addEventListener('relocate', e => relocate(e.detail));
    },
    // Once book.js has set the type's layout (as the book opens, on a resize, a new Aa): that is
    // kept for the sections that are words, and the pages get theirs. The width is the whole
    // book's, so moving between sections never needs a new layout.
    layout(){
      const r = S.view && S.view.renderer; if (!r) return;
      S.base = { margin: r.getAttribute('margin'), gap: r.getAttribute('gap'), 'max-column-count': r.getAttribute('max-column-count'), 'max-block-size': r.getAttribute('max-block-size') };
      const box = r.getBoundingClientRect(), w = box.width || innerWidth, h = box.height || innerHeight, scrolled = r.getAttribute('flow') === 'scrolled';
      // the section's own first, then the width, which lays the pages out again with them
      const c = r.getContents()[0];
      if (c) fit(c.index, c.doc);
      r.setAttribute('max-block-size', Math.ceil(Math.max(h, innerHeight)) + 'px');
      r.setAttribute('max-inline-size', Math.ceil(scrolled ? Math.min(w, 980) : w > h ? w / 2 : w) + 'px');
      zoomClose(true);
    },
    css: () => CSS_PAGES,
    // Pages paired the other way (page 1 a picture later, or back): for a scan with the inside of
    // the cover in it, or a first page Daf took for a cover.
    pairs(){
      S.shift = S.shift ? 0 : 1; store.set('scanShift.' + id, S.shift);
      const r = S.view && S.view.renderer, c = r && r.getContents()[0];
      if (c) { fit(c.index, c.doc); r.render(); }
    },
    close(){ zoomClose(true); S.view = null; },
  };
  // The place foliate tells book.js: the pages on the screen, by their numbers; no time left (there
  // are no words to time). Turning the page puts away a page up close.
  function relocate(l){
    if (!S.view) return;
    delete l.time;
    if (Z.el && !Z.pinch && Z.at !== l.cfi) zoomClose();
    const n = l.range && l.range.startContainer, doc = n && (n.ownerDocument || n), list = doc && S.docs.get(doc);
    if (!list || l.pageItem) return;
    // the pages that are on the screen, by where they are (the range can reach the edge of the next one)
    const box = S.view.renderer.getBoundingClientRect(), f = doc.defaultView.frameElement.getBoundingClientRect(), down = doc.documentElement.dataset.dafFlow === 'scrolled';
    const seen = b => {
      const r = b.pic.getBoundingClientRect(), a0 = down ? f.top + r.top : f.left + r.left, a1 = a0 + (down ? r.height : r.width);
      const s0 = down ? box.top : box.left, s1 = down ? box.bottom : box.right;
      return a1 > a0 && Math.min(a1, s1) - Math.max(a0, s0) >= Math.min(a1 - a0, s1 - s0) / 2;
    };
    const shown = list.filter(b => { try { return l.range.intersectsNode(b.el) && seen(b); } catch(e){ return false; } }).map(b => num(b.k)).filter(n => n >= 1).map(String);
    if (shown.length) l.pageItem = { label: shown.length > 1 ? shown[0] + '–' + shown[shown.length - 1] : shown[0], pages: shown };
  }
  // A double tap or a pinch on a page brings it up close. The first tap of a tap waits a moment to
  // be sure it isn't a double one, then goes on to the book as it was (turning the page, the bar).
  function wire(doc){
    const win = doc.defaultView, again = new WeakSet();
    const blockAt = t => { const el = t && t.closest && t.closest('[data-daf-page], [data-daf-pic]'); if (!el) return null; return (S.docs.get(doc) || []).find(b => b.el === el || b.pic === el) || null; };
    const at = (x, y) => { const f = win.frameElement.getBoundingClientRect(); return { x: f.left + x, y: f.top + y }; };
    // up close, until the page is turned (the same place again, as a pinch snaps back, isn't a turn)
    const open = (b, x, y, to) => zoomOpen(b, x, y, to, { at: S.view && S.view.lastLocation && S.view.lastLocation.cfi, back: () => { try { S.view.renderer.focusView(); } catch(e){} } });
    let first = null;
    win.addEventListener('click', ev => {
      if (again.has(ev) || ev.button || ev.pointerType === 'pen') return;
      const b = blockAt(ev.target); if (!b) return;
      ev.stopImmediatePropagation(); ev.preventDefault();
      const x = ev.clientX, y = ev.clientY;
      if (first && ev.timeStamp - first.t < 300 && Math.hypot(x - first.x, y - first.y) < 40) {
        clearTimeout(first.timer); first = null;
        const p = at(x, y); open(b, p.x, p.y, 2.5); return;
      }
      if (first) { clearTimeout(first.timer); first.go(); }
      const target = ev.target, init = { bubbles: true, cancelable: true, composed: true, view: win, detail: 1, clientX: x, clientY: y, screenX: ev.screenX, screenY: ev.screenY };
      const tap = first = { t: ev.timeStamp, x, y, go(){ const e = new win.MouseEvent('click', init); again.add(e); target.dispatchEvent(e); } };
      tap.timer = setTimeout(() => { if (first === tap) first = null; tap.go(); }, 260);
    }, true);
    const pts = ev => [...ev.touches].slice(0, 2).map(t => at(t.clientX, t.clientY));
    doc.addEventListener('touchstart', ev => {
      if (ev.touches.length !== 2 || Z.el) return;
      const b = blockAt(ev.target); if (!b) return;
      ev.preventDefault();
      const [a, c] = pts(ev);
      open(b, (a.x + c.x) / 2, (a.y + c.y) / 2, 1);
      pinchFrom(a, c);
    }, { passive: false });
    doc.addEventListener('touchmove', ev => { if (!Z.pinch || ev.touches.length < 2) return; ev.preventDefault(); const [a, c] = pts(ev); pinchTo(a, c); }, { passive: false });
    const end = ev => { if (Z.pinch && ev.touches.length < 2) pinchDone(); };
    doc.addEventListener('touchend', end); doc.addEventListener('touchcancel', end);
    // a trackpad's pinch (the wheel, with Ctrl)
    win.addEventListener('wheel', ev => {
      if (!ev.ctrlKey || ev.deltaY >= 0) return;
      const b = blockAt(ev.target); if (!b) return;
      ev.preventDefault();
      const p = at(ev.clientX, ev.clientY); open(b, p.x, p.y, 1.6);
    }, { passive: false });
  }
  return api;
}

/* ---------- a page up close ---------- */
// The page's picture over the book, where it was on the screen, then made bigger round a point and
// moved about under the finger: the picture is the book's own (its scan is all there is).
const Z = { el: null, img: null, r: null, s: 1, x: 0, y: 0, pinch: null, at: null, back: null };
// Where the picture is drawn on the screen (its box less what "contain" leaves empty round it).
function drawn(b){
  const pic = b.pic, f = pic.ownerDocument.defaultView.frameElement.getBoundingClientRect(), r = pic.getBoundingClientRect();
  let nw = pic.naturalWidth, nh = pic.naturalHeight;
  if (pic.localName === 'svg') { const vb = pic.viewBox && pic.viewBox.baseVal; nw = vb && vb.width; nh = vb && vb.height; }
  if (!nw || !nh || !r.width || !r.height) return { x: f.left + r.left, y: f.top + r.top, w: r.width, h: r.height };
  const k = Math.min(r.width / nw, r.height / nh), w = nw * k, h = nh * k, ax = b.side === 'l' ? 1 : b.side === 'r' ? 0 : .5;
  return { x: f.left + r.left + (r.width - w) * ax, y: f.top + r.top + (r.height - h) / 2, w, h };
}
function zoomOpen(b, px, py, to, o){
  zoomClose(true);
  const pic = b.pic, im = pic.localName === 'svg' ? pic.querySelector('image') : null;
  const src = im ? (im.href && im.href.baseVal) || im.getAttributeNS(XLINK, 'href') : pic.currentSrc || pic.src;
  const r = drawn(b); if (!src || !r.w) return;
  const el = document.createElement('div');
  el.className = 'pzoom' + (C.HL && C.HL.isDark() ? ' dim' : ''); el.tabIndex = -1;
  el.innerHTML = '<img alt="" draggable="false">';
  const img = el.firstChild; img.src = src;
  Object.assign(img.style, { left: r.x + 'px', top: r.y + 'px', width: r.w + 'px', height: r.h + 'px' });
  document.body.append(el);
  Object.assign(Z, { el, img, r, s: 1, x: 0, y: 0, pinch: null, at: o && o.at, back: o && o.back });
  zoomWire(el);
  el.focus({ preventScroll: true });     // the keys come here (Esc), not to the book's page
  requestAnimationFrame(() => { if (Z.el === el) el.classList.add('on'); });
  if (to > 1) zoomAt(px, py, to, true);
}
function zoomClose(now){
  const el = Z.el; if (!el) return false;
  clearTimeout(Z.tapT);
  const back = Z.back;
  Object.assign(Z, { el: null, pinch: null, back: null });
  if (back && document.activeElement === el) back();
  if (now) { el.remove(); return true; }
  // back to its place in the book, then gone
  Object.assign(Z, { s: 1, x: 0, y: 0 }); zoomDraw(true, el.firstChild);
  el.classList.remove('on'); el.style.pointerEvents = 'none';
  setTimeout(() => el.remove(), 220);
  return true;
}
function zoomDraw(smooth, img){
  img = img || Z.img; if (!img) return;
  img.style.transition = smooth ? 'transform .2s ease' : 'none';
  img.style.transform = 'translate(' + Z.x + 'px,' + Z.y + 'px) scale(' + Z.s + ')';
}
// Never off the screen: an edge stays at the screen's edge until the other one comes in.
function zoomClamp(){
  const W = innerWidth, H = innerHeight, w = Z.r.w * Z.s, h = Z.r.h * Z.s;
  let L = Z.r.x + Z.x, T = Z.r.y + Z.y;
  L = w > W ? Math.min(0, Math.max(W - w, L)) : Math.max(0, Math.min(W - w, L));
  T = h > H ? Math.min(0, Math.max(H - h, T)) : Math.max(0, Math.min(H - h, T));
  Z.x = L - Z.r.x; Z.y = T - Z.r.y;
}
// Bigger or smaller round a point on the screen, which stays where it is.
function zoomAt(px, py, s, smooth){
  s = Math.max(1, Math.min(6, s));
  const k = s / Z.s;
  Z.x = px - Z.r.x - (px - Z.r.x - Z.x) * k; Z.y = py - Z.r.y - (py - Z.r.y - Z.y) * k; Z.s = s;
  zoomClamp(); zoomDraw(smooth);
}
// Two fingers: the point between them stays under them, and the page grows as they part.
function pinchFrom(a, b){ Z.pinch = { d: Math.hypot(a.x - b.x, a.y - b.y) || 1, mx: (a.x + b.x) / 2, my: (a.y + b.y) / 2, s: Z.s, x: Z.x, y: Z.y }; }
function pinchTo(a, b){
  const p = Z.pinch; if (!p || !Z.el) return;
  const s = Math.max(.6, Math.min(6, p.s * Math.hypot(a.x - b.x, a.y - b.y) / p.d)), k = s / p.s, mx = (a.x + b.x) / 2, my = (a.y + b.y) / 2;
  Z.x = mx - Z.r.x - (p.mx - Z.r.x - p.x) * k; Z.y = my - Z.r.y - (p.my - Z.r.y - p.y) * k; Z.s = s;
  zoomDraw(false);
}
function pinchDone(){
  Z.pinch = null; if (!Z.el) return;
  if (Z.s < 1.05) { zoomClose(); return; }
  zoomClamp(); zoomDraw(true);
}
function zoomWire(el){
  const pts = new Map(); let g = null, last = null;
  el.addEventListener('pointerdown', e => {
    pts.set(e.pointerId, { x: e.clientX, y: e.clientY });
    try { el.setPointerCapture(e.pointerId); } catch(err){}
    if (pts.size === 2) { const [a, b] = [...pts.values()]; pinchFrom(a, b); g = null; }
    else if (pts.size === 1) g = { x: e.clientX, y: e.clientY, zx: Z.x, zy: Z.y, moved: false };
  });
  el.addEventListener('pointermove', e => {
    if (!pts.has(e.pointerId)) return;
    pts.set(e.pointerId, { x: e.clientX, y: e.clientY });
    if (Z.pinch && pts.size === 2) { const [a, b] = [...pts.values()]; pinchTo(a, b); return; }
    if (!g) return;
    const dx = e.clientX - g.x, dy = e.clientY - g.y;
    if (!g.moved && Math.hypot(dx, dy) > 6) g.moved = true;
    if (g.moved) { Z.x = g.zx + dx; Z.y = g.zy + dy; zoomClamp(); zoomDraw(false); }
  });
  const up = e => {
    if (!pts.has(e.pointerId)) return;
    pts.delete(e.pointerId);
    if (Z.pinch) { if (pts.size < 2) { pinchDone(); g = null; } return; }
    const s = g; g = null;
    if (!s || s.moved || e.type === 'pointercancel') return;
    // a tap puts the page away; a double tap goes in closer, or back out
    const now = performance.now(), x = e.clientX, y = e.clientY;
    if (last && now - last.t < 300 && Math.hypot(x - last.x, y - last.y) < 40) {
      clearTimeout(Z.tapT); last = null;
      if (Z.s > 1.05) zoomClose(); else zoomAt(x, y, 2.5, true);
      return;
    }
    last = { t: now, x, y };
    clearTimeout(Z.tapT); Z.tapT = setTimeout(() => { last = null; zoomClose(); }, 260);
  };
  el.addEventListener('pointerup', up);
  el.addEventListener('pointercancel', up);
  el.addEventListener('wheel', e => {
    e.preventDefault();
    if (e.ctrlKey) { const s = Z.s * Math.exp(-e.deltaY / 120); if (s < 1) zoomClose(); else zoomAt(e.clientX, e.clientY, s, false); return; }
    Z.x -= e.deltaX; Z.y -= e.deltaY; zoomClamp(); zoomDraw(false);
  }, { passive: false });
}
window.addEventListener('keydown', e => { if (Z.el && e.key === 'Escape') { e.preventDefault(); e.stopImmediatePropagation(); zoomClose(); } }, true);
window.addEventListener('resize', () => zoomClose(true));
window.addEventListener('hashchange', () => zoomClose(true));

// book.js: detect(book, id) as a book opens; shell.js: close() for Back.
C.Scans = { detect, close: () => zoomClose() };
})();
