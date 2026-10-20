/* Hardcover in Daf: a book's status and rating on its page, "finished" with a rating, the
   Want to read shelf on Books, a nudge on Today when the Kindle reaches the end, and the
   settings. Daf writes to Hardcover directly; the vault's own Hardcover sync brings the
   change into the book note. */
(() => {
const C = window.DafCore, { api, esc, toast, $, epochDate, shortTitle, cover } = C;
const HC = C.HC = {};
const STATUS = [[1, 'Want to read'], [2, 'Reading'], [3, 'Read'], [4, 'Paused'], [5, 'Did not finish']];

// Half-star ratings, 0.5 to 5, like Hardcover's own.
function stars(r, editable){
  let h = '<span class="hcstars' + (editable ? ' edit' : '') + '" role="' + (editable ? 'slider' : 'img') + '" aria-label="' + (r ? r + ' of 5 stars' : 'No rating') + '"' + (editable ? ' aria-valuemin="0" aria-valuemax="5" aria-valuenow="' + (r || 0) + '" tabindex="0"' : '') + '>';
  for (let i = 1; i <= 5; i++) {
    const f = r >= i ? 1 : r >= i - 0.5 ? 0.5 : 0;
    h += '<span class="st' + (f === 1 ? ' full' : f ? ' half' : '') + '" data-star="' + i + '">★</span>';
  }
  return h + '</span>';
}
function starValue(el, e){
  const s = e.target.closest('[data-star]'); if (!s) return null;
  const r = s.getBoundingClientRect(), i = +s.dataset.star;
  return e.clientX - r.left < r.width / 2 ? i - 0.5 : i;
}

/* ---------- a book's page ---------- */
HC.section = async (bookId, box) => {
  box = box || $('#hcsec'); if (!box) return;
  let s;
  try { s = await api('/api/hardcover/book/' + encodeURIComponent(bookId)); }
  catch(e){ box.innerHTML = '<div class="cardh"><h2>Hardcover</h2></div><p class="mute tiny" style="margin:0">' + esc(e.message) + '</p>'; return; }
  let h = '<div class="cardh"><h2>Hardcover</h2>' + (s.url ? '<a class="tiny" href="' + esc(s.url) + '" target="_blank" rel="noopener">Open on Hardcover</a>' : '') + '</div>';
  if (!s.linked) {
    h += '<p class="mute" style="margin:0">This book isn’t linked to Hardcover yet.</p><div><button class="btn sm" data-hc="find" data-id="' + esc(bookId) + '">Find it on Hardcover</button></div><div id="hcfind"></div>';
  } else if (!s.on_shelf) {
    h += '<p class="mute" style="margin:0">On Hardcover, but not on your shelves.</p><div class="hcrow">' +
      '<button class="btn sm" data-hc="add" data-s="1" data-id="' + esc(bookId) + '">Add as Want to read</button><button class="btn sm" data-hc="add" data-s="2" data-id="' + esc(bookId) + '">Add as Reading</button></div>';
  } else {
    h += '<div class="hcrow"><select class="field sm" data-hcstatus="' + esc(bookId) + '" aria-label="Status on Hardcover">' + STATUS.map(x => '<option value="' + x[0] + '"' + (x[0] === s.status_id ? ' selected' : '') + '>' + x[1] + '</option>').join('') + '</select>' +
      (s.status_id === 3 ? '<span data-hcrate="' + esc(bookId) + '">' + stars(s.rating || 0, true) + '</span>' : '') +
      (s.status_id !== 3 ? '<button class="btn sm primary" data-hc="finish" data-id="' + esc(bookId) + '">Finished</button>' : '') + '</div>' +
      '<span class="mute tiny">' + [s.progress_pages && s.pages ? 'p. ' + s.progress_pages + ' of ' + s.pages + ' on Hardcover' : '', s.finished_at ? 'read ' + epochDate(Date.parse(s.finished_at) / 1000) : '', s.private ? 'private on Hardcover' : ''].filter(Boolean).join(' · ') + '</span>';
  }
  box.innerHTML = h;
};

async function find(bookId, q){
  const box = $('#hcfind'); if (!box) return;
  box.innerHTML = '<p class="mute tiny">Looking…</p>';
  try {
    const r = await api('/api/hardcover/search?' + (q ? 'q=' + encodeURIComponent(q) : 'book_id=' + encodeURIComponent(bookId)));
    box.innerHTML = '<div class="hchits">' + (r.hits.length ? r.hits.map(x => '<button class="hchit" data-hc="link" data-id="' + esc(bookId) + '" data-hid="' + x.id + '">' + (x.image ? '<img src="' + esc(x.image) + '" alt="" loading="lazy" referrerpolicy="no-referrer">' : '<span class="hcnoimg"></span>') +
      '<span><b>' + esc(x.title || '') + '</b><span class="mute tiny">' + esc([x.author, x.year, x.isbn ? 'same ISBN' : x.readers ? x.readers + ' readers' : ''].filter(Boolean).join(' · ')) + '</span></span></button>').join('') : '<p class="mute tiny">Nothing found.</p>') + '</div>' +
      '<form class="hcq" data-id="' + esc(bookId) + '"><input class="field sm" placeholder="Search Hardcover" value="' + esc(q || '') + '"><button class="btn sm">Search</button></form>';
  } catch(e){ box.innerHTML = '<p class="mute tiny">' + esc(e.message) + '</p>'; }
}

/* ---------- finished ---------- */
HC.finish = (bookId, title, after) => {
  $('#scrim').hidden = false; const m = $('#modal'); m.hidden = false;
  let rating = 0;
  m.innerHTML = '<h2>Finished ' + esc(shortTitle(title || 'this book')) + '</h2>' +
    '<p class="mute" style="margin:0">Marks it Read on Hardcover, with the date. The vault note follows on its next sync.</p>' +
    '<div class="hcrow"><span class="mute tiny">Your rating</span><span id="hcfinstars">' + stars(0, true) + '</span><button class="linkbtn tiny" id="hcnorate">No rating</button></div>' +
    '<label class="mute tiny" for="hcfdate">Finished on</label><input class="field" id="hcfdate" type="date" value="' + new Date().toISOString().slice(0, 10) + '" style="max-width:200px">' +
    '<div style="display:flex;gap:8px;justify-content:flex-end"><button class="btn" data-act="close">Cancel</button><button class="btn primary" id="hcfinish">Mark it read</button></div>';
  const sb = $('#hcfinstars');
  sb.onclick = e => { const v = starValue(sb, e); if (v != null) { rating = v; sb.innerHTML = stars(rating, true); } };
  $('#hcnorate').onclick = () => { rating = 0; sb.innerHTML = stars(0, true); };
  $('#hcfinish').onclick = async () => {
    const b = $('#hcfinish'); b.disabled = true; b.textContent = 'Telling Hardcover…';
    try { await api('/api/hardcover/book/' + encodeURIComponent(bookId) + '/finish', { method: 'POST', body: JSON.stringify({ rating: rating || null, date: $('#hcfdate').value }) });
      C.closeModal(); toast('Read, on Hardcover' + (rating ? ' · ' + rating + ' stars' : '')); after && after(); }
    catch(e){ toast(e.message); b.disabled = false; b.textContent = 'Mark it read'; }
  };
};

/* ---------- the Want to read shelf ---------- */
HC.shelf = async box => {
  if (!box) return;
  let r;
  try { r = await api('/api/hardcover/shelf?status=1'); } catch(e){ box.remove(); return; }
  if (!r.books.length) { box.remove(); return; }
  const n = r.books.filter(b => b.readable).length;
  const card = b => {
    const href = b.readable ? '#ebook/' + encodeURIComponent(b.daf_id) : b.daf_id ? '#book/' + encodeURIComponent(b.daf_id) : b.url;
    const img = b.has_cover ? cover({ id: b.daf_id, title: b.title, has_cover: true }, 'cv lib') : b.image ? '<img class="cv lib" src="' + esc(b.image) + '" alt="" loading="lazy" referrerpolicy="no-referrer">' : cover({ title: b.title }, 'cv lib');
    return '<a class="libcard" href="' + esc(href || '#books') + '"' + (!b.daf_id && b.url ? ' target="_blank" rel="noopener"' : '') + ' title="' + esc(b.title) + '">' + img + '<b>' + esc(shortTitle(b.title)) + '</b><span class="mute tiny">' + esc(b.author || '') + '</span>' + (b.readable ? '<span class="tiny hcread">Read in Daf</span>' : '') + '</a>';
  };
  const all = HC.wantAll;
  box.innerHTML = '<div class="cardh"><h2>Want to read</h2><span class="mute tiny">From Hardcover · ' + r.books.length + ' books, ' + n + ' you can open in Daf</span></div>' +
    '<div class="libgrid">' + (all ? r.books : r.books.slice(0, 12)).map(card).join('') + '</div>' +
    (!all && r.books.length > 12 ? '<button class="btn" data-hc="wantall" style="align-self:flex-start">Show all ' + r.books.length + '</button>' : '');
};

/* ---------- clicks ---------- */
document.addEventListener('click', async e => {
  const b = e.target.closest('[data-hc]'); if (!b) return;
  const a = b.dataset.hc, id = b.dataset.id;
  try {
    if (a === 'find') find(id);
    else if (a === 'link') { await api('/api/hardcover/book/' + encodeURIComponent(id) + '/link', { method: 'POST', body: JSON.stringify({ hc_book_id: +b.dataset.hid }) }); toast('Linked to Hardcover'); HC.section(id); }
    else if (a === 'add') { await api('/api/hardcover/book/' + encodeURIComponent(id), { method: 'PUT', body: JSON.stringify({ status_id: +b.dataset.s }) }); toast('On your Hardcover shelves'); HC.section(id); }
    else if (a === 'finish') HC.finish(id, (document.querySelector('.btitle') || {}).textContent, () => HC.section(id));
    else if (a === 'wantall') { HC.wantAll = true; HC.shelf(b.closest('section')); }
    else if (a === 'done') HC.finish(id, b.dataset.title, () => C.load && C.load());
    else if (a === 'notyet') { await api('/api/hardcover/book/' + encodeURIComponent(id) + '/notyet', { method: 'POST' }); b.closest('.notice').remove(); }
  } catch(err){ toast(err.message); }
});
document.addEventListener('click', async e => {
  const r = e.target.closest('[data-hcrate]'); if (!r) return;
  const v = starValue(r, e); if (v == null) return;
  const id = r.dataset.hcrate;
  r.innerHTML = stars(v, true);
  try { await api('/api/hardcover/book/' + encodeURIComponent(id), { method: 'PUT', body: JSON.stringify({ rating: v }) }); toast(v + ' stars on Hardcover'); }
  catch(err){ toast(err.message); }
});
document.addEventListener('change', async e => {
  const s = e.target.closest('[data-hcstatus]'); if (!s) return;
  const id = s.dataset.hcstatus, v = +s.value;
  if (v === 3) { HC.finish(id, (document.querySelector('.btitle') || {}).textContent, () => HC.section(id)); HC.section(id); return; }
  try { await api('/api/hardcover/book/' + encodeURIComponent(id), { method: 'PUT', body: JSON.stringify({ status_id: v }) }); toast(STATUS.find(x => x[0] === v)[1] + ', on Hardcover'); HC.section(id); }
  catch(err){ toast(err.message); }
});
document.addEventListener('submit', e => { const f = e.target.closest('.hcq'); if (!f) return; e.preventDefault(); find(f.dataset.id, f.querySelector('input').value.trim()); });

/* ---------- Today: the Kindle reached the end ---------- */
HC.todayNotice = d => (d.hc_finished || []).map(b => '<div class="notice"><span style="color:var(--accent)">' + C.I.books + '</span><span style="flex:1">You reached the end of <b>' + esc(shortTitle(b.title)) + '</b> on the Kindle. Mark it read on Hardcover?</span>' +
  '<span style="display:flex;gap:6px;flex-wrap:wrap"><button class="btn sm primary" data-hc="done" data-id="' + esc(b.id) + '" data-title="' + esc(b.title) + '">Mark it read</button><button class="btn sm" data-hc="notyet" data-id="' + esc(b.id) + '">Not yet</button></span></div>').join('');

/* ---------- Preferences ---------- */
HC.prefs = async box => {
  if (!box) return;
  let r;
  try { r = await api('/api/hardcover'); } catch(e){ box.innerHTML = '<h2>Hardcover</h2><p class="mute">' + esc(e.message) + '</p>'; return; }
  if (!r.connected) { box.innerHTML = '<h2>Hardcover</h2><p class="mute" style="margin:0">Not connected: Daf needs HARDCOVER_API_KEY in the vault’s settings file (see docs/OPERATIONS.md).</p>'; return; }
  const s = C.S.settings || {};
  const sw = (k, label, desc) => '<div class="prow"><div class="d"><b>' + label + '</b><span>' + desc + '</span></div><input type="checkbox" class="sw" data-hcset="' + k + '"' + (s[k] !== false ? ' checked' : '') + ' aria-label="' + esc(label) + '"></div>';
  const c = r.counts || {};
  box.innerHTML = '<h2>Hardcover</h2><div class="prow"><div class="d"><b>@' + esc(r.user) + '</b><span>' + ['Want to read', 'Reading', 'Read', 'Paused', 'Did not finish'].filter(k => c[k]).map(k => c[k] + ' ' + k.toLowerCase()).join(' · ') + '. ' + r.linked + ' of your books are linked, through the vault notes.</span></div></div>' +
    sw('hc_progress', 'Send progress from Daf’s reader', 'Forward only, never to a book you’ve finished. The Kindle’s progress already goes up through the vault’s own Hardcover sync.') +
    sw('hc_autostart', 'Start books as Reading', 'A Want to read book you begin in Daf moves to Reading on Hardcover.') +
    (r.last ? '<p class="mute tiny" style="margin:0">Last sent ' + C.ago(r.last.at) + ': ' + r.last.items.map(x => esc(x.did)).join(', ') + '</p>' : '');
};
document.addEventListener('change', async e => {
  const t = e.target.closest('[data-hcset]'); if (!t) return;
  try { const s = await api('/api/settings', { method: 'PUT', body: JSON.stringify({ [t.dataset.hcset]: t.checked }) }); C.S.settings = s; toast('Saved'); }
  catch(err){ toast(err.message); }
});
})();
