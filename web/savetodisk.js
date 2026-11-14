/* Save to disk: Calibre's Save to disk for the chosen books in All books (Download with several
   books chosen, or Library › Save to disk…). Calibre's own options, in its words and with its
   defaults: the save template, the formats, the cover and the OPF beside each book, underscores for
   spaces, English letters only, lower case, and everything in a single folder; kept on this device.
   Calibre names the folders and files (savetodisk.py) and the zip comes back laid out that way.
   C.SaveDisk.open(books) */
(() => {
'use strict';
const C = window.DafCore, { api, esc, toast, $, $$ } = C;
const store = { get(k, d){ try { const v = localStorage.getItem('daf.' + k); return v == null ? d : JSON.parse(v); } catch(e){ return d; } }, set(k, v){ try { localStorage.setItem('daf.' + k, JSON.stringify(v)); } catch(e){} } };
const sleep = ms => new Promise(r => setTimeout(r, ms));
const TEMPLATE = '{author_sort}/{title}/{title} - {authors}';
const DEFAULTS = { template: TEMPLATE, formats: 'all', cover: true, opf: true, underscores: false, ascii: false, lowercase: false, single: false };
const BOXES = [['cover', 'Save cover separately'], ['opf', 'Save metadata in separate OPF file'], ['underscores', 'Replace space with underscores'],
  ['ascii', 'Convert non-English characters to English equivalents'], ['lowercase', 'Change paths to lowercase'], ['single', 'Save in a single folder']];
const M = { books: [], busy: false, run: 0, opts: Object.assign({}, DEFAULTS, store.get('savedisk', {})) };
if (typeof M.opts.template !== 'string' || !M.opts.template.trim()) M.opts.template = TEMPLATE;
const keep = () => store.set('savedisk', M.opts);

function sheet(html){
  let s = $('#svsheet');
  if (!s) { document.body.insertAdjacentHTML('beforeend', '<div class="beshade" id="svshade"></div><div class="besheet svsheet" id="svsheet" role="dialog" aria-modal="true" aria-label="Save to disk"></div>'); s = $('#svsheet'); }
  s.innerHTML = html; s.hidden = false; $('#svshade').hidden = false;
  document.body.classList.add('beopen');
  return s;
}
// Closing while it works leaves the job going; its zip is dropped after an hour.
function close(){
  const s = $('#svsheet'); if (s) s.hidden = true;
  const sh = $('#svshade'); if (sh) sh.hidden = true;
  if (!$('#bedit') || $('#bedit').hidden) document.body.classList.remove('beopen');
  M.books = []; M.busy = false; M.run++;
}
function open(books){
  M.books = (books || []).slice(); M.busy = false; M.run++;
  draw();
}
// The formats the chosen books have, Calibre's order (alphabetical)
const kinds = () => [...new Set(M.books.flatMap(b => b.formats || []))].sort();
const isOn = f => M.opts.formats === 'all' || (M.opts.formats || []).includes(f);
const ready = () => !M.busy && M.books.length && M.opts.template.trim() && (M.opts.formats === 'all' || kinds().some(isOn));
function draw(){
  const dis = M.busy ? ' disabled' : '', n = M.books.length;
  const fmts = '<label class="svchk"><input type="checkbox" data-svall' + (M.opts.formats === 'all' ? ' checked' : '') + dis + '> All formats</label>' +
    kinds().map(f => '<label class="svchk"><input type="checkbox" data-svf="' + esc(f) + '"' + (isOn(f) ? ' checked' : '') + dis + '> ' + esc(f) + '</label>').join('');
  sheet('<div class="behead"><h2>' + (n > 1 ? 'Save ' + n + ' books to disk' : 'Save to disk') + '</h2><span class="spacer"></span><button class="btn sm" data-sv="cancel">Cancel</button>' +
    '<button class="btn sm primary" data-sv="go"' + (ready() ? '' : ' disabled') + '>' + (M.busy ? 'Saving…' : 'Save') + '</button></div>' +
    '<div class="bebody one svbody">' +
    '<div class="berow"><span>Save template</span><div class="bectl svtpl"><input class="field" data-svtpl type="text" autocomplete="off" autocapitalize="off" spellcheck="false" value="' + esc(M.opts.template) + '"' + dis + '>' +
      '<button class="btn sm" data-sv="reset"' + dis + '>Reset</button></div></div>' +
    '<div class="berow betop"><span>Formats to save</span><div class="bectl svfmts">' + fmts + '</div></div>' +
    '<div class="svopts">' + BOXES.map(([k, l]) => '<label class="svchk"><input type="checkbox" data-svo="' + k + '"' + (M.opts[k] ? ' checked' : '') + dis + '> ' + esc(l) + '</label>').join('') + '</div></div>');
}
function sync(){
  const all = $('#svsheet [data-svall]'); if (all) all.checked = M.opts.formats === 'all';
  $$('#svsheet [data-svf]').forEach(c => { c.checked = isOn(c.dataset.svf); });
  const go = $('#svsheet [data-sv="go"]'); if (go) go.disabled = !ready();
  keep();
}
async function save(){
  if (!ready()) return;
  const run = ++M.run, body = Object.assign({ ids: M.books.map(b => b.calibre_id) }, M.opts);
  M.busy = true; draw();
  const mine = () => run === M.run && $('#svsheet') && !$('#svsheet').hidden;
  try {
    const r = await api('/api/catalog/save', { method: 'POST', body: JSON.stringify(body) });
    let j = null;
    for (let i = 0, miss = 0; ; i++) {
      await sleep(i < 5 ? 600 : 1500);
      try { j = await api('/api/catalog/jobs/' + r.job); miss = 0; }
      catch(e){ if (++miss >= 5) throw e; continue; }
      if (!j.running) break;
    }
    if (j.error) throw new Error(j.error);
    if (run !== M.run) return;                     // closed while it worked: no download
    const d = j.done, a = document.createElement('a');
    a.href = '/api/catalog/save/' + d.file; a.download = d.name; document.body.appendChild(a); a.click(); a.remove();
    if (mine()) close();
    if (d.skipped && d.skipped.length) toast(d.books + ' saved · ' + d.skipped.length + ' left out');
  } catch(e){
    if (mine()) { M.busy = false; draw(); }
    toast(e.message);
  }
}
document.addEventListener('click', e => {
  const t = e.target; if (!t.closest) return;
  if (t.closest('#svshade')) { close(); return; }
  const a = t.closest('#svsheet [data-sv]'); if (!a || a.disabled) return;
  if (a.dataset.sv === 'cancel') close();
  else if (a.dataset.sv === 'go') save();
  else if (a.dataset.sv === 'reset') { M.opts.template = TEMPLATE; const i = $('#svsheet [data-svtpl]'); if (i) i.value = TEMPLATE; sync(); }
});
document.addEventListener('input', e => { if (e.target.matches && e.target.matches('#svsheet [data-svtpl]')) { M.opts.template = e.target.value; sync(); } });
document.addEventListener('change', e => {
  const t = e.target; if (!t.closest || !t.closest('#svsheet')) return;
  if (t.hasAttribute('data-svall')) M.opts.formats = t.checked ? 'all' : [];
  else if (t.dataset.svf) {
    const f = t.dataset.svf, now = M.opts.formats === 'all' ? kinds() : (M.opts.formats || []).slice();
    M.opts.formats = t.checked ? [...new Set(now.concat(f))] : now.filter(x => x !== f);
  } else if (t.dataset.svo) M.opts[t.dataset.svo] = t.checked;
  else return;
  sync();
});
document.addEventListener('keydown', e => {
  if (!$('#svsheet') || $('#svsheet').hidden) return;
  if (e.key === 'Escape') { e.stopPropagation(); close(); }
  else if (e.key === 'Enter' && e.target.matches && e.target.matches('[data-svtpl]')) { e.preventDefault(); save(); }
}, true);

C.SaveDisk = { open };
})();
