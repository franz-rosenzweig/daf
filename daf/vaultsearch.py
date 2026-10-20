"""Search the Obsidian vault from ⌘K: note names first, then text (grep, fixed string).
Results open in Obsidian. Folders in settings `vault_search_exclude` are never searched."""
import re
import subprocess
import urllib.parse

from . import config

SKIP = [".obsidian", ".trash", ".claude", ".git"]


def search(q, settings, limit=10):
    q = (q or "").strip()
    if len(q) < 3:
        return []
    skip = SKIP + [d for d in settings.get("vault_search_exclude", []) if isinstance(d, str)]
    vault = config.VAULT
    ql = q.lower()
    out, seen = [], set()
    # Names first.
    for p in vault.rglob("*.md"):
        rel = p.relative_to(vault)
        if any(part.startswith(".") for part in rel.parts) or any(str(rel).startswith(s + "/") for s in skip):
            continue
        if ql in p.stem.lower():
            out.append(str(rel))
            seen.add(str(rel))
            if len(out) >= limit // 2:
                break
    # Then text.
    cmd = ["grep", "-rIl", "-i", "-F", "--include=*.md", "--exclude-dir=.*"] + [f"--exclude-dir={d.split('/')[-1]}" for d in skip] + ["--", q, "."]
    try:
        r = subprocess.run(cmd, cwd=vault, capture_output=True, text=True, timeout=4)
        for line in r.stdout.splitlines():
            rel = line[2:] if line.startswith("./") else line
            if rel in seen or any(rel.startswith(s + "/") for s in skip) or "/." in "/" + rel:
                continue
            out.append(rel)
            seen.add(rel)
            if len(out) >= limit:
                break
    except subprocess.TimeoutExpired:
        pass
    res = []
    for rel in out[:limit]:
        snippet = ""
        try:
            text = (vault / rel).read_text(encoding="utf-8", errors="ignore")
            text = re.sub(r"^---\n.*?\n---\n", "", text, flags=re.S)
            i = text.lower().find(ql)
            if i >= 0:
                snippet = re.sub(r"\s+", " ", text[max(0, i - 60): i + 100]).strip()
        except OSError:
            pass
        name = rel[:-3] if rel.endswith(".md") else rel
        res.append({"path": rel, "title": name.split("/")[-1], "folder": "/".join(name.split("/")[:-1]), "snippet": snippet,
                    "open": "obsidian://open?vault=" + urllib.parse.quote(vault.name) + "&file=" + urllib.parse.quote(name)})
    return res
