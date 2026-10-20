/* Shelves: Nathan's own groups of books (Mussar, Hebrew, a reading project), like BookOrbit's
   collections. On Books, a row of shelves; #shelf/<id> lists one; a book's page toggles which
   shelves it's on. They live in Daf (tables shelves, shelf_books). */
(() => {
const C = window.DafCore, { api, esc, toast, $, cover, shortTitle } = C;
const SH = C.Shelves = {};

function tile(s){
  const covers = s.covers.map(id => cover({ id, title: '', has_cover: id.startsWith('cal:') }, 'cv shc')).join('');
  return '<a class="shelf" href="#shelf/' + encodeURIComponent(s.id) + '"><span class="shstack">' + (covers || '<span class="shempty"></span>') + '</span>' +
    '<b>' + esc(s.name) + '</b><span class="mute tiny">' + s.count + ' book' + (s.count === 1 ? '' : 's') + (s.hardcover ? ' · Hardcover list' : '') + '</span></a>';
}

// The Books page: every shelf, and a way to start one.
SH.section = async box => {
  box = box || $('#shelfsec'); if (!box) return;
  let r;
  try { r = await api('/api/shelves'); } catch(e){ box.innerHTML = '<h2>Shelves</h2><p class="mute">' + esc(e.message) + '</p>'; return; }
  box.innerHTML = '<div class="cardh"><h2>Shelves</h2><span class="spacer"></span><button class="btn sm" data-shelf="new">New shelf</button></div>' +
    (r.shelves.length ? '<div class="shelves">' + r.shelves.map(tile).join('') + '</div>'
      : '<p class="mute" style="margin:0">Group books your way: a subject, a project, a year. Add a book from its page, or start a shelf here.</p>');
};

async function newShelf(book){
  const name = prompt('Name the shelf');
  if (!name || !name.trim()) return null;
  try { const r = await api('/api/shelves', { method: 'POST', body: JSON.stringify({ name: name.trim(), book: book || null }) }); toast('Shelf made'); return r; }
  catch(e){ toast(e.message); return null; }
}

// A book's page: the shelves it's on, as chips to switch on and off.
SH.forBook = async (b, box) => {
  box = box || $('#bshelves'); if (!box) return;
  const r = await api('/api/shelves');
  const on = new Set(b.shelves || []);
  box.innerHTML = '<div class="cardh"><h2>Shelves</h2></div><div class="shchips">' +
    r.shelves.map(s => '<button class="shchip' + (on.has(s.id) ? ' on' : '') + '" data-shelfbook="' + esc(s.id) + '" aria-pressed="' + on.has(s.id) + '"' +
      (s.hardcover ? ' title="Your Hardcover list: it changes there too"' : '') + '>' + esc(s.name) + (s.hardcover ? ' <span class="tiny mute">· Hardcover</span>' : '') + '</button>').join('') +
    '<button class="shchip add" data-shelf="newfor">+ New shelf</button></div>';
  box.onclick = async e => {
    const t = e.target.closest('[data-shelfbook]');
    if (t) {
      const id = t.dataset.shelfbook, was = on.has(id);
      try {
        await api('/api/shelves/' + encodeURIComponent(id) + '/books/' + encodeURIComponent(b.id), { method: was ? 'DELETE' : 'PUT' });
        was ? on.delete(id) : on.add(id); b.shelves = [...on];
        t.classList.toggle('on', !was); t.setAttribute('aria-pressed', !was);
        toast(was ? 'Off the shelf' : 'On the shelf');
      } catch(err){ toast(err.message); }
      return;
    }
    if (e.target.closest('[data-shelf="newfor"]')) { const x = await newShelf(b.id); if (x) { b.shelves = (b.shelves || []).concat([x.id]); SH.forBook(b, box); } }
  };
};

// One shelf.
C.views.shelf = async args => {
  const id = decodeURIComponent(args[0] || '');
  $('#main').innerHTML = '<div class="top"><a class="btn sm" href="#books">' + C.I.back + '</a><h1>Shelf</h1></div><div class="page"><span class="mute">Loading…</span></div>';
  let r;
  try { r = await api('/api/shelves/' + encodeURIComponent(id)); } catch(e){ $('#main .page').innerHTML = '<p class="mute">' + esc(e.message) + '</p>'; return; }
  $('#main .top h1').textContent = r.name;
  $('#main .top').insertAdjacentHTML('beforeend', '<span class="spacer"></span>' + (r.hardcover_url ? '<a class="btn sm" href="' + esc(r.hardcover_url) + '" target="_blank" rel="noopener">On Hardcover</a>' : '') +
    '<button class="btn sm" data-shelf="rename">Rename</button>' + (r.hardcover ? '' : '<button class="btn sm" data-shelf="delete">Delete</button>'));
  const rows = r.books.map(b => '<div class="bcell">' + C.bookRow(b, (b.highlights ? '<span class="tiny mute">' + b.highlights + ' highlights</span>' : '')) +
    '<span class="tiny rowacts">' + (b.readable ? '<a class="btn sm primary" href="#ebook/' + encodeURIComponent(b.id) + '">Read</a> ' : '') +
    '<button class="linkbtn" data-shelfout="' + esc(b.id) + '">Take off this shelf</button></span></div>').join('');
  $('#main .page').innerHTML = (r.hardcover ? '<p class="mute tiny" style="margin:0 0 10px">This shelf is your Hardcover list. Put a book on or take one off here and it changes there too; private books stay off it.</p>' : '') +
    '<section class="card">' + (r.books.length ? '<div class="bgrid">' + rows + '</div>'
    : '<p class="mute" style="margin:0">Nothing here yet. On a book’s page, under Shelves, switch this one on.</p>') + '</section>';
  $('#main').onclick = async e => {
    const a = e.target.closest('[data-shelf],[data-shelfout]'); if (!a) return;
    try {
      if (a.dataset.shelfout) { await api('/api/shelves/' + encodeURIComponent(id) + '/books/' + encodeURIComponent(a.dataset.shelfout), { method: 'DELETE' }); toast('Off the shelf'); C.views.shelf(args); }
      else if (a.dataset.shelf === 'rename') { const n = prompt('Rename the shelf', r.name); if (n && n.trim()) { await api('/api/shelves/' + encodeURIComponent(id), { method: 'PUT', body: JSON.stringify({ name: n.trim() }) }); C.views.shelf(args); } }
      else if (a.dataset.shelf === 'delete') { if (confirm('Delete the shelf “' + r.name + '”? The books stay in your library.')) { await api('/api/shelves/' + encodeURIComponent(id), { method: 'DELETE' }); toast('Shelf deleted'); location.hash = 'books'; } }
    } catch(err){ toast(err.message); }
  };
};

// "New shelf" on the Books page.
document.addEventListener('click', async e => {
  if (!e.target.closest('#shelfsec [data-shelf="new"]')) return;
  if (await newShelf()) SH.section();
});
})();
