#!/usr/bin/env python3
"""Fetch the reading typefaces into web/fonts (served by Daf itself, so they work offline and no font
request leaves the device). Every one is under the SIL Open Font License, from Fontsource (npm, via
jsDelivr): its own @font-face rules are kept, with their unicode ranges, for the Latin, Latin
Extended and Hebrew subsets only, and their files saved beside them.

    tools/fetch-fonts.py        (then commit web/fonts)
"""
import json
import re
import sys
import urllib.request
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "web" / "fonts"
CDN = "https://cdn.jsdelivr.net/npm/"
SUBSETS = ("latin", "latin-ext", "hebrew")

# (CSS family, Fontsource package, variable?, static weights). Variable families bring every weight.
FAMILIES = [
    ("Literata", "literata", True, None),
    ("Source Serif 4", "source-serif-4", True, None),
    ("Charis SIL", "charis-sil", False, (400, 700)),
    ("Merriweather", "merriweather", True, None),
    ("Lora", "lora", True, None),
    ("EB Garamond", "eb-garamond", True, None),
    ("Crimson Pro", "crimson-pro", True, None),
    ("Newsreader", "newsreader", True, None),
    ("Spectral", "spectral", False, (400, 600)),
    ("Libre Baskerville", "libre-baskerville", False, (400, 700)),
    ("Alegreya", "alegreya", True, None),
    ("Vollkorn", "vollkorn", True, None),
    ("Bitter", "bitter", True, None),
    ("IBM Plex Serif", "ibm-plex-serif", False, (400, 600)),
    ("Atkinson Hyperlegible", "atkinson-hyperlegible", False, (400, 700)),
    ("Figtree", "figtree", True, None),
    ("Inter", "inter", True, None),
    ("Source Sans 3", "source-sans-3", True, None),
    ("Lexend", "lexend", True, None),
    ("OpenDyslexic", "opendyslexic", False, (400, 700)),
    ("Frank Ruhl Libre", "frank-ruhl-libre", True, None),
    ("Noto Serif Hebrew", "noto-serif-hebrew", True, None),
    ("David Libre", "david-libre", False, (400, 700)),
    ("Heebo", "heebo", True, None),
]


def get(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Daf fetch-fonts"}), timeout=60) as r:
        return r.read()


def css_files(pkg, variable, weights):
    """The package's stylesheets for what we want: (url, text) pairs."""
    base = CDN + ("@fontsource-variable/" if variable else "@fontsource/") + pkg + "/"
    names = ["wght.css", "wght-italic.css"] if variable else [f"{w}.css" for w in weights] + [f"{w}-italic.css" for w in weights]
    out = []
    for n in names:
        try:
            out.append((base, get(base + n).decode()))
        except Exception:  # noqa: BLE001 - not every family has italics
            pass
    return out


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    rules, total, missing = [], 0, []
    for family, pkg, variable, weights in FAMILIES:
        sheets = css_files(pkg, variable, weights)
        if not sheets and variable:                       # no variable build: the static one
            sheets = css_files(pkg, False, (400, 700))
        if not sheets:
            missing.append(family)
            continue
        n = 0
        for base, css in sheets:
            for block in re.findall(r"@font-face\s*{[^}]*}", css):
                m = re.search(r"url\(\./files/([^)]+?\.woff2)\)", block)
                if not m or not any(re.search(rf"-{s}-", m.group(1)) for s in SUBSETS):
                    continue
                name = m.group(1)
                path = OUT / name
                if not path.exists():
                    path.write_bytes(get(base + "files/" + name))
                total += path.stat().st_size
                block = re.sub(r"font-family:\s*'[^']*'", f"font-family: '{family}'", block)
                block = re.sub(r"src:[^;]*;", f"src: url(./{name}) format('woff2');", block)
                rules.append(block)
                n += 1
        print(f"{family:24s} {n} faces", file=sys.stderr)
    head = "/* Daf's typefaces (tools/fetch-fonts.py): SIL Open Font License, from Fontsource. */\n"
    (OUT / "fonts.css").write_text(head + "\n".join(rules) + "\n")
    print(f"{len(rules)} @font-face rules, {total / 1e6:.1f} MB" + (f"; not found: {', '.join(missing)}" if missing else ""), file=sys.stderr)


if __name__ == "__main__":
    main()
