// Grape's reader, from FineNotes 2.4.1 (https://github.com/joost-8/FineNotes, commit 26f9ee9,
// src/recognition/hwr: recognizer, bundle, blstm, simd, ctc, char-lm, curves, features, lines,
// numeric), bundled to one file with esbuild and otherwise unchanged (as Moshe has it, its
// frontend/src/lib/hwr/grape.js). It reads lines of handwriting from the pen's strokes with the
// Grape model (grape-2.0.bin beside it, Apache-2.0: LICENSE and NOTICE here).
//
// Copyright 2026 Joost (FineNotes). GPL-3.0-or-later, as Daf is.
// To make it again: copy those files from FineNotes and bundle an entry that exports
// parseBundle, readPage, readLine, simdAvailable, segmentPage and lineStrokes.

var __defProp = Object.defineProperty;
var __defNormalProp = (obj, key, value) => key in obj ? __defProp(obj, key, { enumerable: true, configurable: true, writable: true, value }) : obj[key] = value;
var __publicField = (obj, key, value) => __defNormalProp(obj, typeof key !== "symbol" ? key + "" : key, value);

// char-lm.ts
var CharLm = class _CharLm {
  constructor(order, chars, V, nodeChar, children, predCount, predChar, counts) {
    this.order = order;
    this.chars = chars;
    this.V = V;
    this.nodeChar = nodeChar;
    this.children = children;
    this.predCount = predCount;
    this.predChar = predChar;
    this.counts = counts;
    __publicField(this, "codes", /* @__PURE__ */ new Map());
    __publicField(this, "firstChild");
    __publicField(this, "firstPred");
    __publicField(this, "totals");
    chars.forEach((c, i) => this.codes.set(c, i));
    const nodes = nodeChar.length;
    this.firstChild = new Uint32Array(nodes);
    this.firstPred = new Uint32Array(nodes);
    this.totals = new Float64Array(nodes);
    let child = 1;
    let pred = 0;
    for (let i = 0; i < nodes; i++) {
      this.firstChild[i] = child;
      this.firstPred[i] = pred;
      child += children[i];
      let total = 0;
      for (let k = 0; k < predCount[i]; k++) total += counts[pred + k];
      this.totals[i] = total;
      pred += predCount[i];
    }
    if (child !== nodes || pred !== predChar.length) {
      throw new Error("the language model's tables do not add up");
    }
  }
  /** Read the "LM01" section at `start` (`size` bytes) of `buffer`. */
  static fromSection(meta, buffer, start, size) {
    const view = new DataView(buffer, start, size);
    const nodes = view.getUint32(0, true);
    const preds = view.getUint32(4, true);
    const countBytes = view.getUint32(8, true);
    if (nodes !== meta.nodes || preds !== meta.preds || 12 + 3 * nodes + preds + countBytes > size) {
      throw new Error("the language model section does not match its header");
    }
    let o = start + 12;
    const bytes = (n) => {
      const a = new Uint8Array(buffer, o, n);
      o += n;
      return a;
    };
    const nodeChar = bytes(nodes);
    const children = bytes(nodes);
    const predCount = bytes(nodes);
    const predChar = bytes(preds);
    const raw = bytes(countBytes);
    const counts = new Uint32Array(preds);
    let p = 0;
    for (let i = 0; i < preds; i++) {
      let v = 0;
      let mul = 1;
      for (; ; ) {
        if (p >= raw.length) throw new Error("the language model's counts end early");
        const b = raw[p++];
        v += (b & 127) * mul;
        mul *= 128;
        if (b < 128) break;
      }
      counts[i] = v;
    }
    return new _CharLm(
      meta.order,
      meta.chars,
      meta.V,
      nodeChar,
      children,
      predCount,
      predChar,
      counts
    );
  }
  /** The LM's code for a character, or -1 for one it has never seen. */
  codeOf(ch) {
    return this.codes.get(ch) ?? -1;
  }
  /** Index of `code` in the sorted `keys[start, start + n)`, or -1. */
  static find(keys, start, n, code) {
    let lo = start;
    let hi = start + n;
    while (lo < hi) {
      const mid = lo + hi >> 1;
      if (keys[mid] < code) lo = mid + 1;
      else hi = mid;
    }
    return lo < start + n && keys[lo] === code ? lo : -1;
  }
  /** The contexts of `history` (its last order − 1 characters, BOS-padded) the model has. */
  context(history) {
    const nodes = [0];
    let node = 0;
    for (let k = 1; k < this.order; k++) {
      const code = k <= history.length ? this.codeOf(history[history.length - k]) : 0;
      if (code < 0) break;
      node = _CharLm.find(this.nodeChar, this.firstChild[node], this.children[node], code);
      if (node < 0) break;
      nodes.push(node);
    }
    return nodes;
  }
  /** P(code | context); a code of -1 (unknown) only gets the smoothing mass. */
  probIn(context, code) {
    let p = 1 / this.V;
    for (const node of context) {
      const types = this.predCount[node];
      const at = code < 0 ? -1 : _CharLm.find(this.predChar, this.firstPred[node], types, code);
      const count = at < 0 ? 0 : this.counts[at];
      p = (count + types * p) / (this.totals[node] + types);
    }
    return p;
  }
  /** P(ch | history), as `CharLM.prob`. */
  prob(history, ch) {
    return this.probIn(this.context(history), this.codeOf(ch));
  }
};

// numeric.ts
function pairwise(a, start, n) {
  if (n < 8) {
    let res = 0;
    for (let i = 0; i < n; i++) res += a[start + i];
    return res;
  }
  if (n <= 128) {
    let r0 = a[start], r1 = a[start + 1], r2 = a[start + 2], r3 = a[start + 3], r4 = a[start + 4], r5 = a[start + 5], r6 = a[start + 6], r7 = a[start + 7];
    let i = 8;
    for (; i < n - n % 8; i += 8) {
      const o = start + i;
      r0 += a[o];
      r1 += a[o + 1];
      r2 += a[o + 2];
      r3 += a[o + 3];
      r4 += a[o + 4];
      r5 += a[o + 5];
      r6 += a[o + 6];
      r7 += a[o + 7];
    }
    let res = r0 + r1 + (r2 + r3) + (r4 + r5 + (r6 + r7));
    for (; i < n; i++) res += a[start + i];
    return res;
  }
  let n2 = Math.floor(n / 2);
  n2 -= n2 % 8;
  return pairwise(a, start, n2) + pairwise(a, start + n2, n - n2);
}
function npSum(a) {
  return 0 + pairwise(a, 0, a.length);
}
function npMean(a) {
  return npSum(a) / a.length;
}
function linspace(start, stop, n) {
  const out = new Float64Array(n);
  if (n === 1) {
    out[0] = start;
    return out;
  }
  const step = (stop - start) / (n - 1);
  for (let i = 0; i < n; i++) out[i] = i * step + start;
  if (n > 1) out[n - 1] = stop;
  return out;
}
function interp(x, xp, fp) {
  const n = xp.length;
  const out = new Float64Array(x.length);
  if (n === 1) {
    for (let i = 0; i < x.length; i++) out[i] = fp[0];
    return out;
  }
  let j = 0;
  for (let i = 0; i < x.length; i++) {
    const v = x[i];
    if (v < xp[0]) {
      out[i] = fp[0];
      continue;
    }
    if (v > xp[n - 1]) {
      out[i] = fp[n - 1];
      continue;
    }
    while (j > 0 && xp[j] > v) j--;
    while (j + 1 < n && xp[j + 1] <= v) j++;
    if (j === n - 1 || xp[j] === v) {
      out[i] = fp[j];
      continue;
    }
    const slope = (fp[j + 1] - fp[j]) / (xp[j + 1] - xp[j]);
    out[i] = slope * (v - xp[j]) + fp[j];
  }
  return out;
}
function sorted(a) {
  return Float64Array.from(a).sort();
}
function percentileSorted(s, q) {
  const n = s.length;
  const v = (n - 1) * (q / 100);
  if (v >= n - 1) return s[n - 1];
  const lo = Math.floor(v);
  const gamma = v - lo;
  const a = s[lo];
  const b = s[lo + 1];
  const diff = b - a;
  return gamma >= 0.5 ? b - diff * (1 - gamma) : a + diff * gamma;
}
function median(a) {
  const s = sorted(a);
  const n = s.length;
  if (n === 0) return NaN;
  const mid = n >> 1;
  return n % 2 ? s[mid] : (s[mid - 1] + s[mid]) / 2;
}
function fitLine(x, y) {
  const mx = npMean(x);
  const my = npMean(y);
  let sxx = 0;
  let sxy = 0;
  for (let i = 0; i < x.length; i++) {
    const dx = x[i] - mx;
    sxx += dx * dx;
    sxy += dx * (y[i] - my);
  }
  const a = sxy / sxx;
  return [a, my - a * mx];
}

