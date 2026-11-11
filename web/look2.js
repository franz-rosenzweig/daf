/* The new look (html[data-look="2"], look2.css): its frame and its navigation.

   One switch per device (Preferences → New look; daf.look in localStorage, or ?look=2 and ?look=1 on the
   address). With it on, app.js's renderSide and railMode hand over to side() and frame() here, and the
   sidebar's element holds the pieces of the frame instead: the brand, six tabs, the tab's own pages, and
   the corner (add, search, the minutes, the … menu).

   The navigation has three shapes, and a device never changes shape by itself, only when it's turned:
   - top:   anything with a mouse, and a tablet held upright. The tabs are a row above the page.
   - side:  a tablet held sideways. The tabs are a list down the left, the tab's pages under it.
   - phone: a phone. Five tabs along the bottom, and the … menu beside them.
   Reading something (an article, a book, a PDF, manga) hides the frame, as the sidebar always did. */
(() => {
const C = window.DafCore, { $, esc, S } = C;
const L = C.Look = {};
const root = document.documentElement;
L.on = root.dataset.look === '2';

L.shape = () => {
  const coarse = matchMedia('(pointer: coarse)').matches, w = innerWidth, h = innerHeight;
  if ((coarse && Math.min(w, h) < 600) || w <= 780) return 'phone';
  return coarse && w > h ? 'side' : 'top';
};
L.frame = () => {
  const s = L.shape();
  for (const k of ['top', 'side', 'phone']) root.classList.toggle('l2-' + k, k === s);
  root.classList.toggle('l2-hover', matchMedia('(hover: hover) and (pointer: fine)').matches);     // a pointer that hovers: names can be tooltips
};

// The tabs and each one's pages: [label, [[hash, label], …]]. A page that can be pinned shows only while
// it is (Preferences → Sidebar's list, settings nav_pins).
const OWNS = { today: ['today'], books: ['books', 'book', 'shelf'], catalog: ['catalog'], manga: ['manga', 'mread'], torah: ['torah'],
  library: ['library', 'view'], 'library/starred': [], edition: ['edition'], feed: ['feed', 'feeds'],
  highlights: ['highlights'], review: ['review'], paper: ['paper'], podcasts: ['podcasts'], recovery: ['recovery'] };
const isOn = key => {
  const r = S.route || [];
  if (r.join('/') === 'library/starred') return key === 'library/starred';
  return (OWNS[key] || []).includes(r[0]);
};
function tabs(){
  const d = S.data, pins = C.pinsOn(), pin = k => pins.includes(k);
  const ed = d && d.edition && (d.edition.on || d.edition.total);
  return [
    ['Today', [['today', 'Today'], pin('recovery') && ['recovery', 'Recovery']]],
    ['Books', [['books', 'Books'], ['catalog', 'All Books'], pin('manga') && ['manga', 'Manga'], pin('torah') && ['torah', 'Torah']]],
    ['Library', [['library', 'Library'], pin('shortlist') && ['library/starred', 'Shortlist']]],
    ['Feed', [ed && ['edition', 'Edition'], ['feed', 'Feed']]],
    ['Highlights', [['highlights', 'Highlights'], ['review', 'Review'], pin('paper') && ['paper', 'Paper pages']]],
    ['Listen', [pin('podcasts') && ['podcasts', 'Podcasts']]],
  ].map(([label, pages]) => [label, pages.filter(Boolean)]).filter(t => t[1].length);
}
// The Feed's pinned folders and feeds, from the old sidebar's own rows (reader.js navFeed).
function feedFolders(){
  if (!C.navFeed) return [];
  const box = document.createElement('div'); box.innerHTML = C.navFeed();
  return [...box.querySelectorAll('.nv.sub')].map(b => ({ go: b.dataset.go, name: (b.querySelector('span:not(.ct)') || b).textContent.trim(), on: b.classList.contains('on') }));
}

// Library's kinds (Articles, Videos, …) and saved views, from the old sidebar's own rows (reader.js
// navLibrary, which only lists them while its arrow is open: so it's opened for the asking, then put back).
function libraryKinds(){
  if (!C.navLibrary) return [];
  let was = null; try { was = localStorage.getItem('daf.libOpen'); localStorage.setItem('daf.libOpen', 'true'); } catch(e){}
  const box = document.createElement('div'); box.innerHTML = C.navLibrary();
  try { if (was == null) localStorage.removeItem('daf.libOpen'); else localStorage.setItem('daf.libOpen', was); } catch(e){}
  return [...box.querySelectorAll('.nv.sub')].map(b => ({ go: b.dataset.go, name: (b.querySelector('span:not(.ct)') || b).textContent.trim(), on: b.classList.contains('on') }));
}

const PLUS = '<svg width="18" height="18" viewBox="0 0 20 20" aria-hidden="true"><path d="M10 4v12M4 10h12" stroke="currentColor" stroke-width="1.9" stroke-linecap="round"/></svg>';
const DOTS = '<svg width="20" height="20" viewBox="0 0 20 20" aria-hidden="true" fill="currentColor"><circle cx="4.5" cy="10" r="1.7"/><circle cx="10" cy="10" r="1.7"/><circle cx="15.5" cy="10" r="1.7"/></svg>';
function ringSvg(frac){
  const c = 2 * Math.PI * 9;
  return '<svg width="26" height="26" viewBox="0 0 26 26" aria-hidden="true"><circle cx="13" cy="13" r="9" fill="none" stroke="var(--l2-track)" stroke-width="4"/>' +
    '<circle cx="13" cy="13" r="9" fill="none" stroke="var(--accent)" stroke-width="4" stroke-linecap="round" stroke-dasharray="' + (Math.min(1, frac) * c).toFixed(1) + ' ' + c.toFixed(1) + '" transform="rotate(-90 13 13)"/></svg>';
}

L.side = () => {
  const sd = $('#side'); if (!sd) return;
  const d = S.data, all = tabs(), cur = all.find(t => t[1].some(p => isOn(p[0])));
  const day = d && d.main && !(d.main.kind === 'minutes' && d.main.period === 'day');
  const done = d ? (day ? d.main.done : Math.floor(d.counted)) : 0, goal = d ? (day ? d.main.target : Math.round(d.goal || 60)) : 0;
  const sub = (p, cls) => '<button class="l2sub' + (cls || '') + (isOn(p[0]) ? ' on' : '') + '" data-go="' + p[0] + '">' + p[1] + '</button>';
  const folders = cur && cur[0] === 'Feed' ? feedFolders() : cur && cur[0] === 'Library' ? libraryKinds() : [];
  const fsub = f => '<button class="l2sub folder' + (f.on ? ' on' : '') + '" data-go="' + esc(f.go) + '">' + esc(f.name) + '</button>';
  const pages = cur && (cur[1].length > 1 || folders.length) ? cur[1] : [];
  const onFolder = folders.some(f => f.on);
  const tabRow = all.map(t => '<button class="l2tab' + (t === cur ? ' on' : '') + '" data-go="' + t[1][0][0] + '">' + t[0] + '</button>' +
    (t === cur ? pages.map(p => sub(p, ' nested')).join('') + folders.map(f => fsub(f).replace('l2sub folder', 'l2sub folder nested')).join('') : '')).join('');
  const date = new Date().toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric' });
  const phone = all.filter(t => t[0] !== 'Listen').slice(0, 5);
  sd.innerHTML =
    '<div class="l2brand"><button class="l2pill" data-go="today">Daf</button><span class="l2date">' + esc(date) + '</span></div>' +
    '<nav class="l2tabs" aria-label="Daf">' + tabRow + '</nav>' +
    '<div class="l2corner">' +
      '<button class="l2round" data-act="add" aria-label="Add to Daf" title="Add a link, a book or a PDF">' + PLUS + '</button>' +
      '<button class="l2search" data-act="palette">Search</button>' +
      '<button class="l2mins" data-go="stats" aria-label="Stats">' + ringSvg(goal ? done / goal : 0) + (d ? '<span>' + done + ' of ' + goal + '</span>' : '') + '</button>' +
      '<button class="l2round" data-act="l2menu" aria-label="More">' + DOTS + '</button>' +
    '</div>' +
    '<div class="l2subs">' + (cur && cur[0] === 'Library' ? sub(pages[0], onFolder ? ' off' : '') + folders.map(fsub).join('') + pages.slice(1).map(p => sub(p)).join('')
      : pages.map(p => sub(p, onFolder && p[0] === 'feed' ? ' off' : '')).join('') + folders.map(fsub).join('')) + '</div>' +
    '<div class="mobbar l2bar">' + phone.map(t => '<button class="mb' + (t === cur ? ' on' : '') + '" data-go="' + t[1][0][0] + '"><span>' + t[0] + '</span></button>').join('') +
      '<button class="mb l2more" data-act="l2menu" aria-label="More">' + DOTS + '</button></div>';
  if (onFolder) sd.querySelectorAll('.l2sub.off').forEach(b => b.classList.remove('on'));
  $('#app').classList.toggle('hassubs', pages.length + folders.length > 0);
  L.frame();
};

// ---------- a book's own colour ----------
// Two dark shades of the cover's strongest hue, worked out here from the picture and kept on this device
// (daf.tint.<id>). Anything with data-tint="<book id>" gets them as --t1 and --t2 (look2.css paints with them).
function hsv(h, s, v){
  const f = n => { const k = (n + h * 6) % 6; return Math.round(255 * (v - v * s * Math.max(0, Math.min(k, 4 - k, 1)))); };
  return '#' + [f(5), f(3), f(1)].map(x => x.toString(16).padStart(2, '0')).join('');
}
function tintOf(img){
  const cv = document.createElement('canvas'); cv.width = 24; cv.height = 36;
  const x = cv.getContext('2d'); x.drawImage(img, 0, 0, 24, 36);
  const px = x.getImageData(0, 0, 24, 36).data;
  let sw = 0, hx = 0, hy = 0;
  for (let i = 0; i < px.length; i += 4) {
    const r = px[i] / 255, g = px[i + 1] / 255, b = px[i + 2] / 255, mx = Math.max(r, g, b), mn = Math.min(r, g, b), dl = mx - mn;
    if (!dl) continue;
    let h = mx === r ? ((g - b) / dl) % 6 : mx === g ? (b - r) / dl + 2 : (r - g) / dl + 4; h = (h / 6 + 1) % 1;
    const s = dl / mx, w = s * s * (0.3 + mx);
    sw += w; hx += Math.cos(h * 2 * Math.PI) * w; hy += Math.sin(h * 2 * Math.PI) * w;
  }
  const hue = (Math.atan2(hy, hx) / (2 * Math.PI) + 1) % 1, sat = Math.min(0.62, Math.max(0.25, sw / (px.length / 4) * 2.2));
  return [hsv(hue, sat, 0.30), hsv(hue, sat, 0.47)];
}
L.tint = el => {
  const id = el.dataset.tint; if (!id || el.dataset.tinted === id) return;
  el.dataset.tinted = id;
  const put = t => { el.style.setProperty('--t1', t[0]); el.style.setProperty('--t2', t[1]); };
  const kept = C.lsGet('tint.' + id, null);
  if (Array.isArray(kept)) { put(kept); return; }
  const im = new Image();
  im.onload = () => { try { const t = tintOf(im); C.lsSet('tint.' + id, t); if (el.dataset.tint === id) put(t); } catch(e){} };
  im.src = '/api/cover/' + encodeURIComponent(id);
};
// A colour from a picture that's already on the page, where there's no book to ask by: the player's art, a
// manga series, a book's card on Highlights. A picture from another site only lends its colour if that site
// allows it; otherwise the element keeps Daf's blue.
const tintMemo = new Map();
L.tintFrom = (el, src) => {
  if (!src || el.dataset.tintsrc === src) return;
  el.dataset.tintsrc = src; el.classList.remove('l2tinted'); el.style.removeProperty('--t1'); el.style.removeProperty('--t2');
  const put = t => { if (el.dataset.tintsrc !== src) return; el.style.setProperty('--t1', t[0]); el.style.setProperty('--t2', t[1]); el.classList.add('l2tinted'); };
  if (tintMemo.has(src)) { const t = tintMemo.get(src); if (t) put(t); return; }
  const im = new Image();
  if (/^https?:/.test(src) && !src.startsWith(location.origin)) im.crossOrigin = 'anonymous';
  im.onload = () => { try { const t = tintOf(im); tintMemo.set(src, t); put(t); } catch(e){ tintMemo.set(src, null); } };
  im.onerror = () => tintMemo.set(src, null);
  im.src = src;
};
// Today's panel: the lines where you left off, under the title (/api/books/<id>/excerpt; kept while Daf is open).
const exMemo = new Map();
function excerpt(){
  const h = document.querySelector('#main .l2hero[data-book]:not(.small)'); if (!h) return;
  const id = h.dataset.book, sub = h.querySelector('.l2hsub');
  if (!sub || h.querySelector('.l2hex')) return;
  // (Today draws itself again as its data comes in: put the lines into the panel that's there now)
  const put = t => { const x = document.querySelector('#main .l2hero[data-book="' + CSS.escape(id) + '"]:not(.small)'), sb = x && x.querySelector('.l2hsub');
    if (!t || !sb || x.querySelector('.l2hex')) return; sb.insertAdjacentHTML('afterend', '<p class="l2hex" dir="auto">' + esc(t) + '</p>'); };
  if (exMemo.has(id)) { put(exMemo.get(id)); return; }
  exMemo.set(id, '');
  C.api('/api/books/' + encodeURIComponent(id) + '/excerpt').then(r => { exMemo.set(id, r.text || ''); put(r.text); }).catch(() => exMemo.delete(id));
}
function scan(){
  document.querySelectorAll('#main [data-tint]').forEach(L.tint);
  document.querySelectorAll('#main .hlgroup, #main .mcont').forEach(el => { const im = el.querySelector('img'); if (im) L.tintFrom(el, im.getAttribute('src')); });
  const pl = document.getElementById('player'), art = pl && pl.querySelector('img.plart');
  if (pl && art) L.tintFrom(pl, art.getAttribute('src'));
  dupTitle(); prefsSearch(); everywhere(); hlFilter(); excerpt();
}
// Preferences: a box that finds a setting by its name. Cards that don't have the words step away, and in a
// card that does, so do the rows without them (unless it's the card's own name that matched).
function prefsSearch(){
  const page = document.querySelector('#main .prefspage'), top = document.querySelector('#main > .top');
  if (!page || !top || top.querySelector('.l2psearch')) return;
  top.insertAdjacentHTML('beforeend', '<span class="spacer"></span><input class="field l2psearch" type="search" placeholder="Search" aria-label="Search Preferences" autocomplete="off">');
  const box = top.querySelector('.l2psearch'), low = x => (x || '').toLowerCase();
  box.addEventListener('input', () => {
    const q = low(box.value).trim(), grid = page.closest('.prefsgrid') || page;
    grid.classList.toggle('l2finding', !!q);
    page.querySelectorAll(':scope > .card').forEach(card => {
      const h2 = card.querySelector('h2'), inName = !q || low(h2 && h2.textContent).includes(q), rows = [...card.querySelectorAll('.prow, .aaline')];
      const hits = rows.filter(r => low(r.textContent).includes(q));
      card.hidden = !!q && !inName && !hits.length;
      rows.forEach(r => { r.hidden = !!q && !inName && hits.length > 0 && !hits.includes(r); });
    });
    page.querySelectorAll(':scope > .pgroup').forEach(g => { let n = g.nextElementSibling, any = false; while (n && !n.classList.contains('pgroup')) { if (n.classList.contains('card') && !n.hidden) any = true; n = n.nextElementSibling; } g.hidden = !any; });
  });
}
// A screen's own name, when the row of pages just above already says it ("Highlights" under Highlights ·
// Review): the name steps back, and so does its bar if nothing else is in it.
function dupTitle(){
  const sub = document.querySelector('.l2subs .l2sub.on'), h = document.querySelector('#main .top h1');
  if (!h) return;
  const same = !!sub && L.shape() !== 'side' && !h.querySelector('select,a,svg:not(.srcpick svg),button:not(.srcpick)') && h.textContent.trim().toLowerCase() === sub.textContent.trim().toLowerCase();
  h.classList.toggle('l2same', same);
  // (a child's own computed display, not whether it shows: the bar itself may be the hidden one)
  const top = h.closest('.top'); if (top) top.classList.toggle('l2bare', same && ![...top.children].some(c => c !== h && !c.classList.contains('spacer') && getComputedStyle(c).display !== 'none'));
}
if (L.on) {
  let t = 0; const later = () => { clearTimeout(t); t = setTimeout(scan, 30); };
  new MutationObserver(later).observe(document.getElementById('main'), { childList: true, subtree: true });
  new MutationObserver(later).observe(document.getElementById('player'), { childList: true, subtree: true, attributes: true, attributeFilter: ['src', 'hidden'] });
  new MutationObserver(later).observe(document.getElementById('side'), { childList: true });
}

// ---------- Today ----------
// The book being read: the one opened last, from the nightstand or beside it.
const readHref = b => (/in Daf$/.test(b.progress_note || '') ? '#ebook/' : '#book/') + encodeURIComponent(b.id);
function bigRing(done, goal, size){
  const r = 52, c = 2 * Math.PI * r, f = goal ? Math.min(1, done / goal) : 0;
  return '<span class="l2ring" style="width:' + size + 'px;height:' + size + 'px"><svg role="img" aria-label="' + done + ' of ' + goal + '" width="' + size + '" height="' + size + '" viewBox="0 0 124 124">' +
    '<circle cx="62" cy="62" r="52" fill="none" stroke="rgba(255,255,255,.2)" stroke-width="10"/><circle cx="62" cy="62" r="52" fill="none" stroke="#fff" stroke-width="10" stroke-linecap="round" stroke-dasharray="' + (f * c).toFixed(1) + ' ' + c.toFixed(1) + '" transform="rotate(-90 62 62)"/></svg>' +
    '<span class="l2ringn"><b>' + done + '</b><i>of ' + goal + '</i></span></span>';
}
L.hero = (d, isToday, dayN) => {
  const books = (d.nightstand || []).concat(d.offstand ? [d.offstand] : []).sort((a, b) => (+b.last_read || 0) - (+a.last_read || 0));
  const b = books[0];
  const day = d.main && !(d.main.kind === 'minutes' && d.main.period === 'day');
  const done = day ? d.main.done : Math.floor(d.counted), goal = day ? d.main.target : Math.round(d.goal || 60);
  const left = Math.max(0, goal - done), unit = day ? (d.main.unit || '') : '';
  const streak = d.streak && (d.streak.goal > 1 ? d.streak.goal + ' in a row' : d.streak.any > 1 ? d.streak.any + ' days reading' : '');
  const ringCol = '<div class="l2hring">' + bigRing(done, goal, 150) + '<b>' + (left ? left + ' to go' : 'Done for today') + '</b>' +
    '<span>' + [unit, dayN && isToday ? 'Day ' + dayN : '', streak].filter(Boolean).join(' · ') + '</span></div>';
  if (!b) return '<section class="l2hero plain"><div class="l2htext"><span class="l2lab">Today</span><h1>' + esc(new Date().toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric' })) + '</h1>' +
    '<div class="l2hacts"><a class="btn primary" href="#books">Choose a book</a></div></div>' + ringCol + '</section>';
  return '<section class="l2hero" data-book="' + esc(b.id) + '"' + (b.has_cover ? ' data-tint="' + esc(b.id) + '"' : '') + '>' +
    '<a class="l2hcover" href="#book/' + encodeURIComponent(b.id) + '" aria-label="' + esc(C.shortTitle(b.title)) + '">' + C.cover(b, 'cv l2cv') + '</a>' +
    '<div class="l2htext"><span class="l2lab">Continue</span><h1>' + esc(C.shortTitle(b.title)) + '</h1>' +
    '<span class="l2hsub">' + esc([b.author, b.progress != null ? Math.round(b.progress) + '%' : '', b.progress_note].filter(Boolean).join(' · ')) + '</span>' +
    '<div class="l2hacts"><a class="btn primary" href="' + readHref(b) + '">Continue reading</a><a class="btn" href="#book/' + encodeURIComponent(b.id) + '">Book</a></div></div>' +
    ringCol + '</section>';
};
L.todayCards = (d, sessHTML, srcRows, rv) => {
  const hero = (d.nightstand || []).concat(d.offstand ? [d.offstand] : []).sort((a, b) => (+b.last_read || 0) - (+a.last_read || 0))[0];
  const row = (go, title, sub) => '<a class="l2nx" href="#' + go + '"><span><b>' + title + '</b><i>' + esc(sub) + '</i></span><span class="l2chev">›</span></a>';
  const ed = d.edition && (d.edition.on || d.edition.total) ? d.edition : null;
  const left = rv && rv.total ? rv.total - rv.done : 0, cards = d.cards_due || 0;
  const next = (ed ? row('edition', 'The Edition', ed.total ? (ed.total - ed.done > 0 ? (ed.total - ed.done) + ' of ' + ed.total + ' left' : 'Read') : 'Not out yet') : '') +
    (rv && rv.total ? row('review', 'Daily Review', left > 0 || cards ? [left > 0 ? left + ' highlight' + (left === 1 ? '' : 's') : '', cards ? cards + ' flashcard' + (cards === 1 ? '' : 's') : ''].filter(Boolean).join(' · ') : 'Done for today') : '') +
    (C.pinsOn().includes('torah') ? row('torah', 'Torah', 'This week’s parasha') : '');
  const stand = (d.nightstand.length ? d.nightstand : d.nightstand_suggested || []).filter(b => !hero || b.id !== hero.id);
  return '<div class="l2cols">' +
    (next ? '<section class="card"><h2>Next</h2><div class="l2nxs">' + next + '</div></section>' : '') +
    (stand.length ? '<section class="card"><div class="cardh"><h2>' + (d.nightstand.length ? 'Also on the nightstand' : 'Suggested') + '</h2><a class="tiny" href="#books">Change</a></div><div class="brows">' + stand.map(b => C.bookRow(b)).join('') + '</div></section>' : '') +
    '<section class="card"><div class="cardh"><h2>Today so far</h2><span class="l2acts"><button class="linkbtn tiny" data-act="refresh">Sync</button><button class="linkbtn tiny" data-act="paper">Log paper</button></span></div>' +
      '<div class="sess">' + sessHTML + '</div><div class="rows l2src">' + srcRows + '</div></section></div>';
};
// Books: the first book on the nightstand, as a panel in its own colour.
L.readingNow = b => '<section class="l2hero small"' + (b.has_cover ? ' data-tint="' + esc(b.id) + '"' : '') + '>' +
  '<a class="l2hcover" href="#book/' + encodeURIComponent(b.id) + '">' + C.cover(b, 'cv l2cv') + '</a>' +
  '<div class="l2htext"><span class="l2lab">Reading now</span><h1>' + esc(C.shortTitle(b.title)) + '</h1>' +
  '<span class="l2hsub">' + esc([b.author, b.progress != null ? Math.round(b.progress) + '%' : '', b.progress_note].filter(Boolean).join(' · ')) + '</span>' +
  '<div class="l2hacts">' + (b.readable ? '<a class="btn primary" href="#ebook/' + encodeURIComponent(b.id) + '">Continue reading</a>' : '') + '<a class="btn" href="#book/' + encodeURIComponent(b.id) + '">Book</a></div></div></section>';

// ---------- the reader's … menu, tidied ----------
// book.js and reader.js build their menus as before (the same buttons, so every click and every key still
// lands where it did, and the apps' menus that press them too). With the new look on, the menu is then
// rearranged here: a row of tiles with a picture each for the things done most, one short row of "go to"
// chips, a few short lines, and the rare ones small at the foot. What already has a button in the bar
// above isn't repeated. Anything this doesn't know stays as it was, at the end.
const MI = (d, extra) => '<svg width="20" height="20" viewBox="0 0 20 20" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">' + d.split('|').map(p => '<path d="' + p + '"/>').join('') + (extra || '') + '</svg>';
const MICON = {
  speaker: MI('M4 8v4h3l4 3V5L7 8H4z|M14 7.5a3.5 3.5 0 0 1 0 5'),
  headphones: MI('M4 12v-2a6 6 0 0 1 12 0v2|M4 12h2.5v4H5a1 1 0 0 1-1-1v-3z|M16 12h-2.5v4H15a1 1 0 0 0 1-1v-3z'),
  note: MI('M4 16h3l8.5-8.5-3-3L4 13v3z|M11.5 5.5l3 3'),
  ask: MI('M4 5h12v8H9l-3.5 3v-3H4V5z'),
  focus: MI('M4 8V4h4|M12 4h4v4|M16 12v4h-4|M8 16H4v-4'),
  star: MI('m10 3.3 2 4.3 4.6.6-3.4 3.2.9 4.6L10 13.7 5.9 16l.9-4.6-3.4-3.2 4.6-.6z'),
  info: MI('M10 9.2v4.6|M10 6.3v.1', '<circle cx="10" cy="10" r="7"/>'),
  book: MI('M10 6.5C8.5 5 6.5 4.5 4 4.5v10c2.5 0 4.5.5 6 2 1.5-1.5 3.5-2 6-2v-10c-2.5 0-4.5.5-6 2z|M10 6.5v10'),
  bookmark: MI('M6 4h8v12l-4-3-4 3V4z'),
  export: MI('M10 13V4|M6.5 7.5 10 4l3.5 3.5|M4 12v4h12v-4'),
  download: MI('M10 4v9|M6.5 9.5 10 13l3.5-3.5|M4 16h12'),
  kindle: MI('M8.5 14h3', '<rect x="5" y="3" width="10" height="14" rx="1.5"/>'),
  link: MI('M8.5 11.5l3-3|M9 6.5l1.5-1.5a2.8 2.8 0 0 1 4 4L13 10.5|M11 13.5 9.5 15a2.8 2.8 0 0 1-4-4L7 9.5'),
  external: MI('M8 5H5v10h10v-3|M11 4h5v5|M16 4l-7 7'),
  clock: MI('M10 6v4l2.5 2', '<circle cx="10" cy="10" r="7"/>'),
  archive: MI('M4 5h12v3H4z|M5 8v7h10V8|M8.5 11h3'),
  eye: MI('M2.5 10s3-5 7.5-5 7.5 5 7.5 5-3 5-7.5 5-7.5-5-7.5-5z', '<circle cx="10" cy="10" r="2"/>'),
  save: MI('M6 4h8v12l-4-3-4 3V4z|M10 6.5v4|M8 8.5h4'),
  refresh: MI('M15 10a5 5 0 1 1-1.5-3.6|M15 4.5v3h-3'),
  file: MI('M6 3.5h5l3 3v10H6z|M11 3.5v3h3'),
  pairs: MI('M5 7h10l-2.5-2.5|M15 13H5l2.5 2.5'),
  target: MI('', '<circle cx="10" cy="10" r="7"/><circle cx="10" cy="10" r="3.5"/>'),
  list: MI('M7 6h9|M7 10h9|M7 14h9|M4 6h.01|M4 10h.01|M4 14h.01'),
  plus: MI('M10 4.5v11|M4.5 10h11'),
  shelf: MI('M3.5 16h13|M5 16V5h3v11|M9.5 16V7h3v9|M13.5 16l1.6-8.6 2.4.5-1.6 8.1'),
  edit: MI('M4 16h3l8.5-8.5-3-3L4 13v3z'),
  columns: MI('M4 4h12v12H4z|M8 4v12|M12 4v12'),
  views: MI('M4 5h12|M4 10h8|M4 15h5'),
  grid: MI('M4 4h5v5H4z|M11 4h5v5h-5z|M4 11h5v5H4z|M11 11h5v5h-5z'),
  taste: MI('M10 16.5s-6-3.6-6-8A3.5 3.5 0 0 1 10 6a3.5 3.5 0 0 1 6 2.5c0 4.4-6 8-6 8z'),
  select: MI('M4.5 10.5l3.5 3.5 7.5-8'),
};
const MSEL = k => { const [t, v] = k.split(':'); return t === 'a' ? (v === 'export' ? 'a[href*="/highlights/export"]' : 'a[href$="/file"]') : '[data-' + t + '="' + v + '"]'; };
// [button, short label, icon, the words that mean it's on now, the bar's own button for the same thing]
const MENUS = {
  bm: {
    tiles: [['bm:listen', 'Listen', 'speaker', /^Stop/], ['abk:herebook', 'Audiobook', 'headphones'], ['bm:notebook', 'Notebook', 'note'], ['bm:ask', 'Ask', 'ask'], ['bm:focus', 'Focus', 'focus', /^Leave/]],
    chips: ['Go to', [['bm:start', 'Start'], ['bm:goto', 'Page…'], ['bm:kindle', 'Kindle']]],
    rows: [[['bm:info', 'About', 'info'], ['bm:book', 'Book page', 'book'], ['bm:mark', 'Bookmark', 'bookmark', /^Remove/, '[data-bk="bookmark"]'], ['bm:pairs', 'Swap the page pairs', 'pairs']],
      [['a:export', 'Export highlights', 'export'], ['a:file', 'Download', 'download'], ['bm:offline', null, 'download']]],
    foot: [['bm:auto', 'Auto highlight'], ['bm:keys', 'Shortcuts'], ['bm:reset', 'Forget my place']],
  },
  more: {
    tiles: [['more:listen', 'Listen', 'speaker', /^Stop/], ['more:ask', 'Ask', 'ask'], ['more:note', 'Note', 'note'], ['more:star', 'Shortlist', 'star', /^Off/], ['more:focus', 'Focus', 'focus', /^Leave/]],
    chips: ['List', [['more:prevdoc', '‹ Previous'], ['more:nextdoc', 'Next ›']]],
    rows: [[['more:save', 'Save to Library', 'save', null, '#rtop [data-dact="save"]'], ['more:seen', 'Seen', 'eye', /^Back/, '#rtop [data-dact="seen"]'], ['more:later', 'Later', 'clock', /^Back/], ['more:archive', 'Archive', 'archive', /^Back/, '#rtop [data-dact="archive"]'],
        ['more:panel', 'Notebook', 'note', /^Hide/, '#rtop [data-ract="panel"]'], ['more:pages', 'PDF pages', 'file']],
      [['more:kindle', 'Send to Kindle', 'kindle'], ['more:full', 'Load the full article', 'refresh'], ['more:device', null, 'download']],
      [['more:open', 'Open original', 'external'], ['more:copy', 'Copy link', 'link'], ['more:vault', 'Open in Obsidian', 'external']]],
    foot: [['more:meta', 'Edit title'], ['more:reset', 'Reset progress'], ['more:keys', 'Shortcuts'], ['more:delete', 'Delete']],
  },
};
const shown = el => !!(el && el.offsetParent);
// A list's … (reader.js openListMore) with the corner's: Mark seen as one row of chips, Select and Save view
// from the bar, the order (it's in Filter now) left out.
function tidyList(menu){
  const lm = k => menu.querySelector('[data-lm="' + k + '"]');
  [...menu.querySelectorAll('[data-lm^="sort:"]')].forEach(b => b.remove());
  [...menu.querySelectorAll('.mh')].forEach(h => { if (/Order/.test(h.textContent)) h.remove(); });
  const seen = [...menu.querySelectorAll('[data-lm^="seen:"]')];
  const parts = [];
  if (seen.length) {
    const chips = document.createElement('div'); chips.className = 'l2m-chips';
    chips.innerHTML = '<span class="l2m-h">Mark seen</span>';
    const short = { '': 'All', '86400': 'A day', '259200': '3 days', '604800': 'A week' };
    seen.forEach(b => { const k = b.dataset.lm.slice(5); b.title = b.textContent.trim(); b.innerHTML = '<span class="l2ml">' + (short[k] || b.textContent) + '</span>'; chips.appendChild(b); });
    parts.push(chips);
  }
  const rows = document.createElement('div'); rows.className = 'l2m-rows';
  const row = (b, label, icon) => { if (!b) return; b.innerHTML = (MICON[icon] || '<span class="l2mi0"></span>') + '<span class="l2ml">' + label + '</span>'; rows.appendChild(b); };
  const bar = k => document.querySelector('#main .lvmain > .top [data-ract="' + k + '"]');
  const proxy = (k, label, icon) => { if (!bar(k)) return; const b = document.createElement('button'); b.dataset.lm = k === 'selmode' ? 'select' : k; row(b, label, icon); };
  if (lm('select')) row(lm('select'), /Stop/.test(lm('select').textContent) ? 'Stop selecting' : 'Select', 'select'); else proxy('selmode', bar('selmode') && bar('selmode').classList.contains('on') ? 'Stop selecting' : 'Select', 'select');
  const view = lm('saveview') || lm('rmview');
  if (view) row(view, view.dataset.lm === 'rmview' ? 'Remove this view' : 'Save as a view', 'views');
  else if (bar('rmview')) proxy('rmview', 'Remove this view', 'views'); else proxy('saveview', 'Save as a view', 'views');
  row(lm('refresh'), /Check/.test((lm('refresh') || {}).textContent || '') ? 'Check for new posts' : 'Sync now', 'refresh');
  row(lm('editfeed'), 'Rename or move this feed', 'edit');
  if (S.route[0] === 'feed') {
    const f1 = document.createElement('button'); f1.dataset.act = 'add'; row(f1, 'Follow a site', 'plus');
    const f2 = document.createElement('button'); f2.dataset.go = 'feeds'; row(f2, 'What shows where', 'list');
  }
  [...menu.children].forEach(c => { if (!c.closest('.l2m-rows,.l2m-chips') && c.tagName === 'BUTTON') rows.appendChild(c); });
  if (rows.children.length) parts.push(rows);
  menu.textContent = ''; parts.forEach(p => menu.appendChild(p));
  menu.classList.add('l2m');
}
function tidyCat(menu){
  [...menu.querySelectorAll('button,a')].forEach(b => { const i = b.querySelector('i'); if (i && !i.textContent.trim()) i.remove(); });
  menu.classList.add('l2m', 'l2cat');
}
function tidyMenu(menu){
  if (menu.classList.contains('l2m')) return;
  if (menu.querySelector('[data-lm]')) { tidyList(menu); mergeOwn(menu); fit(menu); return; }
  if (menu.querySelector('[data-catm]')) { tidyCat(menu); mergeOwn(menu); fit(menu); return; }
  const spec = menu.querySelector('[data-bm]') ? MENUS.bm : menu.querySelector('[data-more]') ? MENUS.more : null;
  if (!spec) return;
  menu.classList.add('l2m');
  const used = new Set();
  const take = ([key, label, icon, onRe, bar], withIcon, tile) => {
    const b = menu.querySelector(MSEL(key)); if (!b || used.has(b)) return null;
    used.add(b);
    if (bar && shown(document.querySelector(bar))) { b.remove(); return null; }       // the bar above has it
    const ck = b.querySelector('.ck'), c = b.cloneNode(true); c.querySelectorAll('kbd,.kbd').forEach(x => x.remove());
    const was = c.textContent.trim(), on = ck ? !!ck.textContent.trim() : !!(onRe && onRe.test(was));
    b.classList.toggle('on', on); if (on) b.setAttribute('aria-pressed', 'true');
    if (tile) { b.dataset.tip = label || was; b.setAttribute('aria-label', label || was); b.removeAttribute('title'); } else b.title = was;
    b.innerHTML = (withIcon && icon ? MICON[icon] : '') + '<span class="l2ml">' + esc(label || was) + '</span>';
    return b;
  };
  const box = cls => { const d = document.createElement('div'); d.className = cls; return d; };
  const parts = [];
  const tiles = box('l2m-tiles'); spec.tiles.forEach(x => { const b = take(x, true, true); if (b) tiles.appendChild(b); }); if (tiles.children.length) parts.push(tiles);
  const chips = box('l2m-chips'); spec.chips[1].forEach(x => { const b = take(x, false); if (b) chips.appendChild(b); });
  if (chips.children.length) { chips.insertAdjacentHTML('afterbegin', '<span class="l2m-h">' + spec.chips[0] + '</span>'); parts.push(chips); }
  spec.rows.forEach(g => { const rows = box('l2m-rows'); g.forEach(x => { const b = take(x, true); if (b) rows.appendChild(b); }); if (rows.children.length) parts.push(rows); });
  const foot = box('l2m-foot'); spec.foot.forEach(x => { const b = take(x, false); if (b) foot.appendChild(b); });
  const rest = box('l2m-rows'); [...menu.children].forEach(el => { if (!used.has(el) && el.tagName !== 'HR') rest.appendChild(el); }); if (rest.children.length) parts.push(rest);
  if (foot.children.length) parts.push(foot);
  menu.textContent = ''; parts.forEach(p => menu.appendChild(p));
  fit(menu);
}
// it was placed for its old size: keep it on the screen
function fit(menu){
  const p = menu.closest('.pop'); if (!p || p.hidden || !p.style.top) return;
  const r = p.getBoundingClientRect(); if (r.bottom > innerHeight - 8) p.style.top = Math.max(8, innerHeight - 8 - r.height) + 'px'; if (r.right > innerWidth - 8) p.style.left = Math.max(8, innerWidth - 8 - r.width) + 'px';
}
if (L.on) new MutationObserver(() => { const m = document.querySelector('#pop .menu:not(.l2m)'); if (m) tidyMenu(m); const fp = document.querySelector('#pop .fpop'); if (fp) filterExtras(fp); }).observe(document.getElementById('pop'), { childList: true });

// ---------- the corner's … menu: this screen's own things, then the places that have no tab ----------
// A screen keeps on its page the one thing done most there and what changes what its list shows; the rest
// of its bar moves here. The buttons that moved stay in the page,
// hidden (look2.css), and a line here presses the real one, so each still does exactly what it did; a
// menu the button opens appears by the corner, where it was asked for.
let anchorAt = null;
function press(sel, anchor){
  const b = document.querySelector(sel); if (!b) return false;
  $('#pop').hidden = true;
  const r = anchor ? anchor.getBoundingClientRect() : null;
  setTimeout(() => {
    if (r) { b.getBoundingClientRect = () => r; clearTimeout(anchorAt); anchorAt = setTimeout(() => { delete b.getBoundingClientRect; }, 4000); }
    b.click();
  }, 0);
  return true;
}
const goCard = (hash, card) => {
  location.hash = hash;
  if (!card) return;
  let n = 0; const t = setInterval(() => { const c = document.getElementById(card); if (c || ++n > 40) { clearInterval(t); if (c) c.scrollIntoView({ block: 'start' }); } }, 100);
};
// [label, icon, what it does: {press: selector} | {go: hash, card} | {act: data-act} | {href}]
function screenItems(){
  const r = S.route || [], v = r[0], q = sel => document.querySelector('#main ' + sel);
  const it = [];
  const add = (label, icon, how) => it.push([label, icon, how]);
  const pr = (label, icon, sel) => { if (q(sel)) add(label, icon, { press: '#main ' + sel }); };
  if (v === 'today' || !v) { add('Log paper', 'note', { act: 'paper' }); add('Sync now', 'refresh', { act: 'refresh' }); add('Goals', 'target', { go: '#prefs/goals' }); }
  else if (v === 'books') { pr('Add a book', 'plus', '[data-act="addbook"]'); pr('New shelf', 'shelf', '#shelfsec [data-shelf="new"]'); }
  else if (v === 'book') {
    pr('Listen from here', 'headphones', '[data-abk="here"]'); pr('Edit details', 'edit', '[data-act="bookedit"]');
    const o = q('.bookhead a[target="_blank"]'); if (o) add('Open the original', 'external', { href: o.href, blank: true });
    const vl = q('.l2vault code'); if (vl) add('Open the note in Obsidian', 'external', { href: 'obsidian://open?vault=' + encodeURIComponent(q('.l2vault').dataset.vname || '') + '&file=' + encodeURIComponent(vl.textContent.trim()) });
  }
  else if (v === 'catalog') { pr('Columns', 'columns', '[data-act="cat:cols"]'); pr('Views', 'views', '[data-act="cat:views"]'); }
  else if (v === 'library' && !r[1]) pr('Arrange Home', 'grid', '[data-home="config"]');
  else if (v === 'edition') { pr('Taste', 'taste', '.top a[href="#edition/taste"]'); pr('Send to the Kindle', 'kindle', '[data-ed="kindle"]'); pr('Make it again', 'refresh', '[data-ed="again"]'); }
  else if (v === 'highlights') pr('Export', 'export', '[data-act="hlexport"]');
  else if (v === 'review') { add('Review more', 'refresh', { go: '#review/more' }); add('Highlights per day', 'target', { go: '#prefs', card: 'reviewcard' }); }
  else if (v === 'stats') { add('Goals', 'target', { go: '#prefs/goals' }); add('Log paper', 'note', { act: 'paper' }); }
  else if (v === 'manga') add('AniList', 'external', { go: '#prefs/anilist' });
  else if (v === 'podcasts') add('Follow a show', 'plus', { search: true });      // its search finds shows in the directory too
  return it;
}
// The places with no tab, small at the foot (on a phone, Search and Add as well, and Listen's pages).
function footRows(){
  const phone = L.shape() === 'phone', listen = (tabs().find(t => t[0] === 'Listen') || [0, []])[1];
  const f = (label, how) => '<button ' + how + '>' + label + '</button>';
  return (phone ? f('Search', 'data-l2search') + f('Add to Daf', 'data-act="add"') + listen.map(x => f(x[1], 'data-go="' + x[0] + '"')).join('') : '') +
    [['stats', 'Stats'], ['sources', 'Sources'], ['prefs', 'Preferences']].filter(x => x[0] !== (S.route || [])[0]).map(x => f(x[1], 'data-go="' + x[0] + '"')).join('') + (C.Tips ? f('What’s new', 'data-go="tips"') : '');
}
function rowHTML([label, icon, how], i){
  const ic = MICON[icon] || '<span class="l2mi0"></span>';
  if (how.href) return '<a href="' + esc(how.href) + '"' + (how.blank ? ' target="_blank" rel="noopener"' : '') + '>' + ic + '<span class="l2ml">' + esc(label) + '</span></a>';
  const attr = how.act ? 'data-act="' + how.act + '"' : 'data-l2do="' + i + '"';
  return '<button ' + attr + '>' + ic + '<span class="l2ml">' + esc(label) + '</span></button>';
}
let items = [];
function place(anchor){
  const p = $('#pop'), r = anchor.getBoundingClientRect(), w = p.offsetWidth, h = p.offsetHeight;
  p.style.right = 'auto'; p.style.bottom = 'auto';
  p.style.left = Math.max(8, Math.min(r.right - w, innerWidth - w - 8)) + 'px';
  p.style.top = (r.bottom + 8 + h > innerHeight ? Math.max(8, r.top - h - 8) : r.bottom + 8) + 'px';
}
// Screens with a menu of their own (a list's, All Books') open that one by the corner, and it gets this
// screen's other things and the foot added (tidyMenu).
function menu(anchor){
  const own = document.querySelector('#main [data-ract="lmore"]') || document.querySelector('#main [data-act="cat:more"]');
  items = screenItems();
  if (own) { L.extra = { items, anchor }; press('#main ' + (own.dataset.ract ? '[data-ract="lmore"]' : '[data-act="cat:more"]'), anchor); return; }
  const p = $('#pop');
  p.onclick = p.oninput = p.onkeydown = p.onchange = null;
  p.innerHTML = '<div class="menu l2menu l2m">' + (items.length ? '<div class="l2m-rows">' + items.map(rowHTML).join('') + '</div>' : '') + '<div class="l2m-foot">' + footRows() + '</div></div>';
  p.hidden = false; place(anchor);
}
L.extraRows = () => { const x = L.extra; L.extra = null; return x; };
function doItem(how, anchor){
  if (how.press) press(how.press, anchor);
  else if (how.go) { $('#pop').hidden = true; goCard(how.go, how.card); }
  else if (how.search) { $('#pop').hidden = true; setTimeout(L.search, 0); }
}
document.addEventListener('click', e => {
  if (!L.on || !e.target.closest) return;
  const m = e.target.closest('[data-act="l2menu"]');
  if (m) { e.stopPropagation(); if ($('#pop').hidden || !$('#pop .l2m')) menu(m); else $('#pop').hidden = true; return; }
  const d = e.target.closest('#pop [data-l2do]');
  if (d) { e.stopPropagation(); const how = (items[+d.dataset.l2do] || [])[2]; if (how) doItem(how, [...document.querySelectorAll('[data-act="l2menu"]')].find(x => x.offsetParent)); return; }
  const sr = e.target.closest('[data-l2search]');
  if (sr) { e.stopPropagation(); $('#pop').hidden = true; L.search(); return; }
  if (e.target.closest('#pop .l2menu button, #pop .l2menu a')) setTimeout(() => { $('#pop').hidden = true; }, 0);
}, true);

// ---------- one search: the corner's looks on this screen first, and everywhere after ----------
// A screen with its own search (Books, a list, Highlights, …) opens that one in its bar, with Everywhere
// beside it for the rest of Daf; All Books and Preferences have their box already; anywhere else it's
// the search over everything (the palette, also ⌘K).
function palette(words){
  const b = document.createElement('button'); b.dataset.act = 'palette'; b.hidden = true; document.body.appendChild(b); b.click(); b.remove();
  if (words) setTimeout(() => { const i = $('#palq'); if (i) { i.value = words; i.dispatchEvent(new Event('input', { bubbles: true })); } }, 0);
}
L.search = () => {
  const go = document.querySelector('#main .find:not(.open) [data-findgo]');
  if (go) { go.click(); return; }
  const open = document.querySelector('#main .find.open .findq'); if (open) { open.focus(); return; }
  const box = document.querySelector('#main #catq, #main .l2psearch'); if (box) { box.focus(); box.select && box.select(); return; }
  palette('');
};
document.addEventListener('click', e => {
  if (!L.on || !e.target.closest) return;
  if (e.target.closest('.l2search')) { e.preventDefault(); e.stopPropagation(); L.search(); return; }
  const ev = e.target.closest('.l2every');
  if (ev) { e.stopPropagation(); const i = ev.closest('.find') && ev.closest('.find').querySelector('.findq'); palette(i ? i.value.trim() : ''); }
}, true);
function everywhere(){
  const f = document.querySelector('#main .find.open'); if (!f || f.querySelector('.l2every')) return;
  f.insertAdjacentHTML('beforeend', '<button class="btn sm l2every" type="button">Everywhere</button>');
}

// ---------- Filter holds Order and Tag (a list), and Highlights' colour, tag, favourites, order ----------
function filterExtras(fp){
  if (fp.querySelector('.l2fx')) return;
  const mk = (orig, label, id) => {
    if (!orig || orig.tagName !== 'SELECT') return '';
    return '<span class="lbl">' + label + '</span><select class="field sm l2fx" data-l2for="' + id + '">' + orig.innerHTML + '</select>';
  };
  const tag = document.querySelector('#main select#tagf') || document.querySelector('#main #tagf select'), sort = document.querySelector('#main #lsort');
  const h = mk(sort, 'Order', 'lsort') + mk(tag, 'Tag', 'tagf');
  if (!h) return;
  fp.insertAdjacentHTML('afterbegin', h);
  fp.querySelectorAll('.l2fx').forEach(c => {
    const o = c.dataset.l2for === 'lsort' ? sort : tag; c.value = o.value;
    c.addEventListener('change', ev => { ev.stopPropagation(); o.value = c.value; o.dispatchEvent(new Event('change', { bubbles: true })); });
  });
}
function hlFilter(){
  const top = document.querySelector('#main .top'), body = document.querySelector('#hlbody .hlfilters');
  if (!top || !body || S.route[0] !== 'highlights') return;
  const n = document.querySelectorAll('#hlbody .hlf2 .cdot.on, #hlbody .hlf2 [data-act="hlfav"].on').length + (($('#hltag') || {}).value ? 1 : 0) +
    ((($('#hlsort') || {}).value || 'recent') !== 'recent' ? 1 : 0) + (($('#hlpriv') || {}).checked ? 1 : 0);
  let b = top.querySelector('.l2hlf');
  if (!b) { const rv = top.querySelector('[data-act="hlreview"]'); if (!rv) return; rv.insertAdjacentHTML('beforebegin', '<button class="btn sm l2hlf" type="button">Filter</button>'); b = top.querySelector('.l2hlf'); }
  const label = n ? 'Filter · ' + n : 'Filter';
  if (b.textContent !== label) b.textContent = label;
  b.classList.toggle('on', root.classList.contains('l2-hlf') || n > 0);
}
document.addEventListener('click', e => {
  if (!L.on || !e.target.closest || !e.target.closest('.l2hlf')) return;
  root.classList.toggle('l2-hlf'); hlFilter();
});

// what the corner's own lines add to a screen's menu, and its foot
function mergeOwn(menu){
  const x = L.extraRows(); if (!x) return;
  if (x.items.length) { const rows = document.createElement('div'); rows.className = 'l2m-rows'; rows.innerHTML = x.items.map(rowHTML).join(''); menu.prepend(rows); }
  const foot = document.createElement('div'); foot.className = 'l2m-foot'; foot.innerHTML = footRows(); menu.appendChild(foot);
  menu.classList.add('l2menu');
}

addEventListener('resize', () => { if (L.on) L.frame(); });

// Preferences: the switch, on this device.
L.card = () => '<section class="card" id="lookcard"><h2>New look</h2><div class="prow"><div class="d"><b>On this device</b></div>' +
  '<div class="seg">' + [['1', 'Off'], ['2', 'On']].map(x => '<button class="' + ((x[0] === '2') === L.on ? 'on' : '') + '" data-look="' + x[0] + '">' + x[1] + '</button>').join('') + '</div></div></section>';
document.addEventListener('click', e => {
  const b = e.target.closest && e.target.closest('[data-look]'); if (!b) return;
  if ((b.dataset.look === '2') === L.on) return;
  C.lsSet('look', b.dataset.look); location.reload();
});

if (L.on) L.frame();
})();
