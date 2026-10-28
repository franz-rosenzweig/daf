using Daf.Core;
using Microsoft.Windows.AppNotifications;
using Microsoft.Windows.AppNotifications.Builder;

namespace Daf;

/// <summary>
/// New posts from the feeds set to notify (the Feed's sources sheet → a feed → "Notify me
/// of new posts"), as Windows notifications. The notification area's five-minute look
/// (Today.Refresh) asks /api/phone/feed-news with this PC's token; a click opens the post
/// in Daf. The cursor is Daf's own order of arrival, so nothing rings twice and the
/// backlog never does. It stops by itself once no feed is set to notify. The Mac's is mac/Daf/FeedNews.swift.
/// </summary>
static class FeedNews
{
    /// <summary>The posts shown, for the self-test.</summary>
    public static readonly List<string> Shown = [];
    static bool registered;

    public static bool On => Settings.Current.FeedNews;

    /// <summary>Windows' notifications for Daf, and their clicks (also when a click starts Daf).</summary>
    public static void Install()
    {
        try
        {
            AppNotificationManager.Default.NotificationInvoked += (_, e) =>
            {
                var args = new Dictionary<string, string>(e.Arguments);
                App.Queue?.TryEnqueue(() => Open(args));
            };
            AppNotificationManager.Default.Register();
            registered = true;
        }
        catch (Exception e) { Log.Write($"notifications: {e.Message}"); }
    }

    /// <summary>Windows lets Daf notify (Settings → System → Notifications).</summary>
    public static bool Allowed
    {
        get
        {
            try { return registered && AppNotificationManager.IsSupported() && AppNotificationManager.Default.Setting == AppNotificationSetting.Enabled; }
            catch (Exception) { return false; }
        }
    }

    /// <summary>The page asks (dafShell.alerts): from now on the five-minute look includes this. True if Windows lets Daf notify.</summary>
    public static async Task<bool> Start()
    {
        Settings.Current.FeedNews = true;
        Settings.Save();
        await Check();
        return Allowed;
    }

    public static async Task Check()
    {
        if (!On) return;
        var cursor = Settings.Current.FeedNewsCursor;
        FeedNewsAnswer r;
        try { r = await App.Client.GetFeedNews(cursor); }
        catch (Exception) { return; }
        if (r.Feeds == 0)
        {
            // nothing set to notify any more
            Settings.Current.FeedNews = false;
            Settings.Current.FeedNewsCursor = -1;
            Settings.Save();
            return;
        }
        if (cursor >= 0)
            foreach (var item in r.Items)
                Show(new AppNotificationBuilder().AddArgument("route", item.Route).AddText(item.Title).AddText(item.Source).BuildNotification(), item.Id);
        Settings.Current.FeedNewsCursor = r.Cursor;
        Settings.Save();
    }

    /// <summary>"Saved to Daf", quietly, after Save a Link and daf://save.</summary>
    public static void Saved(string link) =>
        Show(new AppNotificationBuilder().AddArgument("route", "#library").AddText("Saved to Daf").AddText(link).MuteAudio().BuildNotification(), "saved");

    static void Show(AppNotification n, string id)
    {
        lock (Shown) Shown.Add(id);
        if (!registered || App.Options.SelfTest) return;
        try
        {
            n.Tag = id.Length > 60 ? id[..60] : id;
            n.Group = id == "saved" ? "saved" : "feed";
            AppNotificationManager.Default.Show(n);
        }
        catch (Exception e) { Log.Write($"a notification: {e.Message}"); }
    }

    /// <summary>A notification was clicked: its post in Daf.</summary>
    public static void Open(IDictionary<string, string> args)
    {
        var route = args.TryGetValue("route", out var r) && r.Length > 0 ? r : null;
        ShellWindow.Show(route == null ? null : route.StartsWith('#') ? route : "#" + route);
    }
}
