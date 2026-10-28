using System.Text.Json.Nodes;
using Daf.Core;
using Microsoft.UI;
using Microsoft.UI.Dispatching;
using Microsoft.UI.Windowing;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;
using Microsoft.UI.Xaml.Media.Imaging;
using Microsoft.Web.WebView2.Core;
using Windows.Graphics;
using WinRT.Interop;
using Color = Windows.UI.Color;

namespace Daf;

/// <summary>
/// One Daf window: the live site (docs/SHELL.md), all page, under a title bar in the
/// page's own colour that holds Daf's menus, the way the Mac's plain title bar takes the
/// page's colour (Readwise Reader's way). The Mac's is DafWindowController in mac/Daf/Window.swift.
/// </summary>
public sealed partial class ShellWindow : Window
{
    /// <summary>Every open window, the way the menus and the notification area find one.</summary>
    public static readonly List<ShellWindow> All = [];
    static ShellWindow? front;

    /// <summary>The window in front, or the last one opened.</summary>
    public static ShellWindow? Front => front != null && All.Contains(front) ? front : All.LastOrDefault();

    public IntPtr Handle { get; }
    /// <summary>A window of its own for one of Daf's files (the PDF as printed), not the app.</summary>
    public Uri? Start { get; }
    readonly string? route;
    WebView2? web;
    CoreWebView2Environment? environment;
    readonly ShellServices services;
    readonly Menus menus;
    bool started;
    ulong opening;
    RectInt32 normal;
    // full screen by F11 or the menu; by the page itself (the Fullscreen API); for the manga reader (dafShell.fullscreen)
    bool shellFull, pageFull, readerFull;
    string? seedId;

    /// <summary>The title bar's colour now, for the self-test.</summary>
    public Color BarColor { get; private set; }
    public bool BarDark { get; private set; }

    public static ShellWindow Open(Uri? start = null, string? route = null)
    {
        var window = new ShellWindow(start, route);
        All.Add(window);
        window.Activate();
        return window;
    }

    /// <summary>The window in front goes to a page of Daf ("#review"), or comes to the front; with none, one opens there.</summary>
    public static void Show(string? route)
    {
        var w = Front is { Start: null } f ? f : All.LastOrDefault(x => x.Start == null);
        if (w == null)
        {
            Open(route: route);
            return;
        }
        w.Bring();
        if (route != null) _ = w.Command("go:" + route.TrimStart('#'));
    }

    ShellWindow(Uri? start, string? route)
    {
        InitializeComponent();
        // the app's own address opened in a new window is the app, not a file
        Start = start == null || start.AbsolutePath is "" or "/" ? null : start;
        this.route = route ?? (start != null && Start == null ? Address.Route(start) : null);
        Title = "Daf";
        Handle = WindowNative.GetWindowHandle(this);
        services = new ShellServices(this);
        menus = new Menus(this, Menu);
        var icon = Path.Join(AppContext.BaseDirectory, "Assets", "Daf.ico");
        if (File.Exists(icon))
        {
            AppWindow.SetIcon(icon);
            AppIcon.Source = new BitmapImage(new Uri(icon));
        }
        ExtendsContentIntoTitleBar = true;
        SetTitleBar(DragArea);
        AppWindow.TitleBar.PreferredHeightOption = TitleBarHeightOption.Tall;
        Minimums();
        Paint(Settings.Current.BarColor, Settings.Current.BarDark);
        Place();
        AppWindow.Changed += OnChanged;
        Root.Loaded += async (_, _) =>
        {
            FitTitleBar();
            await StartAsync();
        };
        Activated += (_, e) =>
        {
            var active = e.WindowActivationState != WindowActivationState.Deactivated;
            // as any Windows title bar: dimmer while another window is in front
            TitleText.Opacity = AppIcon.Opacity = active ? 1 : 0.5;
            if (!active) return;
            front = this;
            menus.Refresh();
        };
        Settings.BaseChanged += OnBaseChanged;
        Closed += (_, _) =>
        {
            SavePlace();
            Settings.BaseChanged -= OnBaseChanged;
            Teardown();
            All.Remove(this);
            if (All.Count == 0) App.LastWindowClosed();
        };
    }

    async Task StartAsync()
    {
        if (started) return;
        started = true;
        Root.XamlRoot.Changed += (_, _) => FitTitleBar();
        await MakeWebViewAsync();
        if (App.Options.SelfTest && All.FirstOrDefault() == this) await SelfTest.Run(this);
    }

    /// <summary>Room for Windows' own caption buttons (minimize, maximize, close), which it draws over the row.</summary>
    void FitTitleBar()
    {
        // a minimized window has no caption buttons to measure: Windows fails asking (0xE0464645, 0xC000027B)
        if (!AppWindow.IsVisible || IsFullScreen || AppWindow.Presenter is OverlappedPresenter { State: OverlappedPresenterState.Minimized }) return;
        try
        {
            var scale = Root.XamlRoot?.RasterizationScale ?? Win32.Scale(Handle);
            if (scale <= 0) return;
            LeftPad.Width = new GridLength(AppWindow.TitleBar.LeftInset / scale);
            RightPad.Width = new GridLength(AppWindow.TitleBar.RightInset / scale);
        }
        catch (Exception e) { Log.Write($"title bar: {e.Message}"); }
    }

