/* Preferences → Import (daf/imports.py): an export file from another app. Daf tells which app it's
   from, shows what's in it, and brings it in in the background, a few links a second; this card
   follows along. */
(function(){
const C = window.DafCore, { $, esc, api, toast, ago } = C;

const APPS = [
  ['Instapaper', 'Settings → Export → Download .CSV file. Instapaper’s export has no highlights.'],
  ['Readwise Reader', 'Preferences → Export → Export library (CSV). Readwise highlights are already in Daf from the vault.'],
  ['Raindrop.io', 'Settings → Backups → Create new, then the CSV. Highlights come along.'],
  ['GoodLinks', 'Settings → Export → JSON. Highlights come along.'],
  ['Wallabag', 'Export → JSON. The articles’ text and annotations come along.'],
  ['Matter, Feedbin and others', 'Any CSV or JSON with a column of links (url), with titles, tags and dates when it has them.'],
  ['Feed readers (Feedly, Inoreader, NetNewsWire…)', 'Export your subscriptions as OPML. They go into FreshRSS, in their folders.'],
  ['Browsers and Pinboard', 'Bookmarks exported as an HTML file. Folders become tags.'],
  ['Pocket (closed July 2025)', 'The export it emailed you: the zip of CSV files, or the older ril_export.html.'],
  ['Omnivore (closed November 2024)', 'The export zip. The articles’ text and highlights come along, which matters for pages that are gone.'],
];
let timer = null;
const n = (x, one, many) => x + ' ' + (x === 1 ? one : (many || one + 's'));

function what(r){
  if (r.service === 'opml') return n(r.feeds, 'feed') + (r.folders.length ? ' in ' + n(r.folders.length, 'folder') : '');
  const st = r.status || {};
  return [n(r.links, 'link'), st.archive ? st.archive + ' read' : '', r.starred ? r.starred + ' starred' : '', r.tagged ? r.tagged + ' tagged' : '',
    r.highlights ? n(r.highlights, 'highlight') : '', r.with_text ? r.with_text + ' with their text' : ''].filter(Boolean).join(' · ');
}
function rowHTML(r){
  const done = r.pos || 0, total = r.total || 0, pct = total ? Math.round(done / total * 100) : 0;
  const head = '<b>' + esc(r.label) + '</b> <span class="mute tiny">' + esc(r.name || '') + ' · ' + ago(r.created) + '</span><div class="mute tiny">' + esc(what(r)) + '</div>';
  if (r.state === 'ready') {
    const read = r.service !== 'opml' && r.status && r.status.archive;
    return '<div class="imrow" data-imp="' + r.id + '">' + head +
      (read ? '<label class="imopt"><input type="checkbox" data-imarch> Bring the ' + r.status.archive + ' read ones too, into the Archive</label>' : '') +
      (r.service === 'opml' && r.folders.length ? '<label class="imopt"><input type="checkbox" data-imfold checked> Into their folders</label>' : '') +
      '<div class="imacts"><button class="btn sm" data-imgo="drop">Never mind</button><button class="btn sm primary" data-imgo="start">Bring ' + (r.service === 'opml' ? 'them' : 'it') + ' in</button></div></div>';
  }
  const tally = [r.added ? r.added + (r.service === 'opml' ? ' followed' : ' saved') : '', r.had ? r.had + (r.service === 'opml' ? ' followed already' : ' already in Daf') : '', r.skipped ? r.skipped + ' read ones left out' : '',
    r.hl_added ? n(r.hl_added, 'highlight') : '', r.failed ? r.failed + ' didn’t go' : ''].filter(Boolean).join(' · ');
  return '<div class="imrow" data-imp="' + r.id + '">' + head +
    (r.state === 'running' ? '<span class="pbar"><i style="width:' + pct + '%"></i></span><div class="mute tiny">' + done + ' of ' + total + (tally ? ' · ' + tally : '') + '</div><div class="imacts"><button class="btn sm" data-imgo="stop">Stop</button></div>'
      : '<div class="mute tiny">' + (r.state === 'stopped' ? 'Stopped at ' + done + ' of ' + total + '. ' : 'Done. ') + esc(tally) + '</div>' +
        (r.errors && r.errors.length ? '<details class="steps"><summary class="mute tiny">What didn’t go</summary><div class="mute tiny">' + r.errors.map(x => esc(x.url) + ': ' + esc(x.error)).join('<br>') + '</div></details>' : '') +
        '<div class="imacts">' + (r.state === 'stopped' ? '<button class="btn sm" data-imgo="start">Go on</button>' : '') + '<button class="btn sm" data-imgo="drop">Clear</button></div>') + '</div>';
}
async function prefs(card){
  const r = await api('/api/imports');
  card.innerHTML = '<h2>Import</h2>' +
    '<p class="mute" style="margin:0">Bring your library over from another app. Drop its export file here and Daf shows what’s in it before anything happens. Links go to the Library with when you saved them, whether you read them, stars and tags.</p>' +
    '<label class="adddrop" id="imdrop"><input type="file" id="imfile" accept=".csv,.json,.html,.htm,.opml,.xml,.zip,.txt" hidden><b>Drop an export file here</b><span class="mute tiny">or click to choose it</span></label>' +
    '<div id="imlist">' + r.imports.map(rowHTML).join('') + '</div>' +
    '<details class="steps"><summary>Where each app keeps its export</summary><ul class="imapps">' + APPS.map(a => '<li><b>' + esc(a[0]) + '</b>: ' + esc(a[1]) + '</li>').join('') + '</ul></details>';
  watch(r.imports);
}
function watch(list){
  clearTimeout(timer);
  if (!list.some(x => x.state === 'running')) return;
  timer = setTimeout(async () => {
    const card = $('#importcard'); if (!card) return;
    try { const r = await api('/api/imports'); const box = $('#imlist'); if (box) box.innerHTML = r.imports.map(rowHTML).join(''); watch(r.imports); } catch(e){}
  }, 2000);
}
async function upload(f){
  const box = $('#imlist'); if (!box) return;
  const note = document.createElement('div'); note.className = 'imrow mute'; note.textContent = 'Reading ' + f.name + '…'; box.prepend(note);
  try {
    const r = await fetch('/api/import?name=' + encodeURIComponent(f.name), { method: 'POST', body: f, credentials: 'same-origin' });
    const j = await r.json().catch(() => ({})); if (!r.ok) throw new Error(j.detail || r.statusText);
    note.outerHTML = rowHTML(Object.assign({ state: 'ready', created: Date.now() / 1000, name: f.name, total: j.links || j.feeds }, j));
  } catch(e){ note.textContent = e.message; note.classList.add('err'); }
}
document.addEventListener('change', e => { if (e.target.id === 'imfile' && e.target.files[0]) upload(e.target.files[0]); });
document.addEventListener('drop', e => {
  if (!e.target.closest || !e.target.closest('#imdrop')) return;
  e.preventDefault(); e.stopPropagation(); document.body.classList.remove('dropping');
  const f = e.dataTransfer.files[0]; if (f) upload(f);
}, true);
document.addEventListener('click', async e => {
  const b = e.target.closest('[data-imgo]'); if (!b) return;
  const row = b.closest('[data-imp]'), id = row.dataset.imp, go = b.dataset.imgo;
  b.disabled = true;
  try {
    if (go === 'start') {
      const a = row.querySelector('[data-imarch]'), f = row.querySelector('[data-imfold]');
      await api('/api/import/' + id + '/start', { method: 'POST', body: JSON.stringify({ archived: !!(a && a.checked), folders: !f || f.checked }) });
      toast('Bringing it in. You can leave this page; it goes on.');
    } else if (go === 'stop') await api('/api/import/' + id + '/stop', { method: 'POST' });
    else if (go === 'drop') await api('/api/import/' + id, { method: 'DELETE' });
  } catch(err){ toast(err.message); }
  prefs($('#importcard'));
});

C.Imports = { prefs };
})();
