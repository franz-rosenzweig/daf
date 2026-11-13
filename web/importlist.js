/* Import list (All books → ⋯ → Import list), Daf's take on Calibre's Import List plugin
   (importlist.py). One sheet, three steps: the list (pasted text, a CSV file, a web page, one of my
   Hardcover lists), the matches (each row's title and authors can be changed, its book picked by hand
   or set to none, the row unticked), and what to do: the ones Calibre doesn't have as empty books,
   with a tag, Read's To read choice and a shelf; the ones it has, a tag and a shelf. Nothing changes
   until Import. C.ImportList.open() */
(() => {
'use strict';
const C = window.DafCore, { api, esc, toast, $, $$ } = C;
const store = { get(k, d){ try { const v = localStorage.getItem('daf.' + k); return v == null ? d : JSON.parse(v); } catch(e){ return d; } }, set(k, v){ try { localStorage.setItem('daf.' + k, JSON.stringify(v)); } catch(e){} } };
const FORMS = [['auto', 'Automatic'], ['by', 'Title by Author'], ['author-title', 'Author - Title'], ['title-author', 'Title - Author'],
  ['slash', 'Title / Author'], ['paren', 'Title (Author)'], ['columns', 'Columns'], ['pattern', 'Pattern']];
const FIELDS = [['title', 'Title'], ['authors', 'Authors'], ['series', 'Series'], ['series_index', 'Number'], ['isbn', 'ISBN'], ['published', 'Published']];
const DELIMS = [[',', 'Comma'], ['\t', 'Tab'], [';', 'Semicolon'], ['|', 'Bar']];
const HOW = { identical: 'Exact', similar: 'Close', fuzzy: 'Loose', title: 'Title', isbn: 'ISBN', hardcover: 'Hardcover', goodreads: 'Goodreads', amazon: 'Amazon', hand: 'Picked' };
const OPTS = { add: true, read: false, add_tag: '', add_shelf: '', have_tag: '', have_shelf: '' };
const L = { meta: null, tab: store.get('importlistTab', 'text'), step: 'in', form: 'auto', text: '', pattern: '', file: null, fileName: '',
  table: null, tsrc: null, url: '', site: '', xp: {}, hc: '', rows: [], filter: 'all', find: null, hits: null, err: '', result: null, busy: false,
  opts: Object.assign({}, OPTS, store.get('importlist', {}), { add_shelf_new: '', have_shelf_new: '' }) };

/* ---------- the sheet ---------- */
function sheet(html){
  let s = $('#ilsheet');
  if (!s) { document.body.insertAdjacentHTML('beforeend', '<div class="beshade" id="ilshade"></div><div class="besheet ilsheet" id="ilsheet" role="dialog" aria-modal="true" aria-label="Import list"></div>'); s = $('#ilsheet'); }
  s.innerHTML = html; s.hidden = false; $('#ilshade').hidden = false;
  document.body.classList.add('beopen');
  return s;
}
function close(force){
  if (!force && L.rows.length && L.step !== 'done' && !confirm('Leave without importing?')) return;
  const s = $('#ilsheet'); if (s) s.hidden = true;
  const sh = $('#ilshade'); if (sh) sh.hidden = true;
  if (!$('#bedit') || $('#bedit').hidden) document.body.classList.remove('beopen');
  L.rows = []; L.table = null; L.file = null; L.fileName = ''; L.busy = false; L.find = null;
}
const head = (title, btns) => '<div class="behead"><h2>' + esc(title) + '</h2><span class="spacer"></span>' + btns + '</div>';
const btn = (act, label, cls, off) => '<button class="btn sm' + (cls ? ' ' + cls : '') + '" data-il="' + act + '"' + (off ? ' disabled' : '') + '>' + label + '</button>';
const row = (label, ctl, cls) => '<div class="berow' + (cls ? ' ' + cls : '') + '"><span>' + esc(label) + '</span><div class="bectl">' + ctl + '</div></div>';
const select = (attr, list, val) => '<select class="field" ' + attr + '>' + list.map(([v, l]) => '<option value="' + esc(v) + '"' + (String(v) === String(val) ? ' selected' : '') + '>' + esc(l) + '</option>').join('') + '</select>';
const errLine = () => L.err ? '<p class="placeholder ilerr">' + esc(L.err) + '</p>' : '';

async function open(){
  Object.assign(L, { step: 'in', rows: [], table: null, filter: 'all', find: null, err: '', result: null, busy: false });
  sheet(head('Import list', btn('cancel', 'Cancel')) + '<div class="bebody one ilbody"><p class="mute">Loading…</p></div>');
  try { L.meta = await api('/api/catalog/importlist'); } catch(e){ close(true); toast(e.message); return; }
  if (L.tab === 'hc' && !L.meta.hardcover) L.tab = 'text';
  draw();
}
function draw(){
  if (!$('#ilsheet') || $('#ilsheet').hidden) return;
  ({ in: drawIn, cols: drawCols, match: drawMatch, do: drawDo, busy: drawBusy, done: drawDone })[L.step]();
}
function drawBusy(){ sheet(head(L.busyText || 'Working…', '') + '<div class="bebody one ilbody">' + (L.busyPct ? '<p>' + C.bar(L.busyPct) + '</p>' : '') + '</div>'); }

/* ---------- 1. the list ---------- */
function drawIn(){
  const tabs = [['text', 'Text'], ['file', 'File'], ['web', 'Web page']].concat(L.meta.hardcover ? [['hc', 'Hardcover']] : []);
  let h = '<div class="bemtabs" role="tablist">' + tabs.map(([k, l]) => '<button role="tab" aria-selected="' + (L.tab === k) + '" class="' + (L.tab === k ? 'on' : '') + '" data-iltab="' + k + '">' + l + '</button>').join('') + '</div>' + errLine();
  if (L.tab === 'text') {
    h += '<textarea class="field iltext" data-ilf="text" rows="12" spellcheck="false" autocapitalize="off" aria-label="List">' + esc(L.text) + '</textarea>' +
      row('Form', select('data-ilf="form"', FORMS, L.form)) +
      (L.form === 'pattern' ? row('Pattern', '<input class="field mono" data-ilf="pattern" value="' + esc(L.pattern) + '" spellcheck="false" autocapitalize="off" autocomplete="off" placeholder="(?P<title>.+) by (?P<authors>.+)">') : '');
  } else if (L.tab === 'file') {
    h += '<div class="ilfile"><label class="btn befile">Choose a file<input type="file" accept=".csv,.tsv,.tab,.txt,text/csv,text/tab-separated-values,text/plain" data-ilfile hidden></label>' +
      (L.fileName ? '<span class="mute">' + esc(L.fileName) + '</span>' : '') + '</div>';
  } else if (L.tab === 'web') {
    const groups = {};
    L.meta.sites.forEach(s => { const g = s.name.split(':')[0]; (groups[g] = groups[g] || []).push(s); });
    h += row('Site', '<select class="field" data-ilf="site"><option value="">—</option>' + Object.entries(groups).map(([g, ss]) => '<optgroup label="' + esc(g) + '">' +
        ss.map(s => '<option value="' + esc(s.name) + '"' + (s.name === L.site ? ' selected' : '') + '>' + esc(s.name.slice(g.length + 1).trim() || s.name) + '</option>').join('') + '</optgroup>').join('') + '</select>') +
      row('Address', '<input class="field" type="url" inputmode="url" data-ilf="url" value="' + esc(L.url) + '" spellcheck="false" autocapitalize="off" autocomplete="off" placeholder="https://">') +
      '<details class="ilxp"' + (Object.values(L.xp).some(Boolean) ? ' open' : '') + '><summary>XPath</summary><div class="ilxpb">' +
      [['rows', 'Rows']].concat(FIELDS).map(([k, l]) => row(l, '<input class="field mono" data-ilxp="' + k + '" value="' + esc(L.xp[k] || '') + '" spellcheck="false" autocapitalize="off" autocomplete="off">')).join('') + '</div></details>';
  } else {
    h += '<div class="illists" role="radiogroup">' + L.meta.hardcover.map(x => '<label class="ilpick"><input type="radio" name="ilhc" value="' + esc(x.key) + '"' + (x.key === L.hc ? ' checked' : '') + '>' +
      '<span>' + esc(x.name) + '</span>' + (x.count != null ? '<b>' + x.count + '</b>' : '') + '</label>').join('') + '</div>';
  }
  sheet(head('Import list', btn('cancel', 'Cancel') + (L.tab === 'file' && !L.file ? '' : btn('read', 'Next', 'primary'))) + '<div class="bebody one ilbody">' + h + '</div>');
}
function source(){
  if (L.tab === 'text') return L.text.trim() ? { source: 'text', text: L.text, form: L.form, pattern: L.pattern } : null;
  if (L.tab === 'web') {
    if (!L.url.trim()) return null;
    const site = L.meta.sites.find(s => s.name === L.site && s.url === L.url.trim()), xp = Object.values(L.xp).some(Boolean) ? L.xp : null;
    return { source: 'web', url: L.url.trim(), config: site ? site.config : null, xpaths: xp };
  }
  if (L.tab === 'hc') return L.hc ? { source: 'hardcover', list: L.hc } : null;
  return L.file ? { source: 'table', data: L.file } : null;
}
async function read(body){
  if (!body || L.busy) return;
  L.busy = true; L.err = ''; const back = L.step;
  L.step = 'busy'; L.busyText = 'Reading…'; L.busyPct = 0; draw();
  let r;
  try { r = await api('/api/catalog/importlist/read', { method: 'POST', body: JSON.stringify(body) }); }
  catch(e){ L.busy = false; L.err = e.message; L.step = back; draw(); return; }
  L.busy = false;
  if (r.table) { L.table = r.table; L.tsrc = body.source === 'text' ? { source: 'table', text: body.text } : { source: 'table', data: body.data }; L.step = 'cols'; draw(); return; }
  if (!r.rows.length) { L.err = 'No books in it'; L.step = back === 'cols' ? 'cols' : 'in'; draw(); return; }
  if (body.source !== 'table') L.table = null;
  L.rows = r.rows.map(x => Object.assign(x, { on: true })); L.filter = 'all'; L.find = null;
  L.step = 'match'; draw();
}
const b64 = buf => { let s = ''; const u = new Uint8Array(buf); for (let i = 0; i < u.length; i += 0x8000) s += String.fromCharCode.apply(null, u.subarray(i, i + 0x8000)); return btoa(s); };

/* ---------- 1b. a table's columns ---------- */
function drawCols(){
  const t = L.table, n = Math.max(1, ...t.rows.map(r => r.length));
  const name = i => (t.headings && t.rows[0] && t.rows[0][i] ? t.rows[0][i] : 'Column ' + (i + 1));
  const cols = [['', '—']].concat([...Array(n).keys()].map(i => [String(i), name(i)]));
  const h = errLine() +
    row('Separator', select('data-ilt="delimiter"', DELIMS, t.delimiter)) +
    row('', '<label class="ilck"><input type="checkbox" data-ilt="headings"' + (t.headings ? ' checked' : '') + '>First row is headings</label>') +
    FIELDS.map(([k, l]) => row(l, select('data-ilcol="' + k + '"', cols, t.columns[k] == null ? '' : t.columns[k]))).join('') +
    '<div class="ilprev"><table>' + t.rows.slice(0, 10).map((r, i) => '<tr' + (i === 0 && t.headings ? ' class="ilhead"' : '') + '>' +
      [...Array(n).keys()].map(c => '<td>' + esc(r[c] || '') + '</td>').join('') + '</tr>').join('') + '</table></div>' +
    (t.count > 10 ? '<span class="mute tiny">' + t.count + ' rows</span>' : '');
  sheet(head('Columns', btn('back', 'Back') + btn('cols', 'Next', 'primary', t.columns.title == null && t.columns.isbn == null)) + '<div class="bebody one ilbody">' + h + '</div>');
}

/* ---------- 2. the matches ---------- */
const isNew = r => !r.match;
function counts(){
  const have = L.rows.filter(r => !isNew(r)).length;
  return { all: L.rows.length, have, new: L.rows.length - have };
}
function shown(){ return L.rows.map((r, i) => [r, i]).filter(([r]) => L.filter === 'all' || (L.filter === 'have') === !isNew(r)); }
function drawMatch(){
  const n = counts(), list = shown(), allOn = list.length && list.every(([r]) => r.on);
  const tabs = [['all', 'All'], ['have', 'In the library'], ['new', 'Not in the library']];
  const h = errLine() + '<div class="ilfilter"><input type="checkbox" data-ilall' + (allOn ? ' checked' : '') + ' aria-label="Choose all">' +
    '<div class="bemtabs" role="tablist">' + tabs.map(([k, l]) => '<button role="tab" aria-selected="' + (L.filter === k) + '" class="' + (L.filter === k ? 'on' : '') + '" data-ilfilter="' + k + '">' + l + ' <b>' + n[k] + '</b></button>').join('') + '</div></div>' +
    '<div class="ilrows">' + (list.length ? list.map(([r, i]) => rowHtml(r, i)).join('') : '<p class="mute">None</p>') + '</div>';
  const on = L.rows.filter(r => r.on).length;
  sheet(head(on === n.all ? n.all + ' books' : on + ' of ' + n.all + ' books', btn('back', 'Back') + btn('next', 'Next', 'primary', !on)) + '<div class="bebody one ilbody">' + h + '</div>');
}
function rowHtml(r, i){
  const extra = [r.series ? r.series + (r.series_index != null ? ' #' + (Math.round(r.series_index * 100) / 100) : '') : '', r.isbn || '', r.published ? r.published.slice(0, 4) : ''].filter(Boolean).join(' · ');
  const m = r.match, which = r.choices && r.choices.length > 1;
  let mh = '<div class="ilmhead">' + (m ? '<span class="ilhow">' + esc(HOW[r.how] || r.how || '') + '</span>' : '<span class="ilnew">Not in the library</span>') +
    '<button class="linkbtn" data-ilfind="' + i + '">' + (L.find === i ? 'Done' : m ? 'Change' : 'Find') + '</button></div>';
  if (which) mh += select('data-ilchoice="' + i + '" aria-label="Which"', r.choices.map(c => [c.id, c.title + ' · ' + ((c.formats || []).join(', ') || 'No file') + ' · #' + c.id]), m.id);
  else if (m) mh += '<b>' + esc(m.title) + '</b><span class="mute tiny">' + esc((m.authors || []).join(' & ')) + ' · ' + esc((m.formats || []).join(', ') || 'No file') + '</span>';
  if (L.find === i) mh += '<div class="ilfind"><input class="field sm" type="search" data-ilq="' + i + '" value="' + esc(L.findQ || '') + '" placeholder="Search the library" autocomplete="off" autocapitalize="off" spellcheck="false">' +
    (L.hits || []).map(b => '<button class="ilhit" data-ilpick="' + i + '|' + b.id + '"><b>' + esc(b.title) + '</b><span class="mute tiny">' + esc((b.authors || []).join(' & ')) + ' · ' + esc((b.formats || []).join(', ') || 'No file') + '</span></button>').join('') +
    (m ? '<button class="ilhit" data-ilnone="' + i + '"><b>Not in the library</b></button>' : '') + '</div>';
  return '<div class="ilrow' + (r.on ? '' : ' off') + '" data-ilrow="' + i + '"><input type="checkbox" data-ilon="' + i + '"' + (r.on ? ' checked' : '') + ' aria-label="Use">' +
    '<div class="illist"><input class="field sm" data-iledit="' + i + '" data-k="title" value="' + esc(r.title || '') + '" placeholder="' + esc(r.isbn || 'Title') + '" aria-label="Title">' +
    '<input class="field sm" data-iledit="' + i + '" data-k="authors" value="' + esc((r.authors || []).join(' & ')) + '" placeholder="Authors" aria-label="Authors">' +
    (extra ? '<span class="mute tiny">' + esc(extra) + '</span>' : '') + '</div><div class="ilmatch">' + mh + '</div></div>';
}
function redrawRow(i){
  const el = $('#ilsheet [data-ilrow="' + i + '"]'); if (!el) return;
  el.outerHTML = rowHtml(L.rows[i], i);
  const n = counts();
  $$('#ilsheet [data-ilfilter]').forEach(b => { const k = b.dataset.ilfilter; b.querySelector('b').textContent = n[k]; });
  const on = L.rows.filter(r => r.on).length, h2 = $('#ilsheet .behead h2'); if (h2) h2.textContent = on === n.all ? n.all + ' books' : on + ' of ' + n.all + ' books';
  const nx = $('#ilsheet [data-il="next"]'); if (nx) nx.disabled = !on;
}
async function rematch(i){
  const r = L.rows[i], seq = r._seq = (r._seq || 0) + 1;
  let got;
  try { got = (await api('/api/catalog/importlist/match', { method: 'POST', body: JSON.stringify({ rows: [strip(r)] }) })).rows[0]; } catch(e){ toast(e.message); return; }
  if (L.rows[i] !== r || r._seq !== seq) return;
  L.rows[i] = Object.assign(got, { on: r.on }); redrawRow(i);
}
const strip = r => ({ title: r.title, authors: r.authors, series: r.series, series_index: r.series_index, isbn: r.isbn, published: r.published, ids: r.ids });
let finding = null;
function search(i, q){
  L.findQ = q; clearTimeout(finding);
  finding = setTimeout(async () => {
    let r; try { r = await api('/api/catalog/importlist/search?q=' + encodeURIComponent(q)); } catch(e){ return; }
    if (L.find !== i || L.findQ !== q) return;
    L.hits = r.books;
    const box = $('#ilsheet [data-ilrow="' + i + '"] .ilfind'); if (!box) return;
    $$('.ilhit', box).forEach(x => x.remove());
    box.insertAdjacentHTML('beforeend', L.hits.map(b => '<button class="ilhit" data-ilpick="' + i + '|' + b.id + '"><b>' + esc(b.title) + '</b><span class="mute tiny">' + esc((b.authors || []).join(' & ')) + ' · ' + esc((b.formats || []).join(', ') || 'No file') + '</span></button>').join('') +
      (L.rows[i].match ? '<button class="ilhit" data-ilnone="' + i + '"><b>Not in the library</b></button>' : ''));
  }, 200);
}

/* ---------- 3. what to do ---------- */
function plan(){
  const add = L.opts.add ? L.rows.filter(r => r.on && isNew(r)) : [], have = L.rows.filter(r => r.on && !isNew(r));
  const haveUsed = have.length && (L.opts.have_tag.trim() || L.opts.have_shelf);
  return { add, have, nothing: !add.length && !haveUsed, newN: L.rows.filter(r => r.on && isNew(r)).length };
}
// The new books go on Daf's own shelves (Hardcover doesn't know an empty book yet); the others on a Hardcover list too.
const shelvesFor = k => (L.meta.shelves || []).filter(s => k === 'have_shelf' || !s.hardcover);
function shelfSel(k){
  const list = [['', '—']].concat(shelvesFor(k).map(s => [s.id, s.name])).concat([['__new', 'New shelf…']]);
  return select('data-ilo="' + k + '"', list, L.opts[k]) + (L.opts[k] === '__new' ? '<input class="field ilnewshelf" data-ilo="' + k + '_new" value="' + esc(L.opts[k + '_new'] || '') + '" placeholder="Name" autocomplete="off">' : '');
}
function drawDo(){
  for (const k of ['add_shelf', 'have_shelf']) if (L.opts[k] && L.opts[k] !== '__new' && !shelvesFor(k).some(s => s.id === L.opts[k])) L.opts[k] = '';
  const p = plan(), haveN = L.rows.filter(r => r.on && !isNew(r)).length, rc = L.meta.read;
  let h = errLine();
  if (p.newN) h += '<h3>Not in the library · ' + p.newN + '</h3>' +
    '<label class="ilck"><input type="checkbox" data-ilo="add"' + (L.opts.add ? ' checked' : '') + '>Add as empty books</label>' +
    (L.opts.add ? (rc ? '<label class="ilck"><input type="checkbox" data-ilo="read"' + (L.opts.read ? ' checked' : '') + '>' + esc(rc.label + ': ' + rc.choice) + '</label>' : '') +
      row('Tag', '<input class="field" data-ilo="add_tag" value="' + esc(L.opts.add_tag) + '" autocomplete="off">') + row('Shelf', shelfSel('add_shelf')) : '');
  if (haveN) h += '<h3>In the library · ' + haveN + '</h3>' + row('Tag', '<input class="field" data-ilo="have_tag" value="' + esc(L.opts.have_tag) + '" autocomplete="off">') + row('Shelf', shelfSel('have_shelf'));
  sheet(head('Import list', btn('back', 'Back') + btn('import', 'Import', 'primary', p.nothing)) + '<div class="bebody one ilbody">' + h + '</div>');
}
function keepOpts(){ const o = Object.assign({}, L.opts); delete o.add_shelf_new; delete o.have_shelf_new; if (o.add_shelf === '__new') o.add_shelf = ''; if (o.have_shelf === '__new') o.have_shelf = ''; store.set('importlist', o); }
async function doImport(){
  const p = plan(); if (p.nothing || L.busy) return;
  const o = L.opts;
  for (const k of ['add_shelf', 'have_shelf']) if (o[k] === '__new' && !(o[k + '_new'] || '').trim()) { L.err = 'A name for the new shelf, please'; draw(); return; }
  L.busy = true; L.err = ''; L.step = 'busy'; L.busyText = 'Importing…'; L.busyPct = 5; draw();
  try {
    const made = {};
    for (const k of ['add_shelf', 'have_shelf']) {         // a new shelf is made now, with the rest
      if (o[k] !== '__new') continue;
      const name = o[k + '_new'].trim();
      if (!made[name.toLowerCase()]) made[name.toLowerCase()] = (await api('/api/shelves', { method: 'POST', body: JSON.stringify({ name }) })).id;
      o[k] = made[name.toLowerCase()];
    }
    const body = { add: p.add.map(strip), add_tag: o.add_tag, add_read: !!(o.read && L.meta.read), add_shelf: p.add.length ? o.add_shelf || null : null,
      have: p.have.map(r => r.match.id), have_tag: o.have_tag, have_shelf: o.have_shelf || null };
    const { job } = await api('/api/catalog/importlist/apply', { method: 'POST', body: JSON.stringify(body) });
    keepOpts();
    for (let n = 0; ; n++) {
      await new Promise(r => setTimeout(r, 1500));
      const j = await api('/api/catalog/job/' + job);
      L.busyPct = Math.min(90, 10 + n * 6); draw();
      if (j.running) continue;
      if (j.error) throw new Error(j.error);
      L.result = j.done; break;
    }
    L.busy = false; L.step = 'done'; draw();
    if (C.Catalog) C.Catalog.reload();
  } catch(e){ L.busy = false; L.err = e.message; L.step = 'do'; draw(); }
}
function drawDone(){
  const r = L.result || { added: [], tagged: 0, shelved: 0, failed: [] }, titles = {};
  L.rows.forEach(x => { if (x.match) titles[x.match.id] = x.match.title; });
  const lines = [r.added.length ? 'Added ' + r.added.length : '', r.tagged ? 'Tagged ' + r.tagged : '', r.shelved ? 'On the shelf ' + r.shelved : ''].filter(Boolean);
  sheet(head('Imported', btn('close', 'Close') + (r.added.length ? btn('show', 'Show in All books', 'primary') : '')) +
    '<div class="bebody one ilbody"><div class="ilsum">' + lines.map(l => '<span>' + esc(l) + '</span>').join('') + '</div>' +
    (r.failed.length ? '<h3>Not done · ' + r.failed.length + '</h3>' + r.failed.map(f => '<div class="mute tiny">' + esc((titles[f.id] || f.id) + ': ' + f.error) + '</div>').join('') : '') + '</div>');
}

/* ---------- events ---------- */
document.addEventListener('click', e => {
  const t = e.target; if (!t.closest) return;
  if (t.closest('#ilshade')) { close(); return; }
  if (!t.closest('#ilsheet')) return;
  const a = t.closest('[data-il]');
  if (a && !a.disabled) {
    const k = a.dataset.il;
    if (k === 'cancel' || k === 'close') close(k === 'close');
    else if (k === 'read') read(source());
    else if (k === 'cols') read(Object.assign({}, L.tsrc, { delimiter: L.table.delimiter, headings: L.table.headings, columns: L.table.columns }));
    else if (k === 'back') { L.err = ''; L.find = null; L.step = L.step === 'do' ? 'match' : L.step === 'match' && L.table ? 'cols' : 'in'; draw(); }
    else if (k === 'next') { L.err = ''; L.find = null; L.step = 'do'; draw(); }
    else if (k === 'import') doImport();
    else if (k === 'show') { const ids = (L.result || {}).added || []; close(true); if (C.Catalog && C.Catalog.choose) C.Catalog.choose(ids); }
    return;
  }
  const tab = t.closest('[data-iltab]'); if (tab) { L.tab = tab.dataset.iltab; store.set('importlistTab', L.tab); L.err = ''; draw(); return; }
  const f = t.closest('[data-ilfilter]'); if (f) { L.filter = f.dataset.ilfilter; L.find = null; draw(); return; }
  const fi = t.closest('[data-ilfind]');
  if (fi) { const i = +fi.dataset.ilfind, was = L.find; L.find = was === i ? null : i; L.hits = null;
    if (was != null && was !== i) redrawRow(was);
    redrawRow(i);
    if (L.find === i) { const r = L.rows[i], q = [r.title, (r.authors || [])[0]].filter(Boolean).join(' '); const box = $('#ilsheet [data-ilq="' + i + '"]'); if (box) { box.value = q; box.focus(); } search(i, q); }
    return; }
  const pk = t.closest('[data-ilpick]');
  if (pk) { const [i, id] = pk.dataset.ilpick.split('|').map(Number), b = (L.hits || []).find(x => x.id === id), r = L.rows[i];
    if (b) { r.match = b; r.how = 'hand'; r.choices = []; r.on = true; } L.find = null; redrawRow(i); return; }
  const no = t.closest('[data-ilnone]'); if (no) { const i = +no.dataset.ilnone; Object.assign(L.rows[i], { match: null, how: null, choices: [] }); L.find = null; redrawRow(i); return; }
});
document.addEventListener('change', e => {
  const t = e.target; if (!t.closest || !t.closest('#ilsheet')) return;
  if (t.matches('[data-ilfile]')) {
    const file = t.files && t.files[0]; if (!file) return;
    if (file.size > 20 * 1024 * 1024) { L.err = 'The file is too big'; draw(); return; }
    const fr = new FileReader();
    fr.onload = () => { L.file = b64(fr.result); L.fileName = file.name; read({ source: 'table', data: L.file }); };
    fr.readAsArrayBuffer(file); return;
  }
  if (t.matches('[data-ilf]')) {
    const k = t.dataset.ilf; L[k] = t.value;
    if (k === 'form') draw();
    if (k === 'site') { const s = L.meta.sites.find(x => x.name === t.value); if (s) { L.url = s.url; const u = $('#ilsheet [data-ilf="url"]'); if (u) u.value = s.url; } }
    return;
  }
  if (t.name === 'ilhc') { L.hc = t.value; return; }
  if (t.matches('[data-ilt]')) {
    if (t.dataset.ilt === 'headings') { L.table.headings = t.checked; draw(); }
    else { L.table.delimiter = t.value; read(Object.assign({}, L.tsrc, { delimiter: t.value })); }
    return;
  }
  if (t.matches('[data-ilcol]')) { L.table.columns[t.dataset.ilcol] = t.value === '' ? null : +t.value; const nx = $('#ilsheet [data-il="cols"]'); if (nx) nx.disabled = L.table.columns.title == null && L.table.columns.isbn == null; return; }
  if (t.matches('[data-ilall]')) { shown().forEach(([r]) => { r.on = t.checked; }); drawMatch(); return; }
  if (t.matches('[data-ilon]')) { const i = +t.dataset.ilon; L.rows[i].on = t.checked; redrawRow(i); const all = $('#ilsheet [data-ilall]'); if (all) all.checked = shown().every(([r]) => r.on); return; }
  if (t.matches('[data-ilchoice]')) { const r = L.rows[+t.dataset.ilchoice]; r.match = r.choices.find(c => c.id === +t.value) || r.match; return; }
  if (t.matches('[data-iledit]')) {
    const i = +t.dataset.iledit, r = L.rows[i], k = t.dataset.k, v = t.value.trim();
    if (k === 'authors') r.authors = v ? v.split(/\s*&\s*/).filter(Boolean) : []; else r.title = v;
    if (r.how !== 'hand') rematch(i);
    return;
  }
  if (t.matches('[data-ilo]')) {
    const k = t.dataset.ilo; L.opts[k] = t.type === 'checkbox' ? t.checked : t.value;
    if (k === 'add' || k === 'add_shelf' || k === 'have_shelf') { drawDo(); const n = $('#ilsheet [data-ilo="' + k + '_new"]'); if (n) n.focus(); }
    else { const b = $('#ilsheet [data-il="import"]'); if (b) b.disabled = plan().nothing; }
  }
});
document.addEventListener('input', e => {
  const t = e.target; if (!t.closest || !t.closest('#ilsheet')) return;
  if (t.matches('[data-ilf="text"],[data-ilf="pattern"],[data-ilf="url"]')) { L[t.dataset.ilf] = t.value; if (t.dataset.ilf === 'url') L.site = ''; }
  else if (t.matches('[data-ilxp]')) L.xp[t.dataset.ilxp] = t.value.trim();
  else if (t.matches('[data-ilq]')) search(+t.dataset.ilq, t.value);
  else if (t.matches('[data-ilo]') && t.type !== 'checkbox') { L.opts[t.dataset.ilo] = t.value; const b = $('#ilsheet [data-il="import"]'); if (b) b.disabled = plan().nothing; }
});
document.addEventListener('keydown', e => {
  const s = $('#ilsheet'); if (!s || s.hidden) return;
  const t = e.target;
  if (e.key === 'Escape') { e.preventDefault(); e.stopImmediatePropagation(); if (L.find != null) { const i = L.find; L.find = null; redrawRow(i); } else if (!L.busy) close(); return; }
  if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) { e.preventDefault(); const p = $('#ilsheet .behead .btn.primary'); if (p && !p.disabled) p.click(); return; }
  if (e.key === 'Enter' && t.matches && t.matches('[data-iledit]')) { e.preventDefault(); t.blur(); return; }
  if (e.key === 'Enter' && t.matches && t.matches('[data-ilf="url"],[data-ilxp],[data-ilf="pattern"]')) { e.preventDefault(); read(source()); }
}, true);

C.ImportList = { open };
})();
