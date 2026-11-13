/* Editing a Calibre book in Daf (calibrewrite.py does the writing, through Calibre itself).
   C.BookEdit.open(calibreId): one book's details, cover and files. C.BookEdit.bulk(ids): the same
   change to several books at once (All books' selection). Only what changed is sent. */
(() => {
'use strict';
const C = window.DafCore, { api, esc, toast, $, $$ } = C;
const E = { d: null, ids: null, orig: null, busy: false };
const MB = n => n == null ? '' : n >= 1048576 ? (n / 1048576).toFixed(1) + ' MB' : Math.max(1, Math.round(n / 1024)) + ' KB';
const ACCEPT = '.epub,.kepub,.azw3,.azw,.mobi,.kfx,.pdf,.fb2,.cbz,.cbr,.cb7,.txt,.rtf,.docx,.html,.htmlz,.djvu,.lit,.odt';

/* ---------- the sheet ---------- */
function sheet(html){
  let s = $('#bedit');
  if (!s) { document.body.insertAdjacentHTML('beforeend', '<div class="beshade" id="beshade"></div><div class="besheet" id="bedit" role="dialog" aria-modal="true"></div>'); s = $('#bedit'); }
  s.innerHTML = html; s.hidden = false; $('#beshade').hidden = false;
  document.body.classList.add('beopen');
  return s;
}
function close(force){
  if (!force && dirty() && !confirm('Leave without saving?')) return;
  const s = $('#bedit'); if (s) s.hidden = true;
  const sh = $('#beshade'); if (sh) sh.hidden = true;
  document.body.classList.remove('beopen');
  E.d = E.ids = E.orig = null; F.snap = null; F.seq++;
}

/* ---------- fields ---------- */
const stars = (name, v) => '<span class="bestars" data-bestars="' + esc(name) + '" data-v="' + (v || '') + '" role="radiogroup" aria-label="Rating">' +
  [1, 2, 3, 4, 5].map(n => '<button type="button" data-star="' + n + '" class="' + ((v || 0) >= n ? 'on' : (v || 0) >= n - .5 ? 'half' : '') + '" aria-label="' + n + ' star' + (n > 1 ? 's' : '') + '">★</button>').join('') + '</span>';
const dl = (id, list) => list && list.length ? '<datalist id="' + id + '">' + list.slice(0, 2000).map(x => '<option value="' + esc(x) + '">').join('') + '</datalist>' : '';
const chips = (name, vals, choices) => '<div class="bechips" data-chips="' + esc(name) + '">' + (vals || []).map(chip).join('') +
  '<input class="bechipin" list="dl-' + esc(name) + '" autocomplete="off" aria-label="Add"></div>' + dl('dl-' + name, choices);
const chip = v => '<span class="bechip" data-v="' + esc(v) + '">' + esc(v) + '<button type="button" data-unchip aria-label="Remove ' + esc(v) + '">×</button></span>';
const row = (label, ctl, cls) => '<div class="berow' + (cls ? ' ' + cls : '') + '"><span>' + esc(label) + '</span><div class="bectl">' + ctl + '</div></div>';
const inp = (name, v, extra) => '<input class="field" data-f="' + esc(name) + '" value="' + esc(v == null ? '' : v) + '"' + (extra || '') + '>';
// A description as Calibre keeps it (HTML), shown and edited with its bold, italics and lists, and only
// those: the same few tags catalog.clean_html keeps. Plain text becomes paragraphs.
const KEEP = new Set(['P', 'BR', 'B', 'STRONG', 'I', 'EM', 'UL', 'OL', 'LI', 'BLOCKQUOTE']);
function cleanHTML(src){
  src = String(src || '');
  if (!/<[a-z!\/]/i.test(src)) return src.trim() ? src.trim().split(/\n\s*\n/).map(p => '<p>' + esc(p).replace(/\n/g, '<br>') + '</p>').join('') : '';
  const doc = new DOMParser().parseFromString('<body>' + src + '</body>', 'text/html'), out = document.createElement('div');
  const walk = (from, to) => {
    for (const n of [...from.childNodes]) {
      if (n.nodeType === 3) { to.appendChild(document.createTextNode(n.nodeValue)); continue; }
      if (n.nodeType !== 1 || /^(SCRIPT|STYLE|TEMPLATE|IFRAME|OBJECT)$/.test(n.tagName)) continue;
      let el = null;
      if (KEEP.has(n.tagName)) el = document.createElement(n.tagName.toLowerCase());
      else if (/^H[1-6]$/.test(n.tagName)) { el = document.createElement('p'); const b = document.createElement('b'); el.appendChild(b); walk(n, b); to.appendChild(el); continue; }
      else if (n.tagName === 'DIV') el = document.createElement('p');
      if (el) { walk(n, el); to.appendChild(el); } else walk(n, to);
    }
  };
  walk(doc.body, out);
  return out.innerHTML.replace(/<p>\s*<\/p>/g, '');
}
const RICH = { bold: '<b>B</b>', italic: '<i>I</i>', insertUnorderedList: '<svg width="16" height="16" viewBox="0 0 20 20" aria-hidden="true"><path d="M8 5.5h8M8 10h8M8 14.5h8" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/><circle cx="4.5" cy="5.5" r="1.2" fill="currentColor"/><circle cx="4.5" cy="10" r="1.2" fill="currentColor"/><circle cx="4.5" cy="14.5" r="1.2" fill="currentColor"/></svg>' };
const RICHNAME = { bold: 'Bold', italic: 'Italic', insertUnorderedList: 'List' };
const rich = (name, html) => '<div class="berichwrap"><div class="berichbar">' + Object.keys(RICH).map(k => '<button type="button" data-richcmd="' + k + '" aria-label="' + RICHNAME[k] + '" title="' + RICHNAME[k] + '">' + RICH[k] + '</button>').join('') + '</div>' +
  '<div class="field berich" contenteditable="true" role="textbox" aria-multiline="true" aria-label="Description" data-rich="' + esc(name) + '">' + cleanHTML(html) + '</div></div>';
// The bar's buttons work on the words chosen in the description (the editor keeps its own selection).
document.addEventListener('mousedown', e => { if (e.target.closest && e.target.closest('[data-richcmd]')) e.preventDefault(); });
document.addEventListener('click', e => {
  const b = e.target.closest && e.target.closest('[data-richcmd]'); if (!b) return;
  const ed = b.closest('.berichwrap').querySelector('[data-rich]'); ed.focus();
  document.execCommand(b.dataset.richcmd, false, null);
});

function customCtl(c, v, bulk){
  const n = c.key;
  if (c.dtype === 'enumeration') return '<select class="field" data-f="' + esc(n) + '">' + (bulk ? '<option value="">No change</option><option value="\u0000">None</option>' : '<option value=""></option>') +
    (c.enum || []).map(x => '<option' + (x === v ? ' selected' : '') + '>' + esc(x) + '</option>').join('') + '</select>';
  if (c.dtype === 'bool') return '<select class="field" data-f="' + esc(n) + '">' + (bulk ? '<option value="">No change</option>' : '<option value=""></option>') + '<option value="true"' + (v === true ? ' selected' : '') + '>Yes</option><option value="false"' + (v === false ? ' selected' : '') + '>No</option></select>';
  const keep = bulk ? ' placeholder="No change"' : '';
  if (c.dtype === 'int' || c.dtype === 'float') return inp(n, v, ' type="number" step="' + (c.dtype === 'int' ? '1' : 'any') + '" inputmode="decimal"' + keep);
  if (c.dtype === 'datetime') return inp(n, v, ' type="date"');
  if (c.dtype === 'rating') return stars(n, v);
  if (c.dtype === 'comments') return '<textarea class="field" rows="3" data-f="' + esc(n) + '">' + esc(v || '') + '</textarea>';
  const list = (E.d && E.d.choices && E.d.choices[n]) || [];
  return inp(n, Array.isArray(v) ? v.join(', ') : v, (list.length ? ' list="dl-' + esc(n) + '" autocomplete="off"' : '') + keep) + dl('dl-' + n, list);
}

/* ---------- one book ---------- */
async function open(cid){
  cid = String(cid).replace(/^cal:/, '');
  sheet('<div class="behead"><h2>Edit details</h2></div><div class="bebody"><p class="mute">Loading…</p></div>');
  let d;
  try { d = await api('/api/catalog/book/' + encodeURIComponent(cid)); } catch(e){ close(true); toast(e.message); return; }
  E.d = d; E.ids = null;
  draw();
}
function draw(){
  const d = E.d, coverUrl = '/api/cover/' + encodeURIComponent(d.id) + '?v=' + (E.coverV || 0);
  const idents = Object.entries(d.identifiers || {}).map(([k, v]) => k + ': ' + v).join('\n');
  const s = sheet('<div class="behead"><h2>' + esc(d.title) + '</h2><span class="spacer"></span><button class="btn sm" data-be="find">Find details</button><button class="btn sm" data-be="cancel">Cancel</button><button class="btn sm primary" data-be="save">Save</button></div>' +
    '<div class="bebody"><div class="beside">' +
      '<div class="becover">' + (d.cover ? '<img src="' + coverUrl + '" alt="">' : '<span class="becovernone">' + esc(d.title) + '</span>') + '</div>' +
      '<label class="btn sm befile">Change cover<input type="file" accept="image/*" data-be="coverfile" hidden></label>' +
      '<button class="btn sm" data-be="coverurl">Cover from a link</button>' +
      '<h3>Files</h3><div class="befiles">' + (d.files.length ? d.files.map(f => '<div class="befilerow"><b>' + esc(f.format) + '</b><span class="mute tiny">' + MB(f.size) + '</span><span class="spacer"></span>' +
        (f.exists ? '<a class="ib" href="/api/catalog/book/' + d.calibre_id + '/files/' + esc(f.format) + '" download aria-label="Download ' + esc(f.format) + '">' + ICON.down + '</a>' : '') +
        '<button class="ib" data-be="filemenu" data-fmt="' + esc(f.format) + '" aria-label="More for ' + esc(f.format) + '">' + ICON.dots + '</button></div>').join('') : '<span class="mute tiny">No file</span>') + '</div>' +
      '<div id="beconv"></div>' +
      '<label class="btn sm befile">Add a file<input type="file" accept="' + ACCEPT + '" data-be="addfile" hidden></label>' +
      '<button class="btn sm danger beremove" data-be="remove">Remove from Calibre</button>' +
    '</div><div class="beform">' +
      row('Title', inp('title', d.title)) +
      row('Title sort', inp('title_sort', d.title_sort || '')) +
      row('Authors', inp('authors', (d.authors || []).join(' & '), ' list="dl-authors" autocomplete="off"') + dl('dl-authors', d.choices.authors)) +
      row('Author sort', inp('author_sort', d.author_sort || '')) +
      row('Series', '<span class="beser">' + inp('series', d.series, ' list="dl-series" autocomplete="off"') + dl('dl-series', d.choices.series) + inp('series_index', d.series ? d.series_index : '', ' type="number" step="any" inputmode="decimal" aria-label="Number in the series"') + '</span>') +
      row('Tags', chips('tags', d.tags, d.choices.tags), 'betop') +
      row('Rating', stars('rating', d.rating)) +
      row('Publisher', inp('publisher', d.publisher, ' list="dl-publisher" autocomplete="off"') + dl('dl-publisher', d.choices.publisher)) +
      row('Published', inp('published', d.published, ' type="date"')) +
      row('Languages', inp('languages', (d.languages || []).join(', '), ' list="dl-languages" autocomplete="off"') + dl('dl-languages', d.choices.languages)) +
      row('Identifiers', '<textarea class="field" rows="' + Math.max(2, Math.min(8, Object.keys(d.identifiers || {}).length + 1)) + '" data-f="identifiers" spellcheck="false">' + esc(idents) + '</textarea>', 'betop') +
      row('Description', rich('comments', d.comments_clean != null ? d.comments_clean : d.comments), 'betop') +
      (d.custom || []).filter(c => c.key !== '#isbn').map(c => row(c.label, customCtl(c, d[c.key]), c.dtype === 'comments' ? 'betop' : '')).join('') +
    '</div></div>');
  E.orig = values(s);
  s.dataset.mode = 'one';
}
const ICON = {
  down: '<svg width="16" height="16" viewBox="0 0 20 20" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M10 3v10M5.5 9l4.5 4.5L14.5 9M4 16.5h12"/></svg>',
  dots: '<svg width="16" height="16" viewBox="0 0 20 20" aria-hidden="true"><circle cx="5" cy="10" r="1.5" fill="currentColor"/><circle cx="10" cy="10" r="1.5" fill="currentColor"/><circle cx="15" cy="10" r="1.5" fill="currentColor"/></svg>',
};

// What the sheet holds now, field by field.
function values(s){
  const v = {};
  $$('[data-f]', s).forEach(el => { v[el.dataset.f] = el.value; });
  $$('[data-chips]', s).forEach(el => { v[el.dataset.chips] = $$('.bechip', el).map(c => c.dataset.v); });
  $$('[data-bestars]', s).forEach(el => { v[el.dataset.bestars] = el.dataset.v ? +el.dataset.v : null; });
  $$('[data-rich]', s).forEach(el => { v[el.dataset.rich] = el.innerHTML; });
  return v;
}
function dirty(){
  const s = $('#bedit'); if (!s || s.hidden || !E.orig) return false;
  if (F.snap) return JSON.stringify(F.snap) !== JSON.stringify(F.orig);
  return JSON.stringify(values(s)) !== JSON.stringify(E.orig);
}
function changed(){
  const now = values($('#bedit')), out = {};
  for (const k of Object.keys(now)) if (JSON.stringify(now[k]) !== JSON.stringify(E.orig[k])) out[k] = now[k];
  return out;
}
function toFields(ch, bulk){
  const f = {}, custom = Object.fromEntries(((E.d && E.d.custom) || []).map(c => [c.key, c]));
  for (const [k, v] of Object.entries(ch)) {
    if (k === 'identifiers') { f.identifiers = {}; String(v).split('\n').forEach(l => { const m = l.match(/^\s*([^:\s]+)\s*:\s*(.+?)\s*$/); if (m) f.identifiers[m[1]] = m[2]; }); }
    else if (k === 'languages') f.languages = v.split(',').map(x => x.trim()).filter(Boolean);
    else if (k === 'comments' && !bulk) f.comments_html = cleanHTML(v);
    else if (k === 'series_index') { if (v !== '') f.series_index = +v; }
    else if (custom[k]) {
      const c = custom[k];
      if (bulk && v === '') continue;
      f[k] = v === '\u0000' || v === '' ? null : c.dtype === 'bool' ? v === 'true' : (c.dtype === 'int' || c.dtype === 'float') ? +v : c.multi && typeof v === 'string' ? v.split(',').map(x => x.trim()).filter(Boolean) : v;
    }
    else f[k] = v;
  }
  return f;
}
async function save(){
  if (E.busy) return;
  const s = $('#bedit'), btn = $('[data-be="save"]', s);
  addTyped(s);
  if (E.ids) return saveBulk();
  const ch = changed();
  if (!Object.keys(ch).length) { close(true); return; }
  E.busy = true; btn.disabled = true; btn.textContent = 'Saving…';
  try {
    await api('/api/catalog/book/' + E.d.calibre_id, { method: 'PUT', body: JSON.stringify({ fields: toFields(ch) }) });
    toast('Saved in Calibre'); close(true); after();
  } catch(e){ toast(e.message); btn.disabled = false; btn.textContent = 'Save'; }
  E.busy = false;
}
// After a change: the All books table, the book's page and the Books page show it.
function after(){
  if (C.Catalog) C.Catalog.reload();
  if (['book', 'books'].includes(C.S.route[0])) window.dispatchEvent(new HashChangeEvent('hashchange'));
}

/* ---------- several books ---------- */
async function bulk(ids){
  ids = ids.map(x => String(x).replace(/^cal:/, ''));
  if (ids.length === 1) return open(ids[0]);
  sheet('<div class="behead"><h2>' + ids.length + ' books</h2></div><div class="bebody"><p class="mute">Loading…</p></div>');
  let d;
  try { d = await api('/api/catalog/book/' + ids[0]); } catch(e){ close(true); toast(e.message); return; }
  E.d = d; E.ids = ids;
  const books = (C.Catalog && C.Catalog.books ? C.Catalog.books() : []).filter(b => ids.includes(String(b.calibre_id)));
  const theirTags = [...new Set(books.flatMap(b => b.tags || []))].sort((a, b) => a.localeCompare(b));
  const s = sheet('<div class="behead"><h2>' + ids.length + ' books</h2><span class="spacer"></span><button class="btn sm" data-be="cancel">Cancel</button><button class="btn sm primary" data-be="save">Save</button></div>' +
    '<div class="bebody one"><div class="beform">' +
      row('Authors', inp('authors', '', ' list="dl-authors" autocomplete="off" placeholder="No change"') + dl('dl-authors', d.choices.authors)) +
      '<div class="berow becheck"><span></span><label class="bectl"><input type="checkbox" data-f2="flip"> Turn “Last, First” names around</label></div>' +
      row('Series', inp('series', '', ' list="dl-series" autocomplete="off" placeholder="No change"') + dl('dl-series', d.choices.series)) +
      '<div class="berow becheck"><span></span><label class="bectl"><input type="checkbox" data-f2="number"> Number them from <input class="field benum" data-f2="start" type="number" value="1" step="any" inputmode="decimal"> in the table’s order</label></div>' +
      row('Add tags', chips('add_tags', [], d.choices.tags), 'betop') +
      row('Remove tags', chips('remove_tags', [], theirTags), 'betop') +
      row('Rating', '<span class="bestarrow">' + stars('rating', null) + '<label class="benone"><input type="checkbox" data-f2="norating"> No rating</label></span>') +
      row('Publisher', inp('publisher', '', ' list="dl-publisher" autocomplete="off" placeholder="No change"') + dl('dl-publisher', d.choices.publisher)) +
      row('Published', inp('published', '', ' type="date"')) +
      row('Languages', inp('languages', '', ' list="dl-languages" autocomplete="off" placeholder="No change"') + dl('dl-languages', d.choices.languages)) +
      (d.custom || []).filter(c => c.key !== '#isbn' && c.dtype !== 'comments').map(c => row(c.label, customCtl(c, null, true))).join('') +
    '</div></div>');
  s.dataset.mode = 'bulk';
  E.orig = values(s);
}
async function saveBulk(){
  const s = $('#bedit'), btn = $('[data-be="save"]', s), ch = changed();
  const add = ch.add_tags || [], rem = ch.remove_tags || [];
  delete ch.add_tags; delete ch.remove_tags;
  for (const k of ['authors', 'series', 'publisher', 'languages', 'published']) if (ch[k] === '') delete ch[k];
  const fields = toFields(ch, true);
  if ($('[data-f2="norating"]', s).checked) fields.rating = null;
  if ($('[data-f2="number"]', s).checked) { fields.series_number = +$('[data-f2="start"]', s).value || 1; }
  if ($('[data-f2="flip"]', s).checked && fields.authors === undefined) fields.authors_flip = true;
  if (!Object.keys(fields).length && !add.length && !rem.length) { close(true); return; }
  if (fields.authors !== undefined) fields.authors = String(fields.authors).split('&').map(x => x.trim()).filter(Boolean);
  // In the table's order, for numbering a series.
  const order = C.Catalog && C.Catalog.books ? C.Catalog.books().map(b => String(b.calibre_id)).filter(id => E.ids.includes(id)) : E.ids;
  E.busy = true; btn.disabled = true; btn.textContent = 'Saving…';
  try {
    await api('/api/catalog/bulk', { method: 'POST', body: JSON.stringify({ ids: order.length === E.ids.length ? order : E.ids, fields, add_tags: add, remove_tags: rem }) });
    toast(E.ids.length + ' books changed in Calibre'); close(true); after();
  } catch(e){ toast(e.message); btn.disabled = false; btn.textContent = 'Save'; }
  E.busy = false;
}

/* ---------- covers and files ---------- */
async function cover(body, type){
  try {
    await api('/api/catalog/book/' + E.d.calibre_id + '/cover', { method: 'PUT', body, headers: { 'Content-Type': type } });
    E.coverV = Date.now(); E.d.cover = true; toast('New cover'); freshCover(E.d.id);
    const keep = values($('#bedit')), orig = E.orig; draw(); restore(keep); E.orig = orig;
    if (C.Catalog) C.Catalog.reload();
  } catch(e){ toast(e.message); }
}
// The cover's plain address is kept a week on the device: it's fetched again now, for the book's
// page, Books and the reader (the table asks for it by its time, catalog.py cover_v).
function freshCover(id){
  const u = '/api/cover/' + encodeURIComponent(id);
  (window.caches ? caches.open('daf-img-v1').then(c => c.delete(u)) : Promise.resolve())
    .then(() => fetch(u, { cache: 'reload', credentials: 'same-origin' })).catch(() => {});
}
function restore(v){
  const s = $('#bedit');
  $$('[data-f]', s).forEach(el => { if (v[el.dataset.f] != null) el.value = v[el.dataset.f]; });
  $$('[data-chips]', s).forEach(el => { $$('.bechip', el).forEach(c => c.remove()); el.insertAdjacentHTML('afterbegin', (v[el.dataset.chips] || []).map(chip).join('')); });
  $$('[data-bestars]', s).forEach(el => setStars(el, v[el.dataset.bestars]));
  $$('[data-rich]', s).forEach(el => { if (v[el.dataset.rich] != null) el.innerHTML = cleanHTML(v[el.dataset.rich]); });
}
async function refreshFiles(){
  const keep = values($('#bedit')), orig = E.orig;
  try { const d = await api('/api/catalog/book/' + E.d.calibre_id); E.d.files = d.files; E.d.formats = d.formats; } catch(e){}
  draw(); restore(keep); E.orig = orig;
  if (C.Catalog) C.Catalog.reload();
}
function fileMenu(anchor, fmt){
  const p = $('#pop'), to = (E.d.convert_to || []).filter(x => x !== fmt);
  p.onclick = p.oninput = p.onkeydown = null;
  p.innerHTML = '<div class="menu fmenu"><div class="fmh">' + esc(fmt) + '</div>' + to.map(t => '<button data-beconv="' + esc(fmt) + '>' + esc(t) + '"><i></i>Convert to ' + esc(t) + '</button>').join('') +
    '<hr><button class="danger" data-berm="' + esc(fmt) + '"><i></i><span>Remove the ' + esc(fmt) + ' file</span></button></div>';
  p.hidden = false; p.style.zIndex = 70;
  if (matchMedia('(max-width:700px)').matches) return;
  const r = anchor.getBoundingClientRect();
  p.style.left = Math.max(8, Math.min(innerWidth - p.offsetWidth - 8, r.right - p.offsetWidth)) + 'px';
  p.style.top = Math.min(r.bottom + 6, innerHeight - p.offsetHeight - 8) + 'px';
}
async function convert(src, to){
  const box = $('#beconv'), cid = E.d.calibre_id;
  if (box) box.innerHTML = '<span class="mute tiny">Converting to ' + esc(to) + '…</span>';
  try {
    const { job } = await api('/api/catalog/book/' + cid + '/convert', { method: 'POST', body: JSON.stringify({ from: src, to }) });
    for (;;) {
      await new Promise(r => setTimeout(r, 2000));
      const j = await api('/api/catalog/jobs/' + job);
      if (j.state === 'done') { toast('Converted to ' + to); break; }
      if (j.state === 'failed') { toast(j.error || 'Calibre couldn’t convert it'); break; }
    }
  } catch(e){ toast(e.message); }
  if (E.d && E.d.calibre_id === cid) refreshFiles();
}

/* ---------- Find details: Hardcover and Calibre's own sources (calibrefind.py) ---------- */
const F = { snap: null, orig: null, results: null, pick: null, seq: 0 };
const far = u => '/api/catalog/coverproxy?u=' + encodeURIComponent(u);          // through the server
function leaveForm(){ F.snap = values($('#bedit')); F.orig = E.orig; }
function backToForm(v){ draw(); restore(v || F.snap); E.orig = F.orig; }
async function find(title, author){
  if (!F.snap) leaveForm();
  const n = ++F.seq, d = E.d;
  sheet('<div class="behead"><h2>Find details</h2><span class="spacer"></span><button class="btn sm" data-be="findback">Back</button></div>' +
    '<div class="bebody one befind"><form class="befq" data-be="findform"><input class="field" name="t" value="' + esc(title || F.snap.title || d.title) + '" aria-label="Title">' +
    '<input class="field" name="a" value="' + esc(author || (F.snap.authors || '').split('&')[0].trim()) + '" aria-label="Author"><button class="btn sm">Search</button></form>' +
    '<div id="befres"><p class="mute">Searching…</p></div></div>');
  try {
    const body = title ? { title, authors: author ? [author] : [] } : {};
    const { job } = await api('/api/catalog/book/' + d.calibre_id + '/find', { method: 'POST', body: JSON.stringify(body) });
    for (;;) {
      await new Promise(r => setTimeout(r, 1500));
      if (n !== F.seq || !E.d) return;
      const j = await api('/api/catalog/jobs/' + job);
      if (j.state === 'running') continue;
      if (j.state === 'failed') throw new Error(j.error || 'Nothing came back');
      F.results = j.results || [];
      list(j.errors || []);
      return;
    }
  } catch(e){ const box = $('#befres'); if (box) box.innerHTML = '<p class="placeholder">' + esc(e.message) + '</p>'; }
}
function list(errs){
  const box = $('#befres'); if (!box) return;
  const yr = x => x.published ? x.published.slice(0, 4) : '';
  box.innerHTML = (F.results.length ? '<div class="befcands">' + F.results.map((x, i) => '<button class="befc" data-befc="' + i + '">' +
      (x.cover ? '<img src="' + far(x.cover) + '" alt="" loading="lazy">' : '<span class="befnc"></span>') +
      '<span class="befct"><b>' + esc(x.title || '') + '</b><span>' + esc((x.authors || []).join(', ')) + '</span>' +
      '<span class="mute tiny">' + [yr(x), x.publisher, x.series ? x.series + (x.series_index ? ' #' + x.series_index : '') : '', x.pages ? x.pages + ' pages' : ''].filter(Boolean).map(esc).join(' · ') + '</span></span>' +
      '<span class="befsrc">' + esc(x.source) + '</span></button>').join('') + '</div>' : '<p class="mute">Nothing found</p>') +
    errs.map(e => '<p class="mute tiny">' + esc(e) + '</p>').join('');
}
// One answer beside what the book has now: tick what to take.
const FIELDS = [['title', 'Title'], ['authors', 'Authors'], ['series', 'Series'], ['tags', 'Tags'], ['publisher', 'Publisher'], ['published', 'Published'], ['languages', 'Languages'], ['identifiers', 'Identifiers'], ['comments', 'Description'], ['#pages', 'Pages']];
function foundVal(x, k){
  if (k === 'authors') return (x.authors || []).join(' & ');
  if (k === 'series') return x.series ? x.series + (x.series_index != null ? ' #' + x.series_index : '') : '';
  if (k === 'tags') return x.tags || [];
  if (k === 'languages') return (x.languages || []).join(', ');
  if (k === 'identifiers') return Object.entries(x.identifiers || {}).map(([a, b]) => a + ': ' + b).join('\n');
  if (k === '#pages') return x.pages ? String(x.pages) : '';
  return x[k] || '';
}
function nowVal(k){
  const v = F.snap;
  if (k === 'series') return v.series ? v.series + (v.series_index ? ' #' + v.series_index : '') : '';
  return v[k] == null ? '' : v[k];
}
function compare(i){
  const x = F.results[i]; F.pick = i;
  const has = k => k !== '#pages' || ('#pages' in F.snap);
  const show = v => Array.isArray(v) ? v.join(', ') : String(v);
  const rows = FIELDS.filter(([k]) => has(k)).map(([k, label]) => {
    const now = nowVal(k), got = foundVal(x, k);
    if (!show(got)) return '';
    let tick = !show(now);
    if (k === 'identifiers') tick = Object.keys(x.identifiers || {}).some(t => !String(now).split('\n').some(l => l.trim().startsWith(t + ':')));
    const same = show(now).trim() === show(got).trim();
    return '<label class="befrow' + (same ? ' same' : '') + '"><input type="checkbox" data-take="' + esc(k) + '"' + (tick && !same ? ' checked' : '') + (same ? ' disabled' : '') + '><span class="befl">' + esc(label) +
      '</span><span class="befnow">' + (show(now) ? esc(show(now)) : '<i class="mute">—</i>') + '</span><span class="befgot">' + esc(show(got)) + '</span></label>';
  }).join('');
  sheet('<div class="behead"><h2>' + esc(x.source) + '</h2><span class="spacer"></span><button class="btn sm" data-be="findlist">Back</button><button class="btn sm primary" data-be="take">Use these</button></div>' +
    '<div class="bebody one befind">' +
    (x.cover ? '<div class="befcov"><figure>' + (E.d.cover ? '<img src="/api/cover/' + encodeURIComponent(E.d.id) + '?v=' + (E.coverV || 0) + '" alt="">' : '<span class="befnc"></span>') + '<figcaption class="mute tiny">Now</figcaption></figure>' +
      '<figure><img src="' + far(x.cover) + '" alt=""><figcaption><label><input type="checkbox" data-take="cover"' + (E.d.cover ? '' : ' checked') + '> Use this cover</label></figcaption></figure></div>' : '') +
    '<div class="befhead"><span></span><span>Now</span><span>Found</span></div>' + rows + '</div>');
}
async function take(){
  const x = F.results[F.pick], v = Object.assign({}, F.snap);
  const on = k => { const c = $('#bedit [data-take="' + CSS.escape(k) + '"]'); return c && c.checked; };
  if (on('title')) v.title = x.title;
  if (on('authors')) v.authors = (x.authors || []).join(' & ');
  if (on('series')) { v.series = x.series || ''; v.series_index = x.series_index != null ? String(x.series_index) : ''; }
  if (on('tags')) v.tags = [...new Set([...(v.tags || []), ...(x.tags || [])])];
  if (on('publisher')) v.publisher = x.publisher || '';
  if (on('published')) v.published = (x.published || '').slice(0, 10);
  if (on('languages')) v.languages = (x.languages || []).join(', ');
  if (on('comments')) v.comments = x.comments || '';
  if (on('#pages')) v['#pages'] = String(x.pages || '');
  if (on('identifiers')) {
    const have = {}; String(v.identifiers || '').split('\n').forEach(l => { const m = l.match(/^\s*([^:\s]+)\s*:\s*(.+?)\s*$/); if (m) have[m[1]] = m[2]; });
    for (const [a, b] of Object.entries(x.identifiers || {})) if (!have[a]) have[a] = b;
    v.identifiers = Object.entries(have).map(([a, b]) => a + ': ' + b).join('\n');
  }
  const cov = on('cover') && x.cover;
  backToForm(v); F.snap = null;
  if (cov) await cover(JSON.stringify({ url: x.cover }), 'application/json');
  toast('Details filled in');
}

/* ---------- the chips, the stars ---------- */
function addTyped(s){ $$('.bechipin', s).forEach(i => { if (i.value.trim()) addChip(i); }); }
function addChip(i){
  const box = i.closest('[data-chips]'), have = $$('.bechip', box).map(c => c.dataset.v.toLowerCase());
  i.value.split(',').map(x => x.trim()).filter(Boolean).forEach(v => { if (!have.includes(v.toLowerCase())) { i.insertAdjacentHTML('beforebegin', chip(v)); have.push(v.toLowerCase()); } });
  i.value = '';
}
function setStars(el, v){
  el.dataset.v = v || '';
  $$('[data-star]', el).forEach(b => { const n = +b.dataset.star; b.className = (v || 0) >= n ? 'on' : (v || 0) >= n - .5 ? 'half' : ''; });
}

/* ---------- events ---------- */
document.addEventListener('click', e => {
  const t = e.target; if (!t.closest) return;
  const ed = t.closest('[data-act="bookedit"]'); if (ed) { open(ed.dataset.id); return; }
  if (!t.closest('#bedit') && !t.closest('#pop')) { if (t.closest('#beshade')) close(); return; }
  const st = t.closest('[data-star]');
  if (st) {     // the left half of a star is half a star
    const el = st.closest('[data-bestars]'), r = st.getBoundingClientRect(), n = +st.dataset.star - (e.clientX && e.clientX < r.left + r.width / 2 ? .5 : 0);
    setStars(el, +el.dataset.v === n ? null : n); const no = $('[data-f2="norating"]'); if (no) no.checked = false; return;
  }
  if (t.closest('[data-unchip]')) { t.closest('.bechip').remove(); return; }
  const fc = t.closest('[data-befc]'); if (fc) { compare(+fc.dataset.befc); return; }
  const cv = t.closest('[data-beconv]'); if (cv) { $('#pop').hidden = true; const [a, b] = cv.dataset.beconv.split('>'); convert(a, b); return; }
  const rm = t.closest('[data-berm]');
  if (rm) { $('#pop').hidden = true; const fmt = rm.dataset.berm;
    if (!confirm('Remove the ' + fmt + ' file from Calibre?')) return;
    api('/api/catalog/book/' + E.d.calibre_id + '/files/' + encodeURIComponent(fmt), { method: 'DELETE' }).then(() => { toast(fmt + ' removed'); refreshFiles(); }).catch(err => toast(err.message));
    return; }
  const b = t.closest('[data-be]'); if (!b) { const box = t.closest('.bechips'); if (box) $('.bechipin', box).focus(); return; }
  const k = b.dataset.be;
  if (k === 'cancel') close();
  else if (k === 'find') find();
  else if (k === 'remove') { const d = E.d; remove([d]).then(ok => { if (ok) { close(true); if (C.S.route[0] === 'book') location.hash = 'catalog'; } }); }
  else if (k === 'merge') doMerge();
  else if (k === 'findback') { F.seq++; backToForm(); F.snap = null; }
  else if (k === 'findlist') sheetList(F.results);
  else if (k === 'take') take();
  else if (k === 'save') save();
  else if (k === 'coverurl') { const u = (prompt('The cover’s address') || '').trim(); if (u) cover(JSON.stringify({ url: u }), 'application/json'); }
  else if (k === 'filemenu') { e.stopPropagation(); fileMenu(b, b.dataset.fmt); }
});
document.addEventListener('submit', e => {
  const f = e.target.closest && e.target.closest('[data-be="findform"]'); if (!f) return;
  e.preventDefault(); find(f.t.value.trim(), f.a.value.trim());
});
// Back from one answer to the list, without asking again.
function sheetList(results){
  sheet('<div class="behead"><h2>Find details</h2><span class="spacer"></span><button class="btn sm" data-be="findback">Back</button></div>' +
    '<div class="bebody one befind"><form class="befq" data-be="findform"><input class="field" name="t" value="' + esc(F.snap.title || '') + '" aria-label="Title">' +
    '<input class="field" name="a" value="' + esc((F.snap.authors || '').split('&')[0].trim()) + '" aria-label="Author"><button class="btn sm">Search</button></form><div id="befres"></div></div>');
  F.results = results; list([]);
}
document.addEventListener('change', e => {
  const t = e.target;
  if (t.matches && t.matches('[data-be="coverfile"]') && t.files[0]) { const f = t.files[0]; cover(f, f.type || 'application/octet-stream'); t.value = ''; }
  else if (t.matches && t.matches('[data-be="addfile"]') && t.files[0]) {
    const f = t.files[0], box = $('#beconv'); t.value = '';
    if (box) box.innerHTML = '<span class="mute tiny">Adding ' + esc(f.name) + '…</span>';
    api('/api/catalog/book/' + E.d.calibre_id + '/files?name=' + encodeURIComponent(f.name), { method: 'POST', body: f, headers: { 'Content-Type': 'application/octet-stream' } })
      .then(r => { toast(r.format + ' added'); refreshFiles(); }).catch(err => { toast(err.message); if (box) box.innerHTML = ''; });
  }
  else if (t.classList && t.classList.contains('bechipin') && t.value.trim()) addChip(t);
});
document.addEventListener('input', e => {
  const t = e.target;
  // A tag picked from the list goes in at once; typing waits for a comma or Enter.
  if (t.classList && t.classList.contains('bechipin')) {
    const opts = t.list ? [...t.list.options].map(o => o.value) : [];
    if (t.value.includes(',') || (e.inputType === 'insertReplacementText' || !e.inputType) && opts.includes(t.value)) addChip(t);
  }
});
document.addEventListener('keydown', e => {
  const s = $('#bedit'); if (!s || s.hidden) return;
  const t = e.target;
  if (t.classList && t.classList.contains('bechipin')) {
    if (e.key === 'Enter' && t.value.trim()) { e.preventDefault(); addChip(t); return; }
    if (e.key === 'Backspace' && !t.value) { const last = $$('.bechip', t.closest('[data-chips]')).pop(); if (last) last.remove(); return; }
  }
  if (e.key === 'Escape') { e.preventDefault(); e.stopImmediatePropagation(); if (!$('#pop').hidden) $('#pop').hidden = true; else close(); }
  else if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) { e.preventDefault(); save(); }
}, true);

/* ---------- tidying: merge copies of one book, remove books ---------- */
// Removed books go to Calibre's trash, which keeps them for 14 days.
async function remove(books){
  const n = books.length, hl = books.reduce((s, b) => s + (b.highlights || 0), 0);
  const what = n === 1 ? '“' + books[0].title + '”' : n + ' books';
  if (!confirm('Remove ' + what + ' from Calibre?' + (hl ? ' ' + (n === 1 ? 'It has' : 'They have') + ' ' + hl + ' highlight' + (hl === 1 ? '' : 's') + ' in Daf.' : ''))) return false;
  try {
    await api('/api/catalog/remove', { method: 'POST', body: JSON.stringify({ ids: books.map(b => b.calibre_id) }) });
    toast(n === 1 ? 'Removed' : n + ' books removed'); after(); return true;
  } catch(e){ toast(e.message); return false; }
}
// Which copy stays: the one with a cover and the most files, then the first added.
function merge(books){
  const best = books.slice().sort((a, b) => (b.cover - a.cover) || ((b.formats || []).length - (a.formats || []).length) || String(a.added).localeCompare(String(b.added)))[0];
  E.merging = books; E.d = null; E.ids = null; E.orig = null;
  sheet('<div class="behead"><h2>Merge ' + books.length + ' books</h2><span class="spacer"></span><button class="btn sm" data-be="cancel">Cancel</button><button class="btn sm primary" data-be="merge">Merge</button></div>' +
    '<div class="bebody one"><div class="bemerge" role="radiogroup" aria-label="Keep">' + books.map(b => '<label class="bemrow"><input type="radio" name="bekeep" value="' + b.calibre_id + '"' + (b === best ? ' checked' : '') + '>' +
      (b.cover ? '<img src="/api/cover/' + encodeURIComponent(b.id) + '?v=' + (b.cover_v || 0) + '" alt="">' : '<span class="befnc"></span>') +
      '<span class="befct"><b>' + esc(b.title) + '</b><span>' + esc((b.authors || []).join(' & ')) + '</span><span class="mute tiny">' + [(b.formats || []).join(', ') || 'No file', b.added, b.highlights ? b.highlights + ' highlights' : ''].filter(Boolean).map(esc).join(' · ') + '</span></span></label>').join('') +
    '</div></div>');
}
async function doMerge(){
  const books = E.merging || [], keep = +(($('#bedit input[name=bekeep]:checked') || {}).value || 0);
  if (!keep) return;
  const btn = $('#bedit [data-be="merge"]'); btn.disabled = true; btn.textContent = 'Merging…';
  try {
    await api('/api/catalog/merge', { method: 'POST', body: JSON.stringify({ keep, ids: books.map(b => b.calibre_id) }) });
    toast('Merged into one'); E.merging = null; close(true); after();
  } catch(e){ toast(e.message); btn.disabled = false; btn.textContent = 'Merge'; }
}

// Calibre's trash: the books removed lately, each with Put back.
async function trash(priv){
  E.d = E.ids = E.orig = null;
  sheet('<div class="behead"><h2>Calibre’s trash</h2><span class="spacer"></span><button class="btn sm" data-be="cancel">Close</button></div><div class="bebody one"><p class="mute">Loading…</p></div>');
  let r;
  try { r = await api('/api/catalog/trash' + (priv ? '?private=1' : '')); } catch(e){ toast(e.message); close(true); return; }
  const when = t => new Date(t * 1000).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
  const body = $('#bedit .bebody'); if (!body) return;
  body.innerHTML = r.books.length ? '<div class="betrash">' + r.books.map(b => '<div class="betrow"><span class="befct"><b>' + esc(b.title) + '</b><span class="mute tiny">' + esc(b.author || '') + ' · ' + when(b.removed) + '</span></span>' +
    '<button class="btn sm" data-betrash="' + b.id + '">Put back</button></div>').join('') + '</div>' : '<p class="mute">Nothing in the trash.</p>';
}
document.addEventListener('click', e => {
  const b = e.target.closest && e.target.closest('[data-betrash]'); if (!b) return;
  b.disabled = true;
  api('/api/catalog/trash/restore', { method: 'POST', body: JSON.stringify({ ids: [+b.dataset.betrash] }) })
    .then(() => { b.closest('.betrow').remove(); toast('Back in Calibre'); after(); })
    .catch(err => { toast(err.message); b.disabled = false; });
});

/* ---------- Tags, authors and series: rename, combine, delete, across the library ---------- */
const M = { field: 'tags', data: null, q: '', sel: new Set(), editing: null };
async function items(field){
  E.d = E.ids = E.orig = null;
  M.field = field || M.field; M.sel.clear(); M.editing = null;
  if (!$('#bedit') || $('#bedit').hidden || !$('#bedit .bemgr')) sheet('<div class="behead"><h2>Tags, authors and series</h2><span class="spacer"></span><button class="btn sm" data-be="cancel">Close</button></div><div class="bebody one bemgr"><p class="mute">Loading…</p></div>');
  try { M.data = await api('/api/catalog/items?field=' + encodeURIComponent(M.field)); } catch(e){ toast(e.message); return; }
  drawItems();
}
function drawItems(){
  const box = $('#bedit .bemgr'); if (!box || !M.data) return;
  const d = M.data, q = M.q.trim().toLowerCase(), count = Object.fromEntries(d.items.map(x => [x.name, x.count]));
  const shown = d.items.filter(x => !q || x.name.toLowerCase().includes(q));
  const tabs = '<div class="bemtabs" role="tablist">' + d.fields.map(f => '<button role="tab" class="' + (f.key === M.field ? 'on' : '') + '" data-bemtab="' + esc(f.key) + '">' + esc(f.label) + '</button>').join('') + '</div>';
  const alike = d.alike.filter(g => !q || g.some(n => n.toLowerCase().includes(q)));
  const by = g => g.slice().sort((a, b) => (count[b] || 0) - (count[a] || 0));
  let h = tabs + '<input class="field bemq" type="search" placeholder="Find a name" value="' + esc(M.q) + '" data-bemq autocomplete="off">';
  if (alike.length) h += '<h3>Look alike</h3><div class="bemalike">' + alike.map(g => { const s = by(g);
    return '<div class="bemarow"><span>' + s.map(n => esc(n) + ' <b>' + (count[n] || 0) + '</b>').join(' · ') + '</span><select class="field sm" data-bemto aria-label="Into">' + s.map(n => '<option>' + esc(n) + '</option>').join('') + '</select>' +
      '<button class="btn sm" data-bemcombine="' + esc(JSON.stringify(g)) + '">Combine</button></div>'; }).join('') + '</div>';
  h += '<h3>' + shown.length + ' ' + esc((d.fields.find(f => f.key === M.field) || {}).label || '').toLowerCase() + '</h3><div class="bemlist">' + shown.map(x =>
    '<div class="bemrow' + (M.sel.has(x.name) ? ' sel' : '') + '"><input type="checkbox" data-bemsel="' + esc(x.name) + '"' + (M.sel.has(x.name) ? ' checked' : '') + ' aria-label="Choose">' +
    (M.editing === x.name ? '<input class="field sm bemedit" data-bemedit="' + esc(x.name) + '" value="' + esc(x.name) + '">' : '<button class="bemname" data-bemren="' + esc(x.name) + '">' + esc(x.name) + '</button>') +
    '<button class="bemcount" data-bemshow="' + esc(x.name) + '">' + x.count + '</button></div>').join('') + '</div>';
  if (M.sel.size) h += '<div class="bembar"><b>' + M.sel.size + ' chosen</b><span class="spacer"></span><button class="btn sm" data-bem="none">Clear</button>' +
    (M.sel.size > 1 ? '<button class="btn sm" data-bem="combine">Combine</button>' : '') + (M.field !== 'authors' ? '<button class="btn sm danger" data-bem="delete">Delete</button>' : '') + '</div>';
  const keepFocus = document.activeElement && document.activeElement.matches && document.activeElement.matches('[data-bemq]');
  box.innerHTML = h;
  if (keepFocus) { const i = $('[data-bemq]', box); i.focus(); i.setSelectionRange(i.value.length, i.value.length); }
  const ed = $('[data-bemedit]', box); if (ed) { ed.focus(); ed.select(); }
}
async function renameItems(names, to){
  to = (to || '').trim(); names = names.filter(n => n !== to);
  if (!to || !names.length) { M.editing = null; drawItems(); return; }
  const into = M.data.items.some(x => x.name === to);
  if (into && !confirm('Combine ' + names.map(n => '“' + n + '”').join(', ') + ' into “' + to + '”?')) return;
  try {
    await api('/api/catalog/items/rename', { method: 'POST', body: JSON.stringify({ field: M.field, from: names, to }) });
    toast(into ? 'Combined' : 'Renamed'); M.sel.clear(); M.editing = null; items(M.field); after();
  } catch(e){ toast(e.message); }
}
document.addEventListener('click', e => {
  const t = e.target; if (!t.closest || !t.closest('#bedit .bemgr')) return;
  const tab = t.closest('[data-bemtab]'); if (tab) { M.q = ''; items(tab.dataset.bemtab); return; }
  const cb = t.closest('[data-bemcombine]'); if (cb) { const g = JSON.parse(cb.dataset.bemcombine), to = cb.parentNode.querySelector('[data-bemto]').value; renameItems(g, to); return; }
  const rn = t.closest('[data-bemren]'); if (rn) { M.editing = rn.dataset.bemren; drawItems(); return; }
  const sh = t.closest('[data-bemshow]'); if (sh) { const f = M.field, n = sh.dataset.bemshow; close(true); if (C.Catalog) C.Catalog.search(f + ':"=' + n.replace(/"/g, '') + '"'); return; }
  const k = t.closest('[data-bem]'); if (!k) return;
  const names = [...M.sel];
  if (k.dataset.bem === 'none') { M.sel.clear(); drawItems(); }
  else if (k.dataset.bem === 'combine') {
    const most = names.slice().sort((a, b) => (M.data.items.find(x => x.name === b) || {}).count - (M.data.items.find(x => x.name === a) || {}).count)[0];
    const to = prompt('Combine into', most); if (to) renameItems(names, to);
  }
  else if (k.dataset.bem === 'delete') {
    if (!confirm('Delete ' + (names.length === 1 ? '“' + names[0] + '”' : names.length + ' names') + ' from every book that has ' + (names.length === 1 ? 'it' : 'them') + '?')) return;
    api('/api/catalog/items/delete', { method: 'POST', body: JSON.stringify({ field: M.field, names }) })
      .then(() => { toast('Deleted'); M.sel.clear(); items(M.field); after(); }).catch(err => toast(err.message));
  }
});
document.addEventListener('change', e => {
  const c = e.target.closest && e.target.closest('[data-bemsel]'); if (!c) return;
  if (c.checked) M.sel.add(c.dataset.bemsel); else M.sel.delete(c.dataset.bemsel);
  drawItems();
});
document.addEventListener('input', e => { if (e.target.matches && e.target.matches('[data-bemq]')) { M.q = e.target.value; drawItems(); } });
document.addEventListener('keydown', e => {
  const t = e.target; if (!t.matches || !t.matches('[data-bemedit]')) return;
  if (e.key === 'Enter') { e.preventDefault(); e.stopPropagation(); renameItems([t.dataset.bemedit], t.value); }
  else if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); M.editing = null; drawItems(); }
}, true);
document.addEventListener('focusout', e => { const t = e.target; if (t.matches && t.matches('[data-bemedit]') && M.editing) setTimeout(() => { if (M.editing === t.dataset.bemedit && !document.activeElement.matches('[data-bemedit]')) { M.editing = null; drawItems(); } }, 150); });

/* ---------- Find details for many books: only what each is missing, from answers surely the same book ---------- */
const FILL = [['publisher', 'Publisher'], ['published', 'Published'], ['comments', 'Description'], ['tags', 'Tags'], ['series', 'Series'], ['languages', 'Languages'], ['identifiers', 'Identifiers'], ['#pages', 'Pages'], ['cover', 'Cover']];
const L = { books: null, res: null, seq: 0 };
function fill(books){
  E.d = E.ids = E.orig = null; L.books = books; L.res = null; L.seq++;
  sheet('<div class="behead"><h2>Find details for ' + books.length + ' book' + (books.length === 1 ? '' : 's') + '</h2><span class="spacer"></span><button class="btn sm" data-be="cancel">Cancel</button><button class="btn sm primary" data-befill="start">Look up</button></div>' +
    '<div class="bebody one befill"><h3>Fill in</h3><div class="befields">' + FILL.map(([k, l]) => '<label><input type="checkbox" data-fillf="' + esc(k) + '" checked> ' + esc(l) + '</label>').join('') + '</div>' +
    '<div class="bebooks">' + books.map(b => '<div class="mute tiny">' + esc(b.title) + '</div>').join('') + '</div></div>');
}
async function fillStart(){
  const fields = $$('#bedit [data-fillf]').filter(c => c.checked).map(c => c.dataset.fillf);
  if (!fields.length) return;
  const n = ++L.seq, body = $('#bedit .befill'), head = $('#bedit .behead');
  head.innerHTML = '<h2>Find details for ' + L.books.length + ' book' + (L.books.length === 1 ? '' : 's') + '</h2><span class="spacer"></span><button class="btn sm" data-be="cancel">Cancel</button>';
  body.innerHTML = '<p class="mute" id="befprog">Looking up…</p>';
  try {
    const { job } = await api('/api/catalog/fill', { method: 'POST', body: JSON.stringify({ ids: L.books.map(b => b.calibre_id), fields }) });
    for (;;) {
      await new Promise(r => setTimeout(r, 1500));
      if (n !== L.seq || !$('#bedit .befill')) return;
      const j = await api('/api/catalog/jobs/' + job);
      const pr = $('#befprog'); if (pr) pr.innerHTML = 'Looking up ' + Math.min(j.done + 1, j.total) + ' of ' + j.total + '… ' + C.bar(100 * j.done / Math.max(1, j.total));
      if (j.state === 'running') continue;
      if (j.state === 'failed') throw new Error(j.error || 'Nothing came back');
      L.res = j.books; drawFill(); return;
    }
  } catch(e){ const b = $('#bedit .befill'); if (b) b.innerHTML = '<p class="placeholder">' + esc(e.message) + '</p>'; }
}
const showVal = (k, v) => k === 'comments' ? String(v).replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim().slice(0, 140) + (String(v).length > 140 ? '…' : '') : Array.isArray(v) ? v.join(', ') : k === 'identifiers' ? Object.entries(v).map(([a, b]) => a + ': ' + b).join(', ') : String(v);
function drawFill(){
  const body = $('#bedit .befill'), head = $('#bedit .behead'); if (!body) return;
  const some = L.res.filter(b => Object.keys(b.fill).length), none = L.res.filter(b => !Object.keys(b.fill).length);
  head.innerHTML = '<h2>' + some.length + ' of ' + L.res.length + ' with something to fill in</h2><span class="spacer"></span><button class="btn sm" data-be="cancel">Cancel</button>' +
    (some.length ? '<button class="btn sm primary" data-befill="save">Save</button>' : '');
  body.innerHTML = some.map(b => '<label class="befrow2"><input type="checkbox" data-fillbook="' + b.id + '" checked>' +
      (b.fill.cover ? '<img src="/api/catalog/coverproxy?u=' + encodeURIComponent(b.fill.cover) + '" alt="" loading="lazy">' : '<span class="befnc"></span>') +
      '<span class="befct"><b>' + esc(b.title) + '</b><span class="mute tiny">' + esc((b.authors || []).join(' & ')) + '</span>' +
      '<span class="befills">' + Object.entries(b.fill).filter(([k]) => k !== 'cover' && k !== 'series_index').map(([k, v]) => '<span class="befx" data-fillx="' + b.id + '|' + esc(k) + '" role="checkbox" aria-checked="true" tabindex="0"><i>' + esc((FILL.find(f => f[0] === k) || [k, k])[1]) + '</i> ' + esc(showVal(k, v)) + (k === 'series' && b.fill.series_index != null ? ' #' + esc(b.fill.series_index) : '') + '</span>').join('') +
      (b.fill.cover ? '<span class="befx" data-fillx="' + b.id + '|cover" role="checkbox" aria-checked="true" tabindex="0"><i>Cover</i></span>' : '') + '</span><span class="mute tiny">' + esc([...new Set(Object.values(b.from))].join(', ')) + '</span></span></label>').join('') +
    (none.length ? '<h3>Nothing to fill in</h3>' + none.map(b => '<div class="befnone"><b>' + esc(b.title) + '</b> <span class="mute tiny">' + (b.found ? 'Nothing new' : 'No sure match') + '</span></div>').join('') : '');
}
async function fillSave(){
  // A line taken out (tapped, so it's crossed out) stays as the book has it.
  $$('#bedit .befx.off').forEach(x => { const [id, k] = x.dataset.fillx.split('|'), b = L.res.find(r => String(r.id) === id); if (b) { delete b.fill[k]; if (k === 'series') delete b.fill.series_index; } });
  const chosen = L.res.filter(b => { const c = $('#bedit [data-fillbook="' + b.id + '"]'); return c && c.checked && Object.keys(b.fill).length; });
  if (!chosen.length) return;
  const head = $('#bedit .behead'); head.innerHTML = '<h2>Saving ' + chosen.length + ' books…</h2>';
  try {
    const { job } = await api('/api/catalog/fill/apply', { method: 'POST', body: JSON.stringify({ books: chosen.map(b => ({ id: b.id, fill: b.fill })) }) });
    for (;;) {
      await new Promise(r => setTimeout(r, 1500));
      const j = await api('/api/catalog/jobs/' + job);
      const h = $('#bedit .behead h2'); if (h) h.textContent = 'Saving ' + j.done + ' of ' + j.total + ' books…';
      if (j.state !== 'running') { toast((j.total - j.failed.length) + ' books filled in' + (j.failed.length ? '; ' + j.failed.length + ' couldn’t be' : '')); break; }
    }
  } catch(e){ toast(e.message); }
  close(true); after();
}
document.addEventListener('click', e => {
  const x = e.target.closest && e.target.closest('[data-fillx]');
  if (x) { e.preventDefault(); x.classList.toggle('off'); x.setAttribute('aria-checked', !x.classList.contains('off')); return; }
  const b = e.target.closest && e.target.closest('[data-befill]'); if (!b) return;
  if (b.dataset.befill === 'start') fillStart(); else if (b.dataset.befill === 'save') fillSave();
});

C.BookEdit = { open, bulk, close, merge, remove, trash, items, fill };
})();