    /// <summary>The window's name, in the title bar and the taskbar: the page's, then Daf, as Windows names a document's window.</summary>
    void NameWindow(string? page)
    {
        var name = (page ?? "").Trim();
        Title = TitleText.Text = name.Length == 0 || name == "Daf" || name.EndsWith(" Daf") ? (name.Length == 0 ? "Daf" : name) : $"{name} - Daf";
    }

    /// <summary>The title row is shown, for the self-test.</summary>
    public bool TitleShown => Strip.Visibility == Visibility.Visible;

    void Minimums()
    {
        if (AppWindow.Presenter is not OverlappedPresenter p) return;
        var scale = Win32.Scale(Handle);
        p.PreferredMinimumWidth = (int)(900 * scale);
        p.PreferredMinimumHeight = (int)(600 * scale);
    }

    // ---- the page --------------------------------------------------------------------------

    async Task MakeWebViewAsync()
    {
        CoreWebView2Environment environment;
        try { environment = this.environment = await App.WebEnvironment; }
        catch (Exception e)
        {
            Log.Write($"no WebView2: {e}");
            Problem("Daf needs the Microsoft Edge WebView2 Runtime",
                "It comes with Windows 11 and recent Windows 10. Install it from https://go.microsoft.com/fwlink/p/?LinkId=2124703, then open Daf again.");
            return;
        }
        var view = new WebView2 { DefaultBackgroundColor = BarColor };
        Grid.SetRow(view, 1);
        Root.Children.Add(view);
        web = view;
        await view.EnsureCoreWebView2Async(environment);
        var core = view.CoreWebView2;
        var settings = core.Settings;
        settings.AreBrowserAcceleratorKeysEnabled = App.Options.DevTools;   // Daf's keys, not a browser's (F12 with --devtools)
        settings.IsStatusBarEnabled = false;
        // Zoom control stays on: off, WebView2 keeps Ctrl+Plus and Ctrl+Minus from the page.
        // Scripts.Shell turns them, and Ctrl and the wheel, into the reading text's size.
        settings.IsPinchZoomEnabled = false;           // the readers have their own
        settings.IsSwipeNavigationEnabled = false;     // a swipe in the manga reader turns its page
        settings.IsGeneralAutofillEnabled = false;
        settings.IsPasswordAutosaveEnabled = false;
        settings.AreDevToolsEnabled = App.Options.DevTools || App.Options.SelfTest;
        // lets the page tell it is inside the shell (docs/SHELL.md §1)
        settings.UserAgent = $"{settings.UserAgent} {App.UserAgent}";

        await core.AddScriptToExecuteOnDocumentCreatedAsync(Scripts.Shell([Address.Origin(Settings.BaseUrl), Address.CopyOrigin]));
        seedId = await core.AddScriptToExecuteOnDocumentCreatedAsync(LocalCopy.SeedScript());
        core.WebMessageReceived += OnMessage;
        core.NavigationStarting += OnNavigationStarting;
        core.NavigationCompleted += OnNavigationCompleted;
        core.NewWindowRequested += OnNewWindowRequested;
        core.ProcessFailed += OnProcessFailed;
        core.ContextMenuRequested += OnContextMenuRequested;
        core.DownloadStarting += services.OnDownloadStarting;
        core.LaunchingExternalUriScheme += OnExternalScheme;
        core.PermissionRequested += OnPermissionRequested;
        core.ContainsFullScreenElementChanged += (_, _) =>
        {
            pageFull = core.ContainsFullScreenElement;
            ApplyFullScreen();
        };
        core.HistoryChanged += (_, _) => RouteChanged();
        core.DocumentTitleChanged += (_, _) => NameWindow(core.DocumentTitle);
        LocalCopy.Attach(core, environment);
        if (App.Options.Cookie is { } cookie)
        {
            // the self-test's sign-in to its sandbox Daf
            var c = core.CookieManager.CreateCookie("daf", cookie, Settings.BaseUrl.Host, "/");
            c.IsHttpOnly = true;
            core.CookieManager.AddOrUpdateCookie(c);
        }
        core.Navigate(StartUrl().AbsoluteUri);
    }

    /// <summary>Where a new page starts: one of Daf's files, the copy when Daf isn't answering, or the live site.</summary>
    Uri StartUrl() =>
        Start ?? (LocalCopy.Active && App.Keeper.Store.Ready ? new Uri(LocalCopy.Url(route)) : Address.Url(Settings.BaseUrl, route ?? "/"));

    /// <summary>Daf's address changed: a file's window closes, the app's opens on the new one.</summary>
    void OnBaseChanged()
    {
        if (Start != null) { Close(); return; }
        Teardown();
        _ = MakeWebViewAsync();
    }

    void Teardown()
    {
        // a page that was full screen goes with its web view
        if (pageFull)
        {
            pageFull = false;
            ApplyFullScreen();
        }
        if (web == null) return;
        Root.Children.Remove(web);
        // a closed window must stop counting: the page goes with it
        try { web.Close(); } catch (Exception) { }
        web = null;
    }

