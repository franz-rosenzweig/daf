/* Adding a book (hardcover.add_book, bookfiles.py): Books → Add a book searches Hardcover by title,
   author or ISBN; each result says what Daf and Hardcover already have of it. Picking one puts it on
   Hardcover (Want to read or Reading, or not at all) and in Daf at once, with its file if you give it
   one, which goes into Calibre with the book's Hardcover id and ISBN inside. A book without its file
   has "Add the file" on its page, and says how the file it was sent is getting on. */
(function(){
const C = window.DafCore, { $, esc, api, toast, closeModal } = C;
const A = { hits: [], pick: null, timer: 0, file: null, shelves: null, src: 'hc', free: [], freeN: 0 };

// The Kindle's shelves (its home folder's folders, as its plugin reported them), Books first.
async function kindleShelves(){
  if (!A.shelves) { try { A.shelves = (await api('/api/kindle/shelves')).shelves; } catch(e){ A.shelves = ['Books']; } }
  return A.shelves;
}
const shelfOptions = (list, pick) => list.map(s => '<option' + (s === pick ? ' selected' : '') + '>' + esc(s) + '</option>').join('');

function open(q){
  A.pick = null; A.file = null;
  $('#scrim').hidden = false; const m = $('#modal'); m.hidden = false; m.classList.add('wide');
  m.innerHTML = '<h2>Add a book</h2>' +
    '<div class="seg absrc" role="radiogroup" aria-label="Where">' + [['hc', 'Hardcover'], ['free', 'Public domain']].map(x =>
      '<button type="button" role="radio" aria-checked="' + (A.src === x[0]) + '" class="' + (A.src === x[0] ? 'on' : '') + '" data-absrc="' + x[0] + '">' + x[1] + '</button>').join('') + '</div>' +
    '<input class="field" id="abq" placeholder="' + (A.src === 'free' ? 'Title or author' : 'Title, author or ISBN') + '" autocomplete="off" value="' + esc(q || '') + '">' +
    '<div id="abres" class="abres"></div>' +
    '<div style="display:flex;justify-content:flex-end;gap:8px"><button class="btn" data-ab="close">Cancel</button></div>';
  const inp = $('#abq'); inp.focus();
  if (q) find(q);
}

async function find(q){
  const box = $('#abres'); if (!box) return;
  if (!q.trim()) { box.innerHTML = ''; return; }
  if (A.src === 'free') return findFree(q);
  box.innerHTML = '<p class="mute tiny" style="margin:0">Searching…</p>';
  try {
    const r = await api('/api/books/find?q=' + encodeURIComponent(q.trim()));
    if (($('#abq') || {}).value !== q) return;            // typed on since
    A.hits = r.hits;
    box.innerHTML = r.hits.length ? r.hits.map((h, i) => {
      const have = h.book_id ? (h.has_file ? 'In your library' : 'In Daf, no file yet') : '';
      const shelf = h.status ? 'On Hardcover: ' + h.status : '';
      return '<button class="abhit" data-abi="' + i + '">' +
        (h.image ? '<img src="' + esc(h.image) + '" alt="" loading="lazy" referrerpolicy="no-referrer">' : '<span class="abnoimg"></span>') +
        '<span class="abt"><b>' + esc(h.title) + '</b><span class="mute tiny">' + esc([h.author, h.year].filter(Boolean).join(' · ')) + '</span>' +
        '<span class="tiny">' + [have && esc(have), shelf && esc(shelf), h.readers && '<span class="mute">' + h.readers.toLocaleString() + (h.readers === 1 ? ' reader' : ' readers') + '</span>'].filter(Boolean).join(' · ') + '</span></span></button>';
    }).join('') : '<p class="mute" style="margin:0">Nothing found</p>';
  } catch(e){ box.innerHTML = '<p class="mute" style="margin:0">' + esc(e.message) + '</p>'; }
}

// Public domain (freebooks.py): Standard Ebooks and Project Gutenberg, each book straight into Calibre.
const SRC = { se: 'Standard Ebooks', pg: 'Project Gutenberg' };
async function findFree(q){
  const box = $('#abres'), n = ++A.freeN, by = { se: null, pg: null }, failed = [];
  box.innerHTML = '<p class="mute tiny" style="margin:0">Searching…</p>';
  const draw = () => {
    if (n !== A.freeN || ($('#abq') || {}).value !== q || A.src !== 'free') return;
    const se = by.se || [], keys = new Set(se.map(x => x.key));
    const list = se.concat((by.pg || []).filter(x => !keys.has(x.key))).map((x, i) => [x, i]).sort((a, b) => a[0].rank - b[0].rank || a[1] - b[1]).map(p => p[0]);
    const waiting = !by.se || !by.pg;
    A.free = list;
    box.innerHTML = (failed.length ? '<p class="mute tiny" style="margin:0">' + esc(failed.join(' and ')) + ' didn’t answer</p>' : '') +
      list.map((x, i) => '<div class="abhit fbhit">' +
        (x.cover ? '<img src="' + esc(x.cover) + '" alt="" loading="lazy" referrerpolicy="no-referrer" onerror="this.replaceWith(Object.assign(document.createElement(\'span\'),{className:\'abnoimg\'}))">' : '<span class="abnoimg"></span>') +
        '<span class="abt"><b>' + esc(x.title) + '</b><span class="mute tiny">' + esc([x.author, SRC[x.source]].filter(Boolean).join(' · ')) + '</span></span>' +
        (x.have ? '<a class="btn sm" href="#book/' + encodeURIComponent(x.have) + '" data-ab="close">Open</a>' : '<button type="button" class="btn sm" data-fbadd="' + i + '">Add</button>') +
        '</div>').join('') +
      (waiting ? '<p class="mute tiny" style="margin:0">Searching…</p>' : list.length ? '' : '<p class="mute" style="margin:0">Nothing found</p>');
  };
  for (const site of ['pg', 'se']) {
    api('/api/free/search?site=' + site + '&q=' + encodeURIComponent(q.trim()))
      .then(r => { by[site] = r.results; failed.push(...r.failed); }, e => { by[site] = []; failed.push(SRC[site]); })
      .then(draw);
  }
}
async function addFree(btn, force){
  const x = A.free[+btn.dataset.fbadd]; if (!x) return;
  btn.disabled = true; btn.textContent = 'Adding…';
  try {
    const r = await fetch('/api/free/add', { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ source: x.source, id: x.id, title: x.title, author: x.author, force: !!force }) });
    const j = await r.json().catch(() => ({}));
    if (r.status === 409) {
      if (confirm(j.detail + '.\n\nAdd this edition too?')) return addFree(btn, true);
      btn.disabled = false; btn.textContent = 'Add'; return;
    }
    if (!r.ok) throw new Error(typeof j.detail === 'string' ? j.detail : r.statusText);
    btn.textContent = 'Added'; toast('Added');
  } catch(e){ btn.disabled = false; btn.textContent = 'Add'; toast(e.message); }
}

