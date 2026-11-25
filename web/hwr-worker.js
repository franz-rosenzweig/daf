// Reads handwriting off the page's thread, for pens.js: English with Grape (vendor/hwr, its model
// fetched once: the one learned from your own writing when the server has it, /api/hwr/model, else
// Grape as shipped), and the lines of any handwriting, for a reader that takes a line at a time (the
// Android app's, for Hebrew). Moshe's lib/hwr/worker.js.
import { parseBundle, readPage, segmentPage, lineStrokes } from './vendor/hwr/grape.js';

let bundle = null;
// The first of `urls` that gives a model Grape can read.
async function model(urls) {
  if (!bundle) {
    let last = null;
    for (const url of urls) {
      try {
        const r = await fetch(url);
        if (!r.ok) throw new Error('the handwriting reader could not be fetched (' + r.status + ')');
        bundle = parseBundle(await r.arrayBuffer());
        break;
      } catch (err) { last = err; }
    }
    if (!bundle) throw last;
  }
  return bundle;
}

self.onmessage = async (e) => {
  const { id, type, ink, urls } = e.data;
  try {
    let result;
    if (type === 'read') result = readPage(await model(urls), ink).lines.map((l) => ({ text: l.text, confidence: l.confidence, box: l.box }));
    else result = segmentPage(ink).lines.map((line) => ({ box: line.box, strokes: lineStrokes(line).map((s) => Array.from(s.pts)) }));
    self.postMessage({ id, result });
  } catch (err) {
    self.postMessage({ id, error: err.message || String(err) });
  }
};
