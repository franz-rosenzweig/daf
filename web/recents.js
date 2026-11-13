/* Recents (recents.py): everything read, watched, listened to or opened, newest first, a day at a
   time. A row opens what it was; a private sitting has no link. More asks for the week before. */
(function(){
const C = window.DafCore, { $, esc, api } = C;
const R = { days: [], next: null, busy: false };

const ICON = {
  Book: 'M4 4.5h3.5v11H4zM9 4.5h3.5v11H9zM13.6 5.2l2.8.8-2.6 9.8-2.8-.8', Kindle: 'M5.5 3h9v14h-9zM8 14.5h4',
  Article: 'M5 3.5h10v13H5zM7.5 7h5M7.5 10h5M7.5 13h3', Video: 'M3.5 5.5h13v9h-13zM8.5 8v4l3.5-2z',
  Podcast: 'M4 13.5V11a6 6 0 0 1 12 0v2.5M4 12.5h2.5v4H4zM13.5 12.5H16v4h-2.5z', Audiobook: 'M4 13.5V11a6 6 0 0 1 12 0v2.5M4 12.5h2.5v4H4zM13.5 12.5H16v4h-2.5z',
  Manga: 'M3.5 4.5h6v11h-6zM10.5 4.5h6v11h-6z', Paper: 'M5 3.5h7l3 3v10H5zM12 3.5v3h3',
};
const icon = k => '<svg width="20" height="20" viewBox="0 0 20 20" aria-hidden="true"><path d="' + (ICON[k] || ICON.Article) + '" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>';

function dayName(iso){
  const d = new Date(iso + 'T12:00:00'), t = new Date(); t.setHours(12, 0, 0, 0);
  const n = Math.round((t - d) / 864e5);
  if (n === 0) return 'Today';
  if (n === 1) return 'Yesterday';
  return d.toLocaleDateString('en-US', n < 7 ? { weekday: 'long' } : { weekday: 'long', month: 'long', day: 'numeric', year: d.getFullYear() === t.getFullYear() ? undefined : 'numeric' });
}
function row(x){
  const book = x.go && x.go.startsWith('book/');
  const pic = x.pic ? '<img class="rcpic' + (book ? ' book' : '') + '" src="' + esc(x.pic) + '" alt="" loading="lazy" onerror="this.replaceWith(Object.assign(document.createElement(\'span\'),{className:\'rcpic none\'}))">'
    : '<span class="rcpic none">' + icon(x.kind) + '</span>';
  const meta = [x.kind, x.author, x.minutes ? x.minutes + ' min' : ''].filter(Boolean).map(esc).join(' · ');
  const inner = '<span class="rcpw">' + pic + '</span><span class="rcb"><span class="rct">' + esc(C.shortTitle ? C.shortTitle(x.title) : x.title) + '</span><span class="rcm">' + meta + '</span></span><span class="rcw">' + esc(x.time) + '</span>';
  return x.go ? '<a class="rcrow" href="#' + esc(x.go) + '">' + inner + '</a>' : '<div class="rcrow">' + inner + '</div>';
}
function draw(){
  const box = $('#rcnt'); if (!box) return;
  box.innerHTML = (R.days.length ? R.days.map(d => '<section class="rcday"><h2>' + esc(dayName(d.date)) + '</h2><div class="card rclist">' + d.items.map(row).join('') + '</div></section>').join('')
    : '<p class="mute">Nothing yet</p>') +
    (R.next ? '<div class="rcmore"><button class="btn sm" data-rcmore>' + (R.busy ? 'Loading…' : 'More') + '</button></div>' : '');
}
async function more(){
  if (R.busy || !R.next) return;
  R.busy = true; draw();
  try {
    let r = await api('/api/recents?n=7&before=' + R.next);
    R.days = R.days.concat(r.days); R.next = r.next;
    // a quiet week: keep going until there's something to show or nothing older
    for (let i = 0; i < 8 && !r.days.length && R.next; i++) { r = await api('/api/recents?n=14&before=' + R.next); R.days = R.days.concat(r.days); R.next = r.next; }
  } catch(e){ C.toast(e.message); }
  R.busy = false; draw();
}
C.views.recents = async () => {
  $('#main').innerHTML = '<div class="top"><h1>Recents</h1></div><div class="page rcpage" id="rcnt"><span class="mute">Loading…</span></div>';
  const r = await api('/api/recents?n=7');
  R.days = r.days; R.next = r.next; R.busy = false;
  draw();
  if (!R.days.length && R.next) more();
};
document.addEventListener('click', e => { if (e.target.closest && e.target.closest('[data-rcmore]')) more(); });
})();
