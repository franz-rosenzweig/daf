/* The PDF as printed: pages drawn by pdf.js (vendored in web/vendor/pdfjs), with a text layer to
   select and highlight on, like Readwise Reader's PDF view (#pdf/<doc>[/hl:<id>]).
   A highlight made here keeps its page and boxes (pos.pdf) and, when its words are in the text
   view too, its place there, so it shows in both. Highlights made in the text view are found on
   the page by their words. Time here counts as reading, and the page read is the progress. */
import * as pdfjs from './vendor/pdfjs/pdf.min.mjs';

pdfjs.GlobalWorkerOptions.workerSrc = '/vendor/pdfjs/pdf.worker.min.mjs';
const C = window.DafCore, { api, esc, toast, $, $$ } = C, H = C.HL;
const P = { id: null, d: null, pdf: null, zoom: 1, base: 1, rendered: new Map(), obs: null, active: Date.now(), page: 1, saveT: 0, found: new Map() };
const store = { get(k, d){ try { const v = localStorage.getItem('daf.' + k); return v == null ? d : JSON.parse(v); } catch(e){ return d; } }, set(k, v){ try { localStorage.setItem('daf.' + k, JSON.stringify(v)); } catch(e){} } };

C.views.pdf = async args => {
  const last = args[args.length - 1] || '', hl = last.startsWith('hl:') && args.length > 1 ? decodeURIComponent(last.slice(3)) : null;
  const id = decodeURIComponent((hl ? args.slice(0, -1) : args).join('/'));
  H.active = ACT;
  if (P.id === id && P.pdf && $('#pdfpages')) { if (hl) goToHl(hl); return; }
  close();
  P.id = id;
  $('#main').innerHTML = '<div class="pdfv"><div class="top" id="ptop"><a class="btn sm" href="#read/' + encodeURIComponent(id) + '" title="The text view" aria-label="Back to the text">' + C.I.back + '</a>' +
    '<h1 id="ptitle">PDF</h1><span class="spacer"></span><span class="mute tiny" id="ppg"></span>' +
    '<button class="btn sm" data-pv="out" aria-label="Smaller" title="Smaller (−)">−</button><button class="btn sm" data-pv="in" aria-label="Larger" title="Larger (+)">+</button>' +
    '<a class="btn sm" href="#read/' + encodeURIComponent(id) + '" title="The text, reflowed">Text</a>' +
    '<a class="btn sm" href="/api/docs/' + encodeURIComponent(id) + '/pdf" download title="The PDF file">Download</a></div>' +
    '<div class="pdfpages" id="pdfpages"><span class="mute" style="padding:24px">Opening the PDF…</span></div></div>';
  try { P.d = await api('/api/docs/' + encodeURIComponent(id) + '?prefetch=1'); } catch(e){ $('#pdfpages').innerHTML = '<p class="mute" style="padding:24px">' + esc(e.message) + '</p>'; return; }
  if (P.id !== id) return;
  $('#ptitle').textContent = P.d.title || 'PDF';
  try {
    P.pdf = await pdfjs.getDocument({ url: '/api/docs/' + encodeURIComponent(id) + '/pdf', withCredentials: true,
      standardFontDataUrl: '/vendor/pdfjs/standard_fonts/', cMapUrl: '/vendor/pdfjs/cmaps/', cMapPacked: true }).promise;
  } catch(e){ $('#pdfpages').innerHTML = '<p class="mute" style="padding:24px">Daf couldn’t open this PDF: ' + esc(e.message) + '</p>'; return; }
  if (P.id !== id) return;
  P.zoom = store.get('pdfZoom', 1);
  await layout();
  const at = hl ? null : store.get('pdfPage.' + id, 0);
  if (hl) goToHl(hl);
  else if (at > 1) scrollToPage(at);
};

// Scroll the pages box itself (not the window) to a page, or to a place on it.
function scrollToPage(pg, frac){
  const box = $('#pdfpages'), el = box && $('.pdfpage[data-pg="' + pg + '"]', box); if (!el) return;
  box.scrollTop = el.offsetTop - 12 + (frac ? frac * el.offsetHeight - box.clientHeight * 0.3 : 0);
}
function close(){
  if (P.obs) P.obs.disconnect();
  if (P.pdf) { try { P.pdf.destroy(); } catch(e){} }
  Object.assign(P, { pdf: null, d: null, obs: null, rendered: new Map(), found: new Map() });
}
window.addEventListener('hashchange', () => { if (!location.hash.startsWith('#pdf/') && P.pdf) close(); });

