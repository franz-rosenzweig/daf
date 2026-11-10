/* The PDF as printed: pages drawn by pdf.js (vendored in web/vendor/pdfjs), with a text layer to
   select and highlight on, like Readwise Reader's PDF view (#pdf/<doc>[/hl:<id>]).
   A highlight made here keeps its page and boxes (pos.pdf) and, when its words are in the text
   view too, its place there, so it shows in both. Highlights made in the text view are found on
   the page by their words. Time here counts as reading, and the page read is the progress.
   A book Calibre has only as a PDF opens here too (#pdf/book/<book>[/hl:<id>], from book.js): its
   highlights keep the same pos.pdf, and its place and reading time are the book's.

   A PDF reader as Preview and Acrobat are: the side panel on the left (the button beside Back, or
   the left edge in focus mode) has the pages as small pictures, the PDF's own contents, its
   highlights and a search; All pages lays every page out in a grid. The page number in the bar
   goes to a page (a number, a printed page number when the PDF has them, or the slider). The view
   menu fits the width or the whole page, scrolls or goes page by page (sideways swipes and the
   arrow keys turn pages either way), shows one page or two side by side, and darkens the pages.
   Two fingers pinch it larger or smaller (⌘ and the wheel on a Mac). How it's set is this
   device's, for every PDF. */
import * as pdfjs from './vendor/pdfjs/pdf.min.mjs';

pdfjs.GlobalWorkerOptions.workerSrc = '/vendor/pdfjs/pdf.worker.min.mjs';
const C = window.DafCore, { api, esc, toast, $, $$ } = C, H = C.HL;
const P = { id: null, d: null, pdf: null, zoom: 1, base: 1, rendered: new Map(), obs: null, active: Date.now(), page: 1, saveT: 0, found: new Map(),
  labels: null, outline: null, thumbs: new Map(), tobs: null, texts: new Map(), find: null, rows: [], gen: 0 };
// Where a PDF document's or a PDF book's things are.
const SRC = {
  doc: id => ({ meta: '/api/docs/' + encodeURIComponent(id) + '?prefetch=1', file: '/api/docs/' + encodeURIComponent(id) + '/pdf',
                back: '#read/' + encodeURIComponent(id), backLabel: 'Back', hl: '/api/docs/' + encodeURIComponent(id) + '/highlights', beat: { doc_id: id } }),
  book: id => ({ meta: '/api/ebooks/' + encodeURIComponent(id), file: '/api/ebooks/' + encodeURIComponent(id) + '/file', book: true,
                 back: '#book/' + encodeURIComponent(id), backLabel: 'Back to the book', hl: '/api/ebooks/' + encodeURIComponent(id) + '/highlights', beat: { book_id: id } }),
};
const store = { get(k, d){ try { const v = localStorage.getItem('daf.' + k); return v == null ? d : JSON.parse(v); } catch(e){ return d; } }, set(k, v){ try { localStorage.setItem('daf.' + k, JSON.stringify(v)); } catch(e){} } };
// How this device shows PDFs: fit ('width' or 'page'), zoom (times the fit), two pages side by side,
// page by page, dark pages, the side panel open (where there's room for it beside the pages) and its tab.
const V = { fit: store.get('pdfFit', 'width'), two: store.get('pdfTwo', false), paged: store.get('pdfPaged', false), dark: store.get('pdfDark', false),
  side: store.get('pdfSide', false), tab: store.get('pdfTab', 'pages'), grid: false };
const keep = () => ['fit', 'two', 'paged', 'dark', 'side', 'tab'].forEach(k => store.set('pdf' + k[0].toUpperCase() + k.slice(1), V[k]));
const K = (e, a) => C.Keys && C.Keys.is(e, 'pdf', a);
const tip = a => C.Keys ? C.Keys.tip('pdf', a) : '';

const IC = {
  side: '<svg width="18" height="18" viewBox="0 0 20 20" aria-hidden="true"><rect x="3" y="3.5" width="14" height="13" rx="2.5" fill="none" stroke="currentColor" stroke-width="1.6"/><path d="M8 3.5v13M4.9 7h1.4M4.9 9.6h1.4M4.9 12.2h1.4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>',
  search: '<svg width="18" height="18" viewBox="0 0 20 20" aria-hidden="true"><circle cx="8.8" cy="8.8" r="5.3" fill="none" stroke="currentColor" stroke-width="1.7"/><path d="m12.8 12.8 4 4" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/></svg>',
  view: '<svg width="18" height="18" viewBox="0 0 20 20" aria-hidden="true"><rect x="4.5" y="2.5" width="11" height="15" rx="1.8" fill="none" stroke="currentColor" stroke-width="1.6"/><path d="M7.5 6.5h5M7.5 9.5h5M7.5 12.5h3" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>',
  grid: '<svg width="18" height="18" viewBox="0 0 20 20" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="3" y="3" width="5.5" height="6" rx="1"/><rect x="11.5" y="3" width="5.5" height="6" rx="1"/><rect x="3" y="11" width="5.5" height="6" rx="1"/><rect x="11.5" y="11" width="5.5" height="6" rx="1"/></svg>',
  x: '<svg width="16" height="16" viewBox="0 0 20 20" aria-hidden="true"><path d="M5 5l10 10M15 5L5 15" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>',
};

C.views.pdf = async args => {
  const book = args[0] === 'book' && args.length > 1; if (book) args = args.slice(1);
  const last = args[args.length - 1] || '', hl = last.startsWith('hl:') && args.length > 1 ? decodeURIComponent(last.slice(3)) : null;
  const id = decodeURIComponent((hl ? args.slice(0, -1) : args).join('/'));
  H.active = ACT;
  if (P.id === id && P.pdf && $('#pdfpages')) { if (hl) goToHl(hl); return; }
  close();
  P.id = id; P.src = (book ? SRC.book : SRC.doc)(id);
  V.grid = false;
  $('#main').innerHTML = '<div class="pdfv" id="pdfv"><div class="top" id="ptop"><button class="ib" data-pv="back" title="' + P.src.backLabel + '" aria-label="' + P.src.backLabel + '">' + C.I.back + '</button>' +
    '<button class="ib" data-pv="side" title="Pages and contents' + tip('side') + '" aria-label="Pages and contents">' + IC.side + '</button>' +
    '<h1 id="ptitle">PDF</h1><span class="spacer"></span><button class="pgbox" data-pv="goto" id="ppg" title="Go to a page' + tip('goto') + '" aria-label="Go to a page"></button>' +
    '<button class="ib pvz" data-pv="out" aria-label="Smaller" title="Smaller' + tip('smaller') + '">−</button><button class="ib pvz" data-pv="in" aria-label="Larger" title="Larger' + tip('larger') + '">+</button>' +
    '<button class="ib" data-pv="find" title="Search in the PDF' + tip('search') + '" aria-label="Search in the PDF">' + IC.search + '</button>' +
    '<button class="ib" data-pv="view" title="View" aria-label="View">' + IC.view + '</button>' +
    (book ? '' : '<a class="btn sm" href="#read/' + encodeURIComponent(id) + '" data-swap title="The text, reflowed">Text</a>') +
    (C.Sketch ? C.Sketch.button('pdf') : '') + (C.Focus ? C.Focus.button('article') : '') + '</div>' +
    '<div class="pdfbody"><aside class="pdfside" id="pside" aria-label="Pages and contents"></aside><div class="pscrim" data-pv="sideclose"></div>' +
    '<div class="pdfpages" id="pdfpages"><span class="mute" style="padding:24px">Opening the PDF…</span></div></div></div>';
  look();
  try { P.d = await api(P.src.meta); } catch(e){ $('#pdfpages').innerHTML = '<p class="mute" style="padding:24px">' + esc(e.message) + '</p>'; return; }
  if (P.id !== id) return;
  $('#ptitle').textContent = P.d.title || 'PDF';
  try {
    P.pdf = await pdfjs.getDocument({ url: P.src.file, withCredentials: true,
      standardFontDataUrl: '/vendor/pdfjs/standard_fonts/', cMapUrl: '/vendor/pdfjs/cmaps/', cMapPacked: true }).promise;
  } catch(e){ $('#pdfpages').innerHTML = '<p class="mute" style="padding:24px">Daf couldn’t open this PDF: ' + esc(e.message) + '</p>'; return; }
  if (P.id !== id) return;
  P.zoom = store.get('pdfZoom', 1);
  P.seen = new Set(); P.pageAt = Date.now();
  try { P.labels = await P.pdf.getPageLabels(); } catch(e){ P.labels = null; }
  if (P.labels && P.labels.every((l, i) => !l || l === String(i + 1))) P.labels = null;     // the same as the page numbers: nothing to show
  // a book's place is kept in Daf for every device ("pdf:<page>"); a document's page on this one
  const kept = book && P.d.position && /^pdf:(\d+)/.exec(P.d.position.cfi || '');
  const at = hl ? null : kept ? +kept[1] : store.get('pdfPage.' + id, 0);
  if (at > 1) P.page = Math.min(at, P.pdf.numPages);
  if (V.side && wide()) place(true);                 // the side panel beside the pages from the start, where there's room
  await layout();
  // the Sketchbook beside it (sketchbook.js): its camera takes the page in view
  if (C.Sketch) C.Sketch.attach({ item: (book ? 'book:' : 'doc:') + id, kind: 'pdf', shots: () => $$('#pdfpages .pdfpage canvas'),
    resized: () => relayout() });
  if (hl) goToHl(hl);
  else if (at > 1) scrollToPage(at);
  if (sideOn()) drawSide();
  P.pdf.getOutline().then(o => { P.outline = o && o.length ? o : []; if (sideOn() && V.tab === 'contents') drawTab(); }).catch(() => { P.outline = []; });
};

