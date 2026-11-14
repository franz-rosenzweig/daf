/* Send to Kindle: Calibre's Send to device for the chosen books in All books, with the Kindle as the
   device. Daf's Kindle queue (kindlequeue.py) holds them, and the Kindle's Daf plugin fetches them on
   its next Wi-Fi sync into the shelf picked here (the Kindle's own folders). Each book shows the
   format that goes (the file Daf reads, EPUB first) and whether it's on the Kindle already or waiting
   for it; those start unticked, and a book with no file is greyed out. The shelf used last is kept on
   this device. C.SendDevice.open(books) */
(() => {
'use strict';
const C = window.DafCore, { api, esc, toast, $ } = C;
const store = { get(k, d){ try { const v = localStorage.getItem('daf.' + k); return v == null ? d : JSON.parse(v); } catch(e){ return d; } }, set(k, v){ try { localStorage.setItem('daf.' + k, JSON.stringify(v)); } catch(e){} } };
const M = { books: [], plan: {}, shelves: [], shelf: store.get('sendShelf', ''), on: new Set(), busy: false, run: 0 };

function sheet(html){
  let s = $('#sdsheet');
  if (!s) { document.body.insertAdjacentHTML('beforeend', '<div class="beshade" id="sdshade"></div><div class="besheet sdsheet" id="sdsheet" role="dialog" aria-modal="true" aria-label="Send to Kindle"></div>'); s = $('#sdsheet'); }
  s.innerHTML = html; s.hidden = false; $('#sdshade').hidden = false;
  document.body.classList.add('beopen');
  return s;
}
function close(){
  if (M.busy) return;
  const s = $('#sdsheet'); if (s) s.hidden = true;
  const sh = $('#sdshade'); if (sh) sh.hidden = true;
  if (!$('#bedit') || $('#bedit').hidden) document.body.classList.remove('beopen');
  M.books = []; M.plan = {}; M.on = new Set(); M.run++;
}
async function open(books){
  M.books = (books || []).slice(); M.plan = {}; M.on = new Set(); M.busy = false;
  const run = ++M.run;
  sheet(head(true) + '<div class="bebody one sdbody"><p class="mute">Loading…</p></div>');
  let r;
  try { r = await api('/api/catalog/kindle?ids=' + M.books.map(b => b.calibre_id).join(',')); }
  catch(e){ if (run === M.run) close(); toast(e.message); return; }
  if (run !== M.run) return;
  M.shelves = r.shelves || [];
  if (!M.shelves.includes(M.shelf)) M.shelf = M.shelves.includes('Books') ? 'Books' : M.shelves[0] || 'Books';
  (r.books || []).forEach(x => { M.plan[x.id] = x; if (x.format && !x.kindle) M.on.add(x.id); });
  draw();
}
const n = () => M.books.filter(b => M.on.has(b.calibre_id)).length;
const head = busy => '<div class="behead"><h2>Send to Kindle</h2><span class="spacer"></span><button class="btn sm" data-sd="cancel">Cancel</button>' +
  '<button class="btn sm primary" data-sd="go"' + (busy || !n() ? ' disabled' : '') + '>' + (M.busy ? 'Sending…' : n() > 1 ? 'Send ' + n() : 'Send') + '</button></div>';
const cover = b => b.cover ? '<img src="/api/cover/' + encodeURIComponent(b.id) + '?v=' + (b.cover_v || 0) + '" alt="" loading="lazy">' : '<span class="befnc"></span>';
function state(p){
  if (!p || !p.format) return 'No file';
  const k = p.kindle;
  return esc(p.format) + (k ? ' · ' + (k.state === 'Waiting' ? 'Waiting' : 'On the Kindle') + (k.shelf ? ' · ' + esc(k.shelf) : '') : '');
}
function draw(){
  const dis = M.busy ? ' disabled' : '';
  const list = M.books.map(b => { const p = M.plan[b.calibre_id], ok = !!(p && p.format);
    return '<label class="sdrow' + (ok ? '' : ' off') + '"><input type="checkbox" data-sdb="' + b.calibre_id + '"' + (M.on.has(b.calibre_id) ? ' checked' : '') + (ok ? dis : ' disabled') + '>' + cover(b) +
      '<span class="befct"><b>' + esc(b.title) + '</b><span class="mute tiny">' + esc((b.authors || []).join(' & ')) + '</span></span>' +
      '<span class="sdfmt mute tiny">' + state(p) + '</span></label>'; }).join('');
  sheet(head(M.busy) + '<div class="bebody one sdbody">' +
    '<div class="berow"><span>Shelf</span><div class="bectl"><select class="field" data-sdshelf' + dis + '>' +
      M.shelves.map(s => '<option' + (s === M.shelf ? ' selected' : '') + '>' + esc(s) + '</option>').join('') + '</select></div></div>' +
    '<h3>' + M.books.length + ' book' + (M.books.length === 1 ? '' : 's') + '</h3><div class="sdlist">' + list + '</div></div>');
}
function sync(){
  const go = $('#sdsheet [data-sd="go"]'); if (!go) return;
  go.disabled = M.busy || !n(); go.textContent = M.busy ? 'Sending…' : n() > 1 ? 'Send ' + n() : 'Send';
}
async function send(){
  const ids = M.books.filter(b => M.on.has(b.calibre_id)).map(b => b.calibre_id);
  if (M.busy || !ids.length) return;
  M.busy = true; draw();
  try {
    const r = await api('/api/catalog/kindle', { method: 'POST', body: JSON.stringify({ ids, shelf: M.shelf }) });
    M.busy = false; close();
    const bad = (r.skipped || []).length;
    toast((r.queued === 1 ? 'Queued for the Kindle' : r.queued + ' queued for the Kindle') + (bad ? ' · ' + bad + ' without a file' : ''));
    if (C.Catalog) C.Catalog.reload();
  } catch(e){ M.busy = false; draw(); toast(e.message); }
}
document.addEventListener('click', e => {
  const t = e.target; if (!t.closest) return;
  if (t.closest('#sdshade')) { close(); return; }
  const a = t.closest('#sdsheet [data-sd]'); if (!a) return;
  if (a.dataset.sd === 'cancel') close();
  else if (a.dataset.sd === 'go' && !a.disabled) send();
});
document.addEventListener('change', e => {
  const t = e.target; if (!t.closest || !t.closest('#sdsheet')) return;
  if (t.hasAttribute('data-sdshelf')) { M.shelf = t.value; store.set('sendShelf', M.shelf); }
  else if (t.dataset.sdb) { const id = +t.dataset.sdb; if (t.checked) M.on.add(id); else M.on.delete(id); sync(); }
});
document.addEventListener('keydown', e => { if (e.key === 'Escape' && $('#sdsheet') && !$('#sdsheet').hidden) { e.stopPropagation(); close(); } }, true);

C.SendDevice = { open };
})();
