/* Recovery (#recovery, daf/recovery.py): the Big Book by its chapters (the first 164 pages, the
   stories, the appendices), the Step 10 and 11 readings for the time of day, prayers, the highlights
   in it and the other A.A. books. Every reading and prayer opens at its place in the reader's own copy. */
(function(){
const C = window.DafCore, { $, $$, esc, api, cover, bar, shortTitle, bookRow } = C;
let P = null, part = 0;

const when = () => { const h = new Date().getHours(); return h < 12 ? 'morning' : h < 18 ? 'day' : 'evening'; };
const open = (id, at) => '#ebook/' + encodeURIComponent(id) + (at ? '/' + at : '');
const words = w => 'q:' + encodeURIComponent(w);

function readings(){
  const now = when(), list = P.readings.slice().sort((a, b) => (b.when === now) - (a.when === now));
  const head = { morning: 'This morning', day: 'Today', evening: 'Tonight' }[now];
  return '<section class="card"><div class="cardh"><h2>' + head + '</h2><span class="mute tiny">Steps 10 and 11, in your Big Book</span></div>' +
    list.map(r => '<a class="nrow tr rcread' + (r.when === now ? ' now' : '') + '" href="' + (P.book ? open(P.book.id, words(r.find)) : '#recovery') + '">' +
      '<b>' + esc(r.title) + '</b><span class="mute tiny">' + esc(r.step) + ' · page ' + esc(r.page) + '</span></a>').join('') + '</section>';
}

function chapters(){
  const lists = [P.first, P.stories, P.appendices], names = ['First 164 pages', 'Stories', 'Appendices'];
  const rows = (lists[part] || []).map(c => c.part
    ? '<div class="rcpart">' + esc(c.title) + '</div>'
    : '<a class="rch" href="' + open(P.book.id, encodeURIComponent(c.href)) + '"><span class="rcn">' + esc(c.n || '') + '</span><span class="rct">' + esc(c.title) + '</span>' +
      '<span class="rcp mute tiny">' + (c.page ? 'p. ' + esc(c.page) : '') + '</span>' + bar(c.read) + '</a>').join('');
  return '<div class="seg rcseg" role="tablist">' + names.map((n, i) => '<button type="button" role="tab" data-rcpart="' + i + '" class="' + (i === part ? 'on' : '') + '" aria-selected="' + (i === part) + '">' + n + '</button>').join('') + '</div>' +
    '<div class="rchs">' + (rows || '<span class="mute tiny">Nothing here in this copy.</span>') + '</div>';
}

function book(){
  const b = P.book;
  if (!b) return '<section class="card"><h2>The Big Book</h2><p class="mute" style="margin:0">Add your copy to Calibre (an EPUB), and its chapters show up here.</p></section>';
  return '<section class="card"><div class="rcbook">' + cover(b, 'cv') +
    '<div class="rcbt"><b>Alcoholics Anonymous</b><span class="mute tiny">Fourth Edition</span>' +
    '<span class="tiny mute">' + bar(b.progress) + ' ' + Math.round(b.progress) + '%</span>' +
    '<div class="rcacts">' + (P.now ? '<a class="btn primary sm" href="' + open(b.id, encodeURIComponent(P.now.href)) + '">Continue: ' + esc(P.now.title) + (P.now.page ? ', p. ' + esc(P.now.page) : '') + '</a>'
      : '<a class="btn primary sm" href="' + open(b.id) + '">Read</a>') +
    '<a class="btn sm" href="#book/' + encodeURIComponent(b.id) + '">The book’s page</a></div></div></div>' +
    (P.first.length ? '<div id="rcch">' + chapters() + '</div>' : '') + '</section>';
}

function prayers(){
  return '<section class="card"><h2>Prayers</h2>' + P.prayers.map(p =>
    '<details class="rcpr"><summary><b>' + esc(p.title) + '</b><span class="mute tiny">' + esc(p.note || (p.page ? 'Big Book, page ' + p.page : '')) + '</span></summary>' +
    (p.text ? '<p class="rcprt">' + esc(p.text) + '</p>'
      : '<p class="rcprt">' + esc(p.first) + '</p>' + (P.book ? '<a class="btn sm" href="' + open(P.book.id, words(p.find)) + '">Read it on page ' + esc(p.page) + '</a>' : '')) +
    '</details>').join('') + '</section>';
}

function highlights(){
  if (!P.book || !P.highlights.length) return '';
  return '<section class="card"><div class="cardh"><h2>Your highlights</h2><a class="tiny" href="#book/' + encodeURIComponent(P.book.id) + '">All ' + P.highlight_count + '</a></div>' +
    P.highlights.map(h => '<div class="hlc"><q class="go" data-open="' + esc(open(P.book.id, 'hl:' + encodeURIComponent(h.id))) + '" role="link" tabindex="0">' + C.HL.quote(h.text) + '</q></div>').join('') + '</section>';
}

function draw(){
  $('#rcpage').innerHTML = readings() + book() + prayers() + highlights() +
    (P.others.length ? '<section class="card"><h2>More to read</h2><div class="rcmore">' + P.others.map(b => bookRow(b)).join('') + '</div></section>' : '');
}

C.views.recovery = async () => {
  $('#main').innerHTML = '<div class="top"><h1>Recovery</h1><span class="spacer"></span><span class="mute tiny rcp-hint">Private: never in the review, Signal or on the Kindle</span></div><div class="page rcp-page" id="rcpage"><span class="mute">Loading…</span></div>';
  P = await C.swr('/api/recovery');
  if (!P.now && P.first.length) part = 0;
  draw();
};
document.addEventListener('click', e => {
  const t = e.target.closest('[data-rcpart]'); if (!t || !P) return;
  part = +t.dataset.rcpart; const box = $('#rcch'); if (box) box.innerHTML = chapters();
});
})();