// Scroll the pages box itself (not the window) to a page, or to a place on it.
function scrollToPage(pg, frac){
  const box = $('#pdfpages'), el = box && $('.pdfpage[data-pg="' + pg + '"]', box); if (!el) return;
  const top = box.scrollTop + el.getBoundingClientRect().top - box.getBoundingClientRect().top;
  box.scrollTop = top - (V.paged ? (box.clientHeight - el.offsetHeight) / 2 : 12) + (frac ? frac * el.offsetHeight - box.clientHeight * 0.3 : 0);
  if (V.two) { const left = box.scrollLeft + el.getBoundingClientRect().left - box.getBoundingClientRect().left; if (left < box.scrollLeft || left + el.offsetWidth > box.scrollLeft + box.clientWidth) box.scrollLeft = Math.max(0, left - 12); }
  P.page = pg; showPage();
}
function close(){
  if (P.obs) P.obs.disconnect();
  if (P.tobs) P.tobs.disconnect();
  if (P.pdf) { try { P.pdf.destroy(); } catch(e){} }
  for (const u of P.thumbs.values()) if (u && u.startsWith('blob:')) URL.revokeObjectURL(u);
  Object.assign(P, { pdf: null, d: null, obs: null, tobs: null, rendered: new Map(), found: new Map(), labels: null, outline: null, thumbs: new Map(), texts: new Map(), find: null, rows: [], page: 1 });
  P.gen++;
}
window.addEventListener('hashchange', () => { if (!location.hash.startsWith('#pdf/') && P.pdf) close(); });

/* ---------- laying the pages out ---------- */
// The view's classes on .pdfv: page by page, dark pages, the side panel and All pages.
function look(){
  const v = $('#pdfv'); if (!v) return;
  v.classList.toggle('paged', V.paged); v.classList.toggle('pdark', V.dark); v.classList.toggle('ptwo', V.two);
  v.classList.toggle('pgrid', V.grid);
}
// Rows of pages: one each, or two side by side (a book's cover alone first, as a printed book opens).
function rows(n){
  const out = [];
  if (!V.two) { for (let i = 1; i <= n; i++) out.push([i]); return out; }
  let i = 1;
  if (P.src && P.src.book) out.push([i++]);
  for (; i <= n; i += 2) out.push(i + 1 <= n ? [i, i + 1] : [i]);
  return out;
}
// The scale a page is drawn at: the width or the whole page fitted, times the zoom.
function fitScale(w, h){
  const box = $('#pdfpages'), n = V.two ? 2 : 1, gap = 12;
  const aw = Math.max(120, box.clientWidth - (innerWidth <= 600 ? 12 : 32) - (n - 1) * gap), ah = Math.max(120, box.clientHeight - 24);
  const byW = Math.min(V.two ? 1960 : 980, aw) / (w * n);
  return V.fit === 'page' || V.paged ? Math.min(byW, ah / h) : byW;
}
// Placeholders for every page, sized from page 1; pages are drawn as they come into view.
async function layout(){
  const box = $('#pdfpages'); if (!box || !P.pdf) return;
  const gen = P.gen, p1 = await P.pdf.getPage(1), v1 = p1.getViewport({ scale: 1 });
  if (gen !== P.gen) return;
  P.base = Math.max(0.2, fitScale(v1.width, v1.height));
  const scale = P.base * P.zoom, w = Math.round(v1.width * scale), h = Math.round(v1.height * scale);
  P.rendered = new Map(); P.rows = rows(P.pdf.numPages);
  const pg = i => '<div class="pdfpage" data-pg="' + i + '" style="width:' + w + 'px;height:' + h + 'px"><span class="pgn">' + i + '</span></div>';
  box.innerHTML = '<div class="pdfin" id="pdfin">' + P.rows.map(r => '<div class="pdfrow">' + r.map(pg).join('') + '</div>').join('') + '</div>';
  if (P.obs) P.obs.disconnect();
  P.obs = new IntersectionObserver(es => es.forEach(e => {
    const n = +e.target.dataset.pg;
    if (e.isIntersecting && !P.rendered.has(n)) renderPage(n, e.target);
  }), { root: box, rootMargin: '900px 400px' });
  $$('.pdfpage', box).forEach(el => P.obs.observe(el));
  box.onscroll = onScroll;
  onScroll();
}
// Laid out again (a new size, a new fit), at the same page.
async function relayout(){
  const at = P.page;
  await layout();
  scrollToPage(at);
}

async function renderPage(pg, el){
  P.rendered.set(pg, true);
  const gen = P.gen, page = await P.pdf.getPage(pg); if (gen !== P.gen) return;
  const scale = P.base * P.zoom, vp = page.getViewport({ scale }), dpr = Math.min(window.devicePixelRatio || 1, 3);
  el.style.width = Math.round(vp.width) + 'px'; el.style.height = Math.round(vp.height) + 'px';
  el.style.setProperty('--scale-factor', scale);
  const cv = document.createElement('canvas');
  // (a very large page at a high zoom is drawn at less than the screen's density, so it fits in memory)
  const k = Math.min(dpr, Math.sqrt(16e6 / (vp.width * vp.height)));
  cv.width = Math.floor(vp.width * k); cv.height = Math.floor(vp.height * k);
  cv.style.width = Math.round(vp.width) + 'px'; cv.style.height = Math.round(vp.height) + 'px';
  const marks = document.createElement('div'); marks.className = 'pmarks';
  const tl = document.createElement('div'); tl.className = 'textLayer';
  el.replaceChildren(cv, marks, tl);
  try { await page.render({ canvasContext: cv.getContext('2d'), viewport: vp, transform: k !== 1 ? [k, 0, 0, k, 0, 0] : null }).promise; } catch(e){ return; }
  if (gen === P.gen) P.rendered.set(pg, 'done');
  try { await new pdfjs.TextLayer({ textContentSource: page.streamTextContent(), container: tl, viewport: vp }).render(); } catch(e){}
  el.__tm = null;
  drawMarks(pg);
}

