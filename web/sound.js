/* Sound: a quiet bed of recorded sound under the book that follows the scene you're in (rain on the
   moor, a fire in the hall, the sea), from soundscape.py. Two ways to have it:
   - in Daf's reader (book.js tells it each time the page moves: C.Sound.moved), or
   - beside the Kindle: the plugin sends the page it's on, and Today's Sound row plays that scene
     (a request that waits for the next page, so no timer has to run while the screen sleeps).
   The sounds are seamless loops with PAD seconds of their own end before them and of their start
   after them (Chataltul's recordings), played with Web Audio, each fading in and out over FADE seconds. */
(() => {
'use strict';
const C = window.DafCore, { api, esc, $ } = C;
const store = { get(k, d){ try { const v = localStorage.getItem('daf.' + k); return v == null ? d : JSON.parse(v); } catch(e){ return d; } }, set(k, v){ try { localStorage.setItem('daf.' + k, JSON.stringify(v)); } catch(e){} } };
const PAD = 0.5, FADE = 4;
const ICON = '<svg width="18" height="18" viewBox="0 0 20 20" aria-hidden="true"><path d="M3 11.5c1.6 0 1.6-3 3.2-3s1.6 5 3.2 5 1.6-7 3.2-7 1.6 5 3.2 5c.8 0 1.2-1 1.2-1" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>';
const S = C.Sound = { ctx: null, master: null, layers: new Map(), bufs: new Map(), want: {}, mode: null, book: null, r: null, vol: store.get('soundVol', 0.6), icon: ICON };

/* ---------- the mixer ---------- */
function ctx(){
  if (!S.ctx) {
    const A = window.AudioContext || window.webkitAudioContext; if (!A) return null;
    S.ctx = new A(); S.master = S.ctx.createGain(); S.master.gain.value = S.vol; S.master.connect(S.ctx.destination);
  }
  if (S.ctx.state === 'suspended') S.ctx.resume().catch(() => {});
  return S.ctx;
}
// A tap anywhere lets a page that opened with Sound on start playing (browsers wait for one).
S.wake = () => { if (S.ctx && S.ctx.state === 'suspended' && S.mode) S.ctx.resume().catch(() => {}); };
document.addEventListener('pointerdown', S.wake, true);
document.addEventListener('keydown', S.wake, true);
function buffer(id){
  if (!S.bufs.has(id)) S.bufs.set(id, fetch('/api/sounds/' + encodeURIComponent(id) + '.mp3', { credentials: 'same-origin' })
    .then(r => { if (!r.ok) throw new Error('The sound didn’t come'); return r.arrayBuffer(); })
    .then(b => new Promise((ok, no) => { const d = ctx().decodeAudioData(b, ok, no); if (d && d.catch) d.catch(() => {}); }))
    .catch(e => { S.bufs.delete(id); throw e; }));
  return S.bufs.get(id);
}
function ramp(g, to){
  const t = S.ctx.currentTime; g.gain.cancelScheduledValues(t); g.gain.setValueAtTime(g.gain.value, t); g.gain.linearRampToValueAtTime(to, t + FADE);
}
// sounds: {id: level}. What's playing and not wanted fades out; what's wanted fades in or to its level.
async function mix(sounds){
  const c = ctx(); if (!c) return;
  S.want = sounds || {};
  for (const [id, L] of [...S.layers]) if (!(id in S.want)) {
    ramp(L.g, 0); S.layers.delete(id);
    setTimeout(() => { try { L.src.stop(); L.g.disconnect(); } catch(e){} }, FADE * 1000 + 300);
  }
  await Promise.all(Object.entries(S.want).map(async ([id, lv]) => {
    let L = S.layers.get(id);
    if (!L) {
      let buf; try { buf = await buffer(id); } catch(e){ return; }
      if (!(id in S.want) || S.layers.has(id)) return;        // changed while it came
      const g = c.createGain(); g.gain.value = 0; g.connect(S.master);
      const src = c.createBufferSource(), loop = Math.max(1, Math.round(buf.duration - 2 * PAD));
      src.buffer = buf; src.loop = true; src.loopStart = PAD; src.loopEnd = PAD + loop; src.connect(g);
      src.start(c.currentTime, PAD + Math.random() * (loop - 0.5));  // somewhere in the loop, so two of a kind never line up
      L = { g, src }; S.layers.set(id, L);
    }
    ramp(L.g, S.want[id]);
  }));
}
function hush(){ mix({}); }
S.volume = v => { S.vol = Math.max(0, Math.min(1, v)); store.set('soundVol', S.vol); if (S.master) S.master.gain.setTargetAtTime(S.vol, S.ctx.currentTime, 0.1); };

/* ---------- in Daf's reader ---------- */
S.on = () => store.get('soundOn', false);
// A book opened: with Sound on (on this device), its scene plays from the first page it shows.
S.open = id => {
  if (S.book) S.closed();
  S.book = { id, place: null, t: null, again: null }; S.r = null;
  if (S.on() && S.mode !== 'kindle') S.mode = 'book';
};
S.moved = place => {
  const b = S.book; if (!b || !place) return;
  b.place = place;
  if (S.mode !== 'book') return;
  clearTimeout(b.t); b.t = setTimeout(() => ask(place), 1200);
};
S.closed = () => { if (S.mode === 'book') { hush(); S.mode = null; } if (S.book) { clearTimeout(S.book.t); clearTimeout(S.book.again); } S.book = null; S.r = null; };
S.toggle = () => {
  if (S.mode === 'book') { store.set('soundOn', false); hush(); S.mode = null; S.r = null; draw(); return false; }
  if (S.mode === 'kindle') stopKindle();
  store.set('soundOn', true); S.mode = 'book'; ctx();
  if (S.book && S.book.place) ask(S.book.place);
  return true;
};
async function ask(place){
  const b = S.book; if (!b || S.mode !== 'book') return;
  clearTimeout(b.again);
  let r; try { r = await api('/api/ebooks/' + encodeURIComponent(b.id) + '/sound', { method: 'POST', body: JSON.stringify(place || {}) }); }
  catch(e){ b.again = setTimeout(() => ask(b.place), 20000); return; }
  if (S.book !== b || S.mode !== 'book') return;
  got(r);
  if (r.state === 'reading') b.again = setTimeout(() => ask(b.place), 5000);
}
function got(r){
  S.r = r;
  if (r.state === 'ready') mix(r.sounds);
  else if (r.state === 'none' || r.state === 'failed') hush();
  draw();
}

/* ---------- beside the Kindle ---------- */
let kAbort = null;
async function listenKindle(after){
  if (S.mode !== 'kindle') return;
  kAbort = new AbortController();
  let r;
  try { r = await api('/api/sound/kindle?after=' + (after || 0) + '&wait=25', { signal: kAbort.signal }); }
  catch(e){ if (S.mode === 'kindle') setTimeout(() => listenKindle(after), 15000); return; }
  if (S.mode !== 'kindle') return;
  got(r);
  // the model still reading the Kindle's chapter: ask again soon; else wait for the next page
  if (r.state === 'reading') setTimeout(() => listenKindle(0), 5000);
  else listenKindle(r.seen || Date.now() / 1000);
}
function startKindle(){
  if (S.mode === 'book') { S.mode = null; }
  S.mode = 'kindle'; ctx(); listenKindle(0);
  draw();
}
function stopKindle(){ S.mode = null; if (kAbort) kAbort.abort(); hush(); S.r = null; draw(); }
S.kindle = () => S.mode === 'kindle';

// Today: a row for the Kindle's book when it has sent a page in the last half hour (Sound on there).
S.todayNotice = () => {
  setTimeout(fillToday, 0);
  return '<div id="sndtoday"></div>';
};
async function fillToday(){
  const el = $('#sndtoday'); if (!el) return;
  let r = S.mode === 'kindle' && S.r ? S.r : null;
  if (!r) { try { r = await api('/api/sound/kindle'); } catch(e){ return; } }
  const fresh = r && r.seen && Date.now() / 1000 - r.seen < 1800;
  if (!$('#sndtoday')) return;
  if (!fresh && S.mode !== 'kindle') { el.innerHTML = ''; return; }
  if (!S.r && S.mode !== 'kindle') S.kr = r;
  drawToday(r);
}
function drawToday(r){
  const el = $('#sndtoday'); if (!el) return;
  r = r || S.r || S.kr || {};
  const on = S.mode === 'kindle';
  el.innerHTML = '<div class="notice sndrow"><span style="color:var(--accent)">' + ICON + '</span><span style="flex:1"><b>' + esc(shortT(r.title || 'Kindle')) + '</b>' +
    (on && r.scene ? '<span class="mute"> · ' + esc(r.scene) + '</span>' : on && r.state === 'reading' ? '<span class="mute"> · …</span>' : '') + '</span>' +
    (on ? '<input type="range" class="sndvol" min="0" max="100" value="' + Math.round(S.vol * 100) + '" aria-label="Volume">' : '') +
    '<button class="btn sm' + (on ? '' : ' primary') + '" data-snd="kindle">' + (on ? 'Stop' : 'Sound') + '</button></div>';
}
const shortT = t => String(t || '').split(/:\s/)[0];

/* ---------- the reader's button and its menu ---------- */
function draw(){
  const b = $('[data-bk="sound"]');
  if (b) { b.classList.toggle('on', S.mode === 'book'); b.title = S.mode === 'book' && S.r && S.r.scene ? S.r.scene : 'Sound'; }
  const p = $('#pop .sndpop'); if (p) p.outerHTML = popHTML();
  if ($('#sndtoday') && (S.mode === 'kindle' || $('#sndtoday').innerHTML)) drawToday();
}
function popHTML(){
  const on = S.mode === 'book', r = S.r || {};
  const what = !on ? '' : r.state === 'ready' ? (r.scene || '') : r.state === 'reading' ? '…' : r.why || '';
  return '<div class="menu sndpop">' + (on ? '<div class="sndscene"' + (what ? '' : ' hidden') + '>' + esc(what) + '</div>' +
    '<label class="sndvl"><span>Volume</span><input type="range" class="sndvol" min="0" max="100" value="' + Math.round(S.vol * 100) + '"></label><hr>' : '') +
    '<button data-snd="toggle">' + (on ? 'Turn off Sound' : 'Turn on Sound') + '</button></div>';
}
S.menu = anchor => {
  const p = $('#pop'), r = anchor.getBoundingClientRect();
  p.innerHTML = popHTML(); p.hidden = false;
  if (!r.width || anchor.dataset.bk === 'pmenu') {      // a phone: above the round button, where its menu was
    p.style.left = Math.max(8, window.innerWidth - p.offsetWidth - 12) + 'px';
    p.style.top = Math.max(8, (r.width ? r.top : window.innerHeight - 90) - p.offsetHeight - 12) + 'px';
    return;
  }
  p.style.left = Math.max(8, Math.min(window.innerWidth - p.offsetWidth - 8, r.right - p.offsetWidth)) + 'px';
  p.style.top = (r.bottom + 8 + p.offsetHeight > window.innerHeight ? Math.max(8, r.top - p.offsetHeight - 10) : r.bottom + 8) + 'px';
};
S.button = () => '<button class="ib' + (S.mode === 'book' ? ' on' : '') + '" data-bk="sound" title="Sound" aria-label="Sound">' + ICON + '</button>';
document.addEventListener('input', e => { if (e.target.classList && e.target.classList.contains('sndvol')) S.volume(e.target.value / 100); });
document.addEventListener('click', e => {
  const t = e.target.closest('[data-snd]'); if (!t) return;
  const a = t.dataset.snd;
  if (a === 'toggle') { S.toggle(); draw(); }
  else if (a === 'kindle') { if (S.mode === 'kindle') stopKindle(); else startKindle(); }
});
})();