// curves.ts
var CURVE_RAW = 10;
var FIT_ITERS = 4;
function fitCubic(q, a, b) {
  const n = b - a + 1;
  const p0 = [q[a * 3], q[a * 3 + 1], q[a * 3 + 2]];
  const p3 = [q[b * 3], q[b * 3 + 1], q[b * 3 + 2]];
  const lineP1 = [0, 0, 0];
  const lineP2 = [0, 0, 0];
  for (let c = 0; c < 3; c++) {
    lineP1[c] = p0[c] + (p3[c] - p0[c]) / 3;
    lineP2[c] = p3[c] - (p3[c] - p0[c]) / 3;
  }
  if (n <= 2) return { p1: lineP1, p2: lineP2, err: 0 };
  const s = new Float64Array(n);
  for (let i = 1; i < n; i++) {
    const o = (a + i) * 3;
    const dx = q[o] - q[o - 3];
    const dy = q[o + 1] - q[o - 2];
    const dt = q[o + 2] - q[o - 1];
    s[i] = s[i - 1] + Math.sqrt(dx * dx + dy * dy + dt * dt);
  }
  const total = s[n - 1];
  if (total <= 0) return { p1: [...p0], p2: [...p3], err: 0 };
  for (let i = 0; i < n; i++) s[i] /= total;
  let p1 = lineP1;
  let p2 = lineP2;
  for (let it = 0; it < FIT_ITERS; it++) {
    let a11 = 0;
    let a12 = 0;
    let a22 = 0;
    const r1 = [0, 0, 0];
    const r2 = [0, 0, 0];
    for (let i = 0; i < n; i++) {
      const si = s[i];
      const u = 1 - si;
      const b0 = u * u * u;
      const b1 = 3 * u * u * si;
      const b2 = 3 * u * si * si;
      const b3 = si * si * si;
      a11 += b1 * b1;
      a12 += b1 * b2;
      a22 += b2 * b2;
      const o = (a + i) * 3;
      for (let c = 0; c < 3; c++) {
        const r = q[o + c] - b0 * p0[c] - b3 * p3[c];
        r1[c] += b1 * r;
        r2[c] += b2 * r;
      }
    }
    const det = a11 * a22 - a12 * a12;
    if (det < 1e-10) {
      p1 = lineP1;
      p2 = lineP2;
      break;
    }
    p1 = [0, 0, 0];
    p2 = [0, 0, 0];
    for (let c = 0; c < 3; c++) {
      p1[c] = (a22 * r1[c] - a12 * r2[c]) / det;
      p2[c] = (a11 * r2[c] - a12 * r1[c]) / det;
    }
    for (let i = 0; i < n; i++) {
      const si = s[i];
      const u = 1 - si;
      const b0 = u * u * u;
      const b1 = 3 * u * u * si;
      const b2 = 3 * u * si * si;
      const b3 = si * si * si;
      const k1 = 3 * (u * u);
      const k2 = 6 * (u * si);
      const k3 = 3 * (si * si);
      const o = (a + i) * 3;
      let num = 0;
      let dd = 0;
      let dx2 = 0;
      for (let c = 0; c < 3; c++) {
        const diff = b0 * p0[c] + b1 * p1[c] + b2 * p2[c] + b3 * p3[c] - q[o + c];
        const d1 = k1 * (p1[c] - p0[c]) + k2 * (p2[c] - p1[c]) + k3 * (p3[c] - p2[c]);
        const d2 = 6 * u * (p2[c] - 2 * p1[c] + p0[c]) + 6 * si * (p3[c] - 2 * p2[c] + p1[c]);
        num += diff * d1;
        dd += d1 * d1;
        dx2 += diff * d2;
      }
      const den = dd + dx2;
      const step = Math.abs(den) > 1e-12 ? num / den : 0;
      s[i] = Math.min(Math.max(si - step, 0), 1);
    }
    s[0] = 0;
    s[n - 1] = 1;
  }
  let err = 0;
  for (let i = 0; i < n; i++) {
    const si = s[i];
    const u = 1 - si;
    const b0 = u * u * u;
    const b1 = 3 * u * u * si;
    const b2 = 3 * u * si * si;
    const b3 = si * si * si;
    const o = (a + i) * 3;
    let sq = 0;
    for (let c = 0; c < 3; c++) {
      const d = b0 * p0[c] + b1 * p1[c] + b2 * p2[c] + b3 * p3[c] - q[o + c];
      sq += d * d;
    }
    const e = Math.sqrt(sq);
    if (e > err || Number.isNaN(e)) err = e;
  }
  return { p1, p2, err };
}
function fitStroke(q, from, to, tol, emit) {
  const last = to - 1;
  if (to - from === 1) {
    const p = [q[from * 3], q[from * 3 + 1], q[from * 3 + 2]];
    emit(from, from, p, p);
    return;
  }
  let a = from;
  while (a < last) {
    let good = a + 1;
    let best = [
      [0, 1, 2].map((c) => q[a * 3 + c] + (q[good * 3 + c] - q[a * 3 + c]) / 3),
      [0, 1, 2].map((c) => q[good * 3 + c] - (q[good * 3 + c] - q[a * 3 + c]) / 3)
    ];
    let bad = -1;
    let step = 4;
    while (good < last) {
      const b = Math.min(a + step, last);
      const fit = fitCubic(q, a, b);
      if (fit.err <= tol) {
        good = b;
        best = [fit.p1, fit.p2];
        step *= 2;
      } else {
        bad = b;
        break;
      }
    }
    if (bad >= 0) {
      while (bad - good > 1) {
        const mid = Math.floor((good + bad) / 2);
        const fit = fitCubic(q, a, mid);
        if (fit.err <= tol) {
          good = mid;
          best = [fit.p1, fit.p2];
        } else {
          bad = mid;
        }
      }
    }
    emit(a, good, best[0], best[1]);
    a = good;
  }
}
function curvesFromFeatures(f, frames, tol, channels = CURVE_RAW) {
  if (channels < CURVE_RAW) throw new Error(`a curve needs ${CURVE_RAW} channels`);
  const x = new Float64Array(frames);
  const y = new Float64Array(frames);
  const t = new Float64Array(frames);
  const stroke = new Int32Array(frames);
  let cx = 0;
  let cy = 0;
  let ct = 0;
  let ns = 0;
  for (let i = 0; i < frames; i++) {
    cx += f[i * 4];
    cy += f[i * 4 + 1];
    ct += f[i * 4 + 2];
    if (f[i * 4 + 3] > 0.5) ns++;
    x[i] = cx;
    y[i] = cy;
    t[i] = ct;
    stroke[i] = Math.max(ns - 1, 0);
  }
  const starts = [0];
  for (let i = 1; i < frames; i++) if (stroke[i] !== stroke[i - 1]) starts.push(i);
  starts.push(frames);
  let ink = 0;
  for (let k2 = 0; k2 + 1 < starts.length; k2++) {
    const a = starts[k2];
    const b = starts[k2 + 1];
    const seg = new Float64Array(Math.max(b - a - 1, 0));
    for (let i = a + 1; i < b; i++) {
      const dx = x[i] - x[i - 1];
      const dy = y[i] - y[i - 1];
      seg[i - a - 1] = Math.sqrt(dx * dx + dy * dy);
    }
    ink += npSum(seg);
  }
  const dur = t[frames - 1] - t[0];
  const k = dur > 0 && ink > 0 ? ink / dur : 1;
  const q = new Float64Array(frames * 3);
  for (let i = 0; i < frames; i++) {
    q[i * 3] = x[i];
    q[i * 3 + 1] = y[i];
    q[i * 3 + 2] = (t[i] - t[0]) * k;
  }
  const rows = [];
  const src = [];
  let prev = -1;
  for (let s = 0; s + 1 < starts.length; s++) {
    const a = starts[s];
    const b = starts[s + 1];
    if (prev >= 0) {
      const d0 = q[a * 3] - q[prev * 3];
      const d1 = q[a * 3 + 1] - q[prev * 3 + 1];
      const d2 = q[a * 3 + 2] - q[prev * 3 + 2];
      rows.push(d0, d1, d0 / 3, d1 / 3, -d0 / 3, -d1 / 3, d2, 0, 0, 1);
      src.push(stroke[a]);
    }
    fitStroke(q, a, b, tol, (i, j, p1, p2) => {
      const t0 = q[i * 3 + 2];
      const t3 = q[j * 3 + 2];
      const t1 = p1[2];
      const t2 = p2[2];
      rows.push(
        q[j * 3] - q[i * 3],
        q[j * 3 + 1] - q[i * 3 + 1],
        p1[0] - q[i * 3],
        p1[1] - q[i * 3 + 1],
        p2[0] - q[j * 3],
        p2[1] - q[j * 3 + 1],
        3 * (t1 - t0),
        3 * (t2 - 2 * t1 + t0),
        t3 - 3 * t2 + 3 * t1 - t0,
        0
      );
      src.push(stroke[a]);
    });
    prev = b - 1;
  }
  const n = src.length;
  const features = new Float32Array(n * channels);
  for (let r = 0; r < n; r++) {
    for (let c = 0; c < CURVE_RAW; c++) features[r * channels + c] = rows[r * CURVE_RAW + c];
  }
  return { features, frames: n, curveStroke: Int32Array.from(src) };
}
function networkInput(input, inputs, features, frames) {
  if (!input) return { features, frames };
  return curvesFromFeatures(features, frames, input.tol, inputs);
}

