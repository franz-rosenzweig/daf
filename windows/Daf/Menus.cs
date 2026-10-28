using System.Text.Json.Nodes;
using Daf.Core;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Automation.Peers;
using Microsoft.UI.Xaml.Automation.Provider;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Input;

namespace Daf;

/// <summary>
/// The menus in the title bar: the Mac's (mac/Daf/Menus.swift) with Ctrl for ⌘. Each
/// item calls the page's own command (window.dafCommand, docs/SHELL.md §3); what's greyed
/// and what Listen and the Shortlist say come from window.dafState(), asked when a menu is
/// pressed open and whenever the page moves. The page hears every key first, so an item
/// only shows its key: the keys with Ctrl reach the shell once the page leaves them alone
/// (Scripts.Shell), and the Reader's single letters are the page's, as in a browser, so
/// typing an "h" in a note stays an "h".
/// </summary>
sealed class Menus
{
    /// <summary>The commands run from the menus and the shell's keys, for the self-test.</summary>
    public static readonly List<string> Ran = [];

    readonly ShellWindow owner;
    readonly MenuBar bar;
    readonly List<(MenuFlyoutItem Item, string Command)> reader = [];
    MenuFlyoutItem? listen, star, forward;

    /// <summary>What the page said last.</summary>
    public JsonObject? State { get; private set; }

    public Menus(ShellWindow owner, MenuBar bar)
    {
        this.owner = owner;
        this.bar = bar;
        Build();
        foreach (var top in bar.Items)
            top.AddHandler(UIElement.PointerPressedEvent, new PointerEventHandler((_, _) => Refresh()), handledEventsToo: true);
    }

    public void Refresh() => _ = Update();

    /// <summary>Alt and a menu's letter opens that menu; Alt alone puts the keyboard on the first.</summary>
    public void Open(string? letter)
    {
        if (letter == null)
        {
            bar.Items.FirstOrDefault()?.Focus(FocusState.Keyboard);
            return;
        }
        var top = bar.Items.FirstOrDefault(m => string.Equals(m.AccessKey, letter, StringComparison.OrdinalIgnoreCase));
        if (top == null) return;
        Refresh();
        top.Focus(FocusState.Keyboard);
        if (FrameworkElementAutomationPeer.CreatePeerForElement(top) is IExpandCollapseProvider menu) menu.Expand();
    }

    /// <summary>The page's state, into the items that depend on it.</summary>
    public async Task Update()
    {
        var s = await owner.State();
        State = s;
        var can = s?["can"] as JsonObject;
        var keys = s?["keys"] as JsonObject;
        foreach (var (item, command) in reader)
        {
            item.IsEnabled = owner.Start == null && J.Bool(can?[command]);
            if (keys?[command] is JsonValue k && k.TryGetValue(out string? key)) item.KeyboardAcceleratorTextOverride = Shown(key);
        }
        if (listen != null) listen.Text = J.Bool(s?["listening"]) ? "Stop Listening" : "Listen";
        if (star != null) star.Text = J.Bool(s?["starred"]) ? "Remove from Shortlist" : "Add to Shortlist";
        if (forward != null) forward.IsEnabled = owner.Core?.CanGoForward == true;
    }

    /// <summary>A key as Preferences → Keyboard binds it, the way a menu shows it: "J" is Shift+J, the arrows are arrows.</summary>
    public static string Shown(string key) => key switch
    {
        "" => "",
        "ArrowRight" => "→",
        "ArrowLeft" => "←",
        "ArrowUp" => "↑",
        "ArrowDown" => "↓",
        " " => "Space",
        _ when key.Length == 1 && char.IsLetter(key[0]) && char.IsUpper(key[0]) => "Shift+" + key,
        _ => key.Length == 1 ? key.ToLowerInvariant() : key,
    };

