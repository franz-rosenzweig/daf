/* EpubMerge: the chosen books' EPUBs, in the order I set, made into one new Calibre book, the way
   Calibre's EpubMerge plugin does it (the plugin runs inside Daf's Calibre: calibrewrite's
   "epubmerge" op). The new book's title is the plugin's (the series, or the first title and
   "Anthology") until I change it. C.EpubMerge.open(books) */
(() => {
'use strict';
const C = window.DafCore, { api, esc, toast, $ } = C;
const store = { get(k, d){ try { const v = localStorage.getItem('daf.' + k); return v == null ? d : JSON.parse(v); } catch(e){ return d; } }, set(k, v){ try { localStorage.setItem('daf.' + k, JSON.stringify(v)); } catch(e){} } };
const sleep = ms => new Promise(r => setTimeout(r, ms));
const UP = '<svg width="16" height="16" viewBox="0 0 20 20" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12l5-5 5 5"/></svg>';
const X = '<svg width="16" height="16" viewBox="0 0 20 20" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"><path d="M6 6l8 8M14 6l-8 8"/></svg>';
const DOWN = '<svg width="16" height="16" viewBox="0 0 20 20" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M5 8l5 5 5-5"/></svg>';
const M = { books: [], off: [], title: '', titleSet: false, authors: '', authorsSet: false, busy: false,
  opts: Object.assign({ flatten: false, descriptions: false }, store.get('epubmerge', {})) };

function sheet(html){
  let s = $('#emsheet');
  if (!s) { document.body.insertAdjacentHTML('beforeend', '<div class="beshade" id="emshade"></div><div class="besheet emsheet" id="emsheet" role="dialog" aria-modal="true" aria-label="EpubMerge"></div>'); s = $('#emsheet'); }
  s.innerHTML = html; s.hidden = false; $('#emshade').hidden = false;
  document.body.classList.add('beopen');
  return s;
}
function close(){
  if (M.busy) return;
  const s = $('#emsheet'); if (s) s.hidden = true;
  const sh = $('#emshade'); if (sh) sh.hidden = true;
  if (!$('#bedit') || $('#bedit').hidden) document.body.classList.remove('beopen');
  M.books = []; M.off = [];
}
// The plugin's title and authors for the books as they're ordered now.
function defTitle(){
  const b = M.books; if (!b.length) return '';
  return b.every(x => x.series && x.series === b[0].series) ? b[0].series : b[0].title + ' Anthology';
}
function defAuthors(){
  const out = []; M.books.forEach(b => (b.authors || []).forEach(a => { if (!out.includes(a)) out.push(a); }));
  return out.join(' & ');
}
function open(books){
  books = (books || []).slice();
  M.off = books.filter(b => !(b.formats || []).includes('EPUB'));
  M.books = books.filter(b => (b.formats || []).includes('EPUB'));
  if (M.books.length > 1 && M.books.every(x => x.series && x.series === M.books[0].series))
    M.books.sort((a, b) => (a.series_index || 0) - (b.series_index || 0));
  Object.assign(M, { titleSet: false, authorsSet: false, busy: false });
  M.title = defTitle(); M.authors = defAuthors();
  draw();
}
const cover = b => b.cover ? '<img src="/api/cover/' + encodeURIComponent(b.id) + '?v=' + (b.cover_v || 0) + '" alt="" loading="lazy">' : '<span class="befnc"></span>';
const sel = (k, list, v) => '<select class="field" data-emo="' + k + '">' + list.map(([x, l]) => '<option value="' + x + '"' + (String(x) === String(v) ? ' selected' : '') + '>' + esc(l) + '</option>').join('') + '</select>';
const row = (label, ctl) => '<div class="berow"><span>' + esc(label) + '</span><div class="bectl">' + ctl + '</div></div>';
function draw(){
  const n = M.books.length;
  const list = M.books.map((b, i) => '<div class="emrow"><span class="emn">' + (i + 1) + '</span>' + cover(b) +
    '<span class="befct"><b>' + esc(b.title) + '</b><span class="mute tiny">' + esc([(b.authors || []).join(' & '), b.series ? b.series + (b.series_index != null ? ' ' + b.series_index : '') : ''].filter(Boolean).join(' · ')) + '</span></span>' +
    '<span class="emacts"><button class="btn sm" data-emmove="' + i + ':-1"' + (i ? '' : ' disabled') + ' aria-label="Up">' + UP + '</button>' +
    '<button class="btn sm" data-emmove="' + i + ':1"' + (i < n - 1 ? '' : ' disabled') + ' aria-label="Down">' + DOWN + '</button>' +
    '<button class="btn sm" data-emdrop="' + i + '" aria-label="Take out">' + X + '</button></span></div>').join('');
  const off = M.off.map(b => '<div class="emrow off">' + '<span class="emn"></span>' + cover(b) + '<span class="befct"><b>' + esc(b.title) + '</b><span class="mute tiny">No EPUB</span></span></div>').join('');
  sheet('<div class="behead"><h2>EpubMerge</h2><span class="spacer"></span><button class="btn sm" data-em="cancel">Cancel</button>' +
    '<button class="btn sm primary" data-em="merge"' + (n < 2 || M.busy ? ' disabled' : '') + '>' + (M.busy ? 'Merging…' : 'Merge') + '</button></div>' +
    '<div class="bebody one embody">' +
    row('Title', '<input class="field" data-emf="title" value="' + esc(M.title) + '">') +
    row('Authors', '<input class="field" data-emf="authors" value="' + esc(M.authors) + '">') +
    row('Contents', sel('flatten', [[0, 'Each book with its chapters'], [1, 'One level']], M.opts.flatten ? 1 : 0)) +
    row('Description', sel('descriptions', [[0, 'Titles'], [1, 'Titles and descriptions']], M.opts.descriptions ? 1 : 0)) +
    '<h3>' + n + ' EPUB' + (n === 1 ? '' : 's') + '</h3><div class="emlist">' + list + off + '</div></div>');
}
function move(i, by){
  const j = i + by; if (j < 0 || j >= M.books.length) return;
  [M.books[i], M.books[j]] = [M.books[j], M.books[i]];
  if (!M.titleSet) M.title = defTitle();
  if (!M.authorsSet) M.authors = defAuthors();
  draw();
  const b = $('#emsheet [data-emmove="' + j + ':' + by + '"]') || $('#emsheet [data-emmove="' + j + ':' + (-by) + '"]'); if (b) b.focus();
}
async function merge(){
  if (M.busy || M.books.length < 2) return;
  M.busy = true; draw();
  const authors = M.authorsSet ? M.authors.split('&').map(a => a.trim()).filter(Boolean) : [];
  try {
    const { job } = await api('/api/catalog/epubmerge', { method: 'POST', body: JSON.stringify({ ids: M.books.map(b => b.calibre_id),
      title: M.titleSet ? M.title.trim() : '', authors, flatten: M.opts.flatten, descriptions: M.opts.descriptions }) });
    let cid;
    for (let i = 0; ; i++) {
      await sleep(i < 4 ? 400 : 1000);
      const j = await api('/api/catalog/jobs/' + job);
      if (!j.running) { if (j.error) throw new Error(j.error); cid = j.done; break; }
    }
    M.busy = false; close(); toast('Merged');
    if (C.Catalog && cid) C.Catalog.choose([cid]);
  } catch(e){ M.busy = false; draw(); toast(e.message); }
}
document.addEventListener('click', e => {
  const t = e.target; if (!t.closest) return;
  if (t.closest('#emshade')) { close(); return; }
  if (!t.closest('#emsheet')) return;
  const a = t.closest('[data-em]');
  if (a) { if (a.dataset.em === 'cancel') close(); else if (a.dataset.em === 'merge') merge(); return; }
  const mv = t.closest('[data-emmove]');
  if (mv && !mv.disabled) { const [i, by] = mv.dataset.emmove.split(':').map(Number); move(i, by); return; }
  const dr = t.closest('[data-emdrop]');
  if (dr) { M.books.splice(+dr.dataset.emdrop, 1); if (!M.titleSet) M.title = defTitle(); if (!M.authorsSet) M.authors = defAuthors(); draw(); }
});
document.addEventListener('input', e => {
  const f = e.target.closest && e.target.closest('#emsheet [data-emf]'); if (!f) return;
  if (f.dataset.emf === 'title') { M.title = f.value; M.titleSet = !!f.value.trim(); }
  else { M.authors = f.value; M.authorsSet = !!f.value.trim(); }
});
document.addEventListener('change', e => {
  const s = e.target.closest && e.target.closest('#emsheet [data-emo]'); if (!s) return;
  M.opts[s.dataset.emo] = s.value === '1'; store.set('epubmerge', M.opts);
});
document.addEventListener('keydown', e => { if (e.key === 'Escape' && $('#emsheet') && !$('#emsheet').hidden) { e.stopPropagation(); close(); } }, true);

C.EpubMerge = { open };
})();
