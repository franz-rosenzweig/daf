using System.Net;
using System.Text.Json;
using System.Text.Json.Nodes;

namespace Daf.Core;

/// <summary>Daf says there's no such thing (any more): 404 or 410.</summary>
public sealed class Gone : Exception
{
    public Gone() : base("Daf has no such thing any more") { }
}

/// <summary>
/// Keeps the copy up to date while Daf answers, and keeps what's kept by hand
/// (<c>dafShell.offline</c>, docs/SHELL.md §2): Daf's screens (every file of web/, from
/// /api/app-files, fetched again only when its hash changes), what /api/offline/plan says
/// to keep (today, the review ahead, lists, the articles being read with their pictures
/// and PDFs, the books being read), and the articles, books and manga volumes kept by
/// hand. What nothing names any more goes once it hasn't been kept or read here for three
/// weeks. The Mac's is LocalCopy.swift and OnThisMac.swift; the calls and answers are Android's.
/// </summary>
public sealed class Keeper
{
    public sealed class CopyState
    {
        public string Version { get; set; } = "";
        public Dictionary<string, string> Hashes { get; set; } = new();
        /// <summary>When the copy last updated, in milliseconds since 1970; 0 for never.</summary>
        public long At { get; set; }
        public long DataAt { get; set; }
    }

    public sealed class Book
    {
        public string Title { get; set; } = "";
        public bool IsPrivate { get; set; }
        public string Format { get; set; } = "";
        public long Size { get; set; }
        public bool Kept { get; set; }
    }

    public sealed class Manga
    {
        public string Title { get; set; } = "";
        public string Series { get; set; } = "";
        public string SeriesId { get; set; } = "";
        public string State { get; set; } = "";
        public string? Error { get; set; }
        public int Done { get; set; }
        public int Total { get; set; }
        public long Bytes { get; set; }
        public int Size { get; set; } = 1800;
    }

    /// <summary>What's kept by hand, and what the plan named last (kept.json).</summary>
    public sealed class Kept
    {
        public List<string> Docs { get; set; } = [];
        public List<string> PlanDocs { get; set; } = [];
        public List<string> PlanBooks { get; set; } = [];
        public Dictionary<string, Book> Books { get; set; } = new();
        public Dictionary<string, Manga> Mangas { get; set; } = new();
    }

    public sealed record Got(byte[] Data, string Type);

    public CopyStore Store { get; }
    public CopyState Copy { get; private set; }
    public Kept State { get; private set; }

    readonly HttpClient http;
    readonly Func<Uri> baseUrl;
    readonly Func<Task<string?>> cookies;
    readonly string userAgent;
    readonly SemaphoreSlim refreshing = new(1, 1);
    readonly object gate = new();
    Task downloading = Task.CompletedTask;

    string CopyFile => Path.Join(Store.Root, "copy.json");
    string KeptFile => Path.Join(Store.Root, "kept.json");

    /// <param name="cookies">The window's sign-in for Daf's address, as a Cookie header.</param>
    public Keeper(string root, HttpClient http, Func<Uri> baseUrl, Func<Task<string?>> cookies, string userAgent)
    {
        Store = new CopyStore(root);
        this.http = http;
        this.baseUrl = baseUrl;
        this.cookies = cookies;
        this.userAgent = userAgent;
        Copy = Load<CopyState>(CopyFile) ?? new CopyState();
        State = Load<Kept>(KeptFile) ?? new Kept();
    }

    static T? Load<T>(string file) where T : class
    {
        try { return File.Exists(file) ? JsonSerializer.Deserialize<T>(File.ReadAllBytes(file)) : null; }
        catch (Exception) { return null; }
    }

    void Save()
    {
        lock (gate)
        {
            CopyStore.Write(KeptFile, JsonSerializer.SerializeToUtf8Bytes(State));
            CopyStore.Write(CopyFile, JsonSerializer.SerializeToUtf8Bytes(Copy));
        }
    }

    Uri Url(string where) => Address.Url(baseUrl(), where);