// Placeholders for every page, sized from page 1; pages are drawn as they come into view.
async function layout(){
  const box = $('#pdfpages'); if (!box || !P.pdf) return;
  const p1 = await P.pdf.getPage(1), v1 = p1.getViewport({ scale: 1 });
  const avail = Math.min(980, box.clientWidth - 32);
  P.base = Math.max(0.4, avail / v1.width);
  const scale = P.base * P.zoom;
  P.rendered = new Map();
  let h = '';
  for (let i = 1; i <= P.pdf.numPages; i++) h += '<div class="pdfpage" data-pg="' + i + '" style="width:' + Math.round(v1.width * scale) + 'px;height:' + Math.round(v1.height * scale) + 'px"><span class="pgn">' + i + '</span></div>';
  box.innerHTML = h;
  if (P.obs) P.obs.disconnect();
  P.obs = new IntersectionObserver(es => es.forEach(e => {
    const pg = +e.target.dataset.pg;
    if (e.isIntersecting && !P.rendered.has(pg)) renderPage(pg, e.target);
  }), { root: box, rootMargin: '900px 0px' });
  $$('.pdfpage', box).forEach(el => P.obs.observe(el));
  box.onscroll = onScroll;
  onScroll();
}

async function renderPage(pg, el){
  P.rendered.set(pg, true);
  const page = await P.pdf.getPage(pg), scale = P.base * P.zoom, vp = page.getViewport({ scale }), dpr = window.devicePixelRatio || 1;
  el.style.width = Math.round(vp.width) + 'px'; el.style.height = Math.round(vp.height) + 'px';
  el.style.setProperty('--scale-factor', scale);
  const cv = document.createElement('canvas');
  cv.width = Math.floor(vp.width * dpr); cv.height = Math.floor(vp.height * dpr);
  cv.style.width = Math.round(vp.width) + 'px'; cv.style.height = Math.round(vp.height) + 'px';
  const marks = document.createElement('div'); marks.className = 'pmarks';
  const tl = document.createElement('div'); tl.className = 'textLayer';
  el.replaceChildren(cv, marks, tl);
  await page.render({ canvasContext: cv.getContext('2d'), viewport: vp, transform: dpr !== 1 ? [dpr, 0, 0, dpr, 0, 0] : null }).promise;
  try { await new pdfjs.TextLayer({ textContentSource: page.streamTextContent(), container: tl, viewport: vp }).render(); } catch(e){}
  drawMarks(pg);
}

