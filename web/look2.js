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
    ['Books', [['books', 'Books'], ['catalog', 'All Books'], pin('manga') && ['manga', 'Manga'], pin('torah') && ['torah', 'Torah']]],
    ['Library', [['library', 'Library'], pin('shortlist') && ['library/starred', 'Shortlist']]],
    ['Feed', [ed && ['edition', 'Edition'], ['feed', 'Feed']]],
    ['Highlights', [['highlights', 'Highlights'], ['review', 'Review'], pin('paper') && ['paper', 'Paper pages']]],
    ['Listen', [pin('podcasts') && ['podcasts', 'Podcasts'], pin('recovery') && ['recovery', 'Recovery']]],
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
