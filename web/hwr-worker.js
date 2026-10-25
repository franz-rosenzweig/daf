// Reads handwriting off the page's thread, for pens.js: English with Grape (vendor/hwr, its model
// fetched once), and the lines of any handwriting, for a reader that takes a line at a time (the
// Android app's, for Hebrew). Moshe's lib/hwr/worker.js.
import { parseBundle, readPage, segmentPage, lineStrokes } from './vendor/hwr/grape.js';

let bundle = null;
async function model(url) {
  if (!bundle) {
    const r = await fetch(url);
    if (!r.ok) throw new Error('the handwriting reader could not be fetched (' + r.status + ')');
    bundle = parseBundle(await r.arrayBuffer());
  }
  return bundle;
}

self.onmessage = async (e) => {
  const { id, type, ink, url } = e.data;
  try {
    let result;
    if (type === 'read') result = readPage(await model(url), ink).lines.map((l) => ({ text: l.text, confidence: l.confidence, box: l.box }));
    else result = segmentPage(ink).lines.map((line) => ({ box: line.box, strokes: lineStrokes(line).map((s) => Array.from(s.pts)) }));
    self.postMessage({ id, result });
  } catch (err) {
    self.postMessage({ id, error: err.message || String(err) });
  }
};
