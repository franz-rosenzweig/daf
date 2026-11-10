/* Dragging books onto shelves and collections. In All books a row (or every chosen row, when it's
   one of them), and on Books and a shelf's page a book (data-dragbook). With a mouse, drag; with a
   finger or the pen, hold a moment and then drag (letting go without moving opens the row's menu in
   All books). While dragging, "Put on" opens at the side with every shelf (Daf's own, Hardcover
   lists, the Kindle's) and Calibre's Collections; the shelf tiles on Books take a drop too.
   C.DragBooks.sheet(books) is the same as a list to tick: All books' bar (Shelves) and row menu. */
(() => {
'use strict';
const C = window.DafCore, { api, esc, toast, $, $$ } = C;
const D = { shelves: null, colls: null, drag: null };
const PAGES = ['catalog', 'books', 'shelf'];
const calId = id => { const m = /^cal:(\d+)$/.exec(id || ''); return m ? +m[1] : null; };

async function lists(){
  const [s, c] = await Promise.all([api('/api/shelves'), api('/api/catalog/items?field=' + encodeURIComponent('#collections')).catch(() => null)]);
  D.shelves = s.shelves || [];
  D.colls = c ? c.items.map(x => x.name) : null;
}
const kind = s => s.kindle != null ? 'Kindle' : s.hardcover ? 'Hardcover' : '';

/* ---------- putting books somewhere ---------- */
async function onShelf(id, books, remove){
  const sh = (D.shelves || []).find(s => s.id === id) || { name: id };
  const r = await api('/api/shelves/' + encodeURIComponent(id) + '/books', { method: 'POST', body: JSON.stringify({ ids: books.map(b => b.id), remove: !!remove }) });
  const n = r.done, what = n === 1 && books.length === 1 ? '“' + books[0].title + '”' : n + ' book' + (n === 1 ? '' : 's');
  toast((remove ? what + ' off ' : what + ' on ') + sh.name + (r.failed.length ? ' · ' + r.failed.length + ' couldn’t be: ' + r.failed[0].error : '') +
    (!remove && r.kindle.length ? ' · on the Kindle at its next sync' : ''));
  return r;
}
async function inCollection(name, books){
  const ids = books.map(b => calId(b.id)).filter(x => x != null);
  if (!ids.length) { toast('Only books in Calibre have a collection'); return; }
  await api('/api/catalog/bulk', { method: 'POST', body: JSON.stringify({ ids, fields: { '#collections': name || null } }) });
  toast(name ? (ids.length === 1 ? '“' + books[0].title + '”' : ids.length + ' books') + ' in ' + name : 'Out of its collection');
}
async function newShelf(books){
  const name = (prompt('Name the shelf') || '').trim(); if (!name) return;
  const r = await api('/api/shelves', { method: 'POST', body: JSON.stringify({ name }) });
  await lists(); await onShelf(r.id, books);
}
// After a change, the page shows it.
function after(){
  const v = C.S.route[0];
  if (v === 'catalog' && C.Catalog) C.Catalog.reload();
  else if (v === 'books' && C.Shelves) C.Shelves.section();
  else if (v === 'shelf') window.dispatchEvent(new HashChangeEvent('hashchange'));
}

/* ---------- the drag ---------- */
function source(t){
  if (!PAGES.includes(C.S.route[0]) || t.closest('input,select,textarea,button,.catrs,[data-catsel],#pop,#bedit')) return null;
  const tr = t.closest('#catscroll tbody tr');
  if (tr && C.Catalog) return { el: tr, books: () => C.Catalog.dragBooks(tr) };
  const b = t.closest('[data-dragbook]');
  if (b) return { el: b, books: () => [{ id: b.dataset.dragbook, title: b.dataset.title || b.textContent.trim().split('\n')[0] }] };
  return null;
}
function dock(books){
  const cal = books.every(b => calId(b.id) != null);
  let el = $('#dbdock');
  if (!el) { document.body.insertAdjacentHTML('beforeend', '<div class="dbdock" id="dbdock" aria-hidden="true"></div><div class="dbghost" id="dbghost"></div>'); el = $('#dbdock'); }
  el.innerHTML = '<div class="dbh">Put on</div>' +
    '<div class="dbsec">' + (D.shelves || []).map(s => '<div class="dbt" data-dbshelf="' + esc(s.id) + '"><span>' + esc(s.name) + '</span>' + (kind(s) ? '<i>' + kind(s) + '</i>' : '') + '</div>').join('') +
    '<div class="dbt dbnew" data-dbnew="shelf"><span>New shelf</span></div></div>' +
    (cal && D.colls ? '<div class="dbh">Collection</div><div class="dbsec">' + D.colls.map(n => '<div class="dbt" data-dbcoll="' + esc(n) + '"><span>' + esc(n) + '</span></div>').join('') +
      '<div class="dbt dbnew" data-dbnew="coll"><span>New collection</span></div></div>' : '');
  el.classList.add('on');
  const g = $('#dbghost');
  g.textContent = books.length === 1 ? books[0].title : books.length + ' books';
  g.classList.add('on');
}
function target(x, y){
  const g = $('#dbghost'); if (g) g.style.display = 'none';
  const el = document.elementFromPoint(x, y);
  if (g) g.style.display = '';
  return el && el.closest && el.closest('[data-dbshelf],[data-dbcoll],[data-dbnew],[data-dropshelf]');
}
function move(x, y){
  const g = $('#dbghost'); if (g) { g.style.left = (x + 14) + 'px'; g.style.top = (y + 12) + 'px'; }
  const t = target(x, y);
  $$('.dbt.over,[data-dropshelf].over').forEach(e => { if (e !== t) e.classList.remove('over'); });
  if (t) t.classList.add('over');
}
function end(){
  const el = $('#dbdock'); if (el) el.classList.remove('on');
  const g = $('#dbghost'); if (g) g.classList.remove('on');
  $$('.over').forEach(e => e.classList.remove('over'));
  document.body.classList.remove('dragging');
  D.drag = null;
}
async function drop(x, y){
  const d = D.drag, t = target(x, y); end();
  if (!t || !d) return;
  try {
    if (t.dataset.dbshelf || t.dataset.dropshelf) await onShelf(t.dataset.dbshelf || t.dataset.dropshelf, d.books);
    else if (t.dataset.dbcoll) await inCollection(t.dataset.dbcoll, d.books);
    else if (t.dataset.dbnew === 'shelf') await newShelf(d.books);
    else if (t.dataset.dbnew === 'coll') { const n = (prompt('Name the collection') || '').trim(); if (n) await inCollection(n, d.books); }
    after();
  } catch(e){ toast(e.message); }
}
function start(src, x, y){
  const books = src.books(); if (!books.length) return false;
  D.drag = { books, src };
  document.body.classList.add('dragging');
  if (navigator.vibrate) navigator.vibrate(10);
  dock(books); move(x, y);
  if (!D.shelves) lists().then(() => { if (D.drag) dock(books); }).catch(() => {});
  return true;
}

// The pointer: a mouse drags once it moves; a finger or the pen holds first. Their scrolling is
// held back only while a drag is on (the touchmove below).
let P = null;
document.addEventListener('pointerdown', e => {
  if (e.button > 0 || D.drag) return;
  const src = source(e.target); if (!src) return;
  P = { src, x: e.clientX, y: e.clientY, id: e.pointerType, held: false, moved: false, timer: null };
  if (e.pointerType !== 'mouse') P.timer = setTimeout(() => { if (P && !P.moved) { P.held = true; start(P.src, P.x, P.y); } }, 450);
}, true);
document.addEventListener('pointermove', e => {
  if (!P) return;
  const far = Math.hypot(e.clientX - P.x, e.clientY - P.y) > 6;
  if (D.drag) { e.preventDefault(); move(e.clientX, e.clientY); P.lx = e.clientX; P.ly = e.clientY; P.moved = P.moved || far; return; }
  if (!far) return;
  if (P.id === 'mouse') { if (start(P.src, e.clientX, e.clientY)) { P.moved = true; P.lx = e.clientX; P.ly = e.clientY; e.preventDefault(); } }
  else { clearTimeout(P.timer); P = null; }                  // a finger that moves first is scrolling
}, true);
const up = e => {
  if (!P) return;
  clearTimeout(P.timer);
  const p = P; P = null;
  if (!D.drag) return;
  if (p.held && !p.moved) {                                  // held and let go: the row's menu, as before
    end();
    const tr = p.src.el.closest && p.src.el.closest('#catscroll tbody tr');
    if (tr && C.Catalog && C.Catalog.rowMenu) C.Catalog.rowMenu(tr, p.x, p.y);
    D.ate = Date.now();
    return;
  }
  D.ate = Date.now();
  if (e.type === 'pointercancel') { end(); return; }
  drop(p.lx != null ? p.lx : e.clientX, p.ly != null ? p.ly : e.clientY);         // a finger lifting off has no place of its own
};
document.addEventListener('pointerup', up, true);
document.addEventListener('pointercancel', up, true);
document.addEventListener('touchmove', e => { if (D.drag) e.preventDefault(); }, { passive: false, capture: true });
// The click that ends a drag isn't a click on the row or the link under it.
document.addEventListener('click', e => { if (D.ate && Date.now() - D.ate < 500) { e.preventDefault(); e.stopPropagation(); D.ate = 0; } }, true);
document.addEventListener('dragstart', e => { if (source(e.target)) e.preventDefault(); }, true);
document.addEventListener('contextmenu', e => { if (D.drag || (P && P.id !== 'mouse')) e.preventDefault(); }, true);
document.addEventListener('keydown', e => { if (e.key === 'Escape' && D.drag) { e.preventDefault(); P = null; end(); } }, true);

/* ---------- the same as a list to tick: All books' bar and row menu ---------- */
async function sheet(books, anchor){
  try { await lists(); } catch(e){ toast(e.message); return; }
  const n = books.length, cal = books.every(b => calId(b.id) != null);
  const on = s => books.filter(b => (b.shelf_ids || []).includes(s.id)).length;
  const coll = cal && D.colls ? [...new Set(books.map(b => b['#collections'] || ''))] : null;
  const p = $('#pop'); p.onclick = p.oninput = p.onkeydown = null;
  p.innerHTML = '<div class="menu catmenu dbmenu"><div class="fmh">' + (n === 1 ? esc(books[0].title) : n + ' books') + '</div><div class="ml">Shelves</div>' +
    D.shelves.map(s => { const k = on(s); return '<button data-dbtick="' + esc(s.id) + '" data-state="' + (k === n ? 'all' : k ? 'some' : '') + '"><i>' + (k === n ? '✓' : k ? '–' : '') + '</i><span>' + esc(s.name) + '</span>' + (kind(s) ? '<em>' + kind(s) + '</em>' : '') + '</button>'; }).join('') +
    '<button data-dbtick="+"><i></i>New shelf</button>' +
    (coll ? '<hr><div class="ml">Collection</div>' + ['', ...D.colls].map(c => '<button data-dbcolltick="' + esc(c) + '"><i>' + (coll.length === 1 && coll[0] === c ? '✓' : '') + '</i>' + (c ? esc(c) : 'None') + '</button>').join('') +
      '<button data-dbcolltick="+"><i></i>New collection</button>' : '') + '</div>';
  p.hidden = false; D.sheetBooks = books;
  if (matchMedia('(max-width:700px)').matches || !anchor) { p.style.left = ''; p.style.top = ''; if (!anchor) { p.style.left = Math.max(8, (innerWidth - p.offsetWidth) / 2) + 'px'; p.style.top = '12vh'; } return; }
  const r = anchor.getBoundingClientRect();
  p.style.left = Math.max(8, Math.min(innerWidth - p.offsetWidth - 8, r.right - p.offsetWidth)) + 'px';
  p.style.top = Math.max(8, Math.min(r.top - p.offsetHeight - 6, innerHeight - p.offsetHeight - 8)) + 'px';
}
document.addEventListener('click', async e => {
  const t = e.target.closest && e.target.closest('[data-dbtick],[data-dbcolltick]'); if (!t) return;
  e.stopPropagation();
  const books = D.sheetBooks || []; $('#pop').hidden = true;
  try {
    if (t.dataset.dbtick === '+') await newShelf(books);
    else if (t.dataset.dbtick) await onShelf(t.dataset.dbtick, books, t.dataset.state === 'all');
    else if (t.dataset.dbcolltick === '+') { const n = (prompt('Name the collection') || '').trim(); if (n) await inCollection(n, books); }
    else await inCollection(t.dataset.dbcolltick, books);
    after();
  } catch(err){ toast(err.message); }
});

C.DragBooks = { sheet, refresh: () => { D.shelves = null; } };
})();
