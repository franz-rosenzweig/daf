using Daf.Core;
using Windows.ApplicationModel.DataTransfer;

namespace Daf;

/// <summary>
/// Saving a link to Daf's Library (POST /api/save, with the device token): from File ›
/// Save a Link…, from the notification area, and from daf://save?url=…&amp;title=…, which
/// anything on the PC can open (a bookmarklet, a shortcut). The Mac's is mac/Daf/SaveLink.swift.
/// </summary>
static class SaveLink
{
    /// <summary>What was saved, for the self-test.</summary>
    public static readonly List<string> Saved = [];

    /// <summary>Save a Link…: an address, with the one on the clipboard filled in.</summary>
    public static async Task Ask()
    {
        string? clip = null;
        try
        {
            var content = Clipboard.GetContent();
            if (content.Contains(StandardDataFormats.Text)) clip = Links.FirstLink(await content.GetTextAsync());
        }
        catch (Exception) { }
        var typed = await Dialogs.Ask("Save a link to Daf", "It goes to your Library.", "https://", clip, "Save");
        if (typed == null) return;
        if (Links.FirstLink(typed) is not { } link)
        {
            await Fail("That isn't a link.");
            return;
        }
        await Save(link, null, null);
    }

    public static async Task Save(string? link, string? title, string? text)
    {
        if (string.IsNullOrEmpty(link))
        {
            await Fail("There was no link to save.");
            return;
        }
        try
        {
            await App.Client.Save(link, title, text);
            lock (Saved) Saved.Add(link);
            FeedNews.Saved(link);
        }
        catch (DafFailure f)
        {
            // a missing or refused token is fixed in Settings; a Daf that didn't answer isn't
            await Fail(f.Message, settings: f.Kind != "unreachable");
        }
    }

    static async Task Fail(string why, bool settings = false)
    {
        Log.Write($"not saved: {why}");
        if (App.Options.SelfTest) return;
        if (await Dialogs.Tell("Daf didn't save the link", why, settings ? "Open Settings" : null)) SettingsWindow.Show();
    }
}
