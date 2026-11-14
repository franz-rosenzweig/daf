/* Metadata download: Calibre's Preferences → Metadata download for Daf's own Calibre, the settings
   Find details runs with (daf/calibreprefs.py reads and writes them through Calibre): the sources,
   on or off, with their cover priority; the fields to download; the options; and the rules that
   transform downloaded tags. From All books' Library menu and Find details. C.DlPrefs.open() */
(() => {
'use strict';
const C = window.DafCore, { api, esc, toast, $, $$ } = C;
const UP = '<svg width="16" height="16" viewBox="0 0 20 20" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12l5-5 5 5"/></svg>';
const DOWN = '<svg width="16" height="16" viewBox="0 0 20 20" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M5 8l5 5 5-5"/></svg>';
const X = '<svg width="16" height="16" viewBox="0 0 20 20" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"><path d="M6 6l8 8M14 6l-8 8"/></svg>';
// The dialog's options, in its order and words.
const TICKS = [['txt_comments', 'Convert all downloaded comments to plain text'], ['swap_author_names', 'Swap author names from FN LN to LN, FN'],
  ['append_comments', 'Append comments to existing'], ['keep_dups', 'Keep more than one entry per source'], ['fewer_tags', 'Prefer fewer tags']];
const NUMS = [['max_tags', 'Max. number of tags to download', ''], ['wait_after_first_identify_result', 'Max. time to wait after first match is found', 'secs'],
  ['wait_after_first_cover_result', 'Max. time to wait after first cover is found', 'secs']];
const M = { d: null, src: {}, p: null, rules: [], busy: false };

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
// What the sheet shows: Calibre's state, with the sheet's own changes over it.
function take(d){
  M.d = d;
  M.src = Object.fromEntries(d.sources.map(s => [s.name, { enabled: s.enabled, priority: s.priority }]));
  M.p = JSON.parse(JSON.stringify(d.prefs));
  M.rules = (d.prefs.tag_map_rules || []).map(r => Object.assign({ replace: '' }, r));
}
const opt = (v, label, on) => '<option value="' + esc(v) + '"' + (on ? ' selected' : '') + '>' + esc(label) + '</option>';
const row = (label, ctl) => '<div class="berow"><span>' + esc(label) + '</span><div class="bectl">' + ctl + '</div></div>';
const sec = (title, body) => '<section class="mdsec"><h3>' + esc(title) + '</h3>' + body + '</section>';
function draw(){
  const d = M.d, L = d.labels, ign = new Set(M.p.ignore_fields || []);
  const sources = '<div class="mdsrc mdsrch"><span>Source</span><span>Cover priority</span></div>' + d.sources.map(s => {
    const v = M.src[s.name];
    return '<div class="mdsrc"><label class="cvchk"><input type="checkbox" data-mds="' + esc(s.name) + '"' + (v.enabled ? ' checked' : '') + '><span>' + esc(s.name) + '</span>' +
      (s.configured ? '' : '<span class="mute tiny">Not configured</span>') + '</label>' +
      '<input class="field" type="number" min="1" max="99" step="1" inputmode="numeric" data-mdp="' + esc(s.name) + '" value="' + v.priority + '" aria-label="Cover priority"' + (s.covers ? '' : ' disabled') + '></div>';
  }).join('');
  const fields = '<div class="mdfields">' + d.fields.map(f => '<label class="cvchk"><input type="checkbox" data-mdf="' + esc(f) + '"' + (ign.has(f) ? '' : ' checked') + '><span>' + esc(L.fields[f] || f) + '</span></label>').join('') + '</div>' +
    '<div class="mdbtns"><button class="btn sm" data-md="all">Select all</button><button class="btn sm" data-md="none">Select none</button></div>';
  const opts = TICKS.map(([k, l]) => '<div><label class="cvchk"><input type="checkbox" data-mdo="' + k + '"' + (M.p[k] ? ' checked' : '') + '><span>' + esc(l) + '</span></label></div>').join('') +
    NUMS.map(([k, l, u]) => row(l, '<span class="cvnum"><input class="field" type="number" min="0" max="99" step="1" inputmode="numeric" data-mdn="' + k + '" value="' + esc(M.p[k]) + '">' + (u ? '<span class="mute">' + u + '</span>' : '') + '</span>')).join('');
  const n = M.rules.length;
  const rules = M.rules.map((r, i) => '<div class="mdrule">' +
    '<select class="field" data-mdr="' + i + ':action" aria-label="Action">' + L.actions.map(([v, l]) => opt(v, l, v === r.action)).join('') + '</select>' +
    '<select class="field" data-mdr="' + i + ':match_type" aria-label="the tag, if it">' + L.matches.map(([v, l]) => opt(v, l, v === r.match_type)).join('') + '</select>' +
    '<input class="field" data-mdr="' + i + ':query" value="' + esc(r.query || '') + '" aria-label="Tags" spellcheck="false" autocapitalize="off" autocomplete="off">' +
    '<input class="field" data-mdr="' + i + ':replace" value="' + esc(r.replace || '') + '" aria-label="' + (r.action === 'split' ? 'on the character' : 'with the tag') + '" spellcheck="false" autocapitalize="off" autocomplete="off"' + (r.action === 'replace' || r.action === 'split' ? '' : ' disabled') + '>' +
    '<span class="emacts"><button class="btn sm" data-mdmove="' + i + ':-1"' + (i ? '' : ' disabled') + ' aria-label="Up">' + UP + '</button>' +
    '<button class="btn sm" data-mdmove="' + i + ':1"' + (i < n - 1 ? '' : ' disabled') + ' aria-label="Down">' + DOWN + '</button>' +
    '<button class="btn sm" data-mdx="' + i + '" aria-label="Remove rule">' + X + '</button></span></div>').join('') +
    '<div class="mdbtns"><button class="btn sm" data-md="add">Add rule</button></div>';
  const sc = $('#mdsheet .bebody'), top = sc ? sc.scrollTop : 0;
  sheet('<div class="behead"><h2>Metadata download</h2><span class="spacer"></span><button class="btn sm" data-md="cancel">Cancel</button>' +
    '<button class="btn sm primary" data-md="save"' + (M.busy ? ' disabled' : '') + '>' + (M.busy ? 'Saving…' : 'Save') + '</button></div>' +
    '<div class="bebody one mdbody">' + sec('Metadata sources', sources) + sec('Metadata fields to download', fields) + sec('Options', opts) +
    sec('Tag rules', rules) + '<div class="cvfoot"><button class="btn sm" data-md="defaults">Restore defaults</button></div></div>');
  const nb = $('#mdsheet .bebody'); if (nb && top) nb.scrollTop = top;
}
async function open(){
  let d;
  try { d = await api('/api/catalog/download-prefs'); } catch(e){ toast(e.message); return; }
  take(d); draw();
}
// Only what changed goes to Calibre, as its dialog commits.
async function save(){
  if (M.busy || !M.d) return;
  const d = M.d, sources = {}, prefs = {};
  d.sources.forEach(s => { const v = M.src[s.name], c = {};
    if (v.enabled !== s.enabled) c.enabled = v.enabled;
    if (v.priority !== s.priority) c.priority = v.priority;
    if (Object.keys(c).length) sources[s.name] = c; });
  M.p.tag_map_rules = M.rules.filter(r => String(r.query || '').trim()).map(r => ({ action: r.action, match_type: r.match_type, query: r.query, replace: r.action === 'replace' || r.action === 'split' ? r.replace || '' : '' }));
  for (const k of Object.keys(M.p)) if (JSON.stringify(M.p[k]) !== JSON.stringify(d.prefs[k])) prefs[k] = M.p[k];
  if (!Object.keys(sources).length && !Object.keys(prefs).length) { close(); return; }
  M.busy = true; draw();
  try { await api('/api/catalog/download-prefs', { method: 'PUT', body: JSON.stringify({ prefs, sources }) }); M.busy = false; close(); toast('Saved'); }
  catch(e){ M.busy = false; draw(); toast(e.message); }
}
function fieldsFromBoxes(){ M.p.ignore_fields = $$('#mdsheet [data-mdf]').filter(c => !c.checked).map(c => c.dataset.mdf).sort(); }
document.addEventListener('click', e => {
  const t = e.target; if (!t.closest) return;
  if (t.closest('#mdshade')) { close(); return; }
  if (!t.closest('#mdsheet') || !M.d) return;
  const mv = t.closest('[data-mdmove]');
  if (mv && !mv.disabled) { const [i, by] = mv.dataset.mdmove.split(':').map(Number), j = i + by; [M.rules[i], M.rules[j]] = [M.rules[j], M.rules[i]]; draw(); return; }
  const x = t.closest('[data-mdx]'); if (x) { M.rules.splice(+x.dataset.mdx, 1); draw(); return; }
  const b = t.closest('[data-md]'); if (!b || b.disabled) return;
  const k = b.dataset.md;
  if (k === 'cancel') close();
  else if (k === 'save') save();
  else if (k === 'all' || k === 'none') { M.p.ignore_fields = k === 'all' ? [] : M.d.fields.slice(); draw(); }
  else if (k === 'add') { M.rules.push({ action: 'remove', match_type: 'one_of', query: '', replace: '' }); draw(); const f = $('#mdsheet [data-mdr="' + (M.rules.length - 1) + ':query"]'); if (f) f.focus(); }
  else if (k === 'defaults') {       // Calibre's Restore defaults: its default sources and priorities, every field, the options' defaults; the rules stay
    M.d.sources.forEach(s => { M.src[s.name] = { enabled: s.default_enabled, priority: s.default_priority }; });
    const keep = M.p.tag_map_rules;
    M.p = JSON.parse(JSON.stringify(M.d.defaults)); M.p.tag_map_rules = keep; M.p.ignore_fields = [];
    draw();
  }
});
document.addEventListener('change', e => {
  const t = e.target; if (!t.closest || !t.closest('#mdsheet') || !M.d) return;
  if (t.matches('[data-mds]')) M.src[t.dataset.mds].enabled = t.checked;
  else if (t.matches('[data-mdf]')) fieldsFromBoxes();
  else if (t.matches('[data-mdo]')) M.p[t.dataset.mdo] = t.checked;
  else if (t.matches('select[data-mdr]')) { const [i, f] = t.dataset.mdr.split(':'); M.rules[+i][f] = t.value; if (f === 'action') draw(); }
});
document.addEventListener('input', e => {
  const t = e.target; if (!t.closest || !t.closest('#mdsheet') || !M.d) return;
  if (t.matches('[data-mdp]')) { const n = parseInt(t.value, 10); if (n >= 1) M.src[t.dataset.mdp].priority = Math.min(99, n); }
  else if (t.matches('[data-mdn]')) { const n = parseInt(t.value, 10); if (n >= 0) M.p[t.dataset.mdn] = Math.min(99, n); }
  else if (t.matches('input[data-mdr]')) { const [i, f] = t.dataset.mdr.split(':'); M.rules[+i][f] = t.value; }
});
// On window, ahead of Edit metadata's own keys: the sheet can sit over Find details.
window.addEventListener('keydown', e => {
  const s = $('#mdsheet'); if (!s || s.hidden) return;
  if (e.key === 'Escape') { e.preventDefault(); e.stopImmediatePropagation(); close(); }
  else if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) { e.preventDefault(); e.stopImmediatePropagation(); save(); }
}, true);

C.DlPrefs = { open };
})();