// bundle.ts
var MAGIC = 1464356422;
var BUNDLE_FORMAT_POINTS = 1;
var BUNDLE_FORMAT_INPUT = 2;
var HwrFormatError = class extends Error {
  constructor(message) {
    super(message);
    this.name = "HwrFormatError";
  }
};
var Reader = class {
  constructor(buffer, start, end) {
    this.buffer = buffer;
    this.start = start;
    this.end = end;
    __publicField(this, "pos", 0);
    this.pos = start;
  }
  take(bytes) {
    const at = this.pos;
    if (at + bytes > this.end) throw new HwrFormatError("the file ends inside the network");
    this.pos += bytes + (4 - bytes % 4) % 4;
    return at;
  }
  f32(n) {
    return new Float32Array(this.buffer, this.take(n * 4), n);
  }
  i8(n) {
    return new Int8Array(this.buffer, this.take(n), n);
  }
  get consumed() {
    return this.pos - this.start;
  }
};
function readNet(meta, buffer, start, end) {
  const { inputs, hidden: H, layers, classes, standardize: standardize2 } = meta.net;
  const r = new Reader(buffer, start, end);
  const mean = standardize2 ? r.f32(inputs) : null;
  const std = standardize2 ? r.f32(inputs) : null;
  const out = [];
  for (let k = 0; k < layers; k++) {
    const n = k === 0 ? inputs : 2 * H;
    const dir = () => {
      const wihScale = r.f32(4 * H);
      const whhScale = r.f32(4 * H);
      const bias = r.f32(4 * H);
      const wih = r.i8(4 * H * n);
      const whh = r.i8(4 * H * H);
      return { inputs: n, wih, wihScale, whh, whhScale, bias };
    };
    out.push([dir(), dir()]);
  }
  const outScale = r.f32(classes);
  const outBias = r.f32(classes);
  const weights = r.i8(classes * 2 * H);
  if (start + r.consumed !== end)
    throw new HwrFormatError("the network section has a size its header does not explain");
  return { inputs, hidden: H, classes, mean, std, layers: out, out: weights, outScale, outBias };
}
function checkInput(meta) {
  const input = meta.input;
  if (!input) throw new HwrFormatError("a version 2 model file must say what its network reads");
  if (input.kind !== "curves" || input.encoding !== "raw") {
    throw new HwrFormatError(
      `the model reads ${String(input.kind)} (${String(input.encoding)}); this build computes raw curves`
    );
  }
  if (!(input.tol > 0 && Number.isFinite(input.tol)))
    throw new HwrFormatError(`curve tolerance ${input.tol}`);
  if (meta.net.inputs < CURVE_RAW)
    throw new HwrFormatError(`${meta.net.inputs} network inputs for ${CURVE_RAW} curve values`);
}
function parseBundle(bytes) {
  const src = bytes instanceof Uint8Array ? bytes : new Uint8Array(bytes);
  const buffer = new ArrayBuffer(src.byteLength);
  new Uint8Array(buffer).set(src);
  const view = new DataView(buffer);
  if (buffer.byteLength < 12 || view.getUint32(0, true) !== MAGIC) {
    throw new HwrFormatError("not a FineNotes handwriting model (no FNHW header)");
  }
  const version = view.getUint32(4, true);
  if (version !== BUNDLE_FORMAT_POINTS && version !== BUNDLE_FORMAT_INPUT)
    throw new HwrFormatError(
      `model file version ${version}; this build reads ${BUNDLE_FORMAT_POINTS} and ${BUNDLE_FORMAT_INPUT}`
    );
  const metaLength = view.getUint32(8, true);
  if (12 + metaLength > buffer.byteLength)
    throw new HwrFormatError("the file ends inside its header");
  const meta = JSON.parse(
    new TextDecoder().decode(new Uint8Array(buffer, 12, metaLength))
  );
  if (meta.features?.version !== "v2" || meta.features.norm !== "skew=0,slant=0,scale=core") {
    throw new HwrFormatError(
      `the model expects ${meta.features?.version} features with "${meta.features?.norm}"; this build computes v2 with core scaling only`
    );
  }
  if (version === BUNDLE_FORMAT_POINTS) delete meta.input;
  else checkInput(meta);
  if (meta.net.classes !== meta.alphabet.length + 1) {
    throw new HwrFormatError(`${meta.net.classes} classes for ${meta.alphabet.length} characters`);
  }
  let o = 12 + metaLength;
  let net = null;
  let lm = null;
  while (o + 8 <= buffer.byteLength) {
    const tag = String.fromCharCode(...new Uint8Array(buffer, o, 4));
    const size = view.getUint32(o + 4, true);
    const start = o + 8;
    if (start + size > buffer.byteLength)
      throw new HwrFormatError(`section ${tag} runs past the end of the file`);
    if (tag === "NET1") net = readNet(meta, buffer, start, start + size);
    else if (tag === "LM01" && meta.lm) lm = CharLm.fromSection(meta.lm, buffer, start, size);
    o = start + size + (4 - size % 4) % 4;
  }
  if (!net) throw new HwrFormatError("the file has no network");
  return { meta, net, lm };
}