    /// <summary>Where the window shows something instead of the page.</summary>
    void Problem(string title, string text)
    {
        var panel = new StackPanel { Spacing = 12, Margin = new Thickness(48), MaxWidth = 560, VerticalAlignment = VerticalAlignment.Center };
        panel.Children.Add(new TextBlock { Text = title, Style = (Style)Application.Current.Resources["SubtitleTextBlockStyle"], TextWrapping = TextWrapping.Wrap });
        panel.Children.Add(new TextBlock { Text = text, TextWrapping = TextWrapping.Wrap, IsTextSelectionEnabled = true });
        Grid.SetRow(panel, 1);
        Root.Children.Add(panel);
    }

    public CoreWebView2? Core => web?.CoreWebView2;

    public Uri? Source => Uri.TryCreate(web?.CoreWebView2?.Source, UriKind.Absolute, out var u) ? u : null;

    /// <summary>The live site or its copy is in the window (not one of Daf's files, not the page saying Daf didn't answer).</summary>
    public bool IsApp => Start == null && Source is { } s && Address.IsOurs(s, Settings.BaseUrl);

    /// <summary>The page is shown (not collapsed because the window is minimized).</summary>
    public bool PageShown => web?.Visibility == Visibility.Visible;

    // ---- messages between the page and the window --------------------------------------------

    void OnMessage(CoreWebView2 sender, CoreWebView2WebMessageReceivedEventArgs e)
    {
        // only Daf's own page, never anything else loaded into the window
        if (!Uri.TryCreate(e.Source, UriKind.Absolute, out var source) || !Address.IsOurs(source, Settings.BaseUrl)) return;
        JsonObject? m;
        try { m = JsonNode.Parse(e.WebMessageAsJson) as JsonObject; }
        catch (Exception) { return; }
        if (m == null) return;
        switch (J.Text(m["channel"]))
        {
            case "shell":
                services.Handle(J.Int(m["id"]), J.Text(m["op"]) ?? "", m["args"] as JsonObject ?? new JsonObject());
                break;
            case "key" when J.Text(m["what"]) == "menu":
                menus.Open(J.Text(m["letter"]));
                break;
            case "key":
                Key(J.Text(m["what"]) ?? "");
                break;
        }
    }

    /// <summary>A key the page left alone (Scripts.Shell), or a menu item the shell answers itself.</summary>
    public void Key(string what)
    {
        Menus.Ran.Add(what);
        switch (what)
        {
            case "newWindow": Open(); break;
            case "close": Close(); break;
            case "fullScreen": ToggleFullScreen(); break;
            case "reload": Reload(); break;
            case "back": Back(); break;
            case "forward": Forward(); break;
            case "settings": SettingsWindow.Show(); break;
            case "saveLink": _ = SaveLink.Ask(); break;
            default: _ = Run(what); break;
        }
    }

    /// <summary>A message to the page, from any thread.</summary>
    public void Post(JsonObject message)
    {
        var json = message.ToJsonString();
        DispatcherQueue.TryEnqueue(() =>
        {
            try { web?.CoreWebView2?.PostWebMessageAsJson(json); }
            catch (Exception e) { Log.Write($"post: {e.Message}"); }
        });
    }

    /// <summary>
    /// Runs one of the page's commands (docs/SHELL.md §3): true if the page did something.
    /// A page without them (one of Daf's files, Daf not answering) goes to the place instead.
    /// </summary>
    public async Task<bool> Command(string name)
    {
        if (web?.CoreWebView2 is not { } core) return false;
        if (Start != null)
        {
            Show(name.StartsWith("go:") ? "#" + name[3..] : null);
            return true;
        }
        string answer;
        try { answer = await core.ExecuteScriptAsync($"window.dafCommand ? window.dafCommand({J.Quote(name)}) : null"); }
        catch (Exception) { return false; }
        if (answer == "null" && name.StartsWith("go:"))
        {
            core.Navigate(Address.Url(Settings.BaseUrl, "#" + name[3..]).AbsoluteUri);
            return true;
        }
        return answer == "true";
    }

    /// <summary>A command, and a beep when it doesn't apply where the page is.</summary>
    public async Task Run(string name)
    {
        if (!await Command(name)) Win32.Beep();
        menus.Refresh();
    }

    /// <summary>Back: whatever is in front closes, or Daf goes back a page. A beep when there's nowhere to go.</summary>
    public async void Back()
    {
        if (web?.CoreWebView2 is not { } core) return;
        string went;
        try { went = await core.ExecuteScriptAsync("window.dafBack ? window.dafBack() : null"); }
        catch (Exception) { went = "null"; }
        if (went == "true") return;
        if (went == "null" && core.CanGoBack) { core.GoBack(); return; }   // a page without shell.js
        Win32.Beep();
    }

    public void Forward()
    {
        if (web?.CoreWebView2 is { CanGoForward: true } core) core.GoForward(); else Win32.Beep();
    }

    public void Reload()
    {
        if (web?.CoreWebView2 is not { } core) return;
        if (IsApp) core.Reload(); else core.Navigate(StartUrl().AbsoluteUri);
    }

    /// <summary>window.dafState() (docs/SHELL.md §4), or null before the page has one.</summary>
    public async Task<JsonObject?> State()
    {
        if (web?.CoreWebView2 is not { } core || Start != null) return null;
        try { return JsonNode.Parse(await core.ExecuteScriptAsync("window.dafState ? window.dafState() : null")) as JsonObject; }
        catch (Exception) { return null; }
    }

    /// <summary>The keyboard back to the page, after a menu.</summary>
    public void FocusPage() => web?.Focus(FocusState.Programmatic);

