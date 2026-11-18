/* The Music page (#music): every album in the music folder, sorted into moods or not yet
   (daf/music.py albums). An album opens under its row: Play to hear it whole, its moods and tags
   as chips for the whole album (filled: every track has it; ringed: some do), a mood or a tag of
   your own, how much it moves, and its tracks (a tap plays from there). Each track keeps what else
   it had, so one sad track on a bright album stays sad. It plays through music.js, like Today's row. */
(() => {
'use strict';
const C = window.DafCore, { api, esc, $ } = C;
const P = { albums: [], show: 'new', q: '', open: null, one: null, busy: false };
const label = w => w.charAt(0).toUpperCase() + w.slice(1);
const hm = s => { const m = Math.round(s / 60); return m >= 60 ? Math.floor(m / 60) + ' h ' + (m % 60) + ' min' : m + ' min'; };
const ENERGY = [[1, 'Quiet'], [2, 'Moving'], [3, 'Driving']];
const M = () => C.Music;

const shown = () => {
  const q = P.q.trim().toLowerCase();
  // the open album stays in the list whatever it has become: it doesn't vanish from Not sorted at its first mood
  return P.albums.filter(a => a.id === P.open || ((P.show === 'all' || (P.show === 'new') === !a.sorted) && (!q || (a.album + ' ' + a.by).toLowerCase().includes(q))));
};
const chip = (act, id, text, state) => '<button class="chip' + (state === 2 ? ' on' : state === 1 ? ' some' : '') + '" data-mp="' + act + '" data-id="' + esc(String(id)) + '" aria-pressed="' + (state === 2 ? 'true' : state === 1 ? 'mixed' : 'false') + '">' + esc(text) + '</button>';
const add = (what, text) => '<form class="musadd" data-mp-add="' + what + '"><input class="field" name="w" maxlength="24" autocomplete="off" autocapitalize="none" aria-label="' + text + '" placeholder="' + text + '"><button class="btn sm" type="submit">Add</button></form>';

function editor(a){
  const one = P.one && P.one.id === a.id ? P.one : null;
  if (!one) return '<div class="musaled"><span class="mute">…</span></div>';
  const Mu = M(), n = one.n, has = (list, w) => { const x = list.find(g => g.id === w); return !x ? 0 : x.n >= n ? 2 : 1; };
  const moods = (Mu ? Mu.moods.map(m => m.id) : []).concat(one.moods.map(m => m.id)).filter((w, k, all) => all.indexOf(w) === k);
  const known = {}; (Mu ? Mu.moods : []).forEach(m => m.tags.forEach(g => { known[g.id] = (known[g.id] || 0) + g.n; }));
  const tags = one.tags.map(g => g.id).concat(Object.keys(known).sort((x, y) => known[y] - known[x]).filter(g => !one.tags.some(t => t.id === g)).slice(0, 28));
  const playing = Mu && Mu.going() && Mu.aud && Mu.aud.id === a.id, cur = playing && Mu.cur ? Mu.cur.id : null;
  return '<div class="musaled">' +
    '<div class="musacts"><button class="btn' + (playing ? '' : ' primary') + '" data-mp="play">' + (playing ? 'Stop' : 'Play') + '</button></div>' +
    '<div class="mh">Moods</div><div class="muschips">' + moods.map(w => chip('mood', w, label(w), has(one.moods, w))).join('') + '</div>' + add('moods', 'New mood') +
    '<div class="mh">Tags</div><div class="muschips mustags">' + tags.map(w => chip('tag', w, label(w), has(one.tags, w))).join('') + '</div>' + add('tags', 'New tag') +
    '<div class="mh">Energy</div><div class="muschips">' + ENERGY.map(([k, t]) => chip('energy', k, t, one.energy === k ? 2 : 0)).join('') + '</div>' +
    '<div class="mh">Tracks</div><div class="mustracks">' + one.tracks.map((t, k) => '<button data-mp="track" data-id="' + t.id + '"' + (cur === t.id ? ' class="now"' : '') + '>' +
      '<span class="num">' + (t.n || k + 1) + '</span><span class="mustt">' + esc(t.title) + '</span>' + (t.off ? '<span class="mute">Not for reading</span>' : '') + '<span class="mute num">' + hm(t.secs) + '</span></button>').join('') + '</div></div>';
}
function rows(){
  const list = shown();
  if (!list.length) return '<div class="mute musnone">' + (P.albums.length ? 'Nothing here' : 'No music') + '</div>';
  return list.map(a => '<div class="musal' + (P.open === a.id ? ' open' : '') + '" data-album="' + a.id + '">' +
    '<button class="musalrow" data-mp="open" aria-expanded="' + (P.open === a.id) + '"><span class="musname"><b>' + esc(a.album || a.by || 'Unnamed') + '</b><i>' + esc([a.by, a.n + (a.n === 1 ? ' track' : ' tracks'), hm(a.secs)].filter(Boolean).join(' · ')) + '</i></span>' +
    (a.sorted ? '<span class="musmini">' + esc(a.moods.slice(0, 3).map(m => label(m.id)).join(' · ')) + '</span>' : '') + '</button>' +
    (P.open === a.id ? editor(a) : '') + '</div>').join('');
}
function draw(){
  const el = $('#muslist'); if (!el) return;
  const f = document.activeElement;
  if (f && el.contains(f) && f.matches('input.field') && f.value) return;      // not under a word half typed
  const count = k => P.albums.filter(a => k === 'all' || (k === 'new') === !a.sorted).length;
  $('#musshow').innerHTML = [['new', 'Not sorted'], ['old', 'Sorted'], ['all', 'All']].map(([k, t]) =>
    '<button class="chip' + (P.show === k ? ' on' : '') + '" data-mp="show" data-id="' + k + '" aria-pressed="' + (P.show === k) + '">' + t + ' <span class="num">' + count(k) + '</span></button>').join('');
  el.innerHTML = rows();
}
async function open(id){
  if (P.open === id) { P.open = null; draw(); return; }
  P.open = id; if (!P.one || P.one.id !== id) P.one = null;
  draw();
  try { const one = await api('/api/music/albums/' + id); if (P.open === id) { P.one = one; draw(); } }
  catch(e){ C.toast(e.message); }
  const row = document.querySelector('.musal.open'); if (row && row.scrollIntoView) row.scrollIntoView({ block: 'nearest' });
}
async function say(body){
  if (!P.one || P.busy) return;
  P.busy = true;
  try {
    const one = await api('/api/music/albums/' + P.one.id, { method: 'POST', body: JSON.stringify(body) });
    P.one = one;
    const k = P.albums.findIndex(a => a.id === one.id);
    if (k >= 0) P.albums[k] = Object.assign({}, one, { tracks: undefined });
    if (M()) M().load(true);
  } catch(e){ C.toast(e.message || 'That didn’t save'); }
  P.busy = false; draw();
}
C.views.music = async () => {
  $('#main').innerHTML = '<div class="top"><h1>Music</h1></div><div class="page muspage"><div class="musbar"><div class="muschips" id="musshow"></div>' +
    '<input class="field" id="musq" type="search" autocomplete="off" aria-label="Search" placeholder="Search"></div><div id="muslist"><span class="mute">Loading…</span></div></div>';
  if (M()) M().load();
  const r = await api('/api/music/albums');
  P.albums = r.albums || [];
  if (P.show === 'new' && !P.albums.some(a => !a.sorted)) P.show = 'all';
  $('#musq').value = P.q;
  draw();
};
C.MusicPage = { draw: () => { if ($('#muslist') && P.albums.length) draw(); } };
document.addEventListener('input', e => { if (e.target.id === 'musq') { P.q = e.target.value; const el = $('#muslist'); if (el) el.innerHTML = rows(); } });
document.addEventListener('submit', e => {
  const f = e.target.closest && e.target.closest('[data-mp-add]'); if (!f) return;
  e.preventDefault();
  const w = f.elements.w.value.trim().toLowerCase(); if (!w) return;
  f.elements.w.value = '';
  say({ add: { [f.dataset.mpAdd === 'moods' ? 'moods' : 'tags']: [w] } });
});
document.addEventListener('click', e => {
  const b = e.target.closest('[data-mp]'); if (!b) return;
  const a = b.dataset.mp, id = b.dataset.id, al = b.closest('[data-album]'), Mu = M();
  if (a === 'show') { P.show = id; P.open = null; draw(); }
  else if (a === 'open' && al) open(al.dataset.album);
  else if (!P.one) return;
  else if (a === 'mood' || a === 'tag') {
    const what = a === 'mood' ? 'moods' : 'tags', all = (P.one[what].find(g => g.id === id) || {}).n >= P.one.n;
    say({ [all ? 'remove' : 'add']: { [what]: [id] } });
  }
  else if (a === 'energy') say({ energy: +id });
  else if (a === 'play' && Mu) { if (Mu.going() && Mu.aud && Mu.aud.id === P.one.id) Mu.turn(false); else Mu.hear(P.one); }
  else if (a === 'track' && Mu) Mu.hear(P.one, id);
});
})();
