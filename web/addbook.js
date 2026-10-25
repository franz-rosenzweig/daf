/* Adding a book (hardcover.add_book, bookfiles.py): Books → Add a book searches Hardcover by title,
   author or ISBN; each result says what Daf and Hardcover already have of it. Picking one puts it on
   Hardcover (Want to read or Reading, or not at all) and in Daf at once, with its file if you give it
   one, which goes into Calibre with the book's Hardcover id and ISBN inside. A book without its file
   has "Add the file" on its page, and says how the file it was sent is getting on. */
(function(){
const C = window.DafCore, { $, esc, api, toast, closeModal } = C;
const A = { hits: [], pick: null, timer: 0, file: null, shelves: null };

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
    '<input class="field" id="abq" placeholder="Title, author or ISBN" autocomplete="off" value="' + esc(q || '') + '">' +
    '<div id="abres" class="abres"><p class="mute tiny" style="margin:0">From Hardcover. A book you already have says so.</p></div>' +
    '<div style="display:flex;justify-content:flex-end;gap:8px"><button class="btn" data-ab="close">Cancel</button></div>';
  const inp = $('#abq'); inp.focus();
  if (q) find(q);
}

async function find(q){
  const box = $('#abres'); if (!box) return;
  if (!q.trim()) { box.innerHTML = ''; return; }
  box.innerHTML = '<p class="mute tiny" style="margin:0">Asking Hardcover…</p>';
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
    }).join('') : '<p class="mute" style="margin:0">Nothing on Hardcover by that name.</p>';
  } catch(e){ box.innerHTML = '<p class="mute" style="margin:0">' + esc(e.message) + '</p>'; }
}

function choose(i){
  const h = A.hits[i]; if (!h) return;
  if (h.book_id && h.has_file) { closeModal(); location.hash = 'book/' + encodeURIComponent(h.book_id); return; }
  A.pick = h;
  const m = $('#modal');
  const st = h.status_id ? 0 : 1;                          // already on a Hardcover shelf: leave it there
  m.innerHTML = '<h2>' + esc(h.title) + '</h2><span class="mute">' + esc([h.author, h.year].filter(Boolean).join(' · ')) + '</span>' +
    (h.status ? '<p class="mute tiny" style="margin:0">On Hardcover already: ' + esc(h.status) + '. That stays as it is.</p>' :
      '<div class="prow"><div class="d"><b>On Hardcover</b><span>Where it goes on your Hardcover shelves.</span></div>' +
      '<div class="seg" role="radiogroup" aria-label="On Hardcover">' + [[1, 'Want to read'], [2, 'Reading'], [0, 'Not on Hardcover']].map(x =>
        '<button type="button" role="radio" aria-checked="' + (x[0] === st) + '" class="' + (x[0] === st ? 'on' : '') + '" data-abst="' + x[0] + '">' + x[1] + '</button>').join('') + '</div></div>') +
    '<div class="prow"><div class="d"><b>The book’s file</b><span>Optional. EPUB is best; it goes into Calibre, and Daf can open it. You can add it later from the book’s page.</span></div>' +
      '<label class="btn sm">' + '<span id="abfname">Choose a file</span><input type="file" id="abfile" accept=".epub,.kepub,.mobi,.azw3,.fb2,.cbz,.pdf" hidden></label></div>' +
    '<div class="prow" id="abkindle" hidden><div class="d"><b>Put it on the Kindle</b><span>It downloads on the Kindle’s next Wi-Fi sync, once Calibre has it.</span></div>' +
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
    toast(A.file ? 'Added. The file’s on its way into Calibre.' : 'Added to Daf' + (A.status === 1 ? ' and Want to read' : A.status === 2 ? ' and Reading' : ''));
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
  else if (k && k.after_file) { state = 'Goes to the Kindle, in ' + esc(k.shelf) + ', once Calibre has the file.'; acts = '<button class="btn sm" data-kcancel="' + esc(b.id) + '">Don’t</button>'; }
  else if (k) { state = (k.error ? 'The Kindle couldn’t take it: ' + esc(k.error) + '. ' : '') + 'Waiting for the Kindle’s next Wi-Fi sync; it goes in ' + esc(k.shelf) + '.'; acts = '<button class="btn sm" data-kcancel="' + esc(b.id) + '">Cancel</button>'; }
  else { state = 'Put it on the Kindle: it downloads on the Kindle’s next Wi-Fi sync, into the shelf you pick.';
    acts = '<select class="field" id="kshelf" style="width:auto"><option>Books</option></select><button class="btn sm primary" data-kput="' + esc(b.id) + '">Put it on the Kindle</button>';
    kindleShelves().then(list => { const sel = $('#kshelf'); if (sel) sel.innerHTML = shelfOptions(list, list.includes('Books') ? 'Books' : list[0]); }); }
  return '<section class="card" id="bkindle"><div class="cardh"><h2>The Kindle</h2></div><p class="mute" style="margin:0">' + state + '</p>' +
    '<div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center">' + acts + '</div></section>';
}
// When it has no file: add one, and how the last one is getting on.
function fileSection(b){
  if (b.has_file) return '';
  const f = b.file;
  const state = !f ? 'Daf has this book from ' + (b.vault_path ? 'its note' : 'Hardcover') + ', without its file. Add one and it goes into Calibre, so you can read it in Daf.'
    : f.error ? 'The file you sent didn’t make it: ' + esc(f.error) + '. Try again, maybe as an EPUB.'
    : f.cal_id ? 'Calibre has it now; it opens here at the next sync, in a few minutes.'
    : 'Sent ' + esc(C.ago(f.created)) + ' as “' + esc(f.name) + '”. Calibre-Web takes it in within a few minutes.';
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
    try { await upload(bid, e.target.files[0]); toast('The file’s on its way into Calibre'); C.load(true); }
    catch(err){ toast(err.message); }
  }
});
document.addEventListener('click', async e => {
  const k = e.target.closest && e.target.closest('[data-kput],[data-kcancel]');
  if (k) {
    try {
      if (k.dataset.kcancel) { await api('/api/books/' + encodeURIComponent(k.dataset.kcancel) + '/kindle', { method: 'DELETE' }); toast('It won’t go to the Kindle'); }
      else { const shelf = k.dataset.again || (($('#kshelf') || {}).value || 'Books');
        const r = await api('/api/books/' + encodeURIComponent(k.dataset.kput) + '/kindle', { method: 'POST', body: JSON.stringify({ shelf }) });
        toast(r.kindle && r.kindle.after_file ? 'It goes to the Kindle once Calibre has the file' : 'It goes to the Kindle on its next Wi-Fi sync, in ' + shelf); }
      C.load(true);
    } catch(err){ toast(err.message); }
    return;
  }
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
