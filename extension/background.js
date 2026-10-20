/* Daf for the web: the background half. It keeps the address and the token, talks to Daf (with
   the token, never a cookie) for the page and the popup, sets the badge (a page's highlights, or ✓
   for one in the Library), and has the right-click menu and the keys: Save this page (Alt+Shift+S),
   Save this link, Highlight in Daf (Alt+H). */
const X = globalThis.browser || globalThis.chrome;
const DEFAULT_URL = 'https://daf.tiresia.xyz';

class DafError extends Error { constructor(message, kind){ super(message); this.kind = kind; } }

async function conf(){
  const s = await X.storage.local.get({ url: DEFAULT_URL, token: '' });
  return { url: String(s.url || DEFAULT_URL).trim().replace(/\/+$/, ''), token: String(s.token || '').trim() };
}

async function call(path, method = 'GET', body){
  const c = await conf();
  if (!c.token) throw new DafError('Connect the extension to Daf first: paste a token from Daf in its options.', 'setup');
  let r;
  try {
    r = await fetch(c.url + path, {
      method, credentials: 'omit', cache: 'no-store',
      headers: Object.assign({ Authorization: 'Bearer ' + c.token }, body ? { 'Content-Type': 'application/json' } : {}),
      body: body ? JSON.stringify(body) : undefined,
    });
  } catch (e) {
    throw new DafError('Daf didn’t answer at ' + c.url + '. Check the address in the options.', 'network');
  }
  let data = null;
  try { data = await r.json(); } catch (e) { /* not JSON */ }
  if (r.status === 401) {
    if (globalThis.dafSafariReconnect) globalThis.dafSafariReconnect(c.token);   // Safari: the Daf app makes a new one (safari.js)
    throw new DafError('Daf doesn’t know this token. Make a new one in Daf and paste it in the options.', 'setup');
  }
  if (!r.ok) throw new DafError(data && typeof data.detail === 'string' ? data.detail : 'Daf answered ' + r.status + '.', 'server');
  return data;
}

const sameOrigin = (a, b) => { try { return new URL(a).origin === new URL(b).origin; } catch (e) { return false; } };
const web = id => '/api/web/highlight/' + encodeURIComponent(id);

const handlers = {
  async conf(){ const c = await conf(); return { url: c.url, connected: !!c.token }; },
  async page(m, sender){
    const c = await conf(), url = m.url || (sender.tab && sender.tab.url) || '';
    if (sameOrigin(url, c.url)) return { skip: true };          // Daf itself has its own highlighter
    if (!c.token) return { connected: false, doc_id: null, highlights: [] };
    return Object.assign({ connected: true }, await call('/api/web/page', 'POST', { url }));
  },
  highlight: m => call('/api/web/highlight', 'POST', { url: m.url, title: m.title, text: m.text, prefix: m.prefix, suffix: m.suffix, note: m.note || undefined, color: m.color, html: m.html || undefined }),
  update: m => call(web(m.id), 'PUT', m.changes),
  remove: m => call(web(m.id), 'DELETE'),
  save: m => call('/api/web/save', 'POST', { url: m.url, title: m.title, html: m.html || undefined }),
  tags: () => call('/api/web/tags'),
  async open(m){ const c = await conf(); await X.tabs.create({ url: c.url + '/#read/' + encodeURIComponent(m.doc) }); return true; },
  async test(){ await call('/api/web/page', 'POST', { url: 'https://example.com/' }); return true; },
  async badge(m, sender){
    const tabId = sender.tab && sender.tab.id;
    if (tabId == null) return false;
    await mark(tabId, m.count, m.saved);
    return true;
  },
  async options(){ await X.runtime.openOptionsPage(); return true; },
};

X.runtime.onMessage.addListener((m, sender, reply) => {
  const f = m && handlers[m.type];
  if (!f) return false;
  Promise.resolve().then(() => f(m, sender)).then(
    data => reply({ ok: true, data }),
    e => reply({ ok: false, error: (e && e.message) || String(e), kind: (e && e.kind) || 'error' }));
  return true;
});

/* The toolbar button says what Daf has: the page's highlights, or ✓ when it's in the Library. */
async function mark(tabId, count, saved){
  await X.action.setBadgeBackgroundColor({ tabId, color: '#1a7da4' });
  await X.action.setBadgeText({ tabId, text: count ? String(count) : saved ? '✓' : '' });
  await X.action.setTitle({ tabId, title: saved ? 'Daf: in your Library' + (count ? ', ' + count + (count === 1 ? ' highlight' : ' highlights') : '') : 'Daf' });
}

/* ---------- the right-click menu and the keys ---------- */
const MENU = [
  { id: 'save-page', title: 'Save this page to Daf', contexts: ['page'] },
  { id: 'save-link', title: 'Save this link to Daf', contexts: ['link'] },
  { id: 'highlight', title: 'Highlight in Daf', contexts: ['selection'] },
];
function menus(){
  if (!X.contextMenus) return;
  X.contextMenus.removeAll(() => { for (const m of MENU) X.contextMenus.create(m, () => void X.runtime.lastError); });
}
X.runtime.onInstalled.addListener(menus);
if (X.runtime.onStartup) X.runtime.onStartup.addListener(menus);

const tell = (tab, m) => Promise.resolve(X.tabs.sendMessage(tab.id, m));
const saidOf = r => r.words ? 'Saved with the page’s text, ' + r.words.toLocaleString() + ' words' : r.saved ? 'Saved to your Daf Library' : 'Already in your Daf Library';

/* Save the page: the page's own script sends what's on screen (a paywalled article whole) and
   says so; where it can't run, Daf reads the address itself. */
async function savePage(tab){
  if (!tab || tab.id == null || !/^https?:/.test(tab.url || '') || sameOrigin(tab.url, (await conf()).url)) return;
  try { await tell(tab, { type: 'save-page' }); return; } catch (e) { /* no page script here */ }
  const r = await call('/api/web/save', 'POST', { url: tab.url, title: tab.title });
  await mark(tab.id, 0, true);
  return r;
}

async function onMenu(info, tab){
  try {
    if (info.menuItemId === 'save-page') await savePage(tab);
    else if (info.menuItemId === 'highlight') await tell(tab, { type: 'hl-selection' });
    else if (info.menuItemId === 'save-link' && info.linkUrl) {
      const r = await call('/api/web/save', 'POST', { url: info.linkUrl, title: (info.linkText || '').trim() || undefined });
      tell(tab, { type: 'toast', text: r.saved ? 'Saved the link to your Daf Library' : 'That link is in your Daf Library already' }).catch(() => {});
    }
  } catch (e) {
    if (tab && tab.id != null) tell(tab, { type: 'toast', text: e.message }).catch(() => {});
  }
}
if (X.contextMenus) X.contextMenus.onClicked.addListener(onMenu);

if (X.commands) X.commands.onCommand.addListener(async (name, tab) => {
  if (!tab) [tab] = await X.tabs.query({ active: true, currentWindow: true });
  if (!tab || tab.id == null) return;
  if (name === 'highlight-selection') tell(tab, { type: 'hl-selection' }).catch(() => {});
  else if (name === 'save-page') savePage(tab).catch(() => {});
});