/* ---------- highlights on a page ---------- */
const norm = s => String(s || '').replace(/­/g, '').replace(/-\s+(?=\p{Ll})/gu, '').replace(/\s+/g, ' ').trim();
// A rendered page's text, as one string with its whitespace made single, and from each of its
// characters back to the text layer's nodes.
function textMap(pg){
  const el = $('.pdfpage[data-pg="' + pg + '"]'), tl = el && el.querySelector('.textLayer'); if (!tl) return null;
  if (el.__tm) return el.__tm;
  const nodes = [], walk = document.createTreeWalker(tl, NodeFilter.SHOW_TEXT);
  let flat = '';
  for (let n = walk.nextNode(); n; n = walk.nextNode()) { if (flat && !/\s$/.test(flat)) flat += ' '; nodes.push([n, flat.length]); flat += n.data; }
  // Index from the normalized page text back to the raw one, character by character.
  const map = []; let out = '';
  for (let i = 0; i < flat.length; i++) {
    const ch = flat[i];
    if (/\s/.test(ch)) { if (out && !out.endsWith(' ')) { out += ' '; map.push(i); } continue; }
    if (ch === '­') continue;
    out += ch; map.push(i);
  }
  return (el.__tm = { el, nodes, map, out, low: out.toLowerCase() });
}
// The boxes of the words from `at` for `len` characters of a page's text (textMap).
function rectsAt(tm, at, len){
  const { nodes, map, el } = tm;
  const pos = i => { for (let k = nodes.length - 1; k >= 0; k--) if (nodes[k][1] <= i) return [nodes[k][0], Math.min(i - nodes[k][1], nodes[k][0].data.length)]; return [nodes[0][0], 0]; };
  const r = document.createRange(), a = pos(map[at]), b = pos(map[Math.min(map.length - 1, at + len - 1)] + 1);
  try { r.setStart(a[0], a[1]); r.setEnd(b[0], b[1]); } catch(e){ return null; }
  return rectsOf(r, el);
}
// Where a text-view highlight's words are on this page: rects as fractions of the page.
function findOnPage(pg, text){
  const tm = textMap(pg); if (!tm || !tm.nodes.length) return null;
  const want = norm(text); if (want.length < 8) return null;
  let at = tm.out.indexOf(want), len = want.length;
  if (at < 0 && want.length > 60) { at = tm.out.indexOf(want.slice(0, 60)); len = at < 0 ? 0 : Math.min(tm.out.length - at, want.length); }
  if (at < 0) return null;
  return rectsAt(tm, at, len);
}
function rectsOf(range, el){
  const box = el.getBoundingClientRect(), out = [];
  for (const q of range.getClientRects()) {
    if (q.width < 1 || q.height < 2) continue;
    out.push([(q.left - box.left) / box.width, (q.top - box.top) / box.height, q.width / box.width, q.height / box.height].map(v => Math.round(v * 1e5) / 1e5));
  }
  // Merge pieces on one line, as the text layer splits words into spans.
  out.sort((a, b) => a[1] - b[1] || a[0] - b[0]);
  const merged = [];
  for (const r of out) {
    const m = merged[merged.length - 1];
    if (m && Math.abs(m[1] - r[1]) < r[3] * 0.5 && r[0] <= m[0] + m[2] + 0.01) { const right = Math.max(m[0] + m[2], r[0] + r[2]); m[2] = right - m[0]; m[3] = Math.max(m[3], r[3]); }
    else merged.push(r.slice());
  }
  return merged;
}
function placeOf(h){
  const p = h.pos || {};
  if (p.pdf) return p.pdf;
  const f = P.found.get(h.id); if (f) return f;
  return null;
}
const box = r => 'left:' + (r[0] * 100) + '%;top:' + (r[1] * 100) + '%;width:' + (r[2] * 100) + '%;height:' + (r[3] * 100) + '%';
function drawMarks(pg){
  const el = $('.pdfpage[data-pg="' + pg + '"]'), mk = el && el.querySelector('.pmarks'); if (!mk || !P.d) return;
  let html = '';
  for (const h of P.d.highlights || []) {
    let pl = placeOf(h);
    if (!pl && !P.found.has(h.id)) { const r = findOnPage(pg, h.text); if (r && r.length) { pl = { pg, r }; P.found.set(h.id, pl); } }
    if (!pl || pl.pg !== pg) continue;
    html += pl.r.map(r => '<i class="pmark" data-h="' + esc(h.id) + '" data-color="' + esc(h.color || 'yellow') + '"' + ((h.user_note || '').trim() ? ' data-note="1"' : '') + ' style="' + box(r) + '"></i>').join('');
  }
  // what the search found on this page; the one gone to stands out
  if (P.find && P.find.q) {
    const tm = textMap(pg), q = P.find.q;
    if (tm) for (let at = tm.low.indexOf(q), n = 0; at >= 0; at = tm.low.indexOf(q, at + q.length), n++) {
      const cur = P.find.cur && P.find.cur.pg === pg && P.find.cur.n === n;
      for (const r of rectsAt(tm, at, q.length) || []) html += '<i class="phit' + (cur ? ' cur' : '') + '" style="' + box(r) + '"></i>';
    }
  }
  mk.innerHTML = html;
  const th = $('#pside .pth[data-gopg="' + pg + '"]'); if (th) th.classList.toggle('hl', hasMarks(pg));
}
function redrawAll(){ for (const pg of P.rendered.keys()) drawMarks(pg); }
const hasMarks = pg => (P.d && P.d.highlights || []).some(h => { const pl = placeOf(h); return pl && pl.pg === pg; });