function choose(i){
  const h = A.hits[i]; if (!h) return;
  if (h.book_id && h.has_file) { closeModal(); location.hash = 'book/' + encodeURIComponent(h.book_id); return; }
  A.pick = h;
  const m = $('#modal');
  const st = h.status_id ? 0 : 1;                          // already on a Hardcover shelf: leave it there
  m.innerHTML = '<h2>' + esc(h.title) + '</h2><span class="mute">' + esc([h.author, h.year].filter(Boolean).join(' · ')) + '</span>' +
    (h.status ? '<p class="mute tiny" style="margin:0">On Hardcover: ' + esc(h.status) + '</p>' :
      '<div class="prow"><div class="d"><b>On Hardcover</b></div>' +
      '<div class="seg" role="radiogroup" aria-label="On Hardcover">' + [[1, 'Want to read'], [2, 'Reading'], [0, 'Not on Hardcover']].map(x =>
        '<button type="button" role="radio" aria-checked="' + (x[0] === st) + '" class="' + (x[0] === st ? 'on' : '') + '" data-abst="' + x[0] + '">' + x[1] + '</button>').join('') + '</div></div>') +
    '<div class="prow"><div class="d"><b>The book’s file</b></div>' +
      '<label class="btn sm">' + '<span id="abfname">Choose a file</span><input type="file" id="abfile" accept=".epub,.kepub,.mobi,.azw3,.fb2,.cbz,.pdf" hidden></label></div>' +
    '<div class="prow" id="abkindle" hidden><div class="d"><b>Put it on the Kindle</b></div>' +
      '<select class="field" id="abshelf" style="width:auto"><option value="">Not now</option></select></div>' +
    '<div style="display:flex;justify-content:flex-end;gap:8px"><button class="btn" data-ab="back">Back</button><button class="btn primary" data-ab="add">' + (h.book_id ? 'Add the file' : 'Add to Daf') + '</button></div>';
  A.status = h.status ? 0 : st;
}

