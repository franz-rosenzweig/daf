/* Themes: the whole app's colours, each theme in a light and a dark version (as Moshe's are), one
   chosen for light and one for dark, and when each applies (always light, always dark, or with the
   system). A theme is a handful of base colours; every token in style.css comes from them, so a
   theme reads the same everywhere: lists, the reading views, highlights, charts.

   The choice lives on morten (settings.appearance) so every device reads alike, and in localStorage
   (daf.themeVars) so index.html paints it before anything shows. Preferences → Appearance picks;
   the Aa menu switches light and dark. */
(() => {
const C = window.DafCore;
const T = C.Themes = {};

// bg: the page; side: the sidebar and panels; fg: text; accent: links, buttons, the ring; read: the
// reading text when it should sit a little softer than the UI's; ok/bad; hls: the five highlight hues.
const FAMILIES = [
  { id: 'daf', name: 'Daf', note: 'Teal on white; a warm, softer dark',
    light: { bg: '#ffffff', side: '#f7f7f8', fg: '#1d2127', accent: '#1a7da4' },
    dark: { bg: '#141519', side: '#1a1b20', fg: '#e8e6e1', read: '#d9d6cf', accent: '#62b6da' } },
  { id: 'paper', name: 'Paper', note: 'Sepia, like a printed page',
    light: { bg: '#f7f0e3', side: '#f0e7d6', fg: '#3a3127', accent: '#9a5b1f', hls: { yellow: '#d9ae35', green: '#7fae66', blue: '#7a9fc4', pink: '#d4839a', purple: '#a68bc2' } },
    dark: { bg: '#1d1915', side: '#241f19', fg: '#e8dcc6', read: '#dccfb6', accent: '#d39a5b' } },
  { id: 'nord', name: 'Nord', note: 'Arctic blues',
    light: { bg: '#eceff4', side: '#e5e9f0', fg: '#2e3440', accent: '#5e81ac', ok: '#5f8a4a', bad: '#bf616a', hls: { yellow: '#ebcb8b', green: '#a3be8c', blue: '#81a1c1', pink: '#d08770', purple: '#b48ead' } },
    dark: { bg: '#2e3440', side: '#3b4252', fg: '#e5e9f0', read: '#d8dee9', accent: '#88c0d0', ok: '#a3be8c', bad: '#bf616a', hls: { yellow: '#ebcb8b', green: '#a3be8c', blue: '#81a1c1', pink: '#d08770', purple: '#b48ead' } } },
  { id: 'github', name: 'GitHub', note: 'Primer, light and dark',
    light: { bg: '#ffffff', side: '#f6f8fa', fg: '#1f2328', accent: '#0969da', ok: '#1a7f37', bad: '#d1242f' },
    dark: { bg: '#0d1117', side: '#161b22', fg: '#e6edf3', read: '#d1d9e0', accent: '#4493f8', ok: '#3fb950', bad: '#f85149' } },
  { id: 'github-dimmed', name: 'GitHub dimmed', note: 'GitHub’s softer dark',
    light: { bg: '#ffffff', side: '#f6f8fa', fg: '#1f2328', accent: '#0969da', ok: '#1a7f37', bad: '#d1242f' },
    dark: { bg: '#22272e', side: '#2d333b', fg: '#cdd9e5', read: '#adbac7', accent: '#539bf5', ok: '#57ab5a', bad: '#e5534b' } },
  { id: 'cupertino', name: 'Cupertino', note: 'Apple’s system colours',
    light: { bg: '#ffffff', side: '#f2f2f7', fg: '#1c1c1e', accent: '#007aff', ok: '#248a3d', bad: '#d70015', hls: { yellow: '#ffcc00', green: '#34c759', blue: '#5ac8fa', pink: '#ff2d55', purple: '#af52de' } },
    dark: { bg: '#1c1c1e', side: '#2c2c2e', fg: '#f2f2f7', read: '#e5e5ea', accent: '#0a84ff', ok: '#30d158', bad: '#ff453a', hls: { yellow: '#ffd60a', green: '#30d158', blue: '#64d2ff', pink: '#ff375f', purple: '#bf5af2' } } },
  { id: 'solarized', name: 'Solarized', note: 'Ethan Schoonover’s',
    light: { bg: '#fdf6e3', side: '#eee8d5', fg: '#475b62', accent: '#268bd2', ok: '#859900', bad: '#dc322f', hls: { yellow: '#b58900', green: '#859900', blue: '#268bd2', pink: '#d33682', purple: '#6c71c4' } },
    dark: { bg: '#002b36', side: '#073642', fg: '#a3b1b1', read: '#93a1a1', accent: '#268bd2', ok: '#859900', bad: '#dc322f', hls: { yellow: '#b58900', green: '#859900', blue: '#268bd2', pink: '#d33682', purple: '#6c71c4' } } },
  { id: 'gruvbox', name: 'Gruvbox', note: 'Retro, warm',
    light: { bg: '#fbf1c7', side: '#f2e5bc', fg: '#3c3836', accent: '#076678', ok: '#79740e', bad: '#9d0006', hls: { yellow: '#d79921', green: '#98971a', blue: '#458588', pink: '#b16286', purple: '#8f3f71' } },
    dark: { bg: '#282828', side: '#32302f', fg: '#ebdbb2', read: '#e1d2a9', accent: '#83a598', ok: '#b8bb26', bad: '#fb4934', hls: { yellow: '#fabd2f', green: '#b8bb26', blue: '#83a598', pink: '#d3869b', purple: '#b16286' } } },
  { id: 'catppuccin', name: 'Catppuccin', note: 'Latte and Mocha',
    light: { bg: '#eff1f5', side: '#e6e9ef', fg: '#4c4f69', accent: '#1e66f5', ok: '#40a02b', bad: '#d20f39', hls: { yellow: '#df8e1d', green: '#40a02b', blue: '#1e66f5', pink: '#ea76cb', purple: '#8839ef' } },
    dark: { bg: '#1e1e2e', side: '#181825', fg: '#cdd6f4', accent: '#89b4fa', ok: '#a6e3a1', bad: '#f38ba8', hls: { yellow: '#f9e2af', green: '#a6e3a1', blue: '#89b4fa', pink: '#f5c2e7', purple: '#cba6f7' } } },
  { id: 'rose-pine', name: 'Rosé Pine', note: 'Dawn and Moon',
    light: { bg: '#faf4ed', side: '#f2e9e1', fg: '#575279', accent: '#286983', ok: '#56949f', bad: '#b4637a', hls: { yellow: '#ea9d34', green: '#56949f', blue: '#286983', pink: '#d7827e', purple: '#907aa9' } },
    dark: { bg: '#232136', side: '#2a273f', fg: '#e0def4', accent: '#c4a7e7', ok: '#9ccfd8', bad: '#eb6f92', hls: { yellow: '#f6c177', green: '#9ccfd8', blue: '#3e8fb0', pink: '#ea9a97', purple: '#c4a7e7' } } },
  { id: 'tokyo', name: 'Tokyo Night', note: 'Day and Night',
    light: { bg: '#e1e2e7', side: '#d5d6db', fg: '#343b58', accent: '#2e7de9', ok: '#587539', bad: '#f52a65', hls: { yellow: '#8c6c3e', green: '#587539', blue: '#2e7de9', pink: '#f52a65', purple: '#9854f1' } },
    dark: { bg: '#1a1b26', side: '#16161e', fg: '#c0caf5', read: '#a9b1d6', accent: '#7aa2f7', ok: '#9ece6a', bad: '#f7768e', hls: { yellow: '#e0af68', green: '#9ece6a', blue: '#7aa2f7', pink: '#f7768e', purple: '#bb9af7' } } },
  { id: 'one', name: 'One', note: 'Atom’s One Light and One Dark',
    light: { bg: '#fafafa', side: '#f0f0f1', fg: '#383a42', accent: '#4078f2', ok: '#50a14f', bad: '#e45649', hls: { yellow: '#c18401', green: '#50a14f', blue: '#4078f2', pink: '#e45649', purple: '#a626a4' } },
    dark: { bg: '#282c34', side: '#21252b', fg: '#d7dae0', read: '#abb2bf', accent: '#61afef', ok: '#98c379', bad: '#e06c75', hls: { yellow: '#e5c07b', green: '#98c379', blue: '#61afef', pink: '#e06c75', purple: '#c678dd' } } },
  { id: 'dracula', name: 'Dracula', note: 'and Alucard, its light one',
    light: { bg: '#fffbeb', side: '#f5f0d8', fg: '#1f1f1f', accent: '#644ac9', ok: '#14710a', bad: '#cb3a2a', hls: { yellow: '#846e15', green: '#14710a', blue: '#036a96', pink: '#a3144d', purple: '#644ac9' } },
    dark: { bg: '#282a36', side: '#21222c', fg: '#f8f8f2', read: '#e9e9e2', accent: '#bd93f9', ok: '#50fa7b', bad: '#ff5555', hls: { yellow: '#f1fa8c', green: '#50fa7b', blue: '#8be9fd', pink: '#ff79c6', purple: '#bd93f9' } } },
  { id: 'everforest', name: 'Everforest', note: 'Green and calm',
    light: { bg: '#fdf6e3', side: '#f4f0d9', fg: '#4d5a61', accent: '#3a94c5', ok: '#8da101', bad: '#f85552', hls: { yellow: '#dfa000', green: '#8da101', blue: '#3a94c5', pink: '#f85552', purple: '#df69ba' } },
    dark: { bg: '#2d353b', side: '#343f44', fg: '#d3c6aa', accent: '#a7c080', ok: '#a7c080', bad: '#e67e80', hls: { yellow: '#dbbc7f', green: '#a7c080', blue: '#7fbbb3', pink: '#e67e80', purple: '#d699b6' } } },
  { id: 'eink', name: 'E-ink', note: 'Greys, like the Kindle',
    light: { bg: '#f4f1ea', side: '#ebe7de', fg: '#1a1a1a', accent: '#2f2f2f', hls: { yellow: '#b9a24a', green: '#7f9a72', blue: '#7890a8', pink: '#b5848f', purple: '#9789ad' } },
    dark: { bg: '#121212', side: '#1a1a1a', fg: '#e8e4da', read: '#ddd8cc', accent: '#c9c9c9' } },
  { id: 'contrast', name: 'High contrast', note: 'Black and white, for bright light',
    light: { bg: '#ffffff', side: '#f3f3f3', fg: '#000000', accent: '#0040c0', ok: '#006b2d', bad: '#b00020' },
    dark: { bg: '#000000', side: '#0c0c0c', fg: '#ffffff', accent: '#7ab8ff', ok: '#5ee08a', bad: '#ff7a7a' } },
  { id: 'oled', name: 'Black', note: 'Pure black for OLED screens; Daf’s light by day',
    light: { bg: '#ffffff', side: '#f7f7f8', fg: '#1d2127', accent: '#1a7da4' },
    dark: { bg: '#000000', side: '#0b0b0c', fg: '#e8e6e1', read: '#d6d3cc', accent: '#62b6da' } },
];
T.FAMILIES = FAMILIES;
const byId = id => FAMILIES.find(f => f.id === id) || FAMILIES[0];

/* ---------- colour arithmetic ---------- */
const rgb = h => [1, 3, 5].map(i => parseInt(h.slice(i, i + 2), 16) / 255);
const hex = c => '#' + c.map(v => Math.round(Math.min(1, Math.max(0, v)) * 255).toString(16).padStart(2, '0')).join('');
const mix = (a, b, t) => hex(rgb(a).map((v, i) => v + (rgb(b)[i] - v) * t));
const lum = h => { const [r, g, b] = rgb(h).map(v => v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4); return 0.2126 * r + 0.7152 * g + 0.0722 * b; };
const contrast = (a, b) => { const x = lum(a), y = lum(b); return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05); };
const HUES = { yellow: '#f0c232', green: '#62b862', blue: '#4f8fe6', pink: '#e8679a', purple: '#9b72d9' };

// Every token style.css uses, from a palette's few colours.
T.vars = (p, dark) => {
  const bg = p.bg, fg = p.fg, ac = p.accent, side = p.side || mix(bg, fg, dark ? 0.04 : 0.025);
  const onAccent = contrast(ac, '#ffffff') >= contrast(ac, '#101418') ? '#ffffff' : '#101418';
  const v = {
    '--bg': bg, '--side': side, '--panel': mix(bg, side, 0.6), '--hover': mix(bg, fg, dark ? 0.07 : 0.05), '--active': mix(bg, fg, dark ? 0.12 : 0.085),
    '--line': mix(bg, fg, dark ? 0.12 : 0.09), '--line-2': mix(bg, fg, dark ? 0.2 : 0.16),
    '--fg': fg, '--fg-2': mix(fg, bg, 0.34), '--fg-3': mix(fg, bg, 0.52), '--read-fg': p.read || fg,
    '--accent': ac, '--accent-2': dark ? mix(ac, fg, 0.3) : mix(ac, '#000000', 0.22), '--accent-weak': mix(bg, ac, dark ? 0.2 : 0.12), '--on-accent': onAccent,
    '--g1': mix(bg, ac, dark ? 0.22 : 0.2), '--g2': mix(bg, ac, 0.45), '--g3': mix(bg, ac, 0.72), '--g4': ac,
    '--ok': p.ok || (dark ? '#58b07e' : '#2f8a57'), '--bad': p.bad || (dark ? '#e07a6c' : '#b8392b'),
    '--speak': mix(bg, ac, dark ? 0.18 : 0.12), '--speak-line': mix(bg, ac, dark ? 0.34 : 0.28),
    '--shadow': dark ? '0 1px 2px rgba(0,0,0,.35),0 10px 28px rgba(0,0,0,.45)' : '0 1px 2px rgba(17,24,39,.06),0 10px 28px rgba(17,24,39,.10)',
    'color-scheme': dark ? 'dark' : 'light',
  };
  const hls = Object.assign({}, HUES, p.hls || {});
  for (const [k, h] of Object.entries(hls)) { v['--hl-' + k] = mix(bg, h, dark ? 0.26 : 0.3); v['--hl-' + k + '-line'] = mix(bg, h, dark ? 0.72 : 0.85); }
  v['--hl'] = v['--hl-yellow']; v['--hl-2'] = v['--hl-yellow-line'];
  return v;
};

/* ---------- which one, and putting it on ---------- */
const DEFAULT = { mode: 'system', light: 'daf', dark: 'daf' };
const media = matchMedia('(prefers-color-scheme: dark)');
let cur = null;
function stored(){ try { return JSON.parse(localStorage.getItem('daf.themeVars') || 'null'); } catch(e){ return null; } }
T.get = () => Object.assign({}, DEFAULT, cur || (stored() || {}).a || legacy());
// The Aa menu's old choice (light, sepia, dark, black), once.
function legacy(){
  let t = {}; try { t = JSON.parse(localStorage.getItem('daf.type') || '{}'); } catch(e){}
  return ({ light: { mode: 'light' }, dark: { mode: 'dark' }, sepia: { mode: 'light', light: 'paper' }, black: { mode: 'dark', dark: 'oled' } })[t.theme] || {};
}
T.isDark = a => { a = a || T.get(); return a.mode === 'dark' || (a.mode === 'system' && media.matches); };
T.apply = a => {
  a = Object.assign({}, DEFAULT, a || T.get()); cur = a;
  const dark = T.isDark(a), fam = byId(dark ? a.dark : a.light), vars = T.vars(dark ? fam.dark : fam.light, dark), r = document.documentElement;
  for (const [k, v] of Object.entries(vars)) r.style.setProperty(k, v);
  delete r.dataset.theme;                    // the old fixed themes in style.css stand down
  r.dataset.mode = dark ? 'dark' : 'light'; r.dataset.palette = fam.id;
  let m = document.querySelector('meta[name="theme-color"]'); if (!m) { m = document.createElement('meta'); m.name = 'theme-color'; document.head.appendChild(m); }
  m.content = vars['--side'];
  // For index.html's first paint: both versions, so the system's mode can pick before any script.
  const lf = byId(a.light), df = byId(a.dark);
  try { localStorage.setItem('daf.themeVars', JSON.stringify({ a, light: T.vars(lf.light, false), dark: T.vars(df.dark, true) })); } catch(e){}
  window.dispatchEvent(new CustomEvent('daf-theme', { detail: { name: fam.id, dark, bg: vars['--bg'], side: vars['--side'], fg: vars['--fg'], accent: vars['--accent'] } }));
  window.dispatchEvent(new Event('daf-type'));     // the book's pages take the new colours
};
T.set = (patch, quiet) => {
  const a = Object.assign(T.get(), patch); T.apply(a);
  if (!quiet) C.api('/api/settings', { method: 'PUT', body: JSON.stringify({ appearance: a }) }).catch(() => {});
};
media.addEventListener('change', () => { if (T.get().mode === 'system') T.apply(); });
// Morten's choice wins over this device's, once settings arrive.
T.fromSettings = s => { T.fromSettingsFonts(s); if (s && s.appearance) { const a = Object.assign({}, DEFAULT, s.appearance); if (JSON.stringify(a) !== JSON.stringify(T.get())) T.apply(a); } };
T.apply();

/* ---------- typefaces for reading (web/fonts, tools/fetch-fonts.py), and his own ---------- */
// [id, name, CSS family, group]. Hebrew falls back to Frank Ruhl Libre in the serifs, Heebo in the sans.
T.FACES = [
  ['serif', 'Source Serif', "'Source Serif 4'", 'Serif'], ['literata', 'Literata', "'Literata'", 'Serif'],
  ['charis', 'Charis (Charter)', "'Charis SIL'", 'Serif'], ['merriweather', 'Merriweather', "'Merriweather'", 'Serif'],
  ['lora', 'Lora', "'Lora'", 'Serif'], ['garamond', 'EB Garamond', "'EB Garamond'", 'Serif'],
  ['crimson', 'Crimson Pro', "'Crimson Pro'", 'Serif'], ['newsreader', 'Newsreader', "'Newsreader'", 'Serif'],
  ['spectral', 'Spectral', "'Spectral'", 'Serif'], ['baskerville', 'Libre Baskerville', "'Libre Baskerville'", 'Serif'],
  ['alegreya', 'Alegreya', "'Alegreya'", 'Serif'], ['vollkorn', 'Vollkorn', "'Vollkorn'", 'Serif'],
  ['plexserif', 'IBM Plex Serif', "'IBM Plex Serif'", 'Serif'], ['bitter', 'Bitter', "'Bitter'", 'Serif'],
  ['sans', 'Figtree', "'Figtree'", 'Sans'], ['inter', 'Inter', "'Inter'", 'Sans'], ['sourcesans', 'Source Sans', "'Source Sans 3'", 'Sans'],
  ['atkinson', 'Atkinson Hyperlegible', "'Atkinson Hyperlegible'", 'Easier to read'], ['lexend', 'Lexend', "'Lexend'", 'Easier to read'],
  ['dyslexic', 'OpenDyslexic', "'OpenDyslexic'", 'Easier to read'],
  ['frank', 'Frank Ruhl Libre', "'Frank Ruhl Libre'", 'Hebrew'], ['notohebrew', 'Noto Serif Hebrew', "'Noto Serif Hebrew'", 'Hebrew'],
  ['david', 'David Libre', "'David Libre'", 'Hebrew'], ['heebo', 'Heebo', "'Heebo'", 'Hebrew'],
];
let userFonts = [];
T.faces = () => T.FACES.concat([...new Set(userFonts.map(f => f.family))].map(fam => ['u:' + fam, fam, "'" + fam.replace(/'/g, '') + "'", 'Yours']));
T.stack = id => {
  const f = T.faces().find(x => x[0] === id) || T.FACES[0];
  return f[2] + (f[3] === 'Sans' || f[3] === 'Easier to read' ? ", 'Heebo', 'Figtree', system-ui, sans-serif" : ", 'Frank Ruhl Libre', Georgia, serif");
};
// @font-face rules for his own fonts; the book's pages get them too (book.js).
T.userFontCSS = (abs) => userFonts.map(f => "@font-face{font-family:'" + f.family.replace(/'/g, '') + "';src:url('" + (abs ? location.origin : '') + '/api/fonts/' + encodeURIComponent(f.file) +
  "');font-weight:" + (f.weight || 400) + ';font-style:' + (f.style || 'normal') + ';font-display:swap}').join('\n');
T.setUserFonts = list => {
  userFonts = Array.isArray(list) ? list : [];
  let st = document.getElementById('userfonts'); if (!st) { st = document.createElement('style'); st.id = 'userfonts'; document.head.appendChild(st); }
  st.textContent = T.userFontCSS(false);
  window.dispatchEvent(new Event('daf-type'));
};
T.fromSettingsFonts = s => { if (s && Array.isArray(s.fonts) && JSON.stringify(s.fonts) !== JSON.stringify(userFonts)) T.setUserFonts(s.fonts); };

/* ---------- Preferences → Appearance ---------- */
// A theme's card: a little window in its light half and its dark half.
function swatch(p, dark){
  const v = T.vars(p, dark);
  return '<span class="thw" style="background:' + v['--bg'] + '"><span class="ths" style="background:' + v['--side'] + ';border-color:' + v['--line'] + '">' +
    '<i style="background:' + v['--accent'] + '"></i><i style="background:' + v['--fg-3'] + '"></i><i style="background:' + v['--fg-3'] + '"></i></span>' +
    '<span class="thm"><b style="color:' + v['--fg'] + '">Aa</b><i style="background:' + v['--fg-2'] + '"></i><i style="background:' + v['--fg-3'] + '"></i>' +
    '<i class="thh" style="background:' + v['--hl-yellow'] + ';box-shadow:inset 0 -2px 0 ' + v['--hl-yellow-line'] + '"></i><i style="background:' + v['--fg-3'] + '"></i>' +
    '<em style="background:' + v['--accent'] + '"></em></span></span>';
}
T.section = box => {
  if (!box) return;
  const a = T.get(), esc = C.esc;
  const seg = '<div class="seg" role="radiogroup" aria-label="When">' + [['system', 'Match the system'], ['light', 'Always light'], ['dark', 'Always dark']].map(m =>
    '<button type="button" role="radio" aria-checked="' + (a.mode === m[0]) + '" class="' + (a.mode === m[0] ? 'on' : '') + '" data-thmode="' + m[0] + '">' + m[1] + '</button>').join('') + '</div>';
  const card = (f, which) => {
    const on = which === 'both' ? a.light === f.id && a.dark === f.id : a[which] === f.id;
    return '<button type="button" class="thcard' + (on ? ' on' : '') + '" data-thpick="' + f.id + '" data-which="' + which + '" aria-pressed="' + on + '" title="' + esc(f.note || '') + '">' +
      (which !== 'dark' ? swatch(f.light, false) : '') + (which !== 'light' ? swatch(f.dark, true) : '') + '<span class="thn">' + esc(f.name) + '</span></button>';
  };
  const split = box.dataset.split === '1' || a.light !== a.dark;
  box.innerHTML = '<div class="cardh"><h2>Appearance</h2><span class="mute tiny">Every device follows what you pick here</span></div>' +
    '<div class="prow"><div class="d"><b>Light or dark</b><span>' + (a.mode === 'system' ? 'Light by day, dark at night, as the device is set' : a.mode === 'light' ? 'Always the light version' : 'Always the dark version') + '</span></div>' + seg + '</div>' +
    (split ? '<span class="lbl">For light</span><div class="thgrid">' + FAMILIES.map(f => card(f, 'light')).join('') + '</div><span class="lbl">For dark</span><div class="thgrid">' + FAMILIES.map(f => card(f, 'dark')).join('') + '</div>'
      : '<div class="thgrid">' + FAMILIES.map(f => card(f, 'both')).join('') + '</div>') +
    '<label class="aaline thsplit"><input type="checkbox" data-thsplit' + (split ? ' checked' : '') + '> A different theme for dark</label>' +
    '<div class="prow thfonts"><div class="d"><b>Your own fonts</b><span>A font file you have (TTF, OTF or WOFF), such as Bookerly from a Kindle. It stays on morten and your devices, ' +
    'and shows under Typeface in Aa.</span></div><label class="btn sm">Add a font file<input type="file" accept=".ttf,.otf,.woff,.woff2" multiple hidden data-thfont></label></div>' +
    (userFonts.length ? '<div class="thmine">' + userFonts.map(f => '<span class="chip">' + '<span style="font-family:\'' + esc(f.family) + '\';font-weight:' + f.weight + ';font-style:' + f.style + '">' + esc(f.family) + '</span>' +
      ' <span class="mute tiny">' + (f.weight >= 700 ? 'bold ' : f.weight <= 300 ? 'light ' : '') + (f.style === 'italic' ? 'italic' : f.weight >= 700 || f.weight <= 300 ? '' : 'regular') + '</span>' +
      '<button type="button" data-thfontrm="' + esc(f.file) + '" aria-label="Remove">×</button></span>').join('') + '</div>' : '');
  box.onclick = e => {
    const rm = e.target.closest('[data-thfontrm]');
    if (rm) { C.api('/api/fonts/' + encodeURIComponent(rm.dataset.thfontrm), { method: 'DELETE' }).then(r => { T.setUserFonts(r.fonts); T.section(box); }, err => C.toast(err.message)); return; }
    const m = e.target.closest('[data-thmode]'); if (m) { T.set({ mode: m.dataset.thmode }); T.section(box); return; }
    const p = e.target.closest('[data-thpick]'); if (!p) return;
    const w = p.dataset.which, id = p.dataset.thpick;
    T.set(w === 'both' ? { light: id, dark: id } : { [w]: id }); T.section(box);
  };
  box.onchange = async e => {
    if (e.target.matches('[data-thfont]')) {
      for (const f of e.target.files) {
        try { const r = await fetch('/api/fonts?name=' + encodeURIComponent(f.name), { method: 'POST', credentials: 'same-origin', body: f });
          const j = await r.json(); if (!r.ok) throw new Error(j.detail || r.statusText); T.setUserFonts(j.fonts); C.toast(j.family + ' added: Aa → Typeface'); }
        catch(err){ C.toast(f.name + ': ' + err.message); }
      }
      T.section(box); return;
    }
    if (!e.target.matches('[data-thsplit]')) return;
    if (e.target.checked) box.dataset.split = '1';
    else { delete box.dataset.split; T.set({ dark: T.get().light }); }     // one theme again: dark follows light
    T.section(box);
  };
};
})();