/* ---------- selecting and highlighting ---------- */
document.addEventListener('mouseup', e => { if (C.S.route[0] === 'pdf' && !e.target.closest('#selbar, #pop, #pside')) setTimeout(() => onSelect(e), 10); });
document.addEventListener('touchend', e => { if (C.S.route[0] === 'pdf' && !e.target.closest('#selbar, #pop, #pside')) setTimeout(() => onSelect(e, true), 400); });
function onSelect(e, touch){
  const sel = window.getSelection();
  if (!sel || sel.isCollapsed || !sel.rangeCount) { if (!touch) clickMark(e); return; }
  const range = sel.getRangeAt(0);
  const start = range.startContainer.parentElement && range.startContainer.parentElement.closest('.pdfpage');
  if (!start) return;
  snapWords(range); sel.removeAllRanges(); sel.addRange(range);
  const text = norm(sel.toString()); if (text.length < 2) return;
  const pg = +start.dataset.pg;
  // Only the boxes on the page where the selection starts.
  const endPage = range.endContainer.parentElement && range.endContainer.parentElement.closest('.pdfpage');
  const r1 = document.createRange(); r1.setStart(range.startContainer, range.startOffset);
  if (endPage === start) r1.setEnd(range.endContainer, range.endOffset); else r1.setEnd(start.querySelector('.textLayer'), start.querySelector('.textLayer').childNodes.length);
  const info = { pg, r: rectsOf(r1, start), text };
  const rect = range.getBoundingClientRect();
  if (!touch && H.auto && H.auto() && !e.altKey) { highlight(info); return; }
  H.show(H.selBar({ text }), rect, { kind: 'sel', text, info });
}
function clickMark(e){
  const pageEl = e.target.closest && e.target.closest('.pdfpage'); if (!pageEl) { if (!e.target.closest('#selbar')) H.hide(); return; }
  const hit = [...pageEl.querySelectorAll('.pmark')].find(m => { const q = m.getBoundingClientRect(); return e.clientX >= q.left && e.clientX <= q.right && e.clientY >= q.top && e.clientY <= q.bottom; });
  if (!hit) { H.hide(); return; }
  const h = (P.d.highlights || []).find(x => x.id === hit.dataset.h); if (!h) return;
  H.show(H.hlBar(h), hit.getBoundingClientRect(), { kind: 'hl', h });
}
// Whole words, as everywhere in Daf: a selection that starts or ends inside a word takes all of it.
const WORD = /[\p{L}\p{N}'’־-]/u;
function snapWords(r){
  const a = r.startContainer, b = r.endContainer;
  if (a.nodeType === 3) { let i = r.startOffset; while (i > 0 && WORD.test(a.data[i - 1]) && WORD.test(a.data[i] || ' ')) i--; r.setStart(a, i); }
  if (b.nodeType === 3) { let j = r.endOffset; while (j < b.data.length && WORD.test(b.data[j]) && j > 0 && WORD.test(b.data[j - 1])) j++; r.setEnd(b, j); }
}
// The text view's place for these words, so the highlight shows there as well.
function textPlace(text){
  const words = norm(text).split(' ').filter(Boolean); if (words.length < 2 || !P.d) return null;
  const esc2 = w => w.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const head = new RegExp(words.slice(0, 8).map(esc2).join('\\s+')), tail = new RegExp(words.slice(-5).map(esc2).join('\\s+'));
  for (let i = 0; i < (P.d.blocks || []).length; i++) {
    const full = P.d.blocks[i].x || ''; const m = head.exec(full); if (!m) continue;
    const rest = full.slice(m.index), t = words.length > 8 ? tail.exec(rest) : null;
    return { b: i, s: m.index, e: t ? m.index + t.index + t[0].length : Math.min(full.length, m.index + Math.max(m[0].length, text.length)) };
  }
  return null;
}
async function highlight(info, withNote){
  H.hide(); window.getSelection().removeAllRanges();
  if (!info || !info.r.length) return;
  const place = P.src.book ? null : textPlace(info.text), color = store.get('hlColor', 'yellow');
  const body = P.src.book ? { text: info.text, color, pdf: { pg: info.pg, r: info.r }, fraction: info.pg / P.pdf.numPages, chapter: 'p. ' + info.pg }
    : Object.assign({ text: info.text, color, pdf: { pg: info.pg, r: info.r } }, place || { b: null, s: null, e: null });
  try {
    const r = await api(P.src.hl, { method: 'POST', body: JSON.stringify(body) });
    const h = { id: r.id, text: info.text, color, pos: Object.assign({}, place || {}, { pdf: { pg: info.pg, r: info.r } }), user_note: '', tags: [] };
    P.d.highlights = (P.d.highlights || []).filter(x => x.id !== h.id).concat([h]);
    drawMarks(info.pg);
    if (sideOn() && V.tab === 'marks') drawTab();
    if (withNote) editNote(h);
  } catch(e){ toast(e.message); }
}
function editNote(h){
  const m = $('#modal'); $('#scrim').hidden = false; m.hidden = false;
  m.innerHTML = '<h2>A note</h2><q class="pnq">' + esc(h.text.slice(0, 280)) + '</q><textarea class="field" id="pnote" rows="4" placeholder="Your thought">' + esc(h.user_note || '') + '</textarea>' +
    '<div style="display:flex;gap:8px;justify-content:flex-end"><button class="btn" data-act="close">Cancel</button><button class="btn primary" id="pnsave">Save</button></div>';
  const t = $('#pnote'); t.focus();
  $('#pnsave').onclick = async () => {
    try { await api('/api/highlights/' + encodeURIComponent(h.id) + '/note', { method: 'PUT', body: JSON.stringify({ note: t.value }) }); h.user_note = t.value; C.closeModal(); toast('Saved'); const pl = placeOf(h); if (pl) drawMarks(pl.pg); }
    catch(e){ toast(e.message); }
  };
}
async function removeHl(h){
  H.hide();
  try { await api('/api/highlights/' + encodeURIComponent(h.id), { method: 'DELETE' }); } catch(e){ toast(e.message); return; }
  const pl = placeOf(h);
  P.d.highlights = P.d.highlights.filter(x => x.id !== h.id); P.found.delete(h.id);
  if (pl) drawMarks(pl.pg);
  if (sideOn() && V.tab === 'marks') drawTab();
  H.undo && H.undo('Highlight deleted', async () => {
    await api('/api/highlights/' + encodeURIComponent(h.id) + '/restore', { method: 'POST' });
    P.d.highlights.push(h); if (pl) drawMarks(pl.pg);
  });
}
function goToHl(id){
  const h = (P.d && P.d.highlights || []).find(x => x.id === id);
  const go = async pl => {
    scrollToPage(pl.pg, pl.r[0] ? pl.r[0][1] : 0);
    // its marks are there once the page is drawn, which can take a moment after the scroll
    for (let k = 0; k < 15 && !$$('.pmark[data-h="' + CSS.escape(id) + '"]').length; k++) await new Promise(r => setTimeout(r, 200));
    $$('.pmark[data-h="' + CSS.escape(id) + '"]').forEach(m => { m.classList.add('flash'); setTimeout(() => m.classList.remove('flash'), 1800); });
  };
  if (!h) { toast('That highlight isn’t on these pages'); return; }
  const pl = placeOf(h);
  if (pl) { go(pl); return; }
  toast('Finding it in the pages…');
  (async () => {                                   // a text-view highlight: look page by page
    for (let pg = 1; pg <= P.pdf.numPages; pg++) {
      const el = $('.pdfpage[data-pg="' + pg + '"]');
      if (!P.rendered.has(pg)) await renderPage(pg, el);
      const f = P.found.get(h.id); if (f) { go(f); return; }
    }
    toast('Not found on the pages');
  })();
}
const ACT = {
  hl: ctx => highlight(ctx.info),
  note: ctx => ctx.h ? editNote(ctx.h) : highlight(ctx.info, true),
  rm: ctx => removeHl(ctx.h),
  define: ctx => { H.hide(); C.lookup && C.lookup({ text: ctx.text, rect: $('#selbar').getBoundingClientRect() }, ctx.text, false); },
  translate: ctx => { H.hide(); C.lookup && C.lookup({ text: ctx.text, rect: $('#selbar').getBoundingClientRect() }, ctx.text, true); },
  ask: () => { H.hide(); if (P.src.book) { toast('Ask works in a book’s text, not on a PDF’s pages'); return; } toast('Ask works in the text view'); location.hash = 'read/' + encodeURIComponent(P.id); },
  notebook: () => { H.hide(); location.hash = P.src.book ? 'book/' + encodeURIComponent(P.id) : 'read/' + encodeURIComponent(P.id); },
  changed: h => { const pl = placeOf(h); if (pl) drawMarks(pl.pg); },
  deselect: () => window.getSelection().removeAllRanges(),
  meta: () => ({ title: P.d && P.d.title, author: P.d && (P.d.author || P.d.source) }),
};

/* ---------- the side panel: pages, contents, highlights, search ---------- */
// Beside the pages where there's room (and not in focus mode), else over them from the left.
const wide = () => { const v = $('#pdfv'); return (v ? v.clientWidth : innerWidth) >= 1000 && !(C.Focus && C.Focus.on()); };
// open or not, and beside the pages or over them
function place(open){
  const v = $('#pdfv'); if (!v) return;
  v.classList.toggle('pside', !!open);
  v.classList.toggle('pdock', !!open && wide() && !V.grid);
}
// (in focus mode it's focus mode's drawer; the panel's place beside the pages waits for after)
const sideOn = () => { const v = $('#pdfv'); return !!v && (C.Focus && C.Focus.on() ? document.documentElement.classList.contains('ftoc') : v.classList.contains('pside')); };
const TABS = [['pages', 'Pages'], ['contents', 'Contents'], ['marks', 'Highlights'], ['find', 'Search']];
function openSide(tab){
  const v = $('#pdfv'); if (!v || !P.pdf) return;
  if (tab) V.tab = tab;
  if (C.Focus && C.Focus.on()) C.Focus.toc(true); else place(true);
  if (wide() && !V.grid) { V.side = true; keep(); }
  drawSide();
  if (!V.grid && wide()) relayoutSoon();
}
function closeSide(){
  const v = $('#pdfv'); if (!v) return;
  if (C.Focus && C.Focus.on()) { C.Focus.close(); V.grid = false; look(); TQ.want.clear(); return; }
  const had = v.classList.contains('pdock');
  place(false); V.grid = false; look();
  if (wide()) { V.side = false; keep(); if (had) relayoutSoon(); }
  if (P.tobs) { P.tobs.disconnect(); P.tobs = null; }
  TQ.want.clear();
}
// Over the pages (a narrow screen, focus mode, All pages): a page or a chapter chosen puts it away.
const afterGo = () => { if (V.grid || !wide()) closeSide(); };
let relayT = 0;
function relayoutSoon(){ clearTimeout(relayT); relayT = setTimeout(() => { if (P.pdf) relayout(); }, 60); }

function drawSide(){
  const s = $('#pside'); if (!s || !P.pdf) return;
  s.innerHTML = '<div class="pstabs" role="tablist">' + TABS.map(([k, l]) => '<button role="tab" data-ps="' + k + '" class="' + (V.tab === k ? 'on' : '') + '">' + l + '</button>').join('') +
    '<span class="spacer"></span><button class="ib' + (V.grid ? ' on' : '') + '" data-pv="grid" title="All pages' + tip('grid') + '" aria-label="All pages">' + IC.grid + '</button>' +
    '<button class="ib" data-pv="sideclose" title="Close" aria-label="Close">' + IC.x + '</button></div><div class="psbody" id="psbody"></div>';
  drawTab();
}
function drawTab(){
  const b = $('#psbody'); if (!b || !P.pdf) return;
  $$('#pside [data-ps]').forEach(t => t.classList.toggle('on', t.dataset.ps === V.tab));
  if (P.tobs) { P.tobs.disconnect(); P.tobs = null; }
  TQ.want.clear();
  b.dataset.ptab = V.tab;
  if (V.tab === 'pages') drawThumbs(b);
  else if (V.tab === 'contents') drawContents(b);
  else if (V.tab === 'marks') drawHls(b);
  else drawFind(b);
}
const label = pg => P.labels && P.labels[pg - 1] ? P.labels[pg - 1] : String(pg);
// Scroll one box (only it, not the page round it, as scrollIntoView would) so `el` is in it: in the
// middle, or just inside the nearest edge.
function into(box, el, mid){
  if (!box || !el) return;
  const b = box.getBoundingClientRect(), r = el.getBoundingClientRect();
  if (mid) { box.scrollTop += r.top - b.top - (box.clientHeight - r.height) / 2; box.scrollLeft += Math.max(0, r.right - b.right + 16) - Math.max(0, b.left - r.left + 16); return; }
  if (r.top < b.top) box.scrollTop -= b.top - r.top + 8; else if (r.bottom > b.bottom) box.scrollTop += r.bottom - b.bottom + 8;
}

// The pages as small pictures, drawn as they come into view and kept for the PDF's while.
function drawThumbs(b){
  const p1 = $('.pdfpage[data-pg="1"]'), ratio = p1 ? p1.offsetWidth / p1.offsetHeight : 0.7;
  let h = '<div class="pths">';
  for (let i = 1; i <= P.pdf.numPages; i++) {
    const u = P.thumbs.get(i);
    h += '<button class="pth' + (i === P.page ? ' on' : '') + (hasMarks(i) ? ' hl' : '') + '" data-gopg="' + i + '"><span class="pthc" style="aspect-ratio:' + ratio.toFixed(4) + '">' + (u ? '<img alt="" src="' + u + '">' : '') + '</span><span class="pthn">' + esc(label(i)) + '</span></button>';
  }
  b.innerHTML = h + '</div>';
  P.tobs = new IntersectionObserver(es => es.forEach(e => {
    const n = +e.target.dataset.gopg;
    if (e.isIntersecting && !P.thumbs.has(n)) TQ.want.add(n); else if (!e.isIntersecting) TQ.want.delete(n);
    pumpThumbs();
  }), { root: b, rootMargin: '400px 0px' });
  setTimeout(pumpThumbs, 0);
  $$('.pth', b).forEach(el => P.tobs.observe(el));
  into(b, $('.pth.on', b), true);
}
// The pages small, as pictures (JPEGs, so hundreds of them stay light), one at a time: those in the
// middle of the panel first, and from the page itself when it's already drawn.
const TQ = { want: new Set(), busy: false };
async function pumpThumbs(){
  if (TQ.busy) return;
  TQ.busy = true;
  const gen = P.gen;
  try {
    while (TQ.want.size && gen === P.gen && P.pdf && $('#psbody')) {
      const b = $('#psbody'), r = b.getBoundingClientRect(), at = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
      const mid = at && at.closest && at.closest('.pth') ? +at.closest('.pth').dataset.gopg : P.page;
      let n = null; for (const k of TQ.want) if (n === null || Math.abs(k - mid) < Math.abs(n - mid)) n = k;
      TQ.want.delete(n);
      if (P.thumbs.has(n)) continue;
      P.thumbs.set(n, null);
      try { await thumb(n, gen); } catch(e){ if (gen === P.gen) P.thumbs.delete(n); }
    }
  } finally { TQ.busy = false; }
}
async function thumb(n, gen){
  const W = 240, drawn = $('.pdfpage[data-pg="' + n + '"] canvas');
  let cv = document.createElement('canvas');
  if (drawn && drawn.width > W && P.rendered.get(n) === 'done') {
    cv.width = W; cv.height = Math.round(drawn.height * W / drawn.width);
    cv.getContext('2d').drawImage(drawn, 0, 0, cv.width, cv.height);
  } else {
    const page = await P.pdf.getPage(n), v = page.getViewport({ scale: 1 }), vp = page.getViewport({ scale: W / v.width });
    cv.width = Math.round(vp.width); cv.height = Math.round(vp.height);
    const x = cv.getContext('2d'); x.fillStyle = '#fff'; x.fillRect(0, 0, cv.width, cv.height);
    await page.render({ canvasContext: x, viewport: vp }).promise;
  }
  const blob = await new Promise(ok => cv.toBlob(ok, 'image/jpeg', 0.82)); cv = null;
  if (gen !== P.gen || !blob) return;
  const u = URL.createObjectURL(blob); P.thumbs.set(n, u);
  const c = $('#pside .pth[data-gopg="' + n + '"] .pthc'); if (c) c.innerHTML = '<img alt="" src="' + u + '">';
}

// The PDF's own contents (its bookmarks), each with its page.
async function drawContents(b){
  if (P.outline === null) { b.innerHTML = '<p class="mute pse">Reading the contents…</p>'; try { P.outline = (await P.pdf.getOutline()) || []; } catch(e){ P.outline = []; } if (V.tab !== 'contents') return; }
  if (!P.outline.length) { b.innerHTML = '<p class="mute pse">This PDF has no contents.</p>'; return; }
  const flat = []; (function walk(items, d){ for (const it of items) { flat.push({ it, d }); if (it.items && it.items.length) walk(it.items, d + 1); } })(P.outline, 0);
  P.flatOut = flat;
  b.innerHTML = '<div class="ptoc">' + flat.map((x, i) => '<button class="pto d' + Math.min(x.d, 3) + '" data-goout="' + i + '"><span>' + esc(x.it.title || '—') + '</span><em data-outpg="' + i + '"></em></button>').join('') + '</div>';
  // each one's page, as they're found
  for (let i = 0; i < flat.length; i++) {
    const at = await destOf(flat[i].it); if (!at || V.tab !== 'contents' || P.flatOut !== flat) continue;
    flat[i].at = at;
    const em = $('#pside [data-outpg="' + i + '"]'); if (em) em.textContent = label(at.pg);
  }
  markContents();
}
// Where a contents entry goes: {pg, frac} (its place down the page, when the PDF says).
async function destOf(it){
  if (it.at) return it.at;
  try {
    let d = it.dest; if (typeof d === 'string') d = await P.pdf.getDestination(d);
    if (!Array.isArray(d) || !d.length) return null;
    const idx = typeof d[0] === 'number' ? d[0] : await P.pdf.getPageIndex(d[0]);
    let frac = 0;
    if (d[1] && d[1].name === 'XYZ' && typeof d[3] === 'number') { const pg = await P.pdf.getPage(idx + 1), vb = pg.view; frac = Math.max(0, Math.min(1, 1 - (d[3] - vb[1]) / (vb[3] - vb[1]))); }
    return (it.at = { pg: idx + 1, frac });
  } catch(e){ return null; }
}
// The chapter I'm in: the last one that starts at or before this page.
function markContents(){
  const flat = P.flatOut; if (!flat || V.tab !== 'contents') return;
  let on = -1; flat.forEach((x, i) => { if (x.at && x.at.pg <= P.page) on = i; });
  $$('#pside .pto').forEach((el, i) => el.classList.toggle('on', i === on));
}

// The highlights on these pages, in page order; one made in the text view is found on the page when chosen.
function drawHls(b){
  const hs = (P.d && P.d.highlights || []).map(h => ({ h, pl: placeOf(h) })).sort((a, b) => (a.pl ? a.pl.pg : 1e9) - (b.pl ? b.pl.pg : 1e9));
  if (!hs.length) { b.innerHTML = '<p class="mute pse">No highlights yet.</p>'; return; }
  b.innerHTML = '<div class="phls">' + hs.map(({ h, pl }) => '<button class="phl" data-gohl="' + esc(h.id) + '"><i data-color="' + esc(h.color || 'yellow') + '"></i><span>' + esc((h.text || '').slice(0, 220)) +
    ((h.user_note || '').trim() ? '<b>' + esc(h.user_note.slice(0, 160)) + '</b>' : '') + '</span><em>' + (pl ? esc(label(pl.pg)) : '') + '</em></button>').join('') + '</div>';
}

// Search: every page's words, read once; the pages it's on, a few words round each.
function drawFind(b){
  b.innerHTML = '<div class="psq"><span class="ic">' + IC.search + '</span><input id="pfind" placeholder="Search in the PDF" autocomplete="off" value="' + esc(P.find ? P.find.raw : '') + '"></div>' +
    '<div id="pfres">' + (P.find ? '<p class="mute pse" id="pfstat">Searching…</p><div class="pfl" id="pfl"></div>' : '') + '</div>';
  const inp = $('#pfind');
  let t = 0;
  inp.addEventListener('input', () => { clearTimeout(t); t = setTimeout(() => search(inp.value), 280); });
  inp.addEventListener('keydown', e => {
    if (e.key === 'Enter') { e.preventDefault(); clearTimeout(t); if (P.find && P.find.raw === inp.value && P.find.hits.length) nextHit(e.shiftKey ? -1 : 1); else search(inp.value); }
    else if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); if (inp.value) { inp.value = ''; search(''); } else closeSide(); }
  });
  if (P.find) listHits();
  setTimeout(() => inp.focus({ preventScroll: true }), 30);
}
async function pageText(n){
  if (P.texts.has(n)) return P.texts.get(n);
  const page = await P.pdf.getPage(n), tc = await page.getTextContent();
  let s = ''; for (const it of tc.items) { if (!('str' in it)) continue; if (s && !/\s$/.test(s)) s += ' '; s += it.str; if (it.hasEOL) s += ' '; }
  const t = norm(s); P.texts.set(n, t); return t;
}
async function search(raw){
  const q = norm(raw).toLowerCase(), gen = P.gen;
  P.find = q.length >= 2 ? { raw, q, hits: [], cur: null, done: false } : null;
  redrawAll();
  const res = $('#pfres'); if (!res) return;
  if (!P.find) { res.innerHTML = ''; return; }
  const f = P.find, N = P.pdf.numPages;
  res.innerHTML = '<p class="mute pse" id="pfstat">Searching…</p><div class="pfl" id="pfl"></div>';
  for (let n = 1; n <= N; n++) {
    let t; try { t = (await pageText(n)).toLowerCase(); } catch(e){ continue; }
    if (P.find !== f || gen !== P.gen) return;
    let k = 0;
    for (let at = t.indexOf(q); at >= 0 && f.hits.length < 500; at = t.indexOf(q, at + q.length), k++) f.hits.push({ pg: n, n: k, at, snip: snip(P.texts.get(n), at, q.length) });
    if (n % 20 === 0 || n === N) { listHits(); const st = $('#pfstat'); if (st && n < N) st.textContent = 'Searching… ' + n + ' of ' + N; }
  }
  f.done = true; listHits();
}
const snip = (t, at, len) => { const a = Math.max(0, at - 40), b = Math.min(t.length, at + len + 60); return (a > 0 ? '…' : '') + esc(t.slice(a, at)) + '<b>' + esc(t.slice(at, at + len)) + '</b>' + esc(t.slice(at + len, b)) + (b < t.length ? '…' : ''); };
function listHits(){
  const f = P.find, l = $('#pfl'), st = $('#pfstat'); if (!f || !l) return;
  if (f.done && st) st.textContent = f.hits.length ? (f.hits.length >= 500 ? 'The first 500' : f.hits.length === 1 ? 'Found once' : 'Found ' + f.hits.length + ' times') : 'Not found';
  const have = l.children.length;
  l.insertAdjacentHTML('beforeend', f.hits.slice(have).map((x, i) => '<button class="pfh' + (f.cur && f.cur === x ? ' on' : '') + '" data-gohit="' + (have + i) + '"><em>' + esc(label(x.pg)) + '</em><span>' + x.snip + '</span></button>').join(''));
}
function goHit(i){
  const f = P.find, x = f && f.hits[i]; if (!x) return;
  f.cur = x; f.i = i;
  $$('#pfl .pfh').forEach((b, k) => b.classList.toggle('on', k === i));
  scrollToPage(x.pg);
  redrawAll();
  // on its page once that's drawn: in view, and standing out
  (async () => { for (let k = 0; k < 20; k++) { const m = $('.pdfpage[data-pg="' + x.pg + '"] .phit.cur'); if (m) { into($('#pdfpages'), m, true); return; } await new Promise(r => setTimeout(r, 150)); if (P.find !== f) return; drawMarks(x.pg); } })();
}
function nextHit(dir){ const f = P.find; if (!f || !f.hits.length) return; goHit(((f.i == null ? (dir > 0 ? -1 : 0) : f.i) + dir + f.hits.length) % f.hits.length); }