/* ---------- highlights on a page ---------- */
const norm = s => String(s || '').replace(/­/g, '').replace(/-\s+(?=\p{Ll})/gu, '').replace(/\s+/g, ' ').trim();
// Where a text-view highlight's words are on this page: rects as fractions of the page.
function findOnPage(pg, text){
  const el = $('.pdfpage[data-pg="' + pg + '"]'), tl = el && el.querySelector('.textLayer'); if (!tl) return null;
  const nodes = [], walk = document.createTreeWalker(tl, NodeFilter.SHOW_TEXT);
  let flat = '';
  for (let n = walk.nextNode(); n; n = walk.nextNode()) { if (flat && !/\s$/.test(flat)) flat += ' '; nodes.push([n, flat.length]); flat += n.data; }
  const want = norm(text); if (want.length < 8) return null;
  // Index from the normalized page text back to the raw one, character by character.
  const map = []; let out = '';
  for (let i = 0; i < flat.length; i++) {
    const ch = flat[i];
    if (/\s/.test(ch)) { if (out && !out.endsWith(' ')) { out += ' '; map.push(i); } continue; }
    if (ch === '­') continue;
    out += ch; map.push(i);
  }
  let at = out.indexOf(want), len = want.length;
  if (at < 0 && want.length > 60) { at = out.indexOf(want.slice(0, 60)); len = at < 0 ? 0 : Math.min(out.length - at, want.length); }
  if (at < 0) return null;
  const pos = i => { for (let k = nodes.length - 1; k >= 0; k--) if (nodes[k][1] <= i) return [nodes[k][0], Math.min(i - nodes[k][1], nodes[k][0].data.length)]; return [nodes[0][0], 0]; };
  const r = document.createRange(), a = pos(map[at]), b = pos(map[Math.min(map.length - 1, at + len - 1)] + 1);
  try { r.setStart(a[0], a[1]); r.setEnd(b[0], b[1]); } catch(e){ return null; }
  return rectsOf(r, el);
}
function rectsOf(range, el){
  const box = el.getBoundingClientRect(), out = [];
  for (const q of range.getClientRects()) {
    if (q.width < 1 || q.height < 2) continue;
    out.push([(q.left - box.left) / box.width, (q.top - box.top) / box.height, q.width / box.width, q.height / box.height].map(v => Math.round(v * 1e5) / 1e5));
  }
  // Merge pieces on one line, as the text layer splits words into spans.
  out.sort((a, b) => a[1] - b[1] || a[0] - b[0]);
  const merged = [];
  for (const r of out) {
    const m = merged[merged.length - 1];
    if (m && Math.abs(m[1] - r[1]) < r[3] * 0.5 && r[0] <= m[0] + m[2] + 0.01) { const right = Math.max(m[0] + m[2], r[0] + r[2]); m[2] = right - m[0]; m[3] = Math.max(m[3], r[3]); }
    else merged.push(r.slice());
  }
  return merged;
}
function placeOf(h){
  const p = h.pos || {};
  if (p.pdf) return p.pdf;
  const f = P.found.get(h.id); if (f) return f;
  return null;
}
function drawMarks(pg){
  const el = $('.pdfpage[data-pg="' + pg + '"]'), box = el && el.querySelector('.pmarks'); if (!box || !P.d) return;
  let html = '';
  for (const h of P.d.highlights || []) {
    let pl = placeOf(h);
    if (!pl && !P.found.has(h.id)) { const r = findOnPage(pg, h.text); if (r && r.length) { pl = { pg, r }; P.found.set(h.id, pl); } }
    if (!pl || pl.pg !== pg) continue;
    html += pl.r.map(r => '<i class="pmark" data-h="' + esc(h.id) + '" data-color="' + esc(h.color || 'yellow') + '"' + ((h.user_note || '').trim() ? ' data-note="1"' : '') +
      ' style="left:' + (r[0] * 100) + '%;top:' + (r[1] * 100) + '%;width:' + (r[2] * 100) + '%;height:' + (r[3] * 100) + '%"></i>').join('');
  }
  box.innerHTML = html;
}
function redrawAll(){ for (const pg of P.rendered.keys()) drawMarks(pg); }

