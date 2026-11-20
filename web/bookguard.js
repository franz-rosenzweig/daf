// Books are other people's files: nothing in one runs as Daf. foliate (vendor/foliate-js) shows each
// chapter in a frame that has Daf's own address and may run scripts, and it passes chapters on as the
// book wrote them, scripts and all. inertBook() hooks foliate's loader before it makes those frames:
// script files aren't loaded, and every chapter or picture that could be shown as a page is read,
// stripped of scripts, frames and event handlers, and given a Content-Security-Policy that allows no
// script, whatever type the book says it is. Pictures, fonts, sound and style sheets pass untouched.

const INERT = /^(text\/css|image\/(png|jpe?g|gif|webp|avif|bmp|x-icon|vnd\.microsoft\.icon)|font\/[\w.+-]+|audio\/[\w.+-]+|video\/[\w.+-]+|application\/(font-[\w.+-]+|x-font-[\w.+-]+|vnd\.ms-opentype|octet-stream|pdf))(\s*;.*)?$/;
// Only scripts, plugins, frames and forms are refused: the reader still brings its own fonts and
// styles into each chapter (book.js fontCSS, from Daf's address).
const CSP = "script-src 'none'; object-src 'none'; frame-src 'none'; base-uri 'none'; form-action 'none'";
const GONE = 'script, iframe, frame, frameset, object, embed, applet, base, meta[http-equiv], portal';
const BAD_URL = /^(javascript|vbscript|data:text\/html|data:application\/xhtml|data:image\/svg)/i;

function clean(doc) {
  for (const n of [...doc.childNodes]) if (n.nodeType === 7 && !/type\s*=\s*["']text\/css["']/i.test(n.data)) n.remove();
  for (const x of doc.querySelectorAll(GONE)) x.remove();
  for (const el of doc.querySelectorAll('*')) {
    // SVG <set>/<animate> can turn a link into javascript: after load
    if (/^(set|animate)$/i.test(el.localName) && /href/i.test(el.getAttribute('attributeName') || '')) { el.remove(); continue; }
    for (const a of [...el.attributes]) {
      const v = a.value.replace(/[\u0000- ]/g, '');
      if (/^on/i.test(a.localName) || a.localName === 'srcdoc' || a.localName === 'formaction' || BAD_URL.test(v)) el.removeAttributeNode(a);
    }
  }
  const root = doc.documentElement;
  if (root && root.localName === 'html') {
    let head = root.querySelector(':scope > head');
    if (!head) { head = doc.createElementNS(root.namespaceURI, 'head'); root.prepend(head); }
    const m = doc.createElementNS(root.namespaceURI, 'meta');
    m.setAttribute('http-equiv', 'Content-Security-Policy');
    m.setAttribute('content', CSP);
    head.prepend(m);
  }
  return doc;
}

async function asText(raw) {
  if (typeof raw === 'string') return raw;
  if (raw && typeof raw.text === 'function') return raw.text();                  // a Blob
  if (raw instanceof ArrayBuffer || ArrayBuffer.isView(raw)) return new TextDecoder().decode(raw);
  return String(raw ?? '');
}

export function inertBook(book) {
  const t = book && book.transformTarget;
  if (!t) return;
  t.addEventListener('load', e => { if (e.detail.isScript) e.detail.allow = false; });
  t.addEventListener('data', e => {
    const d = e.detail, declared = String(d.type || '').trim().toLowerCase();
    if (INERT.test(declared)) return;
    let setType;
    const typeP = new Promise(r => { setType = r; });
    d.data = Promise.resolve(d.data).then(async raw => {
      try {
        const s = await asText(raw);
        // no type given and not markup (a picture or font without its type): leave the bytes, never a page
        if (!declared && !/^\s*</.test(s.replace(/^﻿/, ''))) { setType('application/octet-stream'); return raw; }
        let as = /^text\/html\b/.test(declared) ? 'text/html' : /svg/.test(declared) ? 'image/svg+xml' : 'application/xhtml+xml';
        let doc = new DOMParser().parseFromString(s, as);
        if (as !== 'text/html' && doc.querySelector('parsererror')) { as = 'text/html'; doc = new DOMParser().parseFromString(s, as); }
        clean(doc);
        setType(as);
        return as === 'text/html' ? '<!DOCTYPE html>' + doc.documentElement.outerHTML : new XMLSerializer().serializeToString(doc);
      } catch (err) {
        setType('text/plain');
        return '';
      }
    });
    d.type = typeP;                       // foliate awaits detail.type after detail.data
  });
}

// Links a book may open outside itself: web pages and mail only.
export const outsideLink = href => /^(https?|mailto):/i.test(String(href || '').trim());