/* ---------- going to a page ---------- */
function goPage(pg, frac){
  if (!P.pdf) return;
  pg = Math.max(1, Math.min(P.pdf.numPages, Math.round(pg)));
  scrollToPage(pg, frac);
}
// The next or the previous page, or pair of pages side by side.
function step(dir){
  const r = P.rows.findIndex(x => x.includes(P.page)); if (r < 0) return;
  const to = P.rows[r + dir]; if (to) goPage(to[0]);
}
// The page number in the bar: a box to type a page in (a printed page number, when the PDF has them,
// or the page's place), and a slider through the whole PDF.
function openGoto(anchor){
  const p = $('#pop'), r = anchor.getBoundingClientRect(), N = P.pdf.numPages;
  p.innerHTML = '<div class="pgo"><div class="pgorow"><input id="pgoin" class="field" inputmode="' + (P.labels ? 'text' : 'numeric') + '" autocomplete="off" placeholder="Page" aria-label="Page">' +
    '<button class="btn primary sm" id="pgogo">Go</button></div>' +
    '<input type="range" id="pgosl" min="1" max="' + N + '" value="' + P.page + '" aria-label="Page"><div class="pgolab mute tiny" id="pgolab"></div></div>';
  p.hidden = false;
  p.style.left = Math.max(8, Math.min(innerWidth - p.offsetWidth - 8, r.left + r.width / 2 - p.offsetWidth / 2)) + 'px'; p.style.top = (r.bottom + 8) + 'px';
  const inp = $('#pgoin'), sl = $('#pgosl'), lab = $('#pgolab');
  const say = n => { lab.textContent = (P.labels ? 'p. ' + label(n) + ' · ' : '') + n + ' of ' + N; };
  say(P.page);
  const go = () => {
    const v = inp.value.trim(); if (!v) return;
    let n = P.labels ? P.labels.findIndex(l => l && l.toLowerCase() === v.toLowerCase()) + 1 : 0;
    if (!n && /^\d+$/.test(v)) n = +v;
    if (!n || n > N) { inp.classList.add('bad'); return; }
    p.hidden = true; goPage(n);
  };
  inp.addEventListener('keydown', e => { if (e.key === 'Enter') { e.preventDefault(); go(); } else if (e.key === 'Escape') { e.preventDefault(); p.hidden = true; } });
  inp.addEventListener('input', () => inp.classList.remove('bad'));
  $('#pgogo').onclick = go;
  sl.addEventListener('input', () => say(+sl.value));
  sl.addEventListener('change', () => goPage(+sl.value));
  if (matchMedia('(pointer: fine)').matches) inp.focus({ preventScroll: true });
}

