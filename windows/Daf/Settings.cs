using System.Text.Json;
using Daf.Core;
using Microsoft.Win32;

namespace Daf;

/// <summary>
/// The shell's own settings, in settings.json beside the page's storage
/// (%LOCALAPPDATA%\Daf). Daf's own preferences stay in the page, on the server.
/// </summary>
sealed class Settings
{
    public string? Base { get; set; }
    public bool Tray { get; set; } = true;
    /// <summary>Make a device token by itself once the window is signed in (off after Forget the Token).</summary>
    public bool AutoConnect { get; set; } = true;
    public int[]? WindowPlace { get; set; }
    /// <summary>The title bar's colour, as the page last said it (dafShell.bars), for the next start's first frame.</summary>
    public string? BarColor { get; set; }
    public bool BarDark { get; set; }
    public bool FeedNews { get; set; }
    public int FeedNewsCursor { get; set; } = -1;
    public string? Widget { get; set; }
    public DateTime? WidgetAt { get; set; }

    public static Settings Current { get; private set; } = new();
    static string File_ => Path.Join(App.DataDir, "settings.json");

    public static void Load()
    {
        try { Current = File.Exists(File_) ? JsonSerializer.Deserialize<Settings>(File.ReadAllBytes(File_)) ?? new() : new(); }
        catch (Exception e) { Log.Write($"settings: {e.Message}"); Current = new(); }
    }

    public static void Save()
    {
        try { CopyStore.Write(File_, JsonSerializer.SerializeToUtf8Bytes(Current, new JsonSerializerOptions { WriteIndented = true })); }
        catch (Exception e) { Log.Write($"settings: {e.Message}"); }
    }

    /// <summary>Daf's address: the self-test's, the one set in Settings, or https://daf.tiresia.xyz.</summary>
    public static Uri BaseUrl => Address.Normal(App.Options.Base) ?? Address.Normal(Current.Base) ?? new Uri(Address.Default);

    /// <summary>A new address. False if it isn't one Daf can use.</summary>
    public static bool SetBase(string text)
    {
        var u = Address.Normal(string.IsNullOrWhiteSpace(text) ? Address.Default : text);
        if (u == null) return false;
        if (u == BaseUrl) return true;
        Current.Base = u.AbsoluteUri;
        Save();
        BaseChanged?.Invoke();
        return true;
    }

    /// <summary>The address changed: windows load again, the notification area asks again.</summary>
    public static event Action? BaseChanged;

    // ---- opening at sign-in: the Run key, as Windows' Startup apps lists it -------------------

    const string RunKey = @"Software\Microsoft\Windows\CurrentVersion\Run";

    public static bool AtSignIn
    {
        get
        {
            using var key = Registry.CurrentUser.OpenSubKey(RunKey);
            return key?.GetValue("Daf") is string s && s.Contains(Environment.ProcessPath ?? "Daf.exe", StringComparison.OrdinalIgnoreCase);
        }
        set
        {
            if (App.Options.SelfTest) return;
            using var key = Registry.CurrentUser.CreateSubKey(RunKey);
            if (value) key.SetValue("Daf", $"\"{Environment.ProcessPath}\" --background");
            else key.DeleteValue("Daf", throwOnMissingValue: false);
        }
    }

    /// <summary>
    /// daf:// links open this Daf: the installer says so too, and this keeps it true for a
    /// copy unzipped anywhere, or after Daf moved. For this Windows user only.
    /// </summary>
    public static void RegisterLinks()
    {
        if (App.Options.SelfTest || Environment.ProcessPath is not { } exe) return;
        try
        {
            var command = $"\"{exe}\" \"%1\"";
            using var root = Registry.CurrentUser.CreateSubKey(@"Software\Classes\daf");
            if ((root.OpenSubKey(@"shell\open\command")?.GetValue("") as string) == command) return;
            root.SetValue("", "URL:Daf");
            root.SetValue("URL Protocol", "");
            using (var icon = root.CreateSubKey("DefaultIcon")) icon.SetValue("", $"\"{exe}\",0");
            using var cmd = root.CreateSubKey(@"shell\open\command");
            cmd.SetValue("", command);
        }
        catch (Exception e) { Log.Write($"daf:// links: {e.Message}"); }
    }
}
