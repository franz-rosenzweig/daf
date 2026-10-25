/* Daf for the web: highlight on the page you're reading, and the page goes to your Daf Library
   with its highlights.

   A highlight is kept the way Hypothesis keeps one: its words plus up to 32 characters either
   side. The page's text is indexed with the whitespace left out, so a highlight is found again
   after the page changes its markup, and the words either side choose between two places with
   the same words. Highlights are drawn as <daf-hl> elements around the text. */
(() => {
'use strict';
if (window.top !== window || window.__dafExt) return;
window.__dafExt = true;
const X = globalThis.chrome && globalThis.chrome.runtime ? globalThis.chrome : globalThis.browser;
if (!X || !X.runtime) return;

const COLORS = ['yellow', 'green', 'blue', 'pink', 'purple'];
// Daf's highlight tokens (web/style.css --hl-<color> and --hl-<color>-line): a soft fill, a firmer line.
const TOK = {
  light: { yellow: ['#fdf0c0', '#efc83a'], green: ['#dcf1d5', '#72c46c'], blue: ['#d9e8fc', '#6ea7ee'], pink: ['#fbdee9', '#ec84aa'], purple: ['#ebe1f9', '#ab8ae2'] },
  dark: { yellow: ['#3b3213', '#a4832a'], green: ['#1a3522', '#468c50'], blue: ['#182c44', '#4378b6'], pink: ['#3e1c2a', '#ad5277'], purple: ['#2b2240', '#7d62b8'] },
};
const MAC = /Mac|iPhone|iPad/.test(navigator.platform);
const KEY = MAC ? '⌥H' : 'Alt+H';

/* ---------- talking to the extension ---------- */
function send(msg){
  return new Promise((resolve, reject) => {
    const gone = () => reject(Object.assign(new Error('Reload the page to use Daf here.'), { kind: 'reload' }));
    try {
      X.runtime.sendMessage(msg, r => {
        if (X.runtime.lastError || !r) return gone();
        r.ok ? resolve(r.data) : reject(Object.assign(new Error(r.error), { kind: r.kind }));
      });
    } catch (e) { gone(); }
  });
}

/* ---------- the page's text ---------- */
const SKIP = new Set(['SCRIPT', 'STYLE', 'NOSCRIPT', 'TEMPLATE', 'TEXTAREA', 'INPUT', 'SELECT', 'OPTION', 'IFRAME', 'OBJECT',
  'CANVAS', 'svg', 'SVG', 'math', 'MATH', 'HEAD', 'TITLE', 'DAF-EXT']);
const BLOCK = new Set(['P', 'DIV', 'LI', 'UL', 'OL', 'DL', 'DT', 'DD', 'H1', 'H2', 'H3', 'H4', 'H5', 'H6', 'BLOCKQUOTE', 'PRE',
  'TABLE', 'THEAD', 'TBODY', 'TFOOT', 'TR', 'TD', 'TH', 'CAPTION', 'SECTION', 'ARTICLE', 'HEADER', 'FOOTER', 'NAV', 'ASIDE',
  'MAIN', 'FIGURE', 'FIGCAPTION', 'ADDRESS', 'DETAILS', 'SUMMARY', 'FORM', 'FIELDSET', 'LEGEND', 'BODY', 'HTML']);
const SEP = ' ';                       // a block boundary in the index; whitespace to every regex
const isBlank = c => c <= 32 || c === 0xa0 || c === 0x1680 || (c >= 0x2000 && c <= 0x200d) || c === 0x2028 || c === 0x2029 ||
  c === 0x202f || c === 0x205f || c === 0x2060 || c === 0x3000 || c === 0xfeff || c === 0xad;
function fold1(ch){
  const c = ch.charCodeAt(0);
  if (c >= 65 && c <= 90) return String.fromCharCode(c + 32);
  if (c < 128) return ch;
  if (c === 0x2018 || c === 0x2019 || c === 0x201a || c === 0x201b || c === 0x2032) return "'";
  if (c === 0x201c || c === 0x201d || c === 0x201e || c === 0x201f || c === 0x2033) return '"';
  const l = ch.toLowerCase();
  return l.length === 1 ? l : ch;
}
// What two texts are compared by: no whitespace, curly quotes straight, lower case.
function fold(s){ let o = ''; for (let i = 0; i < s.length; i++) if (!isBlank(s.charCodeAt(i))) o += fold1(s[i]); return o; }
// Text for people: blocks become paragraphs, runs of whitespace one space.
const fmt = s => s.replace(/[­​-‍⁠﻿]/g, '').split(SEP).map(p => p.replace(/\s+/g, ' ').trim()).filter(Boolean).join('\n\n');

let idx = null;                                // the index, dropped whenever the page changes
function index(){
  if (idx) return idx;
  const root = document.body || document.documentElement, nodes = [];
  const w = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT | NodeFilter.SHOW_TEXT, { acceptNode(n){
    if (n.nodeType === 3) return NodeFilter.FILTER_ACCEPT;
    return SKIP.has(n.tagName) || n.isContentEditable ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_SKIP;
  } });
  for (let n; (n = w.nextNode());) nodes.push(n);
  const blocks = new Map(), blockOf = el => {
    if (blocks.has(el)) return blocks.get(el);
    let b = el; while (b && !BLOCK.has(b.tagName)) b = b.parentElement;
    blocks.set(el, b); return b;
  };
  const parts = [], start = new Int32Array(nodes.length), map = new Map();
  let len = 0, prev;
  nodes.forEach((n, i) => {
    const b = blockOf(n.parentElement);
    if (i && b !== prev) { parts.push(SEP); len++; }
    prev = b; start[i] = len; map.set(n, i);
    parts.push(n.nodeValue); len += n.nodeValue.length;
  });
  const R = parts.join(''), sR = new Int32Array(R.length), before = new Int32Array(R.length + 1);
  let S = '', m = 0;
  for (let r = 0; r < R.length; r++) {
    before[r] = m;
    if (isBlank(R.charCodeAt(r))) continue;
    S += fold1(R[r]); sR[m++] = r;
  }
  before[R.length] = m;
  return (idx = { nodes, start, map, R, S, sR, before });
}
// The node holding R[r], and where in it.
function nodeAt(ix, r){
  let lo = 0, hi = ix.nodes.length - 1;
  while (lo < hi) { const mid = (lo + hi + 1) >> 1; if (ix.start[mid] <= r) lo = mid; else hi = mid - 1; }
  return [lo, r - ix.start[lo]];
}
// A boundary point of a range, as a place in R.
function rOf(ix, node, off, isEnd){
  const i = node.nodeType === 3 ? ix.map.get(node) : undefined;
  if (i != null) return ix.start[i] + Math.min(off, node.nodeValue.length);
  const pt = document.createRange();
  try { pt.setStart(node, off); } catch (e) { return -1; }
  let lo = 0, hi = ix.nodes.length;             // the first indexed text after the point
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    let c; try { c = pt.comparePoint(ix.nodes[mid], 0); } catch (e) { c = -1; }
    if (c < 0) lo = mid + 1; else hi = mid;
  }
  if (!isEnd) return lo < ix.nodes.length ? ix.start[lo] : ix.R.length;
  return lo > 0 ? ix.start[lo - 1] + ix.nodes[lo - 1].nodeValue.length : 0;
}
// Half a word is never what you meant: grow to whole words, as Daf does.
const isWord = ch => !!ch && /[\p{L}\p{N}\p{M}’'_-]/u.test(ch);
function snap(R, s, e){
  while (s > 0 && isWord(R[s - 1]) && isWord(R[s])) s--;
  while (e < R.length && isWord(R[e - 1]) && isWord(R[e])) e++;
  while (s < e && isBlank(R.charCodeAt(s))) s++;
  while (e > s && isBlank(R.charCodeAt(e - 1))) e--;
  return [s, e];
}

/* ---------- finding a highlight again ---------- */
function around(S, a, b, pre, suf){
  let n = 0;
  for (let i = 1; i <= pre.length && a - i >= 0 && S[a - i] === pre[pre.length - i]; i++) n++;
  for (let i = 0; i < suf.length && b + i < S.length && S[b + i] === suf[i]; i++) n++;
  return n;
}
function locate(ix, q){
  const ex = fold(q.exact || ''), pre = fold(q.prefix || ''), suf = fold(q.suffix || ''), S = ix.S;
  if (!ex) return null;
  let best = null;
  const consider = (a, b, base) => {
    const sc = base + around(S, a, b, pre, suf) - Math.abs(b - a - ex.length);
    if (!best || sc > best.sc) best = { a, b, sc };
  };
  for (let i = S.indexOf(ex), n = 0; i >= 0 && n < 1000; i = S.indexOf(ex, i + 1), n++) consider(i, i + ex.length, 1000);
  if (best) return best;
  // Not there word for word: its first and last words, about as far apart as they were.
  if (ex.length >= 12) {
    const k = Math.min(32, Math.max(6, ex.length >> 2)), head = ex.slice(0, k), tail = ex.slice(-k);
    const lo = Math.floor(ex.length * 0.7), hi = Math.ceil(ex.length * 1.3) + 8;
    for (let i = S.indexOf(head), n = 0; i >= 0 && n < 300; i = S.indexOf(head, i + 1), n++) {
      const t = S.indexOf(tail, Math.max(i + k, i + lo - k));
      if (t >= 0 && t + k - i <= hi) consider(i, t + k, 500);
    }
  }
  // Or the words around it, with about as much between them.
  if (!best && pre.length >= 8 && suf.length >= 8) {
    const p = pre.slice(-16), s = suf.slice(0, 16), lo = Math.floor(ex.length * 0.7), hi = Math.ceil(ex.length * 1.3) + 8;
    for (let i = S.indexOf(p), n = 0; i >= 0 && n < 300; i = S.indexOf(p, i + 1), n++) {
      const a = i + p.length, t = S.indexOf(s, a);
      if (t > a && t - a >= lo && t - a <= hi) consider(a, t, 200);
    }
  }
  return best;
}

/* ---------- drawing ---------- */
let hls = [], seq = 0, busy = 0;
const byKey = k => hls.find(h => h.key === k);
const mo = new MutationObserver(() => { idx = null; if (!busy) later(); });
function quiet(fn){ busy++; try { return fn(); } finally { mo.takeRecords(); busy--; } }

// Several highlights at once: every text node is cut at every edge first (the last cut first, so
// the earlier offsets stay true), then each highlight wraps its pieces.
function draw(ix, items){
  const cuts = new Map();
  const plans = items.map(({ h, a, b }) => {
    const ra = ix.sR[a], rb = ix.sR[b - 1] + 1, [n0, o0] = nodeAt(ix, ra), [n1, o1] = nodeAt(ix, rb - 1), list = [];
    for (let i = n0; i <= n1; i++) {
      const v = ix.nodes[i].nodeValue, s = i === n0 ? o0 : 0, e = i === n1 ? o1 + 1 : v.length;
      if (s >= e || !/\S/.test(v.slice(s, e))) continue;   // whitespace between blocks stays as it is
      list.push([i, s, e]);
      if (!cuts.has(i)) cuts.set(i, new Set());
      if (s > 0) cuts.get(i).add(s);
      if (e < v.length) cuts.get(i).add(e);
    }
    return { h, list, folded: fold(ix.R.slice(ra, rb)) };
  });
  const pieces = new Map();
  for (const [i, set] of cuts) {
    const node = ix.nodes[i], out = [];
    for (const o of [...set].sort((x, y) => y - x)) out.push({ at: o, node: node.splitText(o) });
    out.push({ at: 0, node });
    pieces.set(i, out.reverse());
  }
  for (const { h, list, folded } of plans) {
    const els = [];
    for (const [i, s, e] of list) for (const p of pieces.get(i)) {
      if (p.at >= s && p.at + p.node.nodeValue.length <= e && p.node.parentNode && /\S/.test(p.node.nodeValue)) {
        const w = document.createElement('daf-hl');
        w.setAttribute('data-daf', h.key);
        w.setAttribute('data-color', h.color);
        p.node.parentNode.insertBefore(w, p.node);
        w.appendChild(p.node);
        els.push(w);
      }
    }
    h.els = els; h.folded = folded;
    marks(h);
  }
  idx = null;
}
function unwrap(h){
  for (const w of h.els) {
    const p = w.parentNode; if (!p) continue;
    while (w.firstChild) p.insertBefore(w.firstChild, w);
    p.removeChild(w);
  }
  h.els = [];
}
function marks(h){
  h.els.forEach((w, i) => {
    w.setAttribute('data-color', h.color);
    if (i === h.els.length - 1 && h.note) w.setAttribute('data-note', ''); else w.removeAttribute('data-note');
  });
}
const intact = h => h.els.length && h.els.every(w => w.isConnected) && fold(h.els.map(w => w.textContent).join('')) === h.folded;

function anchor(list){
  if (!list.length) return;
  fresh();
  quiet(() => {
    const ix = index(), items = [];
    for (const h of list) { const m = locate(ix, h.quote); if (m) items.push({ h, a: m.a, b: m.b }); }
    if (items.length) draw(ix, items);
  });
}
// After the page changes (a site that redraws itself): put back what it took away, and try the ones
// not found yet, at most every two seconds.
let repairT = 0, lastTry = 0;
function later(){ clearTimeout(repairT); repairT = setTimeout(repair, 350); }
function repair(){
  if (stopped) return;
  ensureStyle();
  const broken = hls.filter(h => h.els.length && !intact(h));
  if (broken.length) quiet(() => broken.forEach(unwrap));
  const lost = hls.filter(h => !h.els.length && !h.gone);
  if (!lost.length) return;
  const wait = 2000 - (Date.now() - lastTry);
  if (broken.length || wait <= 0) { lastTry = Date.now(); anchor(lost); }
  else { clearTimeout(repairT); repairT = setTimeout(repair, wait); }
}
// Changes the page made a moment ago, before the observer has said so, also make the index old.
function fresh(){ if (mo.takeRecords().length) { idx = null; later(); } }

/* ---------- the look on the page ---------- */
function pageDark(){
  for (const el of [document.body, document.documentElement]) {
    if (!el) continue;
    const m = getComputedStyle(el).backgroundColor.match(/rgba?\(\s*([\d.]+)[,\s]+([\d.]+)[,\s]+([\d.]+)(?:\s*[,/]\s*([\d.]+%?))?/);
    if (!m || (m[4] !== undefined && parseFloat(m[4]) === 0)) continue;
    return (0.299 * m[1] + 0.587 * m[2] + 0.114 * m[3]) / 255 < 0.45;
  }
  return false;
}
let style = null, dark = false;
function ensureStyle(){
  if (style && style.isConnected) return;
  dark = pageDark();
  const t = dark ? TOK.dark : TOK.light;
  style = style || document.createElement('style');
  style.textContent =
    'daf-hl{display:inline;background:var(--daf-f)!important;box-shadow:inset 0 -2px 0 var(--daf-l)!important;color:inherit;' +
    'border-radius:1px;padding:.08em 0 .1em;cursor:pointer;-webkit-box-decoration-break:clone;box-decoration-break:clone;transition:background-color .3s}' +
    'daf-hl daf-hl{padding:0}' +
    COLORS.map(c => 'daf-hl[data-color="' + c + '"]{--daf-f:' + t[c][0] + ';--daf-l:' + t[c][1] + '}').join('') +
    'daf-hl[data-note]::after{content:"";display:inline-block;width:6px;height:6px;border-radius:50%;background:var(--daf-l);vertical-align:super;margin-left:2px}' +
    'daf-hl.daf-flash{background:var(--daf-l)!important}';
  quiet(() => (document.head || document.documentElement).appendChild(style));
}

/* ---------- the bar, the note box, the side panel and the toast (in a shadow root, so the page's styles stay out) ---------- */
const sv = (d, n) => '<svg width="' + (n || 17) + '" height="' + (n || 17) + '" viewBox="0 0 20 20" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">' + d + '</svg>';
const IC = { note: sv('<path d="M4 4.5h12v8.5H9l-4 3v-3H4z"/>'), x: sv('<path d="M6 6l8 8M14 6l-8 8"/>', 15),
  list: sv('<path d="M7 5.5h9M7 10h9M7 14.5h9"/><circle cx="3.8" cy="5.5" r=".6" fill="currentColor"/><circle cx="3.8" cy="10" r=".6" fill="currentColor"/><circle cx="3.8" cy="14.5" r=".6" fill="currentColor"/>') };
const esc = s => String(s == null ? '' : s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]);
const count = n => n === 1 ? '1 highlight' : (n || 'No') + ' highlights';
// The five colors as variables (--c the line, --f the fill), so no element needs a style attribute:
// a page's CSP can refuse those, and Firefox applies it to markup a content script parses.
const colorVars = t => COLORS.map(c => '--c-' + c + ':' + t[c][1] + ';--f-' + c + ':' + t[c][0]).join(';');
const SANS = '-apple-system,BlinkMacSystemFont,"Segoe UI",system-ui,Roboto,sans-serif';
const UICSS = `
:host{all:initial}
.ui{${colorVars(TOK.light)}}
.ui.dark{${colorVars(TOK.dark)}}
${COLORS.map(c => '[data-c="' + c + '"]{--c:var(--c-' + c + ');--f:var(--f-' + c + ')}').join('\n')}
.ui{--bg:#fff;--line:#d6dade;--fg:#1d2127;--fg2:#565d67;--hover:#f0f1f3;--panel:#fafafa;--accent:#1a7da4;--on:#fff;--hf:#fdf0c0;--hl:#efc83a;--chip:#e8f2f6;
  font:500 13.5px/1.25 ${SANS};color:var(--fg);-webkit-font-smoothing:antialiased}
.ui.dark{--bg:#16171a;--line:#3a3e45;--fg:#e7e9ec;--fg2:#a7adb6;--hover:#23252a;--panel:#1a1b1f;--accent:#57b3d7;--on:#0c1a20;--hf:#3b3213;--hl:#a4832a;--chip:#1c2b32}
[hidden]{display:none!important}
button{all:unset;box-sizing:border-box;cursor:pointer;display:inline-flex;align-items:center;justify-content:center;position:relative}
button:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.bar{position:fixed;display:flex;align-items:center;gap:2px;padding:4px;border-radius:999px;background:var(--bg);border:1px solid var(--line);
  box-shadow:0 2px 6px rgba(17,24,39,.08),0 12px 32px rgba(17,24,39,.16)}
.ic{width:34px;height:34px;border-radius:999px;color:var(--fg2)}
.ic:hover{background:var(--hover);color:var(--fg)}
.ic.has{color:var(--accent)}
.hl{height:34px;padding:0 11px;border-radius:999px;color:var(--fg)}
.hl:hover{background:var(--hover)}
.sw{background:var(--hf);box-shadow:inset 0 -2px 0 var(--hl);border-radius:1px;padding:1px 3px 3px}
.rm{width:34px;height:34px;border-radius:999px;background:var(--f);color:color-mix(in srgb,var(--c) 60%,#000);box-shadow:inset 0 0 0 1.5px var(--c)}
.rm:hover{background:var(--c);color:#fff}
.dots{display:inline-flex;align-items:center;gap:8px;padding:0 9px 0 7px}
.dot{width:16px;height:16px;border-radius:50%;background:var(--c);box-shadow:inset 0 0 0 1px rgba(0,0,0,.08);transition:transform .1s}
.dot:hover{transform:scale(1.18)}
.dot.on{box-shadow:0 0 0 2px var(--bg),0 0 0 3.5px var(--c)}
.sep{width:1px;height:20px;background:var(--line);margin:0 2px}
.bar.card{flex-direction:column;align-items:stretch;gap:8px;padding:10px;border-radius:12px;width:300px}
textarea{all:unset;box-sizing:border-box;display:block;width:100%;min-height:76px;max-height:240px;overflow:auto;white-space:pre-wrap;
  font:400 14px/1.45 ${SANS};color:var(--fg);background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:8px 10px}
textarea:focus{border-color:var(--accent)}
textarea::placeholder,.tagin::placeholder{color:var(--fg2)}
.tags{display:flex;flex-wrap:wrap;align-items:center;gap:4px;padding:5px 6px;border:1px solid var(--line);border-radius:8px;background:var(--panel);cursor:text}
.tags:focus-within{border-color:var(--accent)}
.tagin{all:unset;box-sizing:border-box;flex:1;min-width:90px;font:400 13px/1.4 ${SANS};color:var(--fg);padding:2px 4px}
.chip{display:inline-flex;align-items:center;gap:1px;font-size:12px;font-weight:500;line-height:1.3;color:var(--accent);background:var(--chip);border-radius:999px;padding:2px 8px}
.chip button{width:16px;height:16px;margin:0 -4px 0 1px;border-radius:50%;font-size:14px;line-height:1;color:var(--fg2)}
.chip button:hover{color:var(--fg);background:var(--hover)}
.sugg{display:flex;flex-wrap:wrap;gap:4px}
.sugg:empty{display:none}
.sugg button{font-size:12px;font-weight:500;color:var(--fg2);border:1px solid var(--line);border-radius:999px;padding:2px 8px}
.sugg button:hover{color:var(--accent);border-color:var(--accent)}
.row{display:flex;justify-content:flex-end;align-items:center;gap:6px}
.hint{flex:1;color:var(--fg2);font-size:11.5px;font-weight:400}
.btn{height:30px;padding:0 12px;border-radius:8px;font-size:13px;font-weight:600;color:var(--fg2)}
.btn:hover{background:var(--hover);color:var(--fg)}
.btn.primary{background:var(--accent);color:var(--on)}
.btn.line{box-shadow:inset 0 0 0 1px var(--line);color:var(--fg)}
.panel{position:fixed;top:0;right:0;bottom:0;width:360px;max-width:100vw;box-sizing:border-box;display:flex;flex-direction:column;
  background:var(--bg);color:var(--fg);border-left:1px solid var(--line);box-shadow:-10px 0 34px rgba(17,24,39,.14)}
.phead{display:flex;align-items:center;gap:8px;padding:10px 8px 10px 16px;border-bottom:1px solid var(--line)}
.brand{font-weight:700;font-size:15px;letter-spacing:-.01em}
.pcount{flex:1;color:var(--fg2);font-weight:400}
.pmeta{display:flex;flex-direction:column;gap:6px;padding:12px 16px;border-bottom:1px solid var(--line)}
.ptitle{font-weight:600;font-size:14px;line-height:1.35;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.pstate{display:flex;align-items:center;gap:6px;color:var(--fg2);font-size:12.5px;font-weight:400}
.pstate i{width:7px;height:7px;border-radius:50%;background:var(--line)}
.pstate.on i{background:#3a9b5c}
.pacts{display:flex;gap:6px;margin-top:2px}
.plist{flex:1;overflow:auto;overscroll-behavior:contain;padding-bottom:24px}
.item{padding:14px 16px;border-bottom:1px solid var(--line)}
.item.new{animation:daf-new 1.4s ease-out}
@keyframes daf-new{from{background:var(--hover)}to{background:transparent}}
.q{all:unset;box-sizing:border-box;display:-webkit-box;-webkit-line-clamp:8;-webkit-box-orient:vertical;overflow:hidden;width:100%;cursor:pointer;
  white-space:pre-wrap;font:400 14.5px/1.5 Georgia,"Iowan Old Style",serif;color:var(--fg);padding:1px 0 1px 11px;border-left:3px solid var(--c)}
.q:hover{color:var(--accent)}
.inote{margin:8px 0 0 14px;font-weight:400;font-size:13.5px;line-height:1.45;white-space:pre-wrap;color:var(--fg)}
.chips{display:flex;flex-wrap:wrap;gap:4px;margin:8px 0 0 14px}
.iacts{display:flex;align-items:center;gap:2px;margin:6px 0 0 8px}
.link{height:26px;padding:0 6px;border-radius:6px;font-size:12.5px;font-weight:500;color:var(--fg2)}
.link:hover{background:var(--hover);color:var(--fg)}
.lost{color:var(--fg2);font-size:12px;font-weight:400;margin-left:auto;padding-right:2px}
.pedit{display:flex;flex-direction:column;gap:8px;margin-top:10px}
.empty{padding:28px 18px;color:var(--fg2);font-weight:400;font-size:13.5px;line-height:1.55}
.toast{position:fixed;left:50%;bottom:24px;transform:translateX(-50%);display:flex;gap:14px;align-items:center;max-width:calc(100vw - 32px);
  background:#22252b;color:#fff;padding:10px 16px;border-radius:10px;box-shadow:0 10px 30px rgba(0,0,0,.3);font-weight:400;font-size:14px;line-height:1.4}
.toast button{color:#9fd3ea;font-weight:600}
`;
let host = null, root = null, bar = null, panelEl = null, toastEl = null, mode = null, cur = null;
function ui(){
  if (host && host.isConnected) return;
  if (!host) {
    host = document.createElement('daf-ext');
    host.style.cssText = 'all:initial;position:fixed;top:0;left:0;width:0;height:0;z-index:2147483647';
    root = host.attachShadow({ mode: 'closed' });
    // A <style> made with createElement, not parsed from markup: Firefox lets a page's CSP block the latter.
    const css = document.createElement('style'), wrap = document.createElement('div');
    css.textContent = UICSS;
    wrap.className = 'ui';
    wrap.innerHTML = '<aside class="panel" aria-label="Your highlights on this page" hidden></aside>' +
      '<div class="bar" role="toolbar" aria-label="Daf" hidden></div><div class="toast" role="status" hidden></div>';
    root.append(css, wrap);
    bar = root.querySelector('.bar'); panelEl = root.querySelector('.panel'); toastEl = root.querySelector('.toast');
    // A press on a button keeps the page's selection and the focus in a text field.
    wrap.addEventListener('mousedown', e => { if (e.target.closest('button') || (bar.contains(e.target) && !/^(TEXTAREA|INPUT)$/.test(e.target.tagName))) e.preventDefault(); });
    wrap.addEventListener('click', onUi);
    toastEl.addEventListener('click', e => { const b = e.target.closest('button'); if (b && toastEl._act) { toastEl._act(); toastEl.hidden = true; } });
    // Keys typed in the note stay in the note: the page sees them coming from <daf-ext>, not a text field.
    for (const t of ['keydown', 'keyup', 'keypress', 'input']) root.addEventListener(t, e => {
      e.stopPropagation();
      if (t === 'keydown') onUiKey(e);
      else if (t === 'input' && ed && e.target.classList.contains('tagin')) edSugg(e.target.value);
    });
  }
  quiet(() => document.documentElement.appendChild(host));
}
function theme(){ ui(); root.querySelector('.ui').classList.toggle('dark', pageDark()); }
function place(rect){
  const w = bar.offsetWidth || 200, h = bar.offsetHeight || 44;
  const vw = (document.documentElement.clientWidth || innerWidth) - (panelOpen && innerWidth > 720 ? panelEl.offsetWidth : 0);
  bar.style.left = Math.max(8, Math.min(vw - w - 8, rect.left + rect.width / 2 - w / 2)) + 'px';
  bar.style.top = (rect.top > h + 24 ? rect.top - h - 10 : Math.min(innerHeight - h - 8, rect.bottom + 10)) + 'px';
}
function hideBar(){
  if (ed && ed.where === 'bar') ed = null;
  if (bar) { bar.hidden = true; bar.className = 'bar'; }
  mode = null; cur = null;
}
function toast(msg, action, label){
  ui();
  toastEl.innerHTML = '<span>' + esc(msg) + '</span>' + (action ? '<button type="button" data-a="toast">' + esc(label) + '</button>' : '');
  toastEl._act = action || null; toastEl.hidden = false;
  clearTimeout(toast.t); toast.t = setTimeout(() => { toastEl.hidden = true; }, action ? 6000 : 3500);
}
function fail(e){
  if (e && e.kind === 'setup') toast(e.message, () => send({ type: 'options' }).catch(() => {}), 'Open options');
  else toast((e && e.message) || 'Something went wrong.');
}
const lastRect = h => { const r = h.els.length ? h.els[h.els.length - 1].getBoundingClientRect() : null; return r && r.width ? r : null; };
const firstRect = h => { const r = h.els.length ? h.els[0].getBoundingClientRect() : null; return r && r.width ? r : null; };

function showSelBar(range){
  theme(); mode = 'sel'; cur = null;
  bar.className = 'bar';
  bar.innerHTML = '<button class="hl" data-a="hl" title="Highlight (' + KEY + ')"><span class="sw">Highlight</span></button>' +
    '<button class="ic" data-a="hlnote" title="Highlight with a note" aria-label="Highlight with a note">' + IC.note + '</button>';
  bar.hidden = false;
  const rs = range.getClientRects(), r = rs.length ? rs[0] : range.getBoundingClientRect();
  place(r);
}
function showHlBar(h){
  theme(); mode = 'hl'; cur = h;
  bar.className = 'bar';
  const noted = h.note || (h.tags && h.tags.length), label = noted ? 'Edit the note and tags' : 'Add a note or tags';
  bar.innerHTML = (h.source === 'daf' ? '<button class="rm" data-a="rm" data-c="' + h.color + '" title="Remove the highlight" aria-label="Remove the highlight">' + IC.x + '</button>' : '') +
    '<button class="ic' + (noted ? ' has' : '') + '" data-a="note" title="' + label + '" aria-label="' + label + '">' + IC.note + '</button>' +
    '<span class="dots">' + COLORS.map(k => '<button class="dot' + (k === h.color ? ' on' : '') + '" data-a="color" data-c="' + k + '" title="' + k[0].toUpperCase() + k.slice(1) + '" aria-label="' + k + '"></button>').join('') + '</span>' +
    '<span class="sep"></span><button class="ic" data-a="panel" title="All your highlights on this page" aria-label="All your highlights on this page">' + IC.list + '</button>';
  bar.hidden = false;
  const r = firstRect(h); if (r) place(r);
}
function openNote(h){
  theme(); mode = 'note'; cur = h;
  bar.className = 'bar card';
  bar.hidden = false;
  openEditor(h, bar, 'bar');
  const r = lastRect(h) || firstRect(h);
  if (r) place(r);
}

/* ---------- the note and its tags (the bar's card, or in the side panel) ---------- */
let ed = null, allTags = null;                // ed: { h, box, where, tags }
const loadTags = () => allTags ? Promise.resolve(allTags) : send({ type: 'tags' }).then(r => (allTags = (r && r.tags) || []), () => (allTags = []));
// Tags as Daf keeps them (review.clean_tags): lower case, no spaces or '#'.
const cleanTag = v => String(v || '').trim().replace(/^#+/, '').toLowerCase().replace(/[^\p{L}\p{N}\p{M}_/-]+/gu, '-').replace(/^-+|-+$/g, '').slice(0, 40);
function openEditor(h, box, where){
  ed = { h, box, where, tags: (h.tags || []).slice() };
  box.innerHTML = '<textarea placeholder="Add a note" aria-label="Note" spellcheck="true"></textarea>' +
    '<div class="tags"></div><div class="sugg"></div>' +
    '<div class="row"><span class="hint">' + (MAC ? '⌘' : 'Ctrl+') + 'Enter saves</span><button class="btn" data-a="cancel">Cancel</button><button class="btn primary" data-a="save">Save</button></div>';
  const ta = box.querySelector('textarea'); ta.value = h.note || '';
  edTags();
  loadTags().then(() => { if (ed && ed.box === box) edSugg(''); });
  setTimeout(() => { ta.focus(); ta.setSelectionRange(ta.value.length, ta.value.length); }, 0);
}
function edTags(){
  ed.box.querySelector('.tags').innerHTML = ed.tags.map(t => '<span class="chip">#' + esc(t) + '<button data-a="tagrm" data-t="' + esc(t) + '" aria-label="Remove the tag ' + esc(t) + '">×</button></span>').join('') +
    '<input class="tagin" placeholder="' + (ed.tags.length ? 'Another tag' : 'Add a tag') + '" aria-label="Add a tag" autocomplete="off" autocapitalize="none" spellcheck="false">';
}
function edSugg(q){
  const box = ed && ed.box.querySelector('.sugg'); if (!box) return;
  const want = cleanTag(q), list = (allTags || []).filter(t => !ed.tags.includes(t) && (!want || t.includes(want))).slice(0, 6);
  box.innerHTML = list.map(t => '<button data-a="tagadd" data-t="' + esc(t) + '">#' + esc(t) + '</button>').join('');
}
function edAdd(v){
  const t = cleanTag(v);
  if (t && !ed.tags.includes(t) && ed.tags.length < 12) ed.tags.push(t);
  edTags(); edSugg('');
  ed.box.querySelector('.tagin').focus();
}
function edCancel(){
  if (!ed) return;
  const where = ed.where; ed = null;
  if (where === 'bar') hideBar(); else panelDraw();
}
async function edSave(){
  if (!ed) return;
  const { h, box, where } = ed, typed = box.querySelector('.tagin');
  if (typed && cleanTag(typed.value) && !ed.tags.includes(cleanTag(typed.value))) ed.tags.push(cleanTag(typed.value));
  const note = box.querySelector('textarea').value.trim() || null, tags = ed.tags.slice(), oldNote = h.note, oldTags = h.tags || [];
  ed = null;
  if (where === 'bar') hideBar();
  const changes = {};
  if (note !== oldNote) changes.note = note || '';
  if (tags.join('\n') !== oldTags.join('\n')) changes.tags = tags;
  if (!Object.keys(changes).length) { if (where === 'panel') panelDraw(); return; }
  h.note = note; h.tags = tags; quiet(() => marks(h)); changed();
  try {
    const id = await h.ready;
    const r = await send({ type: 'update', id, changes });
    if (r && Array.isArray(r.tags)) { h.tags = r.tags; changed(); allTags = null; }
    toast('note' in changes ? (note ? 'Note saved' : 'Note removed') : 'Tags saved');
  } catch (e) { if (hls.includes(h)) { h.note = oldNote; h.tags = oldTags; quiet(() => marks(h)); changed(); } if (!e.shown) fail(e); }
}
function onUiKey(e){
  const t = e.target;
  if (ed && ed.box.contains(t)) {
    if (e.key === 'Escape') { e.preventDefault(); edCancel(); }
    else if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) { e.preventDefault(); edSave(); }
    else if (t.classList.contains('tagin')) {
      if (e.key === 'Enter' || e.key === ',') { e.preventDefault(); if (t.value.trim()) edAdd(t.value); }
      else if (e.key === 'Backspace' && !t.value && ed.tags.length) { ed.tags.pop(); edTags(); edSugg(''); ed.box.querySelector('.tagin').focus(); }
    }
    return;
  }
  if (e.key === 'Escape') { if (mode) hideBar(); else if (panelOpen) closePanel(); }
}

/* ---------- the side panel: every highlight on the page, in reading order ---------- */
let panelOpen = false, page = { connected: false, doc_id: null };
function openPanel(){ ui(); theme(); panelOpen = true; panelEl.hidden = false; panelDraw(); }
function closePanel(){
  if (ed && ed.where === 'panel') edSave();
  panelOpen = false; if (panelEl) panelEl.hidden = true;
}
function inOrder(){
  const on = hls.filter(h => h.els.length && h.els[0].isConnected), off = hls.filter(h => !on.includes(h));
  on.sort((a, b) => a.els[0].compareDocumentPosition(b.els[0]) & Node.DOCUMENT_POSITION_FOLLOWING ? -1 : 1);
  return on.concat(off);
}
function itemHTML(h){
  const lost = !h.els.length;
  return '<div class="item" data-k="' + h.key + '"><button class="q" data-a="pgo" data-c="' + h.color + '" title="' + (lost ? 'Not found on the page as it is now' : 'Go to it on the page') + '">' + esc(h.text || h.quote.exact) + '</button>' +
    (h.note ? '<div class="inote">' + esc(h.note) + '</div>' : '') +
    (h.tags && h.tags.length ? '<div class="chips">' + h.tags.map(t => '<span class="chip">#' + esc(t) + '</span>').join('') + '</div>' : '') +
    '<div class="iacts"><button class="link" data-a="pedit">' + (h.note || (h.tags && h.tags.length) ? 'Edit note and tags' : 'Add a note or tags') + '</button>' +
    (h.source === 'daf' ? '<button class="link" data-a="prm">Remove</button>' : '') +
    (lost ? '<span class="lost">Not found on this page</span>' : '') + '</div></div>';
}
function panelDraw(fresh){
  if (!panelOpen || !panelEl) return;
  if (ed && ed.where === 'panel') return;     // not under the note being written
  const y = panelEl.querySelector('.plist') ? panelEl.querySelector('.plist').scrollTop : 0;
  const head = '<div class="phead"><span class="brand">Daf</span><span class="pcount">' + (page.connected ? count(hls.length) : '') + '</span>' +
    '<button class="ic" data-a="pclose" title="Close (Esc)" aria-label="Close">' + IC.x + '</button></div>';
  if (!page.connected) {
    panelEl.innerHTML = head + '<div class="empty">Connect the extension to Daf first: make a token in Daf (Preferences, Account) and paste it in the options.' +
      '<div class="pacts" style="margin-top:12px"><button class="btn primary" data-a="opts">Open options</button></div></div>';
    return;
  }
  const saved = !!page.doc_id && page.where !== 'deleted', inLib = saved && page.where !== 'feed';
  panelEl.innerHTML = head +
    '<div class="pmeta"><div class="ptitle">' + esc(pageTitle() || location.host) + '</div>' +
    '<div class="pstate' + (saved ? ' on' : '') + '"><i></i>' + (saved ? (inLib ? 'In your Library' : 'In your Feed') : 'Not in Daf yet: the first highlight saves it') + '</div>' +
    '<div class="pacts">' + (saved ? '<button class="btn line" data-a="popen">Open in Daf</button>' : '') +
    (inLib ? '' : '<button class="btn primary" data-a="psave">Save to your Library</button>') + '</div></div>' +
    '<div class="plist">' + (hls.length ? inOrder().map(itemHTML).join('') :
      '<div class="empty">' + emptyText() + '</div>') + '</div>';
  const list = panelEl.querySelector('.plist'); list.scrollTop = y;
  if (fresh) { const it = list.querySelector('[data-k="' + fresh.key + '"]'); if (it) { it.classList.add('new'); it.scrollIntoView({ block: 'nearest' }); } }
}
function goTo(h){
  if (!h.els.length || !h.els[0].isConnected) { toast('That highlight isn’t on the page as it is now.'); return; }
  h.els[0].scrollIntoView({ block: 'center', behavior: 'smooth' });
  quiet(() => h.els.forEach(w => w.classList.add('daf-flash')));
  setTimeout(() => quiet(() => h.els.forEach(w => w.classList.remove('daf-flash'))), 1300);
}
/* ---------- the page as you see it ---------- */
// Saving sends the page itself, so Daf keeps what's on your screen: past a paywall you're signed in
// to, and after the page's own scripts have run. Daf finds the article in it (daf/pages.py) and keeps
// it when it has more than Daf's own reading of the address, which is signed in nowhere.
const MAX_PAGE = 6 * 1024 * 1024;
function snapshot(){
  try {
    const live = [...document.querySelectorAll('img')], links = [...document.querySelectorAll('a[href]')];
    const root = document.documentElement.cloneNode(true);
    const imgs = [...root.querySelectorAll('img')], as = [...root.querySelectorAll('a[href]')];
    imgs.forEach((im, i) => {                     // the picture the page shows (lazy ones keep it elsewhere)
      const o = live[i]; if (!o) return;
      const abs = v => { try { return v ? new URL(v.trim().split(/\s+/)[0], location.href).href : ''; } catch (e) { return ''; } };
      const src = [o.currentSrc, o.src, o.getAttribute('data-src'), o.getAttribute('data-lazy-src'), o.getAttribute('data-original'), (o.getAttribute('data-srcset') || '').split(',')[0]]
        .map(abs).find(v => /^https?:/.test(v));
      if (src) im.setAttribute('src', src);
      im.removeAttribute('srcset'); im.removeAttribute('sizes'); im.removeAttribute('loading');
    });
    as.forEach((a, i) => { if (links[i] && /^https?:/.test(links[i].href)) a.setAttribute('href', links[i].href); });
    root.querySelectorAll('script, style, noscript, iframe, object, embed, template, link, source, daf-ext').forEach(n => n.remove());
    root.querySelectorAll('daf-hl').forEach(w => { while (w.firstChild) w.parentNode.insertBefore(w.firstChild, w); w.remove(); });
    const html = '<!doctype html>' + root.outerHTML;
    return html.length > MAX_PAGE ? null : html;
  } catch (e) { return null; }
}
const savedSay = r => r.words ? 'Saved with the page’s text, ' + r.words.toLocaleString() + ' words' : r.saved ? 'Saved to your Daf Library' : 'Already in your Daf Library';
async function savePage(){
  try {
    const r = await send({ type: 'save', url: pageUrl(), title: pageTitle(), html: snapshot() });
    page.doc_id = r.doc_id; page.where = 'library';
    toast(savedSay(r));
  } catch (e) { fail(e); }
  panelDraw();
  badge();
}
// Whatever changed a highlight: the toolbar badge and the panel follow.
function changed(fresh){ badge(); panelDraw(fresh); }

function onUi(e){
  const b = e.target.closest('button'); if (!b) return;
  const a = b.dataset.a, item = b.closest('[data-k]'), h = item ? byKey(item.dataset.k) : cur;
  if (a === 'hl') highlight(false);
  else if (a === 'hlnote') highlight(true);
  else if (a === 'rm' && h) remove(h);
  else if (a === 'note' && h) openNote(h);
  else if (a === 'color' && h) recolor(h, b.dataset.c);
  else if (a === 'panel') { hideBar(); openPanel(); }
  else if (a === 'save') edSave();
  else if (a === 'cancel') edCancel();
  else if (a === 'tagrm' && ed) { ed.tags = ed.tags.filter(t => t !== b.dataset.t); edTags(); edSugg(''); ed.box.querySelector('.tagin').focus(); }
  else if (a === 'tagadd' && ed) edAdd(b.dataset.t);
  else if (a === 'pclose') closePanel();
  else if (a === 'popen') send({ type: 'open', doc: page.doc_id }).catch(fail);
  else if (a === 'psave') savePage();
  else if (a === 'opts') send({ type: 'options' }).catch(() => {});
  else if (a === 'pgo' && h) goTo(h);
  else if (a === 'pedit' && h) { if (ed) edSave(); const box = document.createElement('div'); box.className = 'pedit'; item.querySelector('.iacts').replaceWith(box); openEditor(h, box, 'panel'); }
  else if (a === 'prm' && h) remove(h);
}

/* ---------- what you do ---------- */
function selRange(){
  const s = getSelection();
  if (!s || !s.rangeCount || s.isCollapsed) return null;
  const r = s.getRangeAt(0), c = r.commonAncestorContainer, el = c.nodeType === 1 ? c : c.parentElement;
  if (!el || el.closest('input, textarea, select, daf-ext') || el.isContentEditable || !r.toString().trim()) return null;
  return r;
}
const pageUrl = () => location.href;
function pageTitle(){
  const m = document.querySelector('meta[property="og:title"], meta[name="twitter:title"]');
  return ((m && m.content) || document.title || '').trim().slice(0, 300);
}
function mk(x){
  const h = { key: 'h' + (++seq), id: x.id || null, text: x.text || '', note: x.note || null, color: COLORS.includes(x.color) ? x.color : 'yellow',
    source: x.source || 'daf', tags: Array.isArray(x.tags) ? x.tags : [], quote: x.quote || { exact: x.text || '', prefix: '', suffix: '' }, els: [] };
  h.ready = Promise.resolve(h.id);
  return h;
}
const badge = () => send({ type: 'badge', count: hls.length, saved: !!page.doc_id && page.where === 'library' }).catch(() => {});

function highlight(withNote){
  const range = selRange(); if (!range) return;
  ensureStyle();
  fresh();
  const ix = index();
  let rs = rOf(ix, range.startContainer, range.startOffset, false), re = rOf(ix, range.endContainer, range.endOffset, true);
  if (rs < 0 || re < 0) return;
  [rs, re] = snap(ix.R, rs, re);
  const a = ix.before[rs], b = ix.before[re];
  if (b <= a) return;
  const text = fmt(ix.R.slice(rs, re)), prefix = fmt(ix.R.slice(Math.max(0, rs - 200), rs)).slice(-32), suffix = fmt(ix.R.slice(re, re + 200)).slice(0, 32);
  const h = mk({ text, quote: { exact: text, prefix, suffix } });
  quiet(() => draw(ix, [{ h, a, b }]));
  hls.push(h);
  getSelection().removeAllRanges();
  changed(h);
  // The first highlight saves the page: with the page itself, as Save does.
  const html = page.doc_id && page.where === 'library' ? undefined : snapshot();
  h.ready = send({ type: 'highlight', url: pageUrl(), title: pageTitle(), text, prefix, suffix, color: h.color, html }).then(r => {
    const twin = hls.find(x => x !== h && x.id === r.id);   // the same words at the same place: one highlight
    if (twin) { quiet(() => unwrap(twin)); hls = hls.filter(x => x !== twin); h.note = h.note || twin.note; h.tags = h.tags.length ? h.tags : twin.tags; quiet(() => marks(h)); }
    h.id = r.id;
    if (r.doc_id) { page.doc_id = r.doc_id; if (r.saved) page.where = 'library'; }
    if (r.saved) toast('Saved to your Daf Library');
    changed();
    return r.id;
  }, e => {
    quiet(() => unwrap(h)); hls = hls.filter(x => x !== h);
    if (cur === h) hideBar();
    changed();
    fail(e);
    e.shown = true;                            // what waits on this one doesn't say it again
    throw e;
  });
  h.ready.catch(() => {});
  // Right away, the bar for the new highlight: a color, a note, or take it back.
  if (withNote) openNote(h); else showHlBar(h);
}
async function recolor(h, c){
  if (!COLORS.includes(c) || c === h.color) return;
  const old = h.color;
  h.color = c; quiet(() => marks(h)); showHlBar(h); changed();
  try { await send({ type: 'update', id: await h.ready, changes: { color: c } }); }
  catch (e) { h.color = old; quiet(() => marks(h)); if (cur === h) showHlBar(h); changed(); if (!e.shown) fail(e); }
}
async function remove(h){
  if (ed && ed.h === h) ed = null;
  hideBar();
  quiet(() => unwrap(h)); h.gone = true; hls = hls.filter(x => x !== h); changed();
  try {
    await send({ type: 'remove', id: await h.ready });
    toast('Highlight removed', () => undo(h), 'Undo');
  } catch (e) { if (e.shown) return; h.gone = false; hls.push(h); anchor([h]); changed(); fail(e); }
}
// Undo puts the same words back at the same place: Daf gives them the same id, with the note kept.
async function undo(h){
  h.gone = false; hls.push(h); anchor([h]); changed();
  try {
    const r = await send({ type: 'highlight', url: pageUrl(), title: pageTitle(), text: h.text || h.quote.exact, prefix: h.quote.prefix, suffix: h.quote.suffix, color: h.color });
    h.id = r.id; h.ready = Promise.resolve(r.id); changed();
  } catch (e) { quiet(() => unwrap(h)); hls = hls.filter(x => x !== h); changed(); fail(e); }
}

/* ---------- the page's highlights ---------- */
let pageKey = null, stopped = false;
async function load(){
  const key = pageKey = location.href.split('#')[0];
  let r;
  try { r = await send({ type: 'page', url: location.href }); } catch (e) { return; }
  if (key !== pageKey) return;
  if (r.skip) { stop(); return; }
  page = { connected: r.connected !== false, doc_id: r.doc_id || null, where: r.where || null };
  quiet(() => hls.forEach(unwrap));
  hls = (r.highlights || []).map(mk);
  if (hls.length) { ensureStyle(); anchor(hls); }
  changed();
}
function stop(){
  stopped = true; mo.disconnect(); clearInterval(watchT);
  quiet(() => hls.forEach(unwrap)); hls = [];
  if (host) host.remove();
  if (style) style.remove();
}

/* ---------- settings ---------- */
// select: what selecting text on a page does (Options).
//   ask (the default)  the Highlight button comes up beside it; nothing is kept until it's pressed
//                      (or Alt+H), so selecting to copy never saves a page.
//   shortcut           nothing comes up: Alt+H, or right-click → Highlight in Daf. A touch screen,
//                      which has neither, still gets the button.
//   auto               a selection made with the mouse is highlighted at once, as in Daf's reader;
//                      Alt while selecting, a single word, or a touch screen get the button instead.
// Up to 0.4 there was only `auto`, on unless turned off. It isn't read any more: everyone starts on ask.
const SELECT = ['ask', 'shortcut', 'auto'];
let opts = { select: 'ask' };
try {
  X.storage.local.get({ select: 'ask' }, s => { if (s && SELECT.includes(s.select)) opts.select = s.select; });
  X.storage.onChanged.addListener((ch, area) => {
    if (area !== 'local' || !ch.select) return;
    opts.select = SELECT.includes(ch.select.newValue) ? ch.select.newValue : 'ask';
    if (mode === 'sel') hideBar();
    panelDraw();
  });
} catch (e) { /* storage not here: the default stands */ }
function emptyText(){
  if (opts.select === 'auto') return 'Select some text on the page and it’s highlighted. Hold Alt' + (MAC ? ' (⌥)' : '') + ' while you select to only select.';
  if (opts.select === 'shortcut') return 'Select some text on the page and press ' + esc(KEY) + ', or right-click it and choose Highlight in Daf.';
  return 'Select some text on the page and choose Highlight, or press ' + esc(KEY) + '.';
}

/* ---------- events ---------- */
let down = false, selT = 0, pointer = 'mouse';
const fromUi = e => host && e.composedPath && e.composedPath().includes(host);
function checkSel(ev){
  if (stopped || mode === 'note' || (ed && ed.where === 'bar')) return;
  const r = selRange();
  if (r && ev && opts.select === 'auto' && page.connected && pointer === 'mouse' && !ev.altKey && /\S\s+\S/.test(r.toString().trim())) { highlight(false); return; }
  if (r && (opts.select !== 'shortcut' || pointer !== 'mouse')) showSelBar(r);
  else if (mode === 'sel') hideBar();
}
document.addEventListener('pointerdown', e => { pointer = e.pointerType || 'mouse'; }, true);
document.addEventListener('mousedown', e => {
  if (stopped || fromUi(e)) return;
  down = true;
  if (ed) edSave();
  if (mode) hideBar();
}, true);
document.addEventListener('mouseup', e => {
  down = false;
  if (stopped || fromUi(e) || e.button !== 0) return;
  const ev = { altKey: e.altKey };
  setTimeout(() => checkSel(ev), 10);
}, true);
document.addEventListener('selectionchange', () => { if (!down && !stopped) { clearTimeout(selT); selT = setTimeout(() => checkSel(null), 250); } });
document.addEventListener('click', e => {
  if (stopped || fromUi(e)) return;
  const w = e.target && e.target.closest ? e.target.closest('daf-hl') : null;
  if (!w || !getSelection().isCollapsed || w.closest('a[href]')) return;
  const h = byKey(w.getAttribute('data-daf')); if (!h) return;
  e.preventDefault(); e.stopPropagation();
  showHlBar(h);
}, true);
window.addEventListener('keydown', e => {
  if (stopped || fromUi(e)) return;
  if (e.altKey && e.shiftKey && !e.ctrlKey && !e.metaKey && e.code === 'KeyH') { e.preventDefault(); e.stopPropagation(); if (panelOpen) closePanel(); else openPanel(); }
  else if (e.altKey && !e.ctrlKey && !e.metaKey && e.code === 'KeyH' && selRange()) { e.preventDefault(); e.stopPropagation(); highlight(false); }
  else if (e.key === 'Escape' && mode) hideBar();
  else if (e.key === 'Escape' && panelOpen && !ed) closePanel();
}, true);
window.addEventListener('scroll', () => {
  if (mode === 'sel') { const r = selRange(); if (r) place(r.getClientRects()[0] || r.getBoundingClientRect()); }
  else if ((mode === 'hl' || mode === 'note') && cur) { const r = mode === 'note' ? lastRect(cur) || firstRect(cur) : firstRect(cur); if (r) place(r); }
}, { capture: true, passive: true });
X.runtime.onMessage.addListener((m, sender, reply) => {
  if (!m || stopped) return;
  if (m.type === 'snapshot') { reply({ html: snapshot() }); return; }     // the toolbar button's Save
  if (m.type === 'hl-selection') highlight(false);
  else if (m.type === 'save-page') { savePage(); reply(true); return; }   // the right-click menu or Alt+Shift+S
  else if (m.type === 'toast') toast(m.text);
  else if (m.type === 'panel') { if (panelOpen && !m.open) closePanel(); else openPanel(); }
});
// A site that changes pages without loading one: the new address gets its own highlights.
const watchT = setInterval(() => { if (!stopped && location.href.split('#')[0] !== pageKey) { hideBar(); if (ed) ed = null; load(); } }, 1000);

function start(){
  mo.observe(document.documentElement, { childList: true, subtree: true, characterData: true });
  load();
  if (/(^|\.)instagram\.com$/.test(location.hostname)) send({ type: 'instagram' }).catch(() => {});   // keeps Daf's Instagram sign-in fresh, if Daf asks
}
if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start, { once: true }); else start();
})();