// simd.ts
function u32(n) {
  const out = [];
  do {
    let byte = n & 127;
    n >>>= 7;
    if (n !== 0) byte |= 128;
    out.push(byte);
  } while (n !== 0);
  return out;
}
function s32(n) {
  const out = [];
  for (; ; ) {
    const byte = n & 127;
    n >>= 7;
    if (n === 0 && (byte & 64) === 0 || n === -1 && (byte & 64) !== 0) {
      out.push(byte);
      return out;
    }
    out.push(byte | 128);
  }
}
var vec = (items) => [...u32(items.length), ...items.flat()];
var section = (id, body) => [id, ...u32(body.length), ...body];
var str = (s) => [...u32(s.length), ...Array.from(s, (c) => c.charCodeAt(0))];
var I32 = 127;
var V128 = 123;
var get = (i) => [32, ...u32(i)];
var set = (i) => [33, ...u32(i)];
var tee = (i) => [34, ...u32(i)];
var i32c = (v) => [65, ...s32(v)];
var ADD = [106];
var SHL = [116];
var GE_U = [79];
var block = (body) => [2, 64, ...body, 11];
var loop = (body) => [3, 64, ...body, 11];
var br = (depth) => [12, ...u32(depth)];
var brIf = (depth) => [13, ...u32(depth)];
var f32Load = (offset) => [42, 2, ...u32(offset)];
var f32Store = (offset) => [56, 2, ...u32(offset)];
var F32_ADD = [146];
var simd = (op, ...imm) => [253, ...u32(op), ...imm];
var V128_LOAD = simd(0, 4, 0);
var V128_ZERO = simd(12, ...new Array(16).fill(0));
var lane = (i) => simd(31, i);
var F32X4_ADD = simd(228);
var F32X4_MUL = simd(230);
var F32X4_SUB = simd(229);
var F32X4_DIV = simd(231);
var F32X4_MIN = simd(232);
var F32X4_MAX = simd(233);
var F32X4_NEG = simd(225);
var F32X4_NEAREST = simd(106);
var I32X4_TRUNC_SAT_F32X4_S = simd(248);
var I32X4_ADD = simd(174);
var I32X4_SHL = simd(171);
var V128_STORE = simd(11, 4, 0);
var F32X4_SPLAT = simd(19);
function splat(value, int = false) {
  const view = new DataView(new ArrayBuffer(16));
  for (let i = 0; i < 4; i++) {
    if (int) view.setInt32(i * 4, value, true);
    else view.setFloat32(i * 4, value, true);
  }
  return simd(12, ...new Uint8Array(view.buffer));
}
var [W, N, X, B, OUT, ROWS] = [0, 1, 2, 3, 4, 5];
var [R, J, ROW_BYTES, P0, P1, P2, P3, OB, BB] = [6, 7, 8, 9, 10, 11, 12, 13, 14];
var [A0, A1, A2, A3, XV] = [15, 16, 17, 18, 19];
var madd = (acc, p) => [
  ...get(acc),
  ...get(p),
  ...get(J),
  ...ADD,
  ...V128_LOAD,
  ...get(XV),
  ...F32X4_MUL,
  ...F32X4_ADD,
  ...set(acc)
];
var finish = (acc, k) => [
  ...get(OB),
  ...get(BB),
  ...f32Load(4 * k),
  ...get(acc),
  ...lane(0),
  ...get(acc),
  ...lane(1),
  ...F32_ADD,
  ...get(acc),
  ...lane(2),
  ...get(acc),
  ...lane(3),
  ...F32_ADD,
  ...F32_ADD,
  ...F32_ADD,
  ...f32Store(4 * k)
];
function affineBody() {
  const cols = loop([
    ...get(J),
    ...get(ROW_BYTES),
    ...GE_U,
    ...brIf(1),
    ...get(X),
    ...get(J),
    ...ADD,
    ...V128_LOAD,
    ...set(XV),
    ...madd(A0, P0),
    ...madd(A1, P1),
    ...madd(A2, P2),
    ...madd(A3, P3),
    ...get(J),
    ...i32c(16),
    ...ADD,
    ...set(J),
    ...br(0)
  ]);
  const rows = loop([
    ...get(R),
    ...get(ROWS),
    ...GE_U,
    ...brIf(1),
    ...get(P0),
    ...get(ROW_BYTES),
    ...ADD,
    ...tee(P1),
    ...get(ROW_BYTES),
    ...ADD,
    ...tee(P2),
    ...get(ROW_BYTES),
    ...ADD,
    ...set(P3),
    ...V128_ZERO,
    ...set(A0),
    ...V128_ZERO,
    ...set(A1),
    ...V128_ZERO,
    ...set(A2),
    ...V128_ZERO,
    ...set(A3),
    ...i32c(0),
    ...set(J),
    ...block(cols),
    ...get(OUT),
    ...get(R),
    ...i32c(2),
    ...SHL,
    ...ADD,
    ...set(OB),
    ...get(B),
    ...get(R),
    ...i32c(2),
    ...SHL,
    ...ADD,
    ...set(BB),
    ...finish(A0, 0),
    ...finish(A1, 1),
    ...finish(A2, 2),
    ...finish(A3, 3),
    ...get(R),
    ...i32c(4),
    ...ADD,
    ...set(R),
    ...get(P3),
    ...get(ROW_BYTES),
    ...ADD,
    ...set(P0),
    ...br(0)
  ]);
  const code = [
    ...get(N),
    ...i32c(2),
    ...SHL,
    ...set(ROW_BYTES),
    ...i32c(0),
    ...set(R),
    ...get(W),
    ...set(P0),
    ...block(rows),
    11
  ];
  const locals = vec([
    [9, I32],
    [5, V128]
  ]);
  const body = [...locals, ...code];
  return [...u32(body.length), ...body];
}
var [CZ, CC, CH, COUT, CHN] = [0, 1, 2, 3, 4];
var [K, HB, Z1, Z2, Z3] = [5, 6, 7, 8, 9];
var [VI, VF, VG, VO, VC, TX, TN, TR, TP, TS] = [10, 11, 12, 13, 14, 15, 16, 17, 18, 19];
var expTx = () => [
  ...get(TX),
  ...splat(1.4426950408889634),
  ...F32X4_MUL,
  ...F32X4_NEAREST,
  ...set(TN),
  ...get(TX),
  ...get(TN),
  ...splat(0.693359375),
  ...F32X4_MUL,
  ...F32X4_SUB,
  ...get(TN),
  ...splat(-21219444e-11),
  ...F32X4_MUL,
  ...F32X4_SUB,
  ...set(TR),
  ...splat(198756915e-12),
  ...get(TR),
  ...F32X4_MUL,
  ...splat(0.0013981999507),
  ...F32X4_ADD,
  ...get(TR),
  ...F32X4_MUL,
  ...splat(0.0083334519073),
  ...F32X4_ADD,
  ...get(TR),
  ...F32X4_MUL,
  ...splat(0.041665795894),
  ...F32X4_ADD,
  ...get(TR),
  ...F32X4_MUL,
  ...splat(0.16666665459),
  ...F32X4_ADD,
  ...get(TR),
  ...F32X4_MUL,
  ...splat(0.50000001201),
  ...F32X4_ADD,
  ...get(TR),
  ...get(TR),
  ...F32X4_MUL,
  ...F32X4_MUL,
  ...get(TR),
  ...F32X4_ADD,
  ...splat(1),
  ...F32X4_ADD,
  ...set(TP),
  // 2^n, built in the exponent bits.
  ...get(TN),
  ...I32X4_TRUNC_SAT_F32X4_S,
  ...splat(127, true),
  ...I32X4_ADD,
  ...i32c(23),
  ...I32X4_SHL,
  ...set(TS),
  ...get(TP),
  ...get(TS),
  ...F32X4_MUL
];
var sigmoidOf = (v) => [
  ...get(v),
  ...splat(-60),
  ...F32X4_MAX,
  ...splat(60),
  ...F32X4_MIN,
  ...F32X4_NEG,
  ...set(TX),
  ...splat(1),
  ...splat(1),
  ...expTx(),
  ...F32X4_ADD,
  ...F32X4_DIV,
  ...set(v)
];
var tanhOf = (v) => [
  ...get(v),
  ...splat(2),
  ...F32X4_MUL,
  ...splat(-87),
  ...F32X4_MAX,
  ...splat(87),
  ...F32X4_MIN,
  ...set(TX),
  ...splat(1),
  ...splat(2),
  ...expTx(),
  ...splat(1),
  ...F32X4_ADD,
  ...F32X4_DIV,
  ...F32X4_SUB,
  ...set(v)
];
var loadAt = (base) => [...get(base), ...get(K), ...ADD, ...V128_LOAD];
var storeAt = (base, v) => [
  ...get(base),
  ...get(K),
  ...ADD,
  ...get(v),
  ...V128_STORE
];
function cellBody() {
  const units = loop([
    ...get(K),
    ...get(HB),
    ...GE_U,
    ...brIf(1),
    ...loadAt(CZ),
    ...set(VI),
    ...loadAt(Z1),
    ...set(VF),
    ...loadAt(Z2),
    ...set(VG),
    ...loadAt(Z3),
    ...set(VO),
    ...sigmoidOf(VI),
    ...sigmoidOf(VF),
    ...tanhOf(VG),
    ...sigmoidOf(VO),
    // c = f·c + i·g
    ...get(VF),
    ...loadAt(CC),
    ...F32X4_MUL,
    ...get(VI),
    ...get(VG),
    ...F32X4_MUL,
    ...F32X4_ADD,
    ...set(VC),
    ...storeAt(CC, VC),
    // h = o·tanh(c)
    ...get(VC),
    ...set(VG),
    ...tanhOf(VG),
    ...get(VO),
    ...get(VG),
    ...F32X4_MUL,
    ...set(VG),
    ...storeAt(CH, VG),
    ...storeAt(COUT, VG),
    ...get(K),
    ...i32c(16),
    ...ADD,
    ...set(K),
    ...br(0)
  ]);
  const code = [
    ...get(CHN),
    ...i32c(2),
    ...SHL,
    ...tee(HB),
    ...get(CZ),
    ...ADD,
    ...tee(Z1),
    ...get(HB),
    ...ADD,
    ...tee(Z2),
    ...get(HB),
    ...ADD,
    ...set(Z3),
    ...i32c(0),
    ...set(K),
    ...block(units),
    11
  ];
  const locals = vec([
    [5, I32],
    [10, V128]
  ]);
  const body = [...locals, ...code];
  return [...u32(body.length), ...body];
}
var [YD, YDS, YS, YSS, YDV, YROWS, YN] = [0, 1, 2, 3, 4, 5, 6];
var [YR, YJ, YNB, YPD, YPS, YA] = [7, 8, 9, 10, 11, 12];
function axpyBody() {
  const cols = loop([
    ...get(YJ),
    ...get(YNB),
    ...GE_U,
    ...brIf(1),
    ...get(YPD),
    ...get(YJ),
    ...ADD,
    ...get(YPD),
    ...get(YJ),
    ...ADD,
    ...V128_LOAD,
    ...get(YPS),
    ...get(YJ),
    ...ADD,
    ...V128_LOAD,
    ...get(YA),
    ...F32X4_MUL,
    ...F32X4_ADD,
    ...V128_STORE,
    ...get(YJ),
    ...i32c(16),
    ...ADD,
    ...set(YJ),
    ...br(0)
  ]);
  const rows = loop([
    ...get(YR),
    ...get(YROWS),
    ...GE_U,
    ...brIf(1),
    ...get(YDV),
    ...get(YR),
    ...i32c(2),
    ...SHL,
    ...ADD,
    ...f32Load(0),
    ...F32X4_SPLAT,
    ...set(YA),
    ...i32c(0),
    ...set(YJ),
    ...block(cols),
    ...get(YPD),
    ...get(YDS),
    ...ADD,
    ...set(YPD),
    ...get(YPS),
    ...get(YSS),
    ...ADD,
    ...set(YPS),
    ...get(YR),
    ...i32c(1),
    ...ADD,
    ...set(YR),
    ...br(0)
  ]);
  const code = [
    ...get(YN),
    ...i32c(2),
    ...SHL,
    ...set(YNB),
    ...i32c(0),
    ...set(YR),
    ...get(YD),
    ...set(YPD),
    ...get(YS),
    ...set(YPS),
    ...block(rows),
    11
  ];
  const locals = vec([
    [5, I32],
    [1, V128]
  ]);
  const body = [...locals, ...code];
  return [...u32(body.length), ...body];
}
function kernelModule() {
  const i32s = (n) => new Array(n).fill([I32]);
  const type = vec([
    [96, ...vec(i32s(6)), ...vec([])],
    [96, ...vec(i32s(5)), ...vec([])],
    [96, ...vec(i32s(7)), ...vec([])]
  ]);
  const imports = vec([[...str("env"), ...str("memory"), 2, 0, ...u32(1)]]);
  const functions = vec([u32(0), u32(1), u32(2)]);
  const exports = vec([
    [...str("affine"), 0, ...u32(0)],
    [...str("cell"), 0, ...u32(1)],
    [...str("axpy"), 0, ...u32(2)]
  ]);
  const code = vec([affineBody(), cellBody(), axpyBody()]);
  return new Uint8Array([
    0,
    97,
    115,
    109,
    1,
    0,
    0,
    0,
    ...section(1, type),
    ...section(2, imports),
    ...section(3, functions),
    ...section(7, exports),
    ...section(10, code)
  ]);
}
function simdKernel(bytes) {
  try {
    const wasm = kernelModule();
    if (typeof WebAssembly !== "object" || !WebAssembly.validate(wasm)) return null;
    const memory = new WebAssembly.Memory({ initial: Math.max(1, Math.ceil(bytes / 65536)) });
    const instance = new WebAssembly.Instance(new WebAssembly.Module(wasm), { env: { memory } });
    const affine = instance.exports.affine;
    const cell = instance.exports.cell;
    const axpy = instance.exports.axpy;
    return { memory, affine, cell, axpy };
  } catch {
    return null;
  }
}

