/* Convert books: Calibre's Convert dialog as a sheet, for one book or many (All books' toolbar, and a
   file's Convert to in Edit metadata). The output format, the books and the file each is made from,
   then Calibre's sections: Look & feel, Page setup, Structure detection, Table of contents, Heuristic
   processing, Search & replace, Extra CSS and the output format's own options (daf/convertopts.py has
   the list, Calibre's names and defaults). One book opens with the settings Calibre keeps for it over Daf's defaults; many
   books open with Daf's defaults, and each gets the sheet's settings and keeps them, as in Calibre's
   bulk convert. Save as default keeps the sheet for every device (settings convert_opts); Reset puts
   Calibre's own values back in the sheet. C.ConvertSheet.open(books, {from, to, started(to), done(ok)}) */
(() => {
'use strict';
const C = window.DafCore, { api, esc, toast, $, $$ } = C;
const store = { get(k, d){ try { const v = localStorage.getItem('daf.' + k); return v == null ? d : JSON.parse(v); } catch(e){ return d; } }, set(k, v){ try { localStorage.setItem('daf.' + k, JSON.stringify(v)); } catch(e){} } };
const sleep = ms => new Promise(r => setTimeout(r, ms));
const M = { books: [], to: 'EPUB', from: null, pref: null, v: {}, sr: [], info: null, cb: {}, busy: false, replace: false, fonts: null,
  open: new Set(store.get('convOpen', ['look', 'page'])) };

// The sheet's controls: a number (unit, step), a tick, a list, a line of text, the margins, Filter style information.
// dep: shown greyed out until that tick is on, as Calibre does.
const num = (k, label, unit, step, dep) => ({ kind: 'num', k, label, unit, step, dep });
const tick = (k, label, dep) => ({ kind: 'tick', k, label, dep });
const pick = (k, label) => ({ kind: 'pick', k, label });
const text = (k, label, dep, list) => ({ kind: 'text', k, label, dep, list });
const margins = (keys, label) => ({ kind: 'marg', keys, label });
const area = (k, label) => ({ kind: 'area', k, label });
const imgsize = k => ({ kind: 'img', k, label: 'Shrink images larger than' });
const HEUR = 'enable_heuristics';
const SECTIONS = [
  ['look', 'Look & feel', [
    num('base_font_size', 'Base font size', 'pt', 1), text('font_size_mapping', 'Font size key'),
    num('minimum_line_height', 'Minimum line height', '%', 1), num('line_height', 'Line height', 'pt', 1),
    text('embed_font_family', 'Embed font family', null, 'cvfonts'),
    tick('embed_all_fonts', 'Embed referenced fonts'), tick('subset_embedded_fonts', 'Subset all embedded fonts'),
    pick('change_justification', 'Text justification'),
    tick('smarten_punctuation', 'Smarten punctuation'), tick('unsmarten_punctuation', 'Unsmarten punctuation'),
    tick('remove_paragraph_spacing', 'Remove spacing between paragraphs'),
    num('remove_paragraph_spacing_indent_size', 'Indent size', 'em', .1, 'remove_paragraph_spacing'),
    tick('insert_blank_line', 'Insert blank line between paragraphs'),
    num('insert_blank_line_size', 'Line size', 'em', .1, 'insert_blank_line'),
    tick('linearize_tables', 'Linearize tables'), tick('disable_font_rescaling', 'Disable font size rescaling'),
    { kind: 'filter', k: 'filter_css', label: 'Filter style information' },
  ]],
  ['page', 'Page setup', [
    pick('output_profile', 'Output profile'), pick('input_profile', 'Input profile'),
    margins(['margin_top', 'margin_bottom', 'margin_left', 'margin_right'], 'Margins (pt)'),
  ]],
  ['struct', 'Structure detection', [
    text('chapter', 'Detect chapters at'), pick('chapter_mark', 'Chapter mark'),
    tick('remove_first_image', 'Remove first image'), tick('remove_fake_margins', 'Remove fake margins'),
    tick('insert_metadata', 'Insert metadata as page at start of book'),
    text('page_breaks_before', 'Insert page breaks before'), text('start_reading_at', 'Start reading at'),
  ]],
  ['toc', 'Table of contents', [
    tick('use_auto_toc', 'Force use of auto-generated Table of Contents'),
    tick('no_chapters_in_toc', 'Do not add detected chapters to the Table of Contents'),
    num('max_toc_links', 'Number of links to add', '', 1), num('toc_threshold', 'Chapter threshold', '', 1),
    text('level1_toc', 'Level 1 TOC'), text('level2_toc', 'Level 2 TOC'), text('level3_toc', 'Level 3 TOC'),
  ]],
  ['heur', 'Heuristic processing', [
    tick(HEUR, 'Enable heuristic processing'),
    tick('unwrap_lines', 'Unwrap lines', HEUR), num('html_unwrap_factor', 'Line unwrap factor', '', .05, HEUR),
    tick('markup_chapter_headings', 'Detect and mark up unformatted chapter headings', HEUR),
    tick('renumber_headings', 'Renumber sequences of <h1> or <h2> tags', HEUR),
    tick('delete_blank_paragraphs', 'Delete blank lines between paragraphs', HEUR),
    tick('format_scene_breaks', 'Ensure scene breaks are consistently formatted', HEUR),
    text('replace_scene_breaks', 'Replace soft scene breaks', HEUR),
    tick('dehyphenate', 'Remove unnecessary hyphens', HEUR),
    tick('italicize_common_cases', 'Italicize common words and patterns', HEUR),
    tick('fix_indents', 'Replace entity indents with CSS indents', HEUR),
  ]],
  ['sr', 'Search & replace', [{ kind: 'sr', k: 'search_replace' }]],
  ['css', 'Extra CSS', [{ kind: 'css', k: 'extra_css', label: 'Extra CSS' }]],
];
const TOC_IN = [tick('no_inline_toc', 'Do not add Table of Contents to book'), tick('mobi_toc_at_start', 'Put generated Table of Contents at start of book'),
  text('toc_title', 'Title for Table of Contents'), tick('prefer_author_sort', 'Use author sort for author')];
const OUTPUT = {
  EPUB: [pick('epub_version', 'EPUB version'), num('flow_size', 'Split files larger than', 'KB', 1),
    tick('dont_split_on_page_breaks', 'Do not split on page breaks'), tick('no_default_epub_cover', 'No default cover'),
    tick('no_svg_cover', 'No SVG cover'), tick('preserve_cover_aspect_ratio', 'Preserve cover aspect ratio'),
    tick('epub_inline_toc', 'Insert inline Table of Contents'), tick('epub_toc_at_end', 'Put inserted Table of Contents at the end of the book'),
    text('toc_title', 'Title for inserted ToC'), tick('epub_flatten', 'Flatten EPUB file structure'), imgsize('epub_max_image_size')],
  AZW3: TOC_IN,
  MOBI: [pick('mobi_file_type', 'MOBI file type'), ...TOC_IN,
    tick('mobi_keep_original_images', 'Do not convert all images to JPEG'), tick('mobi_ignore_margins', 'Ignore margins')],
  KEPUB: [num('flow_size', 'Split files larger than', 'KB', 1), tick('dont_split_on_page_breaks', 'Do not split on page breaks'),
    tick('kepub_prefer_justification', 'Prefer justification'), tick('kepub_disable_hyphenation', 'Disable hyphenation'),
    tick('kepub_affect_hyphenation', 'Modify hyphenation'),
    num('kepub_hyphenation_min_chars', 'Minimum word length', '', 1, 'kepub_affect_hyphenation'),
    num('kepub_hyphenation_min_chars_before', 'Characters before hyphen', '', 1, 'kepub_affect_hyphenation'),
    num('kepub_hyphenation_min_chars_after', 'Characters after hyphen', '', 1, 'kepub_affect_hyphenation'),
    num('kepub_hyphenation_limit_lines', 'Hyphenated lines in a row', '', 1, 'kepub_affect_hyphenation'), imgsize('kepub_max_image_size')],
  PDF: [pick('paper_size', 'Paper size'), tick('use_profile_size', 'Use the paper size set in output profile'),
    num('pdf_default_font_size', 'Default font size', 'px', 1), num('pdf_mono_font_size', 'Monospace font size', 'px', 1),
    pick('pdf_standard_font', 'Standard font'), tick('pdf_page_numbers', 'Add page numbers to the bottom of every page'),
    tick('pdf_add_toc', 'Add printable Table of Contents'), text('toc_title', 'Title for ToC'),
    tick('pdf_hyphenate', 'Break long words at the end of lines'), tick('preserve_cover_aspect_ratio', 'Preserve aspect ratio of cover'),
    tick('pdf_no_cover', 'Discard book cover'), tick('pdf_use_document_margins', 'Use page margins from the document'),
    margins(['pdf_page_margin_top', 'pdf_page_margin_bottom', 'pdf_page_margin_left', 'pdf_page_margin_right'], 'Page margins (pt)'),
    { kind: 'size', k: 'custom_size', label: 'Custom size' }, pick('unit', 'Unit'),
    area('pdf_header_template', 'Header template'), area('pdf_footer_template', 'Footer template')],
};
// Filter style information: Calibre's groups of CSS properties, and any others after them.
const FILTER = [['fonts', 'Fonts', ['font-family']], ['margins', 'Margins', ['margin', 'margin-left', 'margin-right', 'margin-top', 'margin-bottom']],
  ['padding', 'Padding', ['padding', 'padding-left', 'padding-right', 'padding-top', 'padding-bottom']], ['floats', 'Floats', ['float']],
  ['colors', 'Colors', ['color', 'background-color']]];
const SIDES = ['Top', 'Bottom', 'Left', 'Right'];
const X = '<svg width="16" height="16" viewBox="0 0 20 20" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"><path d="M6 6l8 8M14 6l-8 8"/></svg>';
const IMG = [['none', 'No limit'], ['profile', 'Output profile’s screen'], ['custom', 'Custom']];

/* ---------- values: the sheet's own, else Calibre's default for this format ---------- */
const has = (o, k) => Object.prototype.hasOwnProperty.call(o, k);
function def(k){ const c = M.info.calibre, o = c.out[M.to] || {}; return has(o, k) ? o[k] : c.pipe[k]; }
const val = k => has(M.v, k) ? M.v[k] : def(k);
const fmts = b => (b.formats || []).map(f => String(f).toUpperCase());
// The file a book is converted from: its best one in Daf's order (app.py CONVERT_FROM), never the output format.
function srcOf(b){ const f = fmts(b).filter(x => x !== M.to); return M.info.from_order.find(x => f.includes(x)) || f[0] || null; }
function plan(b){
  const there = fmts(b).includes(M.to);
  if (there && !M.replace) return { skip: 'Has ' + M.to };
  const s = srcOf(b);
  return s ? { src: s } : { skip: there ? 'Only ' + M.to : 'No file' };
}
function pickFrom(){
  if (M.books.length !== 1) { M.from = null; return; }
  const f = fmts(M.books[0]).filter(x => x !== M.to);
  M.from = f.includes(M.from) ? M.from : f.includes(M.pref) ? M.pref : (M.info.from_order.find(x => f.includes(x)) || f[0] || null);
}

// Search & replace as rows while the sheet is open; the setting is Calibre's JSON of the filled ones.
function srRows(){
  try { const a = JSON.parse(val('search_replace') || '[]'); return Array.isArray(a) ? a.filter(x => Array.isArray(x) && x.length === 2).map(x => [String(x[0]), String(x[1])]) : []; }
  catch(e){ return []; }
}
const srKeep = () => { M.v.search_replace = JSON.stringify(M.sr.filter(x => x[0].trim())); };
// Width x height: Custom size (any unit, decimals) and Shrink images larger than (whole pixels).
const wh = (k, w, h, dis, unit) => '<span class="cvnum"><input class="field" type="number" min="0" step="any" inputmode="decimal" data-cvwh="' + k + ':w" value="' + esc(w) + '" aria-label="Width"' + dis + '>' +
  '<span class="mute">×</span><input class="field" type="number" min="0" step="any" inputmode="decimal" data-cvwh="' + k + ':h" value="' + esc(h) + '" aria-label="Height"' + dis + '>' + (unit ? '<span class="mute">' + unit + '</span>' : '') + '</span>';

/* ---------- the sheet ---------- */
function sheet(html){
  let s = $('#cvsheet');
  if (!s) { document.body.insertAdjacentHTML('beforeend', '<div class="beshade cvshade" id="cvshade"></div><div class="besheet cvsheet" id="cvsheet" role="dialog" aria-modal="true" aria-label="Convert books"></div>'); s = $('#cvsheet'); }
  s.innerHTML = html; s.hidden = false; $('#cvshade').hidden = false;
  document.body.classList.add('beopen');
  return s;
}
function close(){
  if (M.busy) return;
  const s = $('#cvsheet'); if (s) s.hidden = true;
  const sh = $('#cvshade'); if (sh) sh.hidden = true;
  if (!$('#bedit') || $('#bedit').hidden) document.body.classList.remove('beopen');
  M.books = []; M.cb = {};
}
const row = (label, ctl) => '<div class="berow"><span>' + esc(label) + '</span><div class="bectl">' + ctl + '</div></div>';
const cover = b => b.cover && b.id != null ? '<img src="/api/cover/' + encodeURIComponent(b.id) + '?v=' + (b.cover_v || 0) + '" alt="" loading="lazy">' : '<span class="befnc"></span>';
const opt = (v, label, on) => '<option value="' + esc(v) + '"' + (on ? ' selected' : '') + '>' + esc(label) + '</option>';
const numIn = (k, step, dis, extra) => '<input class="field" type="number" inputmode="decimal" step="' + step + '" data-cv="' + k + '" value="' + esc(val(k) == null ? '' : val(k)) + '"' + dis + (extra || '') + '>';
function control(it){
  const off = it.dep && !val(it.dep) ? ' disabled' : '', dep = it.dep ? ' data-cvdep="' + it.dep + '"' : '';
  if (it.kind === 'tick')
    return '<div class="cvtick"><label class="cvchk"><input type="checkbox" data-cv="' + it.k + '"' + (val(it.k) ? ' checked' : '') + off + dep + '><span>' + esc(it.label) + '</span></label></div>';
  if (it.kind === 'num')
    return row(it.label, '<span class="cvnum">' + numIn(it.k, it.step, off, dep) + (it.unit ? '<span class="mute">' + esc(it.unit) + '</span>' : '') + '</span>');
  if (it.kind === 'pick')
    return row(it.label, '<select class="field" data-cv="' + it.k + '">' + (M.info.choices[it.k] || []).map(([v, l]) => opt(v, l, String(v) === String(val(it.k)))).join('') + '</select>');
  if (it.kind === 'text')
    return row(it.label, '<input class="field" data-cv="' + it.k + '" value="' + esc(val(it.k) == null ? '' : val(it.k)) + '" spellcheck="false" autocapitalize="off" autocomplete="off"' + (it.list ? ' list="' + it.list + '"' : '') + off + dep + '>');
  if (it.kind === 'marg')
    return row(it.label, '<div class="cvmarg">' + it.keys.map((k, i) => '<label><span>' + SIDES[i] + '</span>' + numIn(k, .5, '') + '</label>').join('') + '</div>');
  if (it.kind === 'area')
    return row(it.label, '<textarea class="field cvtpl" data-cv="' + it.k + '" rows="3" spellcheck="false" autocapitalize="off">' + esc(val(it.k) || '') + '</textarea>');
  if (it.kind === 'size') {
    const m = /^([\d.]+)x([\d.]+)$/.exec(String(val(it.k) || ''));
    return row(it.label, wh(it.k, m ? m[1] : '', m ? m[2] : '', ''));
  }
  if (it.kind === 'img') {
    const v = String(val(it.k) || 'none'), m = /^(\d+)x(\d+)$/.exec(v), mode = m ? 'custom' : v === 'profile' ? 'profile' : 'none';
    return row(it.label, '<div class="cvpair"><select class="field" data-cvimg="' + it.k + '">' + IMG.map(([x, l]) => opt(x, l, x === mode)).join('') + '</select>' +
      wh(it.k, m ? m[1] : '', m ? m[2] : '', m ? '' : ' disabled', 'px') + '</div>');
  }
  if (it.kind === 'sr')
    return (M.sr.length ? '<div class="cvsr cvsrh"><span>Search regular expression</span><span>Replacement text</span><span></span></div>' : '') +
      M.sr.map(([a, b], i) => '<div class="cvsr"><input class="field" data-cvsr="' + i + ':0" value="' + esc(a) + '" aria-label="Search regular expression" spellcheck="false" autocapitalize="off" autocomplete="off">' +
        '<input class="field" data-cvsr="' + i + ':1" value="' + esc(b) + '" aria-label="Replacement text" spellcheck="false" autocapitalize="off" autocomplete="off">' +
        '<button class="btn sm" data-cvsrx="' + i + '" aria-label="Remove">' + X + '</button></div>').join('') +
      '<div><button class="btn sm" data-cvb="sradd">Add</button></div>';
  if (it.kind === 'css')
    return '<textarea class="field cvcss" data-cv="extra_css" rows="6" spellcheck="false" autocapitalize="off" aria-label="Extra CSS">' + esc(val('extra_css') || '') + '</textarea>';
  if (it.kind === 'filter') {
    let left = new Set(String(val('filter_css') || '').split(',').map(x => x.trim().toLowerCase()).filter(Boolean));
    const boxes = FILTER.map(([g, label, props]) => {
      const on = props.every(p => left.has(p));
      if (on) props.forEach(p => left.delete(p));
      return '<label class="cvchk"><input type="checkbox" data-cvf="' + g + '"' + (on ? ' checked' : '') + '><span>' + label + '</span></label>';
    }).join('');
    return row(it.label, '<div class="cvfilt">' + boxes + '</div>') +
      row('Other CSS properties', '<input class="field" data-cvfo value="' + esc([...left].join(', ')) + '" spellcheck="false" autocapitalize="off" autocomplete="off">');
  }
  return '';
}
const section = (id, title, items) => '<details class="cvsec" data-cvsec="' + id + '"' + (M.open.has(id) ? ' open' : '') + '><summary>' + esc(title) + '</summary>' +
  '<div class="cvrows">' + items.map(control).join('') + '</div></details>';
function draw(){
  const one = M.books.length === 1, b0 = M.books[0];
  const plans = M.books.map(plan), n = plans.filter(p => p.src).length;
  const ready = !M.busy && (one ? !!M.from : n > 0);
  const toSel = '<select class="field" data-cvto>' + M.info.formats.map(f => opt(f, f, f === M.to)).join('') + '</select>';
  let books;
  if (one) {
    const from = fmts(b0).filter(x => x !== M.to);
    books = '<div class="cvbook">' + cover(b0) + '<span class="befct"><b>' + esc(b0.title || '') + '</b><span class="mute tiny">' + esc((b0.authors || []).join(' & ')) + '</span></span></div>' +
      row('Input format', from.length ? '<select class="field" data-cvfrom>' + from.map(f => opt(f, f, f === M.from)).join('') + '</select>' : '<span class="mute">No file</span>') +
      row('Output format', toSel);
  } else {
    const there = M.books.filter(b => fmts(b).includes(M.to) && fmts(b).some(f => f !== M.to)).length;
    books = row('Output format', toSel) +
      (there ? '<div class="cvtick"><label class="cvchk"><input type="checkbox" data-cvrep' + (M.replace ? ' checked' : '') + '><span>Replace existing ' + esc(M.to) + '</span></label></div>' : '') +
      '<h3 class="cvh">' + M.books.length + ' books</h3><div class="cvbooks">' + M.books.map((b, i) => {
        const p = plans[i];
        return '<div class="cvbook' + (p.src ? '' : ' off') + '">' + cover(b) + '<span class="befct"><b>' + esc(b.title || '') + '</b><span class="mute tiny">' + esc((b.authors || []).join(' & ')) + '</span></span>' +
          '<span class="cvfmt">' + (p.src ? esc(p.src) + ' → ' + esc(M.to) : esc(p.skip)) + '</span></div>';
      }).join('') + '</div>';
  }
  const sc = $('#cvsheet .bebody'), top = sc ? sc.scrollTop : 0;
  sheet('<div class="behead"><h2>Convert</h2><span class="spacer"></span><button class="btn sm" data-cvb="cancel">Cancel</button>' +
    '<button class="btn sm primary" data-cvb="go"' + (ready ? '' : ' disabled') + '>' + (M.busy ? 'Converting…' : 'Convert') + '</button></div>' +
    '<div class="bebody one cvbody">' + books +
    SECTIONS.map(([id, title, items]) => section(id, title, items)).join('') +
    section('out', M.to + ' output', OUTPUT[M.to] || []) +
    '<div class="cvfoot"><button class="btn sm" data-cvb="reset">Reset</button><button class="btn sm" data-cvb="save">Save as default</button></div>' +
    '<datalist id="cvfonts">' + (M.fonts || []).map(f => '<option value="' + esc(f) + '">').join('') + '</datalist></div>');
  const nb = $('#cvsheet .bebody'); if (nb && top) nb.scrollTop = top;
}
async function open(books, o){
  o = o || {};
  books = (books || []).filter(Boolean);
  if (!books.length || M.busy) return;
  let info, own = null;
  try {
    [info, own] = await Promise.all([api('/api/catalog/convert-opts'),
      books.length === 1 ? api('/api/catalog/book/' + encodeURIComponent(books[0].calibre_id) + '/convert-opts') : null]);
  } catch(e){ toast(e.message); return; }
  const pref = String(o.from || (own && own.input) || '').toUpperCase() || null;
  Object.assign(M, { info, books, cb: o, replace: false, from: pref, pref });
  const last = store.get('convTo', 'EPUB'), to = o.to && String(o.to).toUpperCase();
  M.to = info.formats.includes(to) ? to : info.formats.includes(last) ? last : info.formats[0];
  if (books.length === 1 && !to) {             // one book with only this format: the next one
    const f = fmts(books[0]);
    if (f.length === 1 && f[0] === M.to) M.to = info.formats.find(x => x !== f[0]) || M.to;
  }
  M.v = Object.assign({}, info.saved, own ? own.opts : {});
  M.sr = srRows();
  pickFrom();
  draw();
  if (!M.fonts) api('/api/catalog/convert-fonts').then(r => { M.fonts = r.fonts || []; const dl = $('#cvfonts'); if (dl) dl.innerHTML = M.fonts.map(f => '<option value="' + esc(f) + '">').join(''); }).catch(() => {});
}

/* ---------- converting: one book through its own endpoint, many as one job ---------- */
async function go(){
  if (M.busy || !M.books.length) return;
  const to = M.to, opts = Object.assign({}, M.v), cb = M.cb, books = M.books.slice(), from = M.from;
  M.busy = true; draw();
  if (books.length === 1) {
    let job;
    try { ({ job } = await api('/api/catalog/book/' + encodeURIComponent(books[0].calibre_id) + '/convert', { method: 'POST', body: JSON.stringify({ from, to, opts }) })); }
    catch(e){ M.busy = false; draw(); toast(e.message); return; }
    M.busy = false; close(); toast('Converting to ' + to);
    if (cb.started) cb.started(to);
    let ok = false;
    for (;;) {
      await sleep(2000);
      let j; try { j = await api('/api/catalog/jobs/' + job); } catch(e){ toast(e.message); break; }
      if (j.state === 'done') { ok = true; toast('Converted to ' + to); break; }
      if (j.state === 'failed') { toast(j.error || 'Calibre couldn’t convert it'); break; }
    }
    if (cb.done) cb.done(ok); else if (C.Catalog) C.Catalog.reload();
    return;
  }
  let r;
  try { r = await api('/api/catalog/convert-many', { method: 'POST', body: JSON.stringify({ ids: books.map(b => b.calibre_id), to, opts, replace: M.replace }) }); }
  catch(e){ M.busy = false; draw(); toast(e.message); return; }
  M.busy = false; close();
  if (!r.job) { toast(r.have ? 'All ' + r.have + ' have ' + to : 'No file to convert'); return; }
  toast('Converting ' + r.total + ' to ' + to);
  for (;;) {
    await sleep(4000);
    let j; try { j = await api('/api/catalog/convert-many/' + r.job); } catch(e){ return; }
    if (j.running) continue;
    toast((j.done - j.failed.length) + ' converted to ' + to + (j.failed.length ? ' · ' + j.failed.length + ' didn’t' : ''));
    if (cb.done) cb.done(!j.failed.length); else if (C.Catalog) C.Catalog.reload();
    return;
  }
}
async function saveDefault(){
  try { const r = await api('/api/catalog/convert-opts', { method: 'PUT', body: JSON.stringify({ opts: M.v }) }); M.info.saved = r.saved; toast('Saved'); }
  catch(e){ toast(e.message); }
}

/* ---------- events ---------- */
function filterValue(){
  const s = $('#cvsheet'), out = [];
  FILTER.forEach(([g, , props]) => { const b = $('[data-cvf="' + g + '"]', s); if (b && b.checked) out.push(...props); });
  const other = $('[data-cvfo]', s);
  if (other) out.push(...other.value.split(',').map(x => x.trim().toLowerCase()).filter(Boolean));
  M.v.filter_css = [...new Set(out)].join(',');
}
function takeWH(k){
  const s = $('#cvsheet'), num = j => { const n = parseFloat(($('[data-cvwh="' + k + ':' + j + '"]', s) || {}).value); return isFinite(n) && n > 0 ? n : 0; };
  const w = num('w'), h = num('h'), px = k !== 'custom_size';
  if (!px && !w && !h) { M.v[k] = null; return; }
  if (w && h) M.v[k] = px ? Math.max(1, Math.round(w)) + 'x' + Math.max(1, Math.round(h)) : Math.round(w * 1000) / 1000 + 'x' + Math.round(h * 1000) / 1000;
}
function take(el){
  const k = el.dataset.cv;
  if (el.type === 'checkbox') {
    M.v[k] = el.checked;
    $$('#cvsheet [data-cvdep="' + k + '"]').forEach(x => { x.disabled = !el.checked; });
  } else if (el.type === 'number') {
    const n = parseFloat(el.value);
    if (el.value === '' || !isFinite(n)) delete M.v[k]; else M.v[k] = n;
  } else M.v[k] = el.value;
}
document.addEventListener('click', e => {
  const t = e.target; if (!t.closest) return;
  if (t.closest('#cvshade')) { close(); return; }
  const x = t.closest('#cvsheet [data-cvsrx]');
  if (x) { M.sr.splice(+x.dataset.cvsrx, 1); srKeep(); draw(); return; }
  const b = t.closest('#cvsheet [data-cvb]'); if (!b || b.disabled) return;
  const k = b.dataset.cvb;
  if (k === 'cancel') close();
  else if (k === 'go') go();
  else if (k === 'save') saveDefault();
  else if (k === 'reset') { M.v = {}; M.sr = srRows(); draw(); }
  else if (k === 'sradd') { M.sr.push(['', '']); draw(); const f = $('#cvsheet [data-cvsr="' + (M.sr.length - 1) + ':0"]'); if (f) f.focus(); }
});
document.addEventListener('input', e => {
  const t = e.target; if (!t.closest || !t.closest('#cvsheet')) return;
  if (t.matches('[data-cvfo]')) filterValue();
  else if (t.matches('[data-cvsr]')) { const [i, j] = t.dataset.cvsr.split(':').map(Number); if (M.sr[i]) { M.sr[i][j] = t.value; srKeep(); } }
  else if (t.matches('[data-cvwh]')) takeWH(t.dataset.cvwh.split(':')[0]);
  else if (t.matches('input[data-cv]:not([type="checkbox"]), textarea[data-cv]')) take(t);
});
document.addEventListener('change', e => {
  const t = e.target; if (!t.closest || !t.closest('#cvsheet')) return;
  if (t.matches('[data-cvto]')) { M.to = t.value; store.set('convTo', M.to); pickFrom(); draw(); }
  else if (t.matches('[data-cvfrom]')) { M.from = t.value; M.pref = t.value; }
  else if (t.matches('[data-cvrep]')) { M.replace = t.checked; draw(); }
  else if (t.matches('[data-cvf]')) filterValue();
  else if (t.matches('[data-cvimg]')) {
    const k = t.dataset.cvimg;
    if (t.value !== 'custom') M.v[k] = t.value;
    else if (!/^\d+x\d+$/.test(String(val(k)))) M.v[k] = '1000x1000';
    draw();
  }
  else if (t.matches('[data-cv]')) take(t);
});
// A section left open stays open next time ('toggle' doesn't bubble, so it's caught on the way down).
document.addEventListener('toggle', e => {
  const d = e.target; if (!d.matches || !d.matches('#cvsheet details[data-cvsec]')) return;
  if (d.open) M.open.add(d.dataset.cvsec); else M.open.delete(d.dataset.cvsec);
  store.set('convOpen', [...M.open]);
}, true);
// On window, ahead of Edit metadata's own keys: the sheet can sit over it.
window.addEventListener('keydown', e => {
  const s = $('#cvsheet'); if (!s || s.hidden) return;
  if (e.key === 'Escape') { e.preventDefault(); e.stopImmediatePropagation(); close(); }
  else if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) { e.preventDefault(); e.stopImmediatePropagation(); go(); }
}, true);

C.ConvertSheet = { open };
})();
