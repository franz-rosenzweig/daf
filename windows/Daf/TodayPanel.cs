using Daf.Core;
using Microsoft.UI;
using Microsoft.UI.Text;
using Microsoft.UI.Windowing;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;
using Microsoft.UI.Xaml.Shapes;
using Windows.Foundation;
using Windows.Graphics;
using WinRT.Interop;
using Color = Windows.UI.Color;

namespace Daf;

/// <summary>
/// What a click on the notification area's ring shows, the Mac's menu-bar menu: the ring
/// with "38 of 60 minutes today · Year 30, day N", the day's highlight with its book, and
/// Open Daf, Review, Save a Link…, Log Paper Minutes… and Settings…. It goes when
/// something else is clicked, and asks Daf again each time it opens.
/// </summary>
sealed class TodayPanel : Window
{
    static TodayPanel? panel;
    public static bool IsOpen => panel?.AppWindow.IsVisible == true;
    /// <summary>What it says now, for the self-test.</summary>
    public static string Said => panel?.said ?? "";

    readonly StackPanel body = new() { Spacing = 10, Padding = new Thickness(16, 14, 16, 12) };
    readonly IntPtr handle;
    DateTime hiddenAt;
    string said = "";
    const double PanelWidth = 320;

    public static void Toggle()
    {
        panel ??= new TodayPanel();
        if (panel.AppWindow.IsVisible) { panel.Hide(); return; }
        // the click on the icon that took the panel away mustn't bring it straight back
        if (DateTime.UtcNow - panel.hiddenAt < TimeSpan.FromMilliseconds(400)) return;
        panel.ShowNearPointer();
    }

    public static void Dismiss() => panel?.Hide();

    TodayPanel()
    {
        Title = "Daf";
        handle = WindowNative.GetWindowHandle(this);
        SystemBackdrop = new DesktopAcrylicBackdrop();
        var presenter = OverlappedPresenter.Create();
        presenter.IsResizable = false;
        presenter.IsMaximizable = false;
        presenter.IsMinimizable = false;
        presenter.IsAlwaysOnTop = true;
        presenter.SetBorderAndTitleBar(true, false);
        AppWindow.SetPresenter(presenter);
        AppWindow.IsShownInSwitchers = false;
        var icon = System.IO.Path.Join(AppContext.BaseDirectory, "Assets", "Daf.ico");
        if (File.Exists(icon)) AppWindow.SetIcon(icon);
        Content = new ScrollViewer { Content = body, VerticalScrollBarVisibility = ScrollBarVisibility.Auto };
        body.SizeChanged += (_, _) => Fit();
        Activated += (_, e) =>
        {
            if (e.WindowActivationState == WindowActivationState.Deactivated && AppWindow.IsVisible) Hide();
        };
        // Alt+F4 puts it away; it's there for the next click
        AppWindow.Closing += (_, e) => { e.Cancel = true; Hide(); };
        Today.Changed += () => DispatcherQueue.TryEnqueue(Fill);
        Fill();
    }

    void Hide()
    {
        AppWindow.Hide();
        hiddenAt = DateTime.UtcNow;
    }

    void ShowNearPointer()
    {
        Fill();
        Place();
        AppWindow.Show();
        Activate();
        Win32.SetForegroundWindow(handle);
        _ = Today.Refresh();
    }

    /// <summary>Beside the pointer, which is on the notification area: above it with the taskbar below, under it with the taskbar on top.</summary>
    void Place()
    {
        var scale = Win32.Scale(handle);
        var w = (int)(PanelWidth * scale);
        var h = (int)(Math.Max(120, body.ActualHeight > 0 ? body.ActualHeight : 360) * scale) + 2;
        Win32.GetCursorPos(out var p);
        var area = DisplayArea.GetFromPoint(new PointInt32(p.X, p.Y), DisplayAreaFallback.Nearest).WorkArea;
        var margin = (int)(12 * scale);
        var x = Math.Clamp(p.X - w / 2, area.X + margin, area.X + area.Width - w - margin);
        var y = p.Y > area.Y + area.Height / 2 ? area.Y + area.Height - h - margin : area.Y + margin;
        AppWindow.MoveAndResize(new RectInt32(x, y, w, h));
    }

    /// <summary>As tall as what it says.</summary>
    void Fit()
    {
        if (!AppWindow.IsVisible) return;
        var scale = Win32.Scale(handle);
        var h = (int)(body.ActualHeight * scale) + 2;
        if (Math.Abs(AppWindow.Size.Height - h) < 2) return;
        var area = DisplayArea.GetFromWindowId(AppWindow.Id, DisplayAreaFallback.Nearest).WorkArea;
        var y = AppWindow.Position.Y + AppWindow.Size.Height > area.Y + area.Height - area.Height / 3
            ? AppWindow.Position.Y + AppWindow.Size.Height - h      // it grows upwards from a taskbar below
            : AppWindow.Position.Y;
        AppWindow.MoveAndResize(new RectInt32(AppWindow.Position.X, Math.Max(area.Y, y), AppWindow.Size.Width, h));
    }