/* ---------- selecting and highlighting ---------- */
document.addEventListener('mouseup', e => { if (C.S.route[0] === 'pdf' && !e.target.closest('#selbar, #pop')) setTimeout(() => onSelect(e), 10); });
document.addEventListener('touchend', e => { if (C.S.route[0] === 'pdf' && !e.target.closest('#selbar, #pop')) setTimeout(() => onSelect(e, true), 400); });
function onSelect(e, touch){
  const sel = window.getSelection();
  if (!sel || sel.isCollapsed || !sel.rangeCount) { if (!touch) clickMark(e); return; }
  const range = sel.getRangeAt(0);
  snapWords(range); sel.removeAllRanges(); sel.addRange(range);
  const start = range.startContainer.parentElement && range.startContainer.parentElement.closest('.pdfpage');
  if (!start) return;
  const text = norm(sel.toString()); if (text.length < 2) return;
  const pg = +start.dataset.pg;
  // Only the boxes on the page where the selection starts.
  const endPage = range.endContainer.parentElement && range.endContainer.parentElement.closest('.pdfpage');
  const r1 = document.createRange(); r1.setStart(range.startContainer, range.startOffset);
  if (endPage === start) r1.setEnd(range.endContainer, range.endOffset); else r1.setEnd(start.querySelector('.textLayer'), start.querySelector('.textLayer').childNodes.length);
  const info = { pg, r: rectsOf(r1, start), text };
  const rect = range.getBoundingClientRect();
  if (!touch && H.auto && H.auto() && !e.altKey) { highlight(info); return; }
  H.show(H.selBar({ text }), rect, { kind: 'sel', text, info });
}
function clickMark(e){
  const pageEl = e.target.closest && e.target.closest('.pdfpage'); if (!pageEl) { if (!e.target.closest('#selbar')) H.hide(); return; }
  const hit = [...pageEl.querySelectorAll('.pmark')].find(m => { const q = m.getBoundingClientRect(); return e.clientX >= q.left && e.clientX <= q.right && e.clientY >= q.top && e.clientY <= q.bottom; });
  if (!hit) { H.hide(); return; }
  const h = (P.d.highlights || []).find(x => x.id === hit.dataset.h); if (!h) return;
  H.show(H.hlBar(h), hit.getBoundingClientRect(), { kind: 'hl', h });
}
// Whole words, as everywhere in Daf: a selection that starts or ends inside a word takes all of it.
const WORD = /[\p{L}\p{N}'’\u05be-]/u;
function snapWords(r){
  const a = r.startContainer, b = r.endContainer;
  if (a.nodeType === 3) { let i = r.startOffset; while (i > 0 && WORD.test(a.data[i - 1]) && WORD.test(a.data[i] || ' ')) i--; r.setStart(a, i); }
  if (b.nodeType === 3) { let j = r.endOffset; while (j < b.data.length && WORD.test(b.data[j]) && j > 0 && WORD.test(b.data[j - 1])) j++; r.setEnd(b, j); }
}
// The text view's place for these words, so the highlight shows there as well.
function textPlace(text){
  const words = norm(text).split(' ').filter(Boolean); if (words.length < 2 || !P.d) return null;
  const esc2 = w => w.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const head = new RegExp(words.slice(0, 8).map(esc2).join('\\s+')), tail = new RegExp(words.slice(-5).map(esc2).join('\\s+'));
  for (let i = 0; i < (P.d.blocks || []).length; i++) {
    const full = P.d.blocks[i].x || ''; const m = head.exec(full); if (!m) continue;
    const rest = full.slice(m.index), t = words.length > 8 ? tail.exec(rest) : null;
    return { b: i, s: m.index, e: t ? m.index + t.index + t[0].length : Math.min(full.length, m.index + Math.max(m[0].length, text.length)) };
  }
  return null;
}
async function highlight(info, withNote){
  H.hide(); window.getSelection().removeAllRanges();
  if (!info || !info.r.length) return;
  const place = textPlace(info.text), color = store.get('hlColor', 'yellow');
  const body = Object.assign({ text: info.text, color, pdf: { pg: info.pg, r: info.r } }, place || { b: null, s: null, e: null });
  try {
    const r = await api('/api/docs/' + encodeURIComponent(P.id) + '/highlights', { method: 'POST', body: JSON.stringify(body) });
    const h = { id: r.id, text: info.text, color, pos: Object.assign({}, place || {}, { pdf: { pg: info.pg, r: info.r } }), user_note: '', tags: [] };
    P.d.highlights = (P.d.highlights || []).filter(x => x.id !== h.id).concat([h]);
    drawMarks(info.pg);
    if (withNote) editNote(h);
  } catch(e){ toast(e.message); }
}
function editNote(h){
  const m = $('#modal'); $('#scrim').hidden = false; m.hidden = false;
  m.innerHTML = '<h2>A note</h2><q class="pnq">' + esc(h.text.slice(0, 280)) + '</q><textarea class="field" id="pnote" rows="4" placeholder="Your thought">' + esc(h.user_note || '') + '</textarea>' +
    '<div style="display:flex;gap:8px;justify-content:flex-end"><button class="btn" data-act="close">Cancel</button><button class="btn primary" id="pnsave">Save</button></div>';
  const t = $('#pnote'); t.focus();
  $('#pnsave').onclick = async () => {
    try { await api('/api/highlights/' + encodeURIComponent(h.id) + '/note', { method: 'PUT', body: JSON.stringify({ note: t.value }) }); h.user_note = t.value; C.closeModal(); toast('Saved'); const pl = placeOf(h); if (pl) drawMarks(pl.pg); }
    catch(e){ toast(e.message); }
  };
}
async function removeHl(h){
  H.hide();
  try { await api('/api/highlights/' + encodeURIComponent(h.id), { method: 'DELETE' }); } catch(e){ toast(e.message); return; }
  const pl = placeOf(h);
  P.d.highlights = P.d.highlights.filter(x => x.id !== h.id); P.found.delete(h.id);
  if (pl) drawMarks(pl.pg);
  H.undo && H.undo('Highlight deleted', async () => {
    await api('/api/highlights/' + encodeURIComponent(h.id) + '/restore', { method: 'POST' });
    P.d.highlights.push(h); if (pl) drawMarks(pl.pg);
  });
}
function goToHl(id){
  const h = (P.d && P.d.highlights || []).find(x => x.id === id);
  const go = pl => { scrollToPage(pl.pg, pl.r[0] ? pl.r[0][1] : 0);
    setTimeout(() => $$('.pmark[data-h="' + CSS.escape(id) + '"]').forEach(m => { m.classList.add('flash'); setTimeout(() => m.classList.remove('flash'), 1800); }), 400); };
  if (!h) { toast('That highlight isn’t on these pages'); return; }
  const pl = placeOf(h);
  if (pl) { go(pl); return; }
  toast('Finding it in the pages…');
  (async () => {                                   // a text-view highlight: look page by page
    for (let pg = 1; pg <= P.pdf.numPages; pg++) {
      const el = $('.pdfpage[data-pg="' + pg + '"]');
      if (!P.rendered.has(pg)) await renderPage(pg, el);
      const f = P.found.get(h.id); if (f) { go(f); return; }
    }
    toast('Not found on the pages');
  })();
}
const ACT = {
  hl: ctx => highlight(ctx.info),
  note: ctx => ctx.h ? editNote(ctx.h) : highlight(ctx.info, true),
  rm: ctx => removeHl(ctx.h),
  define: ctx => { H.hide(); C.lookup && C.lookup({ text: ctx.text, rect: $('#selbar').getBoundingClientRect() }, ctx.text, false); },
  translate: ctx => { H.hide(); C.lookup && C.lookup({ text: ctx.text, rect: $('#selbar').getBoundingClientRect() }, ctx.text, true); },
  ask: () => { H.hide(); toast('Ask works in the text view'); location.hash = 'read/' + encodeURIComponent(P.id); },
  notebook: () => { H.hide(); location.hash = 'read/' + encodeURIComponent(P.id); },
  changed: h => { const pl = placeOf(h); if (pl) drawMarks(pl.pg); },
  deselect: () => window.getSelection().removeAllRanges(),
  meta: () => ({ title: P.d && P.d.title, author: P.d && (P.d.author || P.d.source) }),
};

/* ---------- page, zoom, progress, reading time ---------- */
function onScroll(){
  const box = $('#pdfpages'); if (!box || !P.pdf) return;
  const mid = box.getBoundingClientRect().top + box.clientHeight * 0.35;
  const cur = $$('.pdfpage', box).find(el => { const r = el.getBoundingClientRect(); return r.top <= mid && r.bottom >= mid; });
  if (cur) P.page = +cur.dataset.pg;
  const pp = $('#ppg'); if (pp) pp.textContent = 'p. ' + P.page + ' of ' + P.pdf.numPages;
  P.active = Date.now();
  clearTimeout(P.saveT);
  P.saveT = setTimeout(() => {
    if (!P.id || !P.pdf) return;
    store.set('pdfPage.' + P.id, P.page);
    const pct = Math.round(P.page / P.pdf.numPages * 100);
    if (pct > (P.d && P.d.progress || 0)) { P.d.progress = pct; api('/api/docs/' + encodeURIComponent(P.id) + '/progress', { method: 'PUT', body: JSON.stringify({ pct }) }).catch(() => {}); }
  }, 1200);
}
async function zoom(dir){
  const keep = P.page;
  P.zoom = Math.max(0.6, Math.min(2.4, Math.round((P.zoom + dir * 0.15) * 100) / 100));
  store.set('pdfZoom', P.zoom);
  await layout();
  scrollToPage(keep);
}
document.addEventListener('click', e => {
  const b = e.target.closest('[data-pv]'); if (!b || C.S.route[0] !== 'pdf') return;
  if (b.dataset.pv === 'in') zoom(1); else if (b.dataset.pv === 'out') zoom(-1);
});
document.addEventListener('keydown', e => {
  if (C.S.route[0] !== 'pdf' || e.metaKey || e.ctrlKey || e.altKey || /input|textarea|select/i.test(e.target.tagName)) return;
  if (e.key === '+' || e.key === '=') { e.preventDefault(); zoom(1); }
  else if (e.key === '-') { e.preventDefault(); zoom(-1); }
  else if (e.key === 'h' && H.ctx && H.ctx.kind === 'sel') { e.preventDefault(); highlight(H.ctx.info); }
  else if (e.key === 'Escape' && H.visible && H.visible()) H.hide();
});
['mousemove', 'keydown', 'touchstart', 'wheel'].forEach(ev => document.addEventListener(ev, () => { P.active = Date.now(); }, { passive: true }));
setInterval(() => {
  if (C.S.route[0] !== 'pdf' || !P.id || !P.pdf || document.hidden || Date.now() - P.active > 90000) return;
  C.sendBeat && C.sendBeat({ doc_id: P.id, seconds: 15, at: Math.floor(Date.now() / 1000) });
}, 15000);

window.dispatchEvent(new Event('daf-pdf-ready'));