// blstm.ts
function sigmoid(x) {
  return 1 / (1 + Math.exp(x < -60 ? 60 : x > 60 ? -60 : -x));
}
function project(x, frames, d, pre) {
  const n = d.inputs;
  const G = d.bias.length;
  const w = d.wih;
  const scale = d.wihScale;
  const bias = d.bias;
  for (let t = 0; t < frames; t++) {
    const xo = t * n;
    const po = t * G;
    let r = 0;
    for (; r + 3 < G; r += 4) {
      const w0 = r * n;
      const w1 = w0 + n;
      const w2 = w1 + n;
      const w3 = w2 + n;
      let a0 = 0;
      let a1 = 0;
      let a2 = 0;
      let a3 = 0;
      for (let j = 0; j < n; j++) {
        const v = x[xo + j];
        a0 += w[w0 + j] * v;
        a1 += w[w1 + j] * v;
        a2 += w[w2 + j] * v;
        a3 += w[w3 + j] * v;
      }
      pre[po + r] = bias[r] + scale[r] * a0;
      pre[po + r + 1] = bias[r + 1] + scale[r + 1] * a1;
      pre[po + r + 2] = bias[r + 2] + scale[r + 2] * a2;
      pre[po + r + 3] = bias[r + 3] + scale[r + 3] * a3;
    }
    for (; r < G; r++) {
      let a = 0;
      for (let j = 0; j < n; j++) a += w[r * n + j] * x[xo + j];
      pre[po + r] = bias[r] + scale[r] * a;
    }
  }
}
function recur(pre, frames, d, reverse, out, offset, stride) {
  const G = d.bias.length;
  const H = G >> 2;
  const w = d.whh;
  const scale = d.whhScale;
  const h = new Float64Array(H);
  const c = new Float64Array(H);
  const z = new Float64Array(G);
  for (let step = 0; step < frames; step++) {
    const t = reverse ? frames - 1 - step : step;
    const po = t * G;
    let r = 0;
    for (; r + 3 < G; r += 4) {
      const w0 = r * H;
      const w1 = w0 + H;
      const w2 = w1 + H;
      const w3 = w2 + H;
      let a0 = 0;
      let a1 = 0;
      let a2 = 0;
      let a3 = 0;
      for (let j = 0; j < H; j++) {
        const v = h[j];
        a0 += w[w0 + j] * v;
        a1 += w[w1 + j] * v;
        a2 += w[w2 + j] * v;
        a3 += w[w3 + j] * v;
      }
      z[r] = pre[po + r] + scale[r] * a0;
      z[r + 1] = pre[po + r + 1] + scale[r + 1] * a1;
      z[r + 2] = pre[po + r + 2] + scale[r + 2] * a2;
      z[r + 3] = pre[po + r + 3] + scale[r + 3] * a3;
    }
    for (; r < G; r++) {
      let a = 0;
      for (let j = 0; j < H; j++) a += w[r * H + j] * h[j];
      z[r] = pre[po + r] + scale[r] * a;
    }
    const oo = t * stride + offset;
    for (let u = 0; u < H; u++) {
      const cu = sigmoid(z[H + u]) * c[u] + sigmoid(z[u]) * Math.tanh(z[2 * H + u]);
      c[u] = cu;
      const hu = sigmoid(z[3 * H + u]) * Math.tanh(cu);
      h[u] = hu;
      out[oo + u] = hu;
    }
  }
}
function standardize(net, features, frames) {
  const n = net.inputs;
  const x = new Float32Array(frames * n);
  const { mean, std } = net;
  for (let t = 0; t < frames; t++) {
    for (let j = 0; j < n; j++) {
      const v = features[t * n + j];
      x[t * n + j] = mean && std ? Math.fround(v - mean[j]) / std[j] : v;
    }
  }
  return x;
}
function classify(net, x, frames) {
  const n = 2 * net.hidden;
  const C = net.classes;
  const w = net.out;
  const out = new Float32Array(frames * C);
  const logits = new Float64Array(C);
  for (let t = 0; t < frames; t++) {
    const xo = t * n;
    let max = -Infinity;
    for (let k = 0; k < C; k++) {
      const wo = k * n;
      let a = 0;
      for (let j = 0; j < n; j++) a += w[wo + j] * x[xo + j];
      const l = net.outBias[k] + net.outScale[k] * a;
      logits[k] = l;
      if (l > max) max = l;
    }
    let sum = 0;
    for (let k = 0; k < C; k++) sum += Math.exp(logits[k] - max);
    const lse2 = Math.log(sum);
    for (let k = 0; k < C; k++) out[t * C + k] = logits[k] - max - lse2;
  }
  return out;
}
function logSoftmax(logits, at, frames, C, Cp) {
  const out = new Float32Array(frames * C);
  for (let t = 0; t < frames; t++) {
    const o = at + t * Cp;
    let max = -Infinity;
    for (let k = 0; k < C; k++) if (logits[o + k] > max) max = logits[o + k];
    let sum = 0;
    for (let k = 0; k < C; k++) sum += Math.exp(logits[o + k] - max);
    const lse2 = Math.log(sum);
    for (let k = 0; k < C; k++) out[t * C + k] = logits[o + k] - max - lse2;
  }
  return out;
}
function forwardJs(net, features, frames) {
  const H = net.hidden;
  let x = standardize(net, features, frames);
  const pre = new Float32Array(frames * 4 * H);
  for (const [fwd, bwd] of net.layers) {
    const y = new Float32Array(frames * 2 * H);
    project(x, frames, fwd, pre);
    recur(pre, frames, fwd, false, y, 0, 2 * H);
    project(x, frames, bwd, pre);
    recur(pre, frames, bwd, true, y, H, 2 * H);
    x = y;
  }
  return classify(net, x, frames);
}
var simdNets = /* @__PURE__ */ new WeakMap();
function dequantise(f, at, q, scale, n) {
  for (let r = 0; r < scale.length; r++) {
    const s = scale[r];
    for (let j = 0; j < n; j++) f[at + r * n + j] = q[r * n + j] * s;
  }
}
function simdNet(net) {
  if (simdNets.has(net)) return simdNets.get(net) ?? null;
  const H = net.hidden;
  const G = 4 * H;
  const Cp = Math.ceil(net.classes / 4) * 4;
  let made = null;
  if (H % 4 === 0 && net.inputs % 4 === 0) {
    let floats = 0;
    for (const dirs of net.layers) for (const d of dirs) floats += G * d.inputs + G * H + G;
    floats += Cp * 2 * H + Cp;
    const kernel = simdKernel(floats * 4 + (1 << 20));
    if (kernel) {
      const f = new Float32Array(kernel.memory.buffer);
      let at = 0;
      const layers = net.layers.map(
        (dirs) => dirs.map((d) => {
          const wih = at;
          dequantise(f, at, d.wih, d.wihScale, d.inputs);
          at += G * d.inputs;
          const whh = at;
          dequantise(f, at, d.whh, d.whhScale, H);
          at += G * H;
          const bias = at;
          f.set(d.bias, at);
          at += G;
          return { wih: wih * 4, whh: whh * 4, bias: bias * 4, inputs: d.inputs };
        })
      );
      const out = at;
      dequantise(f, at, net.out, net.outScale, 2 * H);
      at += Cp * 2 * H;
      const outBias = at;
      f.set(net.outBias, at);
      at += Cp;
      made = {
        kernel,
        layers,
        out: out * 4,
        outBias: outBias * 4,
        classesPadded: Cp,
        free: at * 4
      };
    }
  }
  simdNets.set(net, made);
  return made;
}
function simdAvailable(net) {
  return simdNet(net) !== null;
}
function forwardSimd(s, net, features, frames) {
  const H = net.hidden;
  const G = 4 * H;
  const n0 = net.inputs;
  const Cp = s.classesPadded;
  const width = Math.max(n0, 2 * H);
  const A = s.free / 4;
  const B2 = A + frames * width;
  const PRE = B2 + frames * width;
  const Z = PRE + frames * G;
  const HS = Z + G;
  const CS = HS + H;
  const LOG = CS + H;
  const need = (LOG + frames * Cp) * 4;
  const memory = s.kernel.memory;
  if (need > memory.buffer.byteLength) {
    memory.grow(Math.ceil((need - memory.buffer.byteLength) / 65536));
  }
  const f = new Float32Array(memory.buffer);
  f.set(standardize(net, features, frames), A);
  const { affine, cell } = s.kernel;
  let input = A;
  let output = B2;
  for (let k = 0; k < s.layers.length; k++) {
    const n = s.layers[k][0].inputs;
    for (let dir = 0; dir < 2; dir++) {
      const L = s.layers[k][dir];
      for (let t = 0; t < frames; t++)
        affine(L.wih, n, (input + t * n) * 4, L.bias, (PRE + t * G) * 4, G);
      f.fill(0, HS, HS + 2 * H);
      const offset = dir * H;
      for (let step = 0; step < frames; step++) {
        const t = dir === 0 ? step : frames - 1 - step;
        affine(L.whh, H, HS * 4, (PRE + t * G) * 4, Z * 4, G);
        cell(Z * 4, CS * 4, HS * 4, (output + t * 2 * H + offset) * 4, H);
      }
    }
    const swap = input;
    input = output;
    output = swap;
  }
  for (let t = 0; t < frames; t++) {
    affine(s.out, 2 * H, (input + t * 2 * H) * 4, s.outBias, (LOG + t * Cp) * 4, Cp);
  }
  return logSoftmax(f, LOG, frames, net.classes, Cp);
}
function forward(net, features, frames, options = {}) {
  if (frames === 0) return new Float32Array(0);
  const s = options.simd === false ? null : simdNet(net);
  return s ? forwardSimd(s, net, features, frames) : forwardJs(net, features, frames);
}

