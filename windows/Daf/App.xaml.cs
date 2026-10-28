using System.Net;
using Daf.Core;
using Microsoft.UI.Dispatching;
using Microsoft.UI.Xaml;
using Microsoft.Web.WebView2.Core;
using Microsoft.Windows.AppLifecycle;
using Microsoft.Windows.AppNotifications;

namespace Daf;

/// <summary>
/// Daf for Windows: the live site (docs/SHELL.md) in a window with Daf's menus in its
/// title bar, today's minutes in the notification area, alerts for new posts, daf://
/// links, and a copy of Daf for no connection. Everything a person reads is the page;
/// this adds what a page can't do. The Mac's is mac/Daf.
/// </summary>
public partial class App : Application
{
    public static Options Options { get; private set; } = Options.Parse([]);

    /// <summary>The settings, the page's own storage, the copy and the log: %LOCALAPPDATA%\Daf, or --data for the self-test.</summary>
    public static string DataDir { get; private set; } = "";

    public static string Version { get; } =
        typeof(App).Assembly.GetName().Version is { } v ? $"{v.Major}.{v.Minor}.{v.Build}" : "0";

    /// <summary>What the page looks for (docs/SHELL.md §1), and what the shell's own requests say they are.</summary>
    public static string UserAgent => $"Daf/{Version} (Windows shell)";

    public static DispatcherQueue? Queue { get; private set; }

    /// <summary>For Daf's endpoints and the copy: the sign-in goes by hand (the window's cookie, or the device token), never a jar of its own.</summary>
    public static HttpClient Http { get; } = new(new SocketsHttpHandler
    {
        UseCookies = false,
        AutomaticDecompression = DecompressionMethods.All,
        PooledConnectionLifetime = TimeSpan.FromMinutes(5),
    });

    public static TokenStore Token { get; private set; } = new(null);
    public static DafClient Client { get; private set; } = null!;
    public static Keeper Keeper { get; private set; } = null!;

    static Task<CoreWebView2Environment>? web;
    static readonly List<AppActivationArguments> Early = [];

    /// <summary>One WebView2 environment for every window, its data beside the settings rather than beside the app; Windows 11's thin scrollbars.</summary>
    public static Task<CoreWebView2Environment> WebEnvironment =>
        web ??= CoreWebView2Environment.CreateWithOptionsAsync("", Path.Join(DataDir, "WebView2"),
            new CoreWebView2EnvironmentOptions { ScrollBarStyle = CoreWebView2ScrollbarStyle.FluentOverlay }).AsTask();

    public App()
    {
        InitializeComponent();
        // with the notification area on, Daf stays when its last window closes (Quit, LastWindowClosed)
        DispatcherShutdownMode = DispatcherShutdownMode.OnExplicitShutdown;
        UnhandledException += (_, e) => Log.Write($"unhandled: {e.Exception}");
    }

    protected override void OnLaunched(LaunchActivatedEventArgs args)
    {
        Options = Options.Parse(Environment.GetCommandLineArgs().Skip(1).ToArray());
        DataDir = Path.GetFullPath(Options.Data ?? Path.Join(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Daf"));
        Directory.CreateDirectory(DataDir);
        // no white flash before the page has drawn, in a dark theme
        Environment.SetEnvironmentVariable("WEBVIEW2_DEFAULT_BACKGROUND_COLOR", "0");
        Settings.Load();
        Token = new TokenStore(Options.SelfTest ? null : Path.Join(DataDir, "token.bin"));
        if (Options.Token != null) Token.Set(Options.Token);
        Client = new DafClient(Http, () => Settings.BaseUrl, () => Token.Value, UserAgent);
        Keeper = new Keeper(Path.Join(DataDir, "Copy"), Http, () => Settings.BaseUrl, LocalCopy.CookieHeader, UserAgent);
        Settings.RegisterLinks();
        FeedNews.Install();
        if (Options.SelfTest) SelfTest.Start();
        Queue = DispatcherQueue.GetForCurrentThread();
        Tray.Install();
        Today.Start();

        // what this start was for
        var activation = AppInstance.GetCurrent().GetActivatedEventArgs();
        if (activation.Kind == ExtendedActivationKind.AppNotification && activation.Data is AppNotificationActivatedEventArgs n)
            FeedNews.Open(n.Arguments);
        else if (Options.Link is { } link)
        {
            Handle(link);
            // a link to save needs no window; the self-test always has one
            if (link.Kind == "save" && Options.SelfTest) ShellWindow.Open();
        }
        else if (!Options.Background) ShellWindow.Open();
        lock (Early)
        {
            foreach (var e in Early) Queue.TryEnqueue(() => OnRedirected(e));
            Early.Clear();
        }
    }

    /// <summary>Another start of Daf handed over what it was asked (Program), on any thread.</summary>
    public static void Redirected(AppActivationArguments e)
    {
        lock (Early)
        {
            if (Queue == null) { Early.Add(e); return; }
        }
        Queue.TryEnqueue(() => OnRedirected(e));
    }

    static void OnRedirected(AppActivationArguments e)
    {
        switch (e.Kind)
        {
            case ExtendedActivationKind.AppNotification when e.Data is AppNotificationActivatedEventArgs n:
                FeedNews.Open(n.Arguments);
                break;
            case ExtendedActivationKind.Launch:
                var line = (e.Data as Windows.ApplicationModel.Activation.ILaunchActivatedEventArgs)?.Arguments ?? "";
                if (DafLink.Find(line) is { } link) Handle(link);
                else ShellWindow.Show(null);           // Daf from the Start menu again: its window, in front
                break;
            default:
                ShellWindow.Show(null);
                break;
        }
    }

    /// <summary>A daf:// link: save a link to the Library, or open a page of Daf.</summary>
    public static void Handle(DafLink link)
    {
        if (link.Kind == "save") _ = SaveLink.Save(link.Url, link.Title, link.Text);
        else if (link.Route is { } route) ShellWindow.Show("#" + route);
    }

    /// <summary>The last of Daf's windows closed: without the notification area there's nothing left of Daf, so it leaves.</summary>
    public static void LastWindowClosed()
    {
        if (!Tray.Shown && !Options.SelfTest) Quit();
    }

    /// <summary>Daf leaves, and its icon in the notification area with it.</summary>
    public static void Quit()
    {
        Tray.Remove();
        foreach (var w in ShellWindow.All.ToList()) w.Close();
        Current.Exit();
    }
}
