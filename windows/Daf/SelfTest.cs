using System.Diagnostics;
using System.Text;
using System.Text.Encodings.Web;
using System.Text.Json;
using System.Text.Json.Nodes;
using Daf.Core;
using Microsoft.UI.Windowing;

namespace Daf;

/// <summary>
/// The self-test (windows/selftest.ps1): the real app on a sandbox Daf made from this
/// checkout, never the real one, with no dialog for anyone to answer, checked from inside
/// the page and from outside it. Saving and sharing go to --save-dir; --server-control is
/// where it asks selftest.ps1 to stop and start the sandbox, for the copy. The results go
/// to --out, and the exit code says whether every check held. The Mac's is mac/SelfTest.
/// </summary>
static class SelfTest
{
    sealed record Check(string Name, bool Ok, string Detail);
    static readonly List<Check> Checks = [];
    static readonly object Gate = new();

    // a picture of one pixel, as Share as image would send one
    const string Png = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==";

    public static void Start()
    {
        // never longer than six minutes, whatever hangs
        _ = Task.Delay(TimeSpan.FromMinutes(6)).ContinueWith(_ => Finish("it took more than six minutes"));
    }

    static void Add(string name, bool ok, string detail = "")
    {
        lock (Gate) Checks.Add(new Check(name, ok, detail));
    }

    static string Js(string s) => J.Quote(s);

