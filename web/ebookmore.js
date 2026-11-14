/* Edit book's other tools, as Calibre's editor has them (daf/ebookmore.py runs Calibre's own code
   on the working copy): Split at cursor, Merge files, Beautify current file and all files, Insert
   special character and Check external links. They sit in Edit book's ⋯ menu (Merge also in an HTML
   or CSS file's menu); ebookedit.js hands its helpers over as C.EbookEdit.ext. */
(() => {
'use strict';
const C = window.DafCore, { api, esc, toast, $, $$ } = C;
const ed = () => C.EbookEdit.ext;
const book = () => ed().book();
const short = name => name.split('/').pop();
const folder = name => name.includes('/') ? name.slice(0, name.lastIndexOf('/')) : '';
const recentKey = 'daf.ebx.charsRecent';
const recent = { get(){ try { return JSON.parse(localStorage.getItem(recentKey) || '[]'); } catch(e){ return []; } },
  add(cp){ try { const l = [cp, ...recent.get().filter(x => x !== cp)].slice(0, 40); localStorage.setItem(recentKey, JSON.stringify(l)); } catch(e){} } };
// Calibre's short names for the characters that don't show (char_select.py non_printing), for the grid.
const NP = { 0xa0: 'nbsp', 0x2000: 'nqsp', 0x2001: 'mqsp', 0x2002: 'ensp', 0x2003: 'emsp', 0x2004: '3/msp', 0x2005: '4/msp', 0x2006: '6/msp',
  0x2007: 'fsp', 0x2008: 'psp', 0x2009: 'thsp', 0x200A: 'hsp', 0x200b: 'zwsp', 0x200c: 'zwnj', 0x200d: 'zwj', 0x200e: 'lrm', 0x200f: 'rlm',
  0x2028: 'lsep', 0x2029: 'psep', 0x202a: 'rle', 0x202b: 'lre', 0x202c: 'pdp', 0x202d: 'lro', 0x202e: 'rlo', 0x202f: 'nnbsp',
  0x205f: 'mmsp', 0x2060: 'wj', 0x2061: 'fa', 0x2062: 'x', 0x2063: ',', 0x2064: '+', 0x206A: 'iss', 0x206b: 'ass', 0x206c: 'iafs', 0x206d: 'aafs',
  0x206e: 'nads', 0x206f: 'nods', 0x20: 'sp', 0x7f: 'del', 0x2e3a: '2m', 0x2e3b: '3m', 0xad: 'shy' };
const S = { kind: 'text', chosen: new Set(), into: null, map: null, names: new Map(), shown: [], last: null, q: '', seq: 0, links: null };

const cur = () => { const x = book(); return x && x.files.find(f => f.name === x.cur); };
function menu(){
  const f = cur(), html = f && f.group === 'text' && f.editable, pretty = f && f.editable && ['html', 'css', 'xml'].includes(f.syntax);
  return '<hr><button data-ebm="ebz-split"' + (html ? '' : ' disabled') + '>Split at cursor</button><button data-ebm="ebz-merge">Merge files</button>' +
    '<button data-ebm="ebz-pretty"' + (pretty ? '' : ' disabled') + '>Beautify current file</button><button data-ebm="ebz-prettyall">Beautify all files</button>' +
    '<hr><button data-ebm="ebz-chars"' + (f && f.editable ? '' : ' disabled') + '>Insert special character</button><button data-ebm="ebz-links">Check external links</button>';
}
function fileMenu(name){
  const f = book().files.find(x => x.name === name);
  return f && (f.group === 'text' || f.group === 'styles') ? '<button data-ebm="ebz-merge" data-name="' + esc(name) + '">Merge with…</button>' : '';
}
function run(k, el){
  if (k === 'ebz-split') split();
  else if (k === 'ebz-merge') mergeSheet(el.dataset.name || null);
  else if (k === 'ebz-pretty') beautify(true);
  else if (k === 'ebz-prettyall') beautify(false);
  else if (k === 'ebz-chars') chars();
  else if (k === 'ebz-links') links();
}
const tool = (path, body, label) => ed().busy(label, () => ed().job(ed().post(path, body)));

/* ---------- Split at cursor: before the tag the cursor is in, or the next one ---------- */
async function split(){
  const x = book(), name = x.cur, v = x.view;
  if (!v) return;
  const at = [...v.state.sliceDoc(0, v.state.selection.main.head)].length;      // characters, as the server counts them
  try {
    await ed().flush();
    const r = await tool('/split', { name, at }, 'Splitting…');
    await ed().reload();
    await ed().openFile(r.bottom);
    toast('Split into ' + short(r.bottom));
  } catch(e){ toast(e.message); }
}

/* ---------- Merge files ---------- */
function mergeSheet(first){
  const x = book(), f0 = first && x.files.find(f => f.name === first);
  S.kind = f0 && f0.group === 'styles' ? 'styles' : 'text';
  S.chosen = new Set(first ? [first] : []); S.into = first;
  drawMerge();
}
function drawMerge(){
  const files = book().files.filter(f => f.group === S.kind), chosen = files.filter(f => S.chosen.has(f.name)).map(f => f.name);
  if (!chosen.includes(S.into)) S.into = chosen[0] || null;
  ed().sheet('<h2>Merge files</h2><span class="spacer"></span><button class="btn sm" data-ebx="unsheet">Cancel</button>' +
    '<button class="btn sm primary" data-ebz="merge"' + (chosen.length > 1 ? '' : ' disabled') + '>Merge</button>',
    '<div class="ebzmerge"><div class="ebzseg"><button class="btn sm' + (S.kind === 'text' ? ' on' : '') + '" data-ebz="kind" data-k="text">HTML files</button>' +
    '<button class="btn sm' + (S.kind === 'styles' ? ' on' : '') + '" data-ebz="kind" data-k="styles">CSS files</button></div>' +
    '<div class="ebzfiles">' + files.map(f => '<label class="cvchk"><input type="checkbox" data-ebzpick="' + esc(f.name) + '"' + (S.chosen.has(f.name) ? ' checked' : '') + '>' +
      '<span>' + esc(short(f.name)) + '</span>' + (folder(f.name) ? '<span class="mute tiny">' + esc(folder(f.name)) + '</span>' : '') + '</label>').join('') + '</div>' +
    (chosen.length ? '<div class="berow"><span>Master file</span><div class="bectl"><select class="field" data-ebzinto>' +
      chosen.map(n => '<option value="' + esc(n) + '"' + (n === S.into ? ' selected' : '') + '>' + esc(short(n)) + '</option>').join('') + '</select></div></div>' : '') + '</div>', 'small');
}
async function merge(){
  const names = book().files.filter(f => f.group === S.kind && S.chosen.has(f.name)).map(f => f.name), master = S.into;
  if (names.length < 2 || !master) return;
  ed().unsheet();
  try {
    await ed().flush();
    const r = await tool('/merge', { category: S.kind, names, master }, 'Merging…');
    await ed().reload();
    await ed().openFile(r.master);
    ed().report('Merge files', [names.length + ' files merged into ' + short(r.master)], r.checkpoint);
  } catch(e){ toast(e.message); }
}

/* ---------- Beautify ---------- */
async function beautify(one){
  const name = book().cur;
  try {
    await ed().flush();
    const r = await tool('/beautify', one ? { name } : {}, 'Beautifying…');
    await ed().reload();
    if (one) toast('Beautified'); else ed().report('Beautify all files', ['All files beautified'], r.checkpoint);
  } catch(e){ toast(e.message); }
}

/* ---------- Insert special character ---------- */
const glyph = (cp, n) => NP[cp] ? '<span class="ebznp">' + esc(NP[cp]) + '</span>' : esc(/^COMBINING/.test(n || '') ? '◌' + String.fromCodePoint(cp) : String.fromCodePoint(cp));
const hex = cp => 'U+' + cp.toString(16).toUpperCase().padStart(4, '0');
function grid(list){
  S.shown = list;
  list.forEach(([cp, n]) => S.names.set(cp, n));
  return list.length ? '<div class="ebzgrid">' + list.map(([cp, n]) => '<button class="ebzch" data-ebzc="' + cp + '" title="' + esc(n + ' · ' + hex(cp)) + '" aria-label="' + esc(n) + '">' + glyph(cp, n) + '</button>').join('') + '</div>'
    : '<p class="mute">None</p>';
}
async function chars(){
  if (!S.map) { try { S.map = await api('/api/charmap'); } catch(e){ toast(e.message); return; } }
  S.map.favorites.forEach(([cp, n]) => S.names.set(cp, n));
  S.q = ''; S.last = null;
  const cats = S.map.categories.map(([g, items]) => '<optgroup label="' + esc(g) + '">' + items.map(([n, a, b]) => '<option value="' + a + '-' + b + '">' + esc(n) + '</option>').join('') + '</optgroup>').join('');
  ed().sheet('<h2>Insert special character</h2><span class="spacer"></span><button class="btn sm primary" data-ebx="unsheet">Close</button>',
    '<div class="ebzchars"><div class="ebzcbar"><input class="field" type="search" data-ebzq placeholder="Search" aria-label="Search by name" autocomplete="off" spellcheck="false">' +
    '<select class="field" data-ebzcat aria-label="Category"><option value="fav">Favorites</option>' + (recent.get().length ? '<option value="recent" selected>Recently used</option>' : '') + cats + '</select></div>' +
    '<div class="ebzcgrid" id="ebzcgrid"></div><div class="ebzlast mute tiny" id="ebzlast"></div></div>');
  showCat(recent.get().length ? 'recent' : 'fav');
}
async function showCat(v){
  const box = $('#ebzcgrid'); if (!box) return;
  const n = ++S.seq;
  if (v === 'fav') { box.innerHTML = grid(S.map.favorites); return; }
  if (v === 'recent') { box.innerHTML = grid(recent.get().map(cp => [cp, S.names.get(cp) || hex(cp)])); return; }
  const [a, b] = v.split('-').map(Number);
  box.innerHTML = '<p class="mute">…</p>';
  try { const r = await api('/api/charmap?first=' + a + '&last=' + b); if (n === S.seq && $('#ebzcgrid')) $('#ebzcgrid').innerHTML = grid(r.chars); }
  catch(e){ toast(e.message); }
}
let qTimer = null;
function search(q){
  clearTimeout(qTimer);
  S.q = q.trim();
  if (!S.q) { const c = $('#ebxsheet [data-ebzcat]'); showCat(c ? c.value : 'fav'); return; }
  qTimer = setTimeout(async () => {
    const n = ++S.seq;
    try { const r = await api('/api/charmap?q=' + encodeURIComponent(S.q)); if (n === S.seq && $('#ebzcgrid')) $('#ebzcgrid').innerHTML = grid(r.chars); }
    catch(e){ toast(e.message); }
  }, 250);
}
// At the cursor in the code editor, as Calibre's character map inserts; the sheet stays for more.
function insert(cp){
  const x = book(), v = x && x.view, f = cur();
  if (!v || !f || !f.editable || x.busy) return;
  v.dispatch(v.state.replaceSelection(String.fromCodePoint(cp)), { scrollIntoView: true });
  recent.add(cp);
  const l = $('#ebzlast'); if (l) l.textContent = String.fromCodePoint(cp) + '  ' + (S.names.get(cp) || '') + ' · ' + hex(cp);
}

/* ---------- Check external links ---------- */
const STATUS = { broken: 'Broken', redirected: 'Redirected', skipped: 'Not checked', ok: 'OK' };
async function links(){
  try {
    await ed().flush();
    S.links = await tool('/extlinks', {}, 'Checking links…');
  } catch(e){ toast(e.message); return; }
  drawLinks();
}
function drawLinks(){
  const r = S.links, ls = r.links, count = k => ls.filter(l => l.status === k).length;
  const sum = Object.keys(STATUS).filter(count).map(k => count(k) + ' ' + STATUS[k].toLowerCase()).join(' · ');
  ed().sheet('<h2>External links</h2><span class="spacer"></span><button class="btn sm" data-ebz="relinks">Check again</button><button class="btn sm primary" data-ebx="unsheet">Close</button>',
    '<div class="ebzlinks">' + (ls.length ? '<p class="mute tiny">' + esc(sum) + (r.more ? ' · ' + r.more + ' more not checked' : '') + '</p>' : '<p class="mute">None</p>') +
    ls.map((l, i) => '<div class="ebzlink ' + esc(l.status) + '"><span class="ebzst">' + esc(STATUS[l.status] || l.status) + '</span>' +
      '<span class="ebzhref"><a href="' + esc(l.href) + '" target="_blank" rel="noopener noreferrer">' + esc(l.href) + '</a>' +
      (l.error ? '<span class="mute tiny">' + esc(l.error) + '</span>' : '') + (l.url && l.status !== 'broken' ? '<span class="mute tiny">→ ' + esc(l.url) + '</span>' : '') + '</span>' +
      '<span class="ebzat">' + l.at.map((a, j) => '<button class="btn sm" data-ebzat="' + i + ':' + j + '">' + esc(short(a[0])) + (a[1] ? ':' + a[1] : '') + '</button>').join('') + '</span></div>').join('') + '</div>');
}

/* ---------- events ---------- */
document.addEventListener('click', e => {
  const t = e.target; if (!t.closest || !t.closest('#ebxsheet') || !book()) return;
  const c = t.closest('[data-ebzc]'); if (c) { insert(+c.dataset.ebzc); return; }
  const a = t.closest('[data-ebzat]');
  if (a) { const [i, j] = a.dataset.ebzat.split(':').map(Number), at = S.links.links[i].at[j]; ed().unsheet(); ed().openFile(at[0], { line: at[1] || 1, col: at[2] || 0 }); return; }
  const b = t.closest('[data-ebz]'); if (!b || b.disabled) return;
  const k = b.dataset.ebz;
  if (k === 'kind') { S.kind = b.dataset.k; S.chosen.clear(); S.into = null; drawMerge(); }
  else if (k === 'merge') merge();
  else if (k === 'relinks') { ed().unsheet(); links(); }
});
document.addEventListener('change', e => {
  const t = e.target; if (!t.closest || !t.closest('#ebxsheet') || !book()) return;
  if (t.matches('[data-ebzpick]')) { if (t.checked) S.chosen.add(t.dataset.ebzpick); else S.chosen.delete(t.dataset.ebzpick); drawMerge(); }
  else if (t.matches('[data-ebzinto]')) S.into = t.value;
  else if (t.matches('[data-ebzcat]')) { const q = $('#ebxsheet [data-ebzq]'); if (q) q.value = ''; S.q = ''; showCat(t.value); }
});
document.addEventListener('input', e => {
  const t = e.target; if (t.matches && t.matches('#ebxsheet [data-ebzq]')) search(t.value);
});

C.EbookMore = { menu, fileMenu, run };
})();
