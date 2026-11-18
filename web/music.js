/* Music: your own quiet music under the page (daf/music.py), in the Sound menu beside the scene's
   sounds. You pick moods, and under them the finer tags; a mood shuffles, an album plays in its
   order. With Auto the scene picks the tags instead: Sound's reading of the book says what music
   suits where you are (soundscape.py), and the tracks that fit it best play, within your moods.
   It plays in two places: in the reader while a book is open (kept on for the next book), and
   from Today's Music row with no book open, beside the Kindle or a paper book, until it's stopped.
   Radio is the third thing it can play: one of your own stations, passed on by the server. Whole tracks, so two <audio> elements take turns: the next fades in over FADE seconds
   while the last fades out. What you pick, the volume and whether it's on stay on this device.
   The track that's playing can be fixed from the menu: Not for reading, or its moods and tags. */
(() => {
'use strict';
const C = window.DafCore, { api, esc, $ } = C;
const store = { get(k, d){ try { const v = localStorage.getItem('daf.' + k); return v == null ? d : JSON.parse(v); } catch(e){ return d; } }, set(k, v){ try { localStorage.setItem('daf.' + k, JSON.stringify(v)); } catch(e){} } };
const FADE = 4, FEW = 14;
const M = C.Music = { has: null, moods: [], albums: [], on: false, open: false, beside: false, vol: store.get('musicVol', 0.35),
  pick: Object.assign({ moods: [], tags: [], album: null }, store.get('musicPick', {})), auto: !!store.get('musicAuto', false), want: null,
  q: [], cur: null, els: [], live: -1, duck: 1,
  view: 'main', more: false, fails: 0, rad: null, stations: null, radEdit: false };
// on: it's wanted now. open: a book is open in the reader. beside: it was started from Today.
const there = () => M.open || M.beside;
M.going = () => M.on && there();
const label = w => w.charAt(0).toUpperCase() + w.slice(1);
const post = (url, body) => api(url, { method: 'POST', body: JSON.stringify(body) });

/* ---------- what there is ---------- */
M.load = async again => {
  if (M.has != null && !again) return M.has;
  try { const r = await api('/api/music'); M.has = !!r.on; M.moods = r.moods || []; M.albums = r.albums || []; }
  catch(e){ if (M.has == null) M.has = false; }
  M.redraw();
  return M.has;
};
const tagsNow = () => {            // the tags under the moods picked (every mood, with none picked), the most used first
  const n = {};
  M.moods.filter(m => !M.pick.moods.length || M.pick.moods.includes(m.id)).forEach(m => m.tags.forEach(g => { n[g.id] = (n[g.id] || 0) + g.n; }));
  return Object.keys(n).sort((a, b) => n[b] - n[a] || a.localeCompare(b));
};

/* ---------- the two players ---------- */
function el(k){
  if (!M.els[k]) {
    const a = new Audio(); a.preload = 'auto';
    a.addEventListener('ended', () => { if (k === M.live) next(); });
    a.addEventListener('error', () => {
      if (k !== M.live || !a.getAttribute('src')) return;
      M.fails++;
      if (M.fails < 4) next(true);
      else if (M.rad) { M.rad = null; if (C.toast) C.toast('The station didn’t answer'); M.turn(false); }
      else M.stop();
    });
    a.addEventListener('playing', () => { if (k === M.live) M.fails = 0; });
    M.els[k] = { a, g: 0, to: 0, per: 0 };
  }
  return M.els[k];
}
const fade = (E, to, secs) => { E.to = to; E.per = secs > 0 ? Math.abs(to - E.g) / secs : 1e9; };
let timer = null, last = 0;
function run(){ if (!timer) { last = performance.now(); timer = setInterval(tick, 100); } }
// Under the bottom player's audiobook, podcast or video the music waits; under read-aloud it drops back.
const under = () => { const P = C.Player; return P && P.cur && P.playing() ? (P.cur.driven ? 0.55 : 0) : 1; };
function tick(){
  const now = performance.now(), dt = Math.min(2, (now - last) / 1000); last = now;
  const d = under();
  if (M.duck !== d) M.duck = d > M.duck ? Math.min(d, M.duck + dt / 1.5) : Math.max(d, M.duck - dt / 1.5);
  M.els.forEach((E, k) => {
    if (!E) return;
    if (E.g !== E.to) E.g = E.to > E.g ? Math.min(E.to, E.g + E.per * dt) : Math.max(E.to, E.g - E.per * dt);
    E.a.volume = Math.max(0, Math.min(1, M.vol * E.g * M.duck));
    if (k !== M.live && E.g === 0 && !E.a.paused) E.a.pause();
    if (k !== M.live && E.g === 0 && E.radio) { E.radio = false; E.a.removeAttribute('src'); E.a.load(); }      // a station that's faded out is let go of
  });
  const L = M.els[M.live];
  if (L && M.cur) {
    if (d === 0 && M.duck === 0 && !L.a.paused) { L.a.pause(); M.held = true; }
    else if (M.held && d > 0) { M.held = false; L.a.play().catch(() => {}); }
    const left = L.a.duration - L.a.currentTime;
    if (isFinite(left) && L.a.duration > 3 * FADE && left <= FADE + 0.2) next();      // the next one comes in over this one's end
  }
  if (!M.cur && M.els.every(E => !E || E.a.paused)) { clearInterval(timer); timer = null; }
}
function play(t, secs){
  const old = M.els[M.live]; if (old) fade(old, 0, secs);
  M.live = M.live === 0 ? 1 : 0;
  const E = el(M.live);
  E.a.src = t.src; E.radio = !!t.radio; E.g = 0; E.a.volume = 0; fade(E, 1, secs);
  M.cur = t; M.held = false;
  E.a.play().then(() => { M.blocked = false; }).catch(() => { M.blocked = true; });      // a browser may wait for a tap (wake)
  run(); M.redraw();
  if (t.radio) return;
  const seen = store.get('musicRecent', []).filter(i => i !== t.id); seen.push(t.id); store.set('musicRecent', seen.slice(-150));
  if (M.q[0]) setTimeout(() => { if (M.q[0]) fetch(M.q[0].src, { headers: { Range: 'bytes=0-1' }, credentials: 'same-origin' }).catch(() => {}); }, 8000);   // its copy gets made ahead
}
async function fill(){
  const p = M.pick;
  const f = M.follows(), au = M.aud;
  let r; try { r = await post('/api/music/queue', au ? { album: au.id, all: true } : { moods: p.album ? [] : p.moods, tags: p.album || f ? [] : p.tags, album: p.album || undefined,
    match: f && M.want ? M.want : undefined, recent: store.get('musicRecent', []), n: f ? 8 : 20 }); }
  catch(e){ return; }
  M.q = r.tracks || [];
  if (au && au.from) { const k = M.q.findIndex(t => t.id === au.from); if (k > 0) M.q = M.q.slice(k); au.from = null; }      // from the track that was tapped
}
let turning = false;
async function next(quick){
  if (turning || !M.on) return;
  turning = true;
  try {
    if (M.rad) {                 // a station: the one stream, joined again if it drops
      play({ id: 'radio-' + M.rad.id, title: M.rad.name, artist: 'Radio', src: '/api/music/radio/' + M.rad.id + '/stream?at=' + Date.now(), moods: [], tags: [], radio: true }, quick ? 1.2 : FADE);
      return;
    }
    if (!M.q.length) await fill();
    const t = M.q.shift();
    if (!t || !M.on) { if (!t) M.stop(); return; }
    play(t, quick ? 1.2 : FADE);
  } finally { turning = false; }
}
M.wake = () => { const L = M.els[M.live]; if (M.blocked && L && M.cur) L.a.play().then(() => { M.blocked = false; }).catch(() => {}); };
document.addEventListener('pointerdown', M.wake, true);
document.addEventListener('keydown', M.wake, true);

/* ---------- on, off, and what's picked ---------- */
let soon = null;                 // the one change of track that's waiting to happen
M.start = () => {
  if (!M.on || M.cur || !there()) return;
  M.load().then(has => {
    if (!has || !M.on || M.cur || !there()) return;
    if (M.follows() && !M.want) { clearTimeout(soon); soon = setTimeout(() => { if (!M.cur) next(); }, 5000); }      // a moment for the scene to say what fits
    else next();
  });
};
M.stop = () => {
  M.els.forEach(E => E && fade(E, 0, 1.5));
  M.cur = null; M.live = -1; M.q = []; run(); M.redraw();
};
// In a book this is the reader's Music, kept for the next book. With no book open it's the music
// beside the Kindle or a paper book, which plays on from page to page of Daf until it's stopped.
M.turn = on => {
  M.on = !!on;
  if (M.open) store.set('musicOn', M.on);
  M.beside = M.on && (M.beside || !M.open);
  if (M.on) { M.fails = 0; M.start(); } else { M.aud = null; M.rad = null; M.stop(); }
  if (C.Sound) { C.Sound.remix(); C.Sound.scene(); }
  M.redraw();
};
/* ---------- Auto: the scene picks ---------- */
M.follows = () => M.on && M.auto && there() && !M.pick.album && !M.aud && !M.rad;
// The Music page: hear one album whole, sorted or not, from its start or from one of its tracks. It
// isn't a pick: it plays until something is picked in the menu, or it's stopped.
M.hear = (al, from) => {
  M.aud = { id: al.id, name: al.album || al.by || '', from: from || null }; M.rad = null; M.q = []; M.want = null;
  clearTimeout(soon);
  if (!M.on) M.turn(true); else if (M.cur) next(true); else M.start();
  M.redraw();
};
// Radio: one of your stations, until something is picked in the menu or it's stopped.
M.tune = st => {
  M.rad = { id: st.id, name: st.name }; M.aud = null; M.q = []; M.want = null; M.view = 'main'; M.fails = 0;
  clearTimeout(soon);
  if (!M.on) M.turn(true); else next(true);
  M.redraw();
};
const suits = (t, m) => (!m.tags.length || (t.tags || []).some(g => m.tags.includes(g))) && (!m.energy || !t.energy || Math.abs(m.energy - t.energy) <= 1);
// The scene where you are (sound.js), with what music would suit it: {tags, energy}.
M.scene = r => {
  if (!M.follows() || !r || r.state !== 'ready') return;
  const m = r.music && ((r.music.tags || []).length || r.music.energy) ? { tags: r.music.tags || [], energy: r.music.energy || null } : null;
  if (JSON.stringify(m) === JSON.stringify(M.want)) return;
  M.want = m; M.q = [];
  if (!M.cur) { clearTimeout(soon); next(); return; }
  if (!m || suits(M.cur, m)) return;             // what's playing fits here too: it plays out, and the next is picked for the scene
  clearTimeout(soon); soon = setTimeout(() => next(), 1500);      // else a slow fade into something that fits
};
// A book is open (sound.js): the music plays while one is, and stops with it.
M.opened = () => { M.open = true; if (!M.beside) M.on = !!store.get('musicOn', false); M.start(); };
M.closed = () => {
  M.open = false; M.want = null; clearTimeout(soon);
  if (M.beside) { if (C.Sound) C.Sound.scene(); return; }      // started from Today: it plays on, and follows the Kindle again
  M.on = false; if (M.cur) M.stop();
};
M.volume = v => { M.vol = Math.max(0, Math.min(1, v)); store.set('musicVol', M.vol); run(); };
function picked(){               // a moment after the last chip, so picking three isn't three changes of track
  store.set('musicPick', M.pick); M.q = []; M.aud = null; M.rad = null;
  clearTimeout(soon);
  if (!M.on) { M.turn(true); return; }
  soon = setTimeout(() => next(true), 900);
  M.redraw();
}
const flip = (list, w) => list.includes(w) ? list.filter(x => x !== w) : list.concat(w);

/* ---------- the menu's part ---------- */
const chip = (act, id, text, on) => '<button class="chip' + (on ? ' on' : '') + '" data-mus="' + act + '" data-id="' + esc(id) + '" aria-pressed="' + !!on + '">' + esc(text) + '</button>';
M.section = () => {
  if (!M.has) return '';
  if (M.view === 'albums') return albumsHTML();
  if (M.view === 'radio') return radioHTML();
  if (M.view === 'track' && M.cur && !M.cur.radio) return trackHTML();
  const p = M.pick, tags = tagsNow(), album = M.rad ? { album: M.rad.name } : M.aud ? { album: M.aud.name } : p.album && M.albums.find(a => a.id === p.album);
  const shown = M.more ? tags : tags.filter((g, k) => k < FEW || p.tags.includes(g));
  return '<hr><div class="mush"><b>Music</b>' + (M.on ? '<input type="range" class="musvol" min="0" max="100" value="' + Math.round(M.vol * 100) + '" aria-label="Music volume">' : '') + '</div>' +
    (M.on && M.cur && M.cur.radio ? '<div class="musnow"><span class="musname"><b>' + esc(M.cur.title) + '</b><i>' + esc(M.cur.artist) + '</i></span></div>' : '') +
    (M.on && M.cur && !M.cur.radio ? '<div class="musnow"><span class="musname"><b>' + esc(M.cur.title) + '</b><i>' + esc(M.cur.artist) + '</i></span>' +
      '<button class="ib" data-mus="edit" title="Moods and tags" aria-label="Moods and tags"><svg width="18" height="18" viewBox="0 0 20 20" aria-hidden="true"><path d="M4 10h.01M10 10h.01M16 10h.01" stroke="currentColor" stroke-width="2.6" stroke-linecap="round"/></svg></button>' +
      '<button class="ib" data-mus="next" title="Next" aria-label="Next"><svg width="18" height="18" viewBox="0 0 20 20" aria-hidden="true"><path d="M5 4.5v11l8-5.5zM15 4.5v11" fill="currentColor" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round" stroke-linecap="round"/></svg></button></div>' : '') +
    (album ? '<div class="muschips">' + chip('noalbum', '', album.album || album.by, true) + '</div>'
      : '<div class="muschips">' + chip('auto', '', 'Auto', M.auto) + M.moods.map(m => chip('mood', m.id, label(m.id), p.moods.includes(m.id))).join('') + '</div>' +
        (shown.length && !M.auto ? '<div class="muschips mustags">' + shown.map(g => chip('tag', g, label(g), p.tags.includes(g))).join('') +
          (tags.length > shown.length || M.more ? '<button class="chip musmore" data-mus="more">' + (M.more ? 'Fewer' : 'More') + '</button>' : '') + '</div>' : '')) +
    '<button data-mus="albums">Albums</button><button data-mus="radio">Radio</button>' +
    '<button data-mus="toggle">' + (M.on ? 'Turn off Music' : 'Turn on Music') + '</button>';
};
function albumsHTML(){
  const hm = s => { const m = Math.round(s / 60); return m >= 60 ? Math.floor(m / 60) + ' h ' + (m % 60) + ' min' : m + ' min'; };
  return '<div class="mush"><button class="ib" data-mus="back" title="Back" aria-label="Back"><svg width="18" height="18" viewBox="0 0 20 20" aria-hidden="true"><path d="M12 4l-6 6 6 6" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg></button><b>Albums</b></div>' +
    '<div class="musalbums"><button data-mus="page"><b>All albums</b></button>' + M.albums.map(a => '<button data-mus="album" data-id="' + a.id + '"' + (M.pick.album === a.id ? ' aria-checked="true"' : '') + '><span class="musname"><b>' + esc(a.album || a.by) + '</b><i>' + esc(a.by) + '</i></span><span class="mute">' + hm(a.secs) + '</span></button>').join('') + '</div>';
}
const BACK = '<button class="ib" data-mus="back" title="Back" aria-label="Back"><svg width="18" height="18" viewBox="0 0 20 20" aria-hidden="true"><path d="M12 4l-6 6 6 6" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg></button>';
// Your stations. Edit shows a way to take each off, and the two fields a new one needs.
function radioHTML(){
  const st = M.stations || [];
  return '<div class="mush">' + BACK + '<b>Radio</b>' + (st.length ? '<button class="btn sm" data-mus="radedit">' + (M.radEdit ? 'Done' : 'Edit') + '</button>' : '') + '</div>' +
    '<div class="musalbums">' + st.map(x => '<div class="musst"><button data-mus="station" data-id="' + x.id + '"' + (M.rad && M.rad.id === x.id ? ' aria-checked="true"' : '') + '><b>' + esc(x.name) + '</b></button>' +
      (M.radEdit ? '<button class="ib" data-mus="raddel" data-id="' + x.id + '" title="Remove" aria-label="Remove ' + esc(x.name) + '"><svg width="16" height="16" viewBox="0 0 20 20" aria-hidden="true"><path d="M5 5l10 10M15 5L5 15" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg></button>' : '') + '</div>').join('') + '</div>' +
    (M.radEdit || (M.stations && !st.length) ? '<form class="musadd musradd" data-mus-radio><input class="field" name="n" maxlength="80" autocomplete="off" aria-label="Name" placeholder="Name">' +
      '<input class="field" name="u" type="url" inputmode="url" autocomplete="off" autocapitalize="none" aria-label="Address" placeholder="Address"><button class="btn sm" type="submit">Add</button></form>' : '');
}
async function radio(){
  try { M.stations = (await api('/api/music/radio')).stations || []; } catch(e){ M.stations = M.stations || []; }
  M.redraw();
}
// A word of your own: a mood no track had yet joins the row of moods, a tag the tags under its moods.
const add = (what, text) => '<form class="musadd" data-mus-add="' + what + '"><input class="field" name="w" maxlength="24" autocomplete="off" autocapitalize="none" aria-label="' + text + '" placeholder="' + text + '"><button class="btn sm" type="submit">Add</button></form>';
function trackHTML(){
  const t = M.cur, all = [];
  M.moods.forEach(m => { if (t.moods.includes(m.id)) m.tags.forEach(g => { if (!all.includes(g.id)) all.push(g.id); }); });
  const tags = t.tags.concat(all.filter(g => !t.tags.includes(g)).slice(0, 24));
  return '<div class="mush"><button class="ib" data-mus="back" title="Back" aria-label="Back"><svg width="18" height="18" viewBox="0 0 20 20" aria-hidden="true"><path d="M12 4l-6 6 6 6" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg></button>' +
    '<span class="musname"><b>' + esc(t.title) + '</b><i>' + esc(t.artist) + '</i></span></div>' +
    '<div class="mh">Moods</div><div class="muschips">' + M.moods.map(m => chip('tmood', m.id, label(m.id), t.moods.includes(m.id))).join('') +
      t.moods.filter(w => !M.moods.some(m => m.id === w)).map(w => chip('tmood', w, label(w), true)).join('') + '</div>' +
    add('moods', 'New mood') +
    '<div class="mh">Tags</div><div class="muschips mustags">' + tags.map(g => chip('ttag', g, label(g), t.tags.includes(g))).join('') + '</div>' +
    add('tags', 'New tag') +
    '<hr><button data-mus="off">Not for reading</button>';
}
M.redraw = () => {
  if (C.Sound && C.Sound.redraw) C.Sound.redraw(); drawToday(); if (C.MusicPage) C.MusicPage.draw();
  document.querySelectorAll('.musbtn').forEach(b => { b.hidden = !M.has; b.classList.toggle('on', M.going()); });
};
/* ---------- Today: music beside the Kindle or a paper book ---------- */
const NOTE = '<svg width="18" height="18" viewBox="0 0 20 20" aria-hidden="true"><path d="M8 14.5V4.8l8-1.6v9.3" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/><ellipse cx="6" cy="14.6" rx="2.1" ry="1.7" fill="currentColor"/><ellipse cx="14" cy="12.6" rx="2.1" ry="1.7" fill="currentColor"/></svg>';
const NEXT = '<svg width="18" height="18" viewBox="0 0 20 20" aria-hidden="true"><path d="M5 4.5v11l8-5.5zM15 4.5v11" fill="currentColor" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round" stroke-linecap="round"/></svg>';
// The readers that have no Sound of their own (an article, a PDF) put this in their bar: Music's menu alone.
M.button = () => '<button class="ib musbtn' + (M.going() ? ' on' : '') + '" data-mus="menu" title="Music" aria-label="Music"' + (M.has ? '' : ' hidden') + '>' + NOTE + '</button>';
M.todayNotice = () => { setTimeout(() => M.load().then(drawToday), 0); return '<div id="mustoday"></div>'; };
function drawToday(){
  const el = $('#mustoday'); if (!el) return;
  if (!M.has) { el.innerHTML = ''; return; }
  if (el.querySelector('input[type=range]:active')) return;            // not under a finger on the slider
  const on = M.going(), t = on && M.cur;
  el.innerHTML = '<div class="notice sndrow musrow"><span style="color:var(--accent)">' + NOTE + '</span>' +
    '<span class="musname">' + (t ? '<b>' + esc(t.title) + '</b><i>' + esc(t.artist) + '</i>' : '<b>Music</b>') + '</span>' +
    (on ? '<input type="range" class="musvol" min="0" max="100" value="' + Math.round(M.vol * 100) + '" aria-label="Music volume">' +
      (M.rad ? '' : '<button class="ib" data-mus="next" title="Next" aria-label="Next">' + NEXT + '</button>') : '') +
    '<button class="btn sm" data-mus="menu">Moods</button>' +
    '<button class="btn sm' + (on ? '' : ' primary') + '" data-mus="toggle">' + (on ? 'Stop' : 'Play') + '</button></div>';
}
async function say(change){                    // what you say about the track that's playing
  const t = M.cur; if (!t) return;
  Object.assign(t, change); M.redraw();
  try { await post('/api/music/tracks/' + t.id, change); } catch(e){ C.toast && C.toast('That didn’t save'); return; }
  M.load(true);
}
document.addEventListener('input', e => { if (e.target.classList && e.target.classList.contains('musvol')) M.volume(e.target.value / 100); });
document.addEventListener('submit', async e => {
  const rf = e.target.closest && e.target.closest('[data-mus-radio]');
  if (rf) {                         // a station of your own
    e.preventDefault();
    const name = rf.elements.n.value.trim(), url = rf.elements.u.value.trim(); if (!name || !url) return;
    try { M.stations = (await post('/api/music/radio', { name, url })).stations; rf.elements.n.value = ''; rf.elements.u.value = ''; }
    catch(err){ if (C.toast) C.toast(err.message); }
    M.redraw(); return;
  }
  const f = e.target.closest && e.target.closest('[data-mus-add]'); if (!f) return;
  e.preventDefault();
  const w = f.elements.w.value.trim().toLowerCase(), what = f.dataset.musAdd === 'moods' ? 'moods' : 'tags'; if (!w || !M.cur) return;
  f.elements.w.value = '';
  if (!M.cur[what].includes(w)) say({ [what]: M.cur[what].concat(w) });
});
document.addEventListener('click', e => {
  const b = e.target.closest('[data-mus]'); if (!b) return;
  const a = b.dataset.mus, id = b.dataset.id, p = M.pick;
  if (a === 'toggle') M.turn(!M.going());
  else if (a === 'menu') {          // its own button again puts the menu away, as menus do (app.js keeps what was open when the click began)
    if (C.S && C.S.popAtClick && C.S.popAtClick.includes('sndpop')) $('#pop').hidden = true;
    else if (C.Sound) C.Sound.menu(b, true);
  }
  else if (a === 'auto') {
    M.auto = !M.auto; store.set('musicAuto', M.auto); M.want = null; M.q = [];
    if (!M.on) M.turn(true); else if (C.Sound) C.Sound.scene();
    M.redraw();
  }
  else if (a === 'mood') { p.moods = flip(p.moods, id); p.album = null; const can = tagsNow(); p.tags = p.tags.filter(g => can.includes(g)); picked(); }
  else if (a === 'tag') { p.tags = flip(p.tags, id); picked(); }
  else if (a === 'more') { M.more = !M.more; M.redraw(); }
  else if (a === 'next') { if (!M.rad) { clearTimeout(soon); next(true); } }
  else if (a === 'albums') { M.view = 'albums'; M.redraw(); }
  else if (a === 'radio') { M.view = 'radio'; M.radEdit = false; M.redraw(); radio(); }
  else if (a === 'radedit') { M.radEdit = !M.radEdit; M.redraw(); }
  else if (a === 'station') { const st = (M.stations || []).find(x => x.id === id); if (st) M.tune(st); }
  else if (a === 'raddel') {
    api('/api/music/radio/' + id, { method: 'DELETE' }).then(r => { M.stations = r.stations || []; if (M.rad && M.rad.id === id) M.turn(false); M.redraw(); }).catch(err => { if (C.toast) C.toast(err.message); });
  }
  else if (a === 'back') { M.view = 'main'; M.radEdit = false; M.redraw(); }
  else if (a === 'album') { p.album = id; M.view = 'main'; picked(); }
  else if (a === 'noalbum') { p.album = null; picked(); }
  else if (a === 'page') { $('#pop').hidden = true; location.hash = '#music'; }
  else if (a === 'edit') { if (M.cur && !M.cur.radio) { M.view = 'track'; M.redraw(); } }
  else if (a === 'tmood' && M.cur) say({ moods: flip(M.cur.moods, id) });
  else if (a === 'ttag' && M.cur) say({ tags: flip(M.cur.tags, id) });
  else if (a === 'off' && M.cur) { const t = M.cur; M.view = 'main'; post('/api/music/tracks/' + t.id, { off: true }).then(() => M.load(true)).catch(() => {}); M.q = M.q.filter(x => x.id !== t.id); next(true); }
});
setTimeout(() => M.load(), 1500);      // whether there's Music at all, for the buttons drawn before anyone asks
})();
