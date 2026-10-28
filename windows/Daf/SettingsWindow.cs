using Daf.Core;
using Microsoft.UI.Windowing;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;
using Windows.Graphics;
using WinRT.Interop;

namespace Daf;

/// <summary>
/// File › Settings…: the shell's own settings, the Mac's (mac/Daf/SettingsWindow.swift).
/// Daf's own preferences stay in the page.
/// </summary>
sealed class SettingsWindow : Window
{
    static SettingsWindow? open;
    public static bool IsOpen => open != null;

    readonly TextBox address = new() { PlaceholderText = Address.Default };
    readonly TextBlock addressNote = Note("Your Daf's address, like https://daf.example.com, or http://<server>:8440 on your tailnet.");
    readonly TextBlock status = new() { TextWrapping = TextWrapping.Wrap };
    readonly Button connect = new();
    readonly Button forget = new() { Content = "Forget the Token" };
    readonly PasswordBox pasted = new() { PlaceholderText = "Or paste a token" };
    readonly TextBlock tokenNote = Note("");
    readonly ToggleSwitch tray = new() { Header = "Show today's minutes in the notification area" };
    readonly ToggleSwitch atSignIn = new() { Header = "Open Daf when you sign in to Windows" };
    readonly TextBlock kept = new() { TextWrapping = TextWrapping.Wrap };
    readonly Button update = new() { Content = "Update Now" };
    readonly TextBlock keptNote = Note("Daf keeps its screens, your lists, the articles and books you're reading, and what you keep by hand, so it opens with no connection. What nothing needs any more goes after three weeks.");

    public static void Show()
    {
        if (open != null)
        {
            open.Activate();
            Win32.SetForegroundWindow(WindowNative.GetWindowHandle(open));
            return;
        }
        open = new SettingsWindow();
        open.Activate();
    }

    public static void CloseIt() => open?.Close();

    SettingsWindow()
    {
        Title = "Daf Settings";
        SystemBackdrop = new MicaBackdrop();
        var handle = WindowNative.GetWindowHandle(this);
        var icon = Path.Join(AppContext.BaseDirectory, "Assets", "Daf.ico");
        if (File.Exists(icon)) AppWindow.SetIcon(icon);
        if (AppWindow.Presenter is OverlappedPresenter p) { p.IsMaximizable = false; p.IsMinimizable = false; }
        var scale = Win32.Scale(handle);
        var size = new SizeInt32((int)(520 * scale), (int)(720 * scale));
        var area = DisplayArea.GetFromWindowId(ShellWindow.Front?.AppWindow.Id ?? AppWindow.Id, DisplayAreaFallback.Primary).WorkArea;
        AppWindow.MoveAndResize(new RectInt32(area.X + (area.Width - size.Width) / 2, area.Y + Math.Max(0, (area.Height - size.Height) / 3), size.Width, size.Height));

        var page = new StackPanel { Spacing = 10, Padding = new Thickness(28, 20, 28, 28), MaxWidth = 560 };
        page.Children.Add(Heading("Daf's address"));
        address.Text = Settings.BaseUrl.GetLeftPart(UriPartial.Authority);
        var use = new Button { Content = "Use" };
        use.Click += (_, _) => UseAddress();
        address.KeyDown += (_, e) => { if (e.Key == Windows.System.VirtualKey.Enter) { e.Handled = true; UseAddress(); } };
        page.Children.Add(Row(address, use));
        page.Children.Add(addressNote);

        page.Children.Add(Heading("This PC"));
        page.Children.Add(status);
        connect.Click += async (_, _) =>
        {
            connect.IsEnabled = false;
            tokenNote.Text = await Connect() ?? "";
            connect.IsEnabled = true;
            ShowToken();
        };
        forget.Click += (_, _) =>
        {
            App.Token.Set(null);
            Settings.Current.AutoConnect = false;
            Settings.Save();
            tokenNote.Text = "";
            ShowToken();
            _ = Today.Refresh();
        };
        page.Children.Add(Row(connect, forget));
        var save = new Button { Content = "Save" };
        save.Click += (_, _) =>
        {
            if (pasted.Password.Trim().Length == 0) return;
            tokenNote.Text = App.Token.Set(pasted.Password) ? "" : "Windows didn't keep the token.";
            pasted.Password = "";
            ShowToken();
            _ = Today.Refresh();
        };
        page.Children.Add(Row(pasted, save));
        page.Children.Add(tokenNote);
        page.Children.Add(Note("The notification area, Save a Link and the alerts use a device token of this PC's own, kept encrypted for your Windows account. Daf makes it once you sign in in its window; Preferences → Account lists it as Daf for Windows."));

        page.Children.Add(Heading("Notification area"));
        tray.IsOn = Settings.Current.Tray;
        tray.Toggled += (_, _) => Tray.SetShown(tray.IsOn);
        page.Children.Add(tray);
        atSignIn.IsOn = Settings.AtSignIn;
        atSignIn.Toggled += (_, _) => Settings.AtSignIn = atSignIn.IsOn;
        page.Children.Add(atSignIn);
        page.Children.Add(Note("At sign-in Daf starts in the notification area, without a window. With the notification area off, closing Daf's last window quits it."));

        page.Children.Add(Heading("With no connection"));
        update.Click += async (_, _) =>
        {
            update.IsEnabled = false;
            update.Content = "Updating…";
            var said = await Task.Run(() => App.Keeper.Refresh());
            keptNote.Text = said.StartsWith("Daf didn't") ? said : KeptNoteText;
            ShowKept();
            update.Content = "Update Now";
            update.IsEnabled = true;
        };
        page.Children.Add(Row(kept, update));
        page.Children.Add(keptNote);

        Content = new ScrollViewer { Content = page };
        ShowToken();
        ShowKept();
        Today.Changed += OnToday;
        Closed += (_, _) =>
        {
            Today.Changed -= OnToday;
            open = null;
        };
    }

