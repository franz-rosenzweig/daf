/* Add your own columns (Calibre's Preferences → Add your own columns): my own Calibre columns, each
   with its heading (renamed by a click) and Delete, and a new one made from a lookup name, a heading
   and one of Calibre's kinds (a fixed set takes its values). Calibre makes them (calibrewrite's
   create_column, column_heading and delete_column ops). C.OwnCols.open() */
(() => {
'use strict';
const C = window.DafCore, { api, esc, toast, $ } = C;
const X = '<svg width="16" height="16" viewBox="0 0 20 20" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"><path d="M6 6l8 8M14 6l-8 8"/></svg>';
const M = { data: null, busy: false, form: { label: '', heading: '', type: 'text', values: '' } };

function sheet(html){
  let s = $('#ocsheet');
  if (!s) { document.body.insertAdjacentHTML('beforeend', '<div class="beshade" id="ocshade"></div><div class="besheet ocsheet" id="ocsheet" role="dialog" aria-modal="true" aria-label="Add your own columns"></div>'); s = $('#ocsheet'); }
  s.innerHTML = html; s.hidden = false; $('#ocshade').hidden = false;
  document.body.classList.add('beopen');
  return s;
}
function close(){
  if (M.busy) return;
  const s = $('#ocsheet'); if (s) s.hidden = true;
  const sh = $('#ocshade'); if (sh) sh.hidden = true;
  if (!$('#bedit') || $('#bedit').hidden) document.body.classList.remove('beopen');
}
async function open(){
  sheet('<div class="behead"><h2>Add your own columns</h2></div><div class="bebody one"><p class="mute">Loading…</p></div>');
  try { M.data = await api('/api/catalog/columns'); } catch(e){ close(); toast(e.message); return; }
  draw();
}
const kind = c => { const k = c.dtype === 'text' && c.multi ? '*text' : c.dtype; return ((M.data.types.find(t => t.key === k) || {}).label) || c.dtype; };
const row = (label, ctl) => '<div class="berow"><span>' + esc(label) + '</span><div class="bectl">' + ctl + '</div></div>';
function draw(){
  const d = M.data, f = M.form, dis = M.busy ? ' disabled' : '';
  sheet('<div class="behead"><h2>Add your own columns</h2><span class="spacer"></span><button class="btn sm" data-oc="close">Close</button></div>' +
    '<div class="bebody one ocbody">' +
    '<div class="oclist">' + d.columns.map(c => '<div class="ocrow"><button class="ocname" data-ocren="' + esc(c.key) + '"' + dis + '><b>' + esc(c.label) + '</b><span class="mute tiny">' + esc(c.key) + ' · ' + esc(kind(c)) + '</span></button>' +
      '<button class="btn sm ib" data-ocdel="' + esc(c.key) + '" aria-label="Delete ' + esc(c.label) + '"' + dis + '>' + X + '</button></div>').join('') + '</div>' +
    '<h3>New column</h3>' +
    row('Lookup name', '<span class="ochash"><span>#</span><input class="field" data-ocf="label" value="' + esc(f.label) + '" autocomplete="off" autocapitalize="off" spellcheck="false"></span>') +
    row('Column heading', '<input class="field" data-ocf="heading" value="' + esc(f.heading) + '" autocomplete="off">') +
    row('Column type', '<select class="field" data-ocf="type">' + d.types.map(t => '<option value="' + esc(t.key) + '"' + (t.key === f.type ? ' selected' : '') + '>' + esc(t.label) + '</option>').join('') + '</select>') +
    (f.type === 'enumeration' ? row('Values', '<input class="field" data-ocf="values" value="' + esc(f.values) + '" autocomplete="off">') : '') +
    '<div class="ocgo"><button class="btn primary" data-oc="create"' + (M.busy || !f.label.trim() || !f.heading.trim() ? ' disabled' : '') + '>' + (M.busy ? 'Working…' : 'Create') + '</button></div></div>');
}
async function act(fn){
  M.busy = true; draw();
  try { await fn(); M.data = await api('/api/catalog/columns'); }
  catch(e){ toast(e.message); }
  M.busy = false; draw();
  if (C.Catalog) C.Catalog.reload();
}
document.addEventListener('click', e => {
  const t = e.target; if (!t.closest) return;
  if (t.closest('#ocshade')) { close(); return; }
  if (!t.closest('#ocsheet') || M.busy) return;
  const a = t.closest('[data-oc]');
  if (a && a.dataset.oc === 'close') { close(); return; }
  if (a && a.dataset.oc === 'create') {
    const f = M.form, label = f.label.trim().replace(/^#/, '').toLowerCase();
    act(async () => {
      const r = await api('/api/catalog/columns', { method: 'POST', body: JSON.stringify({ label, heading: f.heading.trim(), type: f.type, values: f.values.split(',').map(x => x.trim()).filter(Boolean) }) });
      M.form = { label: '', heading: '', type: f.type, values: '' };
      if (C.Catalog && C.Catalog.showColumn) C.Catalog.showColumn(r.key);
    });
    return;
  }
  const ren = t.closest('[data-ocren]');
  if (ren) { const c = M.data.columns.find(x => x.key === ren.dataset.ocren), to = (prompt('Column heading', c.label) || '').trim();
    if (to && to !== c.label) act(() => api('/api/catalog/columns/' + encodeURIComponent(c.key.slice(1)), { method: 'PUT', body: JSON.stringify({ heading: to }) }));
    return; }
  const del = t.closest('[data-ocdel]');
  if (del) { const c = M.data.columns.find(x => x.key === del.dataset.ocdel);
    if (confirm('Delete the column “' + c.label + '” and what every book has in it?')) act(() => api('/api/catalog/columns/' + encodeURIComponent(c.key.slice(1)), { method: 'DELETE' }));
    return; }
});
document.addEventListener('input', e => { const f = e.target.closest && e.target.closest('#ocsheet [data-ocf]'); if (!f) return;
  M.form[f.dataset.ocf] = f.value;
  const go = $('#ocsheet [data-oc="create"]'); if (go) go.disabled = M.busy || !M.form.label.trim() || !M.form.heading.trim(); });
document.addEventListener('change', e => { const f = e.target.closest && e.target.closest('#ocsheet [data-ocf="type"]'); if (f) { M.form.type = f.value; draw(); } });
document.addEventListener('keydown', e => { if (e.key === 'Escape' && $('#ocsheet') && !$('#ocsheet').hidden) { e.stopPropagation(); close(); } }, true);

C.OwnCols = { open };
})();
