/* Edit book's Check spelling and Reports (Calibre's Tools menu in its editor), on the working copy.
   ebooktools.py runs Calibre's own code: calibre.spell for the words, their languages, the
   dictionaries and the suggestions, polish.spell's replace_word for Change all (a checkpoint first),
   and polish.report's gather_data for the Reports. Check spelling is a panel beside the code, so the
   code stays in reach; Reports is a sheet with a tab for each. Show next and a tap on a report's row
   open that file at that place. C.EbookTools.spell(), C.EbookTools.reports() (from Edit book's ⋯). */
(() => {
'use strict';
const C = window.DafCore, { api, esc, toast, $, $$ } = C;
const E = () => C.EbookEdit && C.EbookEdit.tools;
const phone = () => matchMedia('(max-width:699px)').matches;
const X = '<svg width="16" height="16" viewBox="0 0 20 20" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"><path d="M6 6l8 8M14 6l-8 8"/></svg>';
const reEsc = s => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
const size = n => n >= 1048576 ? (n / 1048576).toFixed(1) + ' MB' : n >= 1024 ? Math.round(n / 1024) + ' KB' : n + ' B';
const short = name => String(name || '').split('/').pop();
const many = (n, one, more) => n + ' ' + (n === 1 ? one : more || one + 's');

// ---------- going to a place in the code ----------
// The word (or character) in a file, at or after a line: in the text first, inside a tag (alt, title) if
// that's the only place; after the last one shown when it's the same file and line.
async function goWord(name, line, word, after){
  const t = E(); if (!t) return;
  const b = t.book(), f = b && b.files.find(x => x.name === name);
  if (!f) return;
  await t.show(name);
  if (!f.editable) return null;
  const text = t.text(); if (!text) return;
  let start = 0;
  if (line > 1) { let n = 1; for (let i = 0; i < text.length && n < line; i++) if (text[i] === '\n') { n++; start = i + 1; } }
  if (after != null && after > start) start = after;
  const letters = /[\p{L}\p{N}]/u.test(word);
  const re = new RegExp(letters ? '(?<![\\p{L}\\p{N}_])' + reEsc(word) + '(?![\\p{L}\\p{N}_])' : reEsc(word), 'gu');
  const inTag = i => text.lastIndexOf('<', i) > text.lastIndexOf('>', i);
  const find = (from, outside) => { re.lastIndex = from; let m; while ((m = re.exec(text))) { if (!outside || !inTag(m.index)) return m; } return null; };
  const m = find(start, true) || find(start, false) || find(0, true) || find(0, false);
  if (m) { t.goTo({ from: m.index, to: m.index + m[0].length }); return m.index + m[0].length; }
  t.goTo({ line: line || 1, col: 0 });
  return null;
}
async function goLine(name, line){
  const t = E(); if (!t) return;
  await t.show(name, line ? { line, col: 0 } : null);
}

/* ---------- Check spelling ---------- */
const S = { cid: null, data: null, all: false, q: '', at: null, ignored: new Set(), next: {}, sugg: {}, busy: false };
const key = w => w[0] + '|' + w[1];
const langName = code => { const l = S.data && S.data.langs.find(x => x.code === code); return l ? l.name + (code.includes('-') ? ' (' + code.split('-')[1] + ')' : '') : code; };
const isOk = w => w[3] || S.ignored.has(key(w));
function panel(){
  let p = $('#ebxspell');
  const body = $('#ebx .ebxbody');
  if (!p && body) { body.insertAdjacentHTML('beforeend', '<section class="ebxtool" id="ebxspell" aria-label="Check spelling"></section>'); p = $('#ebxspell'); }
  return p;
}
async function spell(){
  const t = E(); if (!t) return;
  const b = t.book(); if (!b) return;
  if (S.cid !== b.cid) Object.assign(S, { cid: b.cid, data: null, at: null, ignored: new Set(), next: {}, sugg: {}, q: '' });
  const p = panel(); if (!p) return;
  p.hidden = false;
  if (S.data) { draw(); return; }
  await check();
}
async function check(){
  const t = E(); if (!t || S.busy) return;
  S.busy = true; draw();
  try {
    await t.flush();
    S.data = await t.job(api(t.base() + '/spell', { method: 'POST', body: '{}' }));
    S.next = {};
  } catch(e){ toast(e.message); }
  S.busy = false; draw();
}
function rows(){
  const q = S.q.trim().toLowerCase();
  return (S.data ? S.data.words : []).filter(w => (S.all || !isOk(w)) && (!q || w[0].toLowerCase().includes(q)));
}
function draw(){
  const p = $('#ebxspell'); if (!p || p.hidden) return;
  const d = S.data, list = rows(), bad = d ? d.words.filter(w => !isOk(w)).length : 0;
  const nodict = d ? d.langs.filter(l => !l.dictionary) : [];
  const shown = list.slice(0, 400);
  p.innerHTML = '<div class="ebxthead"><h2>Check spelling</h2><span class="spacer"></span>' +
      '<button class="btn sm" data-ebs="again"' + (S.busy ? ' disabled' : '') + '>' + (S.busy ? 'Checking…' : 'Check again') + '</button>' +
      '<button class="ib" data-ebs="close" aria-label="Close">' + X + '</button></div>' +
    '<div class="ebxtbar"><input class="field" id="ebsq" type="search" placeholder="Find" value="' + esc(S.q) + '" autocomplete="off" spellcheck="false">' +
      '<label class="ebscheck"><input type="checkbox" id="ebsall"' + (S.all ? ' checked' : '') + '> All words</label></div>' +
    (d ? '<div class="ebssum mute tiny"><span>' + bad + ' misspelled · ' + many(d.words.length, 'word') + '</span>' +
      nodict.map(l => '<span class="ebsnod">' + esc(l.name) + ': no dictionary</span>').join('') + '</div>' : '') +
    '<div class="ebslist">' + (!d ? '<p class="mute ebxempty">' + (S.busy ? 'Checking…' : '') + '</p>'
      : !list.length ? '<p class="mute ebxempty">' + (S.all || S.q ? 'Nothing matches' : 'No misspelled words') + '</p>'
      : shown.map(w => wordRow(w)).join('') + (list.length > shown.length ? '<p class="mute tiny ebxempty">' + (list.length - shown.length) + ' more</p>' : '')) + '</div>';
  const at = $('#ebxspell .ebsw.on'); if (at && at.scrollIntoViewIfNeeded) at.scrollIntoViewIfNeeded(false);
}
function wordRow(w){
  const k = key(w), on = S.at === k, ok = isOk(w);
  const st = S.ignored.has(k) ? 'Ignored' : w[4] ? 'In the dictionary' : ok ? '' : 'Misspelled';
  let h = '<div class="ebsw' + (on ? ' on' : '') + (ok ? '' : ' bad') + '"><button class="ebswh" data-ebsw="' + esc(k) + '"><b>' + esc(w[0]) + '</b>' +
    '<span class="mute tiny">' + esc(langName(w[1])) + '</span><span class="mute tiny ebsst">' + esc(st) + '</span><span class="ebsn">' + w[2] + '</span></button>';
  if (on) {
    const sg = S.sugg[k];
    h += '<div class="ebswx">' +
      '<div class="ebsbtns"><button class="btn sm" data-ebs="next">Show next</button>' +
      (w[3] ? '' : '<button class="btn sm" data-ebs="ignore">' + (S.ignored.has(k) ? 'Unignore' : 'Ignore') + '</button>') +
      (w[3] || w[4] ? '' : '<button class="btn sm" data-ebs="add">Add to dictionary</button>') + '</div>' +
      (sg === undefined ? '' : sg === null ? '<p class="mute tiny">…</p>' : sg.length ? '<div class="ebssug">' + sg.map(s => '<button class="ebchip" data-ebsug="' + esc(s) + '">' + esc(s) + '</button>').join('') + '</div>' : '') +
      '<div class="ebschg"><input class="field" id="ebsto" value="' + esc((sg && sg[0]) || w[0]) + '" autocomplete="off" spellcheck="false" aria-label="Change to">' +
      '<button class="btn sm primary" data-ebs="change">Change all</button></div></div>';
  }
  return h + '</div>';
}
const cur = () => S.data && S.data.words.find(w => key(w) === S.at);
async function pick(k){
  S.at = S.at === k ? null : k; draw();
  const w = cur(); if (!w || S.sugg[k] !== undefined || isOk(w) && w[3]) return;
  S.sugg[k] = null; draw();
  try { S.sugg[k] = (await api(E().base() + '/spell/suggest', { method: 'POST', body: JSON.stringify({ word: w[0], lang: w[1] }) })).suggestions || []; }
  catch(e){ S.sugg[k] = []; }
  if (S.at === k) draw();
}
async function showNext(){
  const w = cur(); if (!w) return;
  const locs = w[5] || [], n = locs.length / 2; if (!n) return;
  const st = S.next[key(w)] || { i: 0, name: null, line: null, end: null };
  const i = st.i % n, name = S.data.files[locs[2 * i]], line = locs[2 * i + 1];
  if (phone()) { const p = $('#ebxspell'); if (p) p.hidden = true; }
  const end = await goWord(name, line, w[0], st.name === name && st.line === line ? st.end : null);
  S.next[key(w)] = { i: i + 1, name, line, end };
}
async function addWord(){
  const w = cur(); if (!w) return;
  try { await api(E().base() + '/spell/add', { method: 'POST', body: JSON.stringify({ word: w[0], lang: w[1] }) }); w[3] = true; w[4] = true; draw(); }
  catch(e){ toast(e.message); }
}
async function changeAll(){
  const w = cur(), t = E(), to = ($('#ebsto') || {}).value || '';
  if (!w || !t || !to.trim() || to.trim() === w[0]) return;
  try {
    await t.flush();
    const r = await t.busy('Changing…', () => t.job(api(t.base() + '/spell/change', { method: 'POST', body: JSON.stringify({ word: w[0], to: to.trim(), lang: w[1] }) })));
    if (!r.changed || !r.changed.length) { toast('Nothing to change'); return; }
    await t.reload();
    S.at = null;
    toast(w[0] + ' → ' + to.trim());
    await check();
  } catch(e){ toast(e.message); }
}

/* ---------- Reports ---------- */
const R = { cid: null, data: null, tab: 'files', busy: false };
const TABS = [['files', 'Files'], ['words', 'Words'], ['images', 'Images'], ['links', 'Links'], ['chars', 'Characters'], ['css', 'Style rules']];
const CATS = { text: 'Text', style: 'Style', image: 'Image', font: 'Font', opf: 'OPF', toc: 'Contents', misc: 'Other' };
function rsheet(){
  let s = $('#ebxrep');
  const ebx = $('#ebx');
  if (!s && ebx) { ebx.insertAdjacentHTML('beforeend', '<div class="beshade" id="ebxrepshade"></div><div class="besheet ebxrep" id="ebxrep" role="dialog" aria-modal="true" aria-label="Reports"></div>'); s = $('#ebxrep'); }
  return s;
}
function rclose(){ const s = $('#ebxrep'); if (s) s.hidden = true; const d = $('#ebxrepshade'); if (d) d.hidden = true; }
async function reports(){
  const t = E(); if (!t) return;
  const b = t.book(); if (!b) return;
  if (R.cid !== b.cid) Object.assign(R, { cid: b.cid, data: null });
  const s = rsheet(); if (!s) return;
  s.hidden = false; $('#ebxrepshade').hidden = false;
  R.data = null; R.busy = true; rdraw();
  try { await t.flush(); R.data = await t.job(api(t.base() + '/reports', { method: 'POST', body: '{}' })); }
  catch(e){ toast(e.message); }
  R.busy = false; rdraw();
}
const go = (name, line, extra) => '<button class="ebrgo" data-ebrname="' + esc(name) + '" data-ebrline="' + (line || '') + '"' + (extra || '') + '>' + esc(short(name)) + (line ? ' · ' + line : '') + '</button>';
function tabHTML(){
  const d = R.data;
  if (!d) return '<p class="mute ebxempty">' + (R.busy ? 'Making the reports…' : '') + '</p>';
  if (R.tab === 'files') {
    const total = d.files.reduce((a, f) => a + f.size, 0);
    return '<p class="mute tiny ebrsum">' + many(d.files.length, 'file') + ' · ' + size(total) + '</p><table class="ebrt"><thead><tr><th>Name</th><th>Type</th><th class="n">Size</th><th class="n">Words</th></tr></thead><tbody>' +
      d.files.map(f => '<tr data-ebrname="' + esc(f.name) + '"><td>' + esc(f.name) + '</td><td>' + esc(CATS[f.category] || f.category) + '</td><td class="n">' + size(f.size) + '</td><td class="n">' + (f.words >= 0 ? f.words : '') + '</td></tr>').join('') + '</tbody></table>';
  }
  if (R.tab === 'words') {
    const w = d.words, per = d.files.filter(f => f.words > 0);
    return '<p class="mute tiny ebrsum">' + many(w.total, 'word') + ' · ' + w.unique + ' different · ' + w.langs.map(l => esc(l.name) + ' ' + l.words).join(' · ') + '</p>' +
      '<h3>In each file</h3><table class="ebrt"><tbody>' + per.map(f => '<tr data-ebrname="' + esc(f.name) + '"><td>' + esc(f.name) + '</td><td class="n">' + f.words + '</td></tr>').join('') + '</tbody></table>' +
      '<h3>Most used</h3><table class="ebrt"><tbody>' + w.list.map(x => '<tr data-ebrname="' + esc(x[3] || '') + '" data-ebrline="' + (x[4] || '') + '" data-ebrword="' + esc(x[0]) + '"><td>' + esc(x[0]) + '</td><td class="mute">' + esc(x[1]) + '</td><td class="n">' + x[2] + '</td></tr>').join('') + '</tbody></table>';
  }
  if (R.tab === 'images') {
    if (!d.images.length) return '<p class="mute ebxempty">No images</p>';
    return '<table class="ebrt"><thead><tr><th>Name</th><th class="n">Size</th><th class="n">Width × height</th><th>Used in</th></tr></thead><tbody>' +
      d.images.map(i => '<tr data-ebrname="' + esc(i.name) + '"><td>' + esc(i.name) + '</td><td class="n">' + size(i.size) + '</td><td class="n">' + (i.width ? i.width + ' × ' + i.height : '') + '</td><td>' +
        (i.used.length ? i.used.map(u => go(u[0], u[1])).join(' ') : '<span class="mute">Not used</span>') + '</td></tr>').join('') + '</tbody></table>';
  }
  if (R.tab === 'links') {
    if (!d.links.length) return '<p class="mute ebxempty">No links</p>';
    const broken = d.links.filter(l => l.ok === false).length;
    return '<p class="mute tiny ebrsum">' + many(d.links.length, 'link') + (broken ? ' · ' + broken + ' broken' : '') + '</p><table class="ebrt"><thead><tr><th></th><th>Where</th><th>Text</th><th>To</th></tr></thead><tbody>' +
      d.links.map(l => '<tr class="' + (l.ok === false ? 'broken' : '') + '" data-ebrname="' + esc(l.name) + '" data-ebrline="' + (l.line || '') + '"><td class="ebrok">' + (l.external ? 'Web' : l.ok ? 'OK' : 'Broken') + '</td><td>' + esc(short(l.name)) + (l.line ? ' · ' + l.line : '') + '</td><td>' + esc(l.text) + '</td><td>' +
        (l.external ? esc(l.href) : l.dest && l.ok ? go(l.dest, l.dest_line, '') + (l.anchor ? '<span class="mute"> #' + esc(l.anchor) + '</span>' : '')
          : esc(l.href) + (l.anchor ? '#' + esc(l.anchor) : '')) + '</td></tr>').join('') + '</tbody></table>';
  }
  if (R.tab === 'chars') {
    return '<p class="mute tiny ebrsum">' + many(d.chars.length, 'character') + '</p><table class="ebrt"><thead><tr><th></th><th>Name</th><th>Code</th><th class="n">Count</th></tr></thead><tbody>' +
      d.chars.map(c => '<tr data-ebrname="' + esc(c.files[0] || '') + '" data-ebrword="' + esc(c.char) + '"><td class="ebrch">' + (c.code <= 32 ? '' : esc(c.char)) + '</td><td>' + esc(c.name) + '</td><td class="mute">U+' + c.code.toString(16).toUpperCase().padStart(4, '0') + '</td><td class="n">' + c.count + '</td></tr>').join('') + '</tbody></table>';
  }
  if (!d.css.length) return '<p class="mute ebxempty">No style rules</p>';
  const unused = d.css.filter(c => !c.count).length;
  return '<p class="mute tiny ebrsum">' + many(d.css.length, 'rule') + (unused ? ' · ' + unused + ' unused' : '') + '</p><table class="ebrt"><thead><tr><th>Rule</th><th>Where</th><th class="n">Used</th><th>In</th></tr></thead><tbody>' +
    d.css.map(c => '<tr class="' + (c.count ? '' : 'unused') + '" data-ebrname="' + esc(c.name) + '" data-ebrline="' + (c.line || '') + '"><td><code>' + esc(c.selector) + '</code></td><td>' + esc(short(c.name)) + ' · ' + c.line + '</td><td class="n">' + c.count + '</td><td>' +
      c.matched.map(m => go(m[0], m[1][0])).join(' ') + '</td></tr>').join('') + '</tbody></table>';
}
function rdraw(){
  const s = $('#ebxrep'); if (!s || s.hidden) return;
  s.innerHTML = '<div class="behead"><h2>Reports</h2><span class="spacer"></span><button class="btn sm" data-ebr="again"' + (R.busy ? ' disabled' : '') + '>Again</button><button class="btn sm primary" data-ebr="close">Close</button></div>' +
    '<div class="ebrtabs" role="tablist">' + TABS.map(([k, l]) => '<button role="tab" class="calsw" data-ebrtab="' + k + '" aria-pressed="' + (R.tab === k) + '">' + l + '</button>').join('') + '</div>' +
    '<div class="ebrbody">' + tabHTML() + '</div>';
}

/* ---------- events ---------- */
document.addEventListener('click', e => {
  const t = e.target; if (!t.closest) return;
  if (t.closest('#ebxspell')) {
    const sw = t.closest('[data-ebsw]'); if (sw) { pick(sw.dataset.ebsw); return; }
    const sg = t.closest('[data-ebsug]'); if (sg) { const f = $('#ebsto'); if (f) { f.value = sg.dataset.ebsug; f.focus(); } return; }
    const a = t.closest('[data-ebs]'); if (!a || a.disabled) return;
    const k = a.dataset.ebs;
    if (k === 'close') { $('#ebxspell').hidden = true; }
    else if (k === 'again') check();
    else if (k === 'next') showNext();
    else if (k === 'ignore') { const w = cur(); if (w) { const kk = key(w); S.ignored.has(kk) ? S.ignored.delete(kk) : S.ignored.add(kk); draw(); } }
    else if (k === 'add') addWord();
    else if (k === 'change') changeAll();
    return;
  }
  if (t.closest('#ebxrepshade')) { rclose(); return; }
  if (!t.closest('#ebxrep')) return;
  const tb = t.closest('[data-ebrtab]'); if (tb) { R.tab = tb.dataset.ebrtab; rdraw(); return; }
  const a = t.closest('[data-ebr]');
  if (a) { if (a.dataset.ebr === 'close') rclose(); else if (!a.disabled) reports(); return; }
  const g = t.closest('[data-ebrname]');
  if (g && g.dataset.ebrname) {
    const name = g.dataset.ebrname, line = +g.dataset.ebrline || null, word = g.dataset.ebrword;
    rclose();
    if (word) goWord(name, line || 1, word, null); else goLine(name, line);
  }
});
document.addEventListener('input', e => {
  if (e.target.id === 'ebsq') { S.q = e.target.value; const pos = e.target.selectionStart; draw(); const f = $('#ebsq'); if (f) { f.focus(); f.setSelectionRange(pos, pos); } }
});
document.addEventListener('change', e => { if (e.target.id === 'ebsall') { S.all = e.target.checked; draw(); } });
document.addEventListener('keydown', e => {
  if (e.key !== 'Escape') return;
  const r = $('#ebxrep');
  if (r && !r.hidden) { e.preventDefault(); e.stopPropagation(); rclose(); return; }
  if (e.target.id === 'ebsto' || e.target.id === 'ebsq') { e.preventDefault(); e.stopPropagation(); const p = $('#ebxspell'); if (p) p.hidden = true; }
}, true);
document.addEventListener('keydown', e => {
  if (e.key === 'Enter' && e.target.id === 'ebsto') { e.preventDefault(); e.stopPropagation(); changeAll(); }
}, true);

C.EbookTools = { spell, reports };
})();
