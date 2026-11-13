/* All books (#catalog): the Calibre library as a spreadsheet (catalog.py). The search is Calibre's
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
};
const DEF = { q: '', sort: 'added', desc: true, cols: null, widths: {}, priv: false, view: null };
const saved = store.get('catalog', {});
const P = Object.assign({}, DEF, saved, { data: null, facets: null, side: store.get('catalogSide', false),
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
  if (c.key === 'title') return '<a class="catt" href="#book/' + encodeURIComponent(b.id) + '">' + (b.cover ? '<img class="cv catcv" src="/api/cover/' + encodeURIComponent(b.id) + '?v=' + (b.cover_v || 0) + '" alt="" loading="lazy">' : C.cover({ id: b.id, title: b.title }, 'cv catcv')) + '<span>' + esc(b.title) + '</span></a>';
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
C.views.catalog = async () => {
  if (matchMedia('(max-width:1100px)').matches) P.side = false;          // there it's a sheet over the books: closed to begin with
  $('#main').innerHTML = '<div class="top cattop"><h1>All books</h1><span class="mute tiny num catn" id="catn"></span><span class="spacer"></span>' +
    '<input class="field catq" id="catq" type="search" placeholder="Search" autocomplete="off" autocapitalize="off" spellcheck="false" aria-label="Search" value="' + esc(P.q) + '">' +
    '<button class="btn sm catb' + (P.side ? ' on' : '') + '" data-act="cat:side">' + IC.filter + '<span>Filter</span></button>' +
    '<button class="btn sm catb" data-act="cat:cols">' + IC.cols + '<span>Columns</span></button>' +
    '<button class="btn sm catb" data-act="cat:views" id="catviewb">' + IC.views + '<span>' + esc(P.view || 'Views') + '</span></button>' +
    '<button class="btn sm catb ib" data-act="cat:more" aria-label="More">' + IC.dots + '</button></div>' +
    '<div class="catpage' + (P.side ? ' filt' : '') + '" id="catpage"><div class="catshade" data-catm="side"></div><aside class="catside" id="catside" aria-label="Filter"></aside>' +
    '<div class="catscroll" id="catscroll"><p class="mute catmsg">Loading…</p></div></div>';
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
  const n = $('#catn'); if (n) n.textContent = r.count === r.total ? r.total + ' books' : r.count + ' of ' + r.total;
  const q = $('#catq'); if (q) { q.classList.toggle('bad', !!r.error); q.title = r.error || ''; }
  const total = cols.reduce((s, c) => s + widthOf(c), 0) + CK;
  const shown = new Set(r.books.map(b => b.calibre_id));
  for (const id of [...P.sel]) if (!shown.has(id)) P.sel.delete(id);          // only what the table shows stays chosen
  const allOn = r.books.length && r.books.every(b => P.sel.has(b.calibre_id));
  let h = '<table class="cattable" style="width:' + total + 'px"><colgroup><col style="width:' + CK + 'px">' + cols.map(c => '<col style="width:' + widthOf(c) + 'px">').join('') + '</colgroup><thead><tr>' +
    '<th class="catck"><input type="checkbox" data-catall' + (allOn ? ' checked' : '') + ' aria-label="Choose all"></th>' +
    cols.map(c => '<th data-ck="' + esc(c.key) + '" class="' + (NUMERIC.has(c.type) ? 'num ' : '') + (P.sort === c.key ? 'on' : '') + '" aria-sort="' + (P.sort === c.key ? (P.desc ? 'descending' : 'ascending') : 'none') + '">' +
      '<button class="catsort" data-catsort="' + esc(c.key) + '">' + esc(c.label) + (P.sort === c.key ? '<i>' + (P.desc ? '↓' : '↑') + '</i>' : '') + '</button><span class="catrs" data-catrs="' + esc(c.key) + '"></span></th>').join('') +
    '</tr></thead><tbody>';
  h += r.books.map(b => '<tr data-cid="' + esc(b.id) + '" data-cal="' + b.calibre_id + '" class="' + (b.private ? 'priv' : '') + (P.sel.has(b.calibre_id) ? ' sel' : '') + '">' +
    '<td class="catck"><input type="checkbox" data-catsel' + (P.sel.has(b.calibre_id) ? ' checked' : '') + ' aria-label="Choose"></td>' + cols.map(c => '<td class="' + (NUMERIC.has(c.type) ? 'num' : '') + '">' + cellHtml(b, c) + '</td>').join('') + '</tr>').join('');
  h += '</tbody></table>';
  if (r.error) h += '<p class="placeholder catmsg">' + esc(r.error) + '</p>';
  else if (!r.books.length) h += '<p class="mute catmsg">Nothing matches.</p>';
  const top = box.scrollTop, left = box.scrollLeft;
  box.innerHTML = h;
  box.scrollTop = P.scroll || top; box.scrollLeft = left; P.scroll = 0;
  const vb = $('#catviewb span'); if (vb) vb.textContent = P.view || 'Views';
  bulkBar();
}
const CK = 36;
// The bar for the chosen books: change them all at once (bookedit.js).
function bulkBar(){
  const pg = $('#catpage'); if (!pg) return;
  let bar = $('#catbulk');
  if (!P.sel.size) { if (bar) bar.hidden = true; return; }
  if (!bar) { pg.insertAdjacentHTML('beforeend', '<div class="catbulk" id="catbulk"></div>'); bar = $('#catbulk'); }
  const n = P.sel.size, all = P.data ? P.data.books.length : 0;
  bar.hidden = false;
  bar.innerHTML = '<b>' + n + ' chosen</b><span class="spacer"></span>' + (n < all ? '<button class="btn sm" data-catb="all">Choose all ' + all + '</button>' : '') +
    '<button class="btn sm" data-catb="none">Clear</button><button class="btn sm" data-catb="shelves">Shelves</button><button class="btn sm" data-catb="fill">Find details</button>' + (n > 1 ? '<button class="btn sm" data-catb="merge">Merge</button>' : '') + '<button class="btn sm danger" data-catb="remove">Remove</button>' +
    '<button class="btn sm primary" data-catb="edit">' + (n === 1 ? 'Edit details' : 'Edit ' + n + ' books') + '</button>';
}
function choose(id, on){
  if (on) P.sel.add(id); else P.sel.delete(id);
  const tr = $('#catscroll tr[data-cal="' + id + '"]');
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
  const val = (t, label, n) => { const st = stateOf(t);
    return '<button class="catv ' + st + '" data-catt="' + esc(t) + '" aria-pressed="' + (st === 'in') + '"><i>' + (st === 'in' ? '✓' : st === 'out' ? '−' : '') + '</i><span>' + label + '</span>' + (n != null ? '<b>' + n + '</b>' : '') + '</button>'; };
  const group = (key, label, items) => {
    if (fq) items = items.filter(x => x[1].toLowerCase().includes(fq) || label.toLowerCase().includes(fq));
    if (!items.length) return '';
    const open = fq || P.open.has(key), many = !fq && !P.all.has(key) && items.length > 30;
    return '<section class="catg"><button class="catgh" data-catg="' + esc(key) + '">' + IC.chev(open) + '<span>' + esc(label) + '</span><b>' + items.length + '</b></button>' +
      (open ? '<div class="catvs">' + (many ? items.slice(0, 30) : items).map(x => val(x[0], x[1], x[2])).join('') +
        (many ? '<button class="linkbtn tiny catall" data-catall="' + esc(key) + '">Show all ' + items.length + '</button>' : '') + '</div>' : '') + '</section>';
  };
  let h = '<div class="catsh"><input class="field sm" id="catfq" type="search" placeholder="Find a value" autocomplete="off" value="' + esc(P.fq) + '">' +
    (P.q ? '<button class="btn sm" data-catm="clear">Clear</button>' : '') + '<button class="btn sm catdone" data-catm="side">Done</button></div>';
  h += group('added', 'Added', ADDED.map(([t, l]) => [t, esc(l)]));
  h += group('missing', 'Missing', MISSING.map(([t, l]) => [t, esc(l)]));
  h += group('tidy', 'Tidy', TIDY.map(([t, l]) => [t, esc(l)]));
  for (const f of P.facets || []) h += group(f.key, f.label, f.values.map(([v, n]) => [term(f.key, v), f.key === 'rating' ? stars(v) : esc(v), n]));
  side.innerHTML = h;
  if (keepFocus) { const i = $('#catfq'); if (i && document.activeElement !== i && P.fq) { i.focus(); i.setSelectionRange(i.value.length, i.value.length); } }
}
function toggleSide(on){
  P.side = on == null ? !P.side : on; store.set('catalogSide', P.side);
  const pg = $('#catpage'); if (pg) pg.classList.toggle('filt', P.side);
  const b = $('[data-act="cat:side"]'); if (b) b.classList.toggle('on', P.side);
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
async function moreMenu(anchor){
  const qs = new URLSearchParams({ q: P.q, sort: P.sort, desc: P.desc ? '1' : '0', cols: colsNow().map(c => c.key).join(',') });
  if (P.priv) qs.set('private', '1');
  let emb = { pending: 0 };
  try { emb = await api('/api/catalog/embed'); } catch(e){}
  openPop(anchor, '<button data-catm="items"><i></i>Tags, authors and series</button>' +
    (emb.pending ? '<button disabled><i></i>Writing details into files · ' + emb.pending + ' left</button>' : '<button data-catm="embedall"><i></i>Write details into every file</button>') + '<hr>' +
    '<a href="/api/catalog/export?' + qs.toString() + '" download><i></i>Export as CSV</a>' +
    '<button data-catm="priv"' + (P.priv ? ' class="on"' : '') + '><i>' + (P.priv ? '✓' : '') + '</i>Show private books</button>' +
    '<hr><button data-catm="trash"><i></i>Calibre’s trash</button>');
}
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
    else if (!P.data) return;
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
    else if (k === 'clear') setQ('');
    else if (k === 'colsreset') { P.cols = null; P.widths = {}; P.view = dirtyView(); keep(); draw(); $('#pop').hidden = true; }
    else if (k === 'trash') { $('#pop').hidden = true; if (C.BookEdit) C.BookEdit.trash(P.priv); }
    else if (k === 'items') { $('#pop').hidden = true; if (C.BookEdit) C.BookEdit.items('tags'); }
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
document.addEventListener('dblclick', e => { const tr = e.target.closest && e.target.closest('#catscroll tbody tr'); if (tr && !e.target.closest('a,input')) location.hash = 'book/' + encodeURIComponent(tr.dataset.cid); });
document.addEventListener('click', e => {
  const t = e.target; if (!t.closest) return;
  const b = t.closest('[data-catb]');
  if (b) { const k = b.dataset.catb;
    if (k === 'edit' && C.BookEdit) C.BookEdit.bulk([...P.sel]);
    else if (k === 'merge' && C.BookEdit) C.BookEdit.merge(P.data.books.filter(x => P.sel.has(x.calibre_id)));
    else if (k === 'fill' && C.BookEdit) C.BookEdit.fill(P.data.books.filter(x => P.sel.has(x.calibre_id)));
    else if (k === 'shelves' && C.DragBooks) C.DragBooks.sheet(P.data.books.filter(x => P.sel.has(x.calibre_id)), b);
    else if (k === 'remove' && C.BookEdit) C.BookEdit.remove(P.data.books.filter(x => P.sel.has(x.calibre_id))).then(done => { if (done) P.sel.clear(); });
    else if (k === 'none') { P.sel.clear(); draw(); }
    else if (k === 'all') { P.data.books.forEach(x => P.sel.add(x.calibre_id)); draw(); }
    return; }
  if (t.closest('[data-catall]')) { const on = t.checked; P.data.books.forEach(x => choose(x.calibre_id, on)); chosenSync(); return; }
  const tr = t.closest('#catscroll tbody tr'); if (!tr) return;
  if (t.closest('a.catt')) { P.scroll = ($('#catscroll') || {}).scrollTop || 0; return; }
  if (Date.now() - held < 600) return;
  const id = +tr.dataset.cal, ids = P.data.books.map(x => x.calibre_id);
  if (t.closest('[data-catsel]') || matchMedia('(pointer:coarse)').matches || e.metaKey || e.ctrlKey) choose(id, !P.sel.has(id));
  else if (e.shiftKey && P.anchor != null && ids.includes(P.anchor)) {
    const [a, z] = [ids.indexOf(P.anchor), ids.indexOf(id)].sort((x, y) => x - y);
    ids.slice(a, z + 1).forEach(x => choose(x, true));
  } else { [...P.sel].forEach(x => { if (x !== id) choose(x, false); }); choose(id, true); }
  if (!e.shiftKey) P.anchor = id;
  chosenSync();
});
// Right-click a row, or hold it and let go (dragbooks.js): Edit details, shelves, the book's page.
let held = 0;
function rowMenu(tr, x, y){
  const p = $('#pop'), id = tr.dataset.cid, cal = +tr.dataset.cal;
  p.onclick = p.oninput = p.onkeydown = null;
  p.innerHTML = '<div class="menu catmenu"><button data-catrow="edit" data-cal="' + cal + '"><i></i>Edit details</button><button data-catrow="shelves" data-cal="' + cal + '"><i></i>Shelves and collection</button><a href="#book/' + encodeURIComponent(id) + '"><i></i>Open the book’s page</a>' +
    (P.sel.size > 1 && P.sel.has(cal) ? '<hr><button data-catrow="bulk"><i></i>Edit the ' + P.sel.size + ' chosen</button>' : '') + '</div>';
  p.hidden = false;
  if (matchMedia('(max-width:700px)').matches) { p.style.left = ''; p.style.top = ''; return; }
  p.style.left = Math.max(8, Math.min(innerWidth - p.offsetWidth - 8, x)) + 'px';
  p.style.top = Math.max(8, Math.min(innerHeight - p.offsetHeight - 8, y)) + 'px';
}
document.addEventListener('contextmenu', e => {
  const tr = e.target.closest && e.target.closest('#catscroll tbody tr'); if (!tr) return;
  e.preventDefault(); rowMenu(tr, e.clientX, e.clientY);
});
document.addEventListener('click', e => {
  const m = e.target.closest && e.target.closest('[data-catrow]'); if (!m) return;
  $('#pop').hidden = true;
  if (m.dataset.catrow === 'edit' && C.BookEdit) C.BookEdit.open(m.dataset.cal);
  else if (m.dataset.catrow === 'shelves' && C.DragBooks) C.DragBooks.sheet(P.data.books.filter(b => b.calibre_id === +m.dataset.cal));
  else if (m.dataset.catrow === 'bulk' && C.BookEdit) C.BookEdit.bulk([...P.sel]);
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

C.Catalog = {
  rowMenu: (tr, x, y) => { held = Date.now(); rowMenu(tr, x, y); },
  // What a drag from this row carries: every chosen row when it's one of them, else just it.
  dragBooks: tr => { const id = +tr.dataset.cal; return P.data ? P.data.books.filter(b => P.sel.has(id) && P.sel.size > 1 ? P.sel.has(b.calibre_id) : b.calibre_id === id) : []; },
  search: q => { if (C.S.route[0] !== 'catalog') { P.q = q; keep(); location.hash = 'catalog'; } else setQ(q); }, reload: () => { if (C.S.route[0] === 'catalog') load(true).then(() => { if (P.side) drawSide(); }); }, books: () => (P.data && P.data.books) || [] };
})();
