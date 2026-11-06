/* The player: one for everything that plays (a podcast episode, an article or a book read aloud, an
   audiobook), docked along the bottom as Metrolist and other Material apps have it. It lives outside
   the page that started it, so it keeps playing while you go anywhere else in Daf, and with the screen
   off in the Android app (shell.js tells Listen.java what #player is doing, and the lock screen's
   buttons press its own). A tap on it opens the whole player: the picture, the time to scrub, the
   speed, a sleep timer, chapters, and the way back to what's playing.

   Two kinds of thing play here:
   - media (C.Player.play): Daf's own <audio> plays a file, or an audiobook's files one after another
     as one long track. The item says where it starts and hears what happens (save), so the page that
     started it can come and go.
   - read-aloud (C.Player.drive): reader.js and book.js play Kokoro's paragraphs themselves; the player
     shows them and its buttons call theirs. */
(() => {
'use strict';
const C = window.DafCore, { $, esc } = C;
const store = { get(k, d){ try { const v = localStorage.getItem('daf.' + k); return v == null ? d : JSON.parse(v); } catch(e){ return d; } }, set(k, v){ try { localStorage.setItem('daf.' + k, JSON.stringify(v)); } catch(e){} } };
const audio = new Audio(); audio.preload = 'auto';
const Pl = C.Player = { cur: null, audio, big: false };
const RATES = [1, 1.2, 1.4, 1.6, 1.8, 2, 0.8];
const SLEEP = [0, 15, 30, 45, 60, -1];          // minutes; -1: the end of the chapter (or of the episode)
const fmt = t => { t = Math.max(0, Math.floor(t || 0)); const h = Math.floor(t / 3600), m = Math.floor(t % 3600 / 60), s = t % 60; return (h ? h + ':' + String(m).padStart(2, '0') : m) + ':' + String(s).padStart(2, '0'); };
const ICON = {
  play: '<svg width="22" height="22" viewBox="0 0 20 20" aria-hidden="true"><path d="M6 3.8v12.4L16 10z" fill="currentColor"/></svg>',
  pause: '<svg width="22" height="22" viewBox="0 0 20 20" aria-hidden="true"><rect x="4.6" y="3.6" width="3.6" height="12.8" rx="1.1" fill="currentColor"/><rect x="11.8" y="3.6" width="3.6" height="12.8" rx="1.1" fill="currentColor"/></svg>',
  back: '<svg width="22" height="22" viewBox="0 0 24 24" aria-hidden="true"><path d="M5 12a7 7 0 1 0 2.1-5" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/><path d="M6.5 2.8v4.4h4.4" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/><text x="12" y="15.2" font-size="6.6" font-weight="700" text-anchor="middle" fill="currentColor" font-family="system-ui,sans-serif">15</text></svg>',
  fwd: '<svg width="22" height="22" viewBox="0 0 24 24" aria-hidden="true"><path d="M19 12a7 7 0 1 1-2.1-5" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/><path d="M17.5 2.8v4.4h-4.4" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/><text x="12" y="15.2" font-size="6.6" font-weight="700" text-anchor="middle" fill="currentColor" font-family="system-ui,sans-serif">30</text></svg>',
  prevp: '<svg width="22" height="22" viewBox="0 0 20 20" aria-hidden="true"><path d="M5 4v12" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/><path d="M15.5 4.5v11L7.5 10z" fill="currentColor"/></svg>',
  nextp: '<svg width="22" height="22" viewBox="0 0 20 20" aria-hidden="true"><path d="M15 4v12" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/><path d="M4.5 4.5v11l8-5.5z" fill="currentColor"/></svg>',
  close: '<svg width="18" height="18" viewBox="0 0 20 20" aria-hidden="true"><path d="M5 5l10 10M15 5L5 15" stroke="currentColor" stroke-width="1.9" stroke-linecap="round"/></svg>',
  down: '<svg width="22" height="22" viewBox="0 0 20 20" aria-hidden="true"><path d="M5 7.5l5 5 5-5" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  wave: '<svg width="28" height="28" viewBox="0 0 20 20" aria-hidden="true"><path d="M3 10h1.5M6.2 7v6M9.4 4.5v11M12.6 7v6M15.8 9v2" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>',
};

/* ---------- media: a file, or an audiobook's files as one track ---------- */
// item: { id, kind, title, sub, art, open (a #place), tracks: [{ url, start, dur }] or url, duration,
//         chapters: [{ t, title }], back: 15, fwd: 30, save(event, info) }
// save hears 'play' (at), 'pause' (at), 'seek' (from, to), 'tick' (at, every 15 s while playing),
// 'ended', 'stop' (at) and 'hidden' (at), so an episode can tell AntennaPod where you stopped.
let track = 0, pending = null, sleepAt = 0, sleepEnd = false;
const tracks = it => it.tracks && it.tracks.length ? it.tracks : [{ url: it.url, start: 0, dur: it.duration || 0 }];
const media = () => Pl.cur && !Pl.cur.driven;
function time(){
  if (!media()) return 0;
  const t = tracks(Pl.cur)[track];
  return (t ? t.start : 0) + (pending != null ? pending : (audio.currentTime || 0));
}
function total(){
  const it = Pl.cur; if (!it || it.driven) return 0;
  const ts = tracks(it), last = ts[ts.length - 1];
  if (ts.length > 1 && last.dur) return last.start + last.dur;
  return it.duration || (isFinite(audio.duration) ? audio.duration : 0) || (last.dur || 0);
}
// To global time t: the track it falls in, and the place in that track.
function load(t, play){
  const ts = tracks(Pl.cur); let i = 0;
  while (i < ts.length - 1 && ts[i + 1].start <= t) i++;
  const off = Math.max(0, t - ts[i].start);
  if (i !== track || !audio.src || audio.dataset.url !== ts[i].url) {
    track = i; audio.dataset.url = ts[i].url; audio.src = ts[i].url; pending = off;
    audio.addEventListener('loadedmetadata', () => { try { audio.currentTime = pending || 0; } catch(e){} pending = null; if (play) go(); }, { once: true });
    audio.load();
  } else { audio.currentTime = off; if (play) go(); }
}
const go = () => { const p = audio.play(); if (p && p.catch) p.catch(() => {}); };
const tell = (ev, info) => { const it = Pl.cur; if (it && !it.driven && it.save) { try { it.save(ev, info || {}); } catch(e){} } };
Pl.play = (item, opts) => {
  opts = opts || {};
  if (Pl.cur && Pl.cur.id === item.id && !Pl.cur.driven) {           // the same one: just go on
    if (opts.at != null) Pl.seek(opts.at);
    if (opts.play !== false) go();
    return;
  }
  if (Pl.cur && Pl.cur.driven) { const old = Pl.cur; Pl.cur = null; if (old.act && old.act.close) old.act.close(); }   // read-aloud stops for it
  else Pl.stop(true);
  if (item.back == null) item.back = 15;
  if (item.fwd == null) item.fwd = 30;
  Pl.cur = item; track = -1; sleepAt = 0; sleepEnd = false;
  audio.playbackRate = +store.get('podRate', 1) || 1;
  load(opts.at || 0, opts.play !== false);
  session(); draw();
  window.dispatchEvent(new CustomEvent('daf-player', { detail: { id: item.id } }));
};
Pl.seek = t => {
  if (!media()) return;
  const from = time(); t = Math.max(0, Math.min(t, total() || t));
  tell('seek', { from, to: t });
  load(t, !audio.paused);
  draw();
};
Pl.skip = d => Pl.seek(time() + d);
Pl.toggle = () => {
  const it = Pl.cur; if (!it) return;
  if (it.driven) { it.act && it.act.play && it.act.play(); return; }
  if (audio.paused) { if (pending == null && !audio.src) load(0, true); else go(); } else audio.pause();
};
Pl.pause = () => { if (media() && !audio.paused) audio.pause(); else if (Pl.cur && Pl.cur.driven && Pl.cur.playing) Pl.toggle(); };
Pl.time = time; Pl.total = total;
Pl.playing = () => !!Pl.cur && (Pl.cur.driven ? !!Pl.cur.playing : !audio.paused);
Pl.is = id => !!Pl.cur && Pl.cur.id === id;
// Stopped: the media's last place told, the bar gone. quiet: another is about to take its place.
Pl.stop = quiet => {
  const it = Pl.cur; if (!it) return;
  if (it.driven) { if (!quiet && it.act && it.act.close) { it.act.close(); return; } }
  else { tell('stop', { at: time() }); audio.pause(); audio.removeAttribute('src'); delete audio.dataset.url; audio.load(); }
  Pl.cur = null; Pl.big = false; sleepAt = 0; sleepEnd = false;
  if (!quiet) { draw(); session(); window.dispatchEvent(new CustomEvent('daf-player', { detail: { id: null } })); }
};
audio.addEventListener('play', () => { tell('play', { at: time() }); C.S.listenedAt = Date.now(); draw(); });
audio.addEventListener('pause', () => { if (!audio.ended) tell('pause', { at: time() }); draw(); });
audio.addEventListener('ended', () => {
  const ts = Pl.cur && !Pl.cur.driven ? tracks(Pl.cur) : [];
  if (track < ts.length - 1) { load(ts[track + 1].start, true); return; }   // the audiobook's next file
  tell('ended', { at: time() }); if (sleepEnd) { sleepEnd = false; }
  draw();
});
audio.addEventListener('ratechange', () => { if (media()) store.set('podRate', audio.playbackRate); draw(); });
audio.addEventListener('error', () => { if (media() && audio.src) C.toast('That didn’t play: ' + ((audio.error && audio.error.message) || 'the file didn’t come')); });
let lastTick = 0;
audio.addEventListener('timeupdate', () => {
  if (!media()) return;
  const now = Date.now();
  if (!audio.paused && now - lastTick > 15000) { lastTick = now; tell('tick', { at: time() }); }
  if (sleepAt && now > sleepAt) { sleepAt = 0; audio.pause(); C.toast('Sleep timer: stopped'); }
  if (sleepEnd) { const ch = chapterAt(time()), nx = Pl.cur.chapters && Pl.cur.chapters[ch + 1]; if (nx && time() >= nx.t - 0.3) { sleepEnd = false; audio.pause(); C.toast('Sleep timer: the end of the chapter'); } }
  tickUI();
  window.dispatchEvent(new CustomEvent('daf-player-time', { detail: { id: Pl.cur.id, t: time() } }));
});
document.addEventListener('visibilitychange', () => { if (document.hidden && media()) tell('hidden', { at: time() }); });
window.addEventListener('pagehide', () => { if (media()) tell('hidden', { at: time(), beacon: true }); });
function chapterAt(t){ const chs = (Pl.cur && Pl.cur.chapters) || []; let k = -1; chs.forEach((c, i) => { if (c.t <= t + 0.5) k = i; }); return k; }

/* ---------- read-aloud: shown here, played by its own page ---------- */
// item: { id, title, sub, art, open, playing, rate, voice, sleep, act: { play, next, prev, close, rate, voice(btn), sleep, open } }
Pl.drive = item => {
  if (Pl.cur && Pl.cur.id !== item.id) {
    if (!Pl.cur.driven) Pl.stop(true);
    else if (Pl.cur.act && Pl.cur.act.close) { const old = Pl.cur; Pl.cur = null; old.act.close(); }
  }
  Pl.cur = Object.assign({ driven: true }, item);
  session(); draw();
};
Pl.clear = id => { if (Pl.cur && Pl.cur.id === id) { Pl.cur = null; Pl.big = false; draw(); session(); } };

/* ---------- the lock screen, the Mac's media keys, headphones ---------- */
function session(){
  if (!('mediaSession' in navigator)) return;
  const it = Pl.cur;
  try {
    if (!it) { navigator.mediaSession.metadata = null; return; }
    navigator.mediaSession.metadata = new MediaMetadata({ title: it.title || 'Daf', artist: it.sub || '', artwork: it.art ? [{ src: it.art }] : [] });
    const h = (a, f) => { try { navigator.mediaSession.setActionHandler(a, f); } catch(e){} };
    h('play', () => Pl.toggle()); h('pause', () => Pl.toggle());
    h('seekbackward', it.driven ? null : () => Pl.skip(-(it.back || 15)));
    h('seekforward', it.driven ? null : () => Pl.skip(it.fwd || 30));
    h('previoustrack', () => act('prev')); h('nexttrack', () => act('next'));
    h('seekto', it.driven ? null : e => Pl.seek(e.seekTime));
  } catch(e){}
}

/* ---------- the bar, and the whole player ---------- */
const bar = () => $('#player');
function art(it, cls){
  return it.art ? '<img class="' + cls + '" src="' + esc(it.art) + '" alt="" loading="lazy" onerror="this.outerHTML=\'<span class=&quot;' + cls + ' plart0&quot;></span>\'">'
    : '<span class="' + cls + ' plart0">' + ICON.wave + '</span>';
}
function draw(){
  const p = bar(); if (!p) return;
  const it = Pl.cur;
  if (!it) { p.hidden = true; p.innerHTML = ''; document.body.classList.remove('playing', 'playerbig'); return; }
  p.hidden = false; document.body.classList.add('playing'); document.body.classList.toggle('playerbig', Pl.big);
  const on = Pl.playing(), d = it.driven;
  const prev = d ? '<button class="pbtn" data-tts="prev" aria-label="Previous paragraph">' + ICON.prevp + '</button>'
    : '<button class="pbtn" data-tts="prev" aria-label="Back ' + it.back + ' seconds">' + ICON.back + '</button>';
  const next = d ? '<button class="pbtn" data-tts="next" aria-label="Next paragraph">' + ICON.nextp + '</button>'
    : '<button class="pbtn" data-tts="next" aria-label="Ahead ' + it.fwd + ' seconds">' + ICON.fwd + '</button>';
  const play = '<button class="pround" data-tts="play" aria-label="' + (on ? 'Pause' : 'Play') + '">' + (on ? ICON.pause : ICON.play) + '</button>';
  const frac = d ? (it.of ? Math.min(1, (it.at || 0) / it.of) : 0) : (total() ? time() / total() : 0);
  let h = '<div class="pmini" data-pl="open" role="button" aria-label="Open the player">' + art(it, 'plart') +
    '<div class="pt"><b dir="auto">' + esc(it.title || '') + '</b><span class="mute" dir="auto">' + esc(it.sub || '') + '</span></div>' +
    '<div class="pmctl">' + prev + play + next + '<button class="pbtn pmx" data-tts="close" aria-label="Stop">' + ICON.close + '</button></div>' +
    '<i class="pline" style="width:' + (frac * 100).toFixed(2) + '%"></i></div>';
  if (Pl.big) h += bigHTML(it, prev, play, next);
  p.innerHTML = h;
}
function bigHTML(it, prev, play, next){
  const d = it.driven, chs = it.chapters || [];
  const rate = d ? it.rate || 1 : audio.playbackRate || 1, ch = d ? -1 : chapterAt(time());
  const sl = d ? it.sleep : sleepEnd ? 'chapter' : sleepAt ? Math.max(1, Math.round((sleepAt - Date.now()) / 60000)) : 0;
  const slLabel = sl === 'chapter' ? 'Sleep: end of chapter' : sl ? 'Sleep in ' + sl + ' min' : 'Sleep timer';
  return '<div class="pbig" role="dialog" aria-label="Player"><div class="pgrab" data-pl="close" aria-hidden="true"></div>' +
    '<div class="pbhead"><button class="ib" data-pl="close" aria-label="Close the player">' + ICON.down + '</button><span class="spacer"></span>' +
      (it.open ? '<button class="btn sm" data-pl="go">Go to it</button>' : '') + '</div>' +
    '<div class="pbbody">' + art(it, 'plbig') +
    '<div class="pbt"><b dir="auto">' + esc(it.title || '') + '</b><span class="mute" dir="auto">' + esc(it.sub || '') + '</span>' +
      (ch >= 0 ? '<span class="mute tiny" dir="auto">' + esc(chs[ch].title) + '</span>' : '') + '</div>' +
    (d ? '<div class="pbpara mute tiny">' + (it.of ? '¶ ' + Math.min((it.at || 0) + 1, it.of) + ' of ' + it.of : '') + '</div>'
       : '<div class="pseekw"><input type="range" class="pseek" id="pseek" min="0" max="1000" step="1" value="' + Math.round(total() ? time() / total() * 1000 : 0) + '" aria-label="Where it is">' +
         '<div class="ptimes"><span id="ptnow">' + fmt(time()) + '</span><span id="ptleft">−' + fmt(Math.max(0, total() - time()) / rate) + '</span></div></div>') +
    '<div class="pbctl">' + prev + play + next + '</div>' +
    '<div class="pbmore"><button class="btn sm" data-pl="rate">' + (Math.round(rate * 100) / 100) + '×</button>' +
      '<button class="btn sm" data-pl="sleep">' + slLabel + '</button>' +
      (d && it.act && it.act.voice ? '<button class="btn sm" data-tts="voice" data-pl="voice">' + esc(it.voice || 'Voice') + '</button>' : '') +
      (chs.length ? '<select class="field sm" data-pl="chap" aria-label="Chapters"><option value="">Chapters</option>' + chs.map((c, i) => '<option value="' + i + '"' + (i === ch ? ' selected' : '') + '>' + fmt(c.t) + '  ' + esc(c.title) + '</option>').join('') + '</select>' : '') +
      '<button class="btn sm" data-tts="close">Stop</button></div></div></div>';
}
// Every half second while it plays: the line, and the whole player's time, without drawing it all again.
function tickUI(){
  const p = bar(); if (!p || !Pl.cur) return;
  const T = total(), t = time(), line = p.querySelector('.pline');
  if (line) line.style.width = (T ? t / T * 100 : 0).toFixed(2) + '%';
  if (!Pl.big) return;
  const s = $('#pseek'); if (s && !s.matches(':active') && !seeking) s.value = Math.round(T ? t / T * 1000 : 0);
  const n = $('#ptnow'), l = $('#ptleft'); if (n) n.textContent = fmt(t); if (l) l.textContent = '−' + fmt(Math.max(0, T - t) / (audio.playbackRate || 1));
}
let seeking = false;
function act(a, btn){
  const it = Pl.cur; if (!it) return;
  if (it.driven) { const f = it.act && it.act[a]; if (f) f(btn); return; }
  if (a === 'play') Pl.toggle();
  else if (a === 'prev') Pl.skip(-(it.back || 15));
  else if (a === 'next') Pl.skip(it.fwd || 30);
  else if (a === 'close') Pl.stop();
}
Pl.act = act;
document.addEventListener('click', e => {
  const p = bar(); if (!p || !p.contains(e.target)) return;
  const t = e.target.closest('[data-tts], [data-pl]'); if (!t) return;
  const it = Pl.cur; if (!it) return;
  if (t.dataset.tts && !(t.dataset.pl === 'voice')) { e.stopPropagation(); act(t.dataset.tts, t); return; }
  const a = t.dataset.pl;
  if (a === 'open' && !e.target.closest('button')) { Pl.big = true; draw(); return; }
  if (a === 'close') { Pl.big = false; draw(); return; }
  if (a === 'go') { Pl.big = false; draw(); if (it.act && it.act.open) it.act.open(); else if (it.open) location.hash = it.open; return; }
  if (a === 'voice') { e.stopPropagation(); if (it.act && it.act.voice) it.act.voice(t); return; }
  if (a === 'rate') {
    if (it.driven) { if (it.act && it.act.rate) it.act.rate(); return; }
    const i = RATES.findIndex(r => Math.abs(r - audio.playbackRate) < 0.01); audio.playbackRate = RATES[(i + 1) % RATES.length]; return;
  }
  if (a === 'sleep') {
    if (it.driven) { if (it.act && it.act.sleep) it.act.sleep(); return; }
    const cur = sleepEnd ? -1 : sleepAt ? Math.round((sleepAt - Date.now()) / 60000) : 0;
    const steps = (it.chapters || []).length ? SLEEP : SLEEP.slice(0, -1);
    const k = cur === -1 ? steps.length - 1 : steps.findIndex(m => m > cur + 1 || m === -1);
    const nx = steps[(k < 0 ? 0 : k + (cur === -1 ? 1 : 0)) % steps.length];
    sleepEnd = nx === -1; sleepAt = nx > 0 ? Date.now() + nx * 60000 : 0; draw(); return;
  }
}, true);
document.addEventListener('change', e => {
  if (e.target.dataset && e.target.dataset.pl === 'chap' && e.target.value !== '') { const c = (Pl.cur.chapters || [])[+e.target.value]; if (c) Pl.seek(c.t); }
});
document.addEventListener('input', e => {
  if (e.target.id !== 'pseek') return;
  seeking = true; const t = +e.target.value / 1000 * total(); const n = $('#ptnow'); if (n) n.textContent = fmt(t);
});
document.addEventListener('change', e => { if (e.target.id === 'pseek') { seeking = false; Pl.seek(+e.target.value / 1000 * total()); } });
// The bar pulled up opens the whole player; the whole player pulled down closes it.
(() => {
  let y0 = null, wasBig = false;
  document.addEventListener('touchstart', e => {
    const p = bar(); if (!p || p.hidden || !p.contains(e.target) || e.target.closest('input, select, button:not([data-pl="close"])')) { y0 = null; return; }
    y0 = e.touches[0].clientY; wasBig = Pl.big;
  }, { passive: true });
  document.addEventListener('touchend', e => {
    if (y0 == null) return;
    const dy = (e.changedTouches[0] || {}).clientY - y0; y0 = null;
    if (!wasBig && dy < -30) { Pl.big = true; draw(); }
    else if (wasBig && dy > 60) { Pl.big = false; draw(); }
  }, { passive: true });
})();
document.addEventListener('keydown', e => { if (e.key === 'Escape' && Pl.big) { Pl.big = false; draw(); e.stopPropagation(); } }, true);
// A tap on the shade around the whole player closes it.
document.addEventListener('click', e => { if (Pl.big && (e.target === document.body || e.target === document.documentElement)) { Pl.big = false; draw(); } });
Pl.draw = draw;
// The whole player is open: Back (the Android app's too, shell.js closeFront) closes it first.
Pl.close = () => { if (!Pl.big) return false; Pl.big = false; draw(); return true; };
})();
