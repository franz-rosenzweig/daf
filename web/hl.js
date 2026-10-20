/* Daf highlights, shared by the article reader, the book reader and every list of highlights:
   how a highlight looks (a soft fill with a firmer underline, as in Readwise), the toolbar over
   a selection or a highlight, auto-highlight, tags, favorites, share as image, and the rows on
   the Highlights page and book pages, where a click opens the exact spot. */
(() => {
const C = window.DafCore, { api, esc, toast, $, $$, epochDate, shortTitle } = C;
const store = { get(k, d){ try { const v = localStorage.getItem('daf.' + k); return v == null ? d : JSON.parse(v); } catch(e){ return d; } }, set(k, v){ try { localStorage.setItem('daf.' + k, JSON.stringify(v)); } catch(e){} } };
const COLORS = ['yellow', 'green', 'blue', 'pink', 'purple'];
const sv = (d, w) => '<svg width="' + (w || 17) + '" height="' + (w || 17) + '" viewBox="0 0 20 20" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">' + d + '</svg>';
const IC = {
  marker: sv('<path d="M12.5 3.5l4 4-7.5 7.5H5v-4z"/><path d="M3 17.5h8"/>'),
  note: sv('<path d="M4 4.5h12v8.5H9l-4 3v-3H4z"/>'),
  tag: sv('<path d="M3.5 3.5h6.2l7 7-6.2 6.2-7-7z"/><circle cx="7" cy="7" r="1.1" fill="currentColor" stroke="none"/>'),
  more: sv('<circle cx="5" cy="10" r="1.3" fill="currentColor" stroke="none"/><circle cx="10" cy="10" r="1.3" fill="currentColor" stroke="none"/><circle cx="15" cy="10" r="1.3" fill="currentColor" stroke="none"/>'),
  x: sv('<path d="M6 6l8 8M14 6l-8 8"/>', 15),
  copy: sv('<rect x="6.5" y="6.5" width="10" height="10" rx="2"/><path d="M13.5 6.5V4.8c0-.7-.6-1.3-1.3-1.3H4.8c-.7 0-1.3.6-1.3 1.3v7.4c0 .7.6 1.3 1.3 1.3h1.7"/>'),
  ask: sv('<path d="M10 3l1.6 4.4L16 9l-4.4 1.6L10 15l-1.6-4.4L4 9l4.4-1.6z"/><path d="M15.5 14.5l.6 1.4 1.4.6-1.4.6-.6 1.4-.6-1.4-1.4-.6 1.4-.6z"/>'),
  share: sv('<path d="M10 3v9M6.5 6.5L10 3l3.5 3.5"/><path d="M5 10v6h10v-6"/>'),
  heart: sv('<path d="M10 16s-6-3.6-6-8a3.4 3.4 0 0 1 6-2.2A3.4 3.4 0 0 1 16 8c0 4.4-6 8-6 8z"/>'),
  open: sv('<path d="M8 4H4.5v11.5H16V12"/><path d="M11 3.5h5.5V9M16.5 3.5L9 11"/>'),
  book: sv('<path d="M4 4.5c2-1 4-1 6 .5v11c-2-1.5-4-1.5-6-.5zM16 4.5c-2-1-4-1-6 .5v11c2-1.5 4-1.5 6-.5z"/>'),
};
const H = C.HL = { IC, COLORS, active: null, ctx: null, reg: new Map(), allTags: null };

/* ---------- preferences ---------- */
H.auto = () => store.get('autoHl', matchMedia('(pointer: fine)').matches);
H.setAuto = v => store.set('autoHl', !!v);
H.color = () => store.get('hlColor', 'yellow');
H.isDark = () => { const v = getComputedStyle(document.documentElement).getPropertyValue('--bg').trim(); const m = v.match(/^#(..)(..)(..)/); return m ? (parseInt(m[1], 16) + parseInt(m[2], 16) + parseInt(m[3], 16)) / 3 < 110 : false; };
H.tok = c => { const cs = getComputedStyle(document.documentElement); c = COLORS.includes(c) ? c : 'yellow'; return { fill: cs.getPropertyValue('--hl-' + c).trim() || '#fdf0bf', line: cs.getPropertyValue('--hl-' + c + '-line').trim() || '#efc93d' }; };
H.isWord = ch => !!ch && /[\p{L}\p{N}\p{M}’'_-]/u.test(ch);
// Grow a selection to whole words, as Readwise does: half a word is never what you meant.
H.snap = (text, s, e) => {
  while (s > 0 && H.isWord(text[s - 1]) && H.isWord(text[s])) s--;
  while (e < text.length && H.isWord(text[e - 1]) && H.isWord(text[e])) e++;
  while (s < e && /\s/.test(text[s])) s++;
  while (e > s && /\s/.test(text[e - 1])) e--;
  return [s, e];
};

/* ---------- the look, inside the book reader's overlay ---------- */
const svgEl = t => document.createElementNS('http://www.w3.org/2000/svg', t);
function lines(rects){
  // One box per line: drop the block boxes a range reports for whole paragraphs, merge the rest.
  const rs = [...rects].filter(r => r.width > 0.5 && r.height > 0.5);
  if (!rs.length) return [];
  const hs = rs.map(r => r.height).sort((a, b) => a - b), med = hs[Math.floor(hs.length / 2)];
  const out = [];
  for (const r of rs.filter(r => r.height <= med * 1.9).sort((a, b) => a.top - b.top || a.left - b.left)) {
    const l = out.find(o => Math.abs((o.top + o.bottom) / 2 - (r.top + r.bottom) / 2) < med * 0.5);
    if (l) { l.left = Math.min(l.left, r.left); l.right = Math.max(l.right, r.right); l.top = Math.min(l.top, r.top); l.bottom = Math.max(l.bottom, r.bottom); }
    else out.push({ left: r.left, right: r.right, top: r.top, bottom: r.bottom });
  }
  return out;
}
// Only the boxes of the text itself: a range over whole paragraphs also reports their block boxes,
// and an empty paragraph would draw as a blank bar.
function textRects(range){
  const root = range.commonAncestorContainer;
  if (root.nodeType === 3) return [...range.getClientRects()];
  const doc = root.ownerDocument || root, w = doc.createTreeWalker(root, NodeFilter.SHOW_TEXT), out = [];
  let n;
  while ((n = w.nextNode())) {
    if (!n.nodeValue.trim() || !range.intersectsNode(n)) continue;
    const r = doc.createRange(); r.selectNodeContents(n);
    if (n === range.startContainer) r.setStart(n, range.startOffset);
    if (n === range.endContainer) r.setEnd(n, range.endOffset);
    out.push(...r.getClientRects());
  }
  return out;
}
H.draw = (rects, o = {}) => {
  const g = svgEl('g'), t = H.tok(o.color), dark = H.isDark();
  g.style.mixBlendMode = dark ? 'screen' : 'multiply';
  if (o.range) { try { rects = textRects(o.range); } catch(e){} }
  const ls = lines(rects);
  for (const r of ls) {
    const h = r.bottom - r.top, pt = Math.max(1, h * 0.06), pb = Math.max(1.5, h * 0.12);
    const a = svgEl('rect'); a.setAttribute('x', r.left - 1); a.setAttribute('y', r.top - pt); a.setAttribute('width', r.right - r.left + 2); a.setAttribute('height', h + pt + pb);
    a.setAttribute('fill', o.flash ? t.line : t.fill); if (o.flash) a.setAttribute('fill-opacity', dark ? '.75' : '.55');
    g.append(a);
    if (!o.soft) { const u = svgEl('rect'); u.setAttribute('x', r.left - 1); u.setAttribute('y', r.bottom + pb - 2); u.setAttribute('width', r.right - r.left + 2); u.setAttribute('height', 2); u.setAttribute('fill', t.line); g.append(u); }
  }
  if (o.note && ls.length) {   // a small mark at the end of a highlight with a note
    const l = ls[ls.length - 1], c = svgEl('circle'); c.setAttribute('cx', l.right + 4); c.setAttribute('cy', l.top + 3); c.setAttribute('r', 3); c.setAttribute('fill', t.line); g.append(c);
  }
  return g;
};

/* ---------- the toolbar ---------- */
const btn = (a, icon, tip, extra) => '<button data-hb="' + a + '" data-tip="' + esc(tip) + '" aria-label="' + esc(tip) + '"' + (extra || '') + '>' + icon + '</button>';
H.dots = cur => '<span class="hbdots">' + COLORS.map(c => '<button class="cdot' + ((cur || 'yellow') === c ? ' on' : '') + '" data-hb="color" data-c="' + c + '" aria-label="' + c + '" style="--c:var(--hl-' + c + '-line)"></button>').join('') + '</span>';
// "(h)", or whatever key Preferences → Keyboard gives it, in the book or the article in front.
const ktip = a => { const K = window.DafCore && window.DafCore.Keys; return K ? K.tip(window.DafCore.S.route[0] === 'ebook' ? 'book' : 'article', a) : ''; };
H.selBar = o => {
  const t = (o.text || '').trim(), word = t && !/\s/.test(t) && t.length <= 40, heb = /[֐-׿]/.test(t);
  return btn('hl', IC.marker, 'Highlight' + ktip('highlight'), ' class="hbmain"') + btn('note', IC.note, 'Highlight with a note' + ktip('note')) +
    (word ? '<button data-hb="define" class="hbtext">Define</button>' : heb && t.length <= 60 ? '<button data-hb="translate" class="hbtext">Translate</button>' : '') +
    btn('ask', IC.ask, 'Ask about this') + btn('copy', IC.copy, 'Copy') + btn('selmore', IC.more, 'More');
};
// A highlighted picture is kept as Markdown's picture: ![alt](address).
H.picture = t => { const m = /^!\[([^\]\n]*)\]\((\S+)\)$/.exec(String(t || '').trim()); return m ? { alt: m[1], src: m[2] } : null; };
// A highlight's words, or its picture, as HTML.
H.quote = t => { const p = H.picture(t); return p ? '<img class="hlpic" src="' + esc(p.src) + '" alt="' + esc(p.alt) + '" loading="lazy" referrerpolicy="no-referrer">' : esc(t); };
H.imgBar = () => btn('hl', IC.marker, 'Highlight the picture' + ktip('highlight'), ' class="hbmain"') + btn('note', IC.note, 'Highlight it with a note' + ktip('note'));
H.hlBar = (h, o = {}) => {
  const c = h.color || 'yellow';
  return (o.kindle ? '<span class="hbsrc" data-tip="Made on the Kindle">Kindle</span>' : '<button data-hb="rm" class="hbx" data-tip="Remove the highlight" aria-label="Remove the highlight" style="--c:var(--hl-' + c + '-line);--f:var(--hl-' + c + ')">' + IC.x + '</button>') +
    btn('note', IC.note, h.user_note ? 'Edit the note' : 'Add a note', h.user_note ? ' class="has"' : '') + btn('tag', IC.tag, (h.tags || []).length ? 'Tags: ' + h.tags.join(', ') : 'Tag it', (h.tags || []).length ? ' class="has"' : '') +
    H.dots(c) + btn('more', IC.more, 'View other actions');
};
H.show = (html, rect, ctx) => {
  const bar = $('#selbar'); bar.innerHTML = html; bar.hidden = false; bar.className = 'selbar hbar';
  H.ctx = ctx || null; H.shownAt = Date.now();
  H.place(rect);
};
// Over the words. On a touch screen the selection's handles hang under them, and their grab area is
// bigger than they look (about 48 px), so a bar there loses its taps to them: a selection's bar goes
// over the words where Daf for Android (0.2.5 on) keeps Android's own text menu away, and in a
// browser, whose menu takes that place, well under the handles.
H.touch = () => !!(window.matchMedia && matchMedia('(pointer: coarse)').matches);
const ownMenu = () => { const m = / Daf\/(\d+)\.(\d+)\.(\d+) \(Android shell\)/.exec(navigator.userAgent); return !!m && (+m[1] > 0 || +m[2] > 2 || (+m[2] === 2 && +m[3] >= 5)); };
H.place = rect => {
  const bar = $('#selbar'), w = bar.offsetWidth || 240, hgt = bar.offsetHeight || 40, vh = window.innerHeight;
  bar.style.left = Math.max(8, Math.min(window.innerWidth - w - 8, rect.left + rect.width / 2 - w / 2)) + 'px';
  const sel = H.touch() && H.ctx && H.ctx.kind === 'sel', over = rect.top - hgt - 12, under = rect.bottom + (sel ? 60 : 10);
  const fitsOver = over >= 8, fitsUnder = under + hgt + 8 <= vh;
  bar.style.top = (sel && !ownMenu() ? (fitsUnder ? under : fitsOver ? over : vh - hgt - 8)
    : fitsOver ? over : fitsUnder ? under : vh - hgt - 8) + 'px';
};
H.hide = () => { const b = $('#selbar'); if (b) b.hidden = true; H.ctx = null; };
H.visible = () => !$('#selbar').hidden;

function menu(anchor, items){
  const p = $('#pop'), r = anchor.getBoundingClientRect();
  p.onclick = p.oninput = p.onkeydown = null;
  p.innerHTML = '<div class="menu">' + items.map(x => x === '-' ? '<hr>' : x.html ? x.html : '<button data-hm="' + x.a + '"' + (x.disabled ? ' disabled' : '') + '><span>' + (x.check != null ? '<span class="ck">' + (x.check ? '✓' : '') + '</span>' : '') + esc(x.label) + '</span>' + (x.key ? '<span class="kbd">' + esc(x.key) + '</span>' : '') + '</button>').join('') + '</div>';
  p.hidden = false;
  const w = p.offsetWidth || 260;
  p.style.left = Math.max(8, Math.min(window.innerWidth - w - 8, r.left + r.width / 2 - w / 2)) + 'px';
  p.style.top = (r.bottom + 8 + 300 < window.innerHeight ? r.bottom + 8 : Math.max(8, r.top - (p.offsetHeight || 280) - 8)) + 'px';
}
const autoHint = '<div class="mhint">Hold <span class="kbd">' + (/Mac|iPhone|iPad/.test(navigator.platform) ? '⌥ option' : 'Alt') + '</span> to select text without highlighting it.</div>';
// A picture has no words to share as an image card or to make a flashcard from.
H.moreMenu = (anchor, h) => menu(anchor, [
  { a: 'copy', label: H.picture(h.text) ? 'Copy the picture’s address' : 'Copy text', key: 'c' }, ...(H.picture(h.text) ? [] : [{ a: 'ask', label: 'Ask about this' }, { a: 'share', label: 'Share as image' }]),
  { a: 'notebook', label: 'View in notebook' }, { a: 'fav', label: h.fav ? 'Unfavorite' : 'Favorite' }, ...(H.picture(h.text) ? [] : [{ a: 'card', label: 'Make a flashcard' }]), '-',
  { a: 'auto', label: 'Auto highlight', check: H.auto() }, { html: autoHint }]);
H.selMenu = anchor => menu(anchor, [{ a: 'share', label: 'Share as image' }, '-', { a: 'auto', label: 'Auto highlight', check: H.auto() }, { html: autoHint }]);

// Clicks on the toolbar and its menu. The reader in front (H.active) does what only it can.
document.addEventListener('click', async e => {
  const b = e.target.closest('#selbar [data-hb], #pop [data-hm]'); if (!b || (b.dataset.hm || '').startsWith('row')) return;
  e.preventDefault(); e.stopPropagation();
  const a = b.dataset.hb || b.dataset.hm, ctx = H.ctx, R = H.active || {};
  if (b.dataset.hm) $('#pop').hidden = true;
  if (!ctx) return;
  const h = ctx.h;
  try {
    if (a === 'more') { H.moreMenu(b, h); return; }
    if (a === 'selmore') { H.selMenu(b); return; }
    if (a === 'auto') { H.setAuto(!H.auto()); toast(H.auto() ? 'Auto highlight on: selecting text highlights it' : 'Auto highlight off'); return; }
    if (a === 'copy') { const t = h ? (H.picture(h.text) ? H.picture(h.text).src : h.text) : ctx.text; H.hide(); navigator.clipboard && navigator.clipboard.writeText(t).then(() => toast('Copied'), () => toast('Couldn’t copy')); R.deselect && R.deselect(); return; }
    if (a === 'share') { H.hide(); H.share(h || { text: ctx.text }, R.meta ? R.meta() : {}); return; }
    if (a === 'card' && h) { H.hide(); H.cardEditor(h); return; }
    if (a === 'color' && h) { const c = b.dataset.c; store.set('hlColor', c); h.color = c; $$('#selbar .cdot').forEach(x => x.classList.toggle('on', x.dataset.c === c)); const x = $('#selbar .hbx'); if (x) { x.style.setProperty('--c', 'var(--hl-' + c + '-line)'); x.style.setProperty('--f', 'var(--hl-' + c + ')'); } await api('/api/highlights/' + encodeURIComponent(h.id) + '/color', { method: 'PUT', body: JSON.stringify({ color: c }) }); R.changed && R.changed(h, 'color'); return; }
    if (a === 'tag' && h) { const r = $('#selbar').getBoundingClientRect(); H.hide(); H.tagEditor(h, r, () => R.changed && R.changed(h, 'tags')); return; }
    if (a === 'fav' && h) { h.fav = !h.fav; await api('/api/highlights/' + encodeURIComponent(h.id) + '/fav', { method: 'PUT', body: JSON.stringify({ fav: h.fav }) }); toast(h.fav ? 'Favorited · it comes back in review more often' : 'No longer a favorite'); R.changed && R.changed(h, 'fav'); return; }
    if (R[a]) { await R[a](ctx, b); return; }
  } catch(err){ toast(err.message); }
}, true);

/* ---------- tags ---------- */
H.loadTags = async () => { if (!H.allTags) { try { H.allTags = (await api('/api/highlights/tags')).tags; } catch(e){ H.allTags = []; } } return H.allTags; };
// Tags for a highlight, or (with o.url and o.all) for anything else that has tags, like a document.
H.tagEditor = async (h, rect, done, o) => {
  o = o || {};
  const all = o.all || await H.loadTags(), p = $('#pop'), mark = o.plain ? '' : '#';
  let tags = (h.tags || []).slice();
  const draw = () => {
    p.innerHTML = '<div class="tagbox"><div class="tagchips">' + tags.map(t => '<span class="tchip">' + mark + esc(t) + '<button data-tagrm="' + esc(t) + '" aria-label="Remove ' + esc(t) + '">×</button></span>').join('') +
      '<input id="tagin" class="tagin" placeholder="' + (tags.length ? 'Another tag' : 'Add a tag') + '" autocomplete="off" autocapitalize="none" spellcheck="false"></div>' +
      '<div class="tagsugg" id="tagsugg"></div><div class="taghint mute tiny">' + esc(o.hint || 'Enter adds a tag · tags go to the vault note as #tags') + '</div></div>';
    sugg('');
    setTimeout(() => $('#tagin') && $('#tagin').focus(), 10);
  };
  const sugg = q => {
    const box = $('#tagsugg'); if (!box) return;
    const list = all.filter(t => !tags.includes(t) && (!q || t.toLowerCase().includes(q.toLowerCase()))).slice(0, 8);
    box.innerHTML = list.map(t => '<button data-tagadd="' + esc(t) + '">' + mark + esc(t) + '</button>').join('');
  };
  const save = async () => {
    // Queued offline, the answer is only {queued}: keep the tags as sent, and the list of all tags as it was.
    try { const r = await api(o.url || '/api/highlights/' + encodeURIComponent(h.id) + '/tags', { method: 'PUT', body: JSON.stringify({ tags }) });
      h.tags = r.tags || tags.slice(); if (r.all) { if (o.url) o.all = r.all; else H.allTags = r.all; } done && done(h); }
    catch(e){ toast(e.message); }
  };
  const add = v => { v = (v || '').trim().replace(/^#/, ''); if (!o.plain) v = v.toLowerCase().replace(/\s+/g, '-'); if (v && !tags.includes(v)) { tags.push(v); draw(); save(); } };
  draw();
  p.hidden = false; p.style.left = Math.max(8, Math.min(window.innerWidth - 300, rect.left)) + 'px'; p.style.top = Math.min(window.innerHeight - 220, rect.bottom + 8) + 'px';
  p.onclick = e => {
    const rm = e.target.closest('[data-tagrm]'); if (rm) { tags = tags.filter(t => t !== rm.dataset.tagrm); draw(); save(); return; }
    const ad = e.target.closest('[data-tagadd]'); if (ad) { add(ad.dataset.tagadd); }
  };
  p.oninput = e => { if (e.target.id === 'tagin') sugg(e.target.value); };
  p.onkeydown = e => {
    if (e.target.id !== 'tagin') return;
    if (e.key === 'Enter' || e.key === ',') { e.preventDefault(); add(e.target.value); }
    else if (e.key === 'Backspace' && !e.target.value && tags.length) { tags.pop(); draw(); save(); }
    else if (e.key === 'Escape') { p.hidden = true; p.onclick = p.oninput = p.onkeydown = null; }
  };
};
// Close the tag editor on a click elsewhere, but only if it was open before that click.
document.addEventListener('click', e => {
  const p = $('#pop');
  if (p && !p.hidden && p.querySelector('.tagbox') && C.S.popAtClick != null && p.innerHTML === C.S.popAtClick && !e.target.closest('#pop')) p.hidden = true;
});

/* ---------- read aloud: the sentence being spoken ---------- */
// Marks the sentence Kokoro is on with the CSS Custom Highlight API: no change to the page's DOM,
// so highlight marks and the shells' buttons stay as they are. Kokoro speaks at an even pace, so
// the place in the audio maps to a place in the text by characters (plus a pause per sentence).
// Returns a function that stops following. Works in the article view and in the book's iframe.
H.follow = (audio, el, opts) => {
  opts = opts || {};
  const doc = el && el.ownerDocument, win = doc && doc.defaultView;
  if (!audio || !win || !win.CSS || !win.CSS.highlights || typeof win.Highlight !== 'function') return () => {};
  const nodes = []; let total = 0;
  const w = doc.createTreeWalker(el, win.NodeFilter.SHOW_TEXT);
  for (let n = w.nextNode(); n; n = w.nextNode()) { nodes.push([n, total]); total += n.data.length; }
  const text = nodes.map(x => x[0].data).join('');
  const ends = [], re = /[.!?…׃]+["'”’»)\]]*\s+/g;
  for (let m = re.exec(text); m; m = re.exec(text)) ends.push(m.index + m[0].length);
  if (!ends.length || ends[ends.length - 1] < text.length) ends.push(text.length);
  if (ends.length < 2) return () => {};                 // one sentence: the paragraph's own mark says it
  const starts = [0].concat(ends.slice(0, -1));
  const weights = starts.map((s0, i) => ends[i] - s0 + 14), W = weights.reduce((a, b) => a + b, 0);
  const at = off => { for (let i = nodes.length - 1; i >= 0; i--) if (nodes[i][1] <= off) return [nodes[i][0], Math.min(off - nodes[i][1], nodes[i][0].data.length)]; return [nodes[0][0], 0]; };
  let cur = -1;
  const show = () => {
    if (!audio.duration || !isFinite(audio.duration)) return;
    let t = audio.currentTime / audio.duration * W, k = 0;
    while (k < weights.length - 1 && t > weights[k]) { t -= weights[k]; k++; }
    if (k === cur) return;
    cur = k;
    let s0 = starts[k], e0 = ends[k];
    while (s0 < e0 && /\s/.test(text[s0])) s0++;
    while (e0 > s0 && /\s/.test(text[e0 - 1])) e0--;
    const r = doc.createRange(), a = at(s0), b = at(e0);
    try { r.setStart(a[0], a[1]); r.setEnd(b[0], b[1]); } catch(e){ return; }
    win.CSS.highlights.set('daf-speaking', new win.Highlight(r));
    if (opts.scroll) {
      // Long paragraphs: keep the sentence on screen.
      const rc = r.getBoundingClientRect();
      if (rc.bottom > win.innerHeight - 110 || rc.top < 70) {
        let sc = el.parentElement; while (sc && sc !== doc.body && !(sc.scrollHeight > sc.clientHeight + 4 && /auto|scroll/.test(win.getComputedStyle(sc).overflowY))) sc = sc.parentElement;
        const target = sc && sc !== doc.body ? sc : doc.scrollingElement;
        target.scrollBy({ top: rc.top - win.innerHeight * 0.4, behavior: 'smooth' });
      }
    }
  };
  audio.addEventListener('timeupdate', show);
  show();
  return () => { audio.removeEventListener('timeupdate', show); try { win.CSS.highlights.delete('daf-speaking'); } catch(e){} };
};

/* ---------- share as image ---------- */
H.share = async (h, meta) => {
  meta = meta || {};
  const W = 1080, Hh = 1350, pad = 96, cv = document.createElement('canvas'); cv.width = W; cv.height = Hh;
  const x = cv.getContext('2d'), text = (h.text || '').trim().replace(/\s+\n/g, '\n');
  const rtl = /[֐-׿]/.test(text), tok = H.tok(h.color || 'yellow');
  try { await document.fonts.load('400 40px "Source Serif 4"'); await document.fonts.load('600 26px Figtree'); } catch(e){}
  x.fillStyle = '#fbf8f1'; x.fillRect(0, 0, W, Hh);
  let size = text.length > 700 ? 30 : text.length > 420 ? 36 : text.length > 220 ? 44 : text.length > 110 ? 52 : 60;
  const wrap = s => { x.font = '400 ' + size + 'px "Source Serif 4", Georgia, serif'; const out = []; for (const para of s.split(/\n+/)) { let line = ''; for (const w of para.split(/\s+/)) { const t = line ? line + ' ' + w : w; if (x.measureText(t).width > W - pad * 2 && line) { out.push(line); line = w; } else line = t; } out.push(line); out.push(''); } out.pop(); return out; };
  let ls = wrap(text);
  while (ls.length * size * 1.42 > Hh - pad * 2 - 200 && size > 22) { size -= 2; ls = wrap(text); }
  if (ls.length * size * 1.42 > Hh - pad * 2 - 200) { const keep = Math.floor((Hh - pad * 2 - 200) / (size * 1.42)); ls = ls.slice(0, keep); ls[keep - 1] = ls[keep - 1].replace(/\s*\S*$/, '…'); }
  // The quote sits in the middle of the space above the title, with the highlight's color beside it.
  const blockH = ls.reduce((h, l) => h + (l ? size * 1.42 : size * 0.6), 0), avail = Hh - pad * 2 - 180;
  let y = pad + Math.max(0, (avail - blockH) / 2);
  x.fillStyle = tok.line || '#efc93d'; x.fillRect(rtl ? W - pad + 28 : pad - 36, y, 8, blockH - size * 0.3);
  x.fillStyle = '#1d2127'; x.textBaseline = 'top'; x.direction = rtl ? 'rtl' : 'ltr'; x.textAlign = rtl ? 'right' : 'left';
  ls.forEach(l => { x.fillText(l, rtl ? W - pad : pad, y); y += l ? size * 1.42 : size * 0.6; });
  x.direction = 'ltr'; x.textAlign = 'left';
  const title = shortTitle(meta.title || h.book_title || h.title || ''), author = meta.author || h.book_author || h.author || '';
  x.fillStyle = '#e4ddcf'; x.fillRect(pad, Hh - pad - 120, W - pad * 2, 2);
  x.fillStyle = '#1d2127'; x.font = '600 32px Figtree, system-ui, sans-serif'; x.fillText(title.slice(0, 56), pad, Hh - pad - 80);
  x.fillStyle = '#6b717a'; x.font = '400 28px Figtree, system-ui, sans-serif'; x.fillText(author.slice(0, 64), pad, Hh - pad - 34);
  x.fillStyle = '#9aa0a8'; x.font = '600 26px Figtree, system-ui, sans-serif'; x.textAlign = 'right'; x.fillText('Daf', W - pad, Hh - pad - 34);
  const blob = await new Promise(r => cv.toBlob(r, 'image/png'));
  const url = URL.createObjectURL(blob), file = new File([blob], 'highlight.png', { type: 'image/png' });
  $('#scrim').hidden = false; const m = $('#modal'); m.hidden = false; m.classList.add('wide');
  m.innerHTML = '<h2>Share as image</h2><img class="shareimg" src="' + url + '" alt="The highlight as an image"><div class="shareacts">' +
    (navigator.canShare && navigator.canShare({ files: [file] }) ? '<button class="btn primary" id="shnative">Share…</button>' : '') +
    (window.ClipboardItem ? '<button class="btn" id="shcopy">Copy image</button>' : '') + '<a class="btn" href="' + url + '" download="' + esc((title || 'highlight').replace(/[^\w\- ]+/g, '').slice(0, 40) || 'highlight') + '.png">Download</a><button class="btn" data-act="close">Close</button></div>';
  const n = $('#shnative'); if (n) n.onclick = () => navigator.share({ files: [file] }).catch(() => {});
  const cp = $('#shcopy'); if (cp) cp.onclick = () => navigator.clipboard.write([new ClipboardItem({ 'image/png': blob })]).then(() => toast('Image copied'), () => toast('Couldn’t copy the image'));
};

/* ---------- flashcards (Readwise's Mastery) ---------- */
// A cloze hides words of the highlight ({{like this}}); a question card asks for the idea.
H.renderFront = (c, shown) => {
  if (c.kind === 'qa') return esc(c.front);
  return esc(c.front).replace(/\{\{(.+?)\}\}/gs, (m, w) => shown ? '<mark class="creveal">' + w + '</mark>' : '<span class="cblank" style="min-width:' + Math.min(14, Math.max(3, w.length * 0.55)) + 'em"></span>');
};
H.cardEditor = async (x, done) => {
  $('#scrim').hidden = false; const m = $('#modal'); m.hidden = false; m.classList.add('wide');
  m.innerHTML = '<h2>Flashcard</h2><span class="mute">Loading…</span>';
  let list = []; try { list = (await api('/api/highlights/' + encodeURIComponent(x.id) + '/cards')).cards; } catch(e){}
  const text = String(x.text || '').trim();
  const words = text.split(/(\s+)/);
  let mode = 'cloze', hidden = new Set(), editing = null, q = '', a = text;
  const clozeText = () => { let out = '', open = false; words.forEach((w, i) => { const hid = hidden.has(i) && /\S/.test(w); if (/\s/.test(w)) { const nextHid = hidden.has(i + 1); if (open && !nextHid) { out += '}}'; open = false; } out += w; return; } if (hid && !open) { out += '{{'; open = true; } if (!hid && open) { out += '}}'; open = false; } out += w; }); if (open) out += '}}'; return out; };
  const fromCloze = s => { hidden = new Set(); let i = 0, inb = false; const parts = s.split(/(\{\{|\}\})/); const flat = []; parts.forEach(p => { if (p === '{{') inb = true; else if (p === '}}') inb = false; else p.split(/(\s+)/).forEach(w => { if (w) flat.push([w, inb]); }); }); flat.forEach(([w, b]) => { if (b && /\S/.test(w)) hidden.add(i); i++; }); };
  const draw = () => {
    m.innerHTML = '<h2>Flashcard</h2>' +
      (list.length ? '<div class="clist">' + list.map(c => '<div class="citem"><span>' + H.renderFront(c, true) + (c.kind === 'qa' ? ' <span class="mute">→ ' + esc(c.back || '') + '</span>' : '') + '</span><span class="mute tiny">' + (c.due ? 'next ' + c.due : 'new') + '</span><button class="linkbtn tiny" data-cedit="' + c.id + '">Edit</button><button class="linkbtn tiny danger" data-cdel="' + c.id + '">Delete</button></div>').join('') + '</div>' : '') +
      '<div class="seg" role="radiogroup"><button type="button" class="' + (mode === 'cloze' ? 'on' : '') + '" data-cmode="cloze">Fill in the blank</button><button type="button" class="' + (mode === 'qa' ? 'on' : '') + '" data-cmode="qa">Question</button></div>' +
      (mode === 'cloze' ? '<span class="mute tiny">Tap the words to hide.</span><div class="cwords">' + words.map((w, i) => /\s/.test(w) ? w : '<span class="cw' + (hidden.has(i) ? ' on' : '') + '" data-cw="' + i + '">' + esc(w) + '</span>').join('') + '</div>'
        : '<label class="mute tiny" for="cq">Question</label><input class="field" id="cq" value="' + esc(q) + '" placeholder="What does it say about…?"><label class="mute tiny" for="ca">Answer</label><textarea class="field" id="ca" rows="3">' + esc(a) + '</textarea>') +
      '<div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center"><button class="btn sm" id="csuggest">' + IC.ask + ' Suggest a card</button><span class="spacer"></span><button class="btn" data-act="close">Close</button><button class="btn primary" id="csave">' + (editing ? 'Save the card' : 'Add the card') + '</button></div>' +
      '<div id="cstatus" class="tiny mute" role="status"></div>';
  };
  draw();
  m.onclick = async e => {
    const w = e.target.closest('[data-cw]'); if (w) { const i = +w.dataset.cw; hidden.has(i) ? hidden.delete(i) : hidden.add(i); w.classList.toggle('on'); return; }
    const md = e.target.closest('[data-cmode]'); if (md) { if (mode === 'qa') { q = $('#cq').value; a = $('#ca').value; } mode = md.dataset.cmode; draw(); return; }
    const ed = e.target.closest('[data-cedit]'); if (ed) { const c = list.find(y => y.id === ed.dataset.cedit); editing = c.id; mode = c.kind; if (c.kind === 'cloze') fromCloze(c.front); else { q = c.front; a = c.back || ''; } draw(); return; }
    const dl = e.target.closest('[data-cdel]'); if (dl) { await api('/api/cards/' + encodeURIComponent(dl.dataset.cdel), { method: 'DELETE' }); list = list.filter(y => y.id !== dl.dataset.cdel); x.cards = list.length; draw(); done && done(); return; }
    if (e.target.closest('#csuggest')) {
      const st = $('#cstatus'); st.textContent = 'Thinking…'; e.target.closest('#csuggest').disabled = true;
      try { const r = await api('/api/highlights/' + encodeURIComponent(x.id) + '/cards/suggest', { method: 'POST' }); if (r.cloze) fromCloze(r.cloze); q = r.question || q; a = r.answer || a; draw(); $('#cstatus').textContent = 'A suggestion: hidden words for the blank, and a question. Change anything.'; }
      catch(err){ st.textContent = err.message; }
      const b = $('#csuggest'); if (b) b.disabled = false; return;
    }
    if (e.target.closest('#csave')) {
      const body = mode === 'cloze' ? { kind: 'cloze', front: clozeText() } : { kind: 'qa', front: $('#cq').value, back: $('#ca').value };
      if (editing) body.id = editing;
      try { const r = await api('/api/highlights/' + encodeURIComponent(x.id) + '/cards', { method: 'POST', body: JSON.stringify(body) }); list = r.cards; x.cards = list.length; editing = null; hidden = new Set(); q = ''; a = text; draw(); toast('Card saved · it comes up in your daily review'); done && done(); }
      catch(err){ $('#cstatus').textContent = err.message; }
    }
  };
};

/* ---------- undo ---------- */
H.undo = (msg, fn) => {
  const t = $('#toast'); t.innerHTML = esc(msg) + ' <button class="linkbtn" id="undo">Undo</button>'; t.hidden = false;
  clearTimeout(toast._t); toast._t = setTimeout(() => { t.hidden = true; }, 6000);
  $('#undo').onclick = () => { t.hidden = true; fn().catch(e => toast(e.message)); };
};

/* ---------- rows on the Highlights page, book pages, review ---------- */
const SRC = { kindle: 'Kindle', epub: 'Daf', daf: 'Daf', karakeep: 'Karakeep', audiobookshelf: 'Audiobook', paper: 'Paper', clip: 'Podcast clip', readwise: 'Readwise' };
H.srcName = s => SRC[s] || 'Kindle';
H.where = x => {
  const p = (() => { try { return typeof x.pos === 'string' && x.pos.startsWith('{') ? JSON.parse(x.pos) : (x.pos && typeof x.pos === 'object' ? x.pos : {}); } catch(e){ return {}; } })();
  if (p.fraction != null) return Math.round(p.fraction * 100) + '%';
  if (p.t != null) { const t = Math.round(p.t); return Math.floor(t / 3600) ? Math.floor(t / 3600) + ':' + String(Math.floor(t % 3600 / 60)).padStart(2, '0') + ':' + String(t % 60).padStart(2, '0') : Math.floor(t / 60) + ':' + String(t % 60).padStart(2, '0'); }
  return x.page ? 'p. ' + x.page : '';
};
H.row = (x, o = {}) => {
  H.reg.set(x.id, x);
  const rtl = /[֐-׿]/.test(x.text || ''), c = x.color || 'yellow', text = String(x.text || '').replace(/[^\S\n]*\n(?:[^\S\n]*\n)+/g, '\n').trim();
  const noteFrom = { readwise: 'In Readwise', karakeep: 'In Karakeep', audiobookshelf: 'In Audiobookshelf' }[x.source] || 'On the Kindle';
  const notes = (x.note ? '<div class="hnote"><span class="mute tiny">' + noteFrom + '</span> ' + esc(x.note) + '</div>' : '') +
    '<div class="hnote mine' + (x.user_note ? '' : ' empty') + '" data-hra="note">' + (x.user_note ? esc(x.user_note) : '') + '</div>';
  const meta = [o.chapter === false ? '' : x.chapter, H.where(x), o.date === false ? '' : epochDate(x.created), H.srcName(x.source), x.r_status === 'never' ? 'not in review' : '', x.cards ? x.cards + ' flashcard' + (x.cards > 1 ? 's' : '') : ''].filter(Boolean).map(esc).join(' · ');
  return '<article class="hrow" data-h="' + esc(x.id) + '" data-color="' + c + '">' +
    '<div class="hq"' + (rtl ? ' dir="rtl"' : '') + (x.open ? ' data-open="' + esc(x.open) + '" title="Open at this spot" role="link" tabindex="0"' : '') + '>' + H.quote(text) + '</div>' + notes +
    '<div class="hmeta"><span class="mute tiny">' + meta + '</span>' + (x.tags && x.tags.length ? '<span class="htags">' + x.tags.map(t => '<a href="#highlights" data-tagf="' + esc(t) + '">#' + esc(t) + '</a>').join('') + '</span>' : '') +
    (x.fav ? '<span class="hfav" title="Favorite">' + IC.heart + '</span>' : '') + '<span class="spacer"></span><span class="hacts">' +
    (x.open ? '<a class="hb" href="' + esc(x.open) + '" data-tip="Open at this spot">' + IC.open + '</a>' : '') +
    '<button class="hb" data-hra="note" data-tip="Note">' + IC.note + '</button><button class="hb" data-hra="tag" data-tip="Tags">' + IC.tag + '</button>' +
    '<button class="hb' + (x.fav ? ' on' : '') + '" data-hra="fav" data-tip="' + (x.fav ? 'Unfavorite' : 'Favorite') + '">' + IC.heart + '</button>' +
    '<button class="hb" data-hra="more" data-tip="More">' + IC.more + '</button></span></div></article>';
};
function rowEl(id){ return $('.hrow[data-h="' + CSS.escape(id) + '"]'); }
// Readwise's inline tags: ".shame" in a note becomes the tag "shame" once you're done typing it.
H.dotTags = t => [...String(t || '').matchAll(/(^|\s)\.(\p{L}[\p{L}\p{N}_-]*)/gu)].map(m => m[2].toLowerCase());
H.noteTags = async (x, text) => {
  const add = H.dotTags(text).filter(t => !(x.tags || []).includes(t));
  if (!add.length) return false;
  const tags = (x.tags || []).concat(add);
  const r = await api('/api/highlights/' + encodeURIComponent(x.id) + '/tags', { method: 'PUT', body: JSON.stringify({ tags }) });
  x.tags = r.tags || tags; if (r.all) H.allTags = r.all; toast('Tagged ' + add.map(t => '#' + t).join(' ')); return true;
};
const changed = x => window.dispatchEvent(new CustomEvent('daf-hl-changed', { detail: { id: x.id, color: x.color, user_note: x.user_note, tags: x.tags, fav: x.fav } }));
function redrawRow(x){ const el = rowEl(x.id); if (el) el.outerHTML = H.row(x, H.rowOpts || {}); changed(x); }
function editNote(x){
  const el = rowEl(x.id); if (!el) return;
  const n = el.querySelector('.hnote.mine'); if (!n || n.querySelector('textarea')) return;
  n.classList.remove('empty');
  n.innerHTML = '<textarea class="field" rows="2" placeholder="A thought, for the vault note" data-hnote="' + esc(x.id) + '">' + esc(x.user_note || '') + '</textarea>';
  const t = n.querySelector('textarea'); t.focus(); t.setSelectionRange(t.value.length, t.value.length);
}
const noteT = {};
document.addEventListener('input', e => {
  const t = e.target.closest('[data-hnote]'); if (!t) return;
  const x = H.reg.get(t.dataset.hnote); if (!x) return;
  x.user_note = t.value; clearTimeout(noteT[x.id]);
  noteT[x.id] = setTimeout(() => api('/api/highlights/' + encodeURIComponent(x.id) + '/note', { method: 'PUT', body: JSON.stringify({ note: t.value }) }).then(r => (changed(x), toast(t.value.trim() ? (r.vault === 'written' || r.vault === 'unchanged' ? 'Note saved to the vault' : 'Note saved') : 'Note removed'))).catch(err => toast(err.message)), 800);
});
document.addEventListener('focusout', e => {
  const t = e.target.closest && e.target.closest('[data-hnote]'); if (!t) return;
  const x = H.reg.get(t.dataset.hnote); if (!x) return;
  setTimeout(() => { if (document.activeElement !== t) { const n = t.closest('.hnote'); if (n) { n.innerHTML = esc(x.user_note || ''); n.classList.toggle('empty', !(x.user_note || '').trim()); } } }, 150);
  H.noteTags(x, t.value).then(did => { if (did) redrawRow(x); }).catch(() => {});
});
document.addEventListener('click', async e => {
  const q = e.target.closest('.hrow .hq[data-open]');
  if (q && !window.getSelection().toString()) { location.hash = q.dataset.open.slice(1); return; }
  const tf = e.target.closest('[data-tagf]'); if (tf) { e.preventDefault(); C.S.hlTag = tf.dataset.tagf; if (C.S.route[0] === 'highlights' && C.drawHighlights) C.drawHighlights(); else location.hash = 'highlights'; return; }
  const b = e.target.closest('[data-hra]'); if (!b) return;
  const row = b.closest('[data-h]'); const x = row && H.reg.get(row.dataset.h); if (!x) return;
  const a = b.dataset.hra;
  try {
    if (a === 'note') editNote(x);
    else if (a === 'tag') H.tagEditor(x, b.getBoundingClientRect(), () => redrawRow(x));
    else if (a === 'fav') { x.fav = !x.fav; await api('/api/highlights/' + encodeURIComponent(x.id) + '/fav', { method: 'PUT', body: JSON.stringify({ fav: x.fav }) }); redrawRow(x); toast(x.fav ? 'Favorited · it comes back in review more often' : 'No longer a favorite'); }
    else if (a === 'more') {
      H.ctxRow = x; H.ctxRowEl = b.closest('.hrow');
      menu(b, [{ html: '<div class="mdots">' + COLORS.map(c => '<button class="cdot' + ((x.color || 'yellow') === c ? ' on' : '') + '" data-hrc="' + c + '" aria-label="' + c + '" style="--c:var(--hl-' + c + '-line)"></button>').join('') + '</div>' },
        ...(H.picture(x.text) ? [] : [{ a: 'rowcard', label: x.cards ? 'Flashcards (' + x.cards + ')' : 'Make a flashcard' }]), { a: 'rowcopy', label: 'Copy text' }, ...(H.picture(x.text) ? [] : [{ a: 'rowshare', label: 'Share as image' }]), ...(x.open ? [{ a: 'rowopen', label: 'Open at this spot' }] : []),
        x.r_status === 'never' ? { a: 'rowback', label: 'Back into review' } : { a: 'rownever', label: 'Never show in review' },
        ...(['epub', 'daf', 'paper'].includes(x.source) ? ['-', { a: 'rowrm', label: 'Delete highlight' }] : [])]);
    }
  } catch(err){ toast(err.message); }
});
document.addEventListener('click', async e => {
  const x = H.ctxRow; if (!x) return;
  const c = e.target.closest('#pop [data-hrc]'), m = e.target.closest('#pop [data-hm^="row"]');
  if (!c && !m) return;
  $('#pop').hidden = true; H.ctxRow = null;
  try {
    if (c) { x.color = c.dataset.hrc; await api('/api/highlights/' + encodeURIComponent(x.id) + '/color', { method: 'PUT', body: JSON.stringify({ color: x.color }) }); redrawRow(x); return; }
    const a = m.dataset.hm;
    if (a === 'rowcopy') navigator.clipboard.writeText(x.text).then(() => toast('Copied'), () => {});
    else if (a === 'rowshare') H.share(x);
    else if (a === 'rowcard') H.cardEditor(x, () => redrawRow(x));
    else if (a === 'rowopen') location.hash = x.open.slice(1);
    else if (a === 'rownever' || a === 'rowback') { await api('/api/review/' + encodeURIComponent(x.id), { method: 'POST', body: JSON.stringify({ action: a === 'rownever' ? 'never' : 'back' }) }); x.r_status = a === 'rownever' ? 'never' : 'kept'; redrawRow(x); toast(a === 'rownever' ? 'It won’t come up in review again' : 'Back in review'); }
    else if (a === 'rowrm') {
      // In a reader's Notebook, the reader removes it: from the text too, with its own Undo.
      const inReader = H.ctxRowEl && H.ctxRowEl.closest('.rpanel') && H.active && H.active.rm;
      if (inReader) { await H.active.rm({ h: x }); return; }
      await api('/api/highlights/' + encodeURIComponent(x.id), { method: 'DELETE' });
      const el = rowEl(x.id); if (el) el.remove();
      H.undo('Highlight deleted', async () => { await api('/api/highlights/' + encodeURIComponent(x.id) + '/restore', { method: 'POST' }); if (C.S.route[0] === 'highlights' && C.drawHighlights) C.drawHighlights(); else window.dispatchEvent(new Event('hashchange')); });
    }
  } catch(err){ toast(err.message); }
}, true);
document.addEventListener('keydown', e => { const q = e.target.closest && e.target.closest('.hq[data-open]'); if (q && e.key === 'Enter') location.hash = q.dataset.open.slice(1); });

// Flash a row or a mark that a link pointed at.
H.flash = el => { if (!el) return; el.scrollIntoView({ block: 'center', behavior: 'smooth' }); el.classList.add('flash'); setTimeout(() => el.classList.remove('flash'), 1800); };
})();