    public static async Task Run(ShellWindow w)
    {
        try
        {
            var saveDir = App.Options.SaveDir ?? throw new Exception("no --save-dir");
            var signedIn = await Until(w, "window.dafState && dafState().signedIn", TimeSpan.FromSeconds(90));
            Add("the page signs in on the sandbox Daf", J.Bool(signedIn), $"at {w.Source}");
            if (!J.Bool(signedIn)) { Finish(); return; }

            // ---- the page knows the shell (docs/SHELL.md §1, §2)
            var agent = J.Text(await w.Evaluate("navigator.userAgent")) ?? "";
            Add("the user agent ends with the shell's name", agent.EndsWith($"Daf/{App.Version} (Windows shell)"), agent);
            Add("shell.js marks the page shell-windows", J.Bool(await w.Evaluate("document.documentElement.classList.contains('shell') && document.documentElement.classList.contains('shell-windows')")));
            var platform = J.Text(await w.Evaluate("window.dafShell && dafShell.platform + ' ' + dafShell.version"));
            Add("window.dafShell is the Windows shell's", platform == $"windows {App.Version}", platform ?? "none");
            var caps = (await w.Evaluate("['share','download','openExternal','alerts','fullscreen','offline','bars','haptic','media','screen','reading','ink'].map(c => dafShell.can(c))"))?.ToJsonString();
            Add("dafShell.can says what Windows answers, and not the phone's", caps == "[true,true,true,true,true,true,true,false,false,false,false,false]", caps ?? "");
            Add("the page has its commands for the menus", J.Bool(await w.Evaluate("typeof window.dafCommand === 'function' && typeof window.dafState === 'function' && typeof window.dafBack === 'function'")));

            // ---- the title bar in the page's colour
            var pageBg = J.Text(await w.Evaluate(
                "(() => { const x = document.createElement('canvas').getContext('2d'); x.fillStyle = getComputedStyle(document.documentElement).getPropertyValue('--bg').trim(); x.fillRect(0, 0, 1, 1); return '#' + [...x.getImageData(0, 0, 1, 1).data.slice(0, 3)].map(v => v.toString(16).padStart(2, '0')).join(''); })()"));
            var said = await Until(() => Hex(w) == pageBg, TimeSpan.FromSeconds(5));
            Add("the title bar takes the page's own colour at load", said, $"page {pageBg}, title bar {Hex(w)}");
            Add("bars: a colour from the page", J.Bool(await w.Evaluate("dafShell.bars({ bg: '#203040', dark: true })")) && Hex(w) == "#203040" && w.BarDark);
            await w.Evaluate("window.dispatchEvent(new CustomEvent('daf-theme', { detail: { bg: '#f0e8d8', dark: false } })), true");
            Add("the title bar follows the theme when it changes", await Until(() => Hex(w) == "#f0e8d8" && !w.BarDark, TimeSpan.FromSeconds(3)), Hex(w));
            Add("bars: a colour it can't read is refused", !J.Bool(await w.Evaluate("dafShell.bars({ bg: 'not a colour', dark: false })")));
            await w.Evaluate($"dafShell.bars({{ bg: {Js(pageBg ?? "#ffffff")}, dark: document.documentElement.dataset.mode === 'dark' }})");

            // ---- the menus and the shell's keys run the page's commands (docs/SHELL.md §3)
            await w.Run("go:review");
            Add("View › Review goes there", J.Bool(await Until(w, "location.hash === '#review'", TimeSpan.FromSeconds(5))), J.Text(await w.Evaluate("location.hash")) ?? "");
            await w.Press("3", "Digit3", 0x33, 2);
            Add("Ctrl+3 goes to the Library, once the page left it alone", J.Bool(await Until(w, "location.hash === '#library'", TimeSpan.FromSeconds(5))), J.Text(await w.Evaluate("location.hash")) ?? "");
            await w.UpdateMenus();
            Add("the Reader items are greyed away from a reader", !w.MenuEnabled("highlight") && !w.MenuEnabled("bookmark"));
            await w.Press("k", "KeyK", 0x4B, 2);
            var palette = J.Bool(await Until(w, "!!document.querySelector('#palette') && !document.querySelector('#palette').hidden", TimeSpan.FromSeconds(3)));
            Add("Ctrl+K is the page's own search", palette && !Menus.Ran.Contains("search"));

            // ---- Back: whatever is in front closes first (the search just opened), then the page before
            var paletteOpen = J.Bool(await Until(w, "!!document.querySelector('#palette') && !document.querySelector('#palette').hidden", TimeSpan.FromSeconds(3)));
            w.Back();
            var closed = J.Bool(await Until(w, "document.querySelector('#palette').hidden", TimeSpan.FromSeconds(3)));
            Add("Back closes search before going back", paletteOpen && closed && J.Text(await w.Evaluate("location.hash")) == "#library");
            w.Back();
            Add("then goes back a page", J.Bool(await Until(w, "location.hash === '#review'", TimeSpan.FromSeconds(3))), J.Text(await w.Evaluate("location.hash")) ?? "");
            await w.Click("back");
            Add("the mouse's Back button goes back through the page", J.Bool(await Until(w, "location.hash !== '#review'", TimeSpan.FromSeconds(3))), J.Text(await w.Evaluate("location.hash")) ?? "");

            // ---- hidden means hidden (docs/SHELL.md §5)
            Add("the page is visible in a window in front", J.Text(await w.Evaluate("document.visibilityState")) == "visible");
            (w.AppWindow.Presenter as OverlappedPresenter)?.Minimize();
            var hidden = J.Bool(await Until(w, "document.visibilityState === 'hidden'", TimeSpan.FromSeconds(5)));
            Add("a minimized window's page is hidden, so no minutes count", hidden, J.Text(await w.Evaluate("document.visibilityState")) ?? "");
            w.Bring();
            Add("and visible again when it comes back", J.Bool(await Until(w, "document.visibilityState === 'visible'", TimeSpan.FromSeconds(5))));

            // ---- only Daf in the window
            await w.Evaluate("location.assign('https://example.com/elsewhere'), true");
            await Task.Delay(1000);
            Add("a link elsewhere opens in the browser, not in the window",
                Outside.Saw("https://example.com/elsewhere") && w.Source is { } s1 && Address.IsDaf(s1, Settings.BaseUrl), w.Source?.AbsoluteUri ?? "");
            await w.Evaluate("window.open('https://example.com/new-window'), true");
            Add("target=_blank elsewhere goes to the browser too", await Until(() => Outside.Saw("https://example.com/new-window"), TimeSpan.FromSeconds(3)));
            await w.Evaluate("(() => { const a = document.createElement('a'); a.href = 'obsidian://open?vault=Daf'; document.body.appendChild(a); a.click(); a.remove(); return true; })()");
            Add("obsidian:// goes to Obsidian", await Until(() => Outside.Saw("obsidian://open?vault=Daf"), TimeSpan.FromSeconds(3)));
            Add("openExternal opens the browser", J.Bool(await w.Evaluate("dafShell.openExternal('https://example.com/help')")) && Outside.Saw("https://example.com/help"));
            Add("openExternal refuses other kinds of address", !J.Bool(await w.Evaluate("dafShell.openExternal('file:///C:/Windows/win.ini')")));
            var before = ShellWindow.All.Count;
            await w.Evaluate("window.open(location.origin + '/api/health'), true");
            var opened = await Until(() => ShellWindow.All.Count == before + 1, TimeSpan.FromSeconds(5));
            var file = ShellWindow.All.LastOrDefault();
            Add("Daf's own file opens in a window of its own", opened && file?.Start?.AbsolutePath == "/api/health", file?.Start?.AbsoluteUri ?? "none");
            if (opened && file != null && file != w) file.Close();

            // ---- saving: the save dialog (here, --save-dir)
            var downloaded = J.Bool(await w.Evaluate("dafShell.download({ name: 'Self-test.md', mime: 'text/markdown', base64: btoa('# Saved\\n') })"));
            var saved = Path.Join(saveDir, "Self-test.md");
            Add("dafShell.download saves the page's bytes", downloaded && File.Exists(saved) && await File.ReadAllTextAsync(saved) == "# Saved\n");
            await w.Evaluate("(() => { const a = document.createElement('a'); a.href = '/api/health'; a.download = 'Self-test health.json'; document.body.appendChild(a); a.click(); a.remove(); return true; })()");
            var health = Path.Join(saveDir, "Self-test health.json");
            Add("an <a download> link goes to the save dialog, with the window's sign-in",
                await Until(() => Finished(health), TimeSpan.FromSeconds(15)) && (await File.ReadAllTextAsync(health)).Contains("\"ok\""));
            await w.Evaluate("(() => { const a = document.createElement('a'); a.href = URL.createObjectURL(new Blob(['blob bytes'], { type: 'text/plain' })); a.download = 'Self-test blob.txt'; document.body.appendChild(a); a.click(); a.remove(); return true; })()");
            var blob = Path.Join(saveDir, "Self-test blob.txt");
            Add("a blob: link is saved too (Share as image's Download)", await Until(() => Finished(blob), TimeSpan.FromSeconds(15)) && await File.ReadAllTextAsync(blob) == "blob bytes");
            var count = Finished();
            Add("dafShell.download(url) fetches it with the sign-in", J.Bool(await w.Evaluate("dafShell.download('/api/health')")) && await Until(() => Finished() > count, TimeSpan.FromSeconds(15)));

            // ---- the share sheet
            Add("share has a picture ready for the share sheet",
                J.Bool(await w.Evaluate($"dafShell.share({{ text: 'From Daf', png: {Js(Png)}, name: 'Self-test card' }})")) && File.Exists(Path.Join(saveDir, "shared-Self-test card.png")));
            Add("share with nothing to share is false", !J.Bool(await w.Evaluate("dafShell.share({})")));
            Add("navigator.share and canShare reach it (Share as image)",
                J.Bool(await w.Evaluate("navigator.canShare({ files: [new File([new Uint8Array([1])], 'x.png', { type: 'image/png' })] }) && navigator.share({ text: 'Daf' }).then(() => true)")));

            // ---- the manga reader's full screen
            Add("fullscreen: the window goes full screen", J.Bool(await w.Evaluate("dafShell.fullscreen()")) && w.IsFullScreen);
            Add("and the same again leaves it", !J.Bool(await w.Evaluate("dafShell.fullscreen()")) && !w.IsFullScreen);

            // ---- the device token, today's minutes, the notification area
            var token = await Until(() => App.Token.Value != null, TimeSpan.FromSeconds(30));
            Add("signed in, the PC makes its own device token", token, Links.DeviceName(Environment.MachineName));
            await Today.Refresh();
            Add("today's minutes come with the token", Today.Last != null && Today.Problem == null, Today.Problem ?? $"{Today.Last?.Line}");
            var taskbar = Win32.FindWindow("Shell_TrayWnd", null) != IntPtr.Zero;
            Add("the ring is in the notification area", Tray.Added || !taskbar, taskbar ? (Tray.Added ? "added" : "Windows refused it") : "no taskbar in this session");
            Add("its tip says the minutes", Tray.Tip.Contains("minutes") || Tray.Tip.Contains("goal"), Tray.Tip);
            TodayPanel.Toggle();
            var panel = await Until(() => TodayPanel.IsOpen, TimeSpan.FromSeconds(3));
            Add("a click shows the ring and the day", panel && (TodayPanel.Said.Contains("minutes") || TodayPanel.Said.Contains("goal")), TodayPanel.Said);
            TodayPanel.Dismiss();
            Add("alerts: Windows is asked, and the page hears whether Daf may notify", J.Text(await w.Evaluate("dafShell.alerts().then(x => typeof x)")) == "boolean");

            // ---- daf:// links: here, and handed over by a second start of Daf
            App.Handle(DafLink.Parse("daf://save?url=https%3A%2F%2Fexample.com%2Fsaved-from-windows&title=Self-test")!);
            Add("daf://save saves the link to the Library", await Until(() => { lock (SaveLink.Saved) return SaveLink.Saved.Contains("https://example.com/saved-from-windows"); }, TimeSpan.FromSeconds(15)));
            var second = Process.Start(new ProcessStartInfo(Environment.ProcessPath!) { ArgumentList = { "--data", App.DataDir, "daf://go/stats" }, UseShellExecute = false });
            var went = J.Bool(await Until(w, "location.hash === '#stats'", TimeSpan.FromSeconds(30)));
            var left = false;
            if (second != null)
            {
                using var wait = new CancellationTokenSource(TimeSpan.FromSeconds(10));
                try { await second.WaitForExitAsync(wait.Token); left = true; } catch (OperationCanceledException) { }
            }
            Add("a second start hands its daf:// link to the Daf running, and leaves", went && left && ShellWindow.All.Count == 1,
                $"{J.Text(await w.Evaluate("location.hash"))}, second {(left ? "left" : "still running")}");

            // ---- Settings
            SettingsWindow.Show();
            Add("Settings opens", SettingsWindow.IsOpen);
            SettingsWindow.CloseIt();
            await w.Capture(Path.Join(saveDir, "window.png"));

            // ---- what's kept for no connection
            var ready = await Until(() => App.Keeper.Store.Ready && App.Keeper.Copy.At > 0, TimeSpan.FromSeconds(120));
            var files = Directory.Exists(App.Keeper.Store.AppDir) ? Directory.EnumerateFiles(App.Keeper.Store.AppDir, "*", SearchOption.AllDirectories).Count() : 0;
            Add("the copy has every file of Daf's screens", ready && files == App.Keeper.Copy.Hashes.Count && files > 10, $"{files} files");
            var list = await w.Evaluate("dafShell.offline({ op: 'sync' })");
            Add("offline sync keeps what the plan names", J.Text(list?["said"])?.Contains("kept") == true && J.Bool(list?["app"]?["ready"]), J.Text(list?["said"]) ?? list?.ToJsonString() ?? "");
            Add("offline has: no book kept that wasn't asked for", (await w.Evaluate("dafShell.offline({ op: 'has', id: 'nothing' }).then(r => r.has)"))?.ToJsonString() == "false");

            await Offline(w);
            Finish();
        }
        catch (Exception e)
        {
            Finish(e.ToString());
        }
    }

    /// <summary>
    /// Daf stops answering: the window moves to the copy at the same page, which answers from
    /// what was kept and keeps a write in the page's outbox; Daf answers again: back to the live site.
    /// </summary>
    static async Task Offline(ShellWindow w)
    {
        if (App.Options.ServerControl is not { } control)
        {
            Add("no connection: the window moves to the copy", false, "no --server-control");
            return;
        }
        await w.Run("go:review");
        // the page's own service worker would answer the page itself, as in a browser; the copy is for when it can't
        await w.Evaluate("navigator.serviceWorker.getRegistrations().then(rs => Promise.all(rs.map(r => r.unregister()))).then(() => true)");
        if (!await Server(control, "down")) { Add("the sandbox Daf stopped", false, "selftest.ps1 didn't say so"); return; }
        w.Reload();
        var moved = await Until(() => Address.IsCopy(w.Source), TimeSpan.FromSeconds(30));
        Add("Daf not answering, the window moves to the copy", moved, w.Source?.AbsoluteUri ?? "");
        if (!moved) w.GoLocal();
        Add("at the same page", J.Bool(await Until(w, "location.hash === '#review'", TimeSpan.FromSeconds(10))), w.Source?.AbsoluteUri ?? "");
        var signed = J.Bool(await Until(w, "window.dafState && dafState().signedIn", TimeSpan.FromSeconds(30)));
        Add("the copy opens signed in, from what was kept", signed);
        Add("its data comes from this PC", J.Text(await w.Evaluate("fetch('/api/today', { credentials: 'same-origin' }).then(r => r.headers.get('X-Daf-Offline'))")) == "1");
        Add("the copy has dafShell and no service worker",
            J.Bool(await w.Evaluate("!!window.dafShell && navigator.serviceWorker.controller === null && navigator.serviceWorker.register('/sw.js').then(() => false, () => true)")));
        var kept = J.Bool(await w.Evaluate(
            "DafCore.api('/api/tips', { method: 'POST', body: JSON.stringify({ seen: 'windows-selftest' }) }).then(() => JSON.parse(localStorage.getItem('daf.outbox') || '[]').length > 0, () => false)"));
        Add("a change made with no connection waits in the outbox", kept);
        if (!await Server(control, "up")) { Add("the sandbox Daf started again", false, "selftest.ps1 didn't say so"); return; }
        var back = await LocalCopy.Check();
        var live = await Until(() => w.Source is { } s && Address.IsDaf(s, Settings.BaseUrl), TimeSpan.FromSeconds(45));
        Add("Daf answering again, the window goes back to the live site", back && live && !LocalCopy.Active, w.Source?.AbsoluteUri ?? "");
        Add("signed in there", J.Bool(await Until(w, "window.dafState && dafState().signedIn", TimeSpan.FromSeconds(30))));
    }

    /// <summary>Asks selftest.ps1 to stop or start the sandbox Daf, and waits until it says it did.</summary>
    static async Task<bool> Server(string dir, string want)
    {
        await File.WriteAllTextAsync(Path.Join(dir, "want"), want);
        var now = Path.Join(dir, "now");
        return await Until(() => File.Exists(now) && File.ReadAllText(now).Trim() == want, TimeSpan.FromSeconds(60));
    }

    static string Hex(ShellWindow w) => $"#{w.BarColor.R:x2}{w.BarColor.G:x2}{w.BarColor.B:x2}";

    static bool Finished(string path)
    {
        lock (ShellServices.Finished) return ShellServices.Finished.Contains(path) && File.Exists(path);
    }

    static int Finished()
    {
        lock (ShellServices.Finished) return ShellServices.Finished.Count;
    }

    /// <summary>The expression's value once it is truthy, or its last value when the time runs out.</summary>
    static async Task<JsonNode?> Until(ShellWindow window, string expression, TimeSpan within)
    {
        var end = DateTime.UtcNow + within;
        JsonNode? value = null;
        while (DateTime.UtcNow < end)
        {
            try { value = await window.Evaluate(expression); }
            catch (Exception) { value = null; }
            if (value != null && value.ToJsonString() is not ("false" or "0" or "\"\"" or "null")) return value;
            await Task.Delay(250);
        }
        return value;
    }

    static async Task<bool> Until(Func<bool> condition, TimeSpan within)
    {
        var end = DateTime.UtcNow + within;
        while (DateTime.UtcNow < end)
        {
            if (condition()) return true;
            await Task.Delay(100);
        }
        return condition();
    }

    static void Finish(string? problem = null)
    {
        Check[] checks;
        lock (Gate)
        {
            if (problem != null) Checks.Add(new Check("the self-test ran to the end", false, problem));
            checks = [.. Checks];
        }
        var ok = checks.Length > 0 && checks.All(c => c.Ok);
        var report = new JsonObject
        {
            ["ok"] = ok,
            ["version"] = App.Version,
            ["checks"] = new JsonArray(checks.Select(c => (JsonNode?)new JsonObject { ["name"] = c.Name, ["ok"] = c.Ok, ["detail"] = c.Detail }).ToArray()),
        };
        try
        {
            if (App.Options.Out is { } path)
                File.WriteAllText(path, report.ToJsonString(new JsonSerializerOptions { WriteIndented = true, Encoder = JavaScriptEncoder.UnsafeRelaxedJsonEscaping }), Encoding.UTF8);
        }
        catch (Exception e) { Log.Write($"self-test results: {e.Message}"); }
        Tray.Remove();
        Environment.Exit(ok ? 0 : 1);
    }
}
