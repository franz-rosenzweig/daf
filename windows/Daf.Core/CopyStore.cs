using System.Security.Cryptography;
using System.Text;
using System.Text.Json.Nodes;

namespace Daf.Core;

/// <summary>
/// The files of the copy of Daf kept on this PC for no connection (docs/SHELL.md,
/// "Offline"; the Mac's is LocalCopy.swift): app\ holds every file of the server's
/// web\ by its path, data\ what the pages ask Daf for, each under a name made from its
/// address, with its content type beside it in a .type file.
/// </summary>
public sealed class CopyStore
{
    public string Root { get; }
    public string AppDir => Path.Join(Root, "app");
    public string DataDir => Path.Join(Root, "data");

    public CopyStore(string root)
    {
        Root = Path.GetFullPath(root);
        Directory.CreateDirectory(Root);
    }

    /// <summary>The copy has Daf's screens: it can open with no connection.</summary>
    public bool Ready => File.Exists(Path.Join(AppDir, "index.html"));

    /// <summary>
    /// A file's name for an address: the same whether its path came percent-encoded (as
    /// the page asks, kk%3A…) or not (as the plan names it), so both find it.
    /// </summary>
    public static string Key(string address)
    {
        var i = address.IndexOf('?');
        var path = Uri.UnescapeDataString(i < 0 ? address : address[..i]);
        return Sha1(Encoding.UTF8.GetBytes(i < 0 ? path : path + address[i..]));
    }

    /// <summary>
    /// A list kept in another order or with other filters still answers for the same list:
    /// the Library's and the Feed's by where, tab, kind, cat and feed; Highlights whatever its query.
    /// </summary>
    public static string? AnyKey(string address)
    {
        var i = address.IndexOf('?');
        var path = i < 0 ? address : address[..i];
        if (path == "/api/highlights") return "/api/highlights?_any";
        if (path != "/api/docs" || i < 0) return null;
        var q = DafLink.Query(address[(i + 1)..]);
        return "/api/docs?_any" + string.Concat(new[] { "where", "tab", "kind", "cat", "feed" }.Select(k => $"&{k}={q.GetValueOrDefault(k, "")}"));
    }

    public string DataFile(string key) => Path.Join(DataDir, Key(key));

    /// <summary>Keeps what came under its key, and its list's any-key too.</summary>
    public void Store(byte[] data, string type, string key)
    {
        foreach (var k in AnyKey(key) is { } any ? new[] { key, any } : new[] { key })
        {
            var f = DataFile(k);
            Write(f, data);
            Write(f + ".type", Encoding.UTF8.GetBytes(type));
        }
    }

    /// <summary>What was kept for a request: its own key, the path alone (an article), or its list's any-key.</summary>
    public string? Kept(string path, string query)
    {
        var keys = new List<string> { path + query, path };
        if (AnyKey(path + query) is { } any) keys.Add(any);
        return keys.Select(DataFile).FirstOrDefault(File.Exists);
    }

    public bool Has(string key) => File.Exists(DataFile(key));

    public long Size(string key)
    {
        var f = new FileInfo(DataFile(key));
        return f.Exists ? f.Length : 0;
    }

    public static string TypeOf(string file, string fallback = "application/json")
    {
        try { return File.Exists(file + ".type") ? File.ReadAllText(file + ".type") : fallback; }
        catch (IOException) { return fallback; }
    }

    public void Remove(string key)
    {
        var f = DataFile(key);
        try { File.Delete(f); File.Delete(f + ".type"); } catch (IOException) { }
    }

    /// <summary>Read here: it stays three weeks more.</summary>
    public static void Touch(string file)
    {
        try { File.SetLastWriteTimeUtc(file, DateTime.UtcNow); } catch (IOException) { } catch (UnauthorizedAccessException) { }
    }

