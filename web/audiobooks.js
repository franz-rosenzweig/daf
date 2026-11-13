/* Audiobookshelf in Daf (absapi.py): its audiobooks and its recordings play in Daf's player, and where
   you stop goes back to ABS as you listen (a playback session, the way ABS's own apps keep it), so ABS
   and its apps pick up where Daf left off, and the other way round.

   A book with its audiobook beside it (audiomap.py):
   - its page has Listen (where the audiobook is) and Listen from here (where you're reading);
   - opening the book after listening offers "In the audiobook you're at <chapter>. Go there?", and
     its … menu has Listen from here too.
   The server finds the one's place in the other: by the chapters that agree, then by hearing a few
   seconds of the audiobook and finding the words in the book, so it lands within a sentence or two.

   Prepare the audiobook (readalong.py), on the book's page, has the server hear the whole recording
   once and keep where every sentence is. From then on the book's own Listen plays the audiobook, marks
   the sentence being read and turns the page with it (book.js), and none of the above needs hearing. */
(() => {
'use strict';
const C = window.DafCore, { api, esc, toast, $ } = C;
const Pl = C.Player;
const hm = s => { s = Math.max(0, Math.round(s || 0)); const h = Math.floor(s / 3600), m = Math.floor(s % 3600 / 60); return h ? h + 'h ' + m + 'm' : m + 'm'; };
const A = C.Audiobooks = { book: {} };

/* ---------- playing, and where you stop going to ABS ---------- */
const key = (item, ep) => 'abs:' + item + (ep ? ':' + ep : '');
// The item the player takes (player.js): every file as one track, ABS's chapters, and a save that
// tells ABS where you are: on pause, on a jump, every minute while it plays, and when it stops.
function playerItem(p){
  let since = null, sent = 0;
  const post = (at, end, beacon) => {
    const now = Date.now(), listened = since ? (now - since) / 1000 : 0;
    since = Pl.playing() && !end ? now : null; sent = now;
    const body = { item: p.item, episode: p.episode || null, at: Math.max(0, at), listened, duration: Pl.total() || p.duration || null, end: !!end };
    if (beacon && navigator.sendBeacon) { navigator.sendBeacon('/api/abs/progress', new Blob([JSON.stringify(body)], { type: 'application/json' })); return; }
    fetch('/api/abs/progress', { method: 'POST', credentials: 'same-origin', keepalive: true, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }).catch(() => {});
  };
  return { id: key(p.item, p.episode), kind: p.kind, title: p.title, sub: p.sub, art: p.art, tracks: p.tracks, duration: p.duration, chapters: p.chapters,
    open: p.episode ? '#podcasts/abs/' + encodeURIComponent(p.item) : '#podcasts/audiobooks/' + encodeURIComponent(p.item),   // its own page (abshelf.js)
    save(ev, x){
      if (ev === 'play') { since = Date.now(); }
      else if (ev === 'tick') { if (Date.now() - sent > 60000) post(x.at); }
      else if (ev === 'seek') post(x.to);
      else if (ev === 'hidden') post(x.at, false, x.beacon);
      else if (ev === 'pause') post(x.at);
      else if (ev === 'ended' || ev === 'stop') post(x.at, true);
      window.dispatchEvent(new CustomEvent('daf-abs-place', { detail: { id: key(p.item, p.episode), at: x.at != null ? x.at : x.to } }));
    } };
}
// Play an audiobook or a recording (or go on with it if it's the one playing), from `at` or where ABS has you.
A.play = async (item, episode, at) => {
  const id = key(item, episode);
  if (Pl.is(id)) { if (at != null) Pl.seek(at); else Pl.toggle(); return; }
  const p = await api('/api/abs/play/' + encodeURIComponent(item) + (episode ? '?episode=' + encodeURIComponent(episode) : ''));
  Pl.play(playerItem(p), { at: at != null ? at : p.at || 0 });
};
A.key = key;
A.hm = hm;

/* ---------- a book's page (app.js renderBook): Listen, and Listen from here ---------- */
A.forBook = async b => {
  const row = $('#bacts'); if (!row || b.kind !== 'book') return;
  let x;
  try { x = await api('/api/abs/book/' + encodeURIComponent(b.id)); } catch(e){ return; }
  if (!x.item || !$('#bacts')) return;
  A.book[b.id] = x;
  const on = Pl.is(key(x.item)) && Pl.playing();
  row.insertAdjacentHTML('beforeend', '<button class="btn" data-abk="listen" data-book="' + esc(b.id) + '" data-item="' + esc(x.item) + '">' +
    (on ? 'Pause' : x.at > 30 && !x.done ? 'Listen · ' + hm(x.at) + ' of ' + hm(x.duration) : 'Listen') + '</button>' +
    (b.readable && x.reading ? '<button class="btn" data-abk="here" data-book="' + esc(b.id) + '" data-item="' + esc(x.item) + '">Listen from here</button>' : '') +
    (b.readable ? prepare(b.id, x.along) : ''));
  if (b.readable && x.reading) start(b.id);          // finding the place takes a few seconds: start before the tap
  if (b.readable && x.along && /queued|going/.test(x.along.state)) watch(b.id);
};
// Prepare the audiobook: the button, then how far the work is, then nothing (the book's Listen is the audiobook).
function prepare(bookId, al){
  if (!al || al.state === 'ready') return '';
  const at = ' data-abprep="' + esc(bookId) + '"';
  if (al.state === 'other') return '<button class="btn"' + at + ' disabled>The audiobook is another text</button>';
  if (al.state === 'queued' || al.state === 'going') return '<button class="btn"' + at + ' disabled>Preparing the audiobook · ' + Math.round((al.done || 0) * 100) + '%</button>';
  return '<button class="btn"' + at + ' data-abk="prepare" data-book="' + esc(bookId) + '"' + (al.error ? ' title="' + esc(al.error) + '"' : '') + '>Prepare the audiobook</button>';
}
const watching = {};
function watch(bookId){
  if (watching[bookId]) return;
  watching[bookId] = setInterval(async () => {
    const b = $('[data-abprep="' + CSS.escape(bookId) + '"]');
    if (!b) { clearInterval(watching[bookId]); delete watching[bookId]; return; }      // the page was left: it goes on without being watched
    let al; try { al = await api('/api/abs/book/' + encodeURIComponent(bookId) + '/along?status=1'); } catch(e){ return; }
    if (A.book[bookId]) A.book[bookId].along = al;
    if (!/queued|going/.test(al.state)) { clearInterval(watching[bookId]); delete watching[bookId]; }
    if (b.isConnected) b.outerHTML = prepare(bookId, al);
  }, 10000);
}
// Where in the audiobook a place in the book is (the server hears it to be sure); one ask a place.
const starts = {};
function start(bookId, place){
  const k = bookId + '|' + (place ? place.cfi : '');
  if (!starts[k]) starts[k] = api('/api/abs/book/' + encodeURIComponent(bookId) + '/start', { method: 'POST', body: JSON.stringify(Object.assign({ exact: true }, place || {})) })
    .catch(e => { delete starts[k]; throw e; });
  return starts[k];
}
async function listenFrom(bookId, item, place){
  const t = setTimeout(() => toast('Finding the place…'), 400);
  try {
    const r = await start(bookId, place);
    clearTimeout(t);
    await A.play(item, null, r.t);
    toast('From ' + (r.chapter ? r.chapter + ', ' : '') + hm(r.t) + ' in');
  } catch(e){ clearTimeout(t); toast(e.message); }
}

/* ---------- the book itself (book.js): the audiobook's place, offered; and Listen from here ---------- */
// After the book opens at your place: if you listened since, its place in the book, to go to.
window.addEventListener('daf-book-open', async e => {
  const { id, mine, at } = e.detail || {};
  const since = mine ? (mine.updated || mine.at || 0) : 0, frac = mine ? (mine.fraction || 0) : -1;
  let x;
  try { x = await api('/api/abs/book/' + encodeURIComponent(id) + (at ? '' : '?offer=1&since=' + since + '&fraction=' + frac)); } catch(err){ return; }
  if (!x.item) return;
  A.book[id] = x;
  // playing already (from its page, or the player): the page follows the narrator, as Listen does
  if (x.along && x.along.state === 'ready' && Pl.is(key(x.item)) && Pl.playing() && C.BookAlong && !C.BookAlong.on(id) && C.curBook && C.curBook() === id &&
      localStorage.getItem('daf.bookListen') !== '"voice"') { await C.BookAlong.follow(); return; }
  const box = $('#bnotice'); if (!x.offer || !box || !C.curBook || C.curBook() !== id) return;
  if (C.BookAlong && C.BookAlong.on(id)) return;        // the page is following it already (book.js)
  const n = document.createElement('div'); n.className = 'bnotice abnotice';
  n.innerHTML = 'In the audiobook you’re at ' + esc(x.offer.chapter || Math.round(x.offer.fraction * 100) + '%') + '. Go there?' +
    ' <button class="btn sm" data-abk="go">Go there</button><button class="btn sm" data-abk="stay">Stay here</button>';
  n.dataset.words = x.offer.words || ''; n.dataset.fraction = x.offer.fraction;
  box.append(n);
});
// The book's … menu (book.js openMore): Listen from here, when the book has its audiobook.
A.menu = bookId => A.book[bookId] && A.book[bookId].item ? '<button data-abk="herebook">The audiobook from here</button>' : '';

document.addEventListener('click', async e => {
  const b = e.target.closest && e.target.closest('[data-abk]'); if (!b) return;
  const a = b.dataset.abk;
  if (a === 'listen') {
    const id = key(b.dataset.item);
    if (Pl.is(id)) { Pl.toggle(); b.textContent = Pl.playing() ? 'Pause' : 'Listen'; return; }
    try { await A.play(b.dataset.item); b.textContent = 'Pause'; } catch(err){ toast(err.message); }
  } else if (a === 'here') listenFrom(b.dataset.book, b.dataset.item);
  else if (a === 'prepare') {
    b.disabled = true;
    try {
      const al = await api('/api/abs/book/' + encodeURIComponent(b.dataset.book) + '/along', { method: 'POST' });
      if (A.book[b.dataset.book]) A.book[b.dataset.book].along = al;
      b.outerHTML = prepare(b.dataset.book, al); watch(b.dataset.book);
    } catch(err){ b.disabled = false; toast(err.message); }
  }
  else if (a === 'herebook') {
    $('#pop').hidden = true;
    const id = C.curBook && C.curBook(), x = id && A.book[id], here = C.BookPlace && C.BookPlace.here();
    if (x && x.along && x.along.state === 'ready' && C.BookAlong && await C.BookAlong.start()) return;   // prepared: the page follows it
    if (x && here) listenFrom(id, x.item, here);
  } else if (a === 'go') {
    const n = b.closest('.abnotice'); n.remove();
    if (C.BookPlace) await C.BookPlace.go(n.dataset.words, +n.dataset.fraction);
  } else if (a === 'stay') b.closest('.abnotice').remove();
});
// The book page's Listen follows the player.
const follow = () => {
  const b = $('[data-abk="listen"]'); if (!b) return;
  if (Pl.is(key(b.dataset.item))) b.textContent = Pl.playing() ? 'Pause' : 'Listen';
};
['play', 'pause'].forEach(ev => Pl.audio.addEventListener(ev, follow));
window.addEventListener('daf-player', follow);
})();