/* ---------- the view menu ---------- */
const pct = () => Math.round(P.base * P.zoom * 72 / 96 * 100);
function openView(anchor){
  const p = $('#pop'), r = anchor.getBoundingClientRect();
  const it = (k, l, on) => '<button data-pvm="' + k + '"' + (on ? ' class="on"' : '') + '><span>' + l + '</span><i>' + (on ? '✓' : '') + '</i></button>';
  p.innerHTML = '<div class="menu pvmenu"><div class="pvzoom"><button class="ib" data-pvm="out" aria-label="Smaller">−</button><b>' + pct() + '%</b><button class="ib" data-pvm="in" aria-label="Larger">+</button></div>' +
    it('fit:width', 'Fit the width', !V.paged && V.fit === 'width' && P.zoom === 1) + it('fit:page', 'The whole page', (V.paged || V.fit === 'page') && P.zoom === 1) + '<hr>' +
    it('paged:0', 'Scroll', !V.paged) + it('paged:1', 'Page by page', V.paged) + '<hr>' +
    it('two:0', 'One page', !V.two) + it('two:1', 'Two pages', V.two) + '<hr>' +
    it('dark', 'Dark pages', V.dark) + '<hr>' +
    '<a href="' + P.src.file + '" download>Download the PDF</a>' + (C.Keys ? '<button data-pvm="keys"><span>Keyboard shortcuts</span><i>?</i></button>' : '') + '</div>';
  p.hidden = false;
  p.style.left = Math.max(8, Math.min(innerWidth - p.offsetWidth - 8, r.right - p.offsetWidth)) + 'px'; p.style.top = (r.bottom + 8) + 'px';
}
function viewAct(k){
  if (k === 'in' || k === 'out') { zoom(k === 'in' ? 1 : -1); const b = $('#pop .pvzoom b'); if (b) setTimeout(() => { b.textContent = pct() + '%'; }, 120); return; }
  $('#pop').hidden = true;
  if (k === 'keys') { C.Keys.sheet('pdf', 'PDF shortcuts'); return; }
  if (k === 'dark') { V.dark = !V.dark; keep(); look(); return; }
  const [a, v] = k.split(':');
  if (a === 'fit') { V.fit = v; P.zoom = 1; store.set('pdfZoom', 1); if (V.paged && v === 'width') V.paged = false; }
  else if (a === 'paged') { V.paged = v === '1'; P.zoom = 1; store.set('pdfZoom', 1); }
  else if (a === 'two') V.two = v === '1';
  keep(); look(); relayout();
}

