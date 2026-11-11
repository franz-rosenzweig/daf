/* The Audiobooks page and an audiobook's own page: Audiobookshelf's books (absapi.py) in Daf.

   #podcasts/audiobooks                   All (what you're in the middle of, then every book), or the
                                          books by Series, Authors, Narrators or Collections, as cards
                                          with their covers fanned
   #podcasts/audiobooks/in/<by>/<name>    one series (in its order), author, narrator or collection
   #podcasts/audiobooks/<item>            an audiobook: Play, Read along (its book in Daf), Bookmark;
                                          its Chapters, Bookmarks, Details (Find details from ABS's own
                                          match providers, and Use) and Files; the player's speed, sleep
                                          timer and skip; the last seven days' listening; its collections

   What you keep is kept in Audiobookshelf itself, through the API its own apps use (bookmarks,
   collections, finished, details), so they see it too. The speed, the sleep timer and the skip are the
   player's (player.js), for whatever plays. */
(() => {
'use strict';
const C = window.DafCore, { api, esc, toast, $, $$, I } = C;
const Pl = C.Player, A = C.Audiobooks;
const enc = encodeURIComponent;
const store = { get(k, d){ try { const v = localStorage.getItem('daf.' + k); return v == null ? d : JSON.parse(v); } catch(e){ return d; } }, set(k, v){ try { localStorage.setItem('daf.' + k, JSON.stringify(v)); } catch(e){} } };
const pref = (k, d) => store.get('pod.' + k, d), setPref = (k, v) => store.set('pod.' + k, v);
const coll = new Intl.Collator(undefined, { numeric: true, sensitivity: 'base' });
const BY = [['all', 'All'], ['series', 'Series'], ['authors', 'Authors'], ['narrators', 'Narrators'], ['collections', 'Collections']];
const SORTS = [['recent', 'Recent'], ['az', 'A–Z']];
const SLEEPS = [[0, 'Off'], [15, '15 min'], [30, '30 min'], [-1, 'End of chapter']];
const SKIPS = [[10, '10 s'], [15, '15 s'], [30, '30 s']];
const ICON = {
  play: '<svg width="18" height="18" viewBox="0 0 20 20" aria-hidden="true"><path d="M6.5 4.2v11.6L16 10z" fill="currentColor"/></svg>',
  pause: '<svg width="18" height="18" viewBox="0 0 20 20" aria-hidden="true"><rect x="5" y="4" width="3.4" height="12" rx="1" fill="currentColor"/><rect x="11.6" y="4" width="3.4" height="12" rx="1" fill="currentColor"/></svg>',
  pen: '<svg width="18" height="18" viewBox="0 0 20 20" aria-hidden="true"><path d="M4 16l1-4 8-8 3 3-8 8zM11.5 5.5l3 3" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/></svg>',
  bin: '<svg width="18" height="18" viewBox="0 0 20 20" aria-hidden="true"><path d="M4.5 6h11M8 6V4.5h4V6M6 6l.8 10h6.4L14 6" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  more: '<svg width="20" height="20" viewBox="0 0 20 20" aria-hidden="true"><circle cx="4.5" cy="10" r="1.6" fill="currentColor"/><circle cx="10" cy="10" r="1.6" fill="currentColor"/><circle cx="15.5" cy="10" r="1.6" fill="currentColor"/></svg>',
};
const X = { tab: 'chapters', found: null, sleepPick: 0 };

/* ---------- pieces ---------- */
const img = (item, cls) => '<img class="' + cls + '" src="/api/abs/cover/' + esc(enc(item)) + '" alt="" loading="lazy" onerror="this.outerHTML=DafCore.PodArt(\'' + cls + '\')">';
const hms = t => { t = Math.max(0, Math.floor(t || 0)); const h = Math.floor(t / 3600), m = Math.floor(t % 3600 / 60), s = t % 60; return (h ? h + ':' + String(m).padStart(2, '0') : m) + ':' + String(s).padStart(2, '0'); };
const len = s => { const m = Math.round((s || 0) / 60); return m >= 60 ? Math.floor(m / 60) + ' h' + (m % 60 ? ' ' + (m % 60) + ' min' : '') : Math.max(m ? 1 : 0, m) + ' min'; };
const size = b => b >= 1e9 ? (b / 1e9).toFixed(1) + ' GB' : b >= 1e6 ? Math.round(b / 1e6) + ' MB' : Math.max(1, Math.round(b / 1e3)) + ' KB';
const chips = (name, opts, cur, cls) => '<div class="pcchips' + (cls ? ' ' + cls : '') + '" role="radiogroup">' + opts.map(o => { const on = String(o[0]) === String(cur);
  return '<button type="button" role="radio" aria-checked="' + on + '" class="pcchip' + (on ? ' on' : '') + '" data-ab="' + name + '" data-v="' + esc(o[0]) + '">' + o[1] + '</button>'; }).join('') + '</div>';
const seg = (name, opts, cur) => '<div class="seg sm pcseg" role="radiogroup">' + opts.map(o => '<button type="button" role="radio" aria-checked="' + (o[0] === cur) + '" class="' + (o[0] === cur ? 'on' : '') + '" data-ab="' + name + '" data-v="' + esc(o[0]) + '">' + o[1] + '</button>').join('') + '</div>';
const playing = item => Pl.is(A.key(item)) && Pl.playing();
const playBtn = (item, label) => { const id = A.key(item), on = playing(item);
  return '<button class="pcplay' + (on ? ' on' : '') + '" data-plid="' + esc(id) + '" data-abplay="' + esc(item) + '" data-abep="" aria-label="' + esc(label || 'Play') + '">' + (on ? ICON.pause : ICON.play) + '</button>'; };
const empty = t => '<div class="empty"><b>' + t + '</b></div>';
const loading = '<span class="mute">Loading…</span>';
const top = (title, id) => '<div class="top"><button class="ib" data-ab="back" aria-label="Back">' + I.back + '</button><h1' + (id ? ' id="' + id + '"' : '') + ' dir="auto">' + esc(title) + '</h1><span class="spacer"></span></div>';
const abs = () => X.x ? Promise.resolve(X.x) : api('/api/abs').then(x => (X.x = x));
// Where you are now: the player's place when it's this book, else what ABS has.
const here = b => Pl.is(A.key(b.item)) ? Pl.time() : b.at || 0;
const chapterAt = (b, t) => { let k = -1; b.chapters.forEach((c, i) => { if (c.t <= t + 0.5) k = i; }); return k; };

// A book's tile: its cover (with how far you are), its name, and its play button.
function tile(b, seq){
  const sub = b.done ? 'Finished' : b.at > 30 ? A.hm(b.duration - b.at) + ' left' : A.hm(b.duration);
  return '<div class="pctile abtile"><a class="pctilea" href="#podcasts/audiobooks/' + enc(b.item) + '"><span class="pctimgw">' + img(b.item, 'pctimg') +
    (b.pct && !b.done ? '<span class="pcbar on"><i style="width:' + b.pct + '%"></i></span>' : '') + '</span><b dir="auto">' + esc(b.title) + '</b>' +
    '<span class="mute tiny">' + esc([seq ? 'Book ' + seq : '', b.author, sub].filter(Boolean).join(' · ')) + '</span></a>' +
    '<div class="pctacts">' + playBtn(b.item, 'Listen') + '</div></div>';
}

/* ---------- the shelf ---------- */
// The books by one of what they have: a series (in its order), an author, a narrator or a collection.
function groups(x, by){
  const m = new Map(), other = [];
  x.audiobooks.forEach(b => {
    const keys = by === 'series' ? (b.series || []).map(s => [s.name, s.seq]) : by === 'authors' ? (b.authors || []).map(n => [n]) :
      by === 'narrators' ? (b.narrators || []).map(n => [n]) : (x.collections || []).filter(c => c.books.includes(b.item)).map(c => [c.name]);
    if (!keys.length) other.push(b);
    keys.forEach(([k, seq]) => { if (!m.has(k)) m.set(k, []); m.get(k).push(Object.assign({ seq }, b)); });
  });
  const out = [...m.entries()].map(([name, books]) => ({ name, books: by === 'series' ? books.sort((a, b) => (parseFloat(a.seq) || 0) - (parseFloat(b.seq) || 0)) : books }))
    .sort((a, b) => coll.compare(a.name, b.name));
  if (other.length && by === 'collections' && out.length) out.push({ name: 'Other', other: true, books: other });   // none at all: no cards, not one of everything
  return out;
}
function groupCard(by, g){
  const listening = g.books.some(b => !b.done && b.at > 30);
  return '<a class="card abgroup" href="#podcasts/audiobooks/in/' + by + '/' + enc(g.other ? '-' : g.name) + '"><span class="abfan n' + Math.min(3, g.books.length) + '">' +
    g.books.slice(0, 3).map(b => img(b.item, 'abfanimg')).join('') + '</span><b dir="auto">' + esc(g.name) + '</b>' +
    '<span class="mute tiny">' + g.books.length + (g.books.length === 1 ? ' book' : ' books') + (listening ? ' · listening' : '') + '</span></a>';
}
// The Audiobooks page (podcasts.js gives it its body and ABS's lists).
function cat(body, x){
  X.x = x; X.body = body;
  const by = pref('bookBy', 'all'), sort = pref('bookSort', 'recent');
  let h = '<div class="pctools">' + chips('by', BY, by) + '<span class="spacer"></span>' + (by === 'all' ? seg('sort', SORTS, sort) : '') + '</div>';
  if (!x.audiobooks.length) { body.innerHTML = h + empty('No audiobooks in Audiobookshelf'); return; }
  if (by === 'all') {
    const list = x.audiobooks.slice().sort(sort === 'az' ? (a, b) => coll.compare(a.title, b.title) : (a, b) => (b.last || 0) - (a.last || 0));
    const going = sort === 'recent' ? list.filter(b => !b.done && b.at > 30) : [];
    if (going.length) h += '<div class="findh">Continue</div><div class="pctiles books">' + going.map(b => tile(b)).join('') + '</div>';
    h += (going.length ? '<div class="findh">All ' + list.length + '</div>' : '') + '<div class="pctiles books">' + list.map(b => tile(b)).join('') + '</div>';
  } else {
    const gs = groups(x, by);
    h += gs.length ? '<div class="abgroups">' + gs.map(g => groupCard(by, g)).join('') + '</div>' : empty('None');
  }
  body.innerHTML = h;
}

// One series, author, narrator or collection.
async function group(by, name){
  $('#main').innerHTML = top(name === '-' ? 'Other' : name) + '<div class="page pcpage" id="abgroup">' + loading + '</div>';
  let x; try { x = await abs(); } catch(e){ $('#abgroup').innerHTML = '<p class="mute">' + esc(e.message) + '</p>'; return; }
  const g = groups(x, by).find(g => name === '-' ? g.other : g.name === name), el = $('#abgroup'); if (!el) return;
  el.innerHTML = g ? '<div class="pctiles books">' + g.books.map(b => tile(b, by === 'series' ? b.seq : '')).join('') + '</div>' : empty('None');
}

/* ---------- an audiobook ---------- */
async function book(item){
  X.item = item; X.page = null; X.found = null;
  $('#main').innerHTML = top('…', 'abt') + '<div class="page pcpage abpage" id="abpage">' + loading + '</div>';
  try { const p = await api('/api/abs/book/' + enc(item) + '/page'); if (X.item !== item) return; X.page = p; }
  catch(e){ const el = $('#abpage'); if (el) el.innerHTML = '<p class="mute">' + esc(e.message) + '</p>'; return; }
  $('#abt').textContent = X.page.title;
  if (!X.page.chapters.length && X.tab === 'chapters') X.tab = X.page.bookmarks.length ? 'marks' : 'details';
  draw();
}
function draw(){
  const b = X.page, el = $('#abpage'); if (!b || !el || X.item !== b.item) return;
  const tabs = [['chapters', 'Chapters'], ['marks', 'Bookmarks' + (b.bookmarks.length ? ' ' + b.bookmarks.length : '')], ['details', 'Details'], ['files', 'Files']];
  el.innerHTML = '<div class="abgrid"><div class="abmain"><div id="abhead">' + head(b) + '</div>' + chips('tab', tabs, X.tab, 'abtabs') +
    '<div class="card abrows" id="abrows">' + rows(b) + '</div></div><aside class="abside" id="abside">' + side(b) + '</aside></div>';
}
function head(b){
  const on = playing(b.item), at = here(b), pct = b.done ? 100 : b.duration ? Math.min(100, at / b.duration * 100) : 0;
  const ser = (b.series || []).map(s => s.name + (s.seq ? ' · Book ' + s.seq : '')).join(', ');
  return '<div class="pchead abhead">' + img(b.item, 'abcover') + '<div class="pcabout"><span class="pclab">Audiobook</span><h2 dir="auto">' + esc(b.title) + '</h2>' +
    (b.subtitle ? '<span class="mute" dir="auto">' + esc(b.subtitle) + '</span>' : '') +
    '<span class="abby" dir="auto">' + esc(b.authors.join(', ')) + (b.narrators.length ? ' · Read by ' + esc(b.narrators.join(', ')) : '') + '</span>' +
    '<span class="mute tiny" dir="auto">' + esc([ser, len(b.duration)].filter(Boolean).join(' · ')) + '</span>' +
    '<span class="pcprog abprog"><span class="pcbar"><i id="abbar" style="width:' + pct.toFixed(1) + '%"></i></span><span class="pcstate" id="ableft">' +
      (b.done ? 'Finished' : Math.round(pct) + '% · ' + len(b.duration - at) + ' left') + '</span></span>' +
    '<div class="pcacts"><button class="btn primary" data-ab="play">' + (on ? ICON.pause + 'Pause' : ICON.play + 'Play') + '</button>' +
      (b.book && b.readable ? '<button class="btn" data-ab="along">Read along</button>' : '') +
      '<button class="btn" data-ab="mark">Bookmark</button><button class="btn abmore" data-ab="more" aria-label="More">' + ICON.more + '</button></div></div></div>';
}
function rows(b){
  const row = (n, a, sub, right, attrs, cls, after) => '<div class="abrow' + (cls ? ' ' + cls : '') + '"><' + (attrs ? 'button class="abrowb" ' + attrs : 'div class="abrowb"') + '>' +
    '<span class="abn">' + n + '</span><span class="abt"><b dir="auto">' + a + '</b>' + (sub ? '<span class="mute tiny" dir="auto">' + sub + '</span>' : '') + '</span>' +
    (right ? '<span class="abr">' + right + '</span>' : '') + '</' + (attrs ? 'button' : 'div') + '>' + (after || '') + '</div>';
  if (X.tab === 'chapters') {
    if (!b.chapters.length) return empty('No chapters');
    const at = here(b), cur = b.done ? -1 : chapterAt(b, at), live = playing(b.item);
    return b.chapters.map((c, i) => {
      const pct = cur === i && c.end > c.t ? Math.round((at - c.t) / (c.end - c.t) * 100) : 0;
      return row(i + 1, esc(c.title || 'Chapter ' + (i + 1)), b.done || i < cur ? 'Done' : i === cur ? (live ? 'Playing · ' : '') + pct + '%' : '',
        len(c.end - c.t), 'data-ab="seek" data-t="' + c.t + '"', i === cur ? 'on' : '');
    }).join('');
  }
  if (X.tab === 'marks') {
    if (!b.bookmarks.length) return empty('No bookmarks');
    return b.bookmarks.map((m, i) => { const ch = b.chapters[chapterAt(b, m.t)];
      return row(i + 1, esc(m.title || (ch && ch.title) || 'Bookmark'), m.title && ch ? esc(ch.title) : '', hms(m.t), 'data-ab="seek" data-t="' + m.t + '"', '',
        '<button class="ib" data-ab="rename" data-t="' + m.t + '" aria-label="Rename">' + ICON.pen + '</button><button class="ib" data-ab="unmark" data-t="' + m.t + '" aria-label="Delete">' + ICON.bin + '</button>'); }).join('');
  }
  if (X.tab === 'files') {
    if (!b.files.length) return empty('No files');
    return b.files.map((f, i) => row(i + 1, esc(f.name), f.kind && f.kind !== 'audio' ? esc(f.kind[0].toUpperCase() + f.kind.slice(1)) : '', size(f.size))).join('');
  }
  // Details: what ABS has, then Find details from one of its providers, and Use.
  const d = [['Title', b.title], ['Subtitle', b.subtitle], ['Author', b.authors.join(', ')], ['Narrator', b.narrators.join(', ')],
    ['Series', (b.series || []).map(s => s.name + (s.seq ? ' #' + s.seq : '')).join(', ')], ['Year', b.year], ['Publisher', b.publisher],
    ['Genres', (b.genres || []).join(', ')], ['Language', b.language], ['ISBN', b.isbn], ['ASIN', b.asin]].filter(r => r[1]);
  const provs = X.providers || [{ value: pref('absProvider', 'audible'), text: '…' }];
  return '<dl class="abdl">' + d.map(r => '<div><dt>' + r[0] + '</dt><dd dir="auto">' + esc(r[1]) + '</dd></div>').join('') + '</dl>' +
    (b.description ? '<p class="pcdesc abdesc" dir="auto">' + esc(b.description) + '</p>' : '') +
    '<div class="abfind"><select class="field" id="abprov" aria-label="Where to look">' + provs.map(p => '<option value="' + esc(p.value) + '"' + (p.value === pref('absProvider', 'audible') ? ' selected' : '') + '>' + esc(p.text) + '</option>').join('') + '</select>' +
    '<button class="btn" data-ab="find">Find details</button></div>' +
    (X.found === 'loading' ? '<p class="mute">Looking…</p>' : Array.isArray(X.found) ? (X.found.length ? X.found.map((c, i) =>
      '<div class="abrow abcand">' + (c.cover ? '<img class="abcandimg" src="' + esc(c.cover) + '" alt="" loading="lazy" onerror="this.remove()">' : '') +
      '<span class="abt"><b dir="auto">' + esc(c.title) + '</b><span class="mute tiny" dir="auto">' + esc([c.author, c.year, c.narrator && 'Read by ' + c.narrator, c.publisher].filter(Boolean).join(' · ')) + '</span></span>' +
      '<button class="btn sm primary" data-ab="use" data-i="' + i + '">Use</button></div>').join('') : '<p class="mute">Nothing found</p>') : '');
}
function side(b){
  const sl = Pl.sleep(), sleepOn = sl === -1 ? -1 : sl > 0 ? (X.sleepPick > 0 ? X.sleepPick : 15) : 0;
  const days = b.week || [], most = Math.max(1, ...days.map(d => d.secs)), total = days.reduce((a, d) => a + d.secs, 0);
  return '<section class="card abcard"><span class="pclab">Player</span>' +
    '<div class="abspeed"><span>Speed</span><button class="ib abpm" data-ab="slower" aria-label="Slower">−</button><b id="abrate">' + (Math.round(Pl.rate() * 10) / 10).toFixed(1) + '×</b>' +
      '<button class="ib abpm" data-ab="faster" aria-label="Faster">+</button></div>' +
    '<span class="abl">Sleep timer</span>' + chips('sleep', b.chapters.length ? SLEEPS : SLEEPS.slice(0, 3), sleepOn) +
    '<span class="abl">Skip</span>' + chips('skip', SKIPS, Pl.skipLen()) + '</section>' +
    '<section class="card abcard"><div class="abweekh"><span class="pclab">This week</span><b>' + (total ? len(total) : '0 min') + '</b></div><div class="abweek">' +
      days.map(d => '<span class="abday" title="' + esc(len(d.secs)) + '"><i class="' + (d.secs ? 'on' : '') + '" style="height:' + (d.secs ? Math.max(6, Math.round(d.secs / most * 64)) : 4) + 'px"></i>' +
        '<span>' + new Date(d.day + 'T12:00:00').toLocaleDateString(undefined, { weekday: 'narrow' }) + '</span></span>').join('') + '</div></section>' +
    '<section class="card abcard"><span class="pclab">Collections</span><div class="pcchips abcols">' +
      b.collections.map(c => '<button type="button" class="pcchip' + (c.on ? ' on' : '') + '" data-ab="col" data-id="' + esc(c.id) + '" data-on="' + (c.on ? 1 : 0) + '" aria-pressed="' + c.on + '">' + (c.on ? '✓ ' : '') + esc(c.name) + '</button>').join('') +
      '<button type="button" class="pcchip" data-ab="newcol">+ New</button></div></section>';
}
// The page follows the player: Play or Pause, how far, which chapter.
let lastCh = null;
function follow(full){
  const b = X.page; if (!b || !$('#abpage')) return;
  const h = $('#abhead'); if (h && full) h.innerHTML = head(b);
  if (!Pl.is(A.key(b.item))) return;
  const at = here(b), pct = b.duration ? Math.min(100, at / b.duration * 100) : 0;
  const bar = $('#abbar'), left = $('#ableft');
  if (bar) bar.style.width = pct.toFixed(1) + '%';
  if (left && !b.done) left.textContent = Math.round(pct) + '% · ' + len(b.duration - at) + ' left';
  const ch = chapterAt(b, at);
  if (X.tab === 'chapters' && (full || ch !== lastCh)) { lastCh = ch; const r = $('#abrows'); if (r) r.innerHTML = rows(b); }
}
['play', 'pause'].forEach(ev => Pl.audio.addEventListener(ev, () => { follow(true); const s = $('#abside'); if (s && X.page) s.innerHTML = side(X.page); }));
window.addEventListener('daf-player', () => follow(true));
window.addEventListener('daf-player-sleep', () => { const s = $('#abside'); if (s && X.page) s.innerHTML = side(X.page); });
let lastT = 0;
window.addEventListener('daf-player-time', () => { const now = Date.now(); if (now - lastT > 3000) { lastT = now; follow(false); } });

// The collections changed: the shelf asks again (podcasts.js keeps its own copy until it hears this).
const shelfChanged = () => { X.x = null; window.dispatchEvent(new CustomEvent('daf-abs-place')); };
function more(btn){
  const b = X.page, p = $('#pop'), r = btn.getBoundingClientRect();
  p.innerHTML = '<div class="menu"><button data-ab="finished">' + (b.done ? 'Mark as not finished' : 'Mark as finished') + '</button>' +
    (b.book ? '<a href="#book/' + enc(b.book) + '" data-ab="close">The book’s page</a>' : '') + '</div>';
  p.hidden = false; p.style.right = 'auto'; p.style.bottom = 'auto';
  p.style.left = Math.max(8, Math.min(r.left, innerWidth - p.offsetWidth - 8)) + 'px';
  p.style.top = Math.max(8, Math.min(r.bottom + 6, innerHeight - p.offsetHeight - 8)) + 'px';
}
const post = (path, body) => api('/api/abs/book/' + enc(X.page.item) + '/' + path, { method: 'POST', body: JSON.stringify(body) });

document.addEventListener('click', async e => {
  const t = e.target.closest && e.target.closest('[data-ab]'); if (!t) return;
  const a = t.dataset.ab, b = X.page;
  try {
    if (a === 'by') { setPref('bookBy', t.dataset.v); if (X.body && X.x) cat(X.body, X.x); }
    else if (a === 'sort') { setPref('bookSort', t.dataset.v); if (X.body && X.x) cat(X.body, X.x); }
    else if (a === 'back') { if ((C.S.navs || 0) > 1) history.back(); else location.hash = 'podcasts/audiobooks'; }
    else if (!b) return;
    else if (a === 'tab') {
      X.tab = t.dataset.v; draw();
      if (X.tab === 'details' && !X.providers) { X.providers = (await api('/api/abs/providers')).providers; if (X.tab === 'details') draw(); }
    }
    else if (a === 'play') { if (Pl.is(A.key(b.item))) Pl.toggle(); else await A.play(b.item); }
    else if (a === 'along') { if (!playing(b.item)) await A.play(b.item); location.hash = 'ebook/' + enc(b.book); }
    else if (a === 'seek') await A.play(b.item, null, +t.dataset.t);
    else if (a === 'mark') {
      const at = Math.floor(here(b)), ch = b.chapters[chapterAt(b, at)];
      b.bookmarks = (await post('bookmark', { t: at, title: ch ? ch.title : '' })).bookmarks;
      X.tab = 'marks'; draw(); toast('Bookmark at ' + hms(at));
    }
    else if (a === 'rename') {
      const m = b.bookmarks.find(x => x.t === +t.dataset.t); if (!m) return;
      const name = prompt('Name the bookmark', m.title); if (name == null) return;
      b.bookmarks = (await post('bookmark', { t: m.t, title: name.trim(), op: 'edit' })).bookmarks; draw();
    }
    else if (a === 'unmark') {
      if (!confirm('Delete the bookmark at ' + hms(+t.dataset.t) + '?')) return;
      b.bookmarks = (await post('bookmark', { t: +t.dataset.t, op: 'drop' })).bookmarks; draw();
    }
    else if (a === 'more') { e.stopPropagation(); more(t); }
    else if (a === 'close') $('#pop').hidden = true;
    else if (a === 'finished') {
      $('#pop').hidden = true;
      await post('finished', { on: !b.done }); shelfChanged();
      toast(b.done ? 'Not finished' : 'Finished'); await book(b.item);
    }
    else if (a === 'slower' || a === 'faster') { const r = Pl.setRate(Pl.rate() + (a === 'faster' ? 0.1 : -0.1)); $('#abrate').textContent = (Math.round(r * 10) / 10).toFixed(1) + '×'; }
    else if (a === 'sleep') { X.sleepPick = +t.dataset.v; Pl.setSleep(+t.dataset.v); $('#abside').innerHTML = side(b); }
    else if (a === 'skip') { Pl.setSkip(+t.dataset.v); $('#abside').innerHTML = side(b); }
    else if (a === 'col') {
      t.disabled = true;
      b.collections = (await post('collection', { id: t.dataset.id, on: t.dataset.on !== '1' })).collections;
      shelfChanged(); $('#abside').innerHTML = side(b);
    }
    else if (a === 'newcol') {
      const name = (prompt('Name the collection') || '').trim(); if (!name) return;
      b.collections = (await post('collection', { name })).collections;
      shelfChanged(); $('#abside').innerHTML = side(b);
    }
    else if (a === 'find') {
      const prov = $('#abprov').value; setPref('absProvider', prov);
      X.found = 'loading'; $('#abrows').innerHTML = rows(b);
      const r = await api('/api/abs/book/' + enc(b.item) + '/find?provider=' + enc(prov));
      if (X.page === b) { X.found = r.results; if (X.tab === 'details') $('#abrows').innerHTML = rows(b); }
    }
    else if (a === 'use') {
      const c = Array.isArray(X.found) && X.found[+t.dataset.i]; if (!c) return;
      if (!confirm('Use these details for ' + b.title + ' in Audiobookshelf?')) return;
      t.disabled = true;
      const r = await post('use', { candidate: c });
      X.page = r.page; X.found = null; shelfChanged(); draw(); $('#abt').textContent = X.page.title;
      toast('Saved in Audiobookshelf');
    }
  } catch(err){ if (a === 'find') { X.found = []; if ($('#abrows') && X.tab === 'details') $('#abrows').innerHTML = rows(b); } toast(err.message); t.disabled = false; }
});
document.addEventListener('change', e => { if (e.target.id === 'abprov') setPref('absProvider', e.target.value); });
window.addEventListener('daf-abs-place', () => { X.x = null; });

C.AbShelf = { cat, group, book };
})();
