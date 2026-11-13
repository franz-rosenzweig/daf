/* Edit book: the inside of a Calibre book (its HTML, CSS, OPF, NCX, images and fonts), as Calibre's
   own Edit book does it. ebookedit.py keeps a working copy and runs Calibre's tools on it; Calibre's
   book changes only on Save. C.EbookEdit.open(calibreId) opens the editor over the page.
   The code editor is CodeMirror 6 (web/vendor/codemirror), loaded the first time. */
(() => {
'use strict';
const C = window.DafCore, { api, esc, toast, $, $$ } = C;
let CM = null, cmLoading = null;
let X = null;           // the open book: {cid, title, fmt, files, cur, view, states, saved, …}
const GROUPS = [['text', 'Text'], ['styles', 'Styles'], ['images', 'Images'], ['fonts', 'Fonts'], ['other', 'Other']];
const TOOLS = [['subset', 'Subset fonts'], ['compress_images', 'Compress images'], ['remove_unused_css', 'Remove unused CSS'],
  ['smarten_punctuation', 'Smarten punctuation'], ['upgrade_book', 'Upgrade book internals']];
const DOTS = '<svg width="16" height="16" viewBox="0 0 20 20" aria-hidden="true"><circle cx="5" cy="10" r="1.5" fill="currentColor"/><circle cx="10" cy="10" r="1.5" fill="currentColor"/><circle cx="15" cy="10" r="1.5" fill="currentColor"/></svg>';
const base = () => '/api/ebookedit/' + X.cid;
const rawUrl = name => base() + '/raw/' + name.split('/').map(encodeURIComponent).join('/');
const short = name => name.split('/').pop();
const folder = name => name.includes('/') ? name.slice(0, name.lastIndexOf('/')) : '';
const phone = () => matchMedia('(max-width:699px)').matches;
const narrow = () => matchMedia('(max-width:1099px)').matches;
const sleep = ms => new Promise(r => setTimeout(r, ms));
const store = (k, v) => { try { if (v === undefined) return localStorage.getItem('daf.ebx.' + k); localStorage.setItem('daf.ebx.' + k, v); } catch(e){} return null; };

function loadCM(){
  if (CM) return Promise.resolve(CM);
  if (!cmLoading) cmLoading = import('/vendor/codemirror/codemirror.js').then(m => { CM = m; return m; }).catch(e => { cmLoading = null; throw e; });
  return cmLoading;
}
// A Calibre job (calibrewrite.start_job): its answer when it's done.
async function job(p){
  const { job: id } = await p;
  for (let i = 0; ; i++) {
    await sleep(i < 4 ? 300 : 800);
    const j = await api('/api/catalog/jobs/' + id);
    if (!j.running) { if (j.error) throw new Error(j.error); return j.done; }
  }
}
const post = (path, body) => api(base() + path, { method: 'POST', body: JSON.stringify(body || {}) });

/* ---------- opening ---------- */
async function open(cid){
  cid = String(cid).replace(/^cal:/, '');
  if (X) await shut(true);
  let st;
  try { st = await api('/api/ebookedit/' + encodeURIComponent(cid)); } catch(e){ toast(e.message); return; }
  if (!st.copy && !st.formats.length) { toast('No EPUB, AZW3 or KEPUB'); return; }
  X = { cid, title: st.title, fmt: st.copy ? st.copy.fmt : st.formats[0], dafId: st.daf_id, changed: !!(st.copy && st.copy.changed),
        files: [], cur: null, view: null, states: new Map(), saved: new Map(), side: 'files', closed: new Set(), busy: 0,
        showFiles: !narrow(), showPrev: true, pane: 'code', prevName: null, errors: null, found: null };
  frame();
  const cm = loadCM();
  try {
    if (st.copy && st.stale) {
      const a = await choose('Changed in Calibre', [['keep', 'Keep my copy'], ['again', 'Start again']]);
      if (!a) { hide(); return; }
      if (a === 'again') { await api(base(), { method: 'DELETE' }); st.copy = null; }
    }
    if (!st.copy && st.formats.length > 1) {
      const f = await choose(st.title, st.formats.map(x => [x, x]));
      if (!f) { hide(); return; }
      X.fmt = f;
    }
    $('#ebxfmt').textContent = X.fmt;
    if (!st.copy) await busy('Opening…', () => job(post('/open', { fmt: X.fmt })));
    await cm;
    makeView();
    await loadFiles();
    const last = store('file.' + cid), f = X.files.find(x => x.name === last) || X.files.find(x => x.group === 'text' && x.editable) || X.files[0];
    if (f) await openFile(f.name);
    if (X && !X.prevName) { const t = X.files.find(x => x.group === 'text'); if (t) preview(t.name); }
  } catch(e){ toast(e.message); hide(); }
}

/* ---------- the frame ---------- */
function frame(){
  let el = $('#ebx');
  if (!el) {
    document.body.insertAdjacentHTML('beforeend', '<div id="ebx" role="dialog" aria-modal="true" aria-label="Edit book"></div>'); el = $('#ebx');
    el.addEventListener('keydown', e => e.stopPropagation());     // typing here is for the editor, not the page's shortcuts under it
  }
  el.innerHTML = '<div class="ebxhead">' +
      '<button class="btn sm" data-ebx="close">Close</button>' +
      '<div class="ebxtitle"><b>' + esc(X.title) + '</b><span class="mute tiny" id="ebxfmt">' + esc(X.fmt) + '</span></div>' +
      '<span class="ebxbusy mute tiny" id="ebxbusy" hidden></span><span class="spacer"></span>' +
      '<button class="btn sm ebxwide" data-ebx="files">Files</button>' +
      '<button class="btn sm" data-ebx="search">Search</button>' +
      '<button class="btn sm ebxwide" data-ebx="toc">Contents</button>' +
      '<button class="btn sm ebxwide" data-ebx="check">Check</button>' +
      '<button class="btn sm ebxwide" data-ebx="preview">Preview</button>' +
      '<button class="btn sm ib" data-ebx="more" aria-label="More">' + DOTS + '</button>' +
      '<button class="btn sm" data-ebx="save" id="ebxsave">Save</button>' +
    '</div>' +
    '<div class="ebxbody">' +
      '<aside class="ebxside"><div class="ebxsidetabs"><button data-ebx="side" data-side="files">Files</button><button data-ebx="side" data-side="check">Check</button></div><div class="ebxsidebody" id="ebxside"></div></aside>' +
      '<section class="ebxmain"><div class="ebxsearch" id="ebxsearch" hidden></div><div class="ebxfbar" id="ebxfbar"></div>' +
        '<div class="ebxed"><div id="ebxcm"></div><div class="ebxview" id="ebxview" hidden></div></div></section>' +
      '<section class="ebxprev"><iframe id="ebxframe" title="Preview" sandbox="allow-same-origin"></iframe></section>' +
    '</div>' +
    '<nav class="ebxtabs"><button data-ebx="pane" data-pane="files">Files</button><button data-ebx="pane" data-pane="code">Code</button><button data-ebx="pane" data-pane="prev">Preview</button></nav>' +
    '<input type="file" id="ebxadd" hidden>';
  el.hidden = false;
  document.body.classList.add('ebxopen');
  $('#ebxframe').addEventListener('load', () => { const f = $('#ebxframe'); try { if (X && X.prevY) f.contentWindow.scrollTo(0, X.prevY); } catch(e){} });
  layout();
  side();
}
function layout(){
  const el = $('#ebx'); if (!el || !X) return;
  el.classList.toggle('nofiles', !X.showFiles);
  el.classList.toggle('noprev', !X.showPrev);
  el.dataset.pane = X.pane;
  $$('[data-ebx="pane"]', el).forEach(b => b.classList.toggle('on', b.dataset.pane === X.pane));
  $$('[data-ebx="side"]', el).forEach(b => b.classList.toggle('on', b.dataset.side === X.side));
  const fb = $('[data-ebx="files"]', el); if (fb) fb.classList.toggle('on', X.showFiles);
  const pb = $('[data-ebx="preview"]', el); if (pb) pb.classList.toggle('on', X.showPrev);
  const sb = $('[data-ebx="search"]', el); if (sb) sb.classList.toggle('on', !$('#ebxsearch').hidden);
  const sv = $('#ebxsave'); if (sv) sv.classList.toggle('primary', !!X.changed);
  if (X.view) X.view.requestMeasure();
}
function hide(){
  const el = $('#ebx'); if (el) { el.hidden = true; el.innerHTML = ''; el.className = ''; }
  document.body.classList.remove('ebxopen');
  if (X && X.view) X.view.destroy();
  X = null;
}
// Close: what's typed is saved into the copy; a copy without changes goes, one with changes stays.
async function shut(quiet){
  if (!X) return;
  const cid = X.cid;
  try { await flush(); } catch(e){}
  hide();
  try { const r = await api('/api/ebookedit/' + cid + '/close', { method: 'POST' }); if (r.kept && !quiet) toast('Changes kept for next time'); } catch(e){}
}
async function busy(label, fn){
  X.busy++;
  const b = $('#ebxbusy'); if (b) { b.textContent = label; b.hidden = false; }
  $('#ebx').classList.add('busy');
  readOnly(true);
  try { return await fn(); }
  finally {
    if (X) { X.busy--; if (!X.busy) { const bb = $('#ebxbusy'); if (bb) bb.hidden = true; $('#ebx').classList.remove('busy'); readOnly(false); } }
  }
}

/* ---------- the code editor ---------- */
let HL = null, THEME = null, setMatches = null, matchField = null, MARK = null, CUR = null;
function cmSetup(){
  if (HL) return;
  const T = CM.tags;
  HL = CM.HighlightStyle.define([
    { tag: [T.tagName], color: 'var(--accent-2)', fontWeight: '600' },
    { tag: [T.angleBracket, T.punctuation, T.separator, T.bracket], color: 'var(--fg-3)' },
    { tag: [T.attributeName, T.propertyName], color: 'var(--accent)' },
    { tag: [T.attributeValue, T.string], color: 'var(--ok)' },
    { tag: [T.comment, T.processingInstruction, T.documentMeta], color: 'var(--fg-3)', fontStyle: 'italic' },
    { tag: [T.number, T.unit, T.color, T.atom, T.bool], color: 'var(--bad)' },
    { tag: [T.keyword, T.modifier, T.definitionKeyword, T.controlKeyword, T.operatorKeyword], color: 'color-mix(in srgb, var(--bad) 65%, var(--accent))' },
    { tag: [T.className, T.labelName, T.constant(T.name)], color: 'color-mix(in srgb, var(--ok) 55%, var(--accent))' },
    { tag: [T.character, T.escape], color: 'color-mix(in srgb, var(--bad) 60%, var(--fg))' },
    { tag: T.invalid, color: 'var(--bad)', textDecoration: 'underline wavy' },
  ]);
  THEME = CM.EditorView.theme({
    '&': { height: '100%', fontSize: '14px', color: 'var(--fg)', backgroundColor: 'var(--bg)' },
    '.cm-scroller': { fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Consolas, "Liberation Mono", monospace', lineHeight: '1.6' },
    '.cm-content': { caretColor: 'var(--fg)', paddingBottom: '40vh' },
    '.cm-gutters': { backgroundColor: 'var(--panel)', color: 'var(--fg-3)', borderRight: '1px solid var(--line)' },
    '.cm-activeLine': { backgroundColor: 'color-mix(in srgb, var(--accent) 6%, transparent)' },
    '.cm-activeLineGutter': { backgroundColor: 'var(--hover)', color: 'var(--fg-2)' },
    '&.cm-focused > .cm-scroller > .cm-selectionLayer .cm-selectionBackground, .cm-selectionLayer .cm-selectionBackground, .cm-content ::selection': { backgroundColor: 'color-mix(in srgb, var(--accent) 28%, transparent)' },
    '.cm-cursor, .cm-dropCursor': { borderLeftColor: 'var(--fg)' },
    '.cm-ebxmatch': { backgroundColor: 'var(--hl)', borderRadius: '2px' },
    '.cm-selectionMatch': { backgroundColor: 'color-mix(in srgb, var(--accent) 12%, transparent)' },
    '&.cm-focused .cm-matchingBracket': { backgroundColor: 'color-mix(in srgb, var(--ok) 25%, transparent)', outline: 'none' },
    '.cm-tooltip': { backgroundColor: 'var(--bg)', border: '1px solid var(--line)', color: 'var(--fg)', borderRadius: '8px', boxShadow: 'var(--shadow)' },
    '.cm-tooltip-autocomplete > ul > li': { padding: '4px 8px' },
    '.cm-tooltip-autocomplete > ul > li[aria-selected]': { backgroundColor: 'var(--accent-weak)', color: 'var(--fg)' },
    '.cm-foldPlaceholder': { backgroundColor: 'var(--hover)', border: '1px solid var(--line)', color: 'var(--fg-2)' },
    '.cm-gutterElement': { padding: '0 6px 0 8px' },
  });
  MARK = CM.Decoration.mark({ class: 'cm-ebxmatch' });
  CUR = CM.Decoration.mark({ class: 'cm-ebxmatch now' });
  setMatches = CM.StateEffect.define();
  matchField = CM.StateField.define({
    create: () => CM.Decoration.none,
    update(deco, tr){ deco = deco.map(tr.changes); for (const e of tr.effects) if (e.is(setMatches)) deco = e.value; return deco; },
    provide: f => CM.EditorView.decorations.from(f),
  });
}
function langOf(syntax){
  if (syntax === 'html') return CM.html({ matchClosingTags: true, autoCloseTags: true });
  if (syntax === 'css') return CM.css();
  if (syntax === 'xml') return CM.xml();
  return [];
}
function newState(text, syntax){
  return CM.EditorState.create({ doc: text, extensions: [
    CM.lineNumbers(), CM.highlightActiveLineGutter(), CM.highlightSpecialChars(), CM.history(), CM.foldGutter(), CM.drawSelection(), CM.dropCursor(),
    CM.EditorState.allowMultipleSelections.of(true), CM.indentOnInput(), CM.syntaxHighlighting(HL), CM.bracketMatching(), CM.closeBrackets(),
    CM.autocompletion(), CM.rectangularSelection(), CM.crosshairCursor(), CM.highlightActiveLine(), CM.highlightSelectionMatches(),
    CM.keymap.of([...CM.closeBracketsKeymap, ...CM.defaultKeymap, ...CM.historyKeymap, ...CM.foldKeymap, ...CM.completionKeymap, CM.indentWithTab]),
    CM.EditorView.lineWrapping, THEME, matchField, langOf(syntax), X.ro.of(CM.EditorState.readOnly.of(!!X.busy)),
    CM.EditorView.updateListener.of(u => { if (u.docChanged) typed(); }),
  ] });
}
function makeView(){
  cmSetup();
  X.ro = new CM.Compartment();
  X.view = new CM.EditorView({ parent: $('#ebxcm'), state: newState('', null) });
}
function readOnly(on){
  if (X && X.view && X.ro) X.view.dispatch({ effects: X.ro.reconfigure(CM.EditorState.readOnly.of(on)) });
}
// The editor's text, made the same as `text` with the smallest change (so undo and the place stay).
function setDoc(text){
  const v = X.view, old = v.state.doc.toString();
  if (old === text) return;
  let a = 0; const n = Math.min(old.length, text.length);
  while (a < n && old.charCodeAt(a) === text.charCodeAt(a)) a++;
  let b = 0;
  while (b < n - a && old.charCodeAt(old.length - 1 - b) === text.charCodeAt(text.length - 1 - b)) b++;
  X.quiet = true;
  v.dispatch({ changes: { from: a, to: old.length - b, insert: text.slice(a, text.length - b) } });
  X.quiet = false;
}
function typed(){
  if (X.quiet) return;
  clearTimeout(X.timer);
  X.timer = setTimeout(() => flush().catch(e => toast(e.message)), 700);
  X.found = null;
}
// What's typed goes into the working copy (a moment after the typing stops, and before anything else).
async function flush(){
  if (!X || !X.view || !X.cur) return;
  clearTimeout(X.timer);
  while (X.flushing) await X.flushing;
  const name = X.cur, f = X.files.find(x => x.name === name);
  if (!f || !f.editable) return;
  const text = X.view.state.doc.toString();
  if (text === X.saved.get(name)) return;
  X.flushing = api(base() + '/text', { method: 'PUT', body: JSON.stringify({ name, text }) })
    .then(r => { if (!X) return; X.saved.set(name, text); if (r.changed) { X.changed = true; layout(); } refreshPreview(); })
    .finally(() => { if (X) X.flushing = null; });
  return X.flushing;
}

/* ---------- files ---------- */
async function loadFiles(){
  const r = await api(base() + '/files');
  X.files = r.files; X.opf = r.opf; X.checkpoints = r.checkpoints || [];
  if (r.meta) { X.changed = !!r.meta.changed; layout(); }
  for (const k of [...X.states.keys()]) if (!X.files.some(f => f.name === k)) { X.states.delete(k); X.saved.delete(k); }
  side();
}
function side(){
  const box = $('#ebxside'); if (!box || !X) return;
  layout();
  if (X.side === 'check') { box.innerHTML = checkHTML(); return; }
  if (!X.files.length) { box.innerHTML = '<p class="mute ebxempty">Opening…</p>'; return; }
  box.innerHTML = GROUPS.map(([g, label]) => {
    const fs = X.files.filter(f => f.group === g);
    if (!fs.length) return '';
    const shut = X.closed.has(g);
    return '<div class="ebxgroup"><button class="ebxgh' + (shut ? ' shut' : '') + '" data-ebx="group" data-g="' + g + '"><span>' + label + '</span><span class="mute">' + fs.length + '</span></button>' +
      (shut ? '' : fs.map(f => '<div class="ebxrow' + (f.name === X.cur ? ' on' : '') + '"><button class="ebxf" data-ebxf="' + esc(f.name) + '" title="' + esc(f.name) + '">' +
        '<span class="ebxfn">' + esc(short(f.name)) + '</span>' + (folder(f.name) ? '<span class="ebxfd">' + esc(folder(f.name)) + '</span>' : '') + '</button>' +
        (f.name === 'META-INF/container.xml' ? '' : '<button class="ib" data-ebx="fmenu" data-name="' + esc(f.name) + '" aria-label="More for ' + esc(short(f.name)) + '">' + DOTS + '</button>') + '</div>').join('')) + '</div>';
  }).join('') + '<div class="ebxsidefoot"><button class="btn sm" data-ebx="add">Add a file</button></div>';
  const on = $('.ebxrow.on', box); if (on && on.scrollIntoViewIfNeeded) on.scrollIntoViewIfNeeded(false);
}
async function openFile(name, at){
  try { await showFile(name, at); } catch(e){ toast(e.message); }
}
async function showFile(name, at){
  const f = X.files.find(x => x.name === name); if (!f) return;
  if (name !== X.cur) {
    await flush();
    let st = null;
    if (f.editable) {
      st = X.states.get(name);
      if (!st) { const r = await api(base() + '/text?name=' + encodeURIComponent(name)); if (!X) return; st = newState(r.text, f.syntax); X.saved.set(name, r.text); }
      await flush();                    // anything typed in the file before, while this one came
    }
    if (!X) return;
    const was = X.files.find(x => x.name === X.cur);
    if (was && was.editable && X.view) X.states.set(X.cur, X.view.state);
    X.cur = name;
    store('file.' + X.cid, name);
    const fb = $('#ebxfbar'); if (fb) fb.innerHTML = '<span>' + esc(short(name)) + '</span>' + (folder(name) ? '<span class="mute">' + esc(folder(name)) + '</span>' : '');
    const view = $('#ebxview'), cm = $('#ebxcm');
    if (st) {
      X.view.setState(st);
      readOnly(!!X.busy);
      view.hidden = true; cm.hidden = false;
    } else {
      cm.hidden = true; view.hidden = false;
      view.innerHTML = f.group === 'images' ? '<div class="ebximg"><img src="' + esc(rawUrl(name)) + '?t=' + Date.now() + '" alt=""><span class="mute tiny" id="ebximgsize">' + esc(size(f.size)) + '</span></div>'
        : '<div class="ebxnone"><b>' + esc(short(name)) + '</b><span class="mute tiny">' + esc(f.type) + ' · ' + esc(size(f.size)) + '</span></div>';
      const im = $('img', view); if (im) im.onload = () => { const s = $('#ebximgsize'); if (s) s.textContent = im.naturalWidth + ' × ' + im.naturalHeight + ' · ' + size(f.size); };
    }
    side();
    if (f.group === 'text') preview(name);
  }
  if (phone() && X.pane !== 'code') { X.pane = 'code'; layout(); }
  if (narrow() && !phone() && X.showFiles && X.side === 'files') { X.showFiles = false; layout(); }
  if (at && f.editable) goTo(at);
  else if (f.editable) showMatches();
}
const size = n => n >= 1048576 ? (n / 1048576).toFixed(1) + ' MB' : n >= 1024 ? Math.round(n / 1024) + ' KB' : n + ' bytes';
// at: {line, col} (Check book) or {from, to} (a match)
function goTo(at){
  const v = X.view, doc = v.state.doc;
  let from, to;
  if (at.line != null) { const l = doc.line(Math.max(1, Math.min(at.line, doc.lines))); from = to = l.from + Math.max(0, Math.min(at.col || 0, l.length)); }
  else { from = Math.min(at.from, doc.length); to = Math.min(at.to, doc.length); }
  v.dispatch({ selection: { anchor: from, head: to }, effects: CM.EditorView.scrollIntoView(from, { y: 'center' }) });
  showMatches();
}

/* ---------- preview ---------- */
function preview(name){
  const f = $('#ebxframe'); if (!f) return;
  if (X.prevName === name) return refreshPreview();
  X.prevName = name; X.prevY = 0;
  f.src = rawUrl(name);
}
function refreshPreview(){
  const f = $('#ebxframe'); if (!f || !X || !X.prevName) return;
  try { X.prevY = f.contentWindow.scrollY; f.contentWindow.location.reload(); }
  catch(e){ f.src = rawUrl(X.prevName); }
}

/* ---------- the menus ---------- */
function pop(anchor, html){
  let p = $('#ebxpop');
  if (!p) { $('#ebx').insertAdjacentHTML('beforeend', '<div class="pop ebxpop" id="ebxpop" hidden></div>'); p = $('#ebxpop'); }
  p.innerHTML = '<div class="menu">' + html + '</div>'; p.hidden = false;
  const r = anchor.getBoundingClientRect();
  p.style.left = Math.max(8, Math.min(innerWidth - p.offsetWidth - 8, r.right - p.offsetWidth)) + 'px';
  p.style.top = Math.max(8, Math.min(r.bottom + 6, innerHeight - p.offsetHeight - 8)) + 'px';
}
const unpop = () => { const p = $('#ebxpop'); if (p) p.hidden = true; };
function moreMenu(anchor){
  pop(anchor, (phone() ? '<button data-ebm="toc">Contents</button><button data-ebm="check">Check book</button><hr>' : '') +
    TOOLS.map(([k, label]) => '<button data-ebm="tool" data-tool="' + k + '">' + label + '</button>').join('') +
    '<hr><button data-ebm="add">Add a file</button><button data-ebm="cps"' + (X.checkpoints.length ? '' : ' disabled') + '>Checkpoints</button>' +
    '<hr><button data-ebm="discard"' + (X.changed ? '' : ' disabled') + '>Discard changes</button>');
}
function fileMenu(anchor, name){
  pop(anchor, '<button data-ebm="rename" data-name="' + esc(name) + '">Rename</button>' + (name === X.opf ? '' : '<button data-ebm="remove" data-name="' + esc(name) + '">Remove</button>'));
}

/* ---------- sheets (the Contents, a tool's report, checkpoints, a choice) ---------- */
function sheet(head, body, cls){
  let s = $('#ebxsheet');
  if (!s) { $('#ebx').insertAdjacentHTML('beforeend', '<div class="beshade" id="ebxshade"></div><div class="besheet ebxsheet" id="ebxsheet" role="dialog" aria-modal="true"></div>'); s = $('#ebxsheet'); }
  s.className = 'besheet ebxsheet' + (cls ? ' ' + cls : '');
  s.innerHTML = '<div class="behead">' + head + '</div><div class="ebxsbody">' + body + '</div>';
  s.hidden = false; $('#ebxshade').hidden = false;
  return s;
}
function unsheet(){ const s = $('#ebxsheet'); if (s) { s.hidden = true; s.innerHTML = ''; } const d = $('#ebxshade'); if (d) d.hidden = true; if (X) X.toc = null; }
let chosen = null;
function choose(title, options){
  return new Promise(ok => {
    chosen = ok;
    sheet('<h2>' + esc(title) + '</h2><span class="spacer"></span><button class="btn sm" data-ebchoose="">Cancel</button>',
      '<div class="ebxchoose">' + options.map(([k, label]) => '<button class="btn" data-ebchoose="' + esc(k) + '">' + esc(label) + '</button>').join('') + '</div>', 'small');
  });
}
function report(label, lines, n){
  const ls = (lines || []).map(l => l.replace(/^\s*#+\s*/, '').trim()).filter(Boolean);
  sheet('<h2>' + esc(label) + '</h2><span class="spacer"></span>' + (n ? '<button class="btn sm" data-ebx="restore" data-n="' + n + '">Undo</button>' : '') + '<button class="btn sm primary" data-ebx="unsheet">Close</button>',
    '<div class="ebxreport">' + ls.map(l => '<p>' + esc(l) + '</p>').join('') + '</div>', 'small');
}
function cpsSheet(){
  sheet('<h2>Checkpoints</h2><span class="spacer"></span><button class="btn sm primary" data-ebx="unsheet">Close</button>',
    X.checkpoints.length ? '<div class="ebxcps">' + X.checkpoints.map(c => '<div class="ebxcp"><span>Before ' + esc(c.label) + '</span><span class="mute tiny">' + esc(when(c.at)) + '</span><span class="spacer"></span><button class="btn sm" data-ebx="restore" data-n="' + c.n + '">Go back</button></div>').join('') + '</div>' : '<p class="mute">None</p>', 'small');
}
const when = at => { const d = new Date(at * 1000); return d.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' }) + (Date.now() - d > 864e5 ? ' · ' + d.toLocaleDateString() : ''); };

/* ---------- Calibre's tools ---------- */
async function calibre(op, args, label){
  await flush();
  return busy(label || 'Working…', () => job(post('/calibre', Object.assign({ op }, args || {}))));
}
// After a tool changed files: the list, the open file's text and the preview again.
async function reload(){
  await loadFiles();
  for (const k of [...X.states.keys()]) if (k !== X.cur) { X.states.delete(k); X.saved.delete(k); }
  const f = X.files.find(x => x.name === X.cur);
  if (!f) { X.cur = null; const t = X.files.find(x => x.group === 'text' && x.editable); if (t) await openFile(t.name); return; }
  if (f.editable) {
    const r = await api(base() + '/text?name=' + encodeURIComponent(X.cur));
    X.saved.set(X.cur, r.text); setDoc(r.text);
  }
  if (X.prevName && !X.files.some(x => x.name === X.prevName)) X.prevName = null;
  if (X.prevName) refreshPreview();
  X.changed = true; layout();
}
async function runTool(k){
  const label = (TOOLS.find(t => t[0] === k) || [k, k])[1];
  try {
    const r = await calibre('polish', { tool: k }, label + '…');
    if (r.changed) await reload();
    const cp = r.changed && X.checkpoints[0] && X.checkpoints[0].label === label ? X.checkpoints[0].n : null;
    report(label, r.report, cp);
  } catch(e){ toast(e.message); }
}
async function restore(n){
  const c = X.checkpoints.find(x => String(x.n) === String(n));
  if (!confirm('Go back to before ' + (c ? c.label : 'this') + '?')) return;
  unsheet();
  try { await flush(); await busy('Going back…', () => post('/checkpoints/' + n)); await reload(); toast('Back to before ' + (c ? c.label : 'it')); }
  catch(e){ toast(e.message); }
}

/* ---------- Check book ---------- */
const LEVELS = [['error', 'Errors'], ['warning', 'Warnings'], ['info', 'Information']];
function checkHTML(){
  const es = X.errors;
  const bar = '<div class="ebxchkbar"><button class="btn sm" data-ebx="recheck">' + (es ? 'Check again' : 'Check book') + '</button>' +
    (es && es.some(e => e.fixable) ? '<button class="btn sm" data-ebx="fix">Fix all</button>' : '') + '</div>';
  if (!es) return bar;
  if (!es.length) return bar + '<p class="mute ebxempty">No problems found</p>';
  return bar + LEVELS.map(([lv, label]) => {
    const list = es.map((e, i) => [e, i]).filter(([e]) => e.level === lv);
    if (!list.length) return '';
    return '<div class="ebxgroup"><div class="ebxgh static"><span>' + label + '</span><span class="mute">' + list.length + '</span></div>' +
      list.map(([e, i]) => '<button class="ebxerr ' + lv + (X.errAt === i ? ' on' : '') + '" data-ebxerr="' + i + '"><span>' + esc(e.msg) + '</span>' +
        (e.name ? '<span class="mute tiny">' + esc(short(e.name)) + (e.line ? ' · ' + e.line : '') + '</span>' : '') +
        (X.errAt === i && e.help ? '<span class="ebxhelp">' + esc(e.help) + '</span>' : '') + '</button>').join('') + '</div>';
  }).join('');
}
async function check(fix){
  X.side = 'check';
  if (phone()) X.pane = 'files'; else X.showFiles = true;
  X.errAt = null; side();
  try { X.errors = (await calibre(fix ? 'fix' : 'check', {}, fix ? 'Fixing…' : 'Checking…')).errors; if (fix) await reload(); }
  catch(e){ toast(e.message); }
  side();
}
// The Check list: shown again as it was, or run the first time
function showCheck(){
  const shown = X.side === 'check' && (phone() ? X.pane === 'files' : X.showFiles);
  if (!X.errors || shown) return check();
  X.side = 'check';
  if (phone()) X.pane = 'files'; else X.showFiles = true;
  side();
}
function openError(i){
  const e = X.errors[i]; if (!e) return;
  X.errAt = i; side();
  if (narrow() && !phone() && X.showFiles) { X.showFiles = false; layout(); }
  if (e.name && X.files.some(f => f.name === e.name)) openFile(e.name, e.line ? { line: e.line, col: e.col } : null);
}

/* ---------- find and replace ---------- */
function searchOpen(){
  const s = $('#ebxsearch'); if (!s) return;
  const sel = X.view ? X.view.state.sliceDoc(X.view.state.selection.main.from, X.view.state.selection.main.to) : '';
  if (s.hidden) {
    const q = X.q || { find: '', replace: '', where: 'file', regex: false, case: false };
    s.innerHTML = '<div class="ebxsrow"><input class="field" id="ebxfind" placeholder="Find" autocomplete="off" autocapitalize="off" spellcheck="false" value="' + esc(sel && !sel.includes('\n') ? sel : q.find) + '">' +
      '<input class="field" id="ebxrep" placeholder="Replace" autocomplete="off" autocapitalize="off" spellcheck="false" value="' + esc(q.replace) + '"></div>' +
      '<div class="ebxsrow"><select class="field" id="ebxwhere">' + [['file', 'Current file'], ['text', 'All text files'], ['styles', 'All styles']].map(([k, l]) => '<option value="' + k + '"' + (q.where === k ? ' selected' : '') + '>' + l + '</option>').join('') + '</select>' +
      '<label class="ebxck"><input type="checkbox" id="ebxre"' + (q.regex ? ' checked' : '') + '> Regex</label><label class="ebxck"><input type="checkbox" id="ebxcase"' + (q.case ? ' checked' : '') + '> Match case</label>' +
      '<span class="mute tiny ebxcount" id="ebxcount"></span><span class="spacer"></span>' +
      '<button class="btn sm" data-ebx="find">Find</button><button class="btn sm" data-ebx="rep">Replace</button><button class="btn sm" data-ebx="repall">Replace all</button><button class="btn sm" data-ebx="count">Count</button>' +
      '<button class="btn sm ib" data-ebx="search" aria-label="Close search">×</button></div>';
    s.hidden = false;
  } else if (sel && !sel.includes('\n')) $('#ebxfind').value = sel;
  layout();
  if (phone() && X.pane !== 'code') { X.pane = 'code'; layout(); }
  const f = $('#ebxfind'); f.focus(); f.select();
}
function query(){
  const q = { find: $('#ebxfind').value, replace: $('#ebxrep').value, where: $('#ebxwhere').value, regex: $('#ebxre').checked, case: $('#ebxcase').checked };
  X.q = q;
  return Object.assign({ name: X.cur }, q);
}
const count = t => { const c = $('#ebxcount'); if (c) c.textContent = t; };
function showMatches(){
  if (!X || !X.view || !matchField) return;
  const doc = X.view.state.doc.length, b = new CM.RangeSetBuilder();
  const sel = X.view.state.selection.main;
  ((X.found && X.found.matches) || []).filter(m => m.name === X.cur && m.end > m.start && m.end <= doc).forEach(m => b.add(m.start, m.end, m.start === sel.from && m.end === sel.to ? CUR : MARK));
  X.view.dispatch({ effects: setMatches.of(b.finish()) });
}
async function findAll(){
  const q = query();
  if (!q.find) return null;
  if (q.where === 'file' && !(X.files.find(f => f.name === X.cur) || {}).editable) { toast('No text file open'); return null; }
  await flush();
  X.found = await post('/find', q);
  return X.found;
}
async function findNext(back){
  let r;
  try { r = await findAll(); } catch(e){ toast(e.message); return; }
  if (!r) return;
  const ms = r.matches;
  if (!ms.length) { count('No matches'); showMatches(); return; }
  const order = X.files.map(f => f.name), fi = n => order.indexOf(n), cur = fi(X.cur), sel = X.view.state.selection.main;
  let i;
  if (!back) {
    i = ms.findIndex(m => fi(m.name) > cur || (m.name === X.cur && m.start >= sel.to && (m.start > sel.from || sel.empty)));
    if (i < 0) i = 0;
  } else {
    for (i = ms.length - 1; i >= 0; i--) { const m = ms[i]; if (fi(m.name) < cur || (m.name === X.cur && m.end <= sel.from && m.start < sel.from)) break; }
    if (i < 0) i = ms.length - 1;
  }
  const m = ms[i];
  count((i + 1) + ' of ' + r.total + (Object.keys(r.files).length > 1 ? ' · ' + short(m.name) : ''));
  if (m.name !== X.cur) await openFile(m.name, { from: m.start, to: m.end });
  else goTo({ from: m.start, to: m.end });
}
async function replaceOne(){
  const q = query(), sel = X.view.state.selection.main;
  const hit = X.found && X.found.matches.find(m => m.name === X.cur && m.start === sel.from && m.end === sel.to);
  if (!hit) return findNext();
  try {
    const r = await post('/replace', Object.assign(q, { at: hit.start }));
    if (r.change) {
      X.quiet = true;
      X.view.dispatch({ changes: { from: r.change.from, to: r.change.to, insert: r.change.insert }, selection: { anchor: r.change.from + r.change.insert.length } });
      X.quiet = false;
      X.saved.set(X.cur, X.view.state.doc.toString());
      X.changed = true; layout(); refreshPreview();
    }
    await findNext();
  } catch(e){ toast(e.message); }
}
async function replaceAll(){
  const q = query(); if (!q.find) return;
  if (q.where === 'file' && !(X.files.find(f => f.name === X.cur) || {}).editable) { toast('No text file open'); return; }
  try {
    await flush();
    const r = await post('/replace', q);
    const n = Object.keys(r.files).length;
    count(r.total ? r.total + ' replaced' + (n > 1 ? ' in ' + n + ' files' : '') : 'No matches');
    if (r.total) {
      if (r.files[X.cur]) { const t = await api(base() + '/text?name=' + encodeURIComponent(X.cur)); X.saved.set(X.cur, t.text); setDoc(t.text); }
      for (const k of Object.keys(r.files)) if (k !== X.cur) { X.states.delete(k); X.saved.delete(k); }
      X.found = null; showMatches();
      X.changed = true; await loadFiles(); refreshPreview();
    }
  } catch(e){ toast(e.message); }
}
async function countAll(){
  try {
    const r = await findAll(); if (!r) return;
    const n = Object.keys(r.files).length;
    count(r.total ? r.total + (n > 1 ? ' in ' + n + ' files' : '') : 'No matches');
    showMatches();
  } catch(e){ toast(e.message); }
}

/* ---------- the Table of Contents ---------- */
// Edited as a flat list with depths; nested again on Save.
function flat(items, d, out){ (items || []).forEach(it => { out.push({ title: it.title, dest: it.dest, frag: it.frag, missing: it.missing, d }); flat(it.children, d + 1, out); }); return out; }
function nest(list){
  const root = { children: [] }, stack = [root];
  list.forEach(it => {
    const node = { title: it.title, dest: it.dest, frag: it.frag || null, children: [] };
    const d = Math.min(it.d, stack.length - 1);
    stack.length = d + 1;
    stack[d].children.push(node);
    stack.push(node);
  });
  return root.children;
}
async function tocOpen(){
  try {
    const r = await calibre('toc', {}, 'Contents…');
    X.toc = { list: flat(r.toc, 0, []), at: null, title: r.title };
    tocDraw();
  } catch(e){ toast(e.message); }
}
const textFiles = () => X.files.filter(f => f.group === 'text');
function tocDraw(){
  const T = X.toc, s = $('#ebxsheet');
  const keepScroll = s && !s.hidden ? ($('.ebxsbody', s) || {}).scrollTop : 0;
  const rows = T.list.map((it, i) => '<div class="ebxtr' + (T.at === i ? ' on' : '') + '" data-ebtr="' + i + '" style="--d:' + it.d + '">' +
    '<input class="field" data-ebtt="' + i + '" value="' + esc(it.title) + '" aria-label="Title">' +
    '<button class="ebxtd' + (it.missing ? ' bad' : '') + '" data-ebt="place" data-i="' + i + '">' + esc(it.dest ? short(it.dest) + (it.frag ? '#' + it.frag : '') : 'No place') + '</button></div>').join('');
  const sel = T.at != null;
  sheet('<h2>Contents</h2><span class="spacer"></span><button class="btn sm" data-ebt="gen">Generate</button><button class="btn sm" data-ebt="cancel">Cancel</button><button class="btn sm primary" data-ebt="save">Save</button>',
    '<div class="ebxtoc">' + (rows || '<p class="mute">Empty</p>') + '</div>', 'tocs');
  $('#ebxsheet').insertAdjacentHTML('beforeend', '<div class="ebxtbar">' +
    '<button class="btn sm" data-ebt="up"' + (sel ? '' : ' disabled') + ' aria-label="Up">↑</button><button class="btn sm" data-ebt="down"' + (sel ? '' : ' disabled') + ' aria-label="Down">↓</button>' +
    '<button class="btn sm" data-ebt="out"' + (sel ? '' : ' disabled') + ' aria-label="Out">←</button><button class="btn sm" data-ebt="in"' + (sel ? '' : ' disabled') + ' aria-label="In">→</button>' +
    '<button class="btn sm danger" data-ebt="del"' + (sel ? '' : ' disabled') + '>Remove</button><span class="spacer"></span><button class="btn sm" data-ebt="add">Add</button></div>');
  const b = $('#ebxsheet .ebxsbody'); if (b) b.scrollTop = keepScroll || 0;
}
// An entry and the ones under it: [first, last+1)
function block(list, i){ let j = i + 1; while (j < list.length && list[j].d > list[i].d) j++; return [i, j]; }
function tocMove(k){
  const T = X.toc, L = T.list, i = T.at; if (i == null) return;
  const [a, z] = block(L, i), d = L[i].d;
  if (k === 'del') { L.splice(a, z - a); T.at = L.length ? Math.min(a, L.length - 1) : null; }
  else if (k === 'in') { if (i > 0 && L[i - 1].d >= d) for (let j = a; j < z; j++) L[j].d++; }
  else if (k === 'out') { if (d > 0) for (let j = a; j < z; j++) L[j].d--; }
  else if (k === 'up') {
    let p = i - 1; while (p >= 0 && L[p].d > d) p--;
    if (p >= 0 && L[p].d === d) { const blk = L.splice(a, z - a); L.splice(p, 0, ...blk); T.at = p; }
  } else if (k === 'down') {
    if (z < L.length && L[z].d === d) { const [, z2] = block(L, z); const nxt = L.splice(z, z2 - z); L.splice(a, 0, ...nxt); T.at = a + nxt.length; }
  }
  tocDraw();
}
async function tocPlace(i, adding){
  const T = X.toc;
  const it = adding ? null : T.list[i], cur = it && it.dest ? it.dest : (X.cur && X.files.some(f => f.name === X.cur && f.group === 'text') ? X.cur : (textFiles()[0] || {}).name);
  T.placing = { i, adding };
  const s = sheet('<h2>' + (adding ? 'Add' : 'Place') + '</h2><span class="spacer"></span><button class="btn sm" data-ebt="back">Back</button>',
    '<div class="ebxplace"><select class="field" id="ebxpfile">' + textFiles().map(f => '<option value="' + esc(f.name) + '"' + (f.name === cur ? ' selected' : '') + '>' + esc(f.name) + '</option>').join('') + '</select>' +
    (adding ? '<input class="field" id="ebxptitle" placeholder="Title">' : '') + '<div class="ebxids" id="ebxids"></div></div>', 'tocs');
  await placeIds(cur, it && it.dest === cur ? it.frag : null);
  return s;
}
async function placeIds(name, frag){
  const box = $('#ebxids'); if (!box || !name) return;
  box.innerHTML = '<p class="mute">…</p>';
  let ids = [];
  try { ids = (await api(base() + '/ids?name=' + encodeURIComponent(name))).ids; } catch(e){ toast(e.message); }
  if (!$('#ebxids')) return;
  box.innerHTML = '<button class="ebxid' + (!frag ? ' on' : '') + '" data-ebt="pick" data-frag=""><b>Top</b></button>' +
    ids.map(x => '<button class="ebxid' + (x.id === frag ? ' on' : '') + '" data-ebt="pick" data-frag="' + esc(x.id) + '" data-text="' + esc(x.text) + '"><b>' + esc(x.tag) + ' #' + esc(x.id) + '</b><span class="mute tiny">' + esc(x.text) + '</span></button>').join('');
}
function tocPick(frag, text){
  const T = X.toc, P = T.placing, dest = $('#ebxpfile').value;
  if (P.adding) {
    const title = ($('#ebxptitle').value || '').trim() || text || short(dest);
    const L = T.list;
    let at = L.length, d = 0;
    if (T.at != null) { at = block(L, T.at)[1]; d = L[T.at].d; }
    L.splice(at, 0, { title, dest, frag: frag || null, d });
    T.at = at;
  } else Object.assign(T.list[P.i], { dest, frag: frag || null, missing: false });
  T.placing = null;
  tocDraw();
}
async function tocGenerate(anchor){
  pop(anchor, '<button data-ebm="gen" data-kind="major">From major headings</button><button data-ebm="gen" data-kind="all">From all headings</button><button data-ebm="gen" data-kind="files">From files</button>');
}
async function tocGen(kind){
  try {
    const r = await calibre('toc_generate', { kind }, 'Contents…');
    if (!r.toc.length) { toast('Nothing found'); return; }
    X.toc.list = flat(r.toc, 0, []); X.toc.at = null; X.toc.generated = true;
    await reload();
    tocDraw();
  } catch(e){ toast(e.message); }
}
async function tocSave(){
  const T = X.toc;
  try {
    await calibre('toc_save', { toc: nest(T.list), title: T.title }, 'Saving the contents…');
    unsheet();
    await reload();
    toast('Contents saved');
  } catch(e){ toast(e.message); }
}

/* ---------- files: add, rename, remove ---------- */
async function addFile(file){
  if (!file) return;
  try {
    await flush();
    const r = await busy('Adding…', async () => {
      const res = await fetch(base() + '/add?name=' + encodeURIComponent(file.name), { method: 'POST', body: file, credentials: 'same-origin' });
      if (!res.ok) { let m = res.statusText; try { m = (await res.json()).detail || m; } catch(e){} throw new Error(m); }
      return job(res.json());
    });
    await reload();
    if (r && r.name) openFile(r.name);
  } catch(e){ toast(e.message); }
}
async function renameFile(name){
  const to = (prompt('Rename', name) || '').trim();
  if (!to || to === name) return;
  try {
    await calibre('rename', { map: { [name]: to } }, 'Renaming…');
    const st = X.states.get(name); if (st) { X.states.delete(name); }
    if (X.cur === name) X.cur = to;
    if (X.prevName === name) X.prevName = to;
    await reload();
  } catch(e){ toast(e.message); }
}
async function removeFile(name){
  if (!confirm('Remove ' + short(name) + '?')) return;
  try {
    await calibre('remove', { names: [name] }, 'Removing…');
    X.states.delete(name);
    await reload();
  } catch(e){ toast(e.message); }
}

/* ---------- Save, Discard ---------- */
async function save(){
  if (!X || X.busy) return;
  try {
    await flush();
    await busy('Saving…', () => job(post('/save')));
    X.changed = false; layout();
    toast('Saved');
    // the device's copy of the book (sw.js keeps it) comes again, so the reader shows the edited one
    if (X.dafId) fetch('/api/ebooks/' + encodeURIComponent(X.dafId) + '/file', { cache: 'reload', credentials: 'same-origin' }).catch(() => {});
  } catch(e){ toast(e.message); }
}
async function discard(){
  if (!confirm('Throw away the changes?')) return;
  const cid = X.cid;
  clearTimeout(X.timer);
  hide();
  try { await api('/api/ebookedit/' + cid, { method: 'DELETE' }); toast('Changes thrown away'); } catch(e){ toast(e.message); }
}

/* ---------- events ---------- */
document.addEventListener('click', async e => {
  const t = e.target; if (!t.closest) return;
  const go = t.closest('[data-act="ebookedit"]');
  if (go) { const pp = $('#pop'); if (pp && go.closest('#pop')) pp.hidden = true; open(go.dataset.id); return; }
  if (!X || !t.closest('#ebx')) return;
  const p = $('#ebxpop');
  if (p && !p.hidden && !t.closest('#ebxpop')) { unpop(); if (!t.closest('[data-ebx="more"],[data-ebx="fmenu"],[data-ebt="gen"]')) return; }
  const ch = t.closest('[data-ebchoose]');
  if (ch) { const f = chosen; chosen = null; unsheet(); if (f) f(ch.dataset.ebchoose || null); return; }
  if (t.closest('#ebxshade')) { if (chosen) { const f = chosen; chosen = null; unsheet(); f(null); } else if (!X.toc) unsheet(); return; }
  // on the tablet the file list is a drawer over the code: a tap beside it puts it away
  if (narrow() && !phone() && X.showFiles && t.closest('.ebxbody') && !t.closest('.ebxside')) { X.showFiles = false; layout(); }
  const f = t.closest('[data-ebxf]'); if (f) { openFile(f.dataset.ebxf); return; }
  const er = t.closest('[data-ebxerr]'); if (er) { openError(+er.dataset.ebxerr); return; }
  const tr = t.closest('[data-ebtr]');
  if (tr && !t.closest('[data-ebt]') && X.toc) { const i = +tr.dataset.ebtr; if (X.toc.at !== i) { X.toc.at = i; $$('.ebxtr', $('#ebxsheet')).forEach(r => r.classList.toggle('on', +r.dataset.ebtr === i)); $$('.ebxtbar [data-ebt]').forEach(b => { if (b.dataset.ebt !== 'add') b.disabled = false; }); } return; }
  const bt = t.closest('[data-ebt]');
  if (bt && X.toc) {
    const k = bt.dataset.ebt;
    if (k === 'cancel') unsheet();
    else if (k === 'save') tocSave();
    else if (k === 'gen') tocGenerate(bt);
    else if (k === 'add') tocPlace(null, true);
    else if (k === 'place') tocPlace(+bt.dataset.i, false);
    else if (k === 'pick') tocPick(bt.dataset.frag, bt.dataset.text);
    else if (k === 'back') { X.toc.placing = null; tocDraw(); }
    else tocMove(k);
    return;
  }
  const m = t.closest('[data-ebm]');
  if (m) {
    unpop();
    const k = m.dataset.ebm;
    if (k === 'tool') runTool(m.dataset.tool);
    else if (k === 'toc') tocOpen();
    else if (k === 'check') showCheck();
    else if (k === 'add') $('#ebxadd').click();
    else if (k === 'cps') cpsSheet();
    else if (k === 'discard') discard();
    else if (k === 'rename') renameFile(m.dataset.name);
    else if (k === 'remove') removeFile(m.dataset.name);
    else if (k === 'gen') tocGen(m.dataset.kind);
    return;
  }
  const b = t.closest('[data-ebx]'); if (!b) return;
  const k = b.dataset.ebx;
  if (X.busy && !['close', 'files', 'preview', 'pane', 'side', 'group', 'search', 'unsheet'].includes(k)) return;
  if (k === 'close') shut();
  else if (k === 'save') save();
  else if (k === 'files') { X.showFiles = !X.showFiles; if (X.showFiles) X.side = 'files'; layout(); side(); }
  else if (k === 'preview') { X.showPrev = !X.showPrev; layout(); }
  else if (k === 'pane') { X.pane = b.dataset.pane; layout(); }
  else if (k === 'side') { X.side = b.dataset.side; side(); if (X.side === 'check' && !X.errors) check(); }
  else if (k === 'group') { const g = b.dataset.g; X.closed.has(g) ? X.closed.delete(g) : X.closed.add(g); side(); }
  else if (k === 'fmenu') fileMenu(b, b.dataset.name);
  else if (k === 'more') moreMenu(b);
  else if (k === 'search') { const s = $('#ebxsearch'); if (s.hidden) searchOpen(); else { s.hidden = true; X.found = null; showMatches(); layout(); } }
  else if (k === 'find') findNext();
  else if (k === 'rep') replaceOne();
  else if (k === 'repall') replaceAll();
  else if (k === 'count') countAll();
  else if (k === 'toc') tocOpen();
  else if (k === 'check') showCheck();
  else if (k === 'recheck') check();
  else if (k === 'fix') check(true);
  else if (k === 'add') $('#ebxadd').click();
  else if (k === 'unsheet') unsheet();
  else if (k === 'restore') restore(b.dataset.n);
});
document.addEventListener('change', e => {
  if (!X) return;
  if (e.target.id === 'ebxadd') { const f = e.target.files[0]; e.target.value = ''; addFile(f); }
  else if (e.target.id === 'ebxpfile') placeIds(e.target.value, null);
  else if (e.target.closest && e.target.closest('#ebxsearch')) { X.found = null; showMatches(); count(''); }
});
document.addEventListener('input', e => {
  if (!X) return;
  const tt = e.target.dataset && e.target.dataset.ebtt;
  if (tt != null && X.toc) { X.toc.list[+tt].title = e.target.value; return; }
  if (e.target.id === 'ebxfind' || e.target.id === 'ebxrep') { X.found = null; count(''); }
});
document.addEventListener('keydown', e => {
  if (!X) return;
  if (e.key === 'Escape') {
    const p = $('#ebxpop'), s = $('#ebxsheet');
    if (p && !p.hidden) { e.preventDefault(); e.stopPropagation(); unpop(); return; }
    if (s && !s.hidden) { e.preventDefault(); e.stopPropagation(); if (X.toc && X.toc.placing) { X.toc.placing = null; tocDraw(); } else if (!X.toc) { if (chosen) { const f = chosen; chosen = null; unsheet(); f(null); } else unsheet(); } return; }
  }
  if (e.target.id === 'ebxfind' || e.target.id === 'ebxrep') {
    if (e.key === 'Enter') { e.preventDefault(); if (e.target.id === 'ebxrep' && (e.metaKey || e.ctrlKey)) replaceAll(); else findNext(e.shiftKey); }
    else if (e.key === 'Escape') { e.preventDefault(); $('#ebxsearch').hidden = true; X.found = null; showMatches(); layout(); X.view.focus(); }
    return;
  }
  if ((e.metaKey || e.ctrlKey) && !e.altKey && (e.key === 's' || e.key === 'f') && $('#ebx') && !$('#ebx').hidden) {
    e.preventDefault(); e.stopPropagation();
    if (e.key === 's') save(); else searchOpen();
  }
}, true);
// Leaving the page or the app: what's typed goes into the copy first.
document.addEventListener('visibilitychange', () => { if (document.hidden && X) flush().catch(() => {}); });
window.addEventListener('hashchange', () => { if (X) shut(); });
window.addEventListener('resize', () => { if (X) layout(); });

C.EbookEdit = { open, close: () => shut() };
})();
