/* Add from ISBN (Calibre's Add books › Add from ISBN): ISBNs pasted or typed, each looked up with
   Calibre's own sources (isbnadd.py), then the ones ticked added as books without a file, with what
   was found, its cover and the tags to apply; the new books come up chosen in All books.
   C.IsbnAdd.open() */
(() => {
'use strict';
const C = window.DafCore, { api, esc, toast, $ } = C;
const sleep = ms => new Promise(r => setTimeout(r, ms));
const far = u => String(u).startsWith('found:') ? '/api/catalog/found/' + String(u).slice(6) + '?thumb=1' : '/api/catalog/coverproxy?u=' + encodeURIComponent(u);
const M = { text: '', tags: '', items: null, off: new Set(), busy: false, run: 0 };

function sheet(html){
  let s = $('#ibsheet');
  if (!s) { document.body.insertAdjacentHTML('beforeend', '<div class="beshade" id="ibshade"></div><div class="besheet ibsheet" id="ibsheet" role="dialog" aria-modal="true" aria-label="Add from ISBN"></div>'); s = $('#ibsheet'); }
  const sc = $('.bebody', s), top = sc ? sc.scrollTop : 0;
  s.innerHTML = html; s.hidden = false; $('#ibshade').hidden = false;
  document.body.classList.add('beopen');
  const nb = $('.bebody', s); if (nb && top) nb.scrollTop = top;
  return s;
}
function close(){
  if (M.busy) return;
  M.run++;
  const s = $('#ibsheet'); if (s) s.hidden = true;
  const sh = $('#ibshade'); if (sh) sh.hidden = true;
  if (!$('#bedit') || $('#bedit').hidden) document.body.classList.remove('beopen');
}
function open(){ Object.assign(M, { items: null, off: new Set(), busy: false }); draw(); const t = $('#ibsheet [data-ibf="text"]'); if (t) t.focus(); }
const chosen = () => (M.items || []).filter(it => it.state === 'found' && !M.off.has(it.isbn));
const row = (label, ctl) => '<div class="berow betop"><span>' + esc(label) + '</span><div class="bectl">' + ctl + '</div></div>';
function item(it){
  const f = it.found, on = it.state === 'found' && !M.off.has(it.isbn);
  const cover = f && f.cover ? '<img src="' + far(f.cover) + '" alt="" loading="lazy">' : '<span class="befnc"></span>';
  const what = it.state === 'wait' ? '<span class="befcvwait ibwait"></span>' : '';
  const body = f ? '<b>' + esc(f.title) + '</b><span class="mute tiny">' + esc([(f.authors || []).join(' & '), f.publisher, (f.published || '').slice(0, 4)].filter(Boolean).join(' · ')) + '</span>'
    : it.state === 'have' ? '<b>' + esc(it.title || '') + '</b><span class="mute tiny">In the library</span>'
    : '<b>' + esc(it.token) + '</b><span class="mute tiny">' + (it.state === 'bad' ? 'Not an ISBN' : it.state === 'missing' ? 'Not found' : 'Looking it up') + '</span>';
  return '<label class="ibrow' + (it.state === 'found' ? '' : ' off') + '">' +
    (it.state === 'found' ? '<input type="checkbox" data-ibon="' + esc(it.isbn) + '"' + (on ? ' checked' : '') + (M.busy ? ' disabled' : '') + '>' : '<span class="ibnobox"></span>') +
    cover + '<span class="befct">' + body + '</span><span class="mute tiny ibisbn">' + esc(it.isbn || '') + '</span>' + what + '</label>';
}
function draw(){
  const looking = M.items && M.items.some(it => it.state === 'wait'), n = chosen().length;
  const go = !M.items ? '<button class="btn sm primary" data-ib="look"' + (M.busy ? ' disabled' : '') + '>Look up</button>'
    : '<button class="btn sm primary" data-ib="add"' + (n && !M.busy && !looking ? '' : ' disabled') + '>' + (M.busy ? 'Adding…' : n === 1 ? 'Add 1 book' : 'Add ' + n + ' books') + '</button>';
  sheet('<div class="behead"><h2>Add from ISBN</h2><span class="spacer"></span>' + (M.items && !M.busy ? '<button class="btn sm" data-ib="back">Back</button>' : '') +
    '<button class="btn sm" data-ib="cancel">Cancel</button>' + go + '</div>' +
    '<div class="bebody one ibbody">' +
    (!M.items ? row('ISBNs', '<textarea class="field ibtext" data-ibf="text" rows="8" spellcheck="false" autocapitalize="off" autocomplete="off">' + esc(M.text) + '</textarea>')
      : '<div class="iblist">' + M.items.map(item).join('') + '</div>') +
    row('Tags to apply', '<input class="field" data-ibf="tags" value="' + esc(M.tags) + '" autocomplete="off" spellcheck="false">') + '</div>');
}
async function look(){
  if (M.busy || !M.text.trim()) return;
  const n = ++M.run; M.busy = true; draw();
  try {
    const { job } = await api('/api/catalog/isbn/lookup', { method: 'POST', body: JSON.stringify({ text: M.text }) });
    M.busy = false;
    for (let i = 0; ; i++) {
      const j = await api('/api/catalog/jobs/' + job);
      if (n !== M.run) return;
      M.items = j.items || []; draw();
      if (j.state !== 'running') break;
      await sleep(i < 3 ? 1200 : 2000);
    }
  } catch(e){ M.busy = false; if (n === M.run) { draw(); toast(e.message); } }
}
async function add(){
  const books = chosen().map(it => Object.assign({}, it.found, { isbn: it.isbn }));
  if (M.busy || !books.length) return;
  M.busy = true; draw();
  try {
    const { job } = await api('/api/catalog/isbn/add', { method: 'POST', body: JSON.stringify({ books, tags: M.tags.split(',').map(x => x.trim()).filter(Boolean) }) });
    let ids;
    for (let i = 0; ; i++) {
      await sleep(i < 4 ? 800 : 1500);
      const j = await api('/api/catalog/jobs/' + job);
      if (!j.running) { if (j.error) throw new Error(j.error); ids = j.done || []; break; }
    }
    M.busy = false; close();
    toast(ids.length === 1 ? '1 book added' : ids.length + ' books added');
    if (C.Catalog && ids.length) C.Catalog.choose(ids);
  } catch(e){ M.busy = false; draw(); toast(e.message); }
}
document.addEventListener('click', e => {
  const t = e.target; if (!t.closest) return;
  if (t.closest('#ibshade')) { close(); return; }
  const a = t.closest('#ibsheet [data-ib]'); if (!a) return;
  const k = a.dataset.ib;
  if (k === 'cancel') close();
  else if (k === 'back') { M.run++; M.items = null; draw(); }
  else if (k === 'look') look();
  else if (k === 'add') add();
});
document.addEventListener('change', e => {
  const c = e.target.closest && e.target.closest('#ibsheet [data-ibon]'); if (!c) return;
  if (c.checked) M.off.delete(c.dataset.ibon); else M.off.add(c.dataset.ibon);
  draw();
});
document.addEventListener('input', e => { const f = e.target.closest && e.target.closest('#ibsheet [data-ibf]'); if (f) M[f.dataset.ibf] = f.value; });
document.addEventListener('keydown', e => {
  if (!$('#ibsheet') || $('#ibsheet').hidden) return;
  if (e.key === 'Escape') { e.stopPropagation(); close(); }
  else if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) { e.preventDefault(); e.stopPropagation(); M.items ? add() : look(); }
}, true);

C.IsbnAdd = { open };
})();
