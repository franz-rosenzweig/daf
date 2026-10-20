/* The options page: Daf's address and the device token, kept in the extension's own storage. */
const P = globalThis.browser || globalThis.chrome;
const DEFAULT_URL = 'https://daf.tiresia.xyz';
const $ = s => document.querySelector(s);

function status(text, kind){ const s = $('#status'); s.textContent = text; s.className = 'status' + (kind ? ' ' + kind : ''); }

async function test(){
  status('Checking…');
  const r = await P.runtime.sendMessage({ type: 'test' });
  if (r && r.ok) status('Connected to Daf.', 'ok');
  else status((r && r.error) || 'The extension didn’t answer.', 'bad');
}

$('#f').addEventListener('submit', async e => {
  e.preventDefault();
  let url;
  try { url = new URL($('#url').value.trim() || DEFAULT_URL); } catch (err) { return status('That address doesn’t look right.', 'bad'); }
  if (!/^https?:$/.test(url.protocol)) return status('The address starts with https:// or http://.', 'bad');
  // Asked first, while the click still counts: a browser only asks about access during one. Chrome
  // grants it at install; Firefox and Zen can hold it back, and without it nothing is drawn on a page.
  let allowed = true;
  try { allowed = await P.permissions.request({ origins: ['http://*/*', 'https://*/*'] }); } catch (err) { /* already granted */ }
  if (!allowed) return status('The extension needs access to the pages you read, and to Daf, to work.', 'bad');
  const base = (url.origin + url.pathname).replace(/\/+$/, '');
  await P.storage.local.set({ url: base, token: $('#token').value.trim() });
  $('#url').value = base;
  if (!$('#token').value.trim()) return status('Saved. Paste a token to connect.', 'bad');
  test();
});

$('#auto').addEventListener('change', e => P.storage.local.set({ auto: e.target.checked }));

(async () => {
  const s = await P.storage.local.get({ url: DEFAULT_URL, token: '', auto: true });
  $('#auto').checked = s.auto !== false;
  $('#url').value = s.url || DEFAULT_URL;
  $('#token').value = s.token || '';
  try {
    const cmd = (await P.commands.getAll()).find(c => c.name === 'highlight-selection');
    if (cmd && cmd.shortcut) $('#key').textContent = cmd.shortcut;
  } catch (err) { /* no shortcuts here */ }
  if (s.token) test();
})();
