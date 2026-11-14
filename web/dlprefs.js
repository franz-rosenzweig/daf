/* Metadata download: Calibre's Preferences → Metadata download for Daf's own Calibre, the settings
   Find details runs with (daf/calibreprefs.py reads and writes them through Calibre): the sources,
   on or off, with their cover priority and, under Configure, each one's own settings (Calibre's
   Configure selected source: its fields to download and its options, or the Goodreads plugins' own);
   the fields to download; the options; and the rules that transform downloaded tags, authors,
   publishers and series. From All books' Library menu and Find details. C.DlPrefs.open() */
(() => {
'use strict';
const C = window.DafCore, { api, esc, toast, $, $$ } = C;
const UP = '<svg width="16" height="16" viewBox="0 0 20 20" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12l5-5 5 5"/></svg>';
const DOWN = '<svg width="16" height="16" viewBox="0 0 20 20" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M5 8l5 5 5-5"/></svg>';
const X = '<svg width="16" height="16" viewBox="0 0 20 20" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"><path d="M6 6l8 8M14 6l-8 8"/></svg>';
const DOTS = '<svg width="16" height="16" viewBox="0 0 20 20" aria-hidden="true"><circle cx="5" cy="10" r="1.5" fill="currentColor"/><circle cx="10" cy="10" r="1.5" fill="currentColor"/><circle cx="15" cy="10" r="1.5" fill="currentColor"/></svg>';
// The dialog's options, in its order and words.
const TICKS = [['txt_comments', 'Convert all downloaded comments to plain text'], ['swap_author_names', 'Swap author names from FN LN to LN, FN'],
  ['append_comments', 'Append comments to existing'], ['keep_dups', 'Keep more than one entry per source'], ['fewer_tags', 'Prefer fewer tags']];
const NUMS = [['max_tags', 'Max. number of tags to download', ''], ['wait_after_first_identify_result', 'Max. time to wait after first match is found', 'secs'],
  ['wait_after_first_cover_result', 'Max. time to wait after first cover is found', 'secs']];
const RULE_KINDS = ['tag_map_rules', 'author_map_rules', 'publisher_map_rules', 'series_map_rules'];
const M = { d: null, src: {}, p: null, rules: {}, cfg: {}, orig: {}, open: new Set(), busy: false };
const copy = x => JSON.parse(JSON.stringify(x));

function sheet(html){
  let s = $('#mdsheet');
  if (!s) { document.body.insertAdjacentHTML('beforeend', '<div class="beshade mdshade" id="mdshade"></div><div class="besheet mdsheet" id="mdsheet" role="dialog" aria-modal="true" aria-label="Metadata download"></div>'); s = $('#mdsheet'); }
  s.innerHTML = html; s.hidden = false; $('#mdshade').hidden = false;
  document.body.classList.add('beopen');
  return s;
}
function close(){
  if (M.busy) return;
  const s = $('#mdsheet'); if (s) s.hidden = true;
  const sh = $('#mdshade'); if (sh) sh.hidden = true;
  if (!$('#bedit') || $('#bedit').hidden) document.body.classList.remove('beopen');
  M.d = null;
}
// A source's own settings as the sheet keeps them while it's open: a plugin's table as rows.
function cfgOf(c){
  const x = c.extra && c.extra.kind !== 'error' ? c.extra : null;
  return { ignore_fields: (c.ignore_fields || []).slice().sort(), options: Object.fromEntries((c.options || []).map(o => [o.name, o.value])),
    extra: x ? { kind: x.kind, values: copy(x.values || {}), rows: Object.entries(x.mappings || {}).map(([k, v]) => [k, (v || []).join(', ')]) } : null };
}
// What Calibre has, with the sheet's own changes over it.
function take(d){
  M.d = d;
  M.src = Object.fromEntries(d.sources.map(s => [s.name, { enabled: s.enabled, priority: s.priority }]));
  M.cfg = Object.fromEntries(d.sources.map(s => [s.name, cfgOf(s.config || {})]));
  M.orig = copy(M.cfg);
  M.p = copy(d.prefs);
  M.rules = Object.fromEntries(RULE_KINDS.map(k => [k, (d.prefs[k] || []).map(r => Object.assign({ replace: '' }, r))]));
}
const hasConfig = s => { const c = s.config || {}; return (c.fields || []).length || (c.options || []).length || (c.extra && c.extra.kind !== 'error'); };
const opt = (v, label, on) => '<option value="' + esc(v) + '"' + (on ? ' selected' : '') + '>' + esc(label) + '</option>';
const row = (label, ctl) => '<div class="berow"><span>' + esc(label) + '</span><div class="bectl">' + ctl + '</div></div>';
const sec = (title, body) => '<section class="mdsec"><h3>' + esc(title) + '</h3>' + body + '</section>';
const tick = (attr, on, label) => '<div><label class="cvchk"><input type="checkbox" ' + attr + (on ? ' checked' : '') + '><span>' + esc(label) + '</span></label></div>';
const numIn = (attr, v, step, unit, min, max) => '<span class="cvnum"><input class="field" type="number" inputmode="decimal" step="' + step + '"' + (min != null ? ' min="' + min + '"' : '') + (max != null ? ' max="' + max + '"' : '') + ' ' + attr + ' value="' + esc(v == null ? '' : v) + '">' + (unit ? '<span class="mute">' + esc(unit) + '</span>' : '') + '</span>';
// Configure selected source: the source's own fields to download and options, as Calibre's page for it.
function srcConfig(s){
  const c = s.config || {}, v = M.cfg[s.name], L = M.d.labels, n = esc(s.name), ign = new Set(v.ignore_fields);
  let h = '';
  if ((c.fields || []).length)
    h += '<h4>Metadata fields to download</h4><div class="mdfields">' + c.fields.map(f => '<label class="cvchk"><input type="checkbox" data-mdcf="' + n + '|' + esc(f) + '"' + (ign.has(f) ? '' : ' checked') + '><span>' + esc(L.fields[f] || f) + '</span></label>').join('') + '</div>';
  (c.options || []).forEach(o => {
    const a = 'data-mdco="' + n + '|' + esc(o.name) + '"', val = v.options[o.name];
    if (o.type === 'bool') h += tick(a, val, o.label);
    else if (o.type === 'number') h += row(o.label, numIn(a, val, o.whole ? 1 : .01, ''));
    else if (o.type === 'choices') h += row(o.label, '<select class="field" ' + a + '>' + (o.choices || []).map(([k, l]) => opt(JSON.stringify(k), l, JSON.stringify(k) === JSON.stringify(val))).join('') + '</select>');
    else h += row(o.label, '<input class="field" ' + a + ' value="' + esc(val == null ? '' : val) + '" spellcheck="false" autocapitalize="off" autocomplete="off">');
  });
  const x = v.extra;
  if (x && x.kind === 'goodreads') h += '<h4>Other options</h4>' + L.goodreads.map(([k, l]) => tick('data-mdgx="' + n + '|' + k + '"', x.values[k], l)).join('');
  if (x && x.kind === 'goodreads_more_tags') h += L.goodreads_more_tags.map(c2 => {
    const a = 'data-mdgx="' + n + '|' + c2.key + '"', val = x.values[c2.key];
    if (c2.type === 'bool') return tick(a, val, c2.label);
    if (c2.type === 'ints') return row(c2.label, '<input class="field" ' + a + ' value="' + esc((val || []).join(', ')) + '" inputmode="numeric" autocomplete="off">');
    return row(c2.label, numIn(a, val, c2.type === 'int' ? 1 : .1, c2.unit, c2.min, c2.max));
  }).join('');
  if (x) {
    const ml = L.mappings[x.kind];
    h += (ml.title ? '<h4>' + esc(ml.title) + '</h4>' : '') + '<div class="mdmap mdmaph"><span>' + esc(ml.cols[0]) + '</span><span>' + esc(ml.cols[1]) + '</span><span></span></div>' +
      x.rows.map(([k, t], i) => '<div class="mdmap"><input class="field" data-mdmk="' + n + '|' + i + '" value="' + esc(k) + '" aria-label="' + esc(ml.cols[0]) + '" autocomplete="off">' +
        '<input class="field" data-mdmt="' + n + '|' + i + '" value="' + esc(t) + '" aria-label="' + esc(ml.cols[1]) + '" autocomplete="off">' +
        '<button class="btn sm" data-mdmx="' + n + '|' + i + '" aria-label="Remove mapping">' + X + '</button></div>').join('') +
      '<div class="mdbtns"><button class="btn sm" data-mdmadd="' + n + '">Add mapping</button></div>';
  }
  if (c.extra && c.extra.kind === 'error') h += '<p class="mute tiny">' + esc(c.extra.error) + '</p>';
  return '<div class="mdcfg">' + h + '</div>';
}
function rulesBlock(kind){
  const R = M.d.labels.rules[kind], list = M.rules[kind], n = list.length, takes = a => R.replace.includes(a);
  return list.map((r, i) => '<div class="mdrule">' +
    '<select class="field" data-mdr="' + kind + ':' + i + ':action" aria-label="Action">' + R.actions.map(([v, l]) => opt(v, l, v === r.action)).join('') + '</select>' +
    '<select class="field" data-mdr="' + kind + ':' + i + ':match_type" aria-label="Match">' + R.matches.map(([v, l]) => opt(v, l, v === r.match_type)).join('') + '</select>' +
    '<input class="field" data-mdr="' + kind + ':' + i + ':query" value="' + esc(r.query || '') + '" aria-label="Value" spellcheck="false" autocapitalize="off" autocomplete="off">' +
    '<input class="field" data-mdr="' + kind + ':' + i + ':replace" value="' + esc(r.replace || '') + '" aria-label="' + esc(r.action === 'split' ? R.split : R.with) + '" spellcheck="false" autocapitalize="off" autocomplete="off"' + (takes(r.action) ? '' : ' disabled') + '>' +
    '<span class="emacts"><button class="btn sm" data-mdmove="' + kind + ':' + i + ':-1"' + (i ? '' : ' disabled') + ' aria-label="Up">' + UP + '</button>' +
    '<button class="btn sm" data-mdmove="' + kind + ':' + i + ':1"' + (i < n - 1 ? '' : ' disabled') + ' aria-label="Down">' + DOWN + '</button>' +
    '<button class="btn sm" data-mdx="' + kind + ':' + i + '" aria-label="Remove rule">' + X + '</button></span></div>').join('') +
    '<div class="mdbtns"><button class="btn sm" data-mdadd="' + kind + '">Add rule</button></div>';
}
function draw(){
  const d = M.d, L = d.labels, ign = new Set(M.p.ignore_fields || []);
  const sources = '<div class="mdsrc mdsrch"><span>Source</span><span>Cover priority</span><span></span></div>' + d.sources.map(s => {
    const v = M.src[s.name], open = M.open.has(s.name);
    return '<div class="mdsrc"><label class="cvchk"><input type="checkbox" data-mds="' + esc(s.name) + '"' + (v.enabled ? ' checked' : '') + '><span>' + esc(s.name) + '</span>' +
      (s.configured ? '' : '<span class="mute tiny">Not configured</span>') + '</label>' +
      '<input class="field" type="number" min="1" max="99" step="1" inputmode="numeric" data-mdp="' + esc(s.name) + '" value="' + v.priority + '" aria-label="Cover priority"' + (s.covers ? '' : ' disabled') + '>' +
      (hasConfig(s) ? '<button class="btn sm' + (open ? ' on' : '') + '" data-mdcfg="' + esc(s.name) + '" aria-expanded="' + open + '" aria-label="Configure ' + esc(s.name) + '">' + DOTS + '</button>' : '<span></span>') + '</div>' +
      (open && hasConfig(s) ? srcConfig(s) : '');
  }).join('');
  const fields = '<div class="mdfields">' + d.fields.map(f => '<label class="cvchk"><input type="checkbox" data-mdf="' + esc(f) + '"' + (ign.has(f) ? '' : ' checked') + '><span>' + esc(L.fields[f] || f) + '</span></label>').join('') + '</div>' +
    '<div class="mdbtns"><button class="btn sm" data-md="all">Select all</button><button class="btn sm" data-md="none">Select none</button></div>';
  const opts = TICKS.map(([k, l]) => tick('data-mdo="' + k + '"', M.p[k], l)).join('') +
    NUMS.map(([k, l, u]) => row(l, numIn('data-mdn="' + k + '"', M.p[k], 1, u, 0, 99))).join('');
  const sc = $('#mdsheet .bebody'), top = sc ? sc.scrollTop : 0;
  sheet('<div class="behead"><h2>Metadata download</h2><span class="spacer"></span><button class="btn sm" data-md="cancel">Cancel</button>' +
    '<button class="btn sm primary" data-md="save"' + (M.busy ? ' disabled' : '') + '>' + (M.busy ? 'Saving…' : 'Save') + '</button></div>' +
    '<div class="bebody one mdbody">' + sec('Metadata sources', sources) + sec('Metadata fields to download', fields) + sec('Options', opts) +
    RULE_KINDS.map(k => sec(L.rules[k].title, rulesBlock(k))).join('') +
    '<div class="cvfoot"><button class="btn sm" data-md="defaults">Restore defaults</button></div></div>');
  const nb = $('#mdsheet .bebody'); if (nb && top) nb.scrollTop = top;
}
async function open(){
  let d;
  try { d = await api('/api/catalog/download-prefs'); } catch(e){ toast(e.message); return; }
  M.open = new Set(); take(d); draw();
}
// A source's changes, only what differs from what Calibre has, in calibreprefs' shape.
function srcChanges(name){
  const v = M.cfg[name], o = M.orig[name], c = {};
  if (JSON.stringify(v.ignore_fields.slice().sort()) !== JSON.stringify(o.ignore_fields)) c.ignore_fields = v.ignore_fields.slice().sort();
  const ch = Object.fromEntries(Object.entries(v.options).filter(([k, x]) => JSON.stringify(x) !== JSON.stringify(o.options[k])));
  if (Object.keys(ch).length) c.options = ch;
  if (v.extra) {
    const x = v.extra, ox = o.extra, e = {};
    const vals = Object.fromEntries(Object.entries(x.values).filter(([k, y]) => JSON.stringify(y) !== JSON.stringify(ox.values[k])));
    if (Object.keys(vals).length) e.values = vals;
    const map = rows => { const m = {}; rows.forEach(([k, t]) => { k = String(k || '').trim(); if (k) m[k] = String(t || '').split(',').map(s => s.trim()).filter(Boolean); }); return m; };
    if (JSON.stringify(map(x.rows)) !== JSON.stringify(map(ox.rows))) e.mappings = map(x.rows);
    if (Object.keys(e).length) c[x.kind] = e;
  }
  return c;
}
// Only what changed goes to Calibre, as its dialogs commit.
async function save(){
  if (M.busy || !M.d) return;
  const d = M.d, sources = {}, prefs = {};
  d.sources.forEach(s => { const v = M.src[s.name], c = srcChanges(s.name);
    if (v.enabled !== s.enabled) c.enabled = v.enabled;
    if (v.priority !== s.priority) c.priority = v.priority;
    if (Object.keys(c).length) sources[s.name] = c; });
  RULE_KINDS.forEach(k => { const R = d.labels.rules[k];
    M.p[k] = M.rules[k].filter(r => String(r.query || '').trim()).map(r => ({ action: r.action, match_type: r.match_type, query: r.query, replace: R.replace.includes(r.action) ? r.replace || '' : '' })); });
  for (const k of Object.keys(M.p)) if (JSON.stringify(M.p[k]) !== JSON.stringify(d.prefs[k])) prefs[k] = M.p[k];
  if (!Object.keys(sources).length && !Object.keys(prefs).length) { close(); return; }
  M.busy = true; draw();
  try { await api('/api/catalog/download-prefs', { method: 'PUT', body: JSON.stringify({ prefs, sources }) }); M.busy = false; close(); toast('Saved'); }
  catch(e){ M.busy = false; draw(); toast(e.message); }
}
const at = (s, sep) => { const i = s.lastIndexOf(sep); return [s.slice(0, i), s.slice(i + 1)]; };
function fieldsFromBoxes(){ M.p.ignore_fields = $$('#mdsheet [data-mdf]').filter(c => !c.checked).map(c => c.dataset.mdf).sort(); }
function gmtValue(c, raw){
  if (c.type === 'bool') return raw;
  if (c.type === 'ints') { const l = String(raw).split(',').map(x => parseInt(x.trim(), 10)).filter(x => x >= 1); return l.length ? l : null; }
  const n = parseFloat(raw); return isFinite(n) ? n : null;
}
document.addEventListener('click', e => {
  const t = e.target; if (!t.closest) return;
  if (t.closest('#mdshade')) { close(); return; }
  if (!t.closest('#mdsheet') || !M.d) return;
  const cf = t.closest('[data-mdcfg]');
  if (cf) { const n = cf.dataset.mdcfg; if (M.open.has(n)) M.open.delete(n); else M.open.add(n); draw(); return; }
  const mv = t.closest('[data-mdmove]');
  if (mv && !mv.disabled) { const [k, i, by] = mv.dataset.mdmove.split(':'), a = +i, b = a + +by, l = M.rules[k]; [l[a], l[b]] = [l[b], l[a]]; draw(); return; }
  const x = t.closest('[data-mdx]'); if (x) { const [k, i] = x.dataset.mdx.split(':'); M.rules[k].splice(+i, 1); draw(); return; }
  const add = t.closest('[data-mdadd]');
  if (add) { const k = add.dataset.mdadd, R = M.d.labels.rules[k]; M.rules[k].push({ action: R.actions[0][0], match_type: R.matches[0][0], query: '', replace: '' }); draw();
    const f = $('#mdsheet [data-mdr="' + k + ':' + (M.rules[k].length - 1) + ':query"]'); if (f) f.focus(); return; }
  const mx = t.closest('[data-mdmx]'); if (mx) { const [n, i] = at(mx.dataset.mdmx, '|'); M.cfg[n].extra.rows.splice(+i, 1); draw(); return; }
  const ma = t.closest('[data-mdmadd]');
  if (ma) { const n = ma.dataset.mdmadd, rows = M.cfg[n].extra.rows; rows.push(['', '']); draw();
    const f = $('#mdsheet [data-mdmk="' + CSS.escape(n) + '|' + (rows.length - 1) + '"]'); if (f) f.focus(); return; }
  const b = t.closest('[data-md]'); if (!b || b.disabled) return;
  const k = b.dataset.md;
  if (k === 'cancel') close();
  else if (k === 'save') save();
  else if (k === 'all' || k === 'none') { M.p.ignore_fields = k === 'all' ? [] : M.d.fields.slice(); draw(); }
  else if (k === 'defaults') {       // Calibre's Restore defaults: its default sources and priorities, every field, the options' defaults; the rules and each source's own settings stay
    M.d.sources.forEach(s => { M.src[s.name] = { enabled: s.default_enabled, priority: s.default_priority }; });
    const keep = Object.fromEntries(RULE_KINDS.map(r => [r, M.p[r]]));
    M.p = Object.assign(copy(M.d.defaults), keep); M.p.ignore_fields = [];
    draw();
  }
});
document.addEventListener('change', e => {
  const t = e.target; if (!t.closest || !t.closest('#mdsheet') || !M.d) return;
  if (t.matches('[data-mds]')) M.src[t.dataset.mds].enabled = t.checked;
  else if (t.matches('[data-mdf]')) fieldsFromBoxes();
  else if (t.matches('[data-mdo]')) M.p[t.dataset.mdo] = t.checked;
  else if (t.matches('[data-mdcf]')) { const [n, f] = at(t.dataset.mdcf, '|'), l = new Set(M.cfg[n].ignore_fields); if (t.checked) l.delete(f); else l.add(f); M.cfg[n].ignore_fields = [...l].sort(); }
  else if (t.matches('input[type="checkbox"][data-mdco]')) { const [n, o] = at(t.dataset.mdco, '|'); M.cfg[n].options[o] = t.checked; }
  else if (t.matches('select[data-mdco]')) { const [n, o] = at(t.dataset.mdco, '|'); M.cfg[n].options[o] = JSON.parse(t.value); }
  else if (t.matches('input[type="checkbox"][data-mdgx]')) { const [n, k] = at(t.dataset.mdgx, '|'); M.cfg[n].extra.values[k] = t.checked; }
  else if (t.matches('select[data-mdr]')) { const [k, i, f] = t.dataset.mdr.split(':'); M.rules[k][+i][f] = t.value; if (f === 'action') draw(); }
});
document.addEventListener('input', e => {
  const t = e.target; if (!t.closest || !t.closest('#mdsheet') || !M.d) return;
  if (t.matches('[data-mdp]')) { const n = parseInt(t.value, 10); if (n >= 1) M.src[t.dataset.mdp].priority = Math.min(99, n); }
  else if (t.matches('[data-mdn]')) { const n = parseInt(t.value, 10); if (n >= 0) M.p[t.dataset.mdn] = Math.min(99, n); }
  else if (t.matches('input[data-mdr]')) { const [k, i, f] = t.dataset.mdr.split(':'); M.rules[k][+i][f] = t.value; }
  else if (t.matches('input[data-mdco]:not([type="checkbox"])')) {
    const [n, o] = at(t.dataset.mdco, '|'), spec = (M.d.sources.find(s => s.name === n).config.options || []).find(x => x.name === o);
    if (spec.type === 'number') { const v = parseFloat(t.value); if (isFinite(v)) M.cfg[n].options[o] = spec.whole ? Math.round(v) : v; }
    else M.cfg[n].options[o] = t.value;
  }
  else if (t.matches('input[data-mdgx]:not([type="checkbox"])')) {
    const [n, k] = at(t.dataset.mdgx, '|'), c = M.d.labels.goodreads_more_tags.find(x => x.key === k), v = gmtValue(c, t.value);
    if (v != null) M.cfg[n].extra.values[k] = v;
  }
  else if (t.matches('[data-mdmk]')) { const [n, i] = at(t.dataset.mdmk, '|'); M.cfg[n].extra.rows[+i][0] = t.value; }
  else if (t.matches('[data-mdmt]')) { const [n, i] = at(t.dataset.mdmt, '|'); M.cfg[n].extra.rows[+i][1] = t.value; }
});
// On window, ahead of Edit metadata's own keys: the sheet can sit over Find details.
window.addEventListener('keydown', e => {
  const s = $('#mdsheet'); if (!s || s.hidden) return;
  if (e.key === 'Escape') { e.preventDefault(); e.stopImmediatePropagation(); close(); }
  else if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) { e.preventDefault(); e.stopImmediatePropagation(); save(); }
}, true);

C.DlPrefs = { open };
})();
