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
    ['Today', [['today', 'Today']]],
    ['Books', [['books', 'Books'], ['catalog', 'All Books'], pin('manga') && ['manga', 'Manga'], pin('torah') && ['torah', 'Torah'], pin('recovery') && ['recovery', 'Recovery']]],
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
  const folders = cur && cur[0] === 'Feed' ? feedFolders() : [];
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
    '<div class="l2subs">' + pages.map(p => sub(p, onFolder && p[0] === 'feed' ? ' off' : '')).join('') + folders.map(fsub).join('') + '</div>' +
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
if (L.on) new MutationObserver(() => document.querySelectorAll('#main [data-tint]').forEach(L.tint)).observe(document.getElementById('main'), { childList: true, subtree: true });

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
  return '<section class="l2hero"' + (b.has_cover ? ' data-tint="' + esc(b.id) + '"' : '') + '>' +
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
function tidyMenu(menu){
  const spec = menu.querySelector('[data-bm]') ? MENUS.bm : menu.querySelector('[data-more]') ? MENUS.more : null;
  if (!spec || menu.classList.contains('l2m')) return;
  menu.classList.add('l2m');
  const used = new Set();
  const take = ([key, label, icon, onRe, bar], withIcon) => {
    const b = menu.querySelector(MSEL(key)); if (!b || used.has(b)) return null;
    used.add(b);
    if (bar && shown(document.querySelector(bar))) { b.remove(); return null; }       // the bar above has it
    const ck = b.querySelector('.ck'), c = b.cloneNode(true); c.querySelectorAll('kbd,.kbd').forEach(x => x.remove());
    const was = c.textContent.trim(), on = ck ? !!ck.textContent.trim() : !!(onRe && onRe.test(was));
    b.classList.toggle('on', on); if (on) b.setAttribute('aria-pressed', 'true');
    b.title = was;
    b.innerHTML = (withIcon && icon ? MICON[icon] : '') + '<span class="l2ml">' + esc(label || was) + '</span>';
    return b;
  };
  const box = cls => { const d = document.createElement('div'); d.className = cls; return d; };
  const parts = [];
  const tiles = box('l2m-tiles'); spec.tiles.forEach(x => { const b = take(x, true); if (b) tiles.appendChild(b); }); if (tiles.children.length) parts.push(tiles);
  const chips = box('l2m-chips'); spec.chips[1].forEach(x => { const b = take(x, false); if (b) chips.appendChild(b); });
  if (chips.children.length) { chips.insertAdjacentHTML('afterbegin', '<span class="l2m-h">' + spec.chips[0] + '</span>'); parts.push(chips); }
  spec.rows.forEach(g => { const rows = box('l2m-rows'); g.forEach(x => { const b = take(x, true); if (b) rows.appendChild(b); }); if (rows.children.length) parts.push(rows); });
  const foot = box('l2m-foot'); spec.foot.forEach(x => { const b = take(x, false); if (b) foot.appendChild(b); });
  const rest = box('l2m-rows'); [...menu.children].forEach(el => { if (!used.has(el) && el.tagName !== 'HR') rest.appendChild(el); }); if (rest.children.length) parts.push(rest);
  if (foot.children.length) parts.push(foot);
  menu.textContent = ''; parts.forEach(p => menu.appendChild(p));
  // it was placed for its old height: keep it on the screen
  const p = menu.closest('.pop'); if (p && !p.hidden) { const r = p.getBoundingClientRect(); if (r.bottom > innerHeight - 8) p.style.top = Math.max(8, innerHeight - 8 - r.height) + 'px'; if (r.right > innerWidth - 8) p.style.left = Math.max(8, innerWidth - 8 - r.width) + 'px'; }
}
if (L.on) new MutationObserver(() => { const m = document.querySelector('#pop .menu:not(.l2m)'); if (m) tidyMenu(m); }).observe(document.getElementById('pop'), { childList: true });

// The … menu: for now the places that have no tab. Each screen's own actions come to it in a later round.
function menu(anchor){
  const p = $('#pop'), phone = L.shape() === 'phone', all = tabs();
  const row = (go, label, act) => '<button ' + (act ? 'data-act="' + act + '"' : 'data-go="' + go + '"') + '>' + label + '</button>';
  const listen = (all.find(t => t[0] === 'Listen') || [0, []])[1];
  p.innerHTML = '<div class="menu l2menu">' +
    (phone ? row('', 'Search', 'palette') + row('', 'Add to Daf', 'add') + listen.map(x => row(x[0], x[1])).join('') + '<hr>' : '') +
    row('stats', 'Stats') + row('sources', 'Sources') + row('prefs', 'Preferences') + (C.Tips ? row('tips', 'What’s new') : '') + '</div>';
  p.hidden = false; p.style.right = 'auto'; p.style.bottom = 'auto';
  const r = anchor.getBoundingClientRect(), w = p.offsetWidth, h = p.offsetHeight;
  p.style.left = Math.max(8, Math.min(r.right - w, innerWidth - w - 8)) + 'px';
  p.style.top = (r.bottom + 8 + h > innerHeight ? Math.max(8, r.top - h - 8) : r.bottom + 8) + 'px';
}
document.addEventListener('click', e => {
  if (!L.on || !e.target.closest) return;
  const m = e.target.closest('[data-act="l2menu"]');
  if (m) { e.stopPropagation(); if ($('#pop').hidden || !$('#pop .l2menu')) menu(m); else $('#pop').hidden = true; return; }
  if (e.target.closest('#pop .l2menu button')) setTimeout(() => { $('#pop').hidden = true; }, 0);
}, true);
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