async function add(btn){
  const h = A.pick; if (!h) return;
  btn.disabled = true; btn.textContent = 'Adding…';
  try {
    const shelf = A.file ? (($('#abshelf') || {}).value || '') : '';
    const bid = h.book_id || (await api('/api/books/add', { method: 'POST', body: JSON.stringify({ hc_book_id: h.id, status: A.status, kindle_shelf: shelf || null }) })).book_id;
    if (A.file) await upload(bid, A.file, false, shelf);
    closeModal();
    toast(A.file ? 'Added' : 'Added to Daf' + (A.status === 1 ? ' and Want to read' : A.status === 2 ? ' and Reading' : ''));
    location.hash = 'book/' + encodeURIComponent(bid);
  } catch(e){ toast(e.message); btn.disabled = false; btn.textContent = 'Add to Daf'; }
}

// The file to Calibre for this Daf book. Calibre having it already asks before sending another.
async function upload(bookId, file, force, shelf){
  const fd = new FormData(); fd.append('file', file); if (force) fd.append('force', '1'); if (shelf) fd.append('kindle_shelf', shelf);
  const r = await fetch('/api/books/' + encodeURIComponent(bookId) + '/file', { method: 'POST', body: fd, credentials: 'same-origin' });
  const j = await r.json().catch(() => ({}));
  if (r.status === 409) {
    if (confirm(j.detail + '.\n\nSend this file to Calibre anyway?')) return upload(bookId, file, true, shelf);
    throw new Error(j.detail);
  }
  if (!r.ok) throw new Error(typeof j.detail === 'string' ? j.detail : r.statusText);
  return j;
}

// On a book's page: its file (when it has none), and the Kindle.
function sections(b){
  return b.kind === 'book' ? fileSection(b) + kindleSection(b) : '';
}
function kindleSection(b){
  const k = b.kindle;
  if (!b.has_file && !(b.file && !b.file.error) && !k) return '';
  let state, acts = '';
  if (k && k.delivered) { state = 'On the Kindle, in ' + esc(k.shelf) + ', since ' + esc(C.ago(k.delivered)) + '.'; acts = '<button class="btn sm" data-kput="' + esc(b.id) + '" data-again="' + esc(k.shelf) + '">Send it again</button>'; }
  else if (k && k.after_file) { state = 'Waiting for Calibre · ' + esc(k.shelf); acts = '<button class="btn sm" data-kcancel="' + esc(b.id) + '">Don’t</button>'; }
  else if (k && k.error) { state = 'The Kindle couldn’t take it: ' + esc(k.error) + '.'; acts = '<button class="btn sm" data-kput="' + esc(b.id) + '" data-again="' + esc(k.shelf) + '">Try again</button><button class="btn sm" data-kcancel="' + esc(b.id) + '">Forget it</button>'; }
  else if (k) { state = 'Waiting for the Kindle · ' + esc(k.shelf); acts = '<button class="btn sm" data-kcancel="' + esc(b.id) + '">Cancel</button>'; }
  else { state = '';
    acts = '<select class="field" id="kshelf" style="width:auto"><option>Books</option></select><button class="btn sm primary" data-kput="' + esc(b.id) + '">Put it on the Kindle</button>';
    kindleShelves().then(list => { const sel = $('#kshelf'); if (sel) sel.innerHTML = shelfOptions(list, list.includes('Books') ? 'Books' : list[0]); }); }
  return '<section class="card" id="bkindle"><div class="cardh"><h2>The Kindle</h2></div>' + (state ? '<p class="mute" style="margin:0">' + state + '</p>' : '') +
    '<div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center">' + acts + '</div></section>';
}
// When it has no file: add one, and how the last one is getting on.
function fileSection(b){
  if (b.has_file) return '';
  const f = b.file;
  const state = !f ? 'No file'
    : f.error ? 'The file didn’t make it: ' + esc(f.error)
    : f.cal_id ? 'In Calibre'
    : 'Sent ' + esc(C.ago(f.created)) + ' · “' + esc(f.name) + '”';
  return '<section class="card" id="bfile"><div class="cardh"><h2>The book’s file</h2></div><p class="mute" style="margin:0">' + state + '</p>' +
    '<label class="btn sm" style="align-self:flex-start">Add the file<input type="file" data-bfile="' + esc(b.id) + '" accept=".epub,.kepub,.mobi,.azw3,.fb2,.cbz,.pdf" hidden></label></section>';
}

