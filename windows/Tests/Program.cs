// The tests of Daf.Core (windows/Daf.Core): the address and daf:// links, the device
// token kept with DPAPI, the widget's numbers and words, the copy's files (their names,
// the lists' any-keys, three weeks before what nothing names goes, pictures pointed at
// the copy), and the copy kept up to date from a stand-in Daf on 127.0.0.1: the screens
// checked by their hashes, the plan, articles, books and manga kept by hand, and the
// copy's /api/ sent on with the sign-in.
//
//   dotnet run --project windows/Tests
using System.Net;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json.Nodes;
using Daf.Core;

var failures = 0;
var scratch = new List<string>();

void Check(bool ok, string what, string detail = "")
{
    Console.WriteLine($"{(ok ? "ok  " : "FAIL")}  {what}{(ok || detail.Length == 0 ? "" : $"  ({detail})")}");
    if (!ok) failures++;
}

string Scratch()
{
    var dir = Path.Join(Path.GetTempPath(), "daf-tests-" + Guid.NewGuid().ToString("N"));
    Directory.CreateDirectory(dir);
    scratch.Add(dir);
    return dir;
}

byte[] Utf8(string s) => Encoding.UTF8.GetBytes(s);
string Sha1(byte[] b) => Convert.ToHexStringLower(SHA1.HashData(b));

