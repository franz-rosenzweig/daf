/* Audiobookshelf in Daf (absapi.py): its audiobooks and its recordings play in Daf's player, and where
   you stop goes back to ABS as you listen (a playback session, the way ABS's own apps keep it), so ABS
   and its apps pick up where Daf left off, and the other way round. */
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
    open: p.book ? '#book/' + encodeURIComponent(p.book) : p.episode ? '#podcasts/abs/' + encodeURIComponent(p.item) : '#podcasts/audiobooks',
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
})();