// ctc.ts
function greedyDecode(logp, frames, alphabet) {
  const C = alphabet.length + 1;
  let text = "";
  const spans = [];
  let prev = 0;
  let confSum = 0;
  let confN = 0;
  for (let t = 0; t < frames; t++) {
    const o = t * C;
    let best = 0;
    for (let k = 1; k < C; k++) if (logp[o + k] > logp[o + best]) best = k;
    if (best !== 0 && best !== prev) {
      text += alphabet[best - 1];
      spans.push([t, t]);
    } else if (best !== 0 && best === prev && spans.length > 0) {
      spans[spans.length - 1][1] = t;
    }
    if (best !== 0) {
      confSum += Math.exp(logp[o + best]);
      confN++;
    }
    prev = best;
  }
  return { text, spans, confidence: confN ? confSum / confN : 0 };
}
var DEFAULT_BEAM = { alpha: 0.3, beta: 0, beam: 16, topk: 8, prune: -9 };
var NEG = -1e30;
function lse(a, b) {
  if (a < b) {
    const s = a;
    a = b;
    b = s;
  }
  if (b <= NEG) return a;
  return a + Math.log1p(Math.exp(b - a));
}
function topClasses(logp, o, C, n) {
  const out = [];
  for (let k = 0; k < C; k++) {
    const v = logp[o + k];
    let i = out.length;
    while (i > 0 && logp[o + out[i - 1]] <= v) i--;
    if (i < n) {
      out.splice(i, 0, k);
      if (out.length > n) out.pop();
    }
  }
  return out;
}
function beamDecode(logp, frames, alphabet, lm, options = {}) {
  const { alpha, beta, beam, topk, prune } = { ...DEFAULT_BEAM, ...options };
  const C = alphabet.length + 1;
  const codes = lm ? alphabet.map((c) => lm.codeOf(c)) : [];
  const contextOf = (p) => p.context ?? (p.context = lm.context(p.text));
  let beams = [{ text: "", pb: 0, pnb: NEG, context: null }];
  for (let t = 0; t < frames; t++) {
    const o = t * C;
    const cand = topClasses(logp, o, C, topk + 1).filter((k) => k !== 0 && logp[o + k] > prune).slice(0, topk);
    const next = /* @__PURE__ */ new Map();
    const entry = (text) => {
      let e = next.get(text);
      if (!e) {
        e = { text, pb: NEG, pnb: NEG, context: null };
        next.set(text, e);
      }
      return e;
    };
    const blank = logp[o];
    for (const b of beams) {
      const ptot = lse(b.pb, b.pnb);
      const e = entry(b.text);
      e.context ?? (e.context = b.context);
      e.pb = lse(e.pb, ptot + blank);
      const last = b.text.length ? b.text[b.text.length - 1] : null;
      for (const k of cand) {
        const ch = alphabet[k - 1];
        const p = logp[o + k];
        const bonus = lm ? alpha * Math.log(lm.probIn(contextOf(b), codes[k - 1])) + beta : 0;
        if (ch === last) {
          e.pnb = lse(e.pnb, b.pnb + p);
          const n = entry(b.text + ch);
          n.pnb = lse(n.pnb, b.pb + p + bonus);
        } else {
          const n = entry(b.text + ch);
          n.pnb = lse(n.pnb, ptot + p + bonus);
        }
      }
    }
    const scored = [...next.values()].map((e) => ({ e, s: lse(e.pb, e.pnb) }));
    scored.sort((a, b) => b.s - a.s);
    beams = scored.slice(0, beam).map((x) => x.e);
  }
  let best = beams[0];
  let bestScore = -Infinity;
  const end = lm ? lm.codeOf("\n") : -1;
  for (const b of beams) {
    let score = lse(b.pb, b.pnb);
    if (lm) score += alpha * Math.log(lm.probIn(contextOf(b), end));
    if (score > bestScore) {
      best = b;
      bestScore = score;
    }
  }
  return best.text;
}

