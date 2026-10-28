using System.Text;
using Daf.Core;
using Microsoft.UI.Dispatching;
using Microsoft.Web.WebView2.Core;
using Microsoft.Windows.System.Power;
using Windows.Networking.Connectivity;
using Windows.Storage.Streams;

namespace Daf;

/// <summary>
/// Daf with no connection (docs/SHELL.md, "Offline"), the Mac's way (mac/Daf/LocalCopy.swift):
/// the app keeps its own copy of Daf's screens and of the data the server says to keep
/// (Keeper), and when Daf can't be reached the window loads that copy from
/// https://daf-app.example/ at the same page. WebView2 answers that address from here
/// (WebResourceRequested): the page's files from the copy, /api/ through to Daf with the
/// window's sign-in, or from what was kept when Daf doesn't answer. Online it is the live
/// site, as before (videos play only on a real address). Coming back, what was done
/// offline goes first, then the live site again.
/// </summary>
static class LocalCopy
{
    /// <summary>The windows are on the copy now (Daf didn't answer).</summary>
    public static bool Active { get; set; }

    static DispatcherQueueTimer? reconnect;

    /// <summary>A page of Daf on the copy: https://daf-app.example/#today.</summary>
    public static string Url(string? route) =>
        Address.CopyOrigin + "/" + (string.IsNullOrEmpty(route) ? "" : route.StartsWith('#') ? route : "#" + route);

    // ---- the window's sign-in -------------------------------------------------------------------

    /// <summary>The window's cookies for Daf's address, as a request header, for the copy's requests to Daf.</summary>
    public static async Task<string?> CookieHeader()
    {
        var done = new TaskCompletionSource<string?>();
        var queue = App.Queue;
        if (queue == null) return null;
        queue.TryEnqueue(async () =>
        {
            try
            {
                var core = ShellWindow.All.Select(w => w.Core).FirstOrDefault(c => c != null);
                if (core == null) { done.TrySetResult(null); return; }
                var cookies = await core.CookieManager.GetCookiesAsync(Settings.BaseUrl.AbsoluteUri);
                done.TrySetResult(cookies.Count == 0 ? null : string.Join("; ", cookies.Select(c => $"{c.Name}={c.Value}")));
            }
            catch (Exception e) { done.TrySetResult(null); Log.Write($"the window's sign-in: {e.Message}"); }
        });
        return await done.Task;
    }

    /// <summary>The sign-in Daf set while the copy was in the window (signing in there) goes where the live site finds it.</summary>
    static void TakeCookies(CoreWebView2 core, IEnumerable<string> setCookies)
    {
        foreach (var header in setCookies)
        {
            var parts = header.Split(';').Select(p => p.Trim()).ToList();
            var eq = parts[0].IndexOf('=');
            if (eq <= 0) continue;
            var attributes = parts.Skip(1).Select(p => (Name: p.Split('=')[0].Trim().ToLowerInvariant(), Value: p.Contains('=') ? p[(p.IndexOf('=') + 1)..].Trim() : "")).ToList();
            var path = attributes.FirstOrDefault(a => a.Name == "path").Value is { Length: > 0 } given ? given : "/";
            var c = core.CookieManager.CreateCookie(parts[0][..eq], parts[0][(eq + 1)..], Settings.BaseUrl.Host, path);
            foreach (var (name, value) in attributes)
            {
                if (name == "httponly") c.IsHttpOnly = true;
                else if (name == "secure") c.IsSecure = true;
                else if (name == "max-age" && long.TryParse(value, out var age)) c.Expires = DateTimeOffset.UtcNow.AddSeconds(age).ToUnixTimeSeconds();
                else if (name == "expires" && DateTimeOffset.TryParse(value, out var at)) c.Expires = at.ToUnixTimeSeconds();
            }
            core.CookieManager.AddOrUpdateCookie(c);
        }
    }

    // ---- the page's settings, carried to the copy -------------------------------------------------

    static string SnapshotFile => Path.Join(App.Keeper.Store.Root, "localStorage.json");