    /// <summary>A box in the page has the keyboard (a note, a search, a field), so Edit › Undo is its own.</summary>
    public async Task<bool> Typing()
    {
        if (web?.CoreWebView2 is not { } core) return false;
        try
        {
            return await core.ExecuteScriptAsync(
                "(() => { const a = document.activeElement; return !!a && (a.isContentEditable || /^(INPUT|TEXTAREA|SELECT|IFRAME)$/.test(a.tagName)); })()") == "true";
        }
        catch (Exception) { return false; }
    }

    /// <summary>The menus as the page is now; whether a Reader item is enabled (for the self-test).</summary>
    public Task UpdateMenus() => menus.Update();
    public bool MenuEnabled(string command) => menus.Enabled(command);

    /// <summary>
    /// A key pressed in the page as if on the keyboard (DevTools' Input domain), for the
    /// self-test. <paramref name="modifiers"/>: 1 Alt, 2 Ctrl, 8 Shift.
    /// </summary>
    public async Task Press(string key, string code, int virtualKey, int modifiers)
    {
        if (web?.CoreWebView2 is not { } core) return;
        web.Focus(FocusState.Programmatic);
        foreach (var type in new[] { "rawKeyDown", "keyUp" })
            await core.CallDevToolsProtocolMethodAsync("Input.dispatchKeyEvent", new JsonObject
            {
                ["type"] = type, ["modifiers"] = modifiers, ["key"] = key, ["code"] = code,
                ["windowsVirtualKeyCode"] = virtualKey, ["nativeVirtualKeyCode"] = virtualKey,
            }.ToJsonString());
    }

    /// <summary>A mouse button pressed and let go over the page (DevTools' Input domain): "back", say.</summary>
    public async Task Click(string button, int x = 300, int y = 300)
    {
        if (web?.CoreWebView2 is not { } core) return;
        var buttons = button switch { "left" => 1, "right" => 2, "middle" => 4, "back" => 8, "forward" => 16, _ => 0 };
        foreach (var type in new[] { "mousePressed", "mouseReleased" })
            await core.CallDevToolsProtocolMethodAsync("Input.dispatchMouseEvent", new JsonObject
            {
                ["type"] = type, ["x"] = x, ["y"] = y, ["button"] = button, ["buttons"] = type == "mousePressed" ? buttons : 0, ["clickCount"] = 1,
            }.ToJsonString());
    }

    /// <summary>The mouse wheel turned over the page, with <paramref name="modifiers"/> held (2: Ctrl), for the self-test.</summary>
    public async Task Wheel(int deltaY, int modifiers, int x = 300, int y = 300)
    {
        if (web?.CoreWebView2 is not { } core) return;
        await core.CallDevToolsProtocolMethodAsync("Input.dispatchMouseEvent", new JsonObject
        {
            ["type"] = "mouseWheel", ["x"] = x, ["y"] = y, ["deltaX"] = 0, ["deltaY"] = deltaY, ["modifiers"] = modifiers,
        }.ToJsonString());
    }

    /// <summary>The menus' titles, for the self-test.</summary>
    public string[] MenuTitles => menus.Titles;

    /// <summary>A picture of the page, as a PNG (for the self-test's record).</summary>
    public async Task Capture(string path)
    {
        if (web?.CoreWebView2 is not { } core) return;
        using var file = File.Create(path);
        await core.CapturePreviewAsync(CoreWebView2CapturePreviewImageFormat.Png, file.AsRandomAccessStream());
    }

    /// <summary>An expression in the page, a promise awaited, the value as JSON; with <paramref name="gesture"/>, as if a person had just clicked (for the Fullscreen API).</summary>
    public async Task<JsonNode?> Evaluate(string expression, bool gesture = false)
    {
        var core = web?.CoreWebView2 ?? throw new InvalidOperationException("no page yet");
        var json = await core.CallDevToolsProtocolMethodAsync("Runtime.evaluate",
            new JsonObject { ["expression"] = expression, ["awaitPromise"] = true, ["returnByValue"] = true, ["userGesture"] = gesture }.ToJsonString());
        var result = JsonNode.Parse(json);
        if (result?["exceptionDetails"] is { } problem)
            throw new Exception(problem["exception"]?["description"]?.ToString() ?? problem.ToJsonString());
        return result?["result"]?["value"]?.DeepClone();
    }

    // ---- what loads in the window ---------------------------------------------------------------

    /// <summary>Only Daf in the window. Anything else opens where it belongs: the browser, Mail, Obsidian.</summary>
    void OnNavigationStarting(CoreWebView2 sender, CoreWebView2NavigationStartingEventArgs e)
    {
        if (Uri.TryCreate(e.Uri, UriKind.Absolute, out var target)
            && (Address.IsOurs(target, Settings.BaseUrl) || target.Scheme is "about" or "data" or "blob"))
        {
            opening = e.NavigationId;
            return;
        }
        e.Cancel = true;
        if (target != null) Outside.Open(target);
    }