    /// <summary>
    /// Lets go of what nothing names any more (<paramref name="live"/>: the addresses that
    /// stay), once it hasn't been kept or read here for three weeks. Returns how many went.
    /// </summary>
    public int Prune(IEnumerable<string> live, DateTime now)
    {
        if (!Directory.Exists(DataDir)) return 0;
        var names = live.Select(Key).ToHashSet();
        var old = now.ToUniversalTime().AddDays(-21);
        var n = 0;
        foreach (var f in Directory.EnumerateFiles(DataDir))
        {
            var name = Path.GetFileName(f);
            if (Path.HasExtension(name) || names.Contains(name)) continue;
            if (File.GetLastWriteTimeUtc(f) >= old) continue;
            try { File.Delete(f); File.Delete(f + ".type"); n++; } catch (IOException) { }
        }
        return n;
    }

    /// <summary>An article's pictures: its picture blocks and its thumbnail.</summary>
    public static List<string> Pictures(byte[] doc)
    {
        var out_ = new List<string>();
        try
        {
            if (JsonNode.Parse(doc) is not JsonObject d) return out_;
            foreach (var b in (d["blocks"] as JsonArray ?? new JsonArray()).OfType<JsonObject>())
                if (Text(b["t"]) == "img" && Text(b["src"]) is { } src) out_.Add(src);
            if (Text(d["thumb"]) is { Length: > 0 } thumb) out_.Add(thumb);
        }
        catch (Exception) { }
        return out_;
    }

    /// <summary>An article's pictures, where a copy was kept, pointed at it: https://daf-app.example/__img/&lt;key&gt;.</summary>
    public byte[] LocalPictures(byte[] doc, Func<string, string> absolute)
    {
        try
        {
            if (JsonNode.Parse(doc) is not JsonObject d || d["blocks"] is not JsonArray blocks) return doc;
            foreach (var b in blocks.OfType<JsonObject>())
            {
                if (Text(b["t"]) != "img" || Text(b["src"]) is not { Length: > 0 } src || src.StartsWith("data:")) continue;
                var abs = absolute(src);
                if (Has(abs)) b["src"] = Address.CopyOrigin + "/__img/" + Key(abs);
            }
            return Encoding.UTF8.GetBytes(d.ToJsonString());
        }
        catch (Exception) { return doc; }
    }

    /// <summary>
    /// One of the copy's own files for a path of the page (/app.js, /fonts/…), or index.html
    /// for any other: a route, a folder, or a path that would leave app\.
    /// </summary>
    public string AppFile(string path)
    {
        var app = Path.TrimEndingDirectorySeparator(Path.GetFullPath(AppDir));
        var index = Path.Join(app, "index.html");
        var rel = path.TrimStart('/');
        if (rel.Length == 0 || rel.Contains('\\') || rel.Contains(':')) return index;
        var candidate = Path.GetFullPath(Path.Join(app, rel.Replace('/', Path.DirectorySeparatorChar)));
        return candidate.StartsWith(app + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase) && File.Exists(candidate) ? candidate : index;
    }

    /// <summary>The copy's size on disk.</summary>
    public long Bytes()
    {
        long n = 0;
        foreach (var dir in new[] { AppDir, DataDir })
            if (Directory.Exists(dir))
                foreach (var f in Directory.EnumerateFiles(dir, "*", SearchOption.AllDirectories))
                    try { n += new FileInfo(f).Length; } catch (IOException) { }
        return n;
    }

    /// <summary>Written whole or not at all: to a file beside it first, then moved into place.</summary>
    public static void Write(string path, byte[] data)
    {
        Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(path))!);
        var temp = path + "." + Guid.NewGuid().ToString("N")[..8] + ".tmp";
        File.WriteAllBytes(temp, data);
        File.Move(temp, path, overwrite: true);
    }

    public static string Sha1(byte[] data) => Convert.ToHexStringLower(SHA1.HashData(data));

    static string? Text(JsonNode? n) => n is JsonValue v && v.TryGetValue(out string? s) ? s : null;
}
