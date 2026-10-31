/* Daf's keyboard shortcuts, in one table: what each key does where, and the ones changed in
   Preferences → Keyboard (settings "keys": {scope: {action: key}}, "" for none). Every handler asks
   DafCore.Keys.is(e, scope, action), and every "Keyboard shortcuts" sheet is drawn from here, so a
   change shows up everywhere at once.

   A key is what the browser calls it (e.key): "d", "D" with Shift, "ArrowDown", " " for Space. With
   another keyboard layout on (Hebrew), a letter key still answers to its place on the keyboard. */
(function(){
const C = window.DafCore, { $, esc, api, toast } = C;

const DEFS = {
  list: ['Library and Feed lists', [
    ['next', 'Next item', ['j', 'ArrowDown']], ['prev', 'Previous item', ['k', 'ArrowUp']], ['open', 'Open it', ['Enter']],
    ['archive', 'Done (archive, or seen in the Feed)', ['e']], ['later', 'Later', ['l']], ['save', 'Save to Library (Feed)', ['s']],
    ['star', 'Shortlist', ['f']], ['tag', 'Tags', ['t']], ['delete', 'Delete', ['d']], ['undo', 'Undo', ['z']],
    ['select', 'Select, for several at once', ['x']], ['search', 'Search everything', ['/']]]],
  article: ['Articles, PDFs and emails', [
    ['next', 'Next paragraph', ['j', 'ArrowDown']], ['prev', 'Previous paragraph', ['k', 'ArrowUp']],
    ['highlight', 'Highlight the paragraph or the selection', ['h']], ['note', 'Highlight with a note', ['n']],
    ['archive', 'Done', ['e']], ['later', 'Later', ['l']], ['save', 'Save to Library (Feed)', ['s']], ['star', 'Shortlist', ['f']],
    ['tag', 'Tags', ['t']], ['delete', 'Delete', ['d']], ['undo', 'Undo', ['z']], ['open', 'Open the original', ['o']],
    ['listen', 'Listen, or pause', ['p']], ['aloud', 'Read aloud from here', ['L']], ['toc', 'Contents', ['[']], ['panel', 'Side panel', [']']],
    ['more', 'The … menu', ['m']], ['nextdoc', 'Next in the list', ['J']], ['prevdoc', 'Previous in the list', ['K']],
    ['docnote', 'Document note', ['N']], ['reset', 'Reset reading progress', ['R']], ['copy', 'Copy the link', ['C']],
    ['meta', 'Edit title and author', ['M']], ['focus', 'Focus mode', ['F']]]],
  book: ['Books', [
    ['next', 'Next page', ['ArrowRight']], ['prev', 'Previous page', ['ArrowLeft']], ['highlight', 'Highlight the selection', ['h']],
    ['note', 'Highlight with a note', ['n']], ['bookmark', 'Bookmark this page', ['b']], ['toc', 'Contents', ['t']],
    ['search', 'Search in the book', ['/']], ['panel', 'Side panel', [']']], ['listen', 'Listen', ['l']], ['focus', 'Focus mode', ['f']]]],
  review: ['Daily review', [
    ['keep', 'Keep', ['k', 'ArrowRight']], ['less', 'Less often', ['l']], ['note', 'Note', ['n']], ['open', 'Open at its spot', ['o']],
    ['never', 'Not in review', ['x']], ['fav', 'Favorite', ['f']]]],
  manga: ['Manga', [
    ['left', 'Page to the left', ['ArrowLeft']], ['right', 'Page to the right', ['ArrowRight']], ['next', 'Next page', [' ', 'PageDown', 'ArrowDown']],
    ['prev', 'Previous page', ['PageUp', 'ArrowUp']], ['first', 'First page', ['Home']], ['last', 'Last page', ['End']],
    ['prevvol', 'Previous volume', ['[']], ['nextvol', 'Next volume', [']']], ['menu', 'Show or hide the bars', ['m']],
    ['thumbs', 'Pages', ['t']], ['settings', 'Settings', ['s']], ['mode', 'Reading mode', ['r']], ['layout', 'Page layout', ['d']],
    ['scale', 'Scale', ['c']], ['crop', 'Crop borders', ['b']], ['auto', 'Auto scroll', ['a']], ['fullscreen', 'Full screen', ['f']]]],
};
const FIXED = { list: [['?', 'These shortcuts'], ['Esc', 'Clear the selection']], article: [['?', 'These shortcuts'], ['Esc', 'Close, then back'], ['Alt-select', 'Select without highlighting']],
  book: [['Space', 'Next page (pages layout)'], ['Shift Space', 'Previous page'], ['?', 'These shortcuts'], ['Alt-select', 'Select without highlighting'], ['Esc', 'Close, then back to the book page']],
  review: [['Space', 'Show a flashcard’s answer'], ['1 2 3 4', 'Again, hard, good, easy'], ['⌘ Enter', 'Save the note']],
  manga: [['Shift Space', 'Previous page'], ['?', 'These shortcuts'], ['Esc', 'Close, then back']],
  general: [['⌘K', 'Search everything, or go somewhere'], ['⌘\\', 'The sidebar: full, mini, hidden'], ['?', 'These shortcuts'], ['Esc', 'Close what’s open']] };

let mine = (() => { try { return JSON.parse(localStorage.getItem('daf.keys') || '{}') || {}; } catch(e){ return {}; } })();
const K = {};
K.DEFS = DEFS;
K.set = keys => {
  mine = keys && typeof keys === 'object' ? keys : {};
  try { localStorage.setItem('daf.keys', JSON.stringify(mine)); } catch(e){}
};
K.keys = (scope, action) => {
  const own = mine[scope] && Object.prototype.hasOwnProperty.call(mine[scope], action) ? mine[scope][action] : null;
  if (own !== null && own !== undefined) return own ? [own] : [];
  const d = (DEFS[scope] || [, []])[1].find(x => x[0] === action);
  return d ? d[2] : [];
};
// The key as a US keyboard has it, for a letter typed with another layout on.
const CODE = { BracketLeft: '[', BracketRight: ']', Slash: '/', Backslash: '\\', Semicolon: ';', Quote: "'", Comma: ',', Period: '.', Minus: '-', Equal: '=', Backquote: '`' };
function usKey(e){
  if (!e.key || e.key.length !== 1) return null;
  const m = /^Key([A-Z])$/.exec(e.code || '');
  // A letter key that typed something else: a Hebrew letter, or the "/" Hebrew puts on Q.
  if (m && !/^[a-z]$/i.test(e.key)) return e.shiftKey ? m[1] : m[1].toLowerCase();
  // Punctuation by place too, unshifted (Shift / is "?"): Hebrew puts "." on the "/" key and mirrors
  // the brackets, so "[" on a US keyboard types "]".
  if (!e.shiftKey && CODE[e.code] && e.key !== CODE[e.code] && /^[\x21-\x2f\x3a-\x40\x5b-\x60\x7b-\x7e]$/.test(e.key)) return CODE[e.code];
  if (/[\x20-\x7e]/.test(e.key)) return null;
  const d = /^Digit(\d)$/.exec(e.code || ''); if (d) return d[1];
  return CODE[e.code] || null;
}
// The key as Daf counts it: where it is for a letter typed with another layout, else what it typed.
K.key = e => usKey(e) || e.key;
K.is = (e, scope, action) => {
  const ks = K.keys(scope, action); if (!ks.length) return false;
  return ks.includes(K.key(e));
};
const NAMES = { ArrowDown: '↓', ArrowUp: '↑', ArrowLeft: '←', ArrowRight: '→', ' ': 'Space', Enter: 'Enter', Escape: 'Esc', PageDown: 'Page Down', PageUp: 'Page Up', Home: 'Home', End: 'End', Backspace: 'Backspace', Delete: 'Delete', Tab: 'Tab' };
K.name = k => NAMES[k] || (k.length === 1 && /[A-Z]/.test(k) ? 'Shift ' + k : k);
K.label = (scope, action) => K.keys(scope, action).map(K.name).join(' / ');
K.tip = (scope, action) => { const l = K.label(scope, action); return l ? ' (' + l + ')' : ''; };
K.rows = scope => (DEFS[scope] ? DEFS[scope][1] : []).map(a => [K.label(scope, a[0]), a[1]]).filter(r => r[0]).concat(FIXED[scope] || []);
// The "Keyboard shortcuts" sheet for one place.
K.sheet = (scope, title) => {
  $('#scrim').hidden = false; const m = $('#modal'); m.hidden = false;
  m.innerHTML = '<h2>' + esc(title || 'Keyboard shortcuts') + '</h2><div class="keys">' + K.rows(scope).map(r => '<kbd>' + esc(r[0]) + '</kbd><span>' + esc(r[1]) + '</span>').join('') + '</div>' +
    '<div style="display:flex;justify-content:space-between;align-items:center;gap:8px"><a class="tiny" href="#prefs/keys" data-act="close">Change them</a><button class="btn" data-act="close">Close</button></div>';
};

/* ---------- Preferences → Keyboard ---------- */
let capture = null;
K.prefs = card => {
  if (!card) return;
  const scopes = Object.keys(DEFS);
  card.innerHTML = '<div class="cardh"><h2>Keyboard</h2><button class="linkbtn tiny" data-kreset' + (Object.keys(mine).length ? '' : ' hidden') + '>Back to Daf’s keys</button></div>' +
    '<p class="mute" style="margin:0">Click a shortcut and press the key you want instead. Backspace leaves an action without one. With a Hebrew keyboard on, the keys still work by where they are.</p>' +
    scopes.map(s => '<details class="kscope"><summary>' + esc(DEFS[s][0]) + '</summary><div class="krows">' + DEFS[s][1].map(a => {
      const own = mine[s] && Object.prototype.hasOwnProperty.call(mine[s], a[0]);
      return '<div class="krow"><span>' + esc(a[1]) + '</span><button class="kbtn' + (own ? ' own' : '') + '" data-kscope="' + s + '" data-kact="' + a[0] + '" title="Change it">' + (esc(K.label(s, a[0])) || '<span class="mute">none</span>') + '</button></div>';
    }).join('') + '</div></details>').join('');
};
async function save(keys){
  try { const r = await api('/api/keys', { method: 'PUT', body: JSON.stringify({ keys }) }); K.set(r.keys); if (C.S.data && C.S.data.settings) C.S.data.settings.keys = r.keys; }
  catch(e){ toast(e.message); }
  K.prefs($('#keyscard'));
}
document.addEventListener('click', e => {
  const b = e.target.closest('[data-kact]');
  if (b) {
    if (capture) capture.btn.textContent = K.label(capture.scope, capture.act) || 'none';
    capture = { btn: b, scope: b.dataset.kscope, act: b.dataset.kact };
    b.innerHTML = '<span class="mute">Press a key…</span>'; b.classList.add('wait');
    return;
  }
  if (e.target.closest('[data-kreset]')) { save({}); toast('Daf’s own keys again'); return; }
  if (capture && !e.target.closest('.kbtn')) { capture.btn.classList.remove('wait'); capture.btn.textContent = K.label(capture.scope, capture.act) || 'none'; capture = null; }
});
document.addEventListener('keydown', e => {
  if (!capture) return;
  e.preventDefault(); e.stopPropagation();
  const { scope, act, btn } = capture; btn.classList.remove('wait'); capture = null;
  if (e.key === 'Escape') { btn.textContent = K.label(scope, act) || 'none'; return; }
  if (['Shift', 'Control', 'Alt', 'Meta', 'CapsLock'].includes(e.key) || e.metaKey || e.ctrlKey || e.altKey) { toast('One key, or one with Shift'); K.prefs($('#keyscard')); return; }
  const key = e.key === 'Backspace' || e.key === 'Delete' ? '' : (usKey(e) || e.key);
  if (key && key !== '?' && key !== 'Escape') {
    const clash = DEFS[scope][1].find(a => a[0] !== act && K.keys(scope, a[0]).includes(key));
    if (clash) { toast(K.name(key) + ' is already ' + clash[1] + ' there'); K.prefs($('#keyscard')); return; }
  } else if (key) { toast(K.name(key) + ' stays as it is'); K.prefs($('#keyscard')); return; }
  const next = JSON.parse(JSON.stringify(mine)); next[scope] = next[scope] || {};
  const def = DEFS[scope][1].find(a => a[0] === act)[2];
  if (key && def.length === 1 && def[0] === key) delete next[scope][act]; else next[scope][act] = key;
  if (!Object.keys(next[scope]).length) delete next[scope];
  save(next);
}, true);

C.Keys = K;
})();