try
{
    // ---- the address
    Check(Address.Normal("https://daf.tiresia.xyz/")?.AbsoluteUri == "https://daf.tiresia.xyz/", "an address keeps its scheme and host");
    Check(Address.Normal(" http://100.1.2.3:8440/some/path?x=1 ")?.AbsoluteUri == "http://100.1.2.3:8440/", "an address drops its path and keeps its port");
    Check(Address.Normal("ftp://daf.example") == null && Address.Normal("daf.tiresia.xyz") == null && Address.Normal("") == null, "only http and https addresses count");
    var live = new Uri("https://daf.tiresia.xyz");
    Check(Address.Url(live, "#today").AbsoluteUri == "https://daf.tiresia.xyz/#today", "a route is a page of the app");
    Check(Address.Url(live, "/api/save").AbsoluteUri == "https://daf.tiresia.xyz/api/save" && Address.Url(live, "api/save").AbsoluteUri == "https://daf.tiresia.xyz/api/save", "a path is on the server");
    Check(Address.IsOurs(new Uri("https://daf.tiresia.xyz:443/#review"), live), "Daf's own origin is ours, its port said or not");
    Check(!Address.IsOurs(new Uri("http://daf.tiresia.xyz/"), live) && !Address.IsOurs(new Uri("https://daf.tiresia.xyz.evil.example/"), live), "another scheme or host isn't");
    Check(Address.IsOurs(new Uri("https://daf-app.example/#today"), live) && !Address.IsDaf(new Uri("https://daf-app.example/"), live), "the copy is ours, and isn't Daf's own origin");
    Check(Address.Route(new Uri("https://daf-app.example/#read/kk:1")) == "#read/kk:1" && Address.Route(new Uri("https://daf.tiresia.xyz/")) == null, "a page's route");

    // ---- links
    Check(Links.FirstLink("look at https://example.com/a?b=c and more") == "https://example.com/a?b=c", "the first link in some text");
    Check(Links.FirstLink("no link here") == null && Links.FirstLink(null) == null, "no link in text without one");
    var save = DafLink.Parse("daf://save?url=https%3A%2F%2Fexample.com%2Fx%3Fy%3D1&title=A+title&text=Some%20words");
    Check(save is { Kind: "save", Url: "https://example.com/x?y=1", Title: "A title", Text: "Some words" }, "daf://save gives its link, title and text", save?.ToString() ?? "null");
    var fromText = DafLink.Parse("daf://save?text=read%20https%3A%2F%2Fexample.com%2Fz%20later");
    Check(fromText?.Url == "https://example.com/z", "daf://save takes the link out of its text when there's no url", fromText?.ToString() ?? "null");
    Check(DafLink.Parse("daf://go/review")?.Route == "review" && DafLink.Parse("daf://go/book/abc%3A1")?.Route == "book/abc:1", "daf://go names a page of Daf");
    Check(DafLink.Parse("daf://go/") == null && DafLink.Parse("https://example.com") == null && DafLink.Parse("daf://other") == null, "anything else isn't a daf link");
    Check(DafLink.Find("\"C:\\Program Files\\Daf\\Daf.exe\" daf://go/stats")?.Route == "stats", "a daf link found in a command line");
    Check(DafLink.Find("--background") == null, "a command line without one");
    Check(Links.DeviceName("DESKTOP-4F2K9") == "windows-desktop-4f2k9", "this PC's device name", Links.DeviceName("DESKTOP-4F2K9"));
    Check(Links.DeviceName("Nate's Surface_Pro 9") == "windows-nates-surface-pro", "a PC's name made fit for Daf", Links.DeviceName("Nate's Surface_Pro 9"));
    Check(Links.DeviceName("") == "windows" && Links.DeviceName("éé") == "windows", "a PC with no usable name");
    Check(Links.DeviceName(new string('a', 40)).Length <= 24, "never longer than Daf takes");

    // ---- the device token, kept with DPAPI
    {
        var dir = Scratch();
        var file = Path.Join(dir, "token.bin");
        var store = new TokenStore(file);
        Check(store.Value == null, "no token at first");
        Check(store.Set("  secret-token-123 "), "a token is kept");
        Check(new TokenStore(file).Value == "secret-token-123", "and read back by the next start, trimmed");
        Check(!Encoding.UTF8.GetString(File.ReadAllBytes(file)).Contains("secret-token-123"), "the file doesn't hold it in the clear");
        Check(store.Set(null) && !File.Exists(file) && new TokenStore(file).Value == null, "forgetting it removes it");
        File.WriteAllBytes(file, [1, 2, 3]);
        Check(new TokenStore(file).Value == null, "a damaged file is no token");
        var memory = new TokenStore(null);
        Check(memory.Set("t") && memory.Value == "t", "the self-test's token stays in memory");
    }

    // ---- the widget
    {
        var w = Widget.Parse("""{"date":"2026-10-27","minutes":38.6,"goal":60,"year_day":19,"highlight":{"text":"A line","title":"A book"},"nightstand":[{"id":"1","title":"B"}]}""")!;
        Check(w.Short == "38′" && !w.Done && Math.Abs(w.Fraction - 38.6 / 60) < 1e-9, "38 minutes of 60", $"{w.Short} {w.Fraction}");
        Check(w.Line == "38 of 60 minutes today" && w.Subtitle == "Year 30, day 19", "its words", $"{w.Line} | {w.Subtitle}");
        Check(w.Today?.Text == "A line" && w.Nightstand?.Count == 1, "the highlight and the nightstand");
        var done = Widget.Parse("""{"date":"x","minutes":64,"goal":60,"year_day":19}""")!;
        Check(done.Done && done.Short == "64′ ✓" && done.Fraction == 1 && done.MetLine == "That's the hour." && done.Subtitle == "64 minutes today · Year 30, day 19", "the hour done", $"{done.Short} {done.Subtitle}");
        var week = Widget.Parse("""{"date":"x","minutes":20,"goal":60,"main":{"id":"g","kind":"pages","done":33,"target":200,"period":"week","period_label":"this week","text":"33 of 200 pages this week"}}""")!;
        Check(week.Short == "33/200" && week.Line == "33 of 200 pages this week" && week.Subtitle == "20 minutes today", "another main goal", $"{week.Short} | {week.Subtitle}");
        week.Main!.Met = true;
        Check(week.Done && week.MetLine == "That's this week's goal.", "another goal met");
        Check(Widget.Parse("not json") == null, "an answer that isn't the minutes");
    }

    // ---- the copy's files
    {
        Check(CopyStore.Key("/api/docs/kk%3Aabc") == CopyStore.Key("/api/docs/kk:abc"), "an address is the same file percent-encoded or not");
        Check(CopyStore.Key("/api/docs?where=inbox") != CopyStore.Key("/api/docs?where=later"), "the query counts");
        Check(CopyStore.AnyKey("/api/docs?where=library&tab=later&order=oldest&kind=article") == "/api/docs?_any&where=library&tab=later&kind=article&cat=&feed=", "a list's any-key keeps what it is, not its order",
            CopyStore.AnyKey("/api/docs?where=library&tab=later&order=oldest&kind=article") ?? "null");
        Check(CopyStore.AnyKey("/api/highlights?color=green") == "/api/highlights?_any" && CopyStore.AnyKey("/api/docs/123") == null && CopyStore.AnyKey("/api/docs") == null, "only lists have one");

        var store = new CopyStore(Scratch());
        Check(!store.Ready, "a new copy isn't ready");
        store.Store(Utf8("""{"items":[1]}"""), "application/json", "/api/docs?where=library&tab=inbox&order=newest");
        var other = store.Kept("/api/docs", "?where=library&tab=inbox&order=oldest");
        Check(other != null && File.ReadAllText(other).Contains("items"), "a list asked in another order finds the kept one");
        Check(store.Kept("/api/docs", "?where=feed") == null, "another list doesn't");
        store.Store(Utf8("""{"id":"kk:1"}"""), "application/json; charset=utf-8", "/api/docs/kk%3A1");
        var doc = store.Kept("/api/docs/kk:1", "?prefetch=1");
        Check(doc != null && CopyStore.TypeOf(doc) == "application/json; charset=utf-8", "an article answers its own path, any query, with its type");

        // three weeks
        var oldKept = store.DataFile("/api/kept-old");
        var oldGone = store.DataFile("/api/gone-old");
        var newGone = store.DataFile("/api/gone-new");
        store.Store(Utf8("1"), "text/plain", "/api/kept-old");
        store.Store(Utf8("2"), "text/plain", "/api/gone-old");
        store.Store(Utf8("3"), "text/plain", "/api/gone-new");
        File.SetLastWriteTimeUtc(oldKept, DateTime.UtcNow.AddDays(-30));
        File.SetLastWriteTimeUtc(oldGone, DateTime.UtcNow.AddDays(-22));
        var went = store.Prune(["/api/kept-old", "/api/docs/kk:1", "/api/docs?where=library&tab=inbox&order=newest", "/api/docs?_any&where=library&tab=inbox&kind=&cat=&feed="], DateTime.UtcNow);
        Check(went == 1 && File.Exists(oldKept) && !File.Exists(oldGone) && !File.Exists(oldGone + ".type") && File.Exists(newGone), "what nothing names goes after three weeks, and only then", $"{went} went");
        CopyStore.Touch(newGone);
        Check(File.GetLastWriteTimeUtc(newGone) > DateTime.UtcNow.AddMinutes(-1), "reading something starts its three weeks again");

        // pictures
        var article = Utf8("""{"id":"d1","thumb":"/api/thumb/ab.jpg","blocks":[{"t":"p","text":"x"},{"t":"img","src":"/api/img/1.png"},{"t":"img","src":"https://pics.example/2.jpg"},{"t":"img","src":"data:image/png;base64,AA"}]}""");
        var pics = CopyStore.Pictures(article);
        Check(pics.SequenceEqual(["/api/img/1.png", "https://pics.example/2.jpg", "data:image/png;base64,AA", "/api/thumb/ab.jpg"]), "an article's pictures and its thumbnail", string.Join(" ", pics));
        string Abs(string s) => s.StartsWith('/') ? "https://daf.tiresia.xyz" + s : s;
        store.Store(Utf8("png"), "image/png", "https://daf.tiresia.xyz/api/img/1.png");
        var local = JsonNode.Parse(store.LocalPictures(article, Abs))!["blocks"]!.AsArray();
        Check(local[1]!["src"]!.GetValue<string>() == "https://daf-app.example/__img/" + CopyStore.Key("https://daf.tiresia.xyz/api/img/1.png"), "a kept picture points at the copy");
        Check(local[2]!["src"]!.GetValue<string>() == "https://pics.example/2.jpg" && local[3]!["src"]!.GetValue<string>().StartsWith("data:"), "one not kept stays where it was");

        // the copy's own files
        CopyStore.Write(Path.Join(store.AppDir, "index.html"), Utf8("<html>"));
        CopyStore.Write(Path.Join(store.AppDir, "vendor", "x.js"), Utf8("x"));
        Check(store.Ready, "with index.html the copy is ready");
        Check(store.AppFile("/vendor/x.js").EndsWith(Path.Join("vendor", "x.js")), "a file of the page is its file");
        Check(store.AppFile("/").EndsWith("index.html") && store.AppFile("/no/such").EndsWith("index.html"), "any other path is the page");
        Check(store.AppFile("/../copy.json").EndsWith("index.html") && store.AppFile("/vendor/..%5C..%5Cx").EndsWith("index.html") && store.AppFile("/C:/Windows/win.ini").EndsWith("index.html"), "a path that leaves the copy is the page too");
    }

    // ---- the copy kept up to date, from a stand-in Daf
    {
        var files = new Dictionary<string, byte[]>
        {
            ["/index.html"] = Utf8("<!doctype html><title>Daf</title>"),
            ["/app.js"] = Utf8("console.log('daf')"),
            ["/fonts/Literata.woff2"] = [0, 1, 2, 3],
        };
        var version = "v1";
        var lie = false;
        var article = """{"id":"kk:1","kind":"pdf","status":"inbox","blocks":[{"t":"img","src":"/api/img/a.png"}]}""";
        var deleted = false;
        string? cookieSeen = null;
        using var daf = new Stub(r =>
        {
            var path = r.Path.Split('?')[0];
            if (path.StartsWith("/api/") && r.Headers.TryGetValue("Cookie", out var c)) cookieSeen = c;
            if (path == "/api/app-files")
                return Stub.Json(new JsonObject
                {
                    ["version"] = version,
                    ["files"] = new JsonArray(files.Select(f => (JsonNode)new JsonObject { ["path"] = f.Key, ["sha1"] = Sha1(f.Value), ["size"] = f.Value.Length }).ToArray()),
                }.ToJsonString());
            if (files.TryGetValue(Uri.UnescapeDataString(path), out var body)) return Stub.Bytes(lie && path == "/app.js" ? Utf8("tampered") : body, "application/octet-stream");
            switch (path)
            {
                case "/api/offline/plan":
                    return Stub.Json("""{"urls":["/api/today","/api/docs?where=library&tab=inbox&order=newest"],"docs":["kk:1"],"images":["/api/thumb/t.jpg"],"ebooks":["b1"]}""");
                case "/api/today": return Stub.Json("""{"counted":12}""");
                case "/api/docs": return Stub.Json("""{"items":[]}""");
                case "/api/docs/kk%3A1":
                case "/api/docs/kk:1": return deleted ? Stub.Json("""{"id":"kk:1","status":"deleted"}""") : Stub.Json(article);
                case "/api/docs/kk%3A1/pdf":
                case "/api/docs/kk:1/pdf": return Stub.Bytes(Utf8("%PDF-1.7"), "application/pdf");
                case "/api/docs/gone": return Stub.Json("{}", 404);
                case "/api/img/a.png": return Stub.Bytes(Utf8("png"), "image/png");
                case "/api/thumb/t.jpg": return Stub.Bytes(Utf8("jpg"), "image/jpeg");
                case "/api/ebooks/b1": return Stub.Json("""{"id":"b1","title":"The Book","format":"epub","size":4,"private":false}""");
                case "/api/ebooks/b1/file": return Stub.Bytes([9, 9, 9, 9], "application/epub+zip");
                case "/api/ebooks/b2": return Stub.Json("""{"id":"b2","title":"Secret","format":"epub","size":2,"private":true}""");
                case "/api/ebooks/b2/file": return Stub.Bytes([7, 7], "application/epub+zip");
                case "/api/cover/b1":
                case "/api/cover/b2": return Stub.Bytes(Utf8("cover"), "image/jpeg");
                case "/api/manga/books/m1": return Stub.Json("""{"name":"Vol. 1","pages":[{},{},{}],"series":{"id":"s1","name":"A Series"}}""");
                case "/api/manga/series/s1": return Stub.Json("""{"id":"s1"}""");
                case "/api/manga/prefs": return Stub.Json("{}");
                case "/api/manga/books/m1/pages/1":
                case "/api/manga/books/m1/pages/2":
                case "/api/manga/books/m1/pages/3": return Stub.Bytes(Utf8("page" + r.Path), "image/webp");
                case "/api/down": return Stub.Json("{}", 530);
                case "/api/echo":
                    return new Stub.Response(201, r.Body, "application/json", new Dictionary<string, string> { ["Set-Cookie"] = "daf=new; Path=/; HttpOnly", ["ETag"] = "\"e1\"" });
            }
            return Stub.Json("""{"detail":"no"}""", 404);
        });
        var http = new HttpClient(new SocketsHttpHandler { UseCookies = false });
        var keeper = new Keeper(Scratch(), http, () => daf.Base, () => Task.FromResult<string?>("daf=signed"), "Daf/0.1.0 (Windows shell)");

        Check(await keeper.RefreshScreens(), "the screens come the first time");
        Check(files.All(f => File.ReadAllBytes(Path.Join(keeper.Store.AppDir, f.Key.TrimStart('/').Replace('/', '\\'))).SequenceEqual(f.Value)) && keeper.Store.Ready, "every file of web/ is in the copy");
        var asked = daf.Count("/app.js");
        Check(!await keeper.RefreshScreens() && daf.Count("/app.js") == asked, "the same version asks for no file again");
        version = "v2";
        files["/app.js"] = Utf8("console.log('daf 2')");
        await keeper.RefreshScreens();
        Check(daf.Count("/app.js") == asked + 1 && daf.Count("/index.html") == 1, "a new version fetches only the file that changed");
        version = "v3";
        files["/app.js"] = Utf8("console.log('daf 3')");
        lie = true;
        var refused = false;
        try { await keeper.RefreshScreens(); } catch (InvalidDataException) { refused = true; }
        Check(refused && File.ReadAllText(Path.Join(keeper.Store.AppDir, "app.js")) == "console.log('daf 2')", "a file that doesn't match its hash is refused, and the old one stays");
        lie = false;
        Check(cookieSeen == null, "the screens go without the sign-in");

        var said = await keeper.KeepData();
        Check(said.StartsWith("3 kept"), "the plan's lists and article are kept", said);
        Check(cookieSeen == "daf=signed", "the data goes with the window's sign-in");
        Check(keeper.Store.Kept("/api/today", "") != null && keeper.Store.Kept("/api/docs", "?where=library&tab=inbox&order=oldest") != null, "the plan's lists answer offline");
        Check(keeper.Store.Has("/api/docs/kk:1") && keeper.Store.Has("/api/docs/kk%3A1/pdf"), "the article and its PDF");
        Check(keeper.Store.Has(daf.Base.GetLeftPart(UriPartial.Authority) + "/api/thumb/t.jpg"), "the plan's pictures");
        Check(keeper.Store.Has("/api/ebooks/b1/file") && keeper.Store.Has("/api/cover/b1") && keeper.State.Books["b1"].Title == "The Book", "the book being read, its file and its cover");
        var bookAsks = daf.Count("/api/ebooks/b1/file");
        await keeper.KeepData();
        Check(daf.Count("/api/ebooks/b1/file") == bookAsks, "a book whose size didn't change isn't fetched again");

        // the page's calls
        var list = (JsonObject)await keeper.Answer(new JsonObject { ["op"] = "list" });
        Check(list["app"]?["ready"]?.GetValue<bool>() == true && list["books"]!.AsArray().Count == 1 && list["docs"]!.AsArray().Count == 1 && list["docs"]![0]!["pinned"]!.GetValue<bool>() == false, "list: the copy, the book being read, the plan's article", list.ToJsonString());
        Check(((JsonObject)await keeper.Answer(new JsonObject { ["op"] = "has", ["id"] = "b1" }))["has"]!.GetValue<bool>(), "has: a book on this PC");
        await keeper.Answer(new JsonObject { ["op"] = "keep", ["id"] = "b2" });
        list = keeper.List();
        var b2 = list["books"]!.AsArray().FirstOrDefault(b => b!["id"]!.GetValue<string>() == "b2");
        Check(b2?["kept"]?.GetValue<bool>() == true && b2["title"]!.GetValue<string>() == "Private reading", "keep: a book by hand, a private one's title never shown", list.ToJsonString());
        await keeper.Answer(new JsonObject { ["op"] = "keep", ["id"] = "b2", ["on"] = false });
        Check(!keeper.Store.Has("/api/ebooks/b2/file") && !keeper.State.Books.ContainsKey("b2"), "keep off: a book nothing else wants goes at once");
        await keeper.Answer(new JsonObject { ["op"] = "doc", ["id"] = "kk:1" });
        Check(keeper.State.Docs.Contains("kk:1") && keeper.Store.Has(daf.Base.GetLeftPart(UriPartial.Authority) + "/api/img/a.png"), "doc: an article kept by hand, with its pictures");
        var goneSaid = "";
        try { await keeper.Answer(new JsonObject { ["op"] = "doc", ["id"] = "gone" }); } catch (InvalidOperationException e) { goneSaid = e.Message; }
        Check(goneSaid == "Daf doesn't have this article any more.", "doc: one Daf doesn't have says so", goneSaid);
        deleted = true;
        await keeper.KeepData();
        Check(!keeper.State.Docs.Contains("kk:1"), "an article deleted in Daf leaves what's kept by hand");
        deleted = false;
        await keeper.Answer(new JsonObject { ["op"] = "manga", ["id"] = "m1", ["size"] = 9000 });
        await keeper.Downloads;
        var m1 = keeper.State.Mangas["m1"];
        Check(m1 is { State: "done", Done: 3, Total: 3, Series: "A Series", Size: 2400 } && keeper.Store.Has("/api/manga/books/m1/pages/3") && keeper.Store.Has("/api/manga/series/s1"),
            "manga: a volume's pages, its series, at a size Daf allows", $"{m1.State} {m1.Done}/{m1.Total} {m1.Size}");
        Check(daf.Asked.Any(a => a.Path == "/api/manga/books/m1/pages/1?size=2400"), "pages asked at that size");
        await keeper.Answer(new JsonObject { ["op"] = "manga", ["id"] = "m1", ["on"] = false });
        Check(!keeper.State.Mangas.ContainsKey("m1") && !keeper.Store.Has("/api/manga/books/m1/pages/2"), "manga off: the volume goes");
        var sync = (JsonObject)await keeper.Answer(new JsonObject { ["op"] = "sync" });
        Check(sync["said"]?.GetValue<string>().Contains("kept") == true && sync["synced"]!.GetValue<long>() > 0, "sync: everything now, and says when", sync["said"]?.ToString() ?? "");

        // the copy's /api/ on to Daf
        var echo = await keeper.Forward("POST", "/api/echo", [new("Content-Type", "application/json"), new("X-Daf-Op", "op1"), new("Cookie", "not=this")], Utf8("""{"a":1}"""));
        var sent = daf.Asked.Last(a => a.Path == "/api/echo");
        Check(echo is { Status: 201 } && Encoding.UTF8.GetString(echo.Data) == """{"a":1}""" && sent.Headers["X-Daf-Op"] == "op1" && sent.Headers["Cookie"] == "daf=signed" && sent.Headers["Content-Type"].StartsWith("application/json"),
            "a write goes on with its body, its headers and the window's sign-in, not the copy's cookie");
        Check(echo!.SetCookies.SingleOrDefault() == "daf=new; Path=/; HttpOnly" && echo.Headers.GetValueOrDefault("ETag") == "\"e1\"", "the sign-in Daf sets comes back, and the headers that matter");
        var got = await keeper.Forward("GET", "/api/docs?where=feed&order=newest", [], null);
        Check(got?.Status == 200 && keeper.Store.Kept("/api/docs", "?where=feed&order=oldest") != null, "a GET that came is kept for later");
        Check(await keeper.Forward("GET", "/api/down", [], null) == null, "Cloudflare saying Daf is down is no answer");
        var nowhere = new Keeper(Scratch(), http, () => new Uri("http://127.0.0.1:9"), () => Task.FromResult<string?>(null), "x");
        Check(await nowhere.Forward("GET", "/api/today", [], null) == null, "a Daf that doesn't answer is no answer");
        Check((await nowhere.Refresh()).StartsWith("Daf didn't answer"), "and refreshing says so");
    }

    // ---- the token's endpoints
    {
        string? auth = null;
        string? posted = null;
        var known = "good";
        using var daf = new Stub(r =>
        {
            auth = r.Headers.GetValueOrDefault("Authorization");
            if (auth != "Bearer " + known) return Stub.Json("""{"detail":"Not signed in"}""", 401);
            return r.Path.Split('?')[0] switch
            {
                "/api/phone/widget" => Stub.Json("""{"date":"2026-10-27","minutes":5,"goal":60}"""),
                "/api/phone/feed-news" => Stub.Json("""{"cursor":7,"feeds":1,"items":[{"id":"f1","title":"A post","source":"A blog","route":"#read/f1"}]}"""),
                "/api/save" => (posted = Encoding.UTF8.GetString(r.Body)) is not null ? Stub.Json("""{"ok":true}""") : Stub.Json("{}", 500),
                _ => Stub.Json("""{"detail":"Nothing here"}""", 404),
            };
        });
        string? token = null;
        var client = new DafClient(new HttpClient(), () => daf.Base, () => token, "Daf/0.1.0 (Windows shell)");
        var kind = "";
        try { await client.GetWidget(); } catch (DafFailure f) { kind = f.Kind; }
        Check(kind == "token" && daf.Asked.Count == 0, "no token: nothing is asked");
        token = "good";
        var w = await client.GetWidget();
        Check(w.Minutes == 5 && auth == "Bearer good", "the minutes, with the token");
        var news = await client.GetFeedNews(-1);
        Check(news.Cursor == 7 && news.Items.Single().Route == "#read/f1" && daf.Asked.Last().Path == "/api/phone/feed-news", "new posts, first without a cursor");
        await client.GetFeedNews(7);
        Check(daf.Asked.Last().Path == "/api/phone/feed-news?cursor=7", "then from the cursor");
        await client.Save("https://example.com/a", "A", null);
        Check(posted != null && JsonNode.Parse(posted)?["url"]?.GetValue<string>() == "https://example.com/a" && JsonNode.Parse(posted)?["text"] == null, "Save sends the link and its title", posted ?? "");
        known = "other";
        kind = "";
        try { await client.GetWidget(); } catch (DafFailure f) { kind = f.Kind; }
        Check(kind == "unknown", "a token Daf no longer knows says so");
        try { await client.GetWidget(); } catch (DafFailure f) { kind = f.Kind; }
        var nowhere = new DafClient(new HttpClient(), () => new Uri("http://127.0.0.1:9"), () => "t", "x");
        try { await nowhere.GetWidget(); } catch (DafFailure f) { kind = f.Kind; }
        Check(kind == "unreachable", "a Daf that doesn't answer");
    }
}
catch (Exception e)
{
    Check(false, "the tests ran to the end", e.ToString());
}
finally
{
    foreach (var dir in scratch)
        try { Directory.Delete(dir, true); } catch (Exception) { }
}

Console.WriteLine(failures == 0 ? "every check held" : $"{failures} failed");
return failures == 0 ? 0 : 1;
