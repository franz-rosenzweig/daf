/* The toolbar button: is this page in Daf, how many highlights it has, save it, open it in Daf. */
const P = globalThis.browser || globalThis.chrome;
const $ = s => document.querySelector(s);
const esc = s => String(s == null ? '' : s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]);
const count = n => n === 1 ? '1 highlight' : n ? n + ' highlights' : 'No highlights yet';
const WHERE = { library: 'In your Library', feed: 'In your Feed', deleted: 'Deleted from your Library' };

async function send(msg){
  const r = await P.runtime.sendMessage(msg);
  if (!r) throw new Error('The extension didn’t answer. Try again.');
  if (!r.ok) throw Object.assign(new Error(r.error), { kind: r.kind });
  return r.data;
}
const show = html => { $('#body').innerHTML = html; };
function openOptions(){ P.runtime.openOptionsPage(); window.close(); }

let tab = null, conf = null;

function setup(msg){
  show('<p style="margin:0">' + esc(msg || 'Connect the extension to Daf first.') + '</p>' +
    '<p class="mute tiny" style="margin:0">In Daf, open Preferences, then Account, and make a token for the browser extension. Paste it in the options.</p>' +
    '<div class="pacts"><button class="btn primary" id="go" type="button">Open options</button></div>');
  $('#go').onclick = openOptions;
}

function draw(p, note){
  if (p.skip) return show('<p class="mute" style="margin:0">This is Daf itself. Highlight here with Daf’s own toolbar.</p>');
  const n = (p.highlights || []).length, saved = !!p.doc_id, inLib = saved && p.where === 'library';
  show('<h1 class="ptitle">' + esc(tab.title || tab.url) + '</h1>' +
    '<div class="pstate' + (saved ? ' on' : '') + '"><i></i><span>' + (saved ? (WHERE[p.where] || 'In Daf') + ' · ' + count(n) : 'Not in Daf yet') + '</span></div>' +
    (note ? '<p class="mute tiny" style="margin:0">' + esc(note) + '</p>' : '') +
    '<div class="pacts">' + (inLib ? '' : '<button class="btn primary" id="save" type="button">Save this page to Daf</button>') +
    (saved ? '<button class="btn' + (inLib ? ' primary' : '') + '" id="open" type="button">Open in Daf</button>' : '') + '</div>' +
    '<button class="linkbtn" id="panel" type="button">' + (n ? 'Show my highlights on the page' : 'Open the highlights panel') + '</button>' +
    (inLib ? '<button class="linkbtn" id="retext" type="button" title="For a page behind a paywall you’re signed in to: Daf keeps the text you see">Give Daf this page’s text</button>' : '') +
    '<p class="perr" id="err" hidden></p>');
  const sv = $('#save'), op = $('#open'), rt = $('#retext');
  // The page as this tab shows it (content.js), for a paywall Daf's own reading can't see past.
  const page = async () => { try { const r = await P.tabs.sendMessage(tab.id, { type: 'snapshot' }); return (r && r.html) || undefined; } catch (e) { return undefined; } };
  if (rt) rt.onclick = async () => {
    rt.disabled = true; rt.textContent = 'Reading the page…';
    try {
      const html = await page();
      if (!html) throw new Error('Reload the page first: Daf wasn’t running on it yet.');
      const r = await send({ type: 'save', url: tab.url, title: tab.title, html });
      draw(await send({ type: 'page', url: tab.url }), r.words ? 'Daf now has this page’s text: ' + r.words.toLocaleString() + ' words.' : 'Daf’s copy already had as much as this page shows.');
    } catch (e) { const er = $('#err'); er.textContent = e.message; er.hidden = false; rt.disabled = false; rt.textContent = 'Give Daf this page’s text'; }
  };
  $('#panel').onclick = async () => {
    try { await P.tabs.sendMessage(tab.id, { type: 'panel', open: true }); window.close(); }
    catch (e) { const er = $('#err'); er.textContent = 'Reload the page first: Daf wasn’t running on it yet.'; er.hidden = false; }
  };
  if (op) op.onclick = () => { P.tabs.create({ url: conf.url + '/#read/' + encodeURIComponent(p.doc_id) }); window.close(); };
  if (sv) sv.onclick = async () => {
    sv.disabled = true; sv.textContent = 'Saving…';
    try {
      const r = await send({ type: 'save', url: tab.url, title: tab.title, html: await page() });
      draw(await send({ type: 'page', url: tab.url }), r.words ? 'Saved with the text you see here: ' + r.words.toLocaleString() + ' words.' : r.saved ? 'Saved. Daf reads the page in a moment.' : '');
    } catch (e) {
      if (e.kind === 'setup') return setup(e.message);
      sv.disabled = false; sv.textContent = 'Save this page to Daf';
      const er = $('#err'); er.textContent = e.message; er.hidden = false;
    }
  };
}

async function main(){
  $('#opts').onclick = openOptions;
  try {
    const cmd = (await P.commands.getAll()).find(c => c.name === 'highlight-selection');
    $('#keyhint').innerHTML = cmd && cmd.shortcut ? '<kbd>' + esc(cmd.shortcut) + '</kbd> highlights a selection' : 'Select text on the page to highlight it';
  } catch (e) { /* no shortcuts here */ }
  [tab] = await P.tabs.query({ active: true, currentWindow: true });
  conf = await send({ type: 'conf' });
  if (!conf.connected) return setup();
  if (!tab || !/^https?:\/\//.test(tab.url || '')) return show('<p class="mute" style="margin:0">Daf saves web pages, and this isn’t one.</p>');
  try { draw(await send({ type: 'page', url: tab.url })); }
  catch (e) {
    if (e.kind === 'setup') return setup(e.message);
    show('<p class="perr">' + esc(e.message) + '</p><div class="pacts"><button class="btn" id="again" type="button">Try again</button></div>');
    $('#again').onclick = main;
  }
}
main();