    static long Now() => DateTimeOffset.UtcNow.ToUnixTimeMilliseconds();

    // ---- fetching --------------------------------------------------------------------------

    /// <summary>GET, with the window's sign-in when <paramref name="auth"/>. 404 and 410 are Gone; anything but 200 fails.</summary>
    public async Task<Got> Fetch(Uri url, bool auth, int seconds = 60)
    {
        using var r = new HttpRequestMessage(HttpMethod.Get, url);
        r.Headers.TryAddWithoutValidation("User-Agent", userAgent);
        r.Headers.TryAddWithoutValidation("Cache-Control", "no-cache");
        if (auth && await cookies() is { Length: > 0 } c) r.Headers.TryAddWithoutValidation("Cookie", c);
        using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(seconds));
        using var response = await http.SendAsync(r, timeout.Token);
        if (auth && response.StatusCode is HttpStatusCode.NotFound or HttpStatusCode.Gone) throw new Gone();
        if (response.StatusCode != HttpStatusCode.OK) throw new HttpRequestException($"Daf answered {(int)response.StatusCode}");
        return new Got(await response.Content.ReadAsByteArrayAsync(timeout.Token), response.Content.Headers.ContentType?.ToString() ?? "application/octet-stream");
    }

    /// <summary>Fetches and keeps an address under its key. False if it didn't come or was too big.</summary>
    public async Task<bool> Keep(string key, Uri url, bool auth = true, long limit = 64L << 20)
    {
        try
        {
            var got = await Fetch(url, auth);
            if (got.Data.Length > limit) return false;
            Store.Store(got.Data, got.Type, key);
            return true;
        }
        catch (Exception) { return false; }
    }

    // ---- keeping up to date ----------------------------------------------------------------

    /// <summary>
    /// Daf's screens, and its data when <paramref name="data"/> or when they're older than three
    /// hours. Asked for (data), it waits for an update already going; in the background it lets
    /// that one be. Says what it did.
    /// </summary>
    public async Task<string> Refresh(bool data = true)
    {
        if (!await refreshing.WaitAsync(data ? TimeSpan.FromMinutes(10) : TimeSpan.Zero)) return "It's already updating.";
        try
        {
            await RefreshScreens();
            var said = "Daf's screens are up to date";
            if (data || Now() - Copy.DataAt > 3 * 3600_000 || Copy.DataAt == 0)
            {
                said = await KeepData();
                Copy.DataAt = Now();
            }
            Copy.At = Now();
            Save();
            return said;
        }
        catch (Exception e)
        {
            return "Daf didn't answer: " + e.Message;
        }
        finally { refreshing.Release(); }
    }

    /// <summary>Fetches the files of web/ that changed, each checked against its SHA-1. True if any came.</summary>
    public async Task<bool> RefreshScreens()
    {
        var list = await Fetch(Url("/api/app-files"), auth: false);
        if (JsonNode.Parse(list.Data) is not JsonObject d || Text(d["version"]) is not { } version || d["files"] is not JsonArray files)
            throw new InvalidDataException("Daf's list of files didn't make sense");
        if (version == Copy.Version && Store.Ready) return false;
        var app = Path.TrimEndingDirectorySeparator(Path.GetFullPath(Store.AppDir));
        var now = new Dictionary<string, string>();
        foreach (var f in files.OfType<JsonObject>())
        {
            if (Text(f["path"]) is not { Length: > 1 } path || Text(f["sha1"]) is not { } sha) continue;
            var to = Path.GetFullPath(Path.Join(app, path.TrimStart('/').Replace('/', Path.DirectorySeparatorChar)));
            if (!to.StartsWith(app + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase)) continue;
            if (Copy.Hashes.GetValueOrDefault(path) != sha || !File.Exists(to))
            {
                var body = (await Fetch(Url(path), auth: false)).Data;
                if (CopyStore.Sha1(body) != sha) throw new InvalidDataException($"{path} came different from Daf's list");
                CopyStore.Write(to, body);
            }
            now[path] = sha;
        }
        Copy.Hashes = now;
        Copy.Version = version;
        Save();
        return true;
    }

    static readonly string[] DefaultUrls = ["/api/me", "/api/settings", "/api/today", "/api/review", "/api/home", "/api/books", "/api/highlights", "/api/docs/counts", "/api/stats"];

    /// <summary>
    /// What the plan names, by address and query; pictures by their whole address; then
    /// what's kept by hand, up to date; then what nothing names any more goes, once it
    /// hasn't been kept or read here for three weeks. Says what it did.
    /// </summary>
    public async Task<string> KeepData()
    {
        var urls = DefaultUrls.ToList();
        List<string> docs = [], images = [], ebooks = [];
        JsonObject? plan = null;
        try { plan = JsonNode.Parse((await Fetch(Url("/api/offline/plan"), auth: true)).Data) as JsonObject; } catch (Exception) { }
        if (plan != null)
        {
            urls = Strings(plan["urls"]) ?? urls;
            docs = Strings(plan["docs"]) ?? [];
            images = Strings(plan["images"]) ?? [];
            ebooks = Strings(plan["ebooks"]) ?? [];
        }
        var live = new HashSet<string>();
        int got = 0, failed = 0;
        foreach (var u in urls)
        {
            live.Add(u);
            if (CopyStore.AnyKey(u) is { } any) live.Add(any);
            if (await Keep(u, Url(u))) got++; else failed++;
        }
        var planDocs = new List<string>();
        foreach (var id in docs)
        {
            var path = DocPath(id);
            try
            {
                var b = await KeepDoc(path, pictures: false);
                images.AddRange(CopyStore.Pictures(b));
                live.UnionWith(DocKeys(path, b));
                planDocs.Add(id);
                got++;
            }
            catch (Exception) { failed++; }
        }
        if (plan != null) lock (gate) State.PlanDocs = planDocs;
        // the articles kept by hand, pictures and all; one deleted in Daf goes from here too
        foreach (var id in State.Docs.ToList())
        {
            var path = DocPath(id);
            try
            {
                var b = await KeepDoc(path, pictures: true);
                if (JsonNode.Parse(b) is JsonObject o && Text(o["status"]) == "deleted") throw new Gone();
                live.UnionWith(DocKeys(path, b));
            }
            catch (Gone)
            {
                lock (gate) State.Docs.Remove(id);
                Store.Remove(path);
                Store.Remove(path + "/pdf");
            }
            catch (Exception)
            {
                if (Store.Has(path)) live.UnionWith(DocKeys(path, File.ReadAllBytes(Store.DataFile(path))));   // no answer now: it stays
            }
        }
        // the books being read (the plan's) and the ones kept by hand
        if (plan != null) lock (gate) State.PlanBooks = ebooks;
        foreach (var id in BooksToKeep(ebooks))
        {
            try { await FetchBook(id); }
            catch (Gone) { lock (gate) State.Books.Remove(id); }
            catch (Exception) { }
            live.UnionWith(BookKeys(id));
        }
        foreach (var img in images.Where(i => i.Length > 0 && !i.StartsWith("data:"))) live.Add(Absolute(img));
        foreach (var img in images.Where(i => i.Length > 0 && !i.StartsWith("data:")).Take(400))
        {
            var abs = Absolute(img);
            if (!Store.Has(abs) && Uri.TryCreate(abs, UriKind.Absolute, out var u)) await Keep(abs, u, auth: Address.IsDaf(u, baseUrl()), limit: 4 << 20);
        }
        live.UnionWith(MangaKeys());
        var gone = Store.Prune(live, DateTime.UtcNow);
        ForgetMissing();
        Save();
        return $"{got} kept" + (failed > 0 ? $", {failed} didn't come" : "") + (gone > 0 ? $", {gone} let go" : "");
    }

    /// <summary>An id as the page puts it in a path (encodeURIComponent).</summary>
    public static string Enc(string id) => Uri.EscapeDataString(id);

    public static string DocPath(string id) => "/api/docs/" + Enc(id);
    public static string BookPath(string id) => "/api/ebooks/" + Enc(id);
    public static string MangaPath(string id) => "/api/manga/books/" + Enc(id);

    public string Absolute(string src) => src.StartsWith('/') ? Url(src).AbsoluteUri : src;

    /// <summary>An article, and its PDF when it has one; by hand, its pictures too. Gone when Daf has no such article.</summary>
    public async Task<byte[]> KeepDoc(string path, bool pictures)
    {
        var got = await Fetch(Url(path + "?prefetch=1"), auth: true);
        Store.Store(got.Data, got.Type, path);
        JsonObject? d = null;
        try { d = JsonNode.Parse(got.Data) as JsonObject; } catch (Exception) { }
        if ((Text(d?["kind"]) == "pdf" || Bool(d?["has_pdf"])) && !Store.Has(path + "/pdf")) await Keep(path + "/pdf", Url(path + "/pdf"));
        if (pictures)
            foreach (var img in CopyStore.Pictures(got.Data).Where(i => i.Length > 0 && !i.StartsWith("data:")))
            {
                var abs = Absolute(img);
                if (!Store.Has(abs) && Uri.TryCreate(abs, UriKind.Absolute, out var u)) await Keep(abs, u, auth: Address.IsDaf(u, baseUrl()), limit: 4 << 20);
            }
        return got.Data;
    }

    /// <summary>The keys an article keeps: itself, its PDF, its pictures.</summary>
    public IEnumerable<string> DocKeys(string path, byte[] doc) =>
        new[] { path, path + "/pdf" }.Concat(CopyStore.Pictures(doc).Where(i => i.Length > 0 && !i.StartsWith("data:")).Select(Absolute));

    public static string[] BookKeys(string id) => [BookPath(id), BookPath(id) + "/file", "/api/cover/" + Enc(id)];

    /// <summary>The plan's books and the ones kept by hand.</summary>
    List<string> BooksToKeep(List<string> plan)
    {
        var out_ = plan.ToList();
        lock (gate) out_.AddRange(State.Books.Where(b => b.Value.Kept && !out_.Contains(b.Key)).Select(b => b.Key));
        return out_;
    }

    /// <summary>A book's details and its file (again only when its format or size changed) and its cover.</summary>
    public async Task FetchBook(string id)
    {
        var path = BookPath(id);
        var info = await Fetch(Url(path), auth: true);
        Store.Store(info.Data, info.Type, path);
        var d = JsonNode.Parse(info.Data) as JsonObject ?? new JsonObject();
        Book b;
        lock (gate) b = State.Books.GetValueOrDefault(id) ?? new Book();
        var format = Text(d["format"]) ?? "";
        var want = d["size"] is JsonValue v && v.TryGetValue(out long size) ? size : -1;
        if (!(Store.Has(path + "/file") && format == b.Format && Store.Size(path + "/file") == want))
        {
            var file = await Fetch(Url(path + "/file"), auth: true, seconds: 600);
            Store.Store(file.Data, file.Type, path + "/file");
        }
        var cover = "/api/cover/" + Enc(id);
        if (!Store.Has(cover)) await Keep(cover, Url(cover), limit: 4 << 20);
        b.Title = Text(d["title"]) ?? b.Title;
        b.IsPrivate = Bool(d["private"]);
        b.Format = format;
        b.Size = Store.Size(path + "/file");
        lock (gate) State.Books[id] = b;
    }

    /// <summary>Books whose file went (let go after three weeks) leave the list; a kept one stays, to come again.</summary>
    void ForgetMissing()
    {
        lock (gate)
            foreach (var id in State.Books.Where(b => !b.Value.Kept && !Store.Has(BookPath(b.Key) + "/file")).Select(b => b.Key).ToList())
                State.Books.Remove(id);
    }

    /// <summary>The keys a downloaded volume keeps: itself, its pages, its series, the reader's settings.</summary>
    List<string> MangaKeys()
    {
        var out_ = new List<string>();
        lock (gate)
            foreach (var (id, m) in State.Mangas)
            {
                out_.Add(MangaPath(id));
                for (var n = 1; n <= m.Total; n++) out_.Add(MangaPath(id) + $"/pages/{n}");
                if (m.SeriesId.Length > 0) out_.Add("/api/manga/series/" + Enc(m.SeriesId));
            }
        if (out_.Count > 0) out_.Add("/api/manga/prefs");
        return out_;
    }

    // ---- the page's calls: dafShell.offline ------------------------------------------------

    public async Task<JsonNode> Answer(JsonObject args)
    {
        var op = Text(args["op"]) is { Length: > 0 } o ? o : "list";
        var id = Text(args["id"]) ?? "";
        var on = args["on"] is not JsonValue onv || !onv.TryGetValue(out bool b) || b;
        switch (op)
        {
            case "has":
                return new JsonObject { ["has"] = Store.Has(BookPath(id) + "/file") };
            case "keep":
                if (id.Length == 0) throw new InvalidOperationException("Which book?");
                await KeepBook(id, on);
                break;
            case "doc":
                if (id.Length == 0) throw new InvalidOperationException("Which article?");
                await KeepDocByHand(id, on);
                break;
            case "manga":
                if (id.Length == 0) throw new InvalidOperationException("Which volume?");
                var size = (int)(Number(args["size"]) ?? 1800);
                if (on) KeepManga(id, Math.Clamp(size == 0 ? 1800 : size, 600, 2400)); else RemoveManga(id);
                break;
            case "sync":
            {
                var said = await Refresh();
                var l = List();
                l["said"] = said;
                return l;
            }
        }
        return List();
    }

    /// <summary>What's on this PC: {app, data, docs: [{id, pinned}], books: [{id, title, size, kept}], manga: [...], bytes, synced}.</summary>
    public JsonObject List()
    {
        lock (gate)
        {
            long bytes = 0;
            var books = new JsonArray();
            foreach (var (id, b) in State.Books)
            {
                if (!Store.Has(BookPath(id) + "/file")) continue;
                bytes += b.Size;
                books.Add(new JsonObject { ["id"] = id, ["title"] = b.IsPrivate ? "Private reading" : b.Title, ["size"] = b.Size, ["kept"] = b.Kept });
            }
            var manga = new JsonArray();
            foreach (var (id, m) in State.Mangas)
            {
                bytes += m.Bytes;
                var x = new JsonObject { ["id"] = id, ["title"] = m.Title, ["series"] = m.Series, ["state"] = m.State, ["done"] = m.Done, ["total"] = m.Total, ["bytes"] = m.Bytes };
                if (m.Error != null) x["error"] = m.Error;
                manga.Add(x);
            }
            var docs = new JsonArray();
            foreach (var id in State.Docs) docs.Add(new JsonObject { ["id"] = id, ["pinned"] = true });
            foreach (var id in State.PlanDocs.Where(d => !State.Docs.Contains(d))) docs.Add(new JsonObject { ["id"] = id, ["pinned"] = false });
            return new JsonObject
            {
                ["app"] = new JsonObject { ["ready"] = Store.Ready, ["version"] = Copy.Version, ["at"] = Copy.At },
                ["data"] = Copy.At, ["docs"] = docs, ["books"] = books, ["manga"] = manga, ["bytes"] = bytes,
                ["reading"] = true, ["wifi"] = false, ["synced"] = Copy.At,
            };
        }
    }

    async Task KeepDocByHand(string id, bool on)
    {
        var path = DocPath(id);
        if (on)
        {
            try { await KeepDoc(path, pictures: true); }
            catch (Gone) { throw new InvalidOperationException("Daf doesn't have this article any more."); }
            catch (Exception e) { throw new InvalidOperationException("Daf didn't answer: " + e.Message); }
            lock (gate) if (!State.Docs.Contains(id)) State.Docs.Add(id);
        }
        else
        {
            bool planned;
            lock (gate) { State.Docs.Remove(id); planned = State.PlanDocs.Contains(id); }
            if (!planned) { Store.Remove(path); Store.Remove(path + "/pdf"); }   // nothing else wants it: now
        }
        Save();
    }

    async Task KeepBook(string id, bool on)
    {
        if (on)
        {
            try { await FetchBook(id); }
            catch (Gone) { throw new InvalidOperationException("Daf has no file for this book."); }
            catch (Exception e) { throw new InvalidOperationException("Daf didn't answer: " + e.Message); }
            lock (gate) if (State.Books.TryGetValue(id, out var b)) b.Kept = true;
        }
        else
        {
            bool planned;
            lock (gate)
            {
                if (State.Books.TryGetValue(id, out var b)) b.Kept = false;
                planned = State.PlanBooks.Contains(id);
                if (!planned) State.Books.Remove(id);
            }
            if (!planned) foreach (var k in BookKeys(id)) Store.Remove(k);   // not being read either: it goes now
        }
        Save();
    }

    /// <summary>Downloads a volume's pages at the size this screen's reader asks for, one volume at a time; what's already here stays.</summary>
    void KeepManga(string id, int size)
    {
        lock (gate)
        {
            var m = State.Mangas.GetValueOrDefault(id) ?? new Manga();
            m.State = "waiting";
            m.Size = size;
            m.Error = null;
            State.Mangas[id] = m;
            var before = downloading;
            downloading = Task.Run(async () =>
            {
                try { await before; } catch (Exception) { }
                await Download(id);
            });
        }
        Save();
    }

    /// <summary>The volume's download, done one after another; for the self-test and Settings.</summary>
    public Task Downloads { get { lock (gate) return downloading; } }

    void Update(string id, Action<Manga> change)
    {
        lock (gate)
        {
            if (!State.Mangas.TryGetValue(id, out var m)) return;
            change(m);
        }
        Save();
    }

    async Task Download(string id)
    {
        int size;
        lock (gate)
        {
            if (!State.Mangas.TryGetValue(id, out var m)) return;      // removed while it waited
            size = m.Size;
        }
        var path = MangaPath(id);
        try
        {
            var got = await Fetch(Url(path), auth: true);
            Store.Store(got.Data, got.Type, path);
            var d = JsonNode.Parse(got.Data) as JsonObject ?? new JsonObject();
            var total = (d["pages"] as JsonArray)?.Count ?? 0;
            var series = d["series"] as JsonObject ?? new JsonObject();
            Update(id, m =>
            {
                m.State = "loading"; m.Total = total;
                m.Title = Text(d["name"]) ?? ""; m.Series = Text(series["name"]) ?? ""; m.SeriesId = Text(series["id"]) ?? "";
            });
            // the series page and the reader's settings, so the volume can be reached and read offline
            if (Text(series["id"]) is { } sid) await Keep("/api/manga/series/" + Enc(sid), Url("/api/manga/series/" + Enc(sid)));
            await Keep("/api/manga/prefs", Url("/api/manga/prefs"));
            long bytes = 0;
            for (var n = 1; n <= total; n++)
            {
                lock (gate) if (!State.Mangas.ContainsKey(id)) return;     // removed while it loaded
                var page = path + $"/pages/{n}";
                if (!Store.Has(page))
                {
                    var g = await Fetch(Url(page + $"?size={size}"), auth: true);
                    Store.Store(g.Data, g.Type, page);
                }
                bytes += Store.Size(page);
                if (n % 5 == 0 || n == total) { var done = n; var b = bytes; Update(id, m => { m.Done = done; m.Bytes = b; }); }
            }
            Update(id, m => m.State = "done");
        }
        catch (Gone) { Update(id, m => { m.State = "failed"; m.Error = "Komga doesn't have it any more"; }); }
        catch (Exception e) { Update(id, m => { m.State = "failed"; m.Error = e.Message; }); }
    }

    void RemoveManga(string id)
    {
        Manga? m;
        lock (gate) { if (!State.Mangas.Remove(id, out m)) return; }
        Store.Remove(MangaPath(id));
        for (var n = 1; n <= m.Total; n++) Store.Remove(MangaPath(id) + $"/pages/{n}");
        Save();
    }

    // ---- the copy's /api/: through to Daf, or from what was kept ------------------------------

    public sealed record Forwarded(int Status, string Type, byte[] Data, Dictionary<string, string> Headers, List<string> SetCookies);

    // the sign-in, the address and the body's own headers are the shell's to say; and no 304s,
    // since nothing in WebView2 is holding a copy to fall back on
    static readonly HashSet<string> NotForwarded = new(StringComparer.OrdinalIgnoreCase)
    {
        "cookie", "host", "origin", "referer", "user-agent", "content-length", "content-type", "connection",
        "accept-encoding", "if-none-match", "if-modified-since",
    };
    static readonly string[] Passed = ["Content-Range", "Accept-Ranges", "Content-Disposition", "ETag", "Last-Modified"];

    /// <summary>
    /// A request the copy's page made to its /api/, sent on to Daf with the window's sign-in.
    /// A 200 GET is kept for later. Null when Daf doesn't answer (no network, or Cloudflare
    /// saying the server is down), so the caller can answer from what was kept.
    /// </summary>
    public async Task<Forwarded?> Forward(string method, string pathAndQuery, IEnumerable<KeyValuePair<string, string>> headers, byte[]? body)
    {
        try
        {
            using var r = new HttpRequestMessage(new HttpMethod(method), Url(pathAndQuery));
            string? contentType = null;
            foreach (var (k, v) in headers)
            {
                if (k.Equals("content-type", StringComparison.OrdinalIgnoreCase)) contentType = v;
                if (!NotForwarded.Contains(k)) r.Headers.TryAddWithoutValidation(k, v);
            }
            r.Headers.TryAddWithoutValidation("User-Agent", userAgent);
            if (await cookies() is { Length: > 0 } c) r.Headers.TryAddWithoutValidation("Cookie", c);
            if (body != null && method is not ("GET" or "HEAD"))
            {
                r.Content = new ByteArrayContent(body);
                if (contentType != null) r.Content.Headers.TryAddWithoutValidation("Content-Type", contentType);
            }
            using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(30));
            using var response = await http.SendAsync(r, timeout.Token);
            var code = (int)response.StatusCode;
            if (code is 502 or 503 or 504 or (>= 520 and <= 530)) return null;
            var data = await response.Content.ReadAsByteArrayAsync(timeout.Token);
            var type = response.Content.Headers.ContentType?.ToString() ?? "application/octet-stream";
            var path = pathAndQuery.Split('?')[0];
            var query = pathAndQuery.Length > path.Length ? pathAndQuery[path.Length..] : "";
            if (method == "GET" && code == 200 && data.Length < (16 << 20) && !path.EndsWith("/file")) Store.Store(data, type, path + query);
            var out_ = new Dictionary<string, string>();
            foreach (var k in Passed)
                if (response.Headers.TryGetValues(k, out var vs) || response.Content.Headers.TryGetValues(k, out vs)) out_[k] = string.Join(", ", vs);
            var setCookies = response.Headers.TryGetValues("Set-Cookie", out var sc) ? sc.ToList() : new List<string>();
            return new Forwarded(code, type, data, out_, setCookies);
        }
        catch (Exception e) when (e is HttpRequestException or TaskCanceledException or IOException)
        {
            return null;
        }
    }

    // ---- JSON ----------------------------------------------------------------------------------

    static string? Text(JsonNode? n) => n is JsonValue v && v.TryGetValue(out string? s) ? s : null;
    static bool Bool(JsonNode? n) => n is JsonValue v && v.TryGetValue(out bool b) && b;
    static double? Number(JsonNode? n) =>
        n is JsonValue && double.TryParse(n.ToJsonString(), System.Globalization.NumberStyles.Float, System.Globalization.CultureInfo.InvariantCulture, out var d) ? d : null;
    static List<string>? Strings(JsonNode? n) => n is JsonArray a ? a.Select(Text).OfType<string>().ToList() : null;
}