document.addEventListener('input', e => {
  if (e.target.id !== 'abq') return;
  clearTimeout(A.timer); const q = e.target.value; A.timer = setTimeout(() => find(q), 350);
});
document.addEventListener('keydown', e => {
  if (e.target.id === 'abq' && e.key === 'Enter') { e.preventDefault(); clearTimeout(A.timer); find(e.target.value); }
});
document.addEventListener('change', async e => {
  if (e.target.id === 'abfile' && e.target.files[0]) {
    A.file = e.target.files[0]; $('#abfname').textContent = A.file.name;
    const row = $('#abkindle'); if (row) { row.hidden = false; const list = await kindleShelves(); $('#abshelf').innerHTML = '<option value="">Not now</option>' + shelfOptions(list, list.includes('Books') ? 'Books' : list[0]); }
    return;
  }
  const bid = e.target.dataset && e.target.dataset.bfile;
  if (bid && e.target.files[0]) {
    try { await upload(bid, e.target.files[0]); toast('Sent to Calibre'); C.load(true); }
    catch(err){ toast(err.message); }
  }
});
document.addEventListener('click', async e => {
  const k = e.target.closest && e.target.closest('[data-kput],[data-kcancel]');
  if (k) {
    try {
      if (k.dataset.kcancel) { await api('/api/books/' + encodeURIComponent(k.dataset.kcancel) + '/kindle', { method: 'DELETE' }); toast('Cancelled'); }
      else { const shelf = k.dataset.again || (($('#kshelf') || {}).value || 'Books');
        const r = await api('/api/books/' + encodeURIComponent(k.dataset.kput) + '/kindle', { method: 'POST', body: JSON.stringify({ shelf }) });
        toast(r.kindle && r.kindle.after_file ? 'Waiting for Calibre' : 'Queued for the Kindle'); }
      C.load(true);
    } catch(err){ toast(err.message); }
    return;
  }
  const sw = e.target.closest && e.target.closest('[data-absrc]');
  if (sw) {
    A.src = sw.dataset.absrc;
    sw.parentNode.querySelectorAll('button').forEach(b => { const on = b === sw; b.classList.toggle('on', on); b.setAttribute('aria-checked', on); });
    const inp = $('#abq'); inp.placeholder = A.src === 'free' ? 'Title or author' : 'Title, author or ISBN'; inp.focus();
    find(inp.value); return;
  }
  const fb = e.target.closest && e.target.closest('[data-fbadd]');
  if (fb) { addFree(fb); return; }
  const t = e.target.closest && e.target.closest('[data-ab],[data-abi],[data-abst],[data-act="addbook"]'); if (!t) return;
  if (t.dataset.act === 'addbook') { open(''); return; }
  if (t.dataset.abi != null) { choose(+t.dataset.abi); return; }
  if (t.dataset.abst != null) { A.status = +t.dataset.abst; t.parentNode.querySelectorAll('[data-abst]').forEach(x => { const on = x === t; x.classList.toggle('on', on); x.setAttribute('aria-checked', on); }); return; }
  const a = t.dataset.ab;
  if (a === 'close') closeModal();
  else if (a === 'back') open(($('#abq') || {}).value || (A.pick && A.pick.title) || '');
  else if (a === 'add') add(t);
});

C.AddBook = { open, fileSection, sections };
})();
