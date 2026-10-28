using System.Runtime.InteropServices;
using System.Text.Json.Nodes;
using Daf.Core;

namespace Daf;

/// <summary>
/// The command line: nothing for a person, --background at sign-in (the notification area
/// only), a daf:// link, and the self-test's switches for windows/selftest.ps1.
/// </summary>
public sealed record Options(bool SelfTest, bool Background, string? Data, string? Base, string? Cookie, string? Token,
    string? Out, string? SaveDir, string? ServerControl, bool DevTools, DafLink? Link)
{
    public static Options Parse(string[] args)
    {
        string? Value(string name)
        {
            var i = Array.IndexOf(args, name);
            return i >= 0 && i + 1 < args.Length ? args[i + 1] : null;
        }
        return new(args.Contains("--selftest"), args.Contains("--background"), Value("--data"), Value("--base"), Value("--cookie"), Value("--token"),
            Value("--out"), Value("--save-dir"), Value("--server-control"), args.Contains("--devtools"),
            args.Select(DafLink.Parse).FirstOrDefault(l => l != null));
    }
}

/// <summary>daf.log, beside the settings: what went wrong where nobody saw it.</summary>
static class Log
{
    static readonly object Gate = new();

    public static void Write(string line)
    {
        System.Diagnostics.Debug.WriteLine(line);
        try
        {
            lock (Gate) File.AppendAllText(Path.Join(App.DataDir, "daf.log"), $"{DateTime.Now:O} {line}{Environment.NewLine}");
        }
        catch (Exception) { }
    }
}

/// <summary>The browser, Mail or Obsidian, for anything that isn't Daf. The self-test only notes it.</summary>
static class Outside
{
    public static readonly List<Uri> Opened = [];
    static readonly HashSet<string> Schemes = ["http", "https", "mailto", "obsidian"];

    public static bool Open(Uri url)
    {
        if (!Schemes.Contains(url.Scheme.ToLowerInvariant())) return false;
        lock (Opened) Opened.Add(url);
        if (!App.Options.SelfTest) _ = Windows.System.Launcher.LaunchUriAsync(url);
        return true;
    }

    public static bool Saw(string url)
    {
        lock (Opened) return Opened.Any(u => u.OriginalString == url || u.AbsoluteUri == url);
    }
}

/// <summary>The little JSON the window and the page pass each other.</summary>
static class J
{
    public static string? Text(JsonNode? node) => node is JsonValue v && v.TryGetValue(out string? s) ? s : null;

    public static int Int(JsonNode? node) =>
        node is JsonValue v ? (v.TryGetValue(out int i) ? i : v.TryGetValue(out double d) ? (int)d : 0) : 0;

    public static bool Bool(JsonNode? node) => node is JsonValue v && v.TryGetValue(out bool b) && b;

    /// <summary>A string as a JavaScript (and JSON) literal.</summary>
    public static string Quote(string s) => JsonValue.Create(s)!.ToJsonString();
}

sealed class ShellError(string message) : Exception(message);

static class Win32
{
    [DllImport("user32.dll")]
    public static extern bool MessageBeep(uint type);

    [DllImport("user32.dll")]
    public static extern uint GetDpiForWindow(IntPtr window);

    [DllImport("user32.dll")]
    public static extern bool SetForegroundWindow(IntPtr window);

    [StructLayout(LayoutKind.Sequential)]
    public struct POINT { public int X, Y; }

    [DllImport("user32.dll")]
    public static extern bool GetCursorPos(out POINT point);

    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    public static extern IntPtr FindWindow(string? className, string? windowName);

    /// <summary>"Nowhere to go" (Back at the first page), as Windows says it.</summary>
    public static void Beep() => MessageBeep(0);

    public static double Scale(IntPtr window) => Math.Max(1, GetDpiForWindow(window)) / 96.0;
}
