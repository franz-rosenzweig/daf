/* All books (#catalog): the Calibre library laid out like Calibre's own main window (catalog.py): a
   toolbar of Calibre's actions for the chosen books, the search under it, the Tag browser on the left,
   the books as a spreadsheet or a cover grid, Book details on the right, and a status bar with the
   switches for the three. The search is Calibre's
   (tags:"=Fiction", added:>30daysago, formats:false, and / or / not); the Filter panel writes it:
   a value's first click puts it in, the second turns it into "not …", the third takes it out.
   The search, the order, the columns, their widths and Show private books are kept on this device;
   a saved view keeps them for every device (settings catalog_views). Calibre is only read here. */
(() => {
'use strict';
const C = window.DafCore, { api, esc, toast, $, $$ } = C;
const store = { get(k, d){ try { const v = localStorage.getItem('daf.' + k); return v == null ? d : JSON.parse(v); } catch(e){ return d; } }, set(k, v){ try { localStorage.setItem('daf.' + k, JSON.stringify(v)); } catch(e){} } };
const svg = (d, w) => '<svg width="' + (w || 16) + '" height="' + (w || 16) + '" viewBox="0 0 20 20" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">' + d + '</svg>';
const IC = {
  filter: svg('<path d="M3 5h14M6 10h8M8.5 15h3"/>'),
  cols: svg('<rect x="3" y="4" width="14" height="12" rx="2"/><path d="M8 4v12M12.5 4v12"/>'),
  views: svg('<path d="M5 3.5h10v13l-5-3.5-5 3.5z"/>'),
  dots: '<svg width="16" height="16" viewBox="0 0 20 20" aria-hidden="true"><circle cx="5" cy="10" r="1.5" fill="currentColor"/><circle cx="10" cy="10" r="1.5" fill="currentColor"/><circle cx="15" cy="10" r="1.5" fill="currentColor"/></svg>',
  grip: svg('<path d="M7 5h.01M13 5h.01M7 10h.01M13 10h.01M7 15h.01M13 15h.01" stroke-width="2.6"/>'),
  x: svg('<path d="M6 6l8 8M14 6l-8 8"/>', 14),
  chev: open => svg('<path d="' + (open ? 'M5 8l5 5 5-5' : 'M8 5l5 5-5 5') + '"/>', 14),
  sort: svg('<path d="M6 4v12M3 13l3 3 3-3M14 16V4M11 7l3-3 3 3"/>'),
  side: svg('<rect x="3" y="4" width="14" height="12" rx="2"/><path d="M8 4v12"/>'),
  det: svg('<rect x="3" y="4" width="14" height="12" rx="2"/><path d="M12 4v12"/>'),
  grid: svg('<rect x="3.5" y="3.5" width="5" height="5" rx="1"/><rect x="11.5" y="3.5" width="5" height="5" rx="1"/><rect x="3.5" y="11.5" width="5" height="5" rx="1"/><rect x="11.5" y="11.5" width="5" height="5" rx="1"/>'),
  qv: svg('<rect x="3" y="4" width="14" height="12" rx="2"/><path d="M3 11.5h14M6 14h3"/>'),
  pin: '<svg class="catpin" width="13" height="13" viewBox="0 0 20 20" aria-label="Marked" role="img" fill="currentColor"><path d="M12.6 2.4l5 5-2.3.7-3.4 3.4.4 4.1-1.4 1.4-3.5-3.5L3.2 17.7l-.9-.9 4.2-4.2L3 9.1l1.4-1.4 4.1.4 3.4-3.4z"/></svg>',
};
// Calibre's toolbar: [key, label, icon, when it can be pressed: 0 always, 1 one book, 'n' some, 2 two or more]
const TB = s => '<svg width="24" height="24" viewBox="0 0 20 20" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.35" stroke-linecap="round" stroke-linejoin="round">' + s + '</svg>';
const TOOLS = [
  ['add', 'Add books', TB('<path d="M4 4.5A1.5 1.5 0 0 1 5.5 3H15v12H5.5A1.5 1.5 0 0 0 4 16.5z"/><path d="M4 16.5A1.5 1.5 0 0 0 5.5 18H15"/><path d="M9.5 6v5.5M6.75 8.75h5.5"/>'), 0],
  ['edit', 'Edit metadata', TB('<path d="M4 16l1-4 8-8 3 3-8 8z"/><path d="M11.5 5.5l3 3"/>'), 'n'],
  ['conv', 'Convert books', TB('<path d="M4 7h11l-3-3M16 13H5l3 3"/>'), 'n'],
  ['read', 'Read', TB('<path d="M10 5.5C8.5 4.3 6.5 4 3 4v11c3.5 0 5.5.3 7 1.5 1.5-1.2 3.5-1.5 7-1.5V4c-3.5 0-5.5.3-7 1.5z"/><path d="M10 5.5v11"/>'), 1],
  ['ebook', 'Edit book', TB('<path d="M7 6.5L3.5 10 7 13.5M13 6.5l3.5 3.5-3.5 3.5M11.2 4.5l-2.4 11"/>'), 1],      // ebookedit.js
  ['find', 'Find details', TB('<circle cx="8.5" cy="8.5" r="5"/><path d="M12.2 12.2L17 17"/><path d="M8.5 6v5M6 8.5h5"/>'), 'n'],
  ['shelves', 'Shelves', TB('<path d="M6 3h8v14l-4-3-4 3z"/>'), 'n'],
  ['merge', 'Merge books', TB('<path d="M5 3v3.5c0 3 5 4 5 7V17M15 3v3.5c0 3-5 4-5 7"/>'), 2],
  ['epubmerge', 'EpubMerge', TB('<rect x="3" y="3" width="5.5" height="7" rx="1"/><rect x="11.5" y="3" width="5.5" height="7" rx="1"/><path d="M5.75 10v2.5h8.5V10M10 12.5V17M7.5 15l2.5 2 2.5-2"/>'), 2],      // epubmerge.js
  ['dl', 'Download', TB('<path d="M10 3v9.5M6 9l4 4 4-4M4 16.5h12"/>'), 'n'],
  ['openwith', 'Open with', TB('<rect x="3" y="4" width="14" height="12" rx="2"/><path d="M8 13l5-5M9 8h4v4"/>'), 1],
  ['remove', 'Remove books', TB('<path d="M4 6h12M8 6V4h4v2M5.8 6l.9 11h6.6l.9-11"/>'), 'n'],
  ['library', 'Library', TB('<path d="M4 3.5v13M7.5 3.5v13M11 4.5l3.5 12.5M3 16.5h14"/>'), 0],
];
// The Tag browser's categories in Calibre's order, each with its icon; Daf's own come after.
const GI = {
  authors: '<circle cx="10" cy="7" r="3"/><path d="M4 17c1-3.5 3.5-5 6-5s5 1.5 6 5"/>',
  languages: '<circle cx="10" cy="10" r="7"/><path d="M3 10h14M10 3c2 2.2 3 4.5 3 7s-1 4.8-3 7c-2-2.2-3-4.5-3-7s1-4.8 3-7z"/>',
  series: '<rect x="3.5" y="3.5" width="4" height="13" rx="1"/><rect x="8.5" y="3.5" width="4" height="13" rx="1"/><path d="M14 4.5l2.5 12"/>',
  formats: '<path d="M6 2.5h5l4 4V17.5H5V3z"/><path d="M11 2.5V7h4"/>',
  publisher: '<path d="M3 17h14M5 17V8l5-4 5 4v9M8.5 17v-4h3v4"/>',
  rating: '<path d="M10 3l2.1 4.4 4.9.6-3.6 3.3.9 4.8L10 13.8 5.7 16.1l.9-4.8L3 8l4.9-.6z"/>',
  tags: '<path d="M3 3h6l8 8-6 6-8-8z"/><circle cx="6.5" cy="6.5" r="1"/>',
  status: '<circle cx="10" cy="10" r="7"/><path d="M7 10l2 2 4-4"/>',
  shelves: '<path d="M6 3h8v14l-4-3-4 3z"/>',
  views: '<circle cx="8.5" cy="8.5" r="5"/><path d="M12.2 12.2L17 17"/>',
  added: '<circle cx="10" cy="10" r="7"/><path d="M10 6v4l3 2"/>',
  missing: '<circle cx="10" cy="10" r="7" stroke-dasharray="2.5 2.5"/>',
  tidy: '<path d="M10 3v3M10 14v3M3 10h3M14 10h3M5.5 5.5l2 2M12.5 12.5l2 2M14.5 5.5l-2 2M7.5 12.5l-2 2"/>',
  custom: '<rect x="3" y="4" width="14" height="12" rx="2"/><path d="M8 4v12"/>',
};
const ORDER = ['authors', 'languages', 'series', 'formats', 'publisher', 'rating', 'tags'];
const DEF = { q: '', sort: 'added', desc: true, cols: null, widths: {}, priv: false, view: null };
const saved = store.get('catalog', {});
const P = Object.assign({}, DEF, saved, { data: null, facets: null, side: store.get('calSide', true), det: store.get('calDet', true), grid: store.get('calGrid', false), info: new Map(),
  qv: store.get('calQv', false), qvField: store.get('calQvField', 'authors'), qvVal: null, cell: 'title',
  open: new Set(store.get('catalogOpen', ['added', 'missing', 'tidy', 'status', 'tags'])), all: new Set(), fq: '', scroll: 0, seq: 0, sel: new Set(), anchor: null });
const keep = () => store.set('catalog', { q: P.q, sort: P.sort, desc: P.desc, cols: P.cols, widths: P.widths, priv: P.priv, view: P.view, lastView: P.lastView });
const WIDTH = { title: 300, authors: 180, series: 170, tags: 200, rating: 112, added: 112, published: 100, modified: 112, publisher: 160, languages: 90,
  formats: 110, size: 80, isbn: 130, identifiers: 240, cover: 70, status: 96, progress: 120, last_read: 112, audio: 110, highlights: 92, shelves: 160, calibre_id: 90 };
const NUMERIC = new Set(['number', 'rating', 'percent', 'size']);
const colsNow = () => { const all = P.data ? P.data.columns : []; const known = new Set(all.map(c => c.key));
  const want = (P.cols || (P.data && P.data.default_columns) || ['title']).filter(k => known.has(k));
  if (!want.includes('title')) want.unshift('title');
  return want.map(k => all.find(c => c.key === k)); };
const widthOf = c => P.widths[c.key] || WIDTH[c.key] || (c.type === 'list' ? 160 : NUMERIC.has(c.type) ? 92 : c.type === 'date' ? 112 : 140);

/* ---------- the cells ---------- */
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const day = (s, monthOnly) => { if (!s) return ''; const [y, m, d] = s.split('-').map(Number); return monthOnly ? MONTHS[m - 1] + ' ' + y : MONTHS[m - 1] + ' ' + d + ', ' + y; };
const stars = n => { if (n == null) return ''; const full = Math.floor(n), half = n - full >= .5;
  return '<span class="catstars" aria-label="' + n + ' stars">' + '★'.repeat(full) + (half ? '½' : '') + '<i>' + '★'.repeat(5 - full - (half ? 1 : 0)) + '</i></span>'; };
function cellHtml(b, c){
  const v = b[c.key];
  if (c.key === 'title') return '<a class="catt" href="#book/' + encodeURIComponent(b.id) + '">' + (b.cover ? '<img class="cv catcv" src="/api/cover/' + encodeURIComponent(b.id) + '?v=' + (b.cover_v || 0) + '" alt="" loading="lazy">' : C.cover({ id: b.id, title: b.title }, 'cv catcv')) + '<span>' + (b.marked ? IC.pin : '') + esc(b.title) + '</span></a>';
  if (c.key === 'series') return v ? esc(v) + ' <span class="mute">#' + (Math.round((b.series_index || 0) * 10) / 10) + '</span>' : '';
  if (v == null || v === '' || (Array.isArray(v) && !v.length)) return '';
  if (c.type === 'rating') return stars(v);
  if (c.type === 'date') return day(v, c.key === 'published');
  if (c.type === 'size') return (v / 1048576).toFixed(1) + ' MB';
  if (c.type === 'percent') return '<span class="catpct" title="' + esc(b.progress_note || '') + '">' + C.bar(v) + '<span>' + Math.round(v) + '%</span></span>';
  if (c.type === 'bool') return v ? '✓' : '';
  if (c.type === 'number') return esc(typeof v === 'number' ? (Math.round(v * 100) / 100).toLocaleString() : v);
  if (Array.isArray(v)) return esc(v.join(c.key === 'authors' ? ' & ' : ', '));
  return esc(v);
}

/* ---------- the page ---------- */
const narrow = () => matchMedia('(max-width:1100px)').matches;        // there the side panels are sheets over the books
C.views.catalog = async () => {
  if (narrow()) { P.side = false; P.det = false; P.qv = false; }
  $('#main').innerHTML = '<div class="top cattop caltop"><h1 class="sr">All books</h1><div class="caltools" id="caltools" role="toolbar" aria-label="Calibre">' +
    TOOLS.filter(([k]) => k !== 'openwith' || canOpenWith()).map(([k, l, ic]) => '<button class="caltool' + (k === 'library' ? ' end' : '') + '" data-cal="' + k + '">' + ic + '<span>' + l + '</span></button>').join('') + '</div></div>' +
    '<div class="calsearch"><button class="btn sm catb" data-act="cat:views" id="catviewb">' + IC.views + '<span>' + esc(P.view || 'Views') + '</span></button>' +
    '<input class="field catq" id="catq" type="search" placeholder="Search" autocomplete="off" autocapitalize="off" spellcheck="false" aria-label="Search" value="' + esc(P.q) + '">' +
    '<button class="btn sm catb" data-act="cat:sort">' + IC.sort + '<span>Sort</span></button>' +
    '<button class="btn sm catb" data-act="cat:cols">' + IC.cols + '<span>Columns</span></button></div>' +
    '<div class="catpage' + (P.side ? ' filt' : '') + (P.det ? ' det' : '') + (P.qv ? ' qv' : '') + '" id="catpage"><div class="catshade" data-catm="shade"></div><aside class="catside" id="catside" aria-label="Tag browser"></aside>' +
    '<div class="catmid"><div class="catscroll" id="catscroll"><p class="mute catmsg">Loading…</p></div><section class="catqv" id="catqv" aria-label="Quickview"></section></div><aside class="catdet" id="catdet" aria-label="Book details"></aside></div>' +
    '<div class="calstatus" id="calstatus"><span class="num" id="catn"></span><span id="calsel"></span><span class="spacer"></span>' +
    '<button class="calsw" data-act="cat:side" aria-pressed="' + P.side + '">' + IC.side + '<span>Tag browser</span></button>' +
    '<button class="calsw" data-act="cat:det" aria-pressed="' + P.det + '">' + IC.det + '<span>Book details</span></button>' +
    '<button class="calsw" data-act="cat:grid" aria-pressed="' + P.grid + '">' + IC.grid + '<span>Cover grid</span></button>' +
    '<button class="calsw" data-act="cat:qv" aria-pressed="' + P.qv + '">' + IC.qv + '<span>Quickview</span></button></div>';
  await load(P.side);
  if (P.side) drawSide();
};

async function load(withFacets){
  const n = ++P.seq;
  const qs = new URLSearchParams({ q: P.q, sort: P.sort, desc: P.desc ? '1' : '0' });
  if (P.priv) qs.set('private', '1');
  if (withFacets || !P.facets) qs.set('facets', '1');
  let r;
  try { r = await api('/api/catalog?' + qs.toString()); }
  catch(e){ const s = $('#catscroll'); if (s) s.innerHTML = '<p class="placeholder catmsg">' + esc(e.message) + '</p>'; return; }
  if (n !== P.seq || C.S.route[0] !== 'catalog') return;               // the search changed again since
  P.data = r;
  if (r.facets) P.facets = r.facets;
  draw();
}

function draw(){
  const box = $('#catscroll'); if (!box || !P.data) return;
  const r = P.data, cols = colsNow();
  const q = $('#catq'); if (q) { q.classList.toggle('bad', !!r.error); q.title = r.error || ''; }
  const shown = new Set(r.books.map(b => b.calibre_id));
  for (const id of [...P.sel]) if (!shown.has(id)) P.sel.delete(id);          // only what the list shows stays chosen
  let h;
  if (P.grid) {          // Calibre's Cover grid
    h = '<div class="calgrid">' + r.books.map(b => '<div class="calcell' + (P.sel.has(b.calibre_id) ? ' sel' : '') + (b.private ? ' priv' : '') + '" data-cid="' + esc(b.id) + '" data-cal="' + b.calibre_id + '" tabindex="0">' +
      '<span class="calcv">' + (b.cover ? '<img src="/api/cover/' + encodeURIComponent(b.id) + '?v=' + (b.cover_v || 0) + '" alt="" loading="lazy">' : C.cover({ id: b.id, title: b.title }, 'cv')) +
      '<input type="checkbox" data-catsel' + (P.sel.has(b.calibre_id) ? ' checked' : '') + ' aria-label="Choose"></span>' +
      '<span class="calct">' + (b.marked ? IC.pin : '') + esc(b.title) + '</span><span class="calca">' + esc((b.authors || []).join(' & ')) + '</span></div>').join('') + '</div>';
  } else {
    const total = cols.reduce((s, c) => s + widthOf(c), 0) + CK;
    const allOn = r.books.length && r.books.every(b => P.sel.has(b.calibre_id));
    h = '<table class="cattable" style="width:' + total + 'px;min-width:100%"><colgroup><col style="width:' + CK + 'px">' + cols.map(c => '<col style="width:' + widthOf(c) + 'px">').join('') + '</colgroup><thead><tr>' +
      '<th class="catck"><input type="checkbox" data-catall' + (allOn ? ' checked' : '') + ' aria-label="Choose all"></th>' +
      cols.map(c => '<th data-ck="' + esc(c.key) + '" class="' + (NUMERIC.has(c.type) ? 'num ' : '') + (P.sort === c.key ? 'on' : '') + '" aria-sort="' + (P.sort === c.key ? (P.desc ? 'descending' : 'ascending') : 'none') + '">' +
        '<button class="catsort" data-catsort="' + esc(c.key) + '">' + esc(c.label) + (P.sort === c.key ? '<i>' + (P.desc ? '↓' : '↑') + '</i>' : '') + '</button><span class="catrs" data-catrs="' + esc(c.key) + '"></span></th>').join('') +
      '</tr></thead><tbody>';
    h += r.books.map(b => '<tr data-cid="' + esc(b.id) + '" data-cal="' + b.calibre_id + '" class="' + (b.private ? 'priv' : '') + (P.sel.has(b.calibre_id) ? ' sel' : '') + '">' +
      '<td class="catck"><input type="checkbox" data-catsel' + (P.sel.has(b.calibre_id) ? ' checked' : '') + ' aria-label="Choose"></td>' + cols.map(c => '<td class="' + (NUMERIC.has(c.type) ? 'num' : '') + '">' + cellHtml(b, c) + '</td>').join('') + '</tr>').join('');
    h += '</tbody></table>';
  }
  if (r.error) h += '<p class="placeholder catmsg">' + esc(r.error) + '</p>';
  else if (!r.books.length) h += '<p class="mute catmsg">Nothing matches.</p>';
  const top = box.scrollTop, left = box.scrollLeft;
  box.innerHTML = h;
  box.scrollTop = P.scroll || top; box.scrollLeft = left; P.scroll = 0;
  const vb = $('#catviewb span'); if (vb) vb.textContent = P.view || 'Views';
  bulkBar();
}
const CK = 36;
// The toolbar's buttons as the chosen books allow, the status bar, and Book details.
function bulkBar(){
  const n = P.sel.size, all = P.data ? P.data.books.length : 0;
  $$('#caltools [data-cal]').forEach(b => {
    const need = (TOOLS.find(t => t[0] === b.dataset.cal) || [])[3];
    b.disabled = need === 1 ? n !== 1 : need === 2 ? n < 2 : need === 'n' ? !n : false;
  });
  const cn = $('#catn'); if (cn && P.data) cn.textContent = P.data.count === P.data.total ? P.data.total + ' books' : P.data.count + ' of ' + P.data.total + ' books';
  const s = $('#calsel');
  if (s) s.innerHTML = n ? '<b>' + n + ' chosen</b>' + (n < all ? '<button class="linkbtn" data-catb="all">Choose all ' + all + '</button>' : '') + '<button class="linkbtn" data-catb="none">Clear</button>' : '';
  drawDet(); drawQv();
}
// Book details (Calibre's panel on the right): the book last chosen, as its page shows it.
async function drawDet(){
  const box = $('#catdet'); if (!box || !P.det) return;
  const id = P.sel.has(P.anchor) ? P.anchor : P.sel.size === 1 ? [...P.sel][0] : null;
  const b = id != null && P.data ? P.data.books.find(x => x.calibre_id === id) : null;
  if (!b) { box.innerHTML = ''; box.dataset.cal = ''; return; }          // nothing chosen: no panel (on the tablet, no sheet)
  if (box.dataset.cal === String(id) && box.firstChild) return;
  box.dataset.cal = String(id);
  const head = '<button class="btn sm ib catdx" data-catm="detx" aria-label="Close">' + IC.x + '</button>' +
    '<a class="cdcov" href="#book/' + encodeURIComponent(b.id) + '">' + (b.cover ? '<img src="/api/cover/' + encodeURIComponent(b.id) + '?v=' + (b.cover_v || 0) + '" alt="">' : C.cover({ id: b.id, title: b.title }, 'cv lg')) + '</a>' +
    '<h2 class="cdt"><a href="#book/' + encodeURIComponent(b.id) + '">' + esc(b.title) + '</a></h2>' +
    '<div class="cda">' + (b.authors || []).map(a => '<button class="linkbtn" data-catq="' + esc('authors:"=' + a.replace(/"/g, '') + '"') + '">' + esc(a) + '</button>').join(' & ') + '</div>';
  box.innerHTML = head + '<div id="cdmore"></div>';
  let x = P.info.get(b.id);
  if (!x) { try { x = await api('/api/books/' + encodeURIComponent(b.id)); P.info.set(b.id, x); } catch(e){ return; } }
  if (box.dataset.cal !== String(id)) return;
  const more = $('#cdmore', box); if (!more) return;
  more.innerHTML = '<div class="cdacts">' + (x.readable ? '<a class="btn sm primary" href="#ebook/' + encodeURIComponent(b.id) + '">' + (x.daf_position ? 'Continue · ' + Math.round((x.daf_position.fraction || 0) * 100) + '%' : 'Read') + '</a>' : '') +
    '<button class="btn sm" data-cal="edit">Edit metadata</button></div>' +
    (x.progress > 0 ? '<div class="cdprog">' + C.bar(x.progress) + '<span class="tiny mute">' + Math.round(x.progress) + '%</span></div>' : '') +
    (C.bookDetails ? C.bookDetails(x.details) : '');
}
function toggleDet(on, quiet){
  P.det = on == null ? !P.det : on; if (!narrow()) store.set('calDet', P.det);
  const pg = $('#catpage'); if (pg) pg.classList.toggle('det', P.det);
  const b = $('[data-act="cat:det"]'); if (b) b.setAttribute('aria-pressed', P.det);
  if (P.det && !quiet) { const box = $('#catdet'); if (box) box.dataset.cal = ''; drawDet(); }
}
function choose(id, on){
  if (on) P.sel.add(id); else P.sel.delete(id);
  const tr = $('#catscroll [data-cal="' + id + '"]');
  if (tr) { tr.classList.toggle('sel', on); const ck = $('[data-catsel]', tr); if (ck) ck.checked = on; }
}
function chosenSync(){
  const all = $('[data-catall]'); if (all && P.data) all.checked = P.data.books.length > 0 && P.data.books.every(b => P.sel.has(b.calibre_id));
  bulkBar();
}

/* ---------- the search ---------- */
let typing = null;
document.addEventListener('input', e => {
  if (e.target.id === 'catq') { clearTimeout(typing); typing = setTimeout(() => { P.q = e.target.value; P.view = dirtyView(); keep(); load(); if (P.side) drawSide(); }, 250); }
  else if (e.target.id === 'catfq') { P.fq = e.target.value; drawSide(true); }
});
document.addEventListener('keydown', e => {
  if (e.target.id === 'catq' && e.key === 'Enter') { clearTimeout(typing); P.q = e.target.value; P.view = dirtyView(); keep(); load(); if (P.side) drawSide(); }
  if (e.target.id === 'catq' && e.key === 'Escape' && e.target.value) { e.preventDefault(); e.target.value = ''; setQ(''); }
});
function setQ(q){
  P.q = q.replace(/\s+/g, ' ').trim(); P.view = dirtyView(); keep();
  const box = $('#catq'); if (box) box.value = P.q;
  load(); if (P.side) drawSide(true);
}
// A view stays chosen while its search, order and columns are the ones on the page.
function dirtyView(){
  const v = (P.data && P.data.views || []).find(x => x.name === P.view);
  if (!v) return null;
  return v.q === P.q && v.sort === P.sort && !!v.desc === !!P.desc && JSON.stringify(v.cols) === JSON.stringify(P.cols || []) ? v.name : null;
}

/* ---------- the Filter panel: Calibre's Tag browser ---------- */
const term = (key, val) => key === 'rating' ? 'rating:' + val : key + ':"=' + String(val).replace(/"/g, '') + '"';
const ADDED = [['added:thisweek', 'This week'], ['added:thismonth', 'This month'], ['added:>=30daysago', 'Last 30 days'], ['added:thisyear', 'This year'], ['added:lastyear', 'Last year']];
const MISSING = [['formats:false', 'No file'], ['cover:false', 'No cover'], ['tags:false', 'No tags'], ['rating:false', 'No rating'], ['series:false', 'No series']];
const TIDY = [['duplicate:true', 'Possible duplicates'], ['title:~[âÃ�]', 'Odd characters'], ['authors:"~^[^&]+, "', 'Last name first']];
const esc_re = s => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
const has = (t, neg) => new RegExp('(^|[\\s(])' + (neg ? 'not ' : '') + esc_re(t) + '(?=$|[\\s)])', 'i').test(P.q);
const stateOf = t => has(t, true) ? 'out' : has(t) ? 'in' : '';
function cycle(t){
  let q = P.q;
  if (has(t, true)) q = q.replace(new RegExp('(^|[\\s(])not ' + esc_re(t) + '(?=$|[\\s)])', 'i'), '$1');
  else if (has(t)) q = q.replace(new RegExp('(^|[\\s(])' + esc_re(t) + '(?=$|[\\s)])', 'i'), '$1not ' + t);
  else q = (q ? q + ' ' : '') + t;
  setQ(q);
}
function drawSide(keepFocus){
  const side = $('#catside'); if (!side) return;
  const fq = P.fq.trim().toLowerCase();
  const val = (t, label, n, k, name) => { const st = stateOf(t);
    return '<button class="catv ' + st + '" data-catt="' + esc(t) + '"' + (k && manageable(k) ? ' data-catk="' + esc(k) + '" data-catn="' + esc(name) + '"' : '') + ' aria-pressed="' + (st === 'in') + '"><i>' + (st === 'in' ? '✓' : st === 'out' ? '−' : '') + '</i><span>' + label + '</span>' + (n != null ? '<b>' + n + '</b>' : '') + '</button>'; };
  const group = (key, label, items, icon, row) => {
    if (fq) items = items.filter(x => x[1].toLowerCase().includes(fq) || label.toLowerCase().includes(fq));
    if (!items.length) return '';
    const open = fq || P.open.has(key), many = !fq && !P.all.has(key) && items.length > 30;
    return '<section class="catg"><button class="catgh" data-catg="' + esc(key) + '">' + IC.chev(open) + svg(GI[icon || key] || GI.custom) + '<span>' + esc(label) + '</span><b>' + items.length + '</b></button>' +
      (open ? '<div class="catvs">' + (many ? items.slice(0, 30) : items).map(row || (x => val(x[0], x[1], x[2], x[3], x[4]))).join('') +
        (many ? '<button class="linkbtn tiny catall" data-catall="' + esc(key) + '">Show all ' + items.length + '</button>' : '') + '</div>' : '') + '</section>';
  };
  let h = '<div class="catsh"><input class="field sm" id="catfq" type="search" placeholder="Find" autocomplete="off" value="' + esc(P.fq) + '" aria-label="Find in the Tag browser">' +
    (P.q ? '<button class="btn sm" data-catm="clear">Clear</button>' : '') + '<button class="btn sm catdone" data-catm="side">Done</button></div>';
  const fs = (P.facets || []).slice().sort((a, b) => { const i = k => { const n = ORDER.indexOf(k); return n < 0 ? 50 + (a.key.startsWith('#') ? 0 : 1) : n; }; return i(a.key) - i(b.key); });
  const calibre = fs.filter(f => ORDER.includes(f.key) || f.key.startsWith('#')), daf = fs.filter(f => !calibre.includes(f));
  const facet = f => group(f.key, f.label, f.values.map(([v, n]) => [term(f.key, v), f.key === 'rating' ? stars(v) : esc(v), n, f.key, v]), f.key.startsWith('#') ? 'custom' : f.key);
  h += calibre.map(facet).join('');
  const vs = (P.data && P.data.views) || [];
  h += group('views', 'Saved searches', vs.map(v => [v.name, esc(v.name)]), 'views',
    x => '<button class="catv' + (x[0] === P.view ? ' in' : '') + '" data-catview="' + esc(x[0]) + '"><i>' + (x[0] === P.view ? '✓' : '') + '</i><span>' + x[1] + '</span></button>');
  h += daf.map(facet).join('');
  h += group('added', 'Added', ADDED.map(([t, l]) => [t, esc(l)]));
  h += group('missing', 'Missing', MISSING.map(([t, l]) => [t, esc(l)]));
  h += group('tidy', 'Tidy', TIDY.map(([t, l]) => [t, esc(l)]));
  side.innerHTML = h;
  if (keepFocus) { const i = $('#catfq'); if (i && document.activeElement !== i && P.fq) { i.focus(); i.setSelectionRange(i.value.length, i.value.length); } }
}
function toggleSide(on){
  P.side = on == null ? !P.side : on; if (!narrow()) store.set('calSide', P.side);
  if (P.side && narrow() && P.det) toggleDet(false, true);           // one sheet at a time
  if (P.side && narrow() && P.qv) toggleQv(false);
  const pg = $('#catpage'); if (pg) pg.classList.toggle('filt', P.side);
  const b = $('[data-act="cat:side"]'); if (b) b.setAttribute('aria-pressed', P.side);
  if (P.side) { if (P.facets) drawSide(); else load(true).then(drawSide); }
}

/* ---------- menus: Columns, Views, More ---------- */
function openPop(anchor, html, cls){
  const p = $('#pop'); p.onclick = p.oninput = p.onkeydown = null;
  p.innerHTML = '<div class="menu catmenu ' + (cls || '') + '">' + html + '</div>'; p.hidden = false;
  if (matchMedia('(max-width:700px)').matches) { p.style.left = ''; p.style.top = ''; return; }       // a sheet (style.css)
  const r = anchor.getBoundingClientRect();
  p.style.left = Math.max(8, Math.min(innerWidth - p.offsetWidth - 8, r.right - p.offsetWidth)) + 'px';
  p.style.top = Math.min(r.bottom + 6, innerHeight - p.offsetHeight - 8) + 'px';
}
function colsMenu(anchor){
  const all = P.data.columns, on = colsNow().map(c => c.key);
  const row = (c, i) => '<div class="catcol' + (i >= 0 ? ' on' : '') + '" data-colkey="' + esc(c.key) + '">' +
    '<label><input type="checkbox" data-catcol="' + esc(c.key) + '"' + (i >= 0 ? ' checked' : '') + (c.key === 'title' ? ' disabled' : '') + '><span>' + esc(c.label) + '</span></label>' +
    (i >= 0 ? '<span class="catgrip" data-catgrip="' + esc(c.key) + '" aria-label="Move">' + IC.grip + '</span>' : '') + '</div>';
  const shown = on.map(k => all.find(c => c.key === k)), rest = all.filter(c => !on.includes(c.key));
  openPop(anchor, '<div class="catcols" id="catcols">' + shown.map((c, i) => row(c, i)).join('') + '</div><hr>' +
    '<div class="catcols rest">' + rest.map(c => row(c, -1)).join('') + '</div><hr><button data-catm="colsreset"><i></i>Default columns</button>', 'wide');
}
function viewsMenu(anchor){
  const vs = P.data.views || [];
  openPop(anchor, (vs.length ? vs.map(v => '<div class="catvrow"><button data-catview="' + esc(v.name) + '"' + (v.name === P.view ? ' class="on"' : '') + '><i>' + (v.name === P.view ? '✓' : '') + '</i>' + esc(v.name) + '</button>' +
      '<button class="catvdel" data-catvdel="' + esc(v.name) + '" aria-label="Delete ' + esc(v.name) + '">' + IC.x + '</button></div>').join('') + '<hr>' : '') +
    (!P.view && P.lastView && vs.some(v => v.name === P.lastView) ? '<button data-catm="update"><i></i>Save into “' + esc(P.lastView) + '”</button>' : '') +
    '<button data-catm="save"><i></i>Save as a view…</button><button data-catm="reset"><i></i>All books, newest first</button>');
}
// Calibre's Open With: one of the book's files handed to another app (the Android app's dafShell.openWith).
const canOpenWith = () => !!(window.dafShell && window.dafShell.can && window.dafShell.can('openWith'));
const MIME = { EPUB: 'application/epub+zip', PDF: 'application/pdf', MOBI: 'application/x-mobipocket-ebook', AZW3: 'application/vnd.amazon.ebook', KEPUB: 'application/epub+zip',
  CBZ: 'application/vnd.comicbook+zip', CBR: 'application/vnd.comicbook-rar', TXT: 'text/plain', DOCX: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', RTF: 'application/rtf', FB2: 'application/x-fictionbook+xml' };
function openWithMenu(anchor, b){
  const fs = b.formats || [];
  if (!fs.length) { toast('No file'); return; }
  openPop(anchor, fs.map(f => '<button data-catopen="' + esc(f) + '" data-cal-id="' + b.calibre_id + '"><i></i>' + esc(f) + '</button>').join(''));
}
document.addEventListener('click', e => {
  const o = e.target.closest && e.target.closest('[data-catopen]'); if (!o) return;
  $('#pop').hidden = true;
  const fmt = o.dataset.catopen, cid = o.dataset.calId, b = P.data && P.data.books.find(x => String(x.calibre_id) === cid);
  const name = ((b && b.title) || 'book').replace(/[\\/:*?"<>|]+/g, ' ').trim().slice(0, 80) + '.' + (fmt === 'KEPUB' ? 'kepub.epub' : fmt.toLowerCase());
  window.dafShell.openWith({ url: '/api/catalog/book/' + cid + '/files/' + encodeURIComponent(fmt), name, mime: MIME[fmt] || 'application/octet-stream' }).catch(err => toast(err.message));
});
function sortMenu(anchor){
  const cs = P.data.columns.filter(c => c.key !== 'cover');
  openPop(anchor, cs.map(c => '<button data-catsortm="' + esc(c.key) + '"' + (P.sort === c.key ? ' class="on"' : '') + '><i>' + (P.sort === c.key ? (P.desc ? '↓' : '↑') : '') + '</i>' + esc(c.label) + '</button>').join(''), 'wide');
}
async function moreMenu(anchor){
  const qs = new URLSearchParams({ q: P.q, sort: P.sort, desc: P.desc ? '1' : '0', cols: colsNow().map(c => c.key).join(',') });
  if (P.priv) qs.set('private', '1');
  let emb = { pending: 0 };
  try { emb = await api('/api/catalog/embed'); } catch(e){}
  openPop(anchor, (P.sel.size ? '<button data-catm="pages"><i></i>Count pages</button><hr>' : '') + '<button data-catm="items"><i></i>Tags, authors and series</button>' +
    (emb.pending ? '<button disabled><i></i>Writing details into files · ' + emb.pending + ' left</button>' : '<button data-catm="embedall"><i></i>Write details into every file</button>') + '<hr>' +
    '<a href="/api/catalog/export?' + qs.toString() + '" download><i></i>Export as CSV</a>' +
    '<button data-catm="priv"' + (P.priv ? ' class="on"' : '') + '><i>' + (P.priv ? '✓' : '') + '</i>Show private books</button>' +
    (P.sel.size ? '<hr><button data-catm="mark"><i></i>' + (chosenBooks().every(b => b.marked) ? 'Unmark' : 'Mark') + '</button>' : '') +
    ((P.data && P.data.marks) ? (P.sel.size ? '' : '<hr>') + '<button data-catm="marked"><i></i>Marked books · ' + P.data.marks + '</button><button data-catm="unmarkall"><i></i>Clear marks</button>' : '') +
    '<hr><button data-catm="import"><i></i>Import list</button><button data-catm="check"><i></i>Check library</button><button data-catm="trash"><i></i>Calibre’s trash</button>');
}
// Many books into one format: one job on the server, a book at a time; the toast says when it's done.
async function convertMany(ids, to){
  let r;
  try { r = await api('/api/catalog/convert-many', { method: 'POST', body: JSON.stringify({ ids, to }) }); } catch(e){ toast(e.message); return; }
  if (!r.job) { toast(r.have ? 'All ' + r.have + ' have ' + to : 'No file to convert'); return; }
  toast('Converting ' + r.total + ' to ' + to);
  const poll = async () => {
    let j; try { j = await api('/api/catalog/convert-many/' + r.job); } catch(e){ return; }
    if (j.running) { setTimeout(poll, 4000); return; }
    const ok = j.total - j.failed.length;
    toast(ok + ' converted to ' + to + (j.failed.length ? ' · ' + j.failed.length + ' didn’t' : ''));
    if (C.S.route[0] === 'catalog') load(true);
  };
  setTimeout(poll, 4000);
}
// Count pages for the chosen books (calibrekeep.py), the way Calibre's Count Pages does.
async function countPages(ids){
  let r;
  try { r = await api('/api/catalog/count-pages', { method: 'POST', body: JSON.stringify({ ids }) }); } catch(e){ toast(e.message); return; }
  toast('Counting ' + r.total);
  const poll = async () => {
    let j; try { j = await api('/api/catalog/job/' + r.job); } catch(e){ return; }
    if (j.running) { setTimeout(poll, 3000); return; }
    toast(j.error ? j.error : (j.done || 0) + ' counted');
    if (C.S.route[0] === 'catalog') load(true);
  };
  setTimeout(poll, 3000);
}
// Check library (catalog.check_library): what doesn't match between Calibre's records and its folders.
const CHECKS = [['missing_files', 'Files missing'], ['no_files', 'Books without a file'], ['missing_cover', 'Covers missing'], ['missing_folder', 'Folders missing'],
  ['extra_files', 'Files Calibre doesn’t list'], ['unknown_folders', 'Folders Calibre doesn’t know'],
  ['read_differs', 'Read column differs from Daf'], ['no_description', 'No description'], ['no_isbn', 'No ISBN'], ['no_pages', 'No page count'],
  ['no_language', 'No language'], ['caps_title', 'Title in capitals'], ['unknown_author', 'Unknown author']];
const DAFST = { 'to-read': 'To read', reading: 'Reading', read: 'Read', paused: 'Paused', dropped: 'Dropped' };
async function checkLibrary(){
  $('#scrim').hidden = false; const m = $('#modal'); m.hidden = false; m.classList.add('wide');
  m.innerHTML = '<h2>Check library</h2><p class="mute">Checking…</p>';
  let r;
  try { r = await api('/api/catalog/check'); } catch(e){ m.innerHTML = '<h2>Check library</h2><p class="mute">' + esc(e.message) + '</p><div class="catchkbtns"><button class="btn" data-ckclose>Close</button></div>'; return; }
  const groups = CHECKS.filter(([k]) => (r[k] || []).length);
  const item = x => x.id ? '<a class="catchkrow" href="#book/cal:' + x.id + '" data-ckclose><span>' + esc(x.title) + '</span><span class="mute tiny">' + esc(x.format || x.file || (x.calibre ? 'Calibre ' + x.calibre + ' · Daf ' + (DAFST[x.daf] || x.daf) : '')) + '</span></a>'
    : '<div class="catchkrow"><span class="mono">' + esc(x.path) + '</span></div>';
  m.innerHTML = '<h2>Check library</h2><span class="mute tiny">' + r.books + ' books</span>' +
    (groups.length ? '<div class="catchk">' + groups.map(([k, l]) => '<h3>' + l + ' <span class="mute tiny">' + r[k].length + '</span></h3>' + r[k].slice(0, 200).map(item).join('')).join('') + '</div>'
      : '<p>Nothing wrong</p>') +
    '<div class="catchkbtns"><button class="btn" data-ckclose>Close</button></div>';
}
document.addEventListener('click', e => { if (e.target.closest && e.target.closest('[data-ckclose]')) C.closeModal ? C.closeModal() : ($('#modal').hidden = $('#scrim').hidden = true); });

async function saveViews(views){
  const r = await api('/api/catalog/views', { method: 'PUT', body: JSON.stringify({ views }) });
  P.data.views = r.views;
}
const thisView = name => ({ name, q: P.q, sort: P.sort, desc: P.desc, cols: P.cols || [], widths: P.widths });
function applyView(v){
  Object.assign(P, { q: v.q || '', sort: v.sort || 'added', desc: !!v.desc, cols: v.cols && v.cols.length ? v.cols : null, widths: v.widths || {}, view: v.name, lastView: v.name });
  keep(); const box = $('#catq'); if (box) box.value = P.q; load(); if (P.side) drawSide();
}

/* ---------- clicks ---------- */
document.addEventListener('click', async e => {
  const t = e.target; if (!t.closest) return;
  const a = t.closest('[data-act^="cat:"]');
  if (a) {
    const k = a.dataset.act.slice(4);
    if (k === 'side') toggleSide();
    else if (k === 'det') { if (narrow() && !P.det) { if (P.side) toggleSide(false); if (P.qv) toggleQv(false); } toggleDet(); }
    else if (k === 'grid') { P.grid = !P.grid; store.set('calGrid', P.grid); a.setAttribute('aria-pressed', P.grid); draw(); }
    else if (k === 'qv') toggleQv();
    else if (!P.data) return;
    else if (k === 'sort') sortMenu(a);
    else if (k === 'cols') colsMenu(a);
    else if (k === 'views') viewsMenu(a);
    else if (k === 'more') moreMenu(a);
    return;
  }
  const s = t.closest('[data-catsort]');
  if (s) { if (Date.now() - drag.ended < 300) return;
    const k = s.dataset.catsort, c = P.data.columns.find(x => x.key === k);
    if (P.sort === k) P.desc = !P.desc; else { P.sort = k; P.desc = !!c && (NUMERIC.has(c.type) || c.type === 'date' || c.type === 'bool'); }
    P.view = dirtyView(); keep(); load(); return; }
  const tt = t.closest('[data-catt]'); if (tt) { cycle(tt.dataset.catt); return; }
  const sm = t.closest('[data-catsortm]');
  if (sm) { const k = sm.dataset.catsortm, c = P.data.columns.find(x => x.key === k);
    if (P.sort === k) P.desc = !P.desc; else { P.sort = k; P.desc = !!c && (NUMERIC.has(c.type) || c.type === 'date' || c.type === 'bool'); }
    P.view = dirtyView(); keep(); load(); sortMenu(sm.closest('#pop') ? $('[data-act="cat:sort"]') : sm); return; }
  const dq = t.closest('#catdet [data-catq]'); if (dq) { setQ(dq.dataset.catq); return; }
  const g = t.closest('[data-catg]'); if (g) { const k = g.dataset.catg; P.open.has(k) ? P.open.delete(k) : P.open.add(k); store.set('catalogOpen', [...P.open]); drawSide(); return; }
  const all = t.closest('[data-catall]'); if (all) { P.all.add(all.dataset.catall); drawSide(); return; }
  const cv = t.closest('[data-catview]'); if (cv) { $('#pop').hidden = true; const v = P.data.views.find(x => x.name === cv.dataset.catview); if (v) applyView(v); return; }
  const vd = t.closest('[data-catvdel]');
  if (vd) { e.stopPropagation(); const name = vd.dataset.catvdel;
    if (!confirm('Delete the view “' + name + '”?')) return;
    try { await saveViews(P.data.views.filter(v => v.name !== name)); if (P.view === name) { P.view = null; keep(); draw(); } viewsMenu($('#catviewb')); } catch(err){ toast(err.message); }
    return; }
  const m = t.closest('[data-catm]');
  if (m) {
    const k = m.dataset.catm;
    if (k === 'side') toggleSide(false);
    else if (k === 'shade') { if (P.side) toggleSide(false); if (P.det && narrow()) toggleDet(false); if (P.qv && narrow()) toggleQv(false); }
    else if (k === 'detx') toggleDet(false);
    else if (k === 'clear') setQ('');
    else if (k === 'colsreset') { P.cols = null; P.widths = {}; P.view = dirtyView(); keep(); draw(); $('#pop').hidden = true; }
    else if (k === 'trash') { $('#pop').hidden = true; if (C.BookEdit) C.BookEdit.trash(P.priv); }
    else if (k === 'items') { $('#pop').hidden = true; if (C.BookEdit) C.BookEdit.items('tags'); }
    else if (k === 'conv') { $('#pop').hidden = true; convertMany([...P.sel], m.dataset.to); }
    else if (k === 'dl') { $('#pop').hidden = true; const a = document.createElement('a'); a.href = '/api/catalog/download?ids=' + [...P.sel].join(','); a.download = ''; document.body.appendChild(a); a.click(); a.remove(); }
    else if (k === 'check') { $('#pop').hidden = true; checkLibrary(); }
    else if (k === 'import') { $('#pop').hidden = true; if (C.ImportList) C.ImportList.open(); }
    else if (k === 'pages') { $('#pop').hidden = true; countPages([...P.sel]); }
    else if (k === 'mark') { $('#pop').hidden = true; toggleMarks(); }
    else if (k === 'marked') { $('#pop').hidden = true; setQ('marked:true'); }
    else if (k === 'unmarkall') { $('#pop').hidden = true; setMarks(null, false); }
    else if (k === 'embedall') { $('#pop').hidden = true;
      if (confirm('Write the details into the files of all ' + (P.data ? P.data.total : '') + ' books?'))
        api('/api/catalog/embed', { method: 'POST', body: JSON.stringify({ all: true }) }).then(r => toast('Writing details into ' + r.pending + ' books’ files')).catch(err => toast(err.message)); }
    else if (k === 'priv') { P.priv = !P.priv; keep(); $('#pop').hidden = true; P.facets = null; load(true).then(() => { if (P.side) drawSide(); }); }
    else if (k === 'reset') { $('#pop').hidden = true; Object.assign(P, { q: '', sort: 'added', desc: true, cols: null, widths: {}, view: null }); keep(); const box = $('#catq'); if (box) box.value = ''; load(); if (P.side) drawSide(); }
    else if (k === 'save' || k === 'update') {
      $('#pop').hidden = true;
      const name = k === 'update' ? P.lastView : (prompt('Name of the view', P.view || '') || '').trim();
      if (!name) return;
      const vs = (P.data.views || []).filter(v => v.name.toLowerCase() !== name.toLowerCase());
      if (k === 'save' && vs.length !== (P.data.views || []).length && !confirm('Replace the view “' + name + '”?')) return;
      try { await saveViews([...vs, thisView(name)]); P.view = name; P.lastView = name; keep(); draw(); toast('Saved'); } catch(err){ toast(err.message); }
    }
    return;
  }
});          // not on the way down: a second click on the button that opened a menu closes it (app.js)
document.addEventListener('change', e => {
  const c = e.target.closest && e.target.closest('[data-catcol]'); if (!c) return;
  const on = colsNow().map(x => x.key), k = c.dataset.catcol;
  P.cols = c.checked ? [...on.filter(x => x !== k), k] : on.filter(x => x !== k);
  P.view = dirtyView(); keep(); draw(); colsMenu($('[data-act="cat:cols"]'));
});
// A row's double-click opens the book's page. A click chooses the row, as in a spreadsheet: alone,
// with Cmd or Ctrl one more, with Shift everything from the last one. Its box, or a tap, adds or takes it out.
document.addEventListener('dblclick', e => { const tr = e.target.closest && e.target.closest('#catscroll tbody tr, #catscroll .calcell'); if (tr && !e.target.closest('a,input')) location.hash = 'book/' + encodeURIComponent(tr.dataset.cid); });
document.addEventListener('click', e => {
  const t = e.target; if (!t.closest) return;
  const tool = t.closest('[data-cal]:is(.caltool, #catdet [data-cal])');
  if (tool && !tool.disabled && P.data) {
    const k = tool.dataset.cal, chosen = P.data.books.filter(x => P.sel.has(x.calibre_id)), ids = chosen.map(x => x.calibre_id);
    const one = P.sel.has(P.anchor) ? P.data.books.find(x => x.calibre_id === P.anchor) : chosen[0];
    if (k === 'add') { if (C.AddBook) C.AddBook.open(); }
    else if (k === 'edit' && C.BookEdit) { if (ids.length === 1 || t.closest('#catdet')) C.BookEdit.open(one.calibre_id); else C.BookEdit.bulk(ids); }
    else if (k === 'conv') openPop(tool, ['EPUB', 'AZW3', 'KEPUB', 'MOBI', 'PDF'].map(f => '<button data-catm="conv" data-to="' + f + '"><i></i>' + f + '</button>').join(''));
    else if (k === 'read' && one) location.hash = 'ebook/' + encodeURIComponent(one.id);
    else if (k === 'ebook' && one && C.EbookEdit) C.EbookEdit.open(one.calibre_id);
    else if (k === 'find' && C.BookEdit) {
      if (chosen.length === 1) Promise.resolve(C.BookEdit.open(one.calibre_id)).then(() => { const f = $('#bedit [data-be="find"]'); if (f) f.click(); });
      else C.BookEdit.fill(chosen); }
    else if (k === 'shelves' && C.DragBooks) C.DragBooks.sheet(chosen, tool);
    else if (k === 'merge' && C.BookEdit) C.BookEdit.merge(chosen);
    else if (k === 'epubmerge' && C.EpubMerge) C.EpubMerge.open(chosen);
    else if (k === 'dl') { const a = document.createElement('a'); a.href = '/api/catalog/download?ids=' + ids.join(','); a.download = ''; document.body.appendChild(a); a.click(); a.remove(); }
    else if (k === 'remove' && C.BookEdit) C.BookEdit.remove(chosen).then(done => { if (done) { P.sel.clear(); bulkBar(); } });
    else if (k === 'library') moreMenu(tool);
    else if (k === 'openwith' && one) openWithMenu(tool, one);
    return; }
  const b = t.closest('[data-catb]');
  if (b) { const k = b.dataset.catb;
    if (k === 'edit' && C.BookEdit) C.BookEdit.bulk([...P.sel]);
    else if (k === 'merge' && C.BookEdit) C.BookEdit.merge(P.data.books.filter(x => P.sel.has(x.calibre_id)));
    else if (k === 'fill' && C.BookEdit) C.BookEdit.fill(P.data.books.filter(x => P.sel.has(x.calibre_id)));
    else if (k === 'shelves' && C.DragBooks) C.DragBooks.sheet(P.data.books.filter(x => P.sel.has(x.calibre_id)), b);
    else if (k === 'remove' && C.BookEdit) C.BookEdit.remove(P.data.books.filter(x => P.sel.has(x.calibre_id))).then(done => { if (done) P.sel.clear(); });
    else if (k === 'more') openPop(b, ['EPUB', 'AZW3', 'KEPUB', 'MOBI', 'PDF'].map(f => '<button data-catm="conv" data-to="' + f + '"><i></i>Convert to ' + f + '</button>').join('') +
      '<hr><button data-catm="pages"><i></i>Count pages</button><button data-catm="dl"><i></i>Download</button>');
    else if (k === 'none') { P.sel.clear(); draw(); }
    else if (k === 'all') { P.data.books.forEach(x => P.sel.add(x.calibre_id)); draw(); }
    return; }
  if (t.closest('[data-catall]')) { const on = t.checked; P.data.books.forEach(x => choose(x.calibre_id, on)); chosenSync(); return; }
  const tr = t.closest('#catscroll tbody tr, #catscroll .calcell'); if (!tr) return;
  if (t.closest('a.catt')) { P.scroll = ($('#catscroll') || {}).scrollTop || 0; return; }
  if (Date.now() - held < 600) return;
  if (t.closest('.catediting')) return;
  const td = t.closest('td'); if (td && td.cellIndex > 0) P.cell = (colsNow()[td.cellIndex - 1] || {}).key || 'title';
  const id = +tr.dataset.cal, ids = P.data.books.map(x => x.calibre_id);
  if (t.closest('[data-catsel]') || e.metaKey || e.ctrlKey) choose(id, !P.sel.has(id));
  else if (e.shiftKey && P.anchor != null && ids.includes(P.anchor)) {
    const [a, z] = [ids.indexOf(P.anchor), ids.indexOf(id)].sort((x, y) => x - y);
    ids.slice(a, z + 1).forEach(x => choose(x, true));
  } else { [...P.sel].forEach(x => { if (x !== id) choose(x, false); }); choose(id, true); }
  if (!e.shiftKey) P.anchor = id;
  chosenSync();
});
// Right-click a row, or hold it and let go (dragbooks.js): Edit details, shelves, the book's page.
let held = 0;
function rowMenu(tr, x, y, td){
  const p = $('#pop'), id = tr.dataset.cid, cal = +tr.dataset.cal, b = P.data && P.data.books.find(z => z.calibre_id === cal);
  const col = td && td.cellIndex > 0 && !P.grid ? colsNow()[td.cellIndex - 1] : null;
  const many = P.sel.size > 1 && P.sel.has(cal), marks = many ? chosenBooks() : [b].filter(Boolean);
  p.onclick = p.oninput = p.onkeydown = null;
  p.innerHTML = '<div class="menu catmenu"><button data-catrow="edit" data-cal="' + cal + '"><i></i>Edit details</button>' +
    (editable(col) ? '<button data-catrow="cell" data-cal="' + cal + '" data-col="' + esc(col.key) + '"><i></i>Edit ' + esc(col.label) + '</button>' : '') +
    '<button data-catrow="shelves" data-cal="' + cal + '"><i></i>Shelves and collection</button><a href="#book/' + encodeURIComponent(id) + '"><i></i>Open the book’s page</a>' +
    (many ? '<hr><button data-catrow="bulk"><i></i>Edit the ' + P.sel.size + ' chosen</button>' : '') +
    '<button data-catrow="mark" data-cal="' + cal + '"><i></i>' + (marks.length && marks.every(z => z.marked) ? 'Unmark' : 'Mark') + (many ? ' the ' + P.sel.size + ' chosen' : '') + '</button>' +
    (b ? '<hr>' + SIM.filter(([f]) => valsOf(b, f).length).map(([f, l]) => '<button data-catrow="sim" data-cal="' + cal + '" data-f="' + f + '"><i></i>' + l + '</button>').join('') : '') + '</div>';
  p.hidden = false;
  if (matchMedia('(max-width:700px)').matches) { p.style.left = ''; p.style.top = ''; return; }
  p.style.left = Math.max(8, Math.min(innerWidth - p.offsetWidth - 8, x)) + 'px';
  p.style.top = Math.max(8, Math.min(innerHeight - p.offsetHeight - 8, y)) + 'px';
}
document.addEventListener('contextmenu', e => {
  const tr = e.target.closest && e.target.closest('#catscroll tbody tr, #catscroll .calcell'); if (!tr) return;
  e.preventDefault(); rowMenu(tr, e.clientX, e.clientY, e.target.closest('td'));
});
document.addEventListener('click', e => {
  const m = e.target.closest && e.target.closest('[data-catrow]'); if (!m) return;
  $('#pop').hidden = true;
  if (m.dataset.catrow === 'edit' && C.BookEdit) C.BookEdit.open(m.dataset.cal);
  else if (m.dataset.catrow === 'shelves' && C.DragBooks) C.DragBooks.sheet(P.data.books.filter(b => b.calibre_id === +m.dataset.cal));
  else if (m.dataset.catrow === 'bulk' && C.BookEdit) C.BookEdit.bulk([...P.sel]);
  else if (m.dataset.catrow === 'cell') editCell(+m.dataset.cal, m.dataset.col);
  else if (m.dataset.catrow === 'mark') { const cal = +m.dataset.cal; toggleMarks(P.sel.size > 1 && P.sel.has(cal) ? null : [cal]); }
  else if (m.dataset.catrow === 'sim') { const b = P.data.books.find(z => z.calibre_id === +m.dataset.cal); if (b) similar(b, m.dataset.f); }
});

/* ---------- dragging: a column's edge (its width), its header (its place), a row in Columns ---------- */
const drag = { ended: 0 };
document.addEventListener('pointerdown', e => {
  const t = e.target; if (!t.closest || e.button > 0) return;
  const rs = t.closest('[data-catrs]'), th = !rs && e.pointerType === 'mouse' && t.closest('#catscroll th[data-ck]'), grip = t.closest('[data-catgrip]');
  if (!rs && !th && !grip) return;
  Object.assign(drag, { kind: rs ? 'width' : th ? 'move' : 'menu', key: (rs || th || grip).dataset[rs ? 'catrs' : th ? 'ck' : 'catgrip'], x: e.clientX, y: e.clientY, moved: false, id: e.pointerId });
  if (rs) { const c = P.data.columns.find(x => x.key === drag.key); drag.w = widthOf(c); e.preventDefault(); }
  if (grip) { drag.row = grip.closest('.catcol'); drag.list = $('#catcols'); e.preventDefault(); }
}, true);
document.addEventListener('pointermove', e => {
  if (!drag.kind || e.pointerId !== drag.id) return;
  const dx = e.clientX - drag.x, dy = e.clientY - drag.y;
  if (!drag.moved && Math.hypot(dx, dy) < 5) return;
  drag.moved = true;
  if (drag.kind === 'width') {
    const w = Math.max(48, Math.min(900, Math.round(drag.w + dx)));
    P.widths[drag.key] = w;
    const i = colsNow().findIndex(c => c.key === drag.key), col = $$('#catscroll col')[i + 1], tb = $('#catscroll table');
    if (col) col.style.width = w + 'px';
    if (tb) tb.style.width = colsNow().reduce((s, c) => s + widthOf(c), 0) + CK + 'px';
  } else if (drag.kind === 'move') {
    $$('#catscroll th').forEach(h => h.classList.remove('dropl', 'dropr'));
    const over = document.elementFromPoint(e.clientX, e.clientY), th = over && over.closest && over.closest('#catscroll th[data-ck]');
    if (th && th.dataset.ck !== drag.key) { const r = th.getBoundingClientRect(); th.classList.add(e.clientX < r.left + r.width / 2 ? 'dropl' : 'dropr'); }
    const me = $('#catscroll th[data-ck="' + CSS.escape(drag.key) + '"]'); if (me) me.classList.add('dragging');
  } else if (drag.kind === 'menu') {
    const rows = $$('#catcols .catcol').filter(r => r !== drag.row);
    drag.row.classList.add('dragging');
    const after = rows.find(r => { const b = r.getBoundingClientRect(); return e.clientY < b.top + b.height / 2; });
    drag.list.insertBefore(drag.row, after || null);
  }
}, true);
const endDrag = e => {
  if (!drag.kind || (e && e.pointerId !== drag.id)) return;
  const kind = drag.kind, moved = drag.moved; drag.kind = null;
  if (!moved) return;
  drag.ended = Date.now();
  if (kind === 'width') { P.view = dirtyView(); keep(); }
  else if (kind === 'move') {
    const th = $('#catscroll th.dropl, #catscroll th.dropr');
    $$('#catscroll th').forEach(h => h.classList.remove('dropl', 'dropr', 'dragging'));
    if (!th) return;
    const on = colsNow().map(c => c.key).filter(k => k !== drag.key);
    let i = on.indexOf(th.dataset.ck); if (th.classList.contains('dropr')) i++;
    on.splice(i, 0, drag.key); P.cols = on; P.view = dirtyView(); keep(); draw();
  } else if (kind === 'menu') {
    drag.row.classList.remove('dragging');
    P.cols = $$('#catcols .catcol').map(r => r.dataset.colkey); P.view = dirtyView(); keep(); draw();
  }
};
document.addEventListener('pointerup', endDrag, true);
document.addEventListener('pointercancel', endDrag, true);

/* ---------- more of Calibre's main window ---------- */
const chosenBooks = () => P.data ? P.data.books.filter(b => P.sel.has(b.calibre_id)) : [];
const anchorBook = () => { const id = P.sel.has(P.anchor) ? P.anchor : P.sel.size === 1 ? [...P.sel][0] : null; return id != null && P.data ? P.data.books.find(x => x.calibre_id === id) : null; };
const valsOf = (b, f) => { const v = b && b[f]; return v == null || v === '' ? [] : Array.isArray(v) ? v : [v]; };

// Similar books (Calibre's Alt+A, Alt+S, Alt+T, Alt+P): any of the authors, the series, every tag, the publisher.
const SIM = [['authors', 'Books by the same author', 'KeyA'], ['series', 'Books in this series', 'KeyS'], ['tags', 'Books with the same tags', 'KeyT'], ['publisher', 'Books by this publisher', 'KeyP']];
function similar(b, f){
  const ts = valsOf(b, f).map(v => term(f, v)); if (!ts.length) return;
  setQ(ts.length === 1 ? ts[0] : f === 'tags' ? ts.join(' and ') : '(' + ts.join(' or ') + ')');
}

// Mark books: a pin on the books to come back to, the same on every device; marked:true finds them.
async function setMarks(ids, on){
  let r;
  try { r = await api('/api/catalog/marks', { method: 'PUT', body: JSON.stringify(ids == null ? { clear: true } : on ? { add: ids } : { remove: ids }) }); }
  catch(e){ toast(e.message); return; }
  const m = new Set(r.marks);
  if (P.data) { P.data.books.forEach(b => { b.marked = m.has(b.calibre_id); }); P.data.marks = r.marks.length; }
  if (/\bmarked:/i.test(P.q)) load(); else draw();
}
function toggleMarks(ids){
  const bs = ids ? P.data.books.filter(b => ids.includes(b.calibre_id)) : chosenBooks();
  if (bs.length) setMarks(bs.map(b => b.calibre_id), !bs.every(b => b.marked));
}

/* Quickview (Calibre's Q): for the chosen book, the other books with its author, series, tags or
   publisher, under the list; a click chooses one in the list, Search puts them in the list. */
const QVF = [['authors', 'Authors'], ['series', 'Series'], ['tags', 'Tags'], ['publisher', 'Publisher']];
const qvCache = new Map();
function toggleQv(on){
  P.qv = on == null ? !P.qv : on; if (!narrow()) store.set('calQv', P.qv);
  if (P.qv && narrow()) { if (P.side) toggleSide(false); if (P.det) toggleDet(false, true); }
  const pg = $('#catpage'); if (pg) pg.classList.toggle('qv', P.qv);
  const b = $('[data-act="cat:qv"]'); if (b) b.setAttribute('aria-pressed', P.qv);
  const box = $('#catqv'); if (box) { box.dataset.key = ''; if (!P.qv) box.innerHTML = ''; }
  drawQv();
}
async function drawQv(){
  const box = $('#catqv'); if (!box || !P.qv) return;
  const b = anchorBook();
  if (!b) { box.innerHTML = ''; box.dataset.key = ''; return; }
  let f = P.qvField; if (!valsOf(b, f).length) f = (QVF.find(([k]) => valsOf(b, k).length) || ['authors'])[0];
  const vals = valsOf(b, f), v = vals.includes(P.qvVal) ? P.qvVal : vals[0];
  const key = JSON.stringify([b.calibre_id, f, v, P.priv]);
  if (box.dataset.key === key && box.firstChild) return;
  box.dataset.key = key; P.qvNow = { f, v };
  box.innerHTML = '<div class="qvhead"><span class="qvtabs" role="tablist">' + QVF.map(([k, l]) => '<button role="tab" class="calsw" data-qvf="' + k + '" aria-pressed="' + (k === f) + '"' + (valsOf(b, k).length ? '' : ' disabled') + '>' + l + '</button>').join('') + '</span>' +
    '<span class="spacer"></span>' + (v != null ? '<button class="btn sm" data-qv="search">Search</button>' : '') + '<button class="btn sm ib" data-qv="close" aria-label="Close">' + IC.x + '</button></div>' +
    (vals.length > 1 ? '<div class="qvvals">' + vals.map(x => '<button class="qvv' + (x === v ? ' on' : '') + '" data-qvv="' + esc(x) + '">' + esc(x) + '</button>').join('') + '</div>' : '') +
    '<div class="qvlist" id="qvlist">' + (v == null ? '' : '<span class="befcvwait"></span>') + '</div>';
  if (v == null) return;
  const qs = new URLSearchParams({ q: term(f, v), sort: f === 'series' ? 'series' : 'title', desc: '0' }); if (P.priv) qs.set('private', '1');
  let r = qvCache.get(qs.toString());
  if (!r) { try { r = await api('/api/catalog?' + qs.toString()); qvCache.set(qs.toString(), r); } catch(e){ const l = $('#qvlist'); if (l) l.innerHTML = '<span class="mute tiny">' + esc(e.message) + '</span>'; return; } }
  const list = $('#qvlist'); if (!list || box.dataset.key !== key) return;
  list.innerHTML = r.books.map(x => '<button class="qvrow' + (x.calibre_id === b.calibre_id ? ' on' : '') + '" data-qvb="' + x.calibre_id + '" data-cid="' + esc(x.id) + '">' +
    (x.cover ? '<img src="/api/cover/' + encodeURIComponent(x.id) + '?v=' + (x.cover_v || 0) + '" alt="" loading="lazy">' : C.cover({ id: x.id, title: x.title }, 'cv')) +
    '<span><b>' + esc(x.title) + '</b><span>' + esc([(x.authors || []).join(' & '), x.series ? x.series + ' #' + (Math.round((x.series_index || 0) * 10) / 10) : ''].filter(Boolean).join(' · ')) + '</span></span></button>').join('');
}
// The list scrolled just enough to show a row (scrollIntoView would move the page around it too).
function reveal(id){
  const box = $('#catscroll'), el = box && $('[data-cal="' + id + '"]', box); if (!el) return;
  const r = el.getBoundingClientRect(), br = box.getBoundingClientRect(), head = (($('thead', box) || {}).offsetHeight) || 0;
  if (r.top < br.top + head) box.scrollTop -= br.top + head - r.top;
  else if (r.bottom > br.bottom) box.scrollTop += r.bottom - br.bottom;
}
function chooseOnly(id){ [...P.sel].forEach(x => { if (x !== id) choose(x, false); }); choose(id, true); P.anchor = id; chosenSync(); reveal(id); }
document.addEventListener('click', e => {
  const t = e.target; if (!t.closest || !t.closest('#catqv')) return;
  const tab = t.closest('[data-qvf]'); if (tab && !tab.disabled) { P.qvField = tab.dataset.qvf; P.qvVal = null; store.set('calQvField', P.qvField); drawQv(); return; }
  const vv = t.closest('[data-qvv]'); if (vv) { P.qvVal = vv.dataset.qvv; drawQv(); return; }
  const a = t.closest('[data-qv]');
  if (a) { if (a.dataset.qv === 'close') toggleQv(false);
    else if (P.qvNow && P.qvNow.v != null) setQ(term(P.qvNow.f, P.qvNow.v));
    return; }
  const row = t.closest('[data-qvb]');
  if (row) { const id = +row.dataset.qvb;
    if (P.data.books.some(x => x.calibre_id === id)) { P.qvVal = P.qvNow ? P.qvNow.v : null; chooseOnly(id); }
    else location.hash = 'book/' + encodeURIComponent(row.dataset.cid); }
});
document.addEventListener('dblclick', e => { const row = e.target.closest && e.target.closest('#catqv [data-qvb]'); if (row) location.hash = 'book/' + encodeURIComponent(row.dataset.cid); });

/* The Tag browser's menu (right-click a name, or hold it): search for it or for everything but it,
   rename it, delete it, or open the manager for its kind, all across the library. */
const MANAGE = { tags: 'Manage tags', authors: 'Manage authors', series: 'Manage series', publisher: 'Manage publishers' };
const manageable = k => !!MANAGE[k] || (k.startsWith('#') && !!P.data && P.data.columns.some(c => c.key === k && c.custom && ['text', 'series'].includes(c.dtype)));
function tagMenu(el, x, y){
  const k = el.dataset.catk, n = el.dataset.catn, t = el.dataset.catt, label = MANAGE[k] || 'Manage ' + ((P.data.columns.find(c => c.key === k) || {}).label || k);
  const p = $('#pop'); p.onclick = p.oninput = p.onkeydown = null;
  p.innerHTML = '<div class="menu catmenu"><button data-tbm="in"><i></i>Search for “' + esc(n) + '”</button><button data-tbm="out"><i></i>Everything but “' + esc(n) + '”</button><hr>' +
    '<button data-tbm="rename"><i></i>Rename “' + esc(n) + '”</button>' + (k !== 'authors' ? '<button data-tbm="delete"><i></i>Delete “' + esc(n) + '”</button>' : '') +
    '<hr><button data-tbm="manage"><i></i>' + esc(label) + '</button></div>';
  p.dataset.tbk = k; p.dataset.tbn = n; p.dataset.tbt = t;
  p.hidden = false;
  if (matchMedia('(max-width:700px)').matches) { p.style.left = ''; p.style.top = ''; return; }
  p.style.left = Math.max(8, Math.min(innerWidth - p.offsetWidth - 8, x)) + 'px';
  p.style.top = Math.max(8, Math.min(innerHeight - p.offsetHeight - 8, y)) + 'px';
}
// What the search had for the old name, now for the new one (or gone).
function swapTerm(t, to){
  const re = new RegExp('(^|[\\s(])(not )?' + esc_re(t) + '(?=$|[\\s)])', 'gi');
  if (re.test(P.q)) setQ(P.q.replace(re, (m, a, nt) => to ? a + (nt || '') + to : a));
}
async function tagAct(act){
  const p = $('#pop'), k = p.dataset.tbk, n = p.dataset.tbn, t = p.dataset.tbt; p.hidden = true;
  if (act === 'in') { setQ(t); return; }
  if (act === 'out') { setQ('not ' + t); return; }
  if (act === 'manage') { if (C.BookEdit) C.BookEdit.items(k); return; }
  try {
    if (act === 'rename') {
      const to = (prompt('Rename “' + n + '”', n) || '').trim();
      if (!to || to === n) return;
      const known = ((P.facets || []).find(f => f.key === k) || { values: [] }).values.some(([v]) => v === to);
      if (known && !confirm('Combine “' + n + '” into “' + to + '”?')) return;
      await api('/api/catalog/items/rename', { method: 'POST', body: JSON.stringify({ field: k, from: [n], to }) });
      swapTerm(t, term(k, to));
    } else if (act === 'delete') {
      if (!confirm('Delete “' + n + '” from every book that has it?')) return;
      await api('/api/catalog/items/delete', { method: 'POST', body: JSON.stringify({ field: k, names: [n] }) });
      swapTerm(t, '');
    }
    qvCache.clear(); P.facets = null; C.Catalog.reload();
  } catch(e){ toast(e.message); }
}
document.addEventListener('click', e => { const b = e.target.closest && e.target.closest('#pop [data-tbm]'); if (b) tagAct(b.dataset.tbm); });
document.addEventListener('contextmenu', e => {
  const v = e.target.closest && e.target.closest('#catside .catv[data-catn]'); if (!v) return;
  e.preventDefault(); const r = v.getBoundingClientRect();
  tagMenu(v, e.clientX || r.left + 24, e.clientY || r.bottom);
});
// Held down with a finger or the pen, a name opens the same menu, and the tap that ends it does nothing.
const hold = { t: null, at: 0 };
document.addEventListener('pointerdown', e => {
  const v = e.target.closest && e.target.closest('#catside .catv[data-catn]'); if (!v || e.pointerType === 'mouse') return;
  const x = e.clientX, y = e.clientY;
  clearTimeout(hold.t); hold.x = x; hold.y = y;
  hold.t = setTimeout(() => { hold.at = Date.now(); tagMenu(v, x, y); }, 550);
});
document.addEventListener('pointermove', e => { if (hold.t && Math.hypot(e.clientX - hold.x, e.clientY - hold.y) > 8) { clearTimeout(hold.t); hold.t = null; } });
['pointerup', 'pointercancel'].forEach(ev => document.addEventListener(ev, () => { clearTimeout(hold.t); hold.t = null; }));
document.addEventListener('click', e => { if (Date.now() - hold.at < 700 && e.target.closest && e.target.closest('#catside .catv')) { e.stopImmediatePropagation(); e.preventDefault(); } }, true);

/* Editing a cell where it is (Calibre's F2, or the row's menu): Enter or leaving it saves it in
   Calibre, Esc puts it back. Series takes "Name [3]" for its number, as Calibre's does. */
const EDIT = new Set(['title', 'authors', 'series', 'tags', 'rating', 'published', 'publisher', 'languages']);
const CEDIT = new Set(['text', 'series', 'int', 'float', 'bool', 'datetime', 'rating', 'enumeration']);
const editable = c => !!c && (EDIT.has(c.key) || (!!c.custom && CEDIT.has(c.dtype)));
const ED = { td: null };
function editCell(cid, key){
  if (P.grid || !P.data) return;
  const cols = colsNow(), i = cols.findIndex(c => c.key === key), c = cols[i], b = P.data.books.find(x => x.calibre_id === cid);
  const tr = $('#catscroll tbody tr[data-cal="' + cid + '"]');
  if (!editable(c) || !tr || !b) return;
  if (ED.td) cancelCell();
  const td = tr.children[i + 1];
  Object.assign(ED, { td, cid, c, b });
  td.classList.add('catediting'); td.innerHTML = editor(c, b);
  const el = $('[data-catin]', td); el.focus();
  if (el.tagName === 'INPUT' && el.type === 'text') el.select();
}
function editor(c, b){
  const v = b[c.key], k = c.key;
  const opts = (list, cur) => list.map(([x, l]) => '<option value="' + esc(x) + '"' + (String(x) === String(cur) ? ' selected' : '') + '>' + esc(l) + '</option>').join('');
  if (c.type === 'rating') return '<select class="field sm catin" data-catin>' + opts([['', '—']].concat([1, 1.5, 2, 2.5, 3, 3.5, 4, 4.5, 5].map(n => [n, '★'.repeat(Math.floor(n)) + (n % 1 ? '½' : '')])), v == null ? '' : v) + '</select>';
  if (c.type === 'bool') return '<select class="field sm catin" data-catin>' + opts([['', '—'], ['true', 'Yes'], ['false', 'No']], v == null ? '' : String(!!v)) + '</select>';
  if (c.dtype === 'enumeration' && c.enum) return '<select class="field sm catin" data-catin>' + opts([['', '—']].concat(c.enum.map(x => [x, x])), v == null ? '' : v) + '</select>';
  if (c.type === 'date') return '<input class="field sm catin" data-catin type="date" value="' + esc(v || '') + '">';
  if (c.type === 'number') return '<input class="field sm catin" data-catin type="number" step="any" inputmode="decimal" value="' + esc(v == null ? '' : v) + '">';
  const text = Array.isArray(v) ? v.join(k === 'authors' ? ' & ' : ', ') : v == null ? '' : String(v);
  const f = c.type !== 'list' && (P.facets || []).find(x => x.key === k);
  return '<input class="field sm catin" data-catin type="text" autocomplete="off" spellcheck="false" value="' + esc(text) + '"' + (f ? ' list="catdl"' : '') + '>' +
    (f ? '<datalist id="catdl">' + f.values.slice(0, 1500).map(([x]) => '<option value="' + esc(x) + '">').join('') + '</datalist>' : '');
}
// What Calibre is told for what's in the box, or null when it's what the book already has.
function cellFields(c, raw, b){
  const k = c.key, cur = b[k], s = String(raw).trim();
  const same = (a, z) => JSON.stringify(a == null ? null : a) === JSON.stringify(z == null ? null : z);
  if (k === 'title') return s && s !== cur ? { title: s } : null;
  if (k === 'authors') { const a = s.split('&').map(x => x.trim()).filter(Boolean); return a.length && !same(a, cur || []) ? { authors: a } : null; }
  if (k === 'series') {
    const m = s.match(/^(.*?)\s*\[\s*(\d+(?:\.\d+)?)\s*\]$/), name = m ? m[1].trim() : s, out = {};
    if (name !== (cur || '')) out.series = name;
    if (m && name && +m[2] !== b.series_index) out.series_index = +m[2];
    return Object.keys(out).length ? out : null;
  }
  if (c.type === 'list') { const a = [...new Set(s.split(',').map(x => x.trim()).filter(Boolean))]; return same(a, cur || []) ? null : { [k]: a }; }
  if (c.type === 'rating' || c.type === 'number') {
    const n = s === '' ? null : +s;
    if (Number.isNaN(n)) { toast('Not a number'); return null; }
    return same(n, cur) ? null : { [k]: n };
  }
  if (c.type === 'bool') { const n = s === '' ? null : s === 'true'; return same(n, cur == null ? null : !!cur) ? null : { [k]: n }; }
  return s === (cur || '') ? null : { [k]: s || null };
}
async function commitCell(){
  if (!ED.td) return;
  const { td, cid, c, b } = ED, el = $('[data-catin]', td); ED.td = null;
  const f = el ? cellFields(c, el.value, b) : null;
  if (!f) { draw(); return; }
  td.classList.remove('catediting'); td.classList.add('catsaving'); td.textContent = el.tagName === 'SELECT' ? el.options[el.selectedIndex].text : el.value;
  try {
    await api('/api/catalog/book/' + cid, { method: 'PUT', body: JSON.stringify({ fields: f }) });
    P.info.delete(b.id); qvCache.clear();
    load(true).then(() => { if (P.side) drawSide(); });
  } catch(e){ toast(e.message); draw(); }
}
function cancelCell(){ if (!ED.td) return; ED.td = null; draw(); }
document.addEventListener('keydown', e => {
  const el = e.target; if (!el.matches || !el.matches('[data-catin]')) return;
  e.stopPropagation();
  if (e.key === 'Enter' || e.key === 'Tab') { e.preventDefault(); commitCell(); }
  else if (e.key === 'Escape') { e.preventDefault(); cancelCell(); }
}, true);
document.addEventListener('change', e => { if (e.target.matches && e.target.matches('select[data-catin]')) commitCell(); });
document.addEventListener('focusout', e => { const el = e.target; if (el.matches && el.matches('input[data-catin]') && ED.td && ED.td.contains(el)) setTimeout(() => { if (ED.td && !ED.td.contains(document.activeElement)) commitCell(); }, 120); });
document.addEventListener('click', e => { if (e.target.closest && e.target.closest('.catediting')) e.stopPropagation(); }, true);

/* Calibre's keys in All books (keys.js "catalog": the letters can be changed in Preferences → Keyboard). */
const TOOLKEY = { add: 'add', edit: 'edit', convert: 'conv', read: 'read', ebook: 'ebook', polish: 'polish', find: 'find', merge: 'merge', download: 'dl', remove: 'remove' };
const moveTo = (by, extend) => {
  const ids = P.data.books.map(x => x.calibre_id); if (!ids.length) return;
  const at = ids.indexOf(P.anchor);
  const i = by === Infinity ? ids.length - 1 : by === -Infinity ? 0 : at < 0 ? (by > 0 ? 0 : ids.length - 1) : Math.max(0, Math.min(ids.length - 1, at + by)), id = ids[i];
  if (extend && at >= 0) { choose(id, true); P.anchor = id; chosenSync(); reveal(id); } else chooseOnly(id);
};
document.addEventListener('keydown', e => {
  if (C.S.route[0] !== 'catalog' || !P.data || e.defaultPrevented) return;
  const t = e.target, tag = (t.tagName || '').toLowerCase();
  if (tag === 'input' || tag === 'textarea' || tag === 'select' || t.isContentEditable) return;
  if (['#modal', '#pop', '#palette', '#bedit', '#emsheet'].some(q => $(q) && !$(q).hidden) || $('.besheet:not([hidden])')) return;
  const K = C.Keys, mod = e.metaKey || e.ctrlKey;
  const go = k => { const b = $('#caltools [data-cal="' + k + '"]'); if (b && !b.disabled) { e.preventDefault(); b.click(); } };
  if (mod && !e.altKey && !e.shiftKey && e.code === 'KeyA') { e.preventDefault(); P.data.books.forEach(x => P.sel.add(x.calibre_id)); draw(); return; }
  if (mod && !e.altKey && e.code === 'KeyD') { go('find'); return; }
  if (mod && !e.altKey && e.code === 'KeyM') { e.preventDefault(); toggleMarks(); return; }
  if (mod && !e.altKey && e.code === 'KeyF') { e.preventDefault(); const q = $('#catq'); if (q) { q.focus(); q.select(); } return; }
  if (e.altKey && !mod) { const s = SIM.find(x => x[2] === e.code), b = anchorBook(); if (s && b) { e.preventDefault(); similar(b, s[0]); } return; }
  if (mod || e.altKey) return;
  if (e.key === '?') { e.preventDefault(); e.stopImmediatePropagation(); if (K) K.sheet('catalog', 'All books'); return; }
  if (e.key === 'Escape') { if (P.sel.size) { e.preventDefault(); P.sel.clear(); draw(); } return; }
  if (e.shiftKey && (e.key === 'ArrowDown' || e.key === 'ArrowUp')) { e.preventDefault(); moveTo(e.key === 'ArrowDown' ? 1 : -1, true); return; }
  if (!K) return;
  const is = a => K.is(e, 'catalog', a);
  if (is('next')) { e.preventDefault(); moveTo(1); }
  else if (is('prev')) { e.preventDefault(); moveTo(-1); }
  else if (is('first')) { e.preventDefault(); moveTo(-Infinity); }
  else if (is('last')) { e.preventDefault(); moveTo(Infinity); }
  else if (is('open')) { const b = anchorBook(); if (b) { e.preventDefault(); location.hash = 'book/' + encodeURIComponent(b.id); } }
  else if (is('search')) { e.preventDefault(); const q = $('#catq'); if (q) { q.focus(); q.select(); } }
  else if (is('quickview')) { e.preventDefault(); toggleQv(); }
  else if (is('cell')) { const b = anchorBook(); if (b) { e.preventDefault(); editCell(b.calibre_id, editable(colsNow().find(c => c.key === P.cell)) ? P.cell : 'title'); } }
  else { const a = Object.keys(TOOLKEY).find(is); if (a) go(TOOLKEY[a]); }
});

C.Catalog = {
  rowMenu: (tr, x, y) => { held = Date.now(); const at = document.elementFromPoint(x, y); rowMenu(tr, x, y, at && at.closest ? at.closest('td') : null); },
  // What a drag from this row carries: every chosen row when it's one of them, else just it.
  dragBooks: tr => { const id = +tr.dataset.cal; return P.data ? P.data.books.filter(b => P.sel.has(id) && P.sel.size > 1 ? P.sel.has(b.calibre_id) : b.calibre_id === id) : []; },
  search: q => { if (C.S.route[0] !== 'catalog') { P.q = q; keep(); location.hash = 'catalog'; } else setQ(q); },
  // These Calibre books, shown and chosen (Import list's new books, ready for Find details).
  choose: ids => { const q = ids.length && ids.length <= 300 ? ids.map(i => 'id:' + i).join(' or ') : 'added:today';
    if (C.S.route[0] !== 'catalog') { C.Catalog.search(q); return; }
    P.q = q; P.view = dirtyView(); keep(); const box = $('#catq'); if (box) box.value = q;
    load().then(() => { ids.forEach(i => P.sel.add(i)); draw(); }); },
  reload: () => { P.info.clear(); const d = $('#catdet'); if (d) d.dataset.cal = ''; if (C.S.route[0] === 'catalog') load(true).then(() => { if (P.side) drawSide(); }); }, books: () => (P.data && P.data.books) || [] };
})();