    public static void KeepSnapshot(string json)
    {
        try { CopyStore.Write(SnapshotFile, Encoding.UTF8.GetBytes(json)); }
        catch (Exception e) { Log.Write($"the page's settings: {e.Message}"); }
    }

    /// <summary>Run first in the copy's page: the live page's settings (Scripts.Seed).</summary>
    public static string SeedScript()
    {
        var json = "{}";
        long at = 0;
        try
        {
            if (File.Exists(SnapshotFile))
            {
                json = File.ReadAllText(SnapshotFile);
                at = new DateTimeOffset(File.GetLastWriteTimeUtc(SnapshotFile)).ToUnixTimeMilliseconds();
            }
        }
        catch (Exception) { }
        return Scripts.Seed(json.TrimStart().StartsWith('{') ? json : "{}", at);
    }

    // ---- keeping it up to date ---------------------------------------------------------------------

    /// <summary>The live site answered: the windows are on it again.</summary>
    public static void WentLive()
    {
        Active = false;
        reconnect?.Stop();
    }

    /// <summary>Daf's screens at each load, its data every few hours (Keeper.Refresh), in the background.</summary>
    public static void KeepUpToDate()
    {
        _ = Task.Run(async () =>
        {
            var said = await App.Keeper.Refresh(data: false);
            if (said.StartsWith("Daf didn't")) Log.Write($"the copy for no connection: {said}");
        });
    }

    // ---- https://daf-app.example/ ---------------------------------------------------------------------

    public static void Attach(CoreWebView2 core, CoreWebView2Environment environment)
    {
        core.AddWebResourceRequestedFilter(Address.CopyOrigin + "/*", CoreWebView2WebResourceContext.All);
        core.WebResourceRequested += async (sender, e) =>
        {
            if (!Uri.TryCreate(e.Request.Uri, UriKind.Absolute, out var url) || !Address.IsCopy(url)) return;
            var deferral = e.GetDeferral();
            try
            {
                if (await Answer(sender, environment, e.Request, url) is { } answer) e.Response = answer;
            }
            catch (Exception x)
            {
                Log.Write($"the copy could not answer {url.AbsolutePath}: {x.Message}");
                e.Response = Respond(environment, 500, Encoding.UTF8.GetBytes(x.Message), "text/plain; charset=utf-8");
            }
            finally { deferral.Complete(); }
        };
    }

    /// <summary>
    /// The copy's answer, or null to let the request go on to the network, where
    /// daf-app.example doesn't exist: a write Daf can't take fails as a lost connection does,
    /// so the page's outbox keeps it.
    /// </summary>
    static async Task<CoreWebView2WebResourceResponse?> Answer(CoreWebView2 core, CoreWebView2Environment environment, CoreWebView2WebResourceRequest request, Uri url)
    {
        var store = App.Keeper.Store;
        var path = url.AbsolutePath;
        if (path.StartsWith("/__img/"))
        {
            var f = Path.Join(store.DataDir, Path.GetFileName(path["/__img/".Length..]));
            return File.Exists(f) ? Respond(environment, 200, await File.ReadAllBytesAsync(f), CopyStore.TypeOf(f, "image/jpeg")) : Respond(environment, 404, [], "text/plain");
        }
        if (!path.StartsWith("/api/"))
        {
            var file = store.AppFile(Uri.UnescapeDataString(path));
            return Respond(environment, 200, await File.ReadAllBytesAsync(file), AppScheme(Path.GetExtension(file)));
        }

        var method = request.Method.ToUpperInvariant();
        var query = url.Query;
        var found = method == "GET" ? store.Kept(path, query) : null;
        if (Active && found != null) return FromKept(environment, store, path, found);
        byte[]? body = null;
        if (request.Content != null)
        {
            using var stream = request.Content.AsStreamForRead();
            using var ms = new MemoryStream();
            await stream.CopyToAsync(ms);
            body = ms.ToArray();
        }
        var headers = request.Headers.Select(h => new KeyValuePair<string, string>(h.Key, h.Value)).ToList();
        var got = await App.Keeper.Forward(method, url.PathAndQuery, headers, body);
        if (got == null) return found != null ? FromKept(environment, store, path, found) : null;
        if (got.SetCookies.Count > 0) TakeCookies(core, got.SetCookies);
        var extra = string.Concat(got.Headers.Select(h => $"\r\n{h.Key}: {h.Value}"));
        return Respond(environment, got.Status, got.Data, got.Type, extra);
    }

