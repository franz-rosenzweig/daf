/* Preferences → Library tags: every tag on saved articles, with how many use it. Rename one (a name
   already in use merges them), remove one everywhere, and the tidy-up: the model proposes merges
   for the whole list, and only the ones you tick happen (daf/tagging.py). */
(function(){
const C = window.DafCore, { $, esc, api, toast, ago } = C;
let st = null, q = '', poll = null;

async function load(card){
  try { st = await api('/api/doc-tags'); } catch(e){ card.innerHTML = '<h2>Library tags</h2><p class="mute">' + esc(e.message) + '</p>'; return; }
  draw(card);
  const j = st.job;
  clearTimeout(poll);
  if (j && (j.status === 'queued' || j.status === 'running')) poll = setTimeout(() => { if (card.isConnected) load(card); }, 5000);
}
function draw(card){
  const tags = st.tags, once = tags.filter(t => t.n === 1).length, j = st.job, busy = j && (j.status === 'queued' || j.status === 'running');
  const shown = tags.filter(t => !q || t.name.toLowerCase().includes(q.toLowerCase()));
  const tidy = st.tidy && st.tidy.changes && st.tidy.changes.length ? st.tidy : null;
  card.innerHTML = '<h2>Library tags</h2>' +
    '<p class="mute" style="margin:0">' + tags.length + ' tags on saved articles' + (once ? ', ' + once + ' of them used once' : '') + '. Renaming one to a name already in use merges the two.</p>' +
    '<div class="prow"><div class="d"><b>Tidy up</b><span>' + (busy ? 'The model is looking at the list. This takes a minute or two.' :
      tidy ? 'Proposed ' + ago(tidy.at) + ': tick what you want, then Apply.' : 'The model proposes merges for the whole list. Nothing changes until you tick and apply.') + '</span></div>' +
      '<button class="btn sm" id="tmtidy"' + (busy ? ' disabled' : '') + '>' + (tidy ? 'Propose again' : 'Propose a tidy-up') + '</button></div>' +
    (j && j.status === 'failed' && !busy ? '<p class="mute tiny">The last try didn’t work: ' + esc(j.error || '') + '</p>' : '') +
    (tidy ? '<div class="tmtidy">' + tidy.changes.map(x => '<label class="tmrow"><input type="checkbox" data-tmpick="' + x.id + '" checked><span><b>' +
        x.from.map(esc).join(', ') + '</b> → ' + (x.to ? '<b>' + esc(x.to) + '</b>' : '<i>removed</i>') + ' <span class="mute tiny">' + x.docs + (x.docs === 1 ? ' article' : ' articles') +
        (x.why ? ' · ' + esc(x.why) : '') + '</span></span></label>').join('') +
      '<div style="display:flex;gap:8px;justify-content:flex-end"><button class="btn sm" id="tmnone">Untick all</button><button class="btn sm primary" id="tmapply">Apply the ticked ones</button></div></div>' : '') +
    '<input class="field sm" id="tmq" placeholder="Find a tag" autocomplete="off" value="' + esc(q) + '" style="width:100%">' +
    '<div class="tmlist">' + shown.map(t => '<div class="tmtag" data-tm="' + esc(t.name) + '"><span class="tmname">' + esc(t.name) + '</span><span class="mute tiny">' + t.n + '</span>' +
      '<button class="linkbtn tiny" data-tmact="rename">Rename</button><button class="linkbtn tiny" data-tmact="rm">Remove</button></div>').join('') +
      (shown.length ? '' : '<span class="mute tiny">No tag has that in it.</span>') + '</div>';
  const qi = card.querySelector('#tmq');
  qi.oninput = () => { q = qi.value; const pos = qi.selectionStart; draw(card); const n = card.querySelector('#tmq'); n.focus(); n.setSelectionRange(pos, pos); };
  card.querySelector('#tmtidy').onclick = async () => { try { await api('/api/doc-tags/tidy', { method: 'POST' }); load(card); } catch(e){ toast(e.message); } };
  const none = card.querySelector('#tmnone'); if (none) none.onclick = () => card.querySelectorAll('[data-tmpick]').forEach(x => { x.checked = false; });
  const ap = card.querySelector('#tmapply');
  if (ap) ap.onclick = async () => {
    const ids = [...card.querySelectorAll('[data-tmpick]:checked')].map(x => +x.dataset.tmpick);
    if (!ids.length) { toast('Nothing ticked'); return; }
    ap.disabled = true;
    try { const r = await api('/api/doc-tags/apply', { method: 'POST', body: JSON.stringify({ ids }) }); toast(r.changed + (r.changed === 1 ? ' article' : ' articles') + ' retagged'); load(card); }
    catch(e){ toast(e.message); ap.disabled = false; }
  };
  card.onclick = async e => {
    const b = e.target.closest('[data-tmact]'); if (!b) return;
    const name = b.closest('[data-tm]').dataset.tm;
    if (b.dataset.tmact === 'rm') {
      if (!confirm('Remove the tag “' + name + '” from every article?')) return;
      try { const r = await api('/api/doc-tags/rename', { method: 'POST', body: JSON.stringify({ from: name, to: '' }) }); toast('Removed from ' + r.changed + (r.changed === 1 ? ' article' : ' articles')); load(card); } catch(err){ toast(err.message); }
      return;
    }
    const to = prompt('Rename “' + name + '” to (a name already in use merges them):', name);
    if (to == null || !to.trim() || to.trim() === name) return;
    try { const r = await api('/api/doc-tags/rename', { method: 'POST', body: JSON.stringify({ from: name, to: to.trim() }) }); toast(r.changed + (r.changed === 1 ? ' article' : ' articles') + ' now say “' + to.trim() + '”'); load(card); } catch(err){ toast(err.message); }
  };
}
C.TagMan = { prefs: load };
})();
