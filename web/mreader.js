/* The manga reader: #mread/<book>[/<page>], full screen over everything, the same in the browser,
   Daf for Mac and Daf for Android.

   Taken from the good manga readers:
   - Mihon / Kahon: the page under the finger (it follows a swipe and slides into place on a tap),
     tap zones with their layouts and inversion, the reading modes, the transition page between
     volumes, pinch and double-tap zoom, the quick buttons under the slider.
   - Suwayomi: its settings (layout per series, scale, background, filters, behaviour), auto scroll,
     the tap-zone overlay, cropped borders.
   - Komga: the thumbnail explorer, the keyboard help, full screen.

   Pages and progress come from Komga through daf/manga.py; the settings live on morten
   (/api/manga/prefs), the layout ones per series, so every device reads a series the same way. */
(() => {
const C = window.DafCore, { api, esc, toast, $ } = C;
const M = C.Manga || (C.Manga = {});

/* ---------- settings ---------- */
const DEF = {
  mode: 'rtl', layout: 'auto', shift: false, split: false, scale: 'screen', stretch: true, crop: false,
  zones: 'auto', invert: 'none', swipe: true, animate: true, dbltap: true, volkeys: 'on',
  bg: 'black', pagenum: true, progress: true, stripw: 100, gap: 12, showzones: true,
  autospeed: 8, brightness: 100, contrast: 100, saturate: 100, sepia: 0, grayscale: 0, invertc: 0,
};
const PER_SERIES = ['mode', 'layout', 'shift', 'split', 'scale', 'crop'];
const MODES = [['rtl', 'Right to left', 'Paged, as manga'], ['ltr', 'Left to right', 'Paged, as comics'], ['vertical', 'Vertical', 'Paged, top to bottom'],
  ['strip', 'Long strip', 'Webtoons, no gaps'], ['gaps', 'Strip with gaps', 'One long column, pages apart']];
const LAYOUTS = [['auto', 'Auto'], ['single', 'One page'], ['double', 'Two pages']];
const SCALES = [['screen', 'Fit screen'], ['width', 'Fit width'], ['height', 'Fit height'], ['original', 'Original size']];
const ZONESETS = [['auto', 'Auto'], ['rl', 'Right and left'], ['l', 'L shape'], ['kindle', 'Kindle'], ['edge', 'Edge'], ['off', 'Off']];
const INVERTS = [['none', 'None'], ['h', 'Left–right'], ['v', 'Top–bottom'], ['both', 'Both']];
const BGS = [['black', 'Black'], ['gray', 'Gray'], ['white', 'White'], ['auto', 'From the page']];
const label = (list, v) => (list.find(x => x[0] === v) || [, v])[1];
const paged = m => m === 'rtl' || m === 'ltr' || m === 'vertical';
const touch = () => matchMedia('(hover: none) and (pointer: coarse)').matches;

let P = null, pending = { defaults: {}, series: {} }, prefT = 0;
async function loadPrefs(){
  if (!P) { try { P = await api('/api/manga/prefs'); } catch(e){ P = { defaults: {}, series: {} }; } }
  P.defaults = P.defaults || {}; P.series = P.series || {};
  return P;
}
function prefsFor(sid, dir){
  const s = Object.assign({}, DEF, P.defaults, P.series[sid] || {});
  const own = P.series[sid] || {};
  if (!own.mode && !P.defaults.mode) s.mode = dir === 'LEFT_TO_RIGHT' ? 'ltr' : dir === 'WEBTOON' || dir === 'VERTICAL' ? 'strip' : 'rtl';
  return s;
}
function setPref(k, v){
  RD.p[k] = v;
  if (k === 'volkeys') window.dispatchEvent(new Event('daf-reading'));
  const sid = RD.book.series.id;
  if (PER_SERIES.includes(k)) { (P.series[sid] = P.series[sid] || {})[k] = v; ((pending.series[sid] = pending.series[sid] || {}))[k] = v; }
  else { P.defaults[k] = v; pending.defaults[k] = v; }
  clearTimeout(prefT);
  prefT = setTimeout(() => { const b = pending; pending = { defaults: {}, series: {} }; api('/api/manga/prefs', { method: 'PUT', body: JSON.stringify(b) }).catch(() => {}); }, 700);
}
// "Use for every series": this series' layout becomes the default, and it stops having its own.
function layoutForAll(){
  const sid = RD.book.series.id, own = P.series[sid] || {}, d = {};
  PER_SERIES.forEach(k => { d[k] = RD.p[k]; P.defaults[k] = RD.p[k]; });
  delete P.series[sid];
  api('/api/manga/prefs', { method: 'PUT', body: JSON.stringify({ defaults: d, series: { [sid]: { _clear: true } } }) }).catch(() => {});
  toast('Every series now reads this way, unless it has its own');
  return own;
}

/* ---------- pages ---------- */
let RD = null;
const isWide = p => p.w && p.h && p.w > p.h * 1.1;
const dpr = () => Math.min(window.devicePixelRatio || 1, 2.5);
function sizeFor(p){
  const W = innerWidth, H = innerHeight, r = (p.h || 3) / (p.w || 2);
  if (!paged(RD.p.mode)) return Math.min(2400, Math.ceil(stripWidth() * dpr() * Math.max(1, r)));
  if (RD.p.scale === 'width') return Math.min(2400, Math.ceil(W * dpr() * Math.max(1, r)));
  if (RD.p.scale === 'original') return 2400;
  return Math.min(2400, Math.ceil(Math.max(W, H) * dpr()));
}
// The address of page n (from 1); manga.js and the apps' offline copies use the same one.
M.pageUrl = (bookId, n, size, crop) => '/api/manga/books/' + encodeURIComponent(bookId) + '/pages/' + n + '?size=' + (size || M.downloadSize()) + (crop ? '&crop=1' : '');
M.downloadSize = M.downloadSize || (() => Math.min(2400, Math.ceil(Math.max(innerWidth, innerHeight) * dpr())));
const src = (n, size) => M.pageUrl(RD.book.id, n + 1, size || sizeFor(RD.book.pages[n]), RD.p.crop);
const stripWidth = () => Math.min(innerWidth, innerWidth >= 700 ? Math.max(320, Math.min(980, innerWidth * RD.p.stripw / 100)) : innerWidth) * (RD.sz || 1);

// What's on screen at once, in order: the start card (when there's a volume before), the pages
// (in twos when the layout says so; a wide page alone, or split in two halves), the end card.
function buildUnits(){
  const ps = RD.book.pages, n = ps.length, us = [];
  const pg = paged(RD.p.mode), side = pg && RD.p.mode !== 'vertical';   // pairs and halves only when pages sit side by side
  if (RD.book.prev && pg) us.push({ t: 'start' });
  const two = side && (RD.p.layout === 'double' || (RD.p.layout === 'auto' && innerWidth > innerHeight * 1.05));
  let i = 0;
  if (two) {
    if (!RD.p.shift && n) { us.push({ t: 'p', pages: [0] }); i = 1; }
    while (i < n) {
      if (isWide(ps[i]) || i + 1 >= n || isWide(ps[i + 1])) { us.push({ t: 'p', pages: [i] }); i++; }
      else { us.push({ t: 'p', pages: [i, i + 1] }); i += 2; }
    }
  } else {
    for (; i < n; i++) {
      if (side && RD.p.split && isWide(ps[i])) {
        const first = RD.p.mode === 'rtl' ? 'R' : 'L';
        us.push({ t: 'h', n: i, side: first, pages: [i] }, { t: 'h', n: i, side: first === 'R' ? 'L' : 'R', pages: [i] });
      } else us.push({ t: 'p', pages: [i] });
    }
  }
  us.push({ t: 'end' });
  return us;
}
const unitOfPage = i => { const k = RD.units.findIndex(u => u.pages && u.pages.includes(i)); return k < 0 ? 0 : k; };
const curPages = () => { const u = RD.units[RD.k]; return u.pages || (u.t === 'end' ? [RD.book.pages.length - 1] : [0]); };

function cardHTML(u){
  const b = RD.book;
  if (u.t === 'start') return '<div class="mcard2"><span class="mute">Before this</span><b>' + esc(b.prev_name || 'The previous volume') + '</b>' +
    '<button class="mbtn primary" data-mr="prevvol">Read it</button><span class="mute tiny">' + (RD.p.mode === 'rtl' ? 'Swipe right' : RD.p.mode === 'vertical' ? 'Swipe down' : 'Swipe left') + ' for its last page</span></div>';
  return '<div class="mcard2"><span class="mute">Finished</span><b>' + esc(b.name) + '</b>' +
    (b.next ? '<span class="mute">Next</span><b>' + esc(b.next_name || 'the next volume') + '</b><button class="mbtn primary" data-mr="nextvol">Keep reading</button>' +
      '<span class="mute tiny">or keep turning</span>' : '<span class="mute">That’s the last volume in Komga.</span>') +
    '<button class="mbtn" data-mr="toseries">Back to the series</button></div>';
}
function unitHTML(u){
  if (!u) return '';
  if (u.t === 'start' || u.t === 'end') return cardHTML(u);
  const ps = RD.book.pages;
  if (u.t === 'h') {
    const p = ps[u.n];
    return '<div class="mpage half sc-' + RD.p.scale + '" data-n="' + u.n + '"><div class="mhalf" role="img" aria-label="Page ' + (u.n + 1) + ', ' + (u.side === 'L' ? 'left' : 'right') + ' half" style="--arw:' +
      ((p.w || 2) / 2) + ';--arh:' + (p.h || 3) + ';background-image:url(\'' + src(u.n) + '\');background-position:' + (u.side === 'L' ? 'left' : 'right') + ' center"></div></div>';
  }
  return '<div class="mpage sc-' + RD.p.scale + (u.pages.length > 1 ? ' two' : '') + (RD.p.stretch ? ' stretch' : '') + '">' +
    u.pages.map(n => '<img class="mpg" data-n="' + n + '" alt="Page ' + (n + 1) + '" decoding="async" draggable="false" src="' + src(n) + '">').join('') + '</div>';
}

/* ---------- open, close ---------- */
M.open = async (bid, page, opts) => {
  close(true);
  const el = document.createElement('div');
  el.id = 'mreader'; el.className = 'mreader'; el.tabIndex = -1;
  el.innerHTML = '<div class="mload">Opening…</div>';
  document.body.appendChild(el);
  let b;
  try { [b] = await Promise.all([api('/api/manga/books/' + encodeURIComponent(bid)), loadPrefs()]); }
  catch(e){ el.querySelector('.mload').textContent = e.message; setTimeout(() => close(), 2500); return; }
  // Gone somewhere else while it loaded (or another volume opened): don't come up over that page.
  if (!el.isConnected || !/^#mread\//.test(location.hash)) { el.remove(); return; }
  RD = { el, book: b, k: 0, p: prefsFor(b.series.id, (b.series.direction || '').toUpperCase()), bar: false, z: { s: 1, x: 0, y: 0 }, sz: 1,
    saveT: 0, savedPage: b.page, lastActive: Date.now(), wake: null, auto: false, busy: false, shown: new Set() };
  window.dispatchEvent(new Event('daf-reading'));   // the app hears whether its volume keys are the reader's (shell.js)
  const n = b.pages.length;
  let start = page ? page - 1 : b.completed ? 0 : Math.max(0, (b.page || 1) - 1);
  if (opts && opts.atEnd) start = n - 1;
  el.innerHTML = '<div class="mstage" id="mstage"></div><div class="mzones" hidden></div><div class="mpnum" hidden></div><div class="mprog"><i></i></div>' +
    '<div class="mtop" hidden></div><div class="mbot" hidden></div><div class="msheet" hidden></div>';
  wire(el);
  layout(Math.min(Math.max(0, start), n - 1));
  el.focus();
  try { RD.wake = await navigator.wakeLock.request('screen'); } catch(e){}
  if (!(opts && opts.quiet)) toast(label(MODES, RD.p.mode) + (paged(RD.p.mode) && RD.p.mode !== 'vertical' && RD.units.some(u => u.pages && u.pages.length > 1) ? ' · two pages' : ''));
  zonesHint();
};
function close(quiet){
  if (!RD) { const old = $('#mreader'); if (old) old.remove(); return; }
  const r = RD; save(false); autoStop(); RD = null;
  if (io) { io.disconnect(); io = null; }
  try { r.wake && r.wake.release(); } catch(e){}
  if (document.fullscreenElement) document.exitFullscreen().catch(() => {});
  r.el.remove();
  if (!quiet && (C.S.route || [])[0] === 'mread') {
    if (history.length > 1 && M.cameIn) history.back(); else location.hash = 'manga/' + encodeURIComponent(r.book.series.id);
  }
}
M.close = close;
async function otherVolume(id, atEnd){
  if (!id || !RD) return;
  await save(RD.units[RD.k].t === 'end');
  history.replaceState(null, '', '#mread/' + encodeURIComponent(id)); C.S.route = ['mread', encodeURIComponent(id)];
  const bar = RD.bar;
  await M.open(id, null, { atEnd, quiet: true });
  if (RD && bar) toggleBar(true);
  if (RD) toast(RD.book.name);
}

/* ---------- laying out ---------- */
// (Re)build everything around page i: on open, and whenever the mode, layout or screen changes.
function layout(i){
  RD.units = buildUnits();
  const st = $('#mstage');
  st.className = 'mstage ' + (paged(RD.p.mode) ? 'paged' : 'strip') + (RD.p.mode === 'vertical' ? ' vert' : '') + (RD.p.mode === 'rtl' ? ' rtl' : '');
  RD.el.dataset.mode = RD.p.mode;
  applyLook();
  if (io) { io.disconnect(); io = null; }
  if (paged(RD.p.mode)) {
    st.innerHTML = '<div class="mtrack"></div>';
    RD.k = i === 'end' ? RD.units.length - 1 : unitOfPage(i);
    slots();
  } else {
    RD.k = unitOfPage(i);
    const gap = RD.p.mode === 'gaps' ? RD.p.gap : 0, w = stripWidth();
    st.innerHTML = '<div class="mstrip" style="--sw:' + w + 'px;--gap:' + gap + 'px">' + RD.book.pages.map((p, n) => '<img class="mpg" data-n="' + n + '" alt="Page ' + (n + 1) + '" loading="lazy" decoding="async" draggable="false"' +
      (p.w && p.h ? ' width="' + p.w + '" height="' + p.h + '"' : '') + ' src="' + src(n) + '">').join('') + '<div class="mstripend">' + cardHTML({ t: 'end' }) + '</div></div>';
    const im = st.querySelector('[data-n="' + i + '"]'); if (im) im.scrollIntoView({ block: 'start' });
    watchStrip();
  }
  drawBars(); counter();
}
// The three places of the pager: the unit before, this one, the one after. In right-to-left the one
// after sits on the left; in vertical, below.
const axis = () => RD.p.mode === 'vertical' ? 'y' : 'x';
const sgn = () => RD.p.mode === 'rtl' ? -1 : 1;
const tr = (v, unit) => axis() === 'x' ? 'translate3d(' + v + unit + ',0,0)' : 'translate3d(0,' + v + unit + ',0)';
function slots(){
  const t = RD.el.querySelector('.mtrack'); if (!t) return;
  t.style.transition = 'none'; t.style.transform = '';
  t.innerHTML = [-1, 0, 1].map(o => '<div class="mslot' + (o ? '' : ' cur') + '" data-o="' + o + '" style="transform:' + tr(o * sgn() * 100, '%') + '">' + unitHTML(RD.units[RD.k + o]) + '</div>').join('');
  RD.z = { s: 1, x: 0, y: 0 };
  const cur = t.querySelector('.mslot.cur');
  if (cur && RD.p.scale === 'width') cur.scrollTop = 0;
  preload();
  bgFromPage();
  counter();
}
function preload(){
  for (const o of [2, 3, -2]) for (const n of ((RD.units[RD.k + o] || {}).pages || [])) { const im = new Image(); im.decoding = 'async'; im.src = src(n); }
}

/* ---------- turning ---------- */
function go(d, opts){
  if (!RD || !paged(RD.p.mode) || RD.busy) return;
  const t = RD.k + d;
  if (t >= RD.units.length) { if (RD.book.next) otherVolume(RD.book.next); else toast('That’s the end of what Komga has'); return; }
  if (t < 0) { if (RD.book.prev) otherVolume(RD.book.prev, true); else toast('The start of ' + RD.book.name); return; }
  if (Math.abs(d) > 1 || !RD.p.animate || (opts && opts.instant)) { RD.k = t; slots(); turned(); return; }
  slide(d, (opts && opts.from) || 0);
}
// Slide the track a whole page (from where the finger left it), then rebuild around the new page.
function slide(d, fromPx){
  const t = RD.el.querySelector('.mtrack'), size = axis() === 'x' ? innerWidth : innerHeight;
  const target = -d * sgn() * size, left = Math.abs(target - fromPx) / size;
  RD.busy = true;
  t.style.transition = 'transform ' + Math.round(Math.max(110, 280 * left)) + 'ms cubic-bezier(.22,.7,.3,1)';
  requestAnimationFrame(() => { t.style.transform = tr(target, 'px'); });
  let done = false;
  const end = () => { if (done || !RD) return; done = true; RD.busy = false; RD.k += d; slots(); turned(); };
  t.addEventListener('transitionend', end, { once: true });
  setTimeout(end, 420);
}
function snapBack(){
  const t = RD.el.querySelector('.mtrack'); if (!t) return;
  t.style.transition = 'transform 180ms cubic-bezier(.22,.7,.3,1)'; t.style.transform = '';
}
function turned(){
  RD.lastActive = Date.now();
  const u = RD.units[RD.k];
  if (u.t === 'end') save(true); else queueSave();
}
const next = () => paged(RD.p.mode) ? go(1) : scrollScreen(1), prev = () => paged(RD.p.mode) ? go(-1) : scrollScreen(-1);
function scrollScreen(d){ $('#mstage').scrollBy({ top: d * innerHeight * 0.85, behavior: RD.p.animate ? 'smooth' : 'auto' }); RD.lastActive = Date.now(); }
// Which way "left" and "right" go depends on the reading direction.
function act(t){
  if (t === 'menu') return toggleBar();
  if (RD.bar) return toggleBar(false);          // with the bars open, a tap anywhere just closes them
  if (t === 'next') return next();
  if (t === 'prev') return prev();
  if (t === 'left') return RD.p.mode === 'rtl' ? next() : prev();
  if (t === 'right') return RD.p.mode === 'rtl' ? prev() : next();
}

/* ---------- tap zones (Mihon's layouts) ---------- */
const ZONES = {
  rl: [{ x: 0, y: 0, w: 1 / 3, h: 1, t: 'left' }, { x: 2 / 3, y: 0, w: 1 / 3, h: 1, t: 'right' }],
  l: [{ x: 0, y: 0, w: 1, h: 1 / 3, t: 'prev' }, { x: 0, y: 1 / 3, w: 1 / 3, h: 1 / 3, t: 'prev' }, { x: 2 / 3, y: 1 / 3, w: 1 / 3, h: 1 / 3, t: 'next' }, { x: 0, y: 2 / 3, w: 1, h: 1 / 3, t: 'next' }],
  kindle: [{ x: 0, y: 1 / 3, w: 1 / 3, h: 2 / 3, t: 'prev' }, { x: 1 / 3, y: 1 / 3, w: 2 / 3, h: 2 / 3, t: 'next' }],
  edge: [{ x: 0, y: 0, w: 1 / 3, h: 1, t: 'next' }, { x: 2 / 3, y: 0, w: 1 / 3, h: 1, t: 'next' }, { x: 1 / 3, y: 2 / 3, w: 1 / 3, h: 1 / 3, t: 'prev' }],
  off: [],
};
const zoneSet = () => RD.p.zones === 'auto' ? (paged(RD.p.mode) ? 'rl' : 'l') : RD.p.zones;
function zoneAt(fx, fy){
  const inv = RD.p.invert;
  if (inv === 'h' || inv === 'both') fx = 1 - fx;
  if (inv === 'v' || inv === 'both') fy = 1 - fy;
  const z = (ZONES[zoneSet()] || []).find(r => fx >= r.x && fx < r.x + r.w && fy >= r.y && fy < r.y + r.h);
  return z ? z.t : 'menu';
}
const ZLABEL = t => ({ next: 'Next', prev: 'Previous', left: RD.p.mode === 'rtl' ? 'Next' : 'Previous', right: RD.p.mode === 'rtl' ? 'Previous' : 'Next' })[t];
function showZones(){
  const z = RD.el.querySelector('.mzones'), inv = RD.p.invert;
  const fl = r => ({ x: inv === 'h' || inv === 'both' ? 1 - r.x - r.w : r.x, y: inv === 'v' || inv === 'both' ? 1 - r.y - r.h : r.y, w: r.w, h: r.h, t: r.t });
  z.innerHTML = '<div class="mzmenu">Menu</div>' + (ZONES[zoneSet()] || []).map(fl).map(r => '<div class="mz ' + (ZLABEL(r.t) === 'Next' ? 'nx' : 'pv') + '" style="left:' + r.x * 100 + '%;top:' + r.y * 100 + '%;width:' + r.w * 100 + '%;height:' + r.h * 100 + '%"><span>' + ZLABEL(r.t) + '</span></div>').join('');
  z.hidden = false; clearTimeout(RD.zT); RD.zT = setTimeout(() => { if (RD) z.hidden = true; }, 1800);
}
// Once for each mode and zone layout, as Suwayomi does when the layout changes.
function zonesHint(){
  if (!RD.p.showzones) return;
  const key = RD.p.mode + '/' + zoneSet() + '/' + RD.p.invert;
  let seen = []; try { seen = JSON.parse(localStorage.getItem('daf.manga.zonesSeen') || '[]'); } catch(e){}
  if (seen.includes(key)) return;
  seen.push(key); try { localStorage.setItem('daf.manga.zonesSeen', JSON.stringify(seen.slice(-40))); } catch(e){}
  showZones();
}

/* ---------- the look: background, filters, page number, progress line ---------- */
function applyLook(){
  const p = RD.p, el = RD.el;
  el.dataset.bg = p.bg;
  el.style.setProperty('--mfilter', 'brightness(' + p.brightness + '%) contrast(' + p.contrast + '%) saturate(' + p.saturate + '%) sepia(' + p.sepia + '%) grayscale(' + p.grayscale + '%) invert(' + p.invertc + '%)');
  if (p.bg !== 'auto') el.style.removeProperty('--mbg');
}
// "From the page": the colour of the page's corners, so a white page sits on white.
function bgFromPage(){
  if (!RD || RD.p.bg !== 'auto') return;
  const im = RD.el.querySelector('.mslot.cur img'); if (!im) return;
  const pick = () => { try {
    const c = document.createElement('canvas'); c.width = c.height = 8; const x = c.getContext('2d');
    x.drawImage(im, 0, 0, 8, 8); const d = x.getImageData(0, 0, 8, 8).data, at = i => [d[i], d[i + 1], d[i + 2]];
    const cs = [at(0), at(28), at(224), at(252)], avg = [0, 1, 2].map(k => Math.round(cs.reduce((s, v) => s + v[k], 0) / 4));
    if (RD) RD.el.style.setProperty('--mbg', 'rgb(' + avg.join(',') + ')');
  } catch(e){} };
  if (im.complete) pick(); else im.addEventListener('load', pick, { once: true });
}
function counter(){
  if (!RD) return;
  const n = RD.book.pages.length, ps = curPages(), u = RD.units[RD.k] || {};
  const lab = u.t === 'end' ? 'End' : u.t === 'start' ? 'Start' : ps.length > 1 ? (ps[0] + 1) + '–' + (ps[1] + 1) : String(ps[0] + 1);
  const pn = RD.el.querySelector('.mpnum');
  pn.textContent = lab + ' / ' + n; pn.hidden = !RD.p.pagenum || RD.bar;
  const pr = RD.el.querySelector('.mprog'); pr.hidden = !RD.p.progress || RD.bar;
  pr.firstChild.style.width = Math.round(100 * (Math.max(...ps) + 1) / n) + '%';
  pr.classList.toggle('rtl', RD.p.mode === 'rtl');
  const c = RD.el.querySelector('.mcount'); if (c) c.textContent = lab + ' / ' + n;
  const r = RD.el.querySelector('.mbot input[type=range]'); if (r && document.activeElement !== r) r.value = ps[0] + 1;
}

/* ---------- the bars ---------- */
const I = {
  back: '<svg viewBox="0 0 20 20" aria-hidden="true"><path d="M12.5 4.5 7 10l5.5 5.5" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  grid: '<svg viewBox="0 0 20 20" aria-hidden="true"><path d="M3.5 3.5h5v5h-5zM11.5 3.5h5v5h-5zM3.5 11.5h5v5h-5zM11.5 11.5h5v5h-5z" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/></svg>',
  gear: '<svg viewBox="0 0 20 20" aria-hidden="true"><path d="M3 5.5h8M15 5.5h2M3 10h2M9 10h8M3 14.5h6M13 14.5h4" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/><circle cx="13" cy="5.5" r="1.9" fill="none" stroke="currentColor" stroke-width="1.6"/><circle cx="7" cy="10" r="1.9" fill="none" stroke="currentColor" stroke-width="1.6"/><circle cx="11" cy="14.5" r="1.9" fill="none" stroke="currentColor" stroke-width="1.6"/></svg>',
  more: '<svg viewBox="0 0 20 20" aria-hidden="true"><circle cx="4.5" cy="10" r="1.4" fill="currentColor"/><circle cx="10" cy="10" r="1.4" fill="currentColor"/><circle cx="15.5" cy="10" r="1.4" fill="currentColor"/></svg>',
  first: '<svg viewBox="0 0 20 20" aria-hidden="true"><path d="M5 4.5v11M15 4.5 8.5 10l6.5 5.5" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  last: '<svg viewBox="0 0 20 20" aria-hidden="true"><path d="M15 4.5v11M5 4.5l6.5 5.5L5 15.5" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  mode: '<svg viewBox="0 0 20 20" aria-hidden="true"><path d="M3.5 4.5h5.5v11H3.5zM11 4.5h5.5v11H11z" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/></svg>',
  strip: '<svg viewBox="0 0 20 20" aria-hidden="true"><path d="M6.5 2.5h7v15h-7zM6.5 7.5h7M6.5 12.5h7" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/></svg>',
  layout: '<svg viewBox="0 0 20 20" aria-hidden="true"><path d="M2.5 4.5h15v11h-15zM10 4.5v11" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/></svg>',
  scale: '<svg viewBox="0 0 20 20" aria-hidden="true"><path d="M3.5 7.5v-4h4M16.5 7.5v-4h-4M3.5 12.5v4h4M16.5 12.5v4h-4" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  play: '<svg viewBox="0 0 20 20" aria-hidden="true"><path d="M6.5 4.5v11l9-5.5z" fill="currentColor"/></svg>',
  pause: '<svg viewBox="0 0 20 20" aria-hidden="true"><path d="M6 4.5h2.8v11H6zM11.2 4.5H14v11h-2.8z" fill="currentColor"/></svg>',
  crop: '<svg viewBox="0 0 20 20" aria-hidden="true"><path d="M5.5 2.5v12h12M2.5 5.5h12v12" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/></svg>',
};
function drawBars(){
  if (!RD) return;
  const b = RD.book, n = b.pages.length, ps = curPages(), rtl = RD.p.mode === 'rtl', top = RD.el.querySelector('.mtop'), bot = RD.el.querySelector('.mbot');
  top.innerHTML = '<button class="mic" data-mr="close" aria-label="Close" title="Close (Esc)">' + I.back + '</button>' +
    '<span class="mtitle"><b>' + esc(b.series.name || '') + '</b><span>' + esc(b.name) + '</span></span>' +
    '<span class="mcount"></span>' +
    '<button class="mic" data-mr="thumbs" aria-label="All pages" title="All pages (T)">' + I.grid + '</button>' +
    '<button class="mic" data-mr="settings" aria-label="Reading settings" title="Reading settings (S)">' + I.gear + '</button>' +
    '<button class="mic" data-mr="more" aria-label="More" title="More">' + I.more + '</button>';
  // Previous / next volume sit where the reading direction puts them.
  const pv = '<button class="mic" data-mr="prevvol" aria-label="Previous volume" title="Previous volume ([)"' + (b.prev ? '' : ' disabled') + '>' + (rtl ? I.last : I.first) + '</button>';
  const nv = '<button class="mic" data-mr="nextvol" aria-label="Next volume" title="Next volume (])"' + (b.next ? '' : ' disabled') + '>' + (rtl ? I.first : I.last) + '</button>';
  const q = (k, icon, lab, on) => '<button class="mq' + (on ? ' on' : '') + '" data-mq="' + k + '">' + icon + '<span>' + esc(lab) + '</span></button>';
  bot.innerHTML = '<div class="mslide">' + (rtl ? nv : pv) + '<span class="mpn">' + (rtl ? n : 1) + '</span>' +
    '<input type="range" min="1" max="' + n + '" value="' + (ps[0] + 1) + '" dir="' + (rtl ? 'rtl' : 'ltr') + '" aria-label="Page">' +
    '<span class="mpn">' + (rtl ? 1 : n) + '</span>' + (rtl ? pv : nv) + '</div>' +
    '<div class="mquick">' + q('mode', paged(RD.p.mode) ? I.mode : I.strip, label(MODES, RD.p.mode)) +
    (paged(RD.p.mode) && RD.p.mode !== 'vertical' ? q('layout', I.layout, RD.p.layout === 'auto' ? 'Auto layout' : label(LAYOUTS, RD.p.layout)) : '') +
    (paged(RD.p.mode) ? q('scale', I.scale, label(SCALES, RD.p.scale)) : '') +
    q('crop', I.crop, 'Crop borders', RD.p.crop) + q('auto', RD.auto ? I.pause : I.play, RD.auto ? 'Stop' : 'Auto scroll', RD.auto) + '</div>';
  top.hidden = bot.hidden = !RD.bar;
  RD.el.classList.toggle('bars', RD.bar);
  counter();
}
function toggleBar(on){ RD.bar = on == null ? !RD.bar : on; if (!RD.bar) closeSheet(); drawBars(); }

/* ---------- sheets: settings, all pages, keys, more ---------- */
function openSheet(kind, tab){
  const s = RD.el.querySelector('.msheet');
  RD.sheet = kind; RD.tab = tab || RD.tab || 'reading';
  s.className = 'msheet ' + kind; s.hidden = false;
  if (kind === 'settings') drawSettings();
  else if (kind === 'thumbs') drawThumbs();
  else if (kind === 'keys') drawKeys();
  else if (kind === 'more') drawMore();
}
function closeSheet(){ if (!RD) return; const s = RD.el.querySelector('.msheet'); if (s) { s.hidden = true; s.innerHTML = ''; } RD.sheet = null; }
const seg = (k, list, help) => '<div class="mrow"><span class="mlab">' + help + '</span><div class="mseg">' + list.map(x => '<button data-mset="' + k + '" data-v="' + x[0] + '" class="' + (String(RD.p[k]) === String(x[0]) ? 'on' : '') + '"' + (x[2] ? ' title="' + esc(x[2]) + '"' : '') + '>' + esc(x[1]) + '</button>').join('') + '</div></div>';
const tog = (k, lab, sub) => '<label class="mrow mtog"><span class="mlab">' + lab + (sub ? '<small>' + sub + '</small>' : '') + '</span><input type="checkbox" data-mtog="' + k + '"' + (RD.p[k] ? ' checked' : '') + '></label>';
const rng = (k, lab, min, max, step, unit) => '<label class="mrow mrng"><span class="mlab">' + lab + '<small data-mval="' + k + '">' + RD.p[k] + (unit || '') + '</small></span><input type="range" data-mrange="' + k + '" min="' + min + '" max="' + max + '" step="' + (step || 1) + '" value="' + RD.p[k] + '" data-unit="' + (unit || '') + '"></label>';
function drawSettings(){
  const s = RD.el.querySelector('.msheet'), t = RD.tab, p = RD.p, pg = paged(p.mode), own = P.series[RD.book.series.id] || {};
  const tabs = [['reading', 'Reading'], ['controls', 'Controls'], ['display', 'Display'], ['filters', 'Filters']];
  let h = '<div class="mshead"><div class="mtabs" role="tablist">' + tabs.map(x => '<button role="tab" data-mtab="' + x[0] + '" class="' + (t === x[0] ? 'on' : '') + '">' + x[1] + '</button>').join('') + '</div><button class="mic" data-mr="sheetclose" aria-label="Close">×</button></div><div class="msbody">';
  if (t === 'reading') {
    h += '<p class="mnote">For ' + esc(RD.book.series.name || 'this series') + (PER_SERIES.some(k => k in own) ? '' : ' (as every series reads)') + '. <button class="mlink" data-mr="forall">Use for every series</button></p>' +
      seg('mode', MODES, 'Reading mode') +
      (pg && p.mode !== 'vertical' ? seg('layout', LAYOUTS, 'Pages') + tog('shift', 'Shift pairs by one', 'When two pages that belong together don’t land side by side') : '') +
      (pg && p.mode !== 'vertical' ? tog('split', 'Split wide pages', 'A two-page spread shown as two pages, in reading order, when one page is on screen') : '') +
      (pg ? seg('scale', SCALES, 'Scale') + tog('stretch', 'Stretch small pages', 'Up to the screen, when a page is smaller') : rng('stripw', 'Strip width on wide screens', 40, 100, 5, '%') + (p.mode === 'gaps' ? rng('gap', 'Gap between pages', 0, 60, 2, 'px') : '')) +
      tog('crop', 'Crop borders', 'Trims white or black margins off each page');
  } else if (t === 'controls') {
    h += seg('zones', ZONESETS, 'Tap zones') + '<div class="mrow"><span class="mlab"></span><button class="mlink" data-mr="showzones">Show the tap zones</button></div>' +
      seg('invert', INVERTS, 'Invert tap zones') +
      (pg ? tog('swipe', 'Swipe to turn', 'The page follows your finger') + tog('animate', 'Slide pages', 'Pages slide in when you tap or press a key; off turns them at once') : tog('animate', 'Smooth scrolling', 'Taps and keys glide down a screen')) +
      tog('dbltap', 'Double tap to zoom', 'Pinch zooms either way') + rng('autospeed', 'Auto scroll: seconds a page (or a screen)', 2, 30, 1, ' s') +
      (window.dafShell ? seg('volkeys', [['on', 'Turn pages'], ['inv', 'Inverted'], ['off', 'Off']], 'Volume keys') : '') +
      tog('showzones', 'Show the tap zones', 'For a moment, when the mode or zones change');
  } else if (t === 'display') {
    h += seg('bg', BGS, 'Background') + tog('pagenum', 'Page number', 'At the bottom while the bars are hidden') + tog('progress', 'Progress line', 'A thin line along the bottom edge');
  } else {
    h += rng('brightness', 'Brightness', 30, 130, 5, '%') + rng('contrast', 'Contrast', 50, 150, 5, '%') + rng('saturate', 'Saturation', 0, 200, 10, '%') +
      rng('sepia', 'Sepia', 0, 100, 10, '%') + rng('grayscale', 'Grayscale', 0, 100, 10, '%') + rng('invertc', 'Invert', 0, 100, 100, '%') +
      '<div class="mrow"><span class="mlab"></span><button class="mlink" data-mr="resetfilters">Reset the filters</button></div>';
  }
  s.innerHTML = h + '</div>';
}
function drawThumbs(){
  const s = RD.el.querySelector('.msheet'), cur = curPages()[0];
  s.innerHTML = '<div class="mshead"><b>' + esc(RD.book.name) + '</b><span class="mute">' + RD.book.pages.length + ' pages</span><button class="mic" data-mr="sheetclose" aria-label="Close">×</button></div>' +
    '<div class="mthumbs' + (RD.p.mode === 'rtl' ? ' rtl' : '') + '">' + RD.book.pages.map((p, n) => '<button data-mgo="' + n + '" class="' + (n === cur ? 'on' : '') + '"><img loading="lazy" decoding="async" alt="" src="' + src(n, 400) + '"><span>' + (n + 1) + '</span></button>').join('') + '</div>';
  const on = s.querySelector('.on'); if (on) on.scrollIntoView({ block: 'center' });
}
function drawKeys(){
  const s = RD.el.querySelector('.msheet');
  const rows = C.Keys.rows('manga');            // keys.js; the arrows turn the page by the reading direction
  s.innerHTML = '<div class="mshead"><b>Keys</b><button class="mic" data-mr="sheetclose" aria-label="Close">×</button></div><div class="msbody"><table class="mkeys">' +
    rows.map(r => '<tr><td><kbd>' + esc(r[0]) + '</kbd></td><td>' + esc(r[1]) + '</td></tr>').join('') + '</table><p class="mute tiny"><a href="#prefs/keys">Change them in Preferences</a></p></div>';
}
function drawMore(){
  const s = RD.el.querySelector('.msheet'), b = RD.book, n = curPages()[0];
  const fs = document.fullscreenEnabled || (window.dafShell && dafShell.can && dafShell.can('fullscreen'));
  s.innerHTML = '<div class="mmenu">' + (fs ? '<button data-mr="fullscreen">' + (document.fullscreenElement ? 'Leave full screen' : 'Full screen') + (C.Keys.label('manga', 'fullscreen') ? ' <kbd>' + esc(C.Keys.label('manga', 'fullscreen')) + '</kbd>' : '') + '</button>' : '') +
    '<button data-mr="showzones">Show the tap zones</button>' +
    '<a href="' + esc(M.pageUrl(b.id, n + 1, 2400, false)) + '" download="' + esc(b.name + ' p' + (n + 1)) + '.webp" data-mr="savepage">Save this page</a>' +
    (touch() ? '' : '<button data-mr="keys">Keys <kbd>?</kbd></button>') + '</div>';
}

/* ---------- progress and auto ---------- */
function queueSave(){ clearTimeout(RD.saveT); RD.saveT = setTimeout(() => save(false), 1500); }
function save(done){
  if (!RD) return Promise.resolve();
  clearTimeout(RD.saveT);
  const b = RD.book, page = Math.max(...curPages()) + 1;
  const completed = !!done || page >= b.pages.length;
  if (page === RD.savedPage && !completed) return Promise.resolve();
  if (completed && RD.savedDone) return Promise.resolve();
  RD.savedPage = page; RD.savedDone = completed;
  return api('/api/manga/books/' + encodeURIComponent(b.id) + '/progress', { method: 'PUT', body: JSON.stringify({ page, completed, at: Math.floor(Date.now() / 1000) }) }).catch(e => toast(e.message));
}
function autoStart(){
  if (!RD) return; RD.auto = true; drawBars();
  const step = () => {
    if (!RD || !RD.auto) return;
    if (paged(RD.p.mode)) {
      RD.autoT = setTimeout(() => { if (!RD || !RD.auto) return; if (!RD.held && !RD.sheet) { if (RD.units[RD.k].t === 'end') { autoStop(); return; } go(1); } step(); }, RD.p.autospeed * 1000);
    } else {
      let last = performance.now();
      const tick = t => {
        if (!RD || !RD.auto) return;
        const dt = Math.min(64, t - last); last = t;
        const st = $('#mstage');
        if (!RD.held && !RD.sheet) { RD.acc = (RD.acc || 0) + innerHeight * 0.85 / RD.p.autospeed * dt / 1000; const px = Math.floor(RD.acc); if (px) { st.scrollTop += px; RD.acc -= px; } }
        if (st.scrollTop + st.clientHeight >= st.scrollHeight - 2) { autoStop(); return; }
        RD.autoT = requestAnimationFrame(tick);
      };
      RD.autoT = requestAnimationFrame(tick);
    }
  };
  step();
  toast('Auto scroll: ' + RD.p.autospeed + ' s ' + (paged(RD.p.mode) ? 'a page' : 'a screen') + '. Tap Stop, or press A');
}
function autoStop(){ if (!RD || !RD.auto) return; RD.auto = false; clearTimeout(RD.autoT); cancelAnimationFrame(RD.autoT); drawBars(); }

/* ---------- the long strip ---------- */
let io = null;
function watchStrip(){
  io = new IntersectionObserver(es => {
    for (const e of es) if (e.isIntersecting && RD) {
      if (e.target.classList.contains('mstripend')) { RD.k = RD.units.length - 1; save(true); counter(); continue; }
      const n = +e.target.dataset.n, k = unitOfPage(n);
      if (k !== RD.k) { RD.k = k; counter(); queueSave(); }
    }
  }, { root: $('#mstage'), rootMargin: '-45% 0px -45% 0px' });
  RD.el.querySelectorAll('.mstrip .mpg, .mstripend').forEach(x => io.observe(x));
}

/* ---------- zoom ---------- */
function zoomEl(){ return RD && (paged(RD.p.mode) ? RD.el.querySelector('.mslot.cur .mpage') : null); }
function applyZoom(){
  const e = zoomEl(); if (!e) return;
  e.style.transform = RD.z.s === 1 ? '' : 'translate(' + RD.z.x + 'px,' + RD.z.y + 'px) scale(' + RD.z.s + ')';
  RD.el.classList.toggle('zoomed', RD.z.s > 1);
}
function zoomAt(x, y, s){
  const z = RD.z, k = s / z.s, cx = innerWidth / 2, cy = innerHeight / 2;
  z.x = (z.x - (x - cx)) * k + (x - cx); z.y = (z.y - (y - cy)) * k + (y - cy); z.s = s;
  if (s <= 1.01) { z.s = 1; z.x = z.y = 0; }
  clampPan(); applyZoom();
}
function clampPan(){ const z = RD.z, mx = innerWidth * (z.s - 1) / 2, my = innerHeight * (z.s - 1) / 2; z.x = Math.max(-mx, Math.min(mx, z.x)); z.y = Math.max(-my, Math.min(my, z.y)); }

/* ---------- touch, mouse, keys ---------- */
function wire(el){
  const pts = new Map(); let g = null, pinch = null, lastTap = { t: 0, x: 0, y: 0 };
  // A page bigger than the screen (fit width, original size) is panned first; at its edge the drag turns the page.
  const scroller = () => { const s = el.querySelector('.mslot.cur'); return s && (s.scrollHeight > s.clientHeight + 2 || s.scrollWidth > s.clientWidth + 2) ? s : null; };
  el.addEventListener('pointerdown', e => {
    if (!RD || e.button > 0 || e.target.closest('.mtop, .mbot, .msheet, .mzones button, .mcard2 button, .mcard2 a')) return;
    if (RD.sheet) { closeSheet(); return; }
    const zs = el.querySelector('.mzones'); if (!zs.hidden) zs.hidden = true;
    pts.set(e.pointerId, { x: e.clientX, y: e.clientY });
    RD.lastActive = Date.now(); RD.held = true;
    if (pts.size === 2) {
      const [a, b] = [...pts.values()];
      pinch = { d: Math.hypot(a.x - b.x, a.y - b.y), s: paged(RD.p.mode) ? RD.z.s : RD.sz, cx: (a.x + b.x) / 2, cy: (a.y + b.y) / 2 };
      if (g && g.drag) snapBack();
      g = null; return;
    }
    g = { x: e.clientX, y: e.clientY, t: performance.now(), zx: RD.z.x, zy: RD.z.y, moved: false, drag: false, sc: scroller(), lx: e.clientX, ly: e.clientY, lt: performance.now(), vx: 0, vy: 0 };
    if (paged(RD.p.mode)) try { el.setPointerCapture(e.pointerId); } catch(err){}
  });
  el.addEventListener('pointermove', e => {
    if (!RD || !pts.has(e.pointerId)) return;
    pts.set(e.pointerId, { x: e.clientX, y: e.clientY });
    if (pinch && pts.size === 2) {
      const [a, b] = [...pts.values()], s = Math.max(1, Math.min(4, pinch.s * Math.hypot(a.x - b.x, a.y - b.y) / pinch.d));
      if (paged(RD.p.mode)) zoomAt(pinch.cx, pinch.cy, s);
      else if (Math.abs(s - RD.sz) > 0.04) { RD.sz = s; const st = $('#mstage'), f = st.scrollTop / (st.scrollHeight || 1); st.querySelector('.mstrip').style.setProperty('--sw', stripWidth() + 'px'); st.scrollTop = f * st.scrollHeight; }
      return;
    }
    if (!g) return;
    const now = performance.now(), dx = e.clientX - g.x, dy = e.clientY - g.y;
    g.vx = (e.clientX - g.lx) / Math.max(1, now - g.lt); g.vy = (e.clientY - g.ly) / Math.max(1, now - g.lt); g.lx = e.clientX; g.ly = e.clientY; g.lt = now;
    if (!g.moved && Math.hypot(dx, dy) > 8) g.moved = true;
    if (!paged(RD.p.mode) || !g.moved) return;
    if (RD.z.s > 1) { RD.z.x = g.zx + dx; RD.z.y = g.zy + dy; clampPan(); applyZoom(); return; }
    const along = axis() === 'x' ? dx : dy, cross = axis() === 'x' ? dy : dx;
    if (!g.drag && g.sc) {
      // Pan the big page; only once it can't go further that way does the page start to move.
      const s = g.sc, mx = e.movementX || 0, my = e.movementY || 0;
      const atEdge = axis() === 'x' ? (mx > 0 ? s.scrollLeft <= 0 : s.scrollLeft >= s.scrollWidth - s.clientWidth - 1) : (my > 0 ? s.scrollTop <= 0 : s.scrollTop >= s.scrollHeight - s.clientHeight - 1);
      const canCross = axis() === 'x' ? s.scrollHeight > s.clientHeight + 2 : s.scrollWidth > s.clientWidth + 2;
      if (!atEdge || (canCross && Math.abs(cross) > Math.abs(along))) { s.scrollLeft -= mx; s.scrollTop -= my; g.x += axis() === 'x' ? mx : 0; g.y += axis() === 'y' ? my : 0; return; }
    }
    if (!RD.p.swipe) return;
    if (!g.drag && Math.abs(along) > 10 && Math.abs(along) > Math.abs(cross) * 1.2) { g.drag = true; g.from = along; RD.el.querySelector('.mtrack').style.transition = 'none'; }
    if (g.drag) {
      let d = along - g.from;
      const toward = -d * sgn();                           // > 0: toward the next page
      if ((toward > 0 && RD.k >= RD.units.length - 1 && !RD.book.next) || (toward < 0 && RD.k <= 0 && !RD.book.prev)) d *= 0.3;   // nothing there: it resists
      RD.el.querySelector('.mtrack').style.transform = tr(d, 'px');
      g.d = d;
    }
  });
  const up = e => {
    if (!RD || !pts.has(e.pointerId)) return;
    pts.delete(e.pointerId);
    if (!pts.size) RD.held = false;
    if (pinch) { if (!pts.size) pinch = null; g = null; return; }
    const s = g; g = null; if (!s) return;
    if (s.drag) {
      const size = axis() === 'x' ? innerWidth : innerHeight, v = axis() === 'x' ? s.vx : s.vy;
      const toward = -(s.d || 0) * sgn() / size, fling = -v * sgn();
      const d = toward > 0.16 || (fling > 0.45 && toward > 0.02) ? 1 : toward < -0.16 || (fling < -0.45 && toward < -0.02) ? -1 : 0;
      if (!d) { snapBack(); return; }
      const t = RD.k + d;
      if (t < 0 || t >= RD.units.length) { snapBack(); go(d); return; }   // past the end: the next or previous volume
      go(d, { from: s.d || 0 });
      return;
    }
    if (s.moved || e.type === 'pointercancel') return;
    tap(e.clientX, e.clientY);
  };
  el.addEventListener('pointerup', up);
  el.addEventListener('pointercancel', up);
  function tap(x, y){
    const now = performance.now(), double = RD.p.dbltap && now - lastTap.t < 280 && Math.hypot(x - lastTap.x, y - lastTap.y) < 40;
    clearTimeout(RD.tapT);
    if (double) { lastTap.t = 0; if (paged(RD.p.mode)) zoomAt(x, y, RD.z.s > 1 ? 1 : 2.2); else { RD.sz = RD.sz > 1 ? 1 : 1.8; layout(curPages()[0]); } return; }
    lastTap = { t: now, x, y };
    const run = () => { if (!RD) return; if (RD.z.s > 1) { toggleBar(); return; } act(zoneAt(x / innerWidth, y / innerHeight)); };   // zoomed in, taps only bring the bars
    // With double tap on, a single tap waits a moment to be sure; the middle (the menu) doesn't wait.
    const t = zoneAt(x / innerWidth, y / innerHeight);
    if (!RD.p.dbltap || (t === 'menu' && !paged(RD.p.mode))) run(); else RD.tapT = setTimeout(run, 230);
  }
  el.addEventListener('wheel', e => {
    if (!RD || !paged(RD.p.mode) || e.ctrlKey || e.target.closest('.msheet')) return;
    const s = el.querySelector('.mslot.cur');
    if (s && s.scrollHeight > s.clientHeight + 2 && !(e.deltaY > 0 ? s.scrollTop >= s.scrollHeight - s.clientHeight - 1 : s.scrollTop <= 0)) return;   // the big page scrolls first
    e.preventDefault(); RD.lastActive = Date.now();
    if (RD.wheelT && Date.now() - RD.wheelT < 320) return;
    const d = Math.abs(e.deltaY) >= Math.abs(e.deltaX) ? e.deltaY : e.deltaX * sgn();
    if (Math.abs(d) > 6) { RD.wheelT = Date.now(); d > 0 ? next() : prev(); }
  }, { passive: false });
  el.addEventListener('click', e => {
    if (!RD) return;
    const m = e.target.closest('[data-mr],[data-mq],[data-mset],[data-mtab],[data-mgo]'); if (!m) return;
    if (m.dataset.mtab) { RD.tab = m.dataset.mtab; drawSettings(); return; }
    if (m.dataset.mgo) { const n = +m.dataset.mgo; closeSheet(); if (paged(RD.p.mode)) { RD.k = unitOfPage(n); slots(); turned(); } else layout(n); return; }
    if (m.dataset.mset) { change(m.dataset.mset, m.dataset.v); drawSettings(); return; }
    if (m.dataset.mq) { quick(m.dataset.mq); return; }
    const a = m.dataset.mr;
    if (a === 'savepage') { setTimeout(closeSheet, 100); return; }
    e.preventDefault();
    if (a === 'close') close();
    else if (a === 'toseries') { const sid = RD.book.series.id; close(true); location.hash = 'manga/' + encodeURIComponent(sid); }
    else if (a === 'nextvol') otherVolume(RD.book.next);
    else if (a === 'prevvol') otherVolume(RD.book.prev, RD.units[RD.k].t === 'start');
    else if (a === 'thumbs' || a === 'settings' || a === 'more' || a === 'keys') { if (RD.sheet === a) closeSheet(); else openSheet(a); }
    else if (a === 'sheetclose') closeSheet();
    else if (a === 'showzones') { closeSheet(); toggleBar(false); showZones(); }
    else if (a === 'fullscreen') { closeSheet(); fullscreen(); }
    else if (a === 'forall') { layoutForAll(); drawSettings(); }
    else if (a === 'resetfilters') { ['brightness', 'contrast', 'saturate', 'sepia', 'grayscale', 'invertc'].forEach(k => setPref(k, DEF[k])); applyLook(); drawSettings(); }
  });
  el.addEventListener('change', e => {
    if (!RD) return;
    const t = e.target;
    if (t.dataset.mtog) { change(t.dataset.mtog, t.checked); if (RD.sheet === 'settings') drawSettings(); }
    else if (t.dataset.mrange) { change(t.dataset.mrange, +t.value); }
    else if (t.matches('.mbot input[type=range]')) { const n = +t.value - 1; if (paged(RD.p.mode)) { RD.k = unitOfPage(n); slots(); turned(); } else layout(n); }
  });
  el.addEventListener('input', e => {
    if (!RD) return;
    const t = e.target;
    if (t.dataset.mrange) { const v = el.querySelector('[data-mval="' + t.dataset.mrange + '"]'); if (v) v.textContent = t.value + (t.dataset.unit || ''); if (['brightness', 'contrast', 'saturate', 'sepia', 'grayscale', 'invertc'].includes(t.dataset.mrange)) { RD.p[t.dataset.mrange] = +t.value; applyLook(); } }
    else if (t.matches('.mbot input[type=range]')) { const c = el.querySelector('.mcount'); if (c) c.textContent = t.value + ' / ' + RD.book.pages.length; }
  });
  el.querySelector('#mstage').addEventListener('scroll', () => { if (RD) RD.lastActive = Date.now(); }, { passive: true });
}
// A setting changed: keep it, and redraw what it touches, staying on the same page.
function change(k, v){
  const was = RD.p[k], keepPage = curPages()[0];
  if (typeof DEF[k] === 'number') v = +v; else if (typeof DEF[k] === 'boolean') v = v === true || v === 'true';
  if (was === v) return;
  setPref(k, v);
  if (['mode', 'layout', 'shift', 'split', 'scale', 'stretch', 'crop', 'stripw', 'gap'].includes(k)) { autoStop(); layout(keepPage); if (k === 'mode') { toast(label(MODES, v)); zonesHint(); } }
  else if (['bg', 'brightness', 'contrast', 'saturate', 'sepia', 'grayscale', 'invertc'].includes(k)) { applyLook(); bgFromPage(); }
  else if (k === 'pagenum' || k === 'progress') counter();
  else if (k === 'zones' || k === 'invert') { showZones(); }
  if (RD.bar) drawBars();
}
const cycle = (list, v) => list[(list.findIndex(x => x[0] === v) + 1) % list.length][0];
function quick(k){
  if (k === 'mode') change('mode', cycle(MODES, RD.p.mode));
  else if (k === 'layout') change('layout', cycle(LAYOUTS, RD.p.layout));
  else if (k === 'scale') change('scale', cycle(SCALES, RD.p.scale));
  else if (k === 'crop') { change('crop', !RD.p.crop); toast(RD.p.crop ? 'Borders cropped' : 'Borders kept'); }
  else if (k === 'auto') RD.auto ? autoStop() : autoStart();
  drawBars();
}
function fullscreen(){
  if (window.dafShell && dafShell.can && dafShell.can('fullscreen')) { dafShell.fullscreen(); return; }
  if (document.fullscreenElement) document.exitFullscreen().catch(() => {});
  else if (document.fullscreenEnabled) document.documentElement.requestFullscreen().catch(e => toast(e.message));
}

document.addEventListener('keydown', e => {
  if (!RD || e.metaKey || e.ctrlKey || e.altKey) return;
  if (e.target.closest('input:not([type=range]), textarea, select')) return;
  RD.lastActive = Date.now();
  const k = e.key;
  if (k === 'Escape') {
    e.preventDefault();
    if (RD.sheet) closeSheet();
    else if (!RD.el.querySelector('.mzones').hidden) RD.el.querySelector('.mzones').hidden = true;
    else if (RD.z.s > 1) zoomAt(innerWidth / 2, innerHeight / 2, 1);
    else if (RD.bar) toggleBar(false);
    else close();
    return;
  }
  if (e.target.matches('[type=range]') && (k === 'ArrowLeft' || k === 'ArrowRight')) return;
  // What each key does is in keys.js (Preferences → Keyboard); Shift Space goes back.
  const acts = { left: () => act('left'), right: () => act('right'), next: () => (k === ' ' && e.shiftKey ? prev() : next()), prev,
    first: () => paged(RD.p.mode) ? (RD.k = unitOfPage(0), slots(), turned()) : layout(0),
    last: () => paged(RD.p.mode) ? (RD.k = unitOfPage(RD.book.pages.length - 1), slots(), turned()) : layout(RD.book.pages.length - 1),
    prevvol: () => otherVolume(RD.book.prev), nextvol: () => otherVolume(RD.book.next), menu: () => toggleBar(), thumbs: () => { toggleBar(true); openSheet('thumbs'); },
    settings: () => { toggleBar(true); openSheet('settings'); }, mode: () => quick('mode'), layout: () => quick('layout'), scale: () => quick('scale'), crop: () => quick('crop'), auto: () => quick('auto'),
    fullscreen, help: () => { toggleBar(true); openSheet('keys'); } };
  if (!paged(RD.p.mode) && (k === 'ArrowDown' || k === 'ArrowUp')) return;     // the strip scrolls by itself
  const name = k === '?' ? 'help' : Object.keys(acts).find(a => a !== 'help' && C.Keys.is(e, 'manga', a));
  if (name) { e.preventDefault(); if (RD.sheet && !['menu', 'settings', 'thumbs', 'help'].includes(name)) closeSheet(); acts[name](); }
}, true);
// The apps' volume keys (dafShell sends this while the reader is open; a plain PageDown works too).
// The app takes them only while this says yes (shell.js tells it); otherwise they change the volume.
M.volumeKeys = () => !!RD && RD.p.volkeys !== 'off';
window.addEventListener('daf-volume', e => {
  if (!RD || RD.p.volkeys === 'off') return;
  const d = (e.detail && e.detail.dir) || 1;
  (RD.p.volkeys === 'inv' ? -d : d) > 0 ? next() : prev();
});
let resizeT = 0;
window.addEventListener('resize', () => { clearTimeout(resizeT); resizeT = setTimeout(() => { if (RD) layout(curPages()[0]); }, 200); });
document.addEventListener('visibilitychange', () => {
  if (!RD) return;
  if (document.hidden) { save(false); autoStop(); }
  else navigator.wakeLock && navigator.wakeLock.request('screen').then(w => { if (RD) RD.wake = w; }, () => {});
});
// Reading time: a beat every 15 seconds while a page is in front of you and you've been active lately (auto counts).
setInterval(() => {
  if (!RD || document.hidden || (Date.now() - RD.lastActive > 120000 && !RD.auto)) return;
  api('/api/manga/beat', { method: 'POST', body: JSON.stringify({ book: RD.book.id, seconds: 15, at: Math.floor(Date.now() / 1000) }) }).catch(() => {});
}, 15000);

C.views.mread = args => {
  const id = decodeURIComponent((args && args[0]) || ''), page = args && args[1] ? parseInt(args[1], 10) : null;
  if (!id) { location.hash = 'manga'; return; }
  if (RD && RD.book.id === id) return;
  if (!$('#main').innerHTML.trim()) $('#main').innerHTML = '<div class="top"><h1>Manga</h1></div>';
  M.open(id, page);
};
// Leaving the reader by the address (Back, a link): it closes, and saves where you were.
let lastView = null;
window.addEventListener('hashchange', () => {
  const v = (location.hash || '').slice(1).split('/')[0];
  if (v === 'mread' && lastView && lastView !== 'mread') M.cameIn = true;
  if (v !== 'mread' && RD) close(true);
  lastView = v;
});
lastView = (location.hash || '').slice(1).split('/')[0];
})();