    async void OnNavigationCompleted(CoreWebView2 sender, CoreWebView2NavigationCompletedEventArgs e)
    {
        if (e.NavigationId != opening) return;
        var onCopy = Address.IsCopy(Source);
        var code = e.HttpStatusCode;
        // Daf didn't answer: no connection, no server, or Cloudflare saying so. A navigation
        // cancelled, or one that became a download, isn't that.
        var down = (!e.IsSuccess && e.WebErrorStatus is not (CoreWebView2WebErrorStatus.OperationCanceled or CoreWebView2WebErrorStatus.ConnectionAborted))
            || code is 502 or 503 or 504 or (>= 520 and <= 530);
        if (down && Start == null && !onCopy && App.Keeper.Store.Ready)
        {
            // Daf didn't answer: the same page from the copy on this PC
            GoLocal();
            return;
        }
        if (!e.IsSuccess && e.WebErrorStatus is not (CoreWebView2WebErrorStatus.OperationCanceled or CoreWebView2WebErrorStatus.ConnectionAborted))
        {
            Log.Write($"could not open {Settings.BaseUrl}: {e.WebErrorStatus}");
            sender.NavigateToString(Unreachable(e.WebErrorStatus.ToString()));
            return;
        }
        menus.Refresh();
        if (!e.IsSuccess || Start != null || Source is not { } now || !Address.IsDaf(now, Settings.BaseUrl)) return;
        // the live site answered
        LocalCopy.WentLive();
        await SnapshotSettings();
        LocalCopy.KeepUpToDate();
        await AutoConnect();
    }

    /// <summary>window.open and target=_blank: Daf's own files in a window of their own, anything else outside.</summary>
    void OnNewWindowRequested(CoreWebView2 sender, CoreWebView2NewWindowRequestedEventArgs e)
    {
        e.Handled = true;
        if (!Uri.TryCreate(e.Uri, UriKind.Absolute, out var target)) return;
        if (Address.IsOurs(target, Settings.BaseUrl)) Open(start: target);
        else Outside.Open(target);
    }

    /// <summary>obsidian:// and mailto: go to their apps without WebView2 asking first.</summary>
    void OnExternalScheme(CoreWebView2 sender, CoreWebView2LaunchingExternalUriSchemeEventArgs e)
    {
        e.Cancel = true;
        if (Uri.TryCreate(e.Uri, UriKind.Absolute, out var target)) Outside.Open(target);
    }

    void OnProcessFailed(CoreWebView2 sender, CoreWebView2ProcessFailedEventArgs e)
    {
        Log.Write($"the page's process failed: {e.ProcessFailedKind}");
        // the page's process went (memory, a crash): bring the page back; the whole browser gone: a web view again
        if (e.ProcessFailedKind == CoreWebView2ProcessFailedKind.RenderProcessExited) sender.Reload();
        else if (e.ProcessFailedKind == CoreWebView2ProcessFailedKind.BrowserProcessExited)
            DispatcherQueue.TryEnqueue(() => { Teardown(); _ = MakeWebViewAsync(); });
    }

    static readonly HashSet<string> Unwanted =
        ["back", "forward", "reload", "saveAs", "print", "createQrCode", "share", "webCapture", "openLinkInNewWindow", "saveLinkAs", "copyLinkToHighlight"];

    /// <summary>
    /// The page's right-click menu, without what belongs to a browser (spelling, cut, copy
    /// and paste stay), and on words chosen in an article or a book with Daf's own Highlight
    /// and Highlight with a Note first, as a Windows reading app has them there.
    /// </summary>
    async void OnContextMenuRequested(CoreWebView2 sender, CoreWebView2ContextMenuRequestedEventArgs e)
    {
        var items = e.MenuItems;
        for (var i = items.Count - 1; i >= 0; i--)
            if (Unwanted.Contains(items[i].Name)) items.RemoveAt(i);
        if (!e.ContextMenuTarget.HasSelection || e.ContextMenuTarget.IsEditable || environment == null)
        {
            Tidy(items);
            return;
        }
        var deferral = e.GetDeferral();
        try
        {
            if (await State() is { } s && s["can"] is JsonObject can && J.Bool(can["highlight"]))
            {
                var at = items.Select((item, i) => (item, i)).FirstOrDefault(x => x.item.Name is "cut" or "copy" or "paste").i;
                if (at == 0 && items.Count > 0 && items[0].Name is not ("cut" or "copy" or "paste")) at = items.Count;
                var ours = new List<CoreWebView2ContextMenuItem> { Item("Highlight", "highlight"), Item("Highlight with a Note", "note") };
                if (at > 0) ours.Insert(0, Line());
                ours.Add(Line());
                for (var i = ours.Count - 1; i >= 0; i--) items.Insert(at, ours[i]);
            }
        }
        catch (Exception x) { Log.Write($"context menu: {x.Message}"); }
        finally
        {
            Tidy(items);
            deferral.Complete();
        }

        CoreWebView2ContextMenuItem Item(string label, string command)
        {
            var item = environment!.CreateContextMenuItem(label, null, CoreWebView2ContextMenuItemKind.Command);
            item.CustomItemSelected += (_, _) => DispatcherQueue.TryEnqueue(() => _ = Run(command));
            return item;
        }
        CoreWebView2ContextMenuItem Line() => environment!.CreateContextMenuItem("", null, CoreWebView2ContextMenuItemKind.Separator);
    }

    /// <summary>No separator left at an end of the menu, or beside another.</summary>
    static void Tidy(IList<CoreWebView2ContextMenuItem> items)
    {
        for (var i = items.Count - 1; i >= 0; i--)
            if (items[i].Kind == CoreWebView2ContextMenuItemKind.Separator
                && (i == 0 || i == items.Count - 1 || items[i - 1].Kind == CoreWebView2ContextMenuItemKind.Separator))
                items.RemoveAt(i);
    }