    void Build()
    {
        var file = Top("File", "F");
        Shell(file, "New Window", () => ShellWindow.Open(), "Ctrl+N");
        Line(file);
        Page(file, "Add to Daf…", "add", "Ctrl+O");
        Shell(file, "Save a Link…", () => _ = SaveLink.Ask(), "Ctrl+Shift+S");
        Page(file, "Log Paper Minutes…", "paper", "Ctrl+Shift+P");
        Page(file, "Export Highlights…", "export", "Ctrl+Shift+E");
        Line(file);
        Shell(file, "Settings…", SettingsWindow.Show, "Ctrl+,");
        Line(file);
        Shell(file, "Close Window", owner.Close, "Ctrl+W");
        Shell(file, "Exit Daf", App.Quit);

        var view = Top("View", "V");
        foreach (var (title, place, n) in new[] { ("Today", "today", 1), ("Review", "review", 2), ("Library", "library", 3), ("Feed", "feed", 4), ("Highlights", "highlights", 5), ("Books", "books", 6), ("Stats", "stats", 7) })
            Page(view, title, "go:" + place, $"Ctrl+{n}");
        Page(view, "Shortlist", "go:library/starred");
        Page(view, "Torah", "go:torah");
        Page(view, "Paper Pages", "go:paper");
        Page(view, "Reading Goals…", "go:prefs/goals");
        Page(view, "Preferences", "go:prefs");
        Line(view);
        ReaderItem(view, "Contents", "toc");
        ReaderItem(view, "Side Panel", "panel");
        ReaderItem(view, "Typography", "aa");
        Line(view);
        Shell(view, "Reload Page", owner.Reload, "Ctrl+R");
        Shell(view, "Full Screen", () => owner.FullScreen(!owner.IsFullScreen), "F11");

        var go = Top("Go", "G");
        Shell(go, "Back", owner.Back, "Alt+←");
        forward = Shell(go, "Forward", owner.Forward, "Alt+→");
        Line(go);
        Page(go, "Search", "search", "Ctrl+K");

        var readerMenu = Top("Reader", "R");
        ReaderItem(readerMenu, "Highlight", "highlight", "h");
        ReaderItem(readerMenu, "Highlight with a Note", "note", "n");
        ReaderItem(readerMenu, "Bookmark This Page", "bookmark", "b");
        listen = ReaderItem(readerMenu, "Listen", "listen");
        star = ReaderItem(readerMenu, "Add to Shortlist", "star", "f");
        ReaderItem(readerMenu, "Tags…", "tag", "t");
        ReaderItem(readerMenu, "Delete", "delete", "d");
        Line(readerMenu);
        ReaderItem(readerMenu, "Next", "next", "→");
        ReaderItem(readerMenu, "Previous", "prev", "←");
        ReaderItem(readerMenu, "Next in the List", "nextdoc", "Shift+J");
        ReaderItem(readerMenu, "Previous in the List", "prevdoc", "Shift+K");

        var help = Top("Help", "H");
        Page(help, "Keyboard Shortcuts", "keys");
        Page(help, "Send Feedback…", "feedback");
        Line(help);
        Shell(help, "The Windows App", () => Outside.Open(new Uri("https://github.com/franz-rosenzweig/daf/blob/master/docs/windows.md")));
        Shell(help, "About Daf", () => _ = Dialogs.Tell("Daf", $"Daf for Windows {App.Version}.\nThe page is Daf at {Settings.BaseUrl.GetLeftPart(UriPartial.Authority)}.\nhttps://github.com/franz-rosenzweig/daf"));
    }

    // ---- the kinds of item ---------------------------------------------------------------------

    IList<MenuFlyoutItemBase> Top(string title, string accessKey)
    {
        var menu = new MenuBarItem { Title = title, AccessKey = accessKey };
        bar.Items.Add(menu);
        return menu.Items;
    }

    static void Line(IList<MenuFlyoutItemBase> into) => into.Add(new MenuFlyoutSeparator());

    /// <summary>An item that runs one of the page's commands, anywhere in Daf.</summary>
    MenuFlyoutItem Page(IList<MenuFlyoutItemBase> into, string text, string command, string? key = null)
    {
        var item = new MenuFlyoutItem { Text = text };
        if (key != null) item.KeyboardAcceleratorTextOverride = key;
        item.Click += (_, _) => { Ran.Add(command); owner.FocusPage(); _ = owner.Run(command); };
        into.Add(item);
        return item;
    }

    /// <summary>An item for an article or a book, greyed where it doesn't apply (dafState().can).</summary>
    MenuFlyoutItem ReaderItem(IList<MenuFlyoutItemBase> into, string text, string command, string? key = null)
    {
        var item = Page(into, text, command, key);
        item.IsEnabled = false;
        reader.Add((item, command));
        return item;
    }

    /// <summary>An item the shell answers itself.</summary>
    MenuFlyoutItem Shell(IList<MenuFlyoutItemBase> into, string text, Action act, string? key = null)
    {
        var item = new MenuFlyoutItem { Text = text };
        if (key != null) item.KeyboardAcceleratorTextOverride = key;
        item.Click += (_, _) => { owner.FocusPage(); act(); };
        into.Add(item);
        return item;
    }

    /// <summary>Whether an item for a command is enabled now, for the self-test.</summary>
    public bool Enabled(string command) => reader.FirstOrDefault(r => r.Command == command).Item?.IsEnabled ?? true;
}