// features.ts
var POINTS_PER_UNIT_LENGTH = 20;
var HEIGHTS_PER_SECOND = 5.3;
var CORE_UNITS = 0.4;
var MIN_LINE_HEIGHT = 1;
var MAX_LINE_FRAMES = 6e3;
var LineTooLongError = class extends Error {
  constructor(frames) {
    super(`a line of ${frames} frames is past the ${MAX_LINE_FRAMES} the recogniser reads`);
    this.frames = frames;
  }
};
function minX(s) {
  let m = Infinity;
  for (let i = 0; i < s.pts.length; i += 3) if (s.pts[i] < m) m = s.pts[i];
  return m;
}
function writingOrder(strokes) {
  if (strokes.every((s) => s.t0 != null)) {
    return [...strokes].sort((a, b) => a.t0 - b.t0);
  }
  return [...strokes].sort((a, b) => minX(a) - minX(b));
}
function timeStrokes(xy, t0s, speed) {
  const timed = [];
  let tEnd = 0;
  let prevX = 0;
  let prevY = 0;
  for (let i = 0; i < xy.length; i++) {
    const { x, y } = xy[i];
    let tStart;
    if (i === 0) {
      tStart = 0;
    } else {
      const a = t0s[i - 1];
      const b = t0s[i];
      if (a != null && b != null && b > a) {
        tStart = Math.max(tEnd + 0.01, timed[i - 1].t[0] + (b - a) / 1e3);
      } else {
        const dx = x[0] - prevX;
        const dy = y[0] - prevY;
        tStart = tEnd + Math.sqrt(dx * dx + dy * dy) / speed + 0.15;
      }
    }
    const t = new Float64Array(x.length);
    let cum = 0;
    t[0] = tStart;
    for (let k = 1; k < x.length; k++) {
      const dx = x[k] - x[k - 1];
      const dy = y[k] - y[k - 1];
      cum += Math.sqrt(dx * dx + dy * dy);
      t[k] = tStart + cum / speed;
    }
    timed.push({ x, y, t });
    tEnd = t[t.length - 1];
    prevX = x[x.length - 1];
    prevY = y[y.length - 1];
  }
  return timed;
}
function localMinima(strokes) {
  const xs = [];
  const ys = [];
  for (const s of strokes) {
    const n = s.y.length;
    if (n < 3) {
      let k = 0;
      for (let i = 1; i < n; i++) if (s.y[i] < s.y[k]) k = i;
      xs.push(s.x[k]);
      ys.push(s.y[k]);
      continue;
    }
    for (let i = 1; i < n - 1; i++) {
      if (s.y[i] <= s.y[i - 1] && s.y[i] <= s.y[i + 1]) {
        xs.push(s.x[i]);
        ys.push(s.y[i]);
      }
    }
  }
  return { x: xs, y: ys };
}
function ptp(a) {
  let lo = Infinity;
  let hi = -Infinity;
  for (let i = 0; i < a.length; i++) {
    if (a[i] < lo) lo = a[i];
    if (a[i] > hi) hi = a[i];
  }
  return hi - lo;
}
function robustLine(xs, ys) {
  const n = xs.length;
  if (n < 2 || ptp(xs) <= 0) return [0, n ? median(ys) : 0];
  let keep = new Array(n).fill(true);
  let a = 0;
  let b = median(ys);
  for (let iter = 0; iter < 3; iter++) {
    const kx = [];
    const ky = [];
    for (let i = 0; i < n; i++) {
      if (keep[i]) {
        kx.push(xs[i]);
        ky.push(ys[i]);
      }
    }
    if (kx.length < 2 || ptp(kx) <= 0) break;
    [a, b] = fitLine(kx, ky);
    const r = xs.map((x, i) => ys[i] - (a * x + b));
    const kept = r.filter((_, i) => keep[i]);
    const mid = median(kept);
    const mad = median(kept.map((v) => Math.abs(v - mid))) + 1e-9;
    keep = r.map((v) => Math.abs(v - mid) <= 1.5 * 1.4826 * mad);
  }
  return [a, b];
}
function normalizeCore(strokes) {
  let count = 0;
  for (const s of strokes) count += s.x.length;
  const allX = new Float64Array(count);
  const allY = new Float64Array(count);
  let o = 0;
  for (const s of strokes) {
    allX.set(s.x, o);
    allY.set(s.y, o);
    o += s.x.length;
  }
  const full = Math.max(ptp(allY), MIN_LINE_HEIGHT);
  const cx = npMean(allX);
  const cy = npMean(allY);
  const centred = strokes.map((s) => ({
    x: s.x.map((v) => v - cx),
    y: s.y.map((v) => v - cy),
    t: s.t
  }));
  const mins = localMinima(centred);
  let base;
  if (mins.x.length >= 2) {
    base = robustLine(mins.x, mins.y)[1];
  } else {
    base = Infinity;
    for (const s of centred) for (const v of s.y) base = Math.min(base, v);
  }
  const step = full / 60;
  const ys = [];
  for (const s of centred) {
    const n = s.x.length;
    const arc = new Float64Array(n);
    for (let k = 1; k < n; k++) {
      const dx = s.x[k] - s.x[k - 1];
      const dy = s.y[k] - s.y[k - 1];
      arc[k] = arc[k - 1] + Math.sqrt(dx * dx + dy * dy);
    }
    const length = arc[n - 1];
    if (length > 0) {
      const m = Math.max(Math.trunc(length / step), 1);
      for (const v of interp(linspace(0, length, m + 1), arc, s.y)) ys.push(v);
    } else {
      ys.push(s.y[0]);
    }
  }
  const sortedYs = sorted(ys);
  let core = (percentileSorted(sortedYs, 80) - percentileSorted(sortedYs, 20)) / 0.6;
  if (!(0.2 * full <= core && core <= 0.9 * full)) core = 0.45 * full;
  const scale = CORE_UNITS / Math.max(core, 1e-6);
  let x0 = Infinity;
  for (const s of centred) for (const v of s.x) x0 = Math.min(x0, v);
  const out = centred.map((s) => ({
    x: s.x.map((v) => (v - x0) * scale),
    y: s.y.map((v) => (v - base) * scale),
    t: s.t
  }));
  return { strokes: out, info: { full, base, core, scale } };
}
function frameFeatures(strokes) {
  const counts = strokes.map((s) => {
    const n0 = s.x.length;
    if (n0 === 1) return 1;
    const seg = new Float64Array(n0 - 1);
    for (let k = 0; k < n0 - 1; k++) {
      const dx = s.x[k + 1] - s.x[k];
      const dy = s.y[k + 1] - s.y[k];
      seg[k] = Math.sqrt(dx * dx + dy * dy);
    }
    return Math.max(Math.ceil(npSum(seg) * POINTS_PER_UNIT_LENGTH), 2);
  });
  const frames = counts.reduce((sum, n) => sum + n, 0);
  if (!(frames <= MAX_LINE_FRAMES)) throw new LineTooLongError(frames);
  const xs = [];
  const ys = [];
  const ts = [];
  let total = 0;
  for (const [i, s] of strokes.entries()) {
    if (s.x.length === 1) {
      xs.push(s.x);
      ys.push(s.y);
      ts.push(s.t);
      total += 1;
      continue;
    }
    const n = counts[i];
    let tmin = Infinity;
    let tmax = -Infinity;
    for (const v of s.t) {
      if (v < tmin) tmin = v;
      if (v > tmax) tmax = v;
    }
    const span = Math.max(1e-9, tmax - tmin);
    const tn = s.t.map((v) => (v - tmin) / span);
    const grid = linspace(0, 1, n);
    xs.push(interp(grid, tn, s.x));
    ys.push(interp(grid, tn, s.y));
    ts.push(interp(grid, tn, s.t));
    total += n;
  }
  const features = new Float32Array(total * 4);
  const frameStroke = new Int32Array(total);
  let f = 0;
  let px = 0;
  let py = 0;
  let pt = 0;
  for (let k = 0; k < xs.length; k++) {
    const x = xs[k];
    const y = ys[k];
    const t = ts[k];
    for (let i = 0; i < x.length; i++, f++) {
      if (f > 0) {
        features[f * 4] = x[i] - px;
        features[f * 4 + 1] = y[i] - py;
        features[f * 4 + 2] = t[i] - pt;
        features[f * 4 + 3] = i === 0 ? 1 : 0;
      } else {
        features[3] = 1;
      }
      frameStroke[f] = k;
      px = x[i];
      py = y[i];
      pt = t[i];
    }
  }
  return { features, frameStroke };
}
function lineFeatures(input, heightsPerSecond = HEIGHTS_PER_SECOND) {
  const strokes = writingOrder(input.filter((s) => s.pts.length >= 3));
  if (strokes.length === 0) throw new Error("a line needs at least one stroke with points");
  const xy = strokes.map((s) => {
    const n = Math.floor(s.pts.length / 3);
    const x = new Float64Array(n);
    const y = new Float64Array(n);
    for (let i = 0; i < n; i++) {
      x[i] = s.pts[i * 3];
      y[i] = -s.pts[i * 3 + 1];
    }
    return { x, y };
  });
  let lo = Infinity;
  let hi = -Infinity;
  for (const { y } of xy) {
    for (const v of y) {
      if (v < lo) lo = v;
      if (v > hi) hi = v;
    }
  }
  const speed = heightsPerSecond * Math.max(hi - lo, 1);
  const timed = timeStrokes(
    xy,
    strokes.map((s) => s.t0),
    speed
  );
  const { strokes: norm, info } = normalizeCore(timed);
  const { features, frameStroke } = frameFeatures(norm);
  return { features, frames: frameStroke.length, frameStroke, strokes, norm: info };
}

