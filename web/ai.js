/* Preferences → AI: what Daf asks the model, and which model (daf/ai.py), like Readwise's
   Ghostreader settings. Each prompt starts as Daf's own; one changed here is kept on the server for
   every device, and "Daf's own" brings the original back. */
(function(){
const C = window.DafCore, { $, esc, api, toast } = C;
let A = null;

function draw(card){
  const a = A.ai, model = a.model || '';
  const qs = (a.questions.length ? a.questions : A.questions).join('\n'), bqs = (a.book_questions.length ? a.book_questions : A.book_questions).join('\n');
  card.innerHTML = '<h2>AI</h2>' +
    '<p class="mute" style="margin:0">Summaries, Ask, the meaning of a word in its sentence and flashcard suggestions. It runs on your own subscription. Private titles never go on their own (summaries skip them); what you ask about yourself does.</p>' +
    '<div class="prow"><div class="d"><b>Summaries of what you save</b><span>Two or three lines on every article in the Library, a few each sync. Off, Summarize still works one at a time.</span></div><input type="checkbox" class="sw" id="aiauto"' + (a.auto_summary ? ' checked' : '') + ' aria-label="Summaries of what you save"></div>' +
    '<div class="prow"><div class="d"><b>Tags for what you save</b><span>Two to four on each new save in the Library, from the tags you already use where one fits. Never on a private one.</span></div><input type="checkbox" class="sw" id="aitags"' + (a.auto_tags ? ' checked' : '') + ' aria-label="Tags for what you save"></div>' +
    '<div class="prow"><div class="d"><b>Model</b><span>Daf’s default is ' + esc((A.models.find(m => m.id === A.default_model) || { label: A.default_model }).label.replace(/ \(.*/, '')) + '.</span></div><select class="field" id="aimodel" style="width:auto">' +
      A.models.map(m => '<option value="' + esc(m.id) + '"' + (m.id === model ? ' selected' : '') + '>' + esc(m.label) + '</option>').join('') + '</select></div>' +
    '<details class="steps"><summary>Ready questions</summary>' +
      '<label class="mute tiny" for="aiqs">In an article’s Ask, one a line</label><textarea class="field" id="aiqs" rows="3">' + esc(qs) + '</textarea>' +
      '<label class="mute tiny" for="aibqs">In a book’s Ask</label><textarea class="field" id="aibqs" rows="3">' + esc(bqs) + '</textarea>' +
      '<div style="display:flex;justify-content:flex-end"><button class="btn sm primary" data-ai="qs">Save</button></div></details>' +
    Object.keys(A.defaults).map(k => {
      const own = a.prompts[k], lab = A.labels[k];
      return '<details class="steps aip"><summary>' + esc(lab[0]) + (own ? ' <span class="pill">yours</span>' : '') + '</summary><span class="mute tiny">' + esc(lab[1]) + ' Daf adds what it’s about.</span>' +
        '<textarea class="field" data-aip="' + k + '" rows="4">' + esc(own || A.defaults[k]) + '</textarea>' +
        '<div style="display:flex;justify-content:flex-end;gap:8px">' + (own ? '<button class="btn sm" data-ai="reset" data-k="' + k + '">Daf’s own</button>' : '') +
        '<button class="btn sm primary" data-ai="save" data-k="' + k + '">Save</button></div></details>';
    }).join('');
}
async function put(body, said){
  try { A = await api('/api/ai', { method: 'PUT', body: JSON.stringify(body) }); toast(said || 'Saved'); }
  catch(e){ toast(e.message); }
  const card = $('#aicard'); if (card) { const open = [...card.querySelectorAll('details[open] summary')].map(x => x.textContent); draw(card); card.querySelectorAll('details summary').forEach(x => { if (open.includes(x.textContent)) x.parentNode.open = true; }); }
}
document.addEventListener('change', e => {
  if (e.target.id === 'aitags') put({ auto_tags: e.target.checked }, e.target.checked ? 'New saves get tags' : 'No tags from the model');
  if (e.target.id === 'aiauto') put({ auto_summary: e.target.checked }, e.target.checked ? 'Summaries on' : 'Summaries off: Summarize still works');
  if (e.target.id === 'aimodel') put({ model: e.target.value }, 'The model is ' + e.target.selectedOptions[0].textContent.replace(/ \(.*/, ''));
});
document.addEventListener('click', e => {
  const b = e.target.closest('[data-ai]'); if (!b) return;
  const lines = id => $(id).value.split('\n').map(x => x.trim()).filter(Boolean);
  if (b.dataset.ai === 'qs') put({ questions: lines('#aiqs'), book_questions: lines('#aibqs') }, 'Questions saved');
  else if (b.dataset.ai === 'save') put({ prompts: { [b.dataset.k]: b.closest('details').querySelector('textarea').value } }, 'Saved: ' + A.labels[b.dataset.k][0]);
  else if (b.dataset.ai === 'reset') put({ prompts: { [b.dataset.k]: '' } }, 'Daf’s own again');
});

C.AI = { prefs: async card => { A = await api('/api/ai'); draw(card); } };
})();