    void Fill()
    {
        body.Children.Clear();
        var w = Today.Last;
        var dark = (Content as FrameworkElement)?.ActualTheme == ElementTheme.Dark;
        var muted = new SolidColorBrush(dark ? Color.FromArgb(0xb0, 0xff, 0xff, 0xff) : Color.FromArgb(0x9a, 0, 0, 0));
        if (w != null)
        {
            var row = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 12 };
            row.Children.Add(Ring(w.Fraction, w.Done, dark));
            var words = new StackPanel { VerticalAlignment = VerticalAlignment.Center, Spacing = 2 };
            var line = w.Done ? w.MetLine : w.Line;
            words.Children.Add(new TextBlock { Text = line, FontWeight = FontWeights.SemiBold, FontSize = 14, TextWrapping = TextWrapping.Wrap, MaxWidth = PanelWidth - 90 });
            if (w.Subtitle.Length > 0) words.Children.Add(new TextBlock { Text = w.Subtitle, FontSize = 12, Foreground = muted });
            row.Children.Add(words);
            body.Children.Add(row);
            said = line + (w.Subtitle.Length > 0 ? " · " + w.Subtitle : "");
            if (w.Today is { Text.Length: > 0 } h)
            {
                var quote = new StackPanel { Spacing = 4 };
                quote.Children.Add(new TextBlock
                {
                    Text = h.Text, FontFamily = new FontFamily("Georgia"), FontSize = 14, LineHeight = 20,
                    TextWrapping = TextWrapping.Wrap, MaxLines = 4, TextTrimming = TextTrimming.WordEllipsis,
                });
                if (h.Title is { Length: > 0 } t) quote.Children.Add(new TextBlock { Text = t, FontSize = 12, Foreground = muted, TextTrimming = TextTrimming.CharacterEllipsis });
                body.Children.Add(quote);
            }
        }
        else
        {
            body.Children.Add(new TextBlock { Text = "Daf", FontWeight = FontWeights.SemiBold, FontSize = 14 });
            said = "Daf";
        }
        if (Today.Note is { } note)
        {
            body.Children.Add(new TextBlock { Text = note, FontSize = 12, Foreground = muted, TextWrapping = TextWrapping.Wrap });
            said += " · " + note;
        }
        body.Children.Add(new Border { Height = 1, Background = new SolidColorBrush(dark ? Color.FromArgb(0x30, 0xff, 0xff, 0xff) : Color.FromArgb(0x20, 0, 0, 0)), Margin = new Thickness(-4, 2, -4, 0) });
        var actions = new StackPanel { Spacing = 0, Margin = new Thickness(-8, 0, -8, 0) };
        foreach (var (text, act) in new (string, Action)[]
                 {
                     ("Open Daf", () => Tray.OpenDaf()), ("Review", () => ShellWindow.Show("#review")),
                     ("Save a Link…", () => _ = SaveLink.Ask()), ("Log Paper Minutes…", () => Tray.LogPaper()), ("Settings…", () => SettingsWindow.Show()),
                 })
        {
            var b = new Button
            {
                Content = text, HorizontalAlignment = HorizontalAlignment.Stretch, HorizontalContentAlignment = HorizontalAlignment.Left,
                Background = new SolidColorBrush(Colors.Transparent), BorderThickness = new Thickness(0), Padding = new Thickness(8, 6, 8, 6),
            };
            b.Click += (_, _) => { Hide(); act(); };
            actions.Children.Add(b);
        }
        body.Children.Add(actions);
    }

    /// <summary>The goal as a ring, like Today's: Daf's blue, green once it's met.</summary>
    static FrameworkElement Ring(double fraction, bool done, bool dark)
    {
        const double size = 40, stroke = 5, r = (size - stroke) / 2, c = size / 2;
        var blue = dark ? Color.FromArgb(255, 0x59, 0xb5, 0xdb) : Color.FromArgb(255, 0x1a, 0x7d, 0xa3);
        var green = dark ? Color.FromArgb(255, 0x4c, 0xc2, 0x6a) : Color.FromArgb(255, 0x2e, 0x9e, 0x4f);
        var g = new Grid { Width = size, Height = size, VerticalAlignment = VerticalAlignment.Center };
        g.Children.Add(new Ellipse { Width = size, Height = size, StrokeThickness = stroke, Stroke = new SolidColorBrush(dark ? Color.FromArgb(0x40, 0xff, 0xff, 0xff) : Color.FromArgb(0x30, 0, 0, 0)) });
        if (done || fraction >= 1)
        {
            g.Children.Add(new Ellipse { Width = size, Height = size, StrokeThickness = stroke, Stroke = new SolidColorBrush(done ? green : blue) });
        }
        else
        {
            var f = Math.Max(0.02, fraction);
            var a = 2 * Math.PI * f - Math.PI / 2;
            var figure = new PathFigure { StartPoint = new Point(c, c - r), IsClosed = false };
            figure.Segments.Add(new ArcSegment
            {
                Point = new Point(c + r * Math.Cos(a), c + r * Math.Sin(a)), Size = new Size(r, r),
                SweepDirection = SweepDirection.Clockwise, IsLargeArc = f > 0.5,
            });
            var geometry = new PathGeometry();
            geometry.Figures.Add(figure);
            g.Children.Add(new Microsoft.UI.Xaml.Shapes.Path
            {
                Data = geometry, Stroke = new SolidColorBrush(blue), StrokeThickness = stroke,
                StrokeStartLineCap = PenLineCap.Round, StrokeEndLineCap = PenLineCap.Round,
            });
        }
        if (done) g.Children.Add(new FontIcon { Glyph = "", FontSize = 14, Foreground = new SolidColorBrush(green), HorizontalAlignment = HorizontalAlignment.Center, VerticalAlignment = VerticalAlignment.Center });
        return g;
    }
}
