/* Manga: Komga's library, read in Daf (daf/manga.py).
   #manga            every series, and the ones under way
   #manga/<series>   its volumes
   #mread/<book>[/<page>]   the reader, full screen: right to left (manga), left to right, or one
                     long strip (webtoons); two pages side by side when the screen is wide.
   Progress goes to Komga as the Kindle's account, so the Kindle and AniList follow; the time
   counts as "Manga in Daf". */
(() => {
const C = window.DafCore, { api, esc, toast, $, $$ } = C;
const M = C.Manga = {};
const thumb = (k, id) => '/api/manga/thumb/' + k + '/' + encodeURIComponent(id);
const store = { get(k, d){ try { const v = localStorage.getItem('daf.manga.' + k); return v == null ? d : JSON.parse(v); } catch(e){ return d; } },
  set(k, v){ try { localStorage.setItem('daf.manga.' + k, JSON.stringify(v)); } catch(e){} } };
const volWord = n => n === 1 ? '1 volume' : n + ' volumes';
const pct = (a, b) => b ? Math.round(100 * a / b) : 0;

/* ---------- the shelf ---------- */
function seriesCard(s){
  const p = s.count ? pct(s.read, s.count) : 0;
  return '<a class="mcard" href="#manga/' + encodeURIComponent(s.id) + '"><span class="mcov"><img src="' + thumb('s', s.id) + '" alt="" loading="lazy"></span>' +
    '<b>' + esc(s.name) + '</b><span class="mute tiny">' + (s.read ? s.read + ' of ' + volWord(s.count) + ' read' : volWord(s.count)) + '</span>' +
    (s.read ? '<span class="mbar"><i style="width:' + p + '%"></i></span>' : '') + '</a>';
}
function continueCard(s){
  const n = s.next, where = n.page ? 'page ' + n.page + ' of ' + n.pages : 'not started';
  return '<a class="mcont" href="#mread/' + encodeURIComponent(n.id) + '"><img src="' + thumb('b', n.id) + '" alt="" loading="lazy">' +
    '<span class="mct"><b>' + esc(s.name) + '</b><span class="mute tiny">' + esc(n.name) + '</span><span class="mute tiny">' + where + '</span>' +
    (n.page ? '<span class="mbar"><i style="width:' + pct(n.page, n.pages) + '%"></i></span>' : '') + '</span></a>';
}
async function shelfView(){
  $('#main').innerHTML = '<div class="top"><h1>Manga</h1></div><div class="page"><span class="mute">Asking Komga…</span></div>';
  let r;
  try { r = await C.swr('/api/manga'); }
  catch(e){ $('#main .page').innerHTML = '<p class="mute">Komga didn’t answer: ' + esc(e.message) + '</p>'; return; }
  $('#main .page').innerHTML =
    (r.continue.length ? '<section class="card"><div class="cardh"><h2>Keep reading</h2></div><div class="mconts">' + r.continue.map(continueCard).join('') + '</div></section>' : '') +
    '<section class="card"><div class="cardh"><h2>All series</h2><span class="mute tiny">' + r.series.length + '</span></div><div class="mgrid">' + r.series.map(seriesCard).join('') + '</div></section>' +
    '<p class="mute tiny">From Komga. Reading here moves the Kindle and AniList along too.</p>';
}

/* ---------- one series ---------- */
async function seriesView(sid){
  $('#main').innerHTML = '<div class="top"><a class="btn sm" href="#manga">' + C.I.back + '</a><h1>Manga</h1></div><div class="page"><span class="mute">Asking Komga…</span></div>';
  let s;
  try { s = await C.swr('/api/manga/series/' + encodeURIComponent(sid)); }
  catch(e){ $('#main .page').innerHTML = '<p class="mute">' + esc(e.message) + '</p>'; return; }
  $('#main .top h1').textContent = s.name;
  let row = b => '<a class="mvol' + (b.completed ? ' done' : '') + '" href="#mread/' + encodeURIComponent(b.id) + '"><img src="' + thumb('b', b.id) + '" alt="" loading="lazy">' +
    '<span class="mvt"><b>' + esc(b.name) + '</b><span class="mute tiny">' + (b.completed ? 'Read' : b.page ? 'Page ' + b.page + ' of ' + b.pages : b.pages + ' pages') + (b.ok ? '' : ' · Komga can’t open this file') + '</span>' +
    (b.page && !b.completed ? '<span class="mbar"><i style="width:' + pct(b.page, b.pages) + '%"></i></span>' : '') + '</span></a>';
  const keep = keeps(), row0 = row;
  if (keep) row = b => '<div class="mvrow">' + row0(b) + '<button class="ib mdl" data-mdl="' + esc(b.id) + '" aria-label="Download for reading without Wi-Fi" title="Download for reading without Wi-Fi">' + DL.get + '</button></div>';
  $('#main .page').innerHTML = '<section class="card mhead"><img src="' + thumb('s', s.id) + '" alt="">' +
    '<div><div class="mute tiny">' + (s.read ? s.read + ' of ' + volWord(s.count) + ' read' : volWord(s.count)) + (s.status && s.status !== 'ONGOING' ? ' · ' + esc(s.status.toLowerCase()) : '') + '</div>' +
    (s.summary ? '<p class="msum">' + esc(s.summary.slice(0, 600)) + (s.summary.length > 600 ? '…' : '') + '</p>' : '') +
    (s.next ? '<a class="btn primary" href="#mread/' + encodeURIComponent(s.next.id) + '">' + (s.next.page ? 'Keep reading ' : 'Read ') + esc(s.next.name) + '</a>' : '') + '</div></section>' +
    '<section class="card"><div class="mvols">' + s.books.map(row).join('') + '</div></section>';
  if (keep) drawDownloads();
}

/* ---------- downloads, in the Android app: a volume kept on the device, for reading with no Wi-Fi ---------- */
// The app (Offline.java) fetches every page at the size this screen's reader asks for and answers
// the reader from its copy; the page and reading time made offline wait in app.js's outbox.
const keeps = () => !!(window.dafShell && dafShell.can && dafShell.can('offline'));
const DL = {
  get: '<svg width="18" height="18" viewBox="0 0 20 20" aria-hidden="true"><path d="M10 3.5v9M6 9l4 4 4-4M4 16.5h12" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  done: '<svg width="18" height="18" viewBox="0 0 20 20" aria-hidden="true"><path d="M4.5 10.5l3.5 3.5 7.5-8" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"/></svg>',
};
let dlT = 0;
async function drawDownloads(){
  clearTimeout(dlT);
  if (!keeps() || !$('[data-mdl]')) return;
  let l; try { l = await dafShell.offline({ op: 'list' }); } catch(e){ return; }
  const have = new Map((l.manga || []).map(x => [x.id, x]));
  let busy = false;
  $$('[data-mdl]').forEach(b => {
    const x = have.get(b.dataset.mdl), st = x ? x.state : '';
    b.dataset.state = st;
    if (st === 'done') { b.innerHTML = DL.done; b.title = 'On this device · ' + Math.round(x.bytes / 1048576) + ' MB. Tap to remove it.'; }
    else if (st === 'loading' || st === 'waiting') { busy = true; b.innerHTML = '<span class="mdlp">' + (x.total ? Math.floor(100 * x.done / x.total) : 0) + '%</span>'; b.title = 'Downloading'; }
    else if (st === 'failed') { b.innerHTML = DL.get; b.title = 'It stopped: ' + (x.error || 'no answer') + '. Tap to carry on.'; b.classList.add('mdlbad'); }
    else { b.innerHTML = DL.get; b.title = 'Download for reading without Wi-Fi'; b.classList.remove('mdlbad'); }
  });
  if (busy) dlT = setTimeout(drawDownloads, 1500);
}
document.addEventListener('click', async e => {
  const b = e.target.closest && e.target.closest('[data-mdl]'); if (!b) return;
  e.preventDefault(); e.stopPropagation();
  const id = b.dataset.mdl, st = b.dataset.state;
  if (st === 'loading' || st === 'waiting') return;
  if (st === 'done' && !confirm('Remove this volume from the device? Komga keeps it.')) return;
  try {
    await dafShell.offline({ op: 'manga', id, on: st !== 'done', size: M.downloadSize() });
    toast(st === 'done' ? 'Removed from this device' : 'Downloading; it reads without Wi-Fi once it’s done');
  } catch(err){ toast(err.message); }
  drawDownloads();
});
C.views.manga = args => { const sid = args && args[0] ? decodeURIComponent(args[0]) : null; return sid ? seriesView(sid) : shelfView(); };

/* The reader is web/mreader.js. */
})();
