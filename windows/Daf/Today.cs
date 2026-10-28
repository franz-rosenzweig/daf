using System.Text.Json;
using Daf.Core;
using Microsoft.UI.Dispatching;
using Microsoft.Windows.System.Power;

namespace Daf;

/// <summary>
/// Today's minutes, from /api/phone/widget with the device token (the Mac's Today in
/// mac/Daf/MenuBar.swift). Asked every five minutes, when the PC wakes and when the
/// panel opens; the last answer is kept, so with no connection the notification area
/// shows what it last knew, dimmed after twenty minutes.
/// </summary>
static class Today
{
    public static Widget? Last { get; private set; }
    /// <summary>When Daf last answered.</summary>
    public static DateTime? At { get; private set; }
    /// <summary>Why the last ask failed, if it did.</summary>
    public static string? Problem { get; private set; }
    public static bool NoToken { get; private set; }

    /// <summary>A new answer, or a new reason there wasn't one.</summary>
    public static event Action? Changed;

    static DispatcherQueueTimer? timer;
    static bool asking;

    public static void Start()
    {
        if (Settings.Current.Widget is { } json)
        {
            Last = Widget.Parse(json);
            At = Settings.Current.WidgetAt;
        }
        var queue = App.Queue!;
        timer = queue.CreateTimer();
        timer.Interval = TimeSpan.FromMinutes(5);
        timer.IsRepeating = true;
        timer.Tick += async (_, _) => await Refresh();
        timer.Start();
        PowerManager.SystemSuspendStatusChanged += (_, _) =>
        {
            if (PowerManager.SystemSuspendStatus is SystemSuspendStatus.AutoResume or SystemSuspendStatus.ManualResume)
                queue.TryEnqueue(async () =>
                {
                    await Task.Delay(3000);       // the network comes back a moment after the screen
                    await Refresh();
                });
        };
        Settings.BaseChanged += () => _ = Refresh();
        _ = Refresh();
    }

    /// <summary>The last answer is old: more than twenty minutes, or none yet.</summary>
    public static bool Stale => At is not { } at || DateTime.UtcNow - at.ToUniversalTime() > TimeSpan.FromMinutes(20);

    public static async Task Refresh()
    {
        if (asking) return;
        asking = true;
        try
        {
            var w = await App.Client.GetWidget();
            Last = w;
            At = DateTime.UtcNow;
            Problem = null;
            NoToken = false;
            Settings.Current.Widget = JsonSerializer.Serialize(w);
            Settings.Current.WidgetAt = At;
            Settings.Save();
        }
        catch (DafFailure f) when (f.Kind == "token")
        {
            NoToken = true;
            Problem = null;
        }
        catch (DafFailure f) when (f.Kind == "unknown")
        {
            // disconnected in Preferences → Account: it stays so until Connect in Settings
            App.Token.Set(null);
            Settings.Current.AutoConnect = false;
            Settings.Save();
            NoToken = true;
            Problem = f.Message;
        }
        catch (Exception e)
        {
            Problem = e.Message;
        }
        finally { asking = false; }
        Changed?.Invoke();
        await FeedNews.Check();
    }

    /// <summary>"Offline, as of 10:42", or why there are no minutes; null when there's nothing to say.</summary>
    public static string? Note
    {
        get
        {
            if (NoToken) return "Connect this PC in Settings to see today's minutes here.";
            if (Problem == null && !(Last != null && Stale)) return null;
            if (At is not { } at) return "Offline";
            var local = at.ToLocalTime();
            return "Offline, as of " + (local.Date == DateTime.Today ? local.ToString("t") : local.ToString("g"));
        }
    }
}