// lines.ts
function boxOf(pts) {
  let x0 = Infinity;
  let y0 = Infinity;
  let x1 = -Infinity;
  let y1 = -Infinity;
  for (let i = 0; i + 1 < pts.length; i += 3) {
    const x = pts[i];
    const y = pts[i + 1];
    if (x < x0) x0 = x;
    if (x > x1) x1 = x;
    if (y < y0) y0 = y;
    if (y > y1) y1 = y;
  }
  return [x0, y0, x1, y1];
}
function union(boxes) {
  let x0 = Infinity;
  let y0 = Infinity;
  let x1 = -Infinity;
  let y1 = -Infinity;
  for (const b of boxes) {
    x0 = Math.min(x0, b[0]);
    y0 = Math.min(y0, b[1]);
    x1 = Math.max(x1, b[2]);
    y1 = Math.max(y1, b[3]);
  }
  return [x0, y0, x1, y1];
}
function xHeightOf(items) {
  const hs = items.map((it) => it.box[3] - it.box[1]).filter((h) => h > 1.5);
  return hs.length ? median(hs) : 10;
}
function isDrawing(box, xh) {
  const w = box[2] - box[0];
  const h = box[3] - box[1];
  return w > 8 * xh && h < 0.8 * xh || h > 4.5 * xh || w > 4.5 * xh && h > 3 * xh;
}
var centreY = (b) => (b[1] + b[3]) / 2;
var centreX = (b) => (b[0] + b[2]) / 2;
function localCy(line, x, xh) {
  let near = line.filter((it) => Math.abs(centreX(it.box) - x) < 6 * xh).map((it) => centreY(it.box));
  if (near.length === 0) near = line.slice(-5).map((it) => centreY(it.box));
  return median(near);
}
function bandsByTime(items, xh) {
  const lines = [];
  const left = [];
  const right = [];
  const join = (k, it) => {
    lines[k].push(it);
    left[k] = Math.min(left[k], it.box[0]);
    right[k] = Math.max(right[k], it.box[2]);
  };
  let cur = -1;
  const byTime = [...items].sort((a, b) => a.s.t0 - b.s.t0);
  for (const it of byTime) {
    const [x0, , x1] = it.box;
    const xc = (x0 + x1) / 2;
    const cy = centreY(it.box);
    if (cur >= 0 && x0 > right[cur] - 3 * xh && Math.abs(cy - localCy(lines[cur], xc, xh)) < 1 * xh) {
      join(cur, it);
      continue;
    }
    let best = -1;
    let bestD = 0.8 * xh;
    for (let k = 0; k < lines.length; k++) {
      if (left[k] - 2 * xh <= xc && xc <= right[k] + 6 * xh) {
        const d = Math.abs(cy - localCy(lines[k], xc, xh));
        if (d < bestD) {
          best = k;
          bestD = d;
        }
      }
    }
    if (best >= 0) {
      join(best, it);
      cur = best;
    } else {
      lines.push([it]);
      left.push(x0);
      right.push(x1);
      cur = lines.length - 1;
    }
  }
  return mergeRows(lines, left, right, xh);
}
function mergeRows(input, left, right, xh) {
  const lines = input.map((l) => [...l]);
  const x0s = [...left];
  const x1s = [...right];
  const n = lines.length;
  const alive = new Array(n).fill(true);
  const bestDy = new Float64Array(n).fill(Infinity);
  const bestJ = new Int32Array(n).fill(-1);
  const distance = (i, j) => {
    const ax0 = x0s[i];
    const ax1 = x1s[i];
    const bx0 = x0s[j];
    const bx1 = x1s[j];
    const gap = Math.max(bx0 - ax1, ax0 - bx1);
    if (gap > 6 * xh) return Infinity;
    const ax = Math.min(Math.max(bx0, ax0), ax1);
    const bx = Math.min(Math.max(ax0, bx0), bx1);
    const b = lines[j];
    const dy = Math.abs(localCy(lines[i], ax, xh) - localCy(b, bx, xh));
    const small = b.length <= 3 && bx1 - bx0 < 3 * xh;
    const limit = (small ? 1.6 : 1.2) * xh;
    return dy < limit ? dy : Infinity;
  };
  const findBest = (i) => {
    bestDy[i] = Infinity;
    bestJ[i] = -1;
    for (let j = 0; j < n; j++) {
      if (j === i || !alive[j]) continue;
      const d = distance(i, j);
      if (d < bestDy[i]) {
        bestDy[i] = d;
        bestJ[i] = j;
      }
    }
  };
  for (let i = 0; i < n; i++) findBest(i);
  for (; ; ) {
    let i = -1;
    for (let k = 0; k < n; k++) if (alive[k] && bestDy[k] < (i < 0 ? Infinity : bestDy[i])) i = k;
    if (i < 0) return lines.filter((_, k) => alive[k]);
    const j = bestJ[i];
    lines[i].push(...lines[j]);
    x0s[i] = Math.min(x0s[i], x0s[j]);
    x1s[i] = Math.max(x1s[i], x1s[j]);
    alive[j] = false;
    findBest(i);
    for (let k = 0; k < n; k++) {
      if (k === i || !alive[k]) continue;
      if (bestJ[k] === j) {
        findBest(k);
        continue;
      }
      const d = distance(k, i);
      if (bestJ[k] === i) {
        if (d <= bestDy[k]) bestDy[k] = d;
        else findBest(k);
      } else if (d < bestDy[k] || d === bestDy[k] && d < Infinity && i < bestJ[k]) {
        bestDy[k] = d;
        bestJ[k] = i;
      }
    }
  }
}
function bandsByHeight(items, xh, lineOverlap) {
  const bands = [];
  const bandBox = [];
  for (const it of [...items].sort((a, b) => centreY(a.box) - centreY(b.box))) {
    const [x0, y0, x1, y1] = it.box;
    let best = -1;
    let bestOv = 0;
    bandBox.forEach((bb, i) => {
      const centre = (bb[1] + bb[3]) / 2;
      const core0 = centre - xh * 0.9;
      const core1 = centre + xh * 0.9;
      const ov = Math.min(y1, core1) - Math.max(y0, core0);
      const rel = ov / Math.max(1e-6, Math.min(y1 - y0, core1 - core0) || 1);
      if (rel > bestOv) {
        best = i;
        bestOv = rel;
      }
    });
    if (best >= 0 && bestOv >= lineOverlap) {
      bands[best].push(it);
      const b = bandBox[best];
      bandBox[best] = [
        Math.min(b[0], x0),
        Math.min(b[1], y0),
        Math.max(b[2], x1),
        Math.max(b[3], y1)
      ];
    } else {
      bands.push([it]);
      bandBox.push([x0, y0, x1, y1]);
    }
  }
  return bands;
}
function wordsInBands(bands, wordGap) {
  const startCy = (band) => {
    let first = band[0];
    for (const it of band) if (it.box[0] < first.box[0]) first = it;
    return centreY(first.box);
  };
  const lines = [];
  for (const band of [...bands].sort((a, b) => startCy(a) - startCy(b))) {
    const lxh = xHeightOf(band);
    const groups = [];
    let right = -Infinity;
    for (const it of [...band].sort((a, b) => a.box[0] - b.box[0])) {
      if (groups.length && it.box[0] - right <= wordGap * lxh) groups[groups.length - 1].push(it);
      else groups.push([it]);
      right = Math.max(...groups[groups.length - 1].map((g) => g.box[2]));
    }
    const words = groups.map((g) => ({
      strokes: g.map((x) => x.s),
      box: union(g.map((x) => x.box))
    }));
    lines.push({ words, box: union(words.map((w) => w.box)), xHeight: lxh });
  }
  return lines;
}
function gapsOf(lines) {
  const out = [];
  for (const line of lines) {
    const boxes = line.words.flatMap((w) => w.strokes.map((s) => boxOf(s.pts)));
    boxes.sort((a, b) => a[0] - b[0]);
    let right = -Infinity;
    for (const b of boxes) {
      if (right > -Infinity) out.push((b[0] - right) / line.xHeight);
      right = Math.max(right, b[2]);
    }
  }
  return out;
}
function autoWordGap(rawGaps, lo = 0.6, hi = 2) {
  const g = rawGaps.filter((x) => x > 0.05).map((x) => Math.log(Math.min(Math.max(x, 0.05), 20)));
  if (g.length < 8) return 1;
  const s = sorted(g);
  let a = percentileSorted(s, 25);
  let b = percentileSorted(s, 85);
  for (let i = 0; i < 30; i++) {
    const cut = (a + b) / 2;
    const left = g.filter((v) => v <= cut);
    const right = g.filter((v) => v > cut);
    if (left.length === 0 || right.length === 0) break;
    a = npMean(left);
    b = npMean(right);
  }
  return Math.min(Math.max(Math.exp((a + b) / 2), lo), hi);
}
function writingStrokes(strokes) {
  return strokes.filter((s) => s.tool === "pen" && s.shape == null && s.pts.length >= 3).map((s) => ({ s, box: boxOf(s.pts) }));
}
function bandsOf(strokes, lineOverlap) {
  const all = writingStrokes(strokes);
  if (all.length === 0) return [];
  const xh = xHeightOf(all);
  const items = all.filter((it) => !isDrawing(it.box, xh));
  if (items.length === 0) return [];
  return items.every((it) => it.s.t0 != null) ? bandsByTime(items, xh) : bandsByHeight(items, xh, lineOverlap);
}
function segmentPage(strokes, options = {}) {
  const bands = bandsOf(strokes, options.lineOverlap ?? 0.35);
  const wordGap = options.wordGap ?? autoWordGap(gapsOf(wordsInBands(bands, 1e9)));
  return { lines: wordsInBands(bands, wordGap), wordGap };
}
function lineStrokes(line) {
  return line.words.flatMap((w) => w.strokes);
}

// recognizer.ts
function readLine(bundle, strokes, options = {}) {
  const now = options.now ?? (() => 0);
  const t0 = now();
  let line;
  try {
    const points = lineFeatures(strokes, bundle.meta.features.heightsPerSecond);
    line = networkInput(bundle.meta.input, bundle.net.inputs, points.features, points.frames);
  } catch (error) {
    if (!(error instanceof LineTooLongError)) throw error;
    const timings = { features: now() - t0, network: 0, greedy: 0, beam: 0 };
    return { greedy: "", text: "", confidence: 0, frames: 0, timings };
  }
  const { features, frames } = line;
  const t1 = now();
  const logp = forward(bundle.net, features, frames);
  const t2 = now();
  options.logp?.(0, logp, frames);
  const alphabet = bundle.meta.alphabet;
  const greedy = greedyDecode(logp, frames, alphabet);
  const t3 = now();
  const lm = options.useLm === false ? null : bundle.lm;
  const text = lm ? beamDecode(logp, frames, alphabet, lm, { ...bundle.meta.decoder, ...options.beam }) : greedy.text;
  const t4 = now();
  return {
    greedy: greedy.text,
    text,
    confidence: greedy.confidence,
    frames,
    timings: { features: t1 - t0, network: t2 - t1, greedy: t3 - t2, beam: t4 - t3 }
  };
}
function readPage(bundle, strokes, options = {}) {
  const now = options.now ?? (() => 0);
  const t0 = now();
  const { lines, wordGap } = segmentPage(strokes);
  const segment = now() - t0;
  return {
    segment,
    wordGap,
    lines: lines.map((line, index) => {
      const ink = lineStrokes(line);
      const keep = options.logp;
      return {
        ...readLine(bundle, ink, {
          ...options,
          logp: keep && ((_, logp, frames) => keep(index, logp, frames))
        }),
        strokeIds: ink.map((s) => s.id),
        words: line.words.map((word) => word.strokes.map((s) => s.id)),
        box: line.box
      };
    })
  };
}
export {
  HwrFormatError,
  lineStrokes,
  parseBundle,
  readLine,
  readPage,
  segmentPage,
  simdAvailable
};