    /// <summary>What was kept, with an article's pictures pointed at their kept copies; read now, so it stays three weeks more.</summary>
    static CoreWebView2WebResourceResponse FromKept(CoreWebView2Environment environment, CopyStore store, string path, string file)
    {
        CopyStore.Touch(file);
        var data = File.ReadAllBytes(file);
        if (path.StartsWith("/api/docs/")) data = store.LocalPictures(data, App.Keeper.Absolute);
        return Respond(environment, 200, data, CopyStore.TypeOf(file), "\r\nX-Daf-Offline: 1");
    }

    static CoreWebView2WebResourceResponse Respond(CoreWebView2Environment environment, int status, byte[] data, string type, string extra = "")
    {
        var reason = status switch { 200 => "OK", 201 => "Created", 204 => "No Content", 400 => "Bad Request", 401 => "Unauthorized", 403 => "Forbidden", 404 => "Not Found", _ => "Status" };
        return environment.CreateWebResourceResponse(new MemoryStream(data).AsRandomAccessStream(), status, reason, $"Content-Type: {type}\r\nCache-Control: no-cache{extra}");
    }

    static string AppScheme(string extension) => extension.TrimStart('.').ToLowerInvariant() switch
    {
        "html" or "htm" => "text/html; charset=utf-8",
        "js" or "mjs" => "text/javascript; charset=utf-8",
        "css" => "text/css; charset=utf-8",
        "json" or "map" => "application/json",
        "webmanifest" => "application/manifest+json",
        "svg" => "image/svg+xml",
        "png" => "image/png",
        "jpg" or "jpeg" => "image/jpeg",
        "webp" => "image/webp",
        "gif" => "image/gif",
        "ico" => "image/x-icon",
        "woff2" => "font/woff2",
        "woff" => "font/woff",
        "ttf" => "font/ttf",
        "otf" => "font/otf",
        "wasm" => "application/wasm",
        "mp3" => "audio/mpeg",
        "txt" => "text/plain; charset=utf-8",
        _ => "application/octet-stream",
    };

    // ---- coming back -------------------------------------------------------------------------------

    /// <summary>On the copy: every 30 seconds, when the network changes and when the PC wakes, ask Daf if it's back.</summary>
    public static void Watch()
    {
        var queue = App.Queue;
        if (queue == null) return;
        if (reconnect == null)
        {
            reconnect = queue.CreateTimer();
            reconnect.Interval = TimeSpan.FromSeconds(30);
            reconnect.IsRepeating = true;
            reconnect.Tick += async (_, _) => await Check();
            NetworkInformation.NetworkStatusChanged += _ => queue.TryEnqueue(async () => await Check());
            PowerManager.SystemSuspendStatusChanged += (_, _) =>
            {
                if (PowerManager.SystemSuspendStatus != SystemSuspendStatus.Entering) queue.TryEnqueue(async () => await Check());
            };
        }
        reconnect.Start();
    }

    /// <summary>When Daf answers, each window sends what was done offline and goes back to the live site.</summary>
    public static async Task<bool> Check()
    {
        if (!Active) { reconnect?.Stop(); return false; }
        try
        {
            using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(5));
            using var r = await App.Http.GetAsync(Address.Url(Settings.BaseUrl, "/api/health"), timeout.Token);
            if (!r.IsSuccessStatusCode) return false;
        }
        catch (Exception) { return false; }
        foreach (var w in ShellWindow.All.ToList()) await w.GoLive();
        return true;
    }
}
