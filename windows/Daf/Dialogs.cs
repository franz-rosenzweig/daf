using Microsoft.UI.Windowing;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Input;
using Windows.Graphics;
using Windows.System;
using WinRT.Interop;

namespace Daf;

/// <summary>
/// The shell's own small questions and messages (Save a Link…, what went wrong), each in a
/// small window of its own, so they work with no Daf window open (from the notification area too).
/// </summary>
static class Dialogs
{
    /// <summary>A question with a box to type in: what was typed, or null if cancelled.</summary>
    public static Task<string?> Ask(string title, string text, string placeholder, string? value, string ok)
    {
        var done = new TaskCompletionSource<string?>();
        var box = new TextBox { PlaceholderText = placeholder, Text = value ?? "" };
        var window = Make(title, text, box, ok, "Cancel", button => done.TrySetResult(button == 0 ? box.Text : null));
        box.KeyDown += (_, e) =>
        {
            if (e.Key != VirtualKey.Enter) return;
            e.Handled = true;
            done.TrySetResult(box.Text);
            window.Close();
        };
        window.Activated += (_, _) => box.Focus(FocusState.Programmatic);
        return done.Task;
    }

    /// <summary>A message with OK, and another button if <paramref name="other"/>: true when that one was pressed.</summary>
    public static Task<bool> Tell(string title, string text, string? other = null)
    {
        var done = new TaskCompletionSource<bool>();
        if (App.Options.SelfTest)
        {
            Log.Write($"{title}: {text}");
            done.SetResult(false);
            return done.Task;
        }
        Make(title, text, null, other ?? "OK", other != null ? "OK" : null, button => done.TrySetResult(other != null && button == 0));
        return done.Task;
    }

    /// <summary>The window: a title, the words, maybe a box, one or two buttons (0 the first, 1 the second, -1 closed).</summary>
    static Window Make(string title, string text, UIElement? extra, string first, string? second, Action<int> answered)
    {
        var window = new Window { Title = title };
        var given = false;
        void Answer(int button)
        {
            if (given) return;
            given = true;
            answered(button);
        }
        var panel = new StackPanel { Spacing = 12, Padding = new Thickness(24, 20, 24, 20) };
        panel.Children.Add(new TextBlock { Text = title, Style = (Style)Application.Current.Resources["SubtitleTextBlockStyle"], TextWrapping = TextWrapping.Wrap });
        panel.Children.Add(new TextBlock { Text = text, TextWrapping = TextWrapping.Wrap, IsTextSelectionEnabled = true });
        if (extra != null) panel.Children.Add(extra);
        var buttons = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 8, HorizontalAlignment = HorizontalAlignment.Right, Margin = new Thickness(0, 8, 0, 0) };
        var one = new Button { Content = first, Style = (Style)Application.Current.Resources["AccentButtonStyle"], MinWidth = 96 };
        one.Click += (_, _) => { Answer(0); window.Close(); };
        buttons.Children.Add(one);
        if (second != null)
        {
            var two = new Button { Content = second, MinWidth = 96 };
            two.Click += (_, _) => { Answer(1); window.Close(); };
            buttons.Children.Add(two);
        }
        panel.Children.Add(buttons);
        panel.KeyDown += (_, e) =>
        {
            if (e.Key != VirtualKey.Escape) return;
            e.Handled = true;
            window.Close();
        };
        window.Content = panel;
        window.SystemBackdrop = new Microsoft.UI.Xaml.Media.MicaBackdrop();
        window.Closed += (_, _) => Answer(-1);
        var handle = WindowNative.GetWindowHandle(window);
        var scale = Win32.Scale(handle);
        if (window.AppWindow.Presenter is OverlappedPresenter p)
        {
            p.IsResizable = false;
            p.IsMaximizable = false;
            p.IsMinimizable = false;
        }
        var icon = Path.Join(AppContext.BaseDirectory, "Assets", "Daf.ico");
        if (File.Exists(icon)) window.AppWindow.SetIcon(icon);
        var size = new SizeInt32((int)(440 * scale), (int)((extra != null ? 250 : 210) * scale));
        var area = DisplayArea.GetFromWindowId(ShellWindow.Front?.AppWindow.Id ?? window.AppWindow.Id, DisplayAreaFallback.Primary).WorkArea;
        window.AppWindow.MoveAndResize(new RectInt32(area.X + (area.Width - size.Width) / 2, area.Y + (area.Height - size.Height) / 3, size.Width, size.Height));
        window.Activate();
        Win32.SetForegroundWindow(handle);
        return window;
    }
}