/* ---------- page, zoom, progress, reading time ---------- */
function showPage(){
  const pp = $('#ppg'); if (pp && P.pdf) pp.textContent = (P.labels && innerWidth > 600 ? 'p. ' + label(P.page) + ' · ' : '') + P.page + ' / ' + P.pdf.numPages;
  if (sideOn()) {
    if (V.tab === 'pages') { const was = $('#pside .pth.on'), on = $('#pside .pth[data-gopg="' + P.page + '"]'); if (was !== on) { if (was) was.classList.remove('on'); if (on) { on.classList.add('on'); into($('#psbody'), on); } } }
    else if (V.tab === 'contents') markContents();
  }
}
function onScroll(){
  const box = $('#pdfpages'); if (!box || !P.pdf) return;
  const bb = box.getBoundingClientRect(), mid = bb.top + box.clientHeight * (V.paged ? 0.5 : 0.35);
  // the row across the line a third of the way down (the middle, page by page), and its first page in view
  const row = $$('.pdfrow', box).find(el => { const r = el.getBoundingClientRect(); return r.top <= mid && r.bottom >= mid; });
  const cur = row && ([...row.children].find(el => { const r = el.getBoundingClientRect(); return r.right > bb.left + 8 && r.left < bb.right - 8; }) || row.firstElementChild);
  if (cur && +cur.dataset.pg !== P.page) {
    if (Date.now() - P.pageAt >= 5000) P.seen.add('p' + P.page);       // a page in front of me for 5 s counts for page goals
    P.page = +cur.dataset.pg; P.pageAt = Date.now();
  }
  showPage();
  P.active = Date.now();
  clearTimeout(P.saveT);
  P.saveT = setTimeout(() => {
    if (!P.id || !P.pdf) return;
    store.set('pdfPage.' + P.id, P.page);
    if (P.src.book) {                     // a book's place, where I am (not the furthest), as its reader keeps it
      const body = { cfi: 'pdf:' + P.page, fraction: P.page / P.pdf.numPages, chapter: 'p. ' + P.page, at: Math.floor(Date.now() / 1000), pages: [...P.seen] };
      P.seen = new Set();
      api('/api/ebooks/' + encodeURIComponent(P.id) + '/position', { method: 'PUT', body: JSON.stringify(body) }).catch(() => {});
      return;
    }
    const pct = Math.round(P.page / P.pdf.numPages * 100);
    if (pct > (P.d && P.d.progress || 0)) { P.d.progress = pct; api('/api/docs/' + encodeURIComponent(P.id) + '/progress', { method: 'PUT', body: JSON.stringify({ pct }) }).catch(() => {}); }
  }, 1200);
}
const ZMIN = 0.5, ZMAX = 4;
async function zoom(dir){
  P.zoom = Math.max(ZMIN, Math.min(ZMAX, Math.round((P.zoom * (dir > 0 ? 1.15 : 1 / 1.15)) * 100) / 100));
  if (Math.abs(P.zoom - 1) < 0.04) P.zoom = 1;
  store.set('pdfZoom', P.zoom);
  await relayout();
}
// Fit the width, or the whole page, each time (and back to the fit from a zoom).
function toggleFit(){ if (P.zoom !== 1) P.zoom = 1; else V.fit = V.fit === 'width' ? 'page' : 'width'; store.set('pdfZoom', 1); keep(); relayout(); }

