/* Polish books: Calibre's Polish books for the chosen books, the way its toolbar action does it
   (calibrewrite's "polish" op runs Calibre's own gui_polish job, a book at a time). Every EPUB, AZW3
   and KEPUB a book has is polished, from its ORIGINAL_ when it has one, and the file it replaces is
   kept as ORIGINAL_<format> first. The actions are the dialog's, in its order, off until ticked; the
   last ones used are kept on this device. When a chosen book has ORIGINAL_ files, Restore the originals
   puts them back in place of the files they were saved from (Calibre's Restore the ORIGINAL_ format,
   calibrewrite's "restore_original" op). C.Polish.open(books) */
(() => {
'use strict';
const C = window.DafCore, { api, esc, toast, $, $$ } = C;
const store = { get(k, d){ try { const v = localStorage.getItem('daf.' + k); return v == null ? d : JSON.parse(v); } catch(e){ return d; } }, set(k, v){ try { localStorage.setItem('daf.' + k, JSON.stringify(v)); } catch(e){} } };
const sleep = ms => new Promise(r => setTimeout(r, ms));
const KINDS = ['EPUB', 'AZW3', 'KEPUB'];
const ACTS = [
  ['embed', 'Embed all referenced fonts'],
  ['subset', 'Subset all embedded fonts'],
  ['smarten_punctuation', 'Smarten punctuation'],
  ['metadata', 'Update metadata in the book files'],
  ['do_cover', 'Update the cover in the book files'],
  ['jacket', 'Add/replace metadata as a “book jacket” page'],
  ['remove_jacket', 'Remove a previously inserted book jacket'],
  ['remove_unused_css', 'Remove unused CSS rules from the book'],
  ['compress_images', 'Losslessly compress images'],
  ['download_external_resources', 'Download external resources'],
  ['add_soft_hyphens', 'Add soft hyphens'],
  ['remove_soft_hyphens', 'Remove soft hyphens'],
  ['upgrade_book', 'Upgrade book internals'],
];
// Ticking one of a pair unticks the other (both would undo each other); a jacket needs the details updated.
const OTHER = { jacket: 'remove_jacket', remove_jacket: 'jacket', add_soft_hyphens: 'remove_soft_hyphens', remove_soft_hyphens: 'add_soft_hyphens' };
const saved = store.get('polish', {}) || {};
const M = { books: [], off: [], busy: false, run: 0, opts: Object.assign({}, saved.opts || {}), keep: saved.keep !== false };

// What gets polished in a book: [format, polished from]
const plan = b => { const f = b.formats || []; return KINDS.filter(k => f.includes(k) || f.includes('ORIGINAL_' + k)).map(k => [k, f.includes('ORIGINAL_' + k) ? 'ORIGINAL_' + k : k]); };
const chosen = () => ACTS.filter(([k]) => M.opts[k]).map(([k]) => k);
const origs = b => (b.formats || []).filter(f => f.startsWith('ORIGINAL_'));

function sheet(html){
  let s = $('#plsheet');
  if (!s) { document.body.insertAdjacentHTML('beforeend', '<div class="beshade" id="plshade"></div><div class="besheet plsheet" id="plsheet" role="dialog" aria-modal="true" aria-label="Polish books"></div>'); s = $('#plsheet'); }
  s.innerHTML = html; s.hidden = false; $('#plshade').hidden = false;
  document.body.classList.add('beopen');
  return s;
}
// Closing while it works leaves the job going on the server; the toast still comes when it's done.
function close(){
  const s = $('#plsheet'); if (s) s.hidden = true;
  const sh = $('#plshade'); if (sh) sh.hidden = true;
  if (!$('#bedit') || $('#bedit').hidden) document.body.classList.remove('beopen');
  M.books = []; M.off = []; M.busy = false; M.run++;
}
function open(books){
  books = (books || []).slice();
  M.books = books.filter(b => plan(b).length);
  M.off = books.filter(b => !plan(b).length);
  M.busy = false; M.run++;
  draw();
}
const cover = b => b.cover ? '<img src="/api/cover/' + encodeURIComponent(b.id) + '?v=' + (b.cover_v || 0) + '" alt="" loading="lazy">' : '<span class="befnc"></span>';
const bookRow = (b, fmt, off) => '<div class="plrow' + (off ? ' off' : '') + '">' + cover(b) +
  '<span class="befct"><b>' + esc(b.title) + '</b><span class="mute tiny">' + esc([(b.authors || []).join(' & '), b.highlights ? b.highlights + ' highlight' + (b.highlights === 1 ? '' : 's') : ''].filter(Boolean).join(' · ')) + '</span></span>' +
  '<span class="plfmt mute tiny">' + esc(fmt) + '</span></div>';
function draw(){
  const n = M.books.length, dis = M.busy ? ' disabled' : '', back = M.books.concat(M.off).some(b => origs(b).length);
  // The formats that would be kept as ORIGINAL_ (a book polished from its ORIGINAL_ keeps nothing new)
  const fresh = KINDS.filter(k => M.books.some(b => plan(b).some(([f, src]) => f === k && src === k)));
  const opts = ACTS.map(([k, l]) => '<label><input type="checkbox" data-plo="' + k + '"' + (M.opts[k] ? ' checked' : '') + dis + '> ' + esc(l) + '</label>').join('');
  const list = M.books.map(b => bookRow(b, plan(b).map(([f, src]) => f === src ? f : f + ' from ' + src).join(' · '), false)).join('') +
    M.off.map(b => bookRow(b, 'No EPUB, AZW3 or KEPUB', true)).join('');
  sheet('<div class="behead"><h2>' + (n > 1 ? 'Polish ' + n + ' books' : n ? 'Polish book' : 'Polish books') + '</h2><span class="spacer"></span>' +
    (back ? '<button class="btn sm" data-pl="restore"' + dis + '>' + (M.busy === 'restore' ? 'Restoring…' : 'Restore the originals') + '</button>' : '') +
    '<button class="btn sm" data-pl="cancel">Cancel</button>' +
    '<button class="btn sm primary" data-pl="go"' + (!n || !chosen().length || M.busy ? ' disabled' : '') + '>' + (M.busy === 'polish' ? 'Polishing…' : 'Polish') + '</button></div>' +
    '<div class="bebody one plbody"><div class="plopts">' + opts + '</div>' +
    (fresh.length ? '<label class="plkeep"><input type="checkbox" data-plkeep' + (M.keep ? ' checked' : '') + dis + '> Keep the original as ' + fresh.map(k => 'ORIGINAL_' + k).join(' and ') + '</label>' : '') +
    '<h3>' + (n + M.off.length) + ' book' + (n + M.off.length === 1 ? '' : 's') + '</h3><div class="pllist">' + list + '</div></div>');
}
// The boxes and the button as M has them, without drawing the sheet again.
function sync(){
  $$('#plsheet [data-plo]').forEach(c => { c.checked = !!M.opts[c.dataset.plo]; });
  const go = $('#plsheet [data-pl="go"]'); if (go) go.disabled = !M.books.length || !chosen().length || M.busy;
}
// Polishing and restoring: a job on the server, a book at a time, followed until it's done.
const JOB = {
  polish: { url: '/api/catalog/polish', btn: 'go', ing: 'Polishing', ed: 'polished', one: 'Polished', fail: 'Calibre couldn’t polish it' },
  restore: { url: '/api/catalog/restore-original', btn: 'restore', ing: 'Restoring', ed: 'restored', one: 'Restored', fail: 'Calibre couldn’t restore it' },
};
function polish(){
  const ids = M.books.map(b => b.calibre_id), acts = chosen(), opts = {};
  if (M.busy || !ids.length || !acts.length) return;
  acts.forEach(k => { opts[k] = true; });
  work('polish', { ids, opts, keep_original: M.keep });
}
function restore(){
  const books = M.books.concat(M.off).filter(b => origs(b).length);
  if (M.busy || !books.length) return;
  const f = [...new Set(books.flatMap(origs))];
  if (!confirm(books.length === 1 ? 'Replace the ' + f.map(x => x.slice(9)).join(' and ') + ' with ' + f.join(' and ') + '?' : 'Replace the files of ' + books.length + ' books with their originals?')) return;
  work('restore', { ids: books.map(b => b.calibre_id) });
}
async function work(kind, body){
  const J = JOB[kind], run = ++M.run;
  M.busy = kind; draw();
  const mine = () => run === M.run && $('#plsheet') && !$('#plsheet').hidden;
  try {
    const r = await api(J.url, { method: 'POST', body: JSON.stringify(body) });
    let j = null;
    for (let i = 0, miss = 0; ; i++) {
      await sleep(i < 5 ? 800 : 2000);
      try { j = await api('/api/catalog/jobs/' + r.job); miss = 0; }
      catch(e){ if (++miss >= 5) throw e; continue; }
      if (!j.running) break;
      const btn = mine() && $('#plsheet [data-pl="' + J.btn + '"]');
      if (btn && j.total > 1) btn.textContent = J.ing + ' ' + Math.min(j.done + 1, j.total) + ' of ' + j.total + '…';
    }
    const bad = (j.failed || []).length, ok = (j.done || 0) - bad;      // done: the books it got to (fewer when stopped)
    if (mine()) close();
    toast(j.total === 1 ? (bad ? j.failed[0].error || J.fail : J.one) : ok + ' ' + J.ed + (bad ? ' · ' + bad + ' didn’t' : ''));
    if (C.Catalog) C.Catalog.reload();
  } catch(e){
    if (mine()) { M.busy = false; draw(); }
    toast(e.message);
  }
}
document.addEventListener('click', e => {
  const t = e.target; if (!t.closest) return;
  if (t.closest('#plshade')) { close(); return; }
  const a = t.closest('#plsheet [data-pl]'); if (!a) return;
  if (a.dataset.pl === 'cancel') close();
  else if (a.dataset.pl === 'go' && !a.disabled) polish();
  else if (a.dataset.pl === 'restore' && !a.disabled) restore();
});
document.addEventListener('change', e => {
  const t = e.target; if (!t.closest || !t.closest('#plsheet')) return;
  if (t.dataset.plo) {
    const k = t.dataset.plo;
    M.opts[k] = t.checked;
    if (t.checked && OTHER[k]) M.opts[OTHER[k]] = false;
    if (k === 'jacket' && t.checked) M.opts.metadata = true;
    if (k === 'metadata' && !t.checked) M.opts.jacket = false;
    sync();
  } else if (t.hasAttribute('data-plkeep')) M.keep = t.checked;
  else return;
  store.set('polish', { opts: M.opts, keep: M.keep });
});
document.addEventListener('keydown', e => { if (e.key === 'Escape' && $('#plsheet') && !$('#plsheet').hidden) { e.stopPropagation(); close(); } }, true);

C.Polish = { open };
})();