    /// <summary>The page moved (a hash route): the menus follow, and the reader's full screen ends with the reader.</summary>
    void RouteChanged()
    {
        menus.Refresh();
        if (readerFull && Address.Route(Source)?.StartsWith("#mread/") != true)
        {
            readerFull = shellFull = false;
            ApplyFullScreen();
        }
    }

    /// <summary>
    /// Daf's own page may download several files without a click in between (Share as
    /// image's Download after the export, a book's file): they go to the save dialog like the
    /// first. Anything else WebView2 asks as it would.
    /// </summary>
    void OnPermissionRequested(CoreWebView2 sender, CoreWebView2PermissionRequestedEventArgs e)
    {
        if (e.PermissionKind == CoreWebView2PermissionKind.MultipleAutomaticDownloads
            && Uri.TryCreate(e.Uri, UriKind.Absolute, out var u) && Address.IsOurs(u, Settings.BaseUrl))
            e.State = CoreWebView2PermissionState.Allow;
    }

    static string Unreachable(string why)
    {
        static string Esc(string s) => s.Replace("&", "&amp;").Replace("<", "&lt;").Replace("\"", "&quot;");
        var base_ = Settings.BaseUrl.AbsoluteUri;
        return $$"""
            <!doctype html><meta charset="utf-8"><style>
            body{font:14px "Segoe UI Variable Text","Segoe UI",sans-serif;color:#555;display:flex;height:100vh;margin:0;align-items:center;justify-content:center;text-align:center}
            @media (prefers-color-scheme:dark){body{color:#bbb;background:#16171a} }
            h1{font-size:18px;font-weight:600;color:inherit}a{color:inherit}
            </style><div><h1>Daf didn't answer</h1><p>{{Esc(base_)}}: {{Esc(why)}}</p>
            <p><a href="{{Esc(base_)}}">Try again</a> · or change the address in File › Settings.</p></div>
            """;
    }

    // ---- the window: full screen, hidden, its colour, where it is -------------------------------

    public bool IsFullScreen => AppWindow.Presenter.Kind == AppWindowPresenterKind.FullScreen;

    /// <summary>
    /// F11 and View › Full Screen. Out of full screen is out, whichever way it came: the
    /// page's own full screen (focus mode) too, so nothing is left half-way.
    /// </summary>
    public void ToggleFullScreen()
    {
        if (shellFull || pageFull || IsFullScreen) LeaveFullScreen();
        else shellFull = true;
        ApplyFullScreen();
    }

    void LeaveFullScreen()
    {
        shellFull = readerFull = false;
        if (pageFull) _ = web?.CoreWebView2?.ExecuteScriptAsync("document.fullscreenElement && document.exitFullscreen()");
        pageFull = false;
    }

    /// <summary>dafShell.fullscreen: the manga reader's Full screen, left again with the reader. True when it went full screen.</summary>
    public bool ReaderFullScreen()
    {
        var entering = !(shellFull || pageFull || IsFullScreen);
        if (entering) shellFull = readerFull = true; else LeaveFullScreen();
        ApplyFullScreen();
        return entering;
    }

    /// <summary>One state from the ways in: full screen while any wants it, the title bar exactly when not.</summary>
    void ApplyFullScreen()
    {
        var want = shellFull || pageFull;
        if (App.Options.SelfTest) Log.Write($"full screen: want {want} (shell {shellFull}, page {pageFull}), now {AppWindow.Presenter.Kind}");
        try
        {
            if (want != IsFullScreen)
            {
                AppWindow.SetPresenter(want ? AppWindowPresenterKind.FullScreen : AppWindowPresenterKind.Overlapped);
                if (!want) Minimums();
            }
        }
        catch (Exception e) { Log.Write($"full screen: {e.Message}"); }
        Presented();
        if (want) Hint(pageFull && !shellFull ? "Press Esc to exit full screen" : "Press F11 to exit full screen");
    }

    /// <summary>
    /// The presenter changed, by Daf or by Windows (Win+↓ takes a window out of full
    /// screen): the title bar follows what the window really is.
    /// </summary>
    void Presented()
    {
        // nothing here may change the presenter, or Windows tells us again (AppWindow.Changed)
        if (App.Options.SelfTest) Log.Write($"presented: {AppWindow.Presenter.Kind}");
        if (!IsFullScreen && (shellFull || pageFull)) LeaveFullScreen();
        Strip.Visibility = IsFullScreen ? Visibility.Collapsed : Visibility.Visible;
    }

    Border? hint;
    DispatcherQueueTimer? hintTimer;

    /// <summary>A word at the top for three seconds, as Windows' browsers say how to leave full screen.</summary>
    void Hint(string text)
    {
        if (hint != null) Root.Children.Remove(hint);
        hint = new Border
        {
            Background = new SolidColorBrush(Color.FromArgb(0xE6, 0x2B, 0x2B, 0x2B)),
            CornerRadius = new CornerRadius(8),
            Padding = new Thickness(16, 10, 16, 10),
            Margin = new Thickness(0, 24, 0, 0),
            HorizontalAlignment = HorizontalAlignment.Center,
            VerticalAlignment = VerticalAlignment.Top,
            IsHitTestVisible = false,
            Child = new TextBlock { Text = text, Foreground = new SolidColorBrush(Colors.White) },
        };
        Grid.SetRowSpan(hint, 2);
        Root.Children.Add(hint);
        var shown = hint;
        hintTimer?.Stop();
        hintTimer = DispatcherQueue.CreateTimer();
        hintTimer.Interval = TimeSpan.FromSeconds(3);
        hintTimer.IsRepeating = false;
        hintTimer.Tick += (_, _) =>
        {
            Root.Children.Remove(shown);
            if (hint == shown) hint = null;
        };
        hintTimer.Start();
    }