// Pinching (two fingers on a tablet, ⌘ and the wheel or a trackpad's pinch on a Mac): the pages grow
// under the fingers at once, and are drawn again at the new size when it stops.
const Z = { s: 1, t: 0 };
function liveScale(s, cx, cy){
  const box = $('#pdfpages'), inn = $('#pdfin'); if (!box || !inn) return;
  const lim = Math.max(ZMIN / P.zoom, Math.min(ZMAX / P.zoom, s));
  if (!Z.o) { const b = box.getBoundingClientRect(), ib = inn.getBoundingClientRect(); Z.o = { ox: cx - ib.left, oy: cy - ib.top, cx: cx - b.left, cy: cy - b.top }; }
  Z.s = lim;
  inn.style.transformOrigin = Z.o.ox + 'px ' + Z.o.oy + 'px'; inn.style.transform = 'scale(' + lim + ')';
}
async function settleScale(){
  const box = $('#pdfpages'), inn = $('#pdfin'), o = Z.o, s = Z.s; Z.o = null; Z.s = 1;
  if (!box || !inn || !o || Math.abs(s - 1) < 0.02) { if (inn) inn.style.transform = ''; return; }
  const z0 = P.zoom; P.zoom = Math.max(ZMIN, Math.min(ZMAX, Math.round(z0 * s * 100) / 100)); store.set('pdfZoom', P.zoom);
  const k = P.zoom / z0;
  await layout();
  const b2 = $('#pdfpages'), i2 = $('#pdfin'); if (!b2 || !i2) return;
  b2.scrollLeft = Math.max(0, i2.offsetLeft + o.ox * k - o.cx); b2.scrollTop = Math.max(0, i2.offsetTop + o.oy * k - o.cy);
  onScroll();
}
document.addEventListener('wheel', e => {
  if (C.S.route[0] !== 'pdf' || !(e.ctrlKey || e.metaKey) || !e.target.closest || !e.target.closest('#pdfpages')) return;
  e.preventDefault();
  liveScale(Z.s * Math.exp(-e.deltaY / 300), e.clientX, e.clientY);
  clearTimeout(Z.t); Z.t = setTimeout(settleScale, 260);
}, { passive: false });
// Fingers on the pages: two pinch; one swiped sideways (when the pages aren't wider than the screen)
// turns the page.
(() => {
  let pin = null, sw = null;
  const dist = t => Math.hypot(t[0].clientX - t[1].clientX, t[0].clientY - t[1].clientY);
  document.addEventListener('touchstart', e => {
    if (C.S.route[0] !== 'pdf' || !e.target.closest || !e.target.closest('#pdfpages')) return;
    if (e.touches.length === 2) { sw = null; pin = { d0: dist(e.touches), x: (e.touches[0].clientX + e.touches[1].clientX) / 2, y: (e.touches[0].clientY + e.touches[1].clientY) / 2 }; Z.o = null; }
    else if (e.touches.length === 1) sw = { x: e.touches[0].clientX, y: e.touches[0].clientY, t: e.timeStamp };
  }, { passive: true });
  document.addEventListener('touchmove', e => {
    if (!pin || e.touches.length !== 2) return;
    e.preventDefault();
    liveScale(dist(e.touches) / pin.d0, pin.x, pin.y);
  }, { passive: false });
  const end = e => {
    if (pin && e.touches.length < 2) { pin = null; settleScale(); sw = null; return; }
    if (!sw || e.type === 'touchcancel') { sw = null; return; }
    const t = e.changedTouches[0], dx = t.clientX - sw.x, dy = t.clientY - sw.y, box = $('#pdfpages'); sw = null;
    if (!box || box.scrollWidth > box.clientWidth + 2 || Math.abs(dx) < 70 || Math.abs(dx) < 2 * Math.abs(dy)) return;
    const s = window.getSelection(); if (s && !s.isCollapsed) return;
    step(dx < 0 ? 1 : -1);
  };
  document.addEventListener('touchend', end, { passive: true });
  document.addEventListener('touchcancel', end, { passive: true });
})();

/* ---------- the bar's buttons, the panel's, the keys ---------- */
document.addEventListener('click', e => {
  if (C.S.route[0] !== 'pdf' || !e.target.closest) return;
  if (e.target.closest('[data-fe="toc"]')) { V.grid = false; look(); setTimeout(drawSide, 0); return; }
  const m = e.target.closest('[data-pvm]'); if (m) { e.preventDefault(); viewAct(m.dataset.pvm); return; }
  const t = e.target.closest('[data-ps]'); if (t) { V.tab = t.dataset.ps; keep(); drawTab(); return; }
  const g = e.target.closest('[data-gopg]'); if (g) { goPage(+g.dataset.gopg); afterGo(); return; }
  const o = e.target.closest('[data-goout]'); if (o) { const x = P.flatOut && P.flatOut[+o.dataset.goout]; if (x) destOf(x.it).then(at => { if (at) { goPage(at.pg, at.frac); afterGo(); } }); return; }
  const hl = e.target.closest('[data-gohl]'); if (hl) { goToHl(hl.dataset.gohl); afterGo(); return; }
  const h = e.target.closest('[data-gohit]'); if (h) { goHit(+h.dataset.gohit); if (!wide()) afterGo(); return; }
  const b = e.target.closest('[data-pv]'); if (!b) return;
  const a = b.dataset.pv;
  if (a === 'back') { if (P.src.book) { if ((C.S.navs || 0) > 1) history.back(); else location.hash = P.src.back; } else C.leaveDoc(P.d); return; }
  if (!P.pdf) return;
  if (a === 'in') zoom(1); else if (a === 'out') zoom(-1);
  else if (a === 'side') { if (sideOn() && !V.grid) closeSide(); else { V.grid = false; look(); openSide(); } }
  else if (a === 'sideclose') closeSide();
  else if (a === 'grid') toggleGrid();
  else if (a === 'find') openSide('find');
  else if (a === 'goto') { if (!$('#pop').hidden && $('#pop .pgo')) $('#pop').hidden = true; else openGoto(b); }
  else if (a === 'view') { if (!$('#pop').hidden && $('#pop .pvmenu')) $('#pop').hidden = true; else openView(b); }
});
// All pages: the side panel's pages over the whole reading area, as many across as fit.
function toggleGrid(){
  V.grid = !V.grid; look();
  if (V.grid) { V.tab = 'pages'; if (C.Focus && C.Focus.on()) C.Focus.toc(true); else place(true); drawSide(); }
  else if (wide() && V.side) { place(true); drawSide(); relayoutSoon(); }
  else closeSide();
}
document.addEventListener('keydown', e => {
  if (C.S.route[0] !== 'pdf' || !P.pdf || e.altKey || e.target.isContentEditable || /input|textarea|select/i.test(e.target.tagName)) return;
  if ((e.metaKey || e.ctrlKey) && e.key === 'f') { e.preventDefault(); openSide('find'); return; }
  if (e.metaKey || e.ctrlKey) return;
  if (K(e, 'larger')) { e.preventDefault(); zoom(1); }
  else if (K(e, 'smaller')) { e.preventDefault(); zoom(-1); }
  else if (K(e, 'fit')) { e.preventDefault(); toggleFit(); }
  else if (K(e, 'next')) { e.preventDefault(); step(1); }
  else if (K(e, 'prev')) { e.preventDefault(); step(-1); }
  else if (V.paged && (e.key === ' ' || e.key === 'PageDown')) { e.preventDefault(); step(e.shiftKey ? -1 : 1); }
  else if (V.paged && e.key === 'PageUp') { e.preventDefault(); step(-1); }
  else if (K(e, 'side')) { e.preventDefault(); if (sideOn()) closeSide(); else openSide(); }
  else if (K(e, 'grid')) { e.preventDefault(); toggleGrid(); }
  else if (K(e, 'search')) { e.preventDefault(); openSide('find'); }
  else if (K(e, 'goto')) { e.preventDefault(); openGoto($('#ppg')); }
  else if (K(e, 'highlight') && H.ctx && H.ctx.kind === 'sel') { e.preventDefault(); highlight(H.ctx.info); }
  else if (e.key === '?') { e.preventDefault(); C.Keys && C.Keys.sheet('pdf', 'PDF shortcuts'); }
  else if (e.key === 'Escape') {
    if (H.visible && H.visible()) H.hide();
    else if (!$('#pop').hidden) $('#pop').hidden = true;
    else if (V.grid || (sideOn() && !wide())) { e.preventDefault(); e.stopImmediatePropagation(); closeSide(); }
  }
}, true);
// A new size (the tablet turned, the window, focus mode): fitted pages fit it again.
let sizeT = 0, lastW = innerWidth, lastH = innerHeight;
window.addEventListener('resize', () => {
  if (C.S.route[0] !== 'pdf' || !P.pdf) return;
  clearTimeout(sizeT);
  sizeT = setTimeout(() => {
    if (innerWidth === lastW && Math.abs(innerHeight - lastH) < 80) return;      // (the keyboard, the browser's bars)
    lastW = innerWidth; lastH = innerHeight;
    const v = $('#pdfv');
    if (v && !V.grid && !(C.Focus && C.Focus.on())) { const was = v.classList.contains('pside'); if (wide() && V.side) { place(true); if (!was) drawSide(); } else if (!wide() && v.classList.contains('pdock')) place(false); else place(was); }
    relayout();
  }, 200);
});
['mousemove', 'keydown', 'touchstart', 'wheel'].forEach(ev => document.addEventListener(ev, () => { P.active = Date.now(); }, { passive: true }));
setInterval(() => {
  if (C.S.route[0] !== 'pdf' || !P.id || !P.pdf || document.hidden || Date.now() - P.active > 90000) return;
  C.sendBeat && C.sendBeat(Object.assign({ seconds: 15, at: Math.floor(Date.now() / 1000) }, P.src.beat));
}, 15000);

window.dispatchEvent(new Event('daf-pdf-ready'));
