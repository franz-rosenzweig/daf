"""Read KOReader's metadata.*.lua sidecars: `return { ... }` tables of strings,
numbers, booleans and nested tables. A small recursive-descent parser, because
regexes over these files drop fields and break on nested quotes."""

_ESC = {"n": "\n", "t": "\t", "r": "\r", "\\": "\\", '"': '"', "'": "'", "\n": "\n", "a": "\a", "b": "\b", "f": "\f", "v": "\v", "0": "\0"}


class _P:
    def __init__(self, s):
        self.s, self.i = s, 0

    def ws(self):
        s, n = self.s, len(self.s)
        while self.i < n:
            c = s[self.i]
            if c in " \t\r\n,;":
                self.i += 1
            elif s.startswith("--", self.i):
                if s.startswith("--[[", self.i):
                    end = s.find("]]", self.i)
                    self.i = n if end < 0 else end + 2
                else:
                    end = s.find("\n", self.i)
                    self.i = n if end < 0 else end + 1
            else:
                break

    def value(self):
        self.ws()
        s = self.s
        c = s[self.i]
        if c == "{":
            return self.table()
        if c in "\"'":
            return self.string()
        if s.startswith("[[", self.i):
            end = s.find("]]", self.i + 2)
            v = s[self.i + 2:end]
            self.i = end + 2
            return v
        if s.startswith("true", self.i):
            self.i += 4
            return True
        if s.startswith("false", self.i):
            self.i += 5
            return False
        if s.startswith("nil", self.i):
            self.i += 3
            return None
        j = self.i
        while j < len(s) and (s[j].isalnum() or s[j] in "+-.xX"):
            j += 1
        tok = s[self.i:j]
        self.i = j
        try:
            return int(tok, 0)
        except ValueError:
            return float(tok)

    def string(self):
        q = self.s[self.i]
        self.i += 1
        out, s = [], self.s
        while True:
            c = s[self.i]
            if c == "\\":
                nxt = s[self.i + 1]
                if nxt.isdigit():
                    j = self.i + 1
                    while j < self.i + 4 and s[j].isdigit():
                        j += 1
                    out.append(chr(int(s[self.i + 1:j])))
                    self.i = j
                    continue
                out.append(_ESC.get(nxt, nxt))
                self.i += 2
            elif c == q:
                self.i += 1
                return "".join(out)
            else:
                out.append(c)
                self.i += 1

    def table(self):
        self.i += 1
        arr, obj = [], {}
        while True:
            self.ws()
            if self.s[self.i] == "}":
                self.i += 1
                break
            if self.s[self.i] == "[" and not self.s.startswith("[[", self.i):
                self.i += 1
                key = self.value()
                self.ws()
                self.i += 1          # ]
                self.ws()
                self.i += 1          # =
                obj[key] = self.value()
            else:
                j = self.i
                while j < len(self.s) and (self.s[j].isalnum() or self.s[j] == "_"):
                    j += 1
                k = self.i
                self.i = j
                self.ws()
                if j > k and self.s[self.i] == "=":
                    self.i += 1
                    obj[self.s[k:j]] = self.value()
                else:
                    self.i = k
                    arr.append(self.value())
        if obj and all(isinstance(k, int) for k in obj) and not arr:
            return [obj[k] for k in sorted(obj)]
        if arr and not obj:
            return arr
        for n, v in enumerate(arr, 1):
            obj.setdefault(n, v)
        return obj


def load(text):
    i = text.find("return")
    p = _P(text[i + 6:] if i >= 0 else text)
    return p.value()
