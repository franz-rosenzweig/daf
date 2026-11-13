/* The Podcasts tab (podcasts.py, absapi.py): what you're listening to, the shows you follow and their
   episodes, your recordings and audiobooks from Audiobookshelf (each its own category, never mixed
   with AntennaPod's shows), and your clips. The search in its bar (find.js) looks through your shows
   and episodes (titles, show notes, and what was said where there's a transcript), Audiobookshelf,
   and Apple's podcast directory for shows to follow and episodes to play.

   #podcasts                  Listening: what you're in the middle of, and what's new
   #podcasts/<category>       shows, episodes, recordings, audiobooks, clips
   #podcasts/add              Add a podcast: the directory's shows and episodes, and a feed by its address
   #podcasts/<feed>           a show: its picture, what it's about, Follow, Download, Mark all played,
                              and its episodes (each with its download)
   #podcasts/abs/<item>       one of Audiobookshelf's recordings, and its episodes
   #podcasts/audiobooks/…     an audiobook, or a series, author, narrator or collection (abshelf.js)

   A row's round button plays it in the player (player.js) without leaving the list; the row opens the
   episode's page (its transcript, chapters and clips). Recordings and audiobooks play from their row. */
(() => {
'use strict';
const C = window.DafCore, { api, esc, toast, $, $$, epochDate, ago, I } = C;
const Pl = C.Player;
const store = { get(k, d){ try { const v = localStorage.getItem('daf.' + k); return v == null ? d : JSON.parse(v); } catch(e){ return d; } }, set(k, v){ try { localStorage.setItem('daf.' + k, JSON.stringify(v)); } catch(e){} } };
const fmtT = t => { t = Math.max(0, Math.floor(t || 0)); const h = Math.floor(t / 3600), m = Math.floor(t % 3600 / 60), x = t % 60; return (h ? h + ':' + String(m).padStart(2, '0') : m) + ':' + String(x).padStart(2, '0'); };
const len = s => { const m = Math.round((s || 0) / 60); return !s ? '' : m >= 60 ? Math.floor(m / 60) + ' h' + (m % 60 ? ' ' + (m % 60) + ' min' : '') : Math.max(1, m) + ' min'; };
const enc = encodeURIComponent;
const ICON = {
  play: '<svg width="18" height="18" viewBox="0 0 20 20" aria-hidden="true"><path d="M6.5 4.2v11.6L16 10z" fill="currentColor"/></svg>',
  pause: '<svg width="18" height="18" viewBox="0 0 20 20" aria-hidden="true"><rect x="5" y="4" width="3.4" height="12" rx="1" fill="currentColor"/><rect x="11.6" y="4" width="3.4" height="12" rx="1" fill="currentColor"/></svg>',
  wave: '<svg width="22" height="22" viewBox="0 0 20 20" aria-hidden="true"><path d="M3 10h1.5M6.2 7v6M9.4 4.5v11M12.6 7v6M15.8 9v2" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>',
  ext: '<svg width="14" height="14" viewBox="0 0 20 20" aria-hidden="true"><path d="M8 4H4.5v11.5H16V12M11 4h5v5M16 4l-7 7" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  plus: '<svg width="16" height="16" viewBox="0 0 20 20" aria-hidden="true"><path d="M10 4v12M4 10h12" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>',
  lens: '<svg width="20" height="20" viewBox="0 0 20 20" aria-hidden="true"><circle cx="8.7" cy="8.7" r="5" fill="none" stroke="currentColor" stroke-width="1.8"/><path d="m12.6 12.6 3.6 3.6" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>',
  rss: '<svg width="16" height="16" viewBox="0 0 20 20" aria-hidden="true"><path d="M4.5 9a6.5 6.5 0 0 1 6.5 6.5M4.5 4.5a11 11 0 0 1 11 11" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/><circle cx="5" cy="15" r="1.5" fill="currentColor"/></svg>',
  dl: '<svg width="20" height="20" viewBox="0 0 20 20" aria-hidden="true"><path d="M10 4v9M6 9.5l4 4 4-4M5 16h10" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  dlon: '<svg width="20" height="20" viewBox="0 0 20 20" aria-hidden="true"><path d="M5 10.5l3.2 3.2L15 7" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  dlwait: '<svg width="20" height="20" viewBox="0 0 20 20" aria-hidden="true"><circle cx="10" cy="10" r="6.5" fill="none" stroke="currentColor" stroke-width="1.6" stroke-dasharray="3 2.6"/><path d="M10 6.8v4.2l2.4 1.6" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg>',
  dlgo: '<svg class="pcspin" width="20" height="20" viewBox="0 0 20 20" aria-hidden="true"><circle cx="10" cy="10" r="6.5" fill="none" stroke="currentColor" stroke-opacity=".25" stroke-width="2"/><path d="M10 3.5a6.5 6.5 0 0 1 6.5 6.5" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>',
};
const CATS = [['', 'Listening'], ['shows', 'Shows'], ['episodes', 'Episodes'], ['recordings', 'Recordings'], ['audiobooks', 'Audiobooks'], ['clips', 'Clips']];
const EP_FILTERS = [['', 'All'], ['unplayed', 'Unplayed'], ['progress', 'In progress'], ['played', 'Played'], ['transcribed', 'Transcribed'], ['clipped', 'Clipped']];
const ABS_FILTERS = EP_FILTERS.slice(0, 4);
const EP_SORTS = [['newest', 'Newest'], ['oldest', 'Oldest'], ['longest', 'Longest']];
// A show's own: Unplayed, All, Downloaded first; the rest only when it has some.
const FEED_FILTERS = [['unplayed', 'Unplayed'], ['', 'All'], ['downloaded', 'Downloaded'], ['progress', 'In progress'], ['played', 'Played'], ['transcribed', 'Transcribed'], ['clipped', 'Clipped']];
const DL_MODES = [['off', 'Off'], ['new', 'New episodes'], ['all', 'All']];
const ADD_SCOPES = [['shows', 'Shows'], ['episodes', 'Episodes']];
const SHOW_SORTS = [['recent', 'Recent'], ['az', 'A–Z'], ['unplayed', 'Unplayed']];
const P = { eps: new Map(), abs: null, kept: {} };
const coll = new Intl.Collator(undefined, { numeric: true, sensitivity: 'base' });
const pref = (k, d) => store.get('pod.' + k, d), setPref = (k, v) => store.set('pod.' + k, v);

/* ---------- pieces ---------- */
// A picture, or the waveform where there's none (or it doesn't come).
const noArt = cls => '<span class="' + cls + ' pcart0">' + ICON.wave + '</span>';
const art = (src, cls) => src ? '<img class="' + cls + '" src="' + esc(src) + '" alt="" loading="lazy" onerror="this.outerHTML=DafCore.PodArt(\'' + cls + '\')">' : noArt(cls);
C.PodArt = noArt;
const absArt = item => '/api/abs/cover/' + enc(item);
const playing = id => Pl.is(id) && Pl.playing();
const playBtn = (id, attrs, label) => '<button class="pcplay' + (playing(id) ? ' on' : '') + '" data-plid="' + esc(id) + '" ' + attrs + ' aria-label="' + esc(label || 'Play') + '">' + (playing(id) ? ICON.pause : ICON.play) + '</button>';
const prog = (at, dur, done) => {
  if (done) return '<span class="pcprog"><span class="pcbar"><i style="width:100%"></i></span><span class="pcstate">Played</span></span>';
  if (!(at > 15) || !dur) return '';
  return '<span class="pcprog"><span class="pcbar"><i style="width:' + Math.min(100, at / dur * 100).toFixed(1) + '%"></i></span><span class="pcstate">' + len(Math.max(0, dur - at)) + ' left</span></span>';
};
const segHTML = (name, opts, cur) => '<div class="seg sm pcseg" role="radiogroup">' + opts.map(o => '<button type="button" role="radio" aria-checked="' + (o[0] === cur) + '" class="' + (o[0] === cur ? 'on' : '') + '" data-pcset="' + name + '" data-v="' + esc(o[0]) + '">' + o[1] + '</button>').join('') + '</div>';
const chipsHTML = (name, opts, cur) => '<div class="pcchips" role="radiogroup">' + opts.map(o => '<button type="button" role="radio" aria-checked="' + (o[0] === cur) + '" class="pcchip' + (o[0] === cur ? ' on' : '') + '" data-pcset="' + name + '" data-v="' + esc(o[0]) + '">' + o[1] + '</button>').join('') + '</div>';
const mark = s => esc(s || '').replace(/\u0002/g, '<mark>').replace(/\u0003/g, '</mark>');

// An AntennaPod episode's row: the row opens its page, the round button plays it here.
function epRow(e, o){
  o = o || {};
  P.eps.set(e.audio, e);
  const id = e.doc ? 'ep:' + e.doc : 'epa:' + e.audio;
  const meta = [o.show !== false && e.show, e.published ? epochDate(e.published) : '', len(e.duration)].filter(Boolean).map(esc).join(' · ');
  const badges = (e.transcript ? '<span class="pcbadge">Transcript</span>' : '') + (e.clips ? '<span class="pcbadge">' + e.clips + (e.clips === 1 ? ' clip' : ' clips') + '</span>' : '');
  return '<div class="pcrow' + (e.done ? ' done' : '') + '"><button class="pcmain" data-pcopen="' + esc(e.audio) + '">' + (o.art === false ? '' : art(e.image, 'pcart')) +
    '<span class="pctext"><b dir="auto">' + esc(e.title || 'Episode') + '</b><span class="pcmeta">' + meta + badges + '</span>' +
    (e.snip ? '<span class="pcsnip" dir="auto">' + mark(e.snip) + '</span>' : '') + prog(e.at, e.duration, e.done) + '</span></button>' +
    (o.dl ? dlBtn(e) : '') + playBtn(id, 'data-pcplay="' + esc(e.audio) + '"') + '</div>';
}
// An episode's download (downloads.py): kept on the server, on its way, waiting, or not.
const DL = { done: ['dlon', 'Downloaded'], going: ['dlgo', 'Downloading'], queued: ['dlwait', 'Waiting to download'], failed: ['dl', 'Download again'] };
const dlBtn = e => { const d = DL[e.kept] || ['dl', 'Download'];
  return '<button class="ib pcdl' + (e.kept ? ' ' + e.kept : '') + '" data-pcdl="' + esc(e.audio) + '" data-st="' + esc(e.kept || '') + '" aria-label="' + d[1] + '" title="' + d[1] + '">' + ICON[d[0]] + '</button>'; };
// A recording's or an audiobook's row (Audiobookshelf): all of it plays.
function absRow(e, o){
  o = o || {};
  const ep = e.kind === 'audiobook' ? '' : e.id || '', id = C.Audiobooks.key(e.item, ep);
  const meta = [o.show !== false && e.show, e.published ? epochDate(e.published) : '', len(e.duration)].filter(Boolean).map(esc).join(' · ');
  const go = 'data-abplay="' + esc(e.item) + '" data-abep="' + esc(ep) + '"';
  return '<div class="pcrow' + (e.done ? ' done' : '') + '"><button class="pcmain" ' + go + '>' + (o.art === false ? '' : art(absArt(e.item), 'pcart')) +
    '<span class="pctext"><b dir="auto">' + esc(e.title || '') + '</b><span class="pcmeta">' + meta + (e.kind === 'audiobook' ? '<span class="pcbadge">Audiobook</span>' : '') + '</span>' +
    prog(e.at, e.duration, e.done) + '</span></button>' + playBtn(id, go) + '</div>';
}
// A tile: a link, or (go starting "data-") a button that plays.
const tile = (go, img, title, sub, extra) => {
  const inner = img + '<b dir="auto">' + esc(title) + '</b>' + (sub ? '<span class="mute tiny">' + sub + '</span>' : '');
  return '<div class="pctile">' + (go.startsWith('data-') ? '<button class="pctilea" ' + go + '>' + inner + '</button>' : '<a href="' + go + '" class="pctilea">' + inner + '</a>') + (extra || '') + '</div>';
};
// The first n, and More for the rest (a search's long lists).
function capped(items, n, fn, cls){
  const id = 'pcx' + (P.capN = (P.capN || 0) + 1);
  (P.rest = P.rest || {})[id] = items.slice(n).map(fn).join('');
  return '<div class="' + cls + '" id="' + id + '">' + items.slice(0, n).map(fn).join('') + '</div>' + (items.length > n ? '<button class="btn pcmore" data-pcrest="' + id + '">More</button>' : '');
}
const card = (title, body, right) => '<section class="card pccard"><div class="cardh"><h2>' + title + '</h2>' + (right || '') + '</div>' + body + '</section>';
const empty = t => '<div class="empty"><b>' + t + '</b></div>';
const loading = '<span class="mute">Loading…</span>';

// Kept answers draw at once, and the fresh one draws over them when it differs.
async function got(path, draw){
  const k = P.kept[path];
  if (k) draw(k, true);
  const d = await api(path);
  P.kept[path] = d;
  if (!k || JSON.stringify(k) !== JSON.stringify(d)) draw(d, false);
  return d;
}
const absData = () => P.abs || (P.abs = api('/api/abs').catch(e => { P.abs = null; return { recordings: [], audiobooks: [], going: [], error: e.message }; }));

/* ---------- the tab ---------- */
C.views.podcasts = async args => {
  const a = (args || []).map(decodeURIComponent);
  if (a[0] === 'abs' && a[1]) return absShow(a[1]);
  if (a[0] === 'add') return addPage();
  if (a[0] === 'audiobooks' && a[1]) return a[1] === 'in' ? C.AbShelf.group(a[2], a[3]) : C.AbShelf.book(a[1]);
  if (a[0] && !CATS.some(c => c[0] === a[0])) return showPage(a[0]);
  P.cat = a[0] || '';
  const add = ['', 'shows', 'episodes'].includes(P.cat) ? '<a class="btn primary pcadd" href="#podcasts/add" aria-label="Add a podcast">' + ICON.plus + '<span>Add a podcast</span></a>' : '';
  $('#main').innerHTML = '<div class="top"><h1>Podcasts</h1><span class="spacer"></span>' + C.Find.html('podcasts', 'Search podcasts', found, 350) + add + '</div>' +
    '<div class="page pcpage"><nav class="pccats" aria-label="Podcasts">' + CATS.map(c => '<a class="pccat' + (c[0] === P.cat ? ' on' : '') + '" href="#podcasts' + (c[0] ? '/' + c[0] : '') + '"' + (c[0] === P.cat ? ' aria-current="page"' : '') + '>' + c[1] + '</a>').join('') + '</nav>' +
    '<div id="pcbody">' + loading + '</div></div>';
  P.abs = null;
  if (C.Find.q('podcasts')) return found(C.Find.q('podcasts'));
  return drawCat();
};
function drawCat(){
  const nav = $('.pccats'); if (nav) nav.hidden = false;
  const f = { '': listening, shows: showsCat, episodes: episodesCat, recordings: recordingsCat, audiobooks: audiobooksCat, clips: clipsCat }[P.cat] || listening;
  return f().catch(e => { const b = $('#pcbody'); if (b) b.innerHTML = '<p class="mute">' + esc(e.message) + '</p>'; });
}
const body = () => $('#pcbody');

// Listening: what you're in the middle of, here and in Audiobookshelf, the last played first; then
// the newest episodes of the shows you follow, not yet played.
async function listening(){
  const [l, x, ov] = await Promise.all([api('/api/podcasts/listening'), absData(), api('/api/podcasts')]);
  if (!body() || P.cat !== '') return;
  const going = l.going.map(e => ({ t: e.last || 0, h: epRow(e) })).concat((x.going || []).map(e => ({ t: e.last || 0, h: absRow(e) })))
    .sort((a, b) => b.t - a.t).map(r => r.h);
  let h = '';
  if (!ov.device && !ov.subs.length) h += card('AntennaPod', '<a class="btn" href="#prefs/podcasts" style="align-self:flex-start">Preferences → Podcasts</a>');
  h += card('Continue', going.length ? capped(going, 10, x => x, 'pcrows') : '<p class="mute" style="margin:0">Nothing started.</p>');
  if (l.new.length) h += card('New', capped(l.new, 10, e => epRow(e), 'pcrows'), '<a class="linkbtn" href="#podcasts/episodes">All episodes</a>');
  h += '<p class="mute tiny pcsync">AntennaPod synced ' + ago(ov.last_sync) + (x.error ? ' · Audiobookshelf: ' + esc(x.error) : '') + '</p>';
  body().innerHTML = h;
}

// Shows: the ones you follow, by their newest episode, by name, or by how many you haven't played.
async function showsCat(){
  const sort = pref('showsSort', 'recent');
  await got('/api/podcasts/shows', d => {
    if (!body() || P.cat !== 'shows') return;
    const list = d.shows.slice().sort(sort === 'az' ? (a, b) => (a.title || '').localeCompare(b.title || '') : sort === 'unplayed' ? (a, b) => b.unplayed - a.unplayed : (a, b) => (b.newest || 0) - (a.newest || 0));
    body().innerHTML = '<div class="pctools">' + segHTML('showsSort', SHOW_SORTS, sort) + '<span class="spacer"></span><span class="mute tiny">' + list.length + ' shows</span></div>' +
      (list.length ? '<div class="pctiles">' + list.map(s => tile('#podcasts/' + enc(s.feed), art(s.image, 'pctimg'), s.title,
        esc([s.unplayed ? s.unplayed + ' unplayed' : '', s.newest ? epochDate(s.newest) : ''].filter(Boolean).join(' · ')))).join('') + '</div>' : empty('No shows yet'));
  });
}

// Episodes of every show you follow: All, Unplayed, In progress, Played, Transcribed, Clipped; by date or length.
async function episodesCat(){
  const flt = pref('epFilter', 'unplayed'), sort = pref('epSort', 'newest');
  P.offset = 0;
  const head = '<div class="pctools">' + chipsHTML('epFilter', EP_FILTERS, flt) + '<span class="spacer"></span>' + segHTML('epSort', EP_SORTS, sort) + '</div>';
  await got('/api/podcasts/episodes?filter=' + flt + '&sort=' + sort + '&limit=60', d => {
    if (!body() || P.cat !== 'episodes') return;
    body().innerHTML = head + '<p class="mute tiny pccount">' + d.total + (d.total === 1 ? ' episode' : ' episodes') + '</p>' +
      (d.episodes.length ? '<div class="pcrows" id="pceps">' + d.episodes.map(e => epRow(e)).join('') + '</div>' + (d.total > 60 ? '<button class="btn pcmore" data-pcmore="60">More</button>' : '') : empty('None'));
  });
}
async function moreEpisodes(b){
  const off = +b.dataset.pcmore, flt = pref('epFilter', 'unplayed'), sort = pref('epSort', 'newest');
  b.disabled = true;
  const d = await api('/api/podcasts/episodes?filter=' + flt + '&sort=' + sort + '&limit=60&offset=' + off);
  $('#pceps').insertAdjacentHTML('beforeend', d.episodes.map(e => epRow(e)).join(''));
  if (off + 60 < d.total) { b.dataset.pcmore = off + 60; b.disabled = false; } else b.remove();
}

// Recordings: Audiobookshelf's podcast libraries, added by hand: their sets, by when you last listened, by name, or unplayed.
async function recordingsCat(){
  const x = await absData(); if (!body() || P.cat !== 'recordings') return;
  const sort = pref('recSort', 'recent');
  if (x.error) { body().innerHTML = '<p class="mute">Audiobookshelf: ' + esc(x.error) + '</p>'; return; }
  if (!x.recordings.length) { body().innerHTML = empty('No podcast library in Audiobookshelf'); return; }
  const by = sort === 'az' ? (a, b) => a.title.localeCompare(b.title) : sort === 'unplayed' ? (a, b) => (b.count - b.played) - (a.count - a.played) : (a, b) => (b.last || b.added || 0) - (a.last || a.added || 0);
  body().innerHTML = '<div class="pctools">' + segHTML('recSort', SHOW_SORTS, sort) + '</div>' + x.recordings.map(lib =>
    (x.recordings.length > 1 ? '<div class="findh">' + esc(lib.name) + '</div>' : '') + '<div class="pctiles">' + lib.shows.slice().sort(by).map(s =>
      tile('#podcasts/abs/' + enc(s.item), art(absArt(s.item), 'pctimg'), s.title, esc([s.author, s.count + (s.count === 1 ? ' episode' : ' episodes'), s.played ? s.played + ' played' : ''].filter(Boolean).join(' · ')))).join('') + '</div>').join('');
}

// Audiobooks: Audiobookshelf's, all of them or by series, author, narrator or collection (abshelf.js).
async function audiobooksCat(){
  const x = await absData(); if (!body() || P.cat !== 'audiobooks') return;
  if (x.error) { body().innerHTML = '<p class="mute">Audiobookshelf: ' + esc(x.error) + '</p>'; return; }
  C.AbShelf.cat(body(), x);
}

// Clips: highlights on episodes (and the older clip-only ones).
async function clipsCat(){
  const p = await api('/api/podcasts'); if (!body() || P.cat !== 'clips') return;
  body().innerHTML = p.clips.length ? card('Clips', p.clips.map(c => {
    const pos = (() => { try { return JSON.parse(c.pos).t; } catch(e){ return null; } })();
    const href = c.doc ? '#read/' + enc(c.doc) + (pos != null ? '/t:' + Math.max(0, Math.floor(pos) - 30) : '') : null;
    return '<div class="hlc"><q dir="auto">' + esc(c.text) + '</q><div class="meta tiny mute">' + (href ? '<a href="' + href + '">' : '') + esc(c.title || '') + (href ? '</a>' : '') +
      (c.author ? ' · ' + esc(c.author) : '') + (pos != null ? ' · ' + fmtT(pos) : '') + ' · ' + epochDate(c.created) + '</div></div>'; }).join(''), '<span class="mute tiny">' + p.clips.length + '</span>') : empty('No clips yet');
}

/* ---------- the search ---------- */
// Yours first (shows, episodes, Audiobookshelf), then the directory's shows and episodes as they come.
async function found(q){
  const nav = $('.pccats');
  if (!q) { if (nav) nav.hidden = false; return drawCat(); }
  if (nav) nav.hidden = true;
  const b = body(); if (!b) return;
  b.innerHTML = '<div id="pcmine">' + loading + '</div><div id="pcdir"></div>';
  const live = () => C.Find.q('podcasts') === q && body();
  const [mine, abs] = await Promise.all([api('/api/podcasts/search?q=' + enc(q)), api('/api/abs/search?q=' + enc(q)).catch(() => ({ audiobooks: [], recordings: [], episodes: [] }))]);
  if (!live()) return;
  let h = '';
  if (mine.shows.length) h += card('Your shows', capped(mine.shows, 12, s => tile('#podcasts/' + enc(s.feed), art(s.image, 'pctimg'), s.title, s.unplayed ? s.unplayed + ' unplayed' : ''), 'pctiles'));
  if (mine.episodes.length) h += card('Your episodes', capped(mine.episodes, 8, e => epRow(e), 'pcrows'), '<span class="mute tiny">' + mine.episodes.length + '</span>');
  if (abs.recordings.length || abs.episodes.length) h += card('Recordings', (abs.recordings.length ? capped(abs.recordings, 12, s => tile('#podcasts/abs/' + enc(s.item), art(absArt(s.item), 'pctimg'), s.title, esc(s.author || '')), 'pctiles') : '') +
    (abs.episodes.length ? capped(abs.episodes, 8, e => absRow(e), 'pcrows') : ''));
  if (abs.audiobooks.length) h += card('Audiobooks', '<div class="pcrows">' + abs.audiobooks.map(e => absRow(Object.assign({ kind: 'audiobook', show: e.author }, e))).join('') + '</div>');
  $('#pcmine').innerHTML = h || '';
  // The directory: shows to follow, episodes to play.
  $('#pcdir').innerHTML = card('Directory', loading);
  const [shows, eps] = await Promise.all(['shows', 'episodes'].map(k => api('/api/podcasts/directory?kind=' + k + '&q=' + enc(q)).then(r => r.results).catch(() => [])));
  if (!live()) return;
  const subs = new Set((P.kept['/api/podcasts/shows'] || { shows: [] }).shows.map(s => s.feed).concat(mine.shows.map(s => s.feed)));
  let d = '';
  if (shows.length) d += card('Shows in the directory', capped(shows, 12, s => tile('#podcasts/' + enc(s.feed), art(s.image, 'pctimg'), s.title, esc([s.author, s.count ? s.count + ' episodes' : ''].filter(Boolean).join(' · ')),
    '<div class="pctacts">' + followBtn(s.feed, subs.has(s.feed), 'sm') + '</div>'), 'pctiles'));
  if (eps.length) d += card('Episodes in the directory', capped(eps, 8, e => { e.found = true; return epRow(e); }, 'pcrows'));
  $('#pcdir').innerHTML = d;
  if (!h && !d) b.innerHTML = C.Find.none();
}
const followBtn = (feed, on, size) => '<button class="btn' + (size ? ' ' + size : '') + (on ? '' : ' primary') + '" data-pcfollow="' + esc(feed) + '" data-on="' + (on ? 1 : 0) + '">' + (on ? 'Following' : 'Follow') + '</button>';

/* ---------- Add a podcast ---------- */
// The directory's shows (Follow from the card) or episodes (play from the row); RSS link adds a feed by its address.
function addPage(){
  const scope = pref('addScope', 'shows');
  $('#main').innerHTML = '<div class="top"><button class="ib" data-pcback aria-label="Back">' + I.back + '</button><h1>Add a podcast</h1><span class="spacer"></span>' +
    '<button class="btn pcaddrss" data-pcrss aria-label="RSS link">' + ICON.rss + '<span>RSS link</span></button></div>' +
    '<div class="page pcpage pcaddpage"><label class="pcbigsearch">' + ICON.lens + '<input type="search" id="pcaddq" placeholder="Search podcasts" autocomplete="off" enterkeyhint="search" value="' + esc(P.addQ || '') + '"></label>' +
    chipsHTML('addScope', ADD_SCOPES, scope) + '<div id="pcaddres"></div></div>';
  const inp = $('#pcaddq');
  inp.addEventListener('input', () => { clearTimeout(P.addT); P.addT = setTimeout(() => addFind(inp.value.trim()), 400); });
  inp.addEventListener('keydown', e => { if (e.key === 'Enter') { clearTimeout(P.addT); addFind(inp.value.trim()); inp.blur(); } });
  if (!P.addQ && !matchMedia('(pointer:coarse)').matches) inp.focus();
  return addFind(P.addQ || '');
}
async function addFind(q){
  P.addQ = q;
  const res = $('#pcaddres'); if (!res) return;
  if (q.length < 2) { res.innerHTML = ''; return; }
  const scope = pref('addScope', 'shows');
  res.innerHTML = loading;
  let list, subs;
  try {
    [list, subs] = await Promise.all([api('/api/podcasts/directory?kind=' + scope + '&q=' + enc(q)).then(r => r.results),
      P.kept['/api/podcasts/shows'] ? Promise.resolve(P.kept['/api/podcasts/shows']) : api('/api/podcasts/shows').then(d => (P.kept['/api/podcasts/shows'] = d))]);
  } catch(e){ if ($('#pcaddres')) $('#pcaddres').innerHTML = '<p class="mute">' + esc(e.message) + '</p>'; return; }
  if (P.addQ !== q || pref('addScope', 'shows') !== scope || !$('#pcaddres')) return;
  const mine = new Set(subs.shows.map(s => s.feed));
  if (!list.length) { res.innerHTML = C.Find.none(); return; }
  res.innerHTML = scope === 'episodes' ? '<div class="card pcrows pclist">' + list.map(e => { e.found = true; return epRow(e); }).join('') + '</div>'
    : '<div class="pcfinds">' + list.map(s => '<div class="card pcfind"><a class="pcfinda" href="#podcasts/' + enc(s.feed) + '">' + art(s.image, 'pctimg') +
        '<b dir="auto">' + esc(s.title) + '</b><span class="mute" dir="auto">' + esc(s.author || '') + '</span>' +
        (s.count ? '<span class="mute tiny">' + s.count + (s.count === 1 ? ' episode' : ' episodes') + '</span>' : '') + '</a>' + followBtn(s.feed, mine.has(s.feed)) + '</div>').join('') + '</div>';
}

/* ---------- a show ---------- */
// What its feed says of it, Follow, and its episodes filtered and sorted; its own search filters them.
async function showPage(feed){
  const fk = P.showKey = 'podshow:' + feed;
  P.show = null;
  $('#main').innerHTML = '<div class="top"><button class="ib" data-pcback aria-label="Back">' + I.back + '</button><h1 id="pct" dir="auto">…</h1><span class="spacer"></span>' +
    C.Find.html(fk, 'Search this show', () => drawShow(), 150) + '</div><div class="page pcpage" id="pcshow">' + loading + '</div>';
  // What Daf knows of it at once (a show you follow has its episodes already), then the feed's latest.
  const put = x => { if (!$('#pcshow') || P.showKey !== fk) return; P.show = x; $('#pct').textContent = x.title || 'Podcast'; drawShow(); };
  const known = api('/api/podcasts/show?known=1&feed=' + enc(feed)).then(x => { if (x.episodes.length && !P.show) put(x); }).catch(() => {});
  try { const x = await api('/api/podcasts/show?feed=' + enc(feed)); await known; put(x); }
  catch(e){ if (!P.show) $('#pcshow').innerHTML = '<p class="mute">' + esc(e.message) + '</p>'; }
}
function drawShow(){
  const x = P.show, page = $('#pcshow'); if (!x || !page) return;
  const sort = pref('feedSort', 'newest'), q = C.Find.q(P.showKey);
  const test = { unplayed: e => e.at == null, progress: e => e.started, played: e => e.done, transcribed: e => e.transcript, clipped: e => e.clips > 0, downloaded: e => e.kept === 'done' };
  const n = k => k ? x.episodes.filter(test[k]).length : x.episodes.length;
  const chips = FEED_FILTERS.filter(f => ['unplayed', '', 'downloaded'].includes(f[0]) || n(f[0])).map(f => [f[0], f[0] ? f[1] : 'All ' + x.episodes.length]);
  let flt = pref('feedFilter', 'unplayed'); if (!chips.some(c => c[0] === flt)) flt = '';
  let eps = flt ? x.episodes.filter(test[flt]) : x.episodes.slice();
  if (q) eps = eps.filter(e => C.Find.match(q, e.title, e.notes));
  eps.sort(sort === 'oldest' ? (a, b) => (a.published || 0) - (b.published || 0) : sort === 'longest' ? (a, b) => (b.duration || 0) - (a.duration || 0) : (a, b) => (b.published || 0) - (a.published || 0));
  const site = x.link && /^https?:\/\//.test(x.link) ? '<a class="btn" href="' + esc(x.link) + '" target="_blank" rel="noopener">' + ICON.ext + 'Website</a>' : '';
  const head = '<div class="pchead">' + art(x.image, 'pcbig') + '<div class="pcabout"><h2 dir="auto">' + esc(x.title) + '</h2>' + (x.author ? '<span class="mute" dir="auto">' + esc(x.author) + '</span>' : '') +
    '<span class="mute tiny">' + [x.count + (x.count === 1 ? ' episode' : ' episodes'), x.updated ? 'updated ' + epochDate(x.updated) : ''].filter(Boolean).join(' · ') + '</span>' +
    '<div class="pcacts">' + followBtn(x.feed, x.following) +
      '<span class="pcdlset"><span class="pclab">Download</span>' + segHTML('feedDl', DL_MODES, x.download || 'off') + '</span>' +
      (x.episodes.some(e => !e.done) ? '<button class="btn" data-pcplayed>Mark all played</button>' : '') + site + '</div>' +
    (x.description ? '<p class="pcdesc" dir="auto">' + esc(x.description) + '</p>' + (x.description.length > 240 ? '<button class="linkbtn pcdmore" data-pcdesc>More</button>' : '') : '') + '</div></div>';
  const shown = eps.slice(0, P.showN || 80);
  page.innerHTML = head + '<div class="pctools">' + chipsHTML('feedFilter', chips, flt) + '<span class="spacer"></span>' + segHTML('feedSort', EP_SORTS, sort) + '</div>' +
    (shown.length ? '<div class="card pcrows pclist">' + shown.map(e => epRow(e, { show: false, art: false, dl: true })).join('') + '</div>' + (eps.length > shown.length ? '<button class="btn pcmore" data-pcshown>More</button>' : '') : q ? C.Find.none() : empty(x.error && !x.episodes.length ? 'The feed didn’t come: ' + esc(x.error) : 'None'));
  watchDl();
}
// While a show's downloads are on their way, the page asks how they're doing every few seconds.
function watchDl(){
  clearTimeout(P.dlT);
  const x = P.show; if (!x || !x.episodes.some(e => e.kept === 'queued' || e.kept === 'going')) return;
  const fk = P.showKey;
  P.dlT = setTimeout(async () => {
    if (P.showKey !== fk || !$('#pcshow')) return;
    try { const y = await api('/api/podcasts/show?known=1&feed=' + enc(x.feed)); if (P.showKey === fk && P.show) { P.show.episodes = y.episodes; drawShow(); } } catch(e){}
  }, 5000);
}

// One of Audiobookshelf's recordings: its episodes, filtered and sorted, each played from its row.
async function absShow(item){
  $('#main').innerHTML = '<div class="top"><button class="ib" data-pcback aria-label="Back">' + I.back + '</button><h1 id="pct" dir="auto">…</h1><span class="spacer"></span>' +
    C.Find.html('podabs', 'Search these', () => drawAbs(), 150) + '</div><div class="page pcpage" id="pcshow">' + loading + '</div>';
  try { P.absShow = await api('/api/abs/show/' + enc(item)); } catch(e){ $('#pcshow').innerHTML = '<p class="mute">' + esc(e.message) + '</p>'; return; }
  $('#pct').textContent = P.absShow.title;
  drawAbs();
}
function drawAbs(){
  const x = P.absShow, page = $('#pcshow'); if (!x || !page) return;
  const flt = pref('absFilter', ''), sort = pref('absSort', 'oldest'), q = C.Find.q('podabs');
  let eps = x.episodes.filter(e => ({ unplayed: !e.done && !(e.at > 15), progress: !e.done && e.at > 15, played: e.done }[flt] !== false));
  if (q) eps = eps.filter(e => C.Find.match(q, e.title, e.description));
  // Recordings often have no date: then by their number, then by title as a person would order them.
  const old = (a, b) => (a.published || 0) - (b.published || 0) || (parseFloat(a.number) || 0) - (parseFloat(b.number) || 0) || coll.compare(a.title, b.title);
  eps.sort(sort === 'newest' ? (a, b) => old(b, a) : sort === 'longest' ? (a, b) => (b.duration || 0) - (a.duration || 0) : old);
  const played = x.episodes.filter(e => e.done).length;
  const head = '<div class="pchead">' + art(absArt(x.item), 'pcbig') + '<div class="pcabout"><h2 dir="auto">' + esc(x.title) + '</h2>' + (x.author ? '<span class="mute" dir="auto">' + esc(x.author) + '</span>' : '') +
    '<span class="mute tiny">' + [x.episodes.length + (x.episodes.length === 1 ? ' episode' : ' episodes'), played ? played + ' played' : '', (x.genres || []).join(', ')].filter(Boolean).map(esc).join(' · ') + '</span>' +
    (x.description ? '<p class="pcdesc" dir="auto">' + esc(x.description) + '</p>' + (x.description.length > 240 ? '<button class="linkbtn pcdmore" data-pcdesc>More</button>' : '') : '') + '</div></div>';
  page.innerHTML = head + '<div class="pctools">' + chipsHTML('absFilter', ABS_FILTERS, flt) + '<span class="spacer"></span>' + segHTML('absSort', EP_SORTS, sort) + '</div>' +
    (eps.length ? '<div class="pcrows">' + eps.map(e => absRow(Object.assign({ item: x.item }, e), { show: false, art: false })).join('') + '</div>' : q ? C.Find.none() : empty('None'));
}

/* ---------- playing from a row ---------- */
async function playEp(audio){
  const e = P.eps.get(audio) || {};
  if (e.doc && Pl.is('ep:' + e.doc)) { Pl.toggle(); return; }
  if (e.found) await api('/api/podcasts/open', { method: 'POST', body: JSON.stringify({ audio, found: e }) });
  const r = await api('/api/podcasts/play?audio=' + enc(audio));
  e.doc = r.id; P.eps.set(audio, e);
  if (Pl.is('ep:' + r.id)) { Pl.toggle(); return; }
  const ep = r.episode, pos = ep.position, dur = ep.duration || 0;
  const at = pos && pos.t > 15 && (!dur || pos.t < dur - 30) ? pos.t : 0;
  Pl.play(C.Episode.item({ id: r.id, title: r.title, source: r.source, episode: ep }), { at });
}
async function openEp(audio){
  const e = P.eps.get(audio) || {};
  if (e.doc) { location.hash = 'read/' + enc(e.doc); return; }
  const r = await api('/api/podcasts/open', { method: 'POST', body: JSON.stringify(e.found ? { audio, found: e } : { audio }) });
  location.hash = 'read/' + enc(r.id);
}
// The round buttons follow the player: the one playing shows pause.
function marks(){
  $$('.pcplay[data-plid]').forEach(b => {
    const on = playing(b.dataset.plid);
    if (b.classList.contains('on') !== on) { b.classList.toggle('on', on); b.innerHTML = on ? ICON.pause : ICON.play; b.setAttribute('aria-label', on ? 'Pause' : 'Play'); }
  });
}
['play', 'pause', 'emptied'].forEach(ev => Pl.audio.addEventListener(ev, marks));
window.addEventListener('daf-player', e => {
  // An episode played from a row has its page's id now: the row's button knows it by that.
  const id = e.detail && e.detail.id, cur = Pl.cur;
  if (id && cur && cur.kind === 'episode' && cur.url) $$('.pcplay[data-pcplay]').forEach(b => { const x = P.eps.get(b.dataset.pcplay); if (x && x.doc && 'ep:' + x.doc === id) b.dataset.plid = id; });
  marks();
});

// Download on a show: Off, New episodes, All. All of a long show asks first.
async function setDownload(m){
  const x = P.show; if (!x) return;
  const missing = x.episodes.filter(e => !e.kept).length;
  if (m === 'all' && missing > 40 && !confirm('Download all ' + missing + ' episodes of ' + x.title + ' to the server?')) return;
  const r = await api('/api/podcasts/download', { method: 'POST', body: JSON.stringify({ feed: x.feed, mode: m }) });
  x.download = r.mode;
  const y = await api('/api/podcasts/show?known=1&feed=' + enc(x.feed));
  if (P.show === x) { x.episodes = y.episodes; drawShow(); }
  if (r.queued) toast(r.queued === 1 ? '1 episode on its way' : r.queued + ' episodes on their way');
}
// One episode's download: keep it, or let go of it (a kept one asks first).
async function keepEp(b){
  const audio = b.dataset.pcdl, st = b.dataset.st, keep = !st || st === 'failed';
  if (st === 'done' && !confirm('Remove the download?')) return;
  const r = await api('/api/podcasts/keep', { method: 'POST', body: JSON.stringify({ audio, keep }) });
  const e = P.show && P.show.episodes.find(x => x.audio === audio);
  if (e) { e.kept = r.kept; drawShow(); } else b.outerHTML = dlBtn(Object.assign(P.eps.get(audio) || { audio }, { kept: r.kept }));
}

document.addEventListener('click', async e => {
  const t = e.target.closest && e.target.closest('[data-pcplay],[data-pcopen],[data-abplay],[data-pcset],[data-pcfollow],[data-pcmore],[data-pcshown],[data-pcrest],[data-pcdesc],[data-pcback],[data-pcdl],[data-pcplayed],[data-pcrss]');
  if (!t) return;
  try {
    if (t.dataset.pcplay) await playEp(t.dataset.pcplay);
    else if (t.dataset.pcopen) await openEp(t.dataset.pcopen);
    else if (t.dataset.abplay) await C.Audiobooks.play(t.dataset.abplay, t.dataset.abep || null);
    else if (t.dataset.pcset === 'feedDl') await setDownload(t.dataset.v);
    else if (t.dataset.pcset === 'addScope') { setPref('addScope', t.dataset.v); $$('[data-pcset="addScope"]').forEach(b => { const on = b === t; b.classList.toggle('on', on); b.setAttribute('aria-checked', on); }); await addFind(P.addQ || ''); }
    else if (t.dataset.pcset) {
      setPref(t.dataset.pcset, t.dataset.v);
      if (/^feed/.test(t.dataset.pcset)) { P.showN = 80; drawShow(); }
      else if (/^abs/.test(t.dataset.pcset)) drawAbs();
      else drawCat();
    }
    else if (t.dataset.pcfollow) {
      const on = t.dataset.on !== '1';
      await api('/api/podcasts/follow', { method: 'POST', body: JSON.stringify({ feed: t.dataset.pcfollow, follow: on }) });
      t.outerHTML = followBtn(t.dataset.pcfollow, on, t.classList.contains('sm') ? 'sm' : '');
      delete P.kept['/api/podcasts/shows'];
      if (P.show && P.show.feed === t.dataset.pcfollow) P.show.following = on;
      if (on && P.show && P.show.feed === t.dataset.pcfollow && !P.show.episodes.length) showPage(P.show.feed);   // a feed added by its address: its episodes now
      toast(on ? 'Following' : 'Not following');
    }
    else if (t.dataset.pcmore) await moreEpisodes(t);
    else if ('pcshown' in t.dataset) { P.showN = (P.showN || 80) + 120; drawShow(); }
    else if (t.dataset.pcrest) { const box = $('#' + t.dataset.pcrest); if (box) box.insertAdjacentHTML('beforeend', P.rest[t.dataset.pcrest] || ''); t.remove(); }
    else if ('pcdesc' in t.dataset) { const d = t.previousElementSibling; d.classList.toggle('open'); t.textContent = d.classList.contains('open') ? 'Less' : 'More'; }
    else if ('pcback' in t.dataset) { if ((C.S.navs || 0) > 1) history.back(); else location.hash = 'podcasts/shows'; }
    else if (t.dataset.pcdl) await keepEp(t);
    else if ('pcplayed' in t.dataset) {
      const x = P.show; if (!x || !confirm('Mark every episode of ' + x.title + ' played?')) return;
      const r = await api('/api/podcasts/played', { method: 'POST', body: JSON.stringify({ feed: x.feed }) });
      toast(r.marked === 1 ? '1 episode marked played' : r.marked + ' episodes marked played');
      showPage(x.feed);
    }
    else if ('pcrss' in t.dataset) {
      const u = (prompt('The feed’s address') || '').trim(); if (!u) return;
      if (!/^https?:\/\/\S+$/.test(u)) { toast('That isn’t a feed’s address'); return; }
      location.hash = 'podcasts/' + enc(u);
    }
  } catch(err){ toast(err.message); }
});
// A show's list starts again at its top on a new show.
window.addEventListener('hashchange', () => { if (!/^#podcasts\/(?!shows|episodes|recordings|audiobooks|clips|add)/.test(location.hash)) { P.show = null; P.absShow = null; P.showN = 80; clearTimeout(P.dlT); } });
// Where you are in a recording or an audiobook changes its row: the lists ask again next time.
window.addEventListener('daf-abs-place', () => { P.abs = null; });
// The Listen widget's Play when nothing is in the player: the episode last played, from where it stopped.
C.Podcasts = Object.assign(C.Podcasts || {}, { resume: async () => {
  const r = await api('/api/podcasts/listening'), e = (r.going || [])[0];
  if (!e) return false;
  P.eps.set(e.audio, Object.assign(P.eps.get(e.audio) || {}, e));
  await playEp(e.audio);
  return true;
} });
})();