    const string KeptNoteText = "Daf keeps its screens, your lists, the articles and books you're reading, and what you keep by hand, so it opens with no connection. What nothing needs any more goes after three weeks.";

    void OnToday() => DispatcherQueue.TryEnqueue(ShowToken);

    void ShowToken()
    {
        var has = App.Token.Value != null;
        connect.Content = has ? "Connect Again" : "Connect This PC";
        forget.Visibility = has ? Visibility.Visible : Visibility.Collapsed;
        status.Text = !has ? "Not connected yet."
            : Today.Last is { } w && !Today.Stale ? $"Connected: {w.Line}."
            : Today.Problem ?? "Connected.";
    }

    /// <summary>"54 MB on this PC, updated today at 10:42."</summary>
    void ShowKept()
    {
        var mb = $"{App.Keeper.Store.Bytes() / 1048576.0:0} MB";
        var at = App.Keeper.Copy.At;
        if (at == 0) { kept.Text = $"{mb} on this PC, not updated yet."; return; }
        var when = DateTimeOffset.FromUnixTimeMilliseconds(at).LocalDateTime;
        kept.Text = $"{mb} on this PC, updated {(when.Date == DateTime.Today ? "today at " + when.ToString("t") : when.ToString("g"))}.";
    }

    void UseAddress()
    {
        if (Settings.SetBase(address.Text))
        {
            address.Text = Settings.BaseUrl.GetLeftPart(UriPartial.Authority);
            addressNote.Text = "Your Daf's address, like https://daf.example.com, or http://<server>:8440 on your tailnet.";
        }
        else addressNote.Text = "That isn't an address Daf can use. It starts with https:// or http://.";
    }

    /// <summary>Makes this PC's device token with the sign-in in the Daf window. Null when it worked.</summary>
    static async Task<string?> Connect()
    {
        var w = ShellWindow.All.FirstOrDefault(x => x.IsApp && !Address.IsCopy(x.Source));
        if (w == null)
        {
            ShellWindow.Show(null);
            return "Sign in to Daf in its window, then press Connect again.";
        }
        return await w.Connect();
    }

    static TextBlock Heading(string text) => new()
    {
        Text = text, Style = (Style)Application.Current.Resources["BodyStrongTextBlockStyle"], Margin = new Thickness(0, 14, 0, 0),
    };

    static TextBlock Note(string text) => new()
    {
        Text = text, TextWrapping = TextWrapping.Wrap, Style = (Style)Application.Current.Resources["CaptionTextBlockStyle"], Opacity = 0.75,
    };

    static Grid Row(FrameworkElement grow, FrameworkElement end)
    {
        var g = new Grid { ColumnSpacing = 8 };
        g.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
        g.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
        grow.VerticalAlignment = VerticalAlignment.Center;
        end.VerticalAlignment = VerticalAlignment.Center;
        Grid.SetColumn(end, 1);
        g.Children.Add(grow);
        g.Children.Add(end);
        return g;
    }
}