    /// <summary>
    /// Hidden means hidden (docs/SHELL.md §5): a minimized window's page is hidden, so Daf
    /// counts no minutes nobody read. And where the window is, while it's neither maximized nor full screen.
    /// </summary>
    void OnChanged(AppWindow sender, AppWindowChangedEventArgs e)
    {
        var state = (sender.Presenter as OverlappedPresenter)?.State;
        if ((e.DidPositionChange || e.DidSizeChange) && state == OverlappedPresenterState.Restored)
            normal = new RectInt32(sender.Position.X, sender.Position.Y, sender.Size.Width, sender.Size.Height);
        // A turn later, not inside Windows' own change (and FitTitleBar leaves a minimized
        // window alone): measuring the caption buttons then made Microsoft.UI.Windowing fail fast.
        if (e.DidSizeChange || e.DidPresenterChange)
        {
            var presenter = e.DidPresenterChange;
            DispatcherQueue.TryEnqueue(() =>
            {
                try
                {
                    FitTitleBar();
                    if (presenter) Presented();
                }
                catch (Exception x) { Log.Write($"the window changed: {x.Message}"); }
            });
        }
        if (web != null)
        {
            var shown = state != OverlappedPresenterState.Minimized && sender.IsVisible;
            var now = shown ? Visibility.Visible : Visibility.Collapsed;
            if (web.Visibility != now) web.Visibility = now;
        }
    }

    /// <summary>To the front, out of the taskbar if it was minimized.</summary>
    public void Bring()
    {
        if (AppWindow.Presenter is OverlappedPresenter { State: OverlappedPresenterState.Minimized } p) p.Restore();
        Activate();
        Win32.SetForegroundWindow(Handle);
    }

    /// <summary>
    /// dafShell.bars: the title bar and its menus in the theme's background (#rrggbb), with
    /// light or dark letters and buttons. False for a colour it can't read. Kept for the
    /// next start's first frame.
    /// </summary>
    public bool Paint(string? bg, bool dark)
    {
        var known = TryColor(bg, out var c);
        if (!known)
        {
            dark = bg == null ? Application.Current.RequestedTheme == ApplicationTheme.Dark : dark;
            c = dark ? Color.FromArgb(255, 0x20, 0x20, 0x20) : Color.FromArgb(255, 0xf9, 0xf9, 0xf9);
        }
        BarColor = c;
        BarDark = dark;
        Strip.Background = new SolidColorBrush(c);
        Root.RequestedTheme = dark ? ElementTheme.Dark : ElementTheme.Light;
        var fg = dark ? Colors.White : Colors.Black;
        var tb = AppWindow.TitleBar;
        tb.ButtonBackgroundColor = Colors.Transparent;
        tb.ButtonInactiveBackgroundColor = Colors.Transparent;
        tb.ButtonForegroundColor = fg;
        tb.ButtonHoverForegroundColor = fg;
        tb.ButtonPressedForegroundColor = fg;
        tb.ButtonInactiveForegroundColor = Color.FromArgb(0x80, fg.R, fg.G, fg.B);
        tb.ButtonHoverBackgroundColor = Color.FromArgb(0x20, fg.R, fg.G, fg.B);
        tb.ButtonPressedBackgroundColor = Color.FromArgb(0x38, fg.R, fg.G, fg.B);
        if (web != null) web.DefaultBackgroundColor = c;
        return known || bg == null;
    }

    public static bool TryColor(string? hex, out Color color)
    {
        color = default;
        if (hex is not { Length: 7 } || hex[0] != '#' || !int.TryParse(hex[1..], System.Globalization.NumberStyles.HexNumber, null, out var rgb)) return false;
        color = Color.FromArgb(255, (byte)(rgb >> 16), (byte)(rgb >> 8), (byte)rgb);
        return true;
    }

    /// <summary>The first window where it was last time; another cascaded from the one in front.</summary>
    void Place()
    {
        var scale = Win32.Scale(Handle);
        var size = new SizeInt32((int)(1280 * scale), (int)(840 * scale));
        if (All.Count == 0 && Settings.Current.WindowPlace is [var x, var y, var w, var h, var maximised]
            && w > 200 && h > 200 && DisplayArea.GetFromRect(new RectInt32(x, y, w, h), DisplayAreaFallback.None) != null)
        {
            normal = new RectInt32(x, y, w, h);
            AppWindow.MoveAndResize(normal);
            if (maximised == 1 && AppWindow.Presenter is OverlappedPresenter presenter) presenter.Maximize();
            return;
        }
        AppWindow.Resize(size);
        if (All.Count > 0)
        {
            var p = All[^1].AppWindow.Position;
            AppWindow.Move(new PointInt32(p.X + (int)(28 * scale), p.Y + (int)(28 * scale)));
        }
        else
        {
            var area = DisplayArea.GetFromWindowId(AppWindow.Id, DisplayAreaFallback.Primary).WorkArea;
            AppWindow.Move(new PointInt32(area.X + Math.Max(0, (area.Width - size.Width) / 2), area.Y + Math.Max(0, (area.Height - size.Height) / 2)));
        }
        normal = new RectInt32(AppWindow.Position.X, AppWindow.Position.Y, AppWindow.Size.Width, AppWindow.Size.Height);
    }

    void SavePlace()
    {
        if (App.Options.SelfTest || Start != null || IsFullScreen || All.FirstOrDefault(w => w.Start == null) != this) return;
        var maximised = AppWindow.Presenter is OverlappedPresenter { State: OverlappedPresenterState.Maximized };
        Settings.Current.WindowPlace = [normal.X, normal.Y, normal.Width, normal.Height, maximised ? 1 : 0];
        Settings.Save();
    }

    // ---- with no connection: the copy, and back ---------------------------------------------------

    /// <summary>Daf didn't answer: the same page from the copy on this PC.</summary>
    public async void GoLocal()
    {
        if (!App.Keeper.Store.Ready || Start != null || web?.CoreWebView2 is not { } core) return;
        var r = Address.Route(Source) ?? route;
        LocalCopy.Active = true;
        await Reseed(core);
        core.Navigate(LocalCopy.Url(r));
        LocalCopy.Watch();
    }

    /// <summary>Daf answers again: what was done on the copy goes first (its outbox), then the live site.</summary>
    public async Task GoLive()
    {
        if (web?.CoreWebView2 is not { } core || !Address.IsCopy(Source)) return;
        var r = Address.Route(Source);
        try
        {
            await core.ExecuteScriptAsync("window.DafCore && DafCore.outbox && DafCore.outbox.flush && DafCore.outbox.flush(), 1");
            for (var i = 0; i < 30; i++)
            {
                if (await core.ExecuteScriptAsync("JSON.parse(localStorage.getItem('daf.outbox') || '[]').length") == "0") break;
                await Task.Delay(1000);
            }
        }
        catch (Exception e) { Log.Write($"sending what was done offline: {e.Message}"); }
        core.Navigate(Address.Url(Settings.BaseUrl, r ?? "/").AbsoluteUri);
    }

    /// <summary>The copy's seed again, so it carries the newest snapshot of the live page's settings.</summary>
    async Task Reseed(CoreWebView2 core)
    {
        if (seedId != null) core.RemoveScriptToExecuteOnDocumentCreated(seedId);
        seedId = await core.AddScriptToExecuteOnDocumentCreatedAsync(LocalCopy.SeedScript());
    }

    /// <summary>The live page's settings, kept for the copy (not its outbox).</summary>
    async Task SnapshotSettings()
    {
        if (web?.CoreWebView2 is not { } core) return;
        try
        {
            if (JsonNode.Parse(await core.ExecuteScriptAsync(Scripts.Snapshot)) is JsonValue v && v.TryGetValue(out string? json))
                LocalCopy.KeepSnapshot(json);
        }
        catch (Exception e) { Log.Write($"the page's settings for the copy: {e.Message}"); }
    }

    // ---- the device token --------------------------------------------------------------------------

    /// <summary>
    /// Once the page is signed in and this PC has no token, the app makes one itself, as the
    /// Android app does, so the notification area and Save a Link need nothing set up.
    /// </summary>
    async Task AutoConnect()
    {
        if (App.Token.Value != null || !Settings.Current.AutoConnect) return;
        for (var i = 0; i < 40 && web != null; i++)
        {
            if (J.Bool((await State())?["signedIn"]))
            {
                var problem = await Connect();
                if (problem != null) Log.Write($"connecting this PC: {problem}");
                return;
            }
            await Task.Delay(500);
        }
    }

    /// <summary>Makes this PC's device token with the window's sign-in, and keeps it. Null when it worked, otherwise what to say.</summary>
    public async Task<string?> Connect()
    {
        var name = Links.DeviceName(Environment.MachineName);
        var js = $$"""
            (async () => {
              const r = await fetch('/api/devices', { method: 'POST', credentials: 'same-origin',
                headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name: {{J.Quote(name)}} }) });
              return { status: r.status, body: await r.text() };
            })()
            """;
        JsonObject? answer;
        try { answer = await Evaluate(js) as JsonObject; }
        catch (Exception e) { return "Daf didn't answer: " + e.Message; }
        var status = J.Int(answer?["status"]);
        JsonObject? body = null;
        try { body = JsonNode.Parse(J.Text(answer?["body"]) ?? "") as JsonObject; } catch (Exception) { }
        switch (status)
        {
            case >= 200 and < 300:
                if (J.Text(body?["token"]) is not { Length: > 0 } token) return "Daf answered without a token.";
                if (!App.Token.Set(token)) return "Windows didn't keep the token.";
                Settings.Current.AutoConnect = true;
                Settings.Save();
                _ = Today.Refresh();
                return null;
            case 401: return "Sign in to Daf in its window first, then press Connect again.";
            case 404 or 405: return $"This Daf can't make tokens for Windows yet. On the server, run daf kindle-token {name} and paste what it prints in Settings.";
            default: return J.Text(body?["detail"]) ?? $"Daf answered {status}.";
        }
    }
}
