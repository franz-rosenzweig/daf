using System.Text;
using System.Text.RegularExpressions;

namespace Daf.Core;

/// <summary>
/// A daf:// link, from anywhere on the PC (a shortcut, a bookmarklet, another app):
/// <c>daf://save?url=…&amp;title=…&amp;text=…</c> saves a link to the Library, and
/// <c>daf://go/review</c> (or any page of Daf) opens Daf there. The Mac's are in
/// mac/Daf/DafApp.swift and SaveLink.swift.
/// </summary>
public sealed record DafLink(string Kind, string? Url = null, string? Title = null, string? Text = null, string? Route = null)
{
    /// <summary>The link in a command line or an activation's arguments, or null when there is none.</summary>
    public static DafLink? Find(string? commandLine)
    {
        if (string.IsNullOrEmpty(commandLine)) return null;
        var m = Regex.Match(commandLine, "daf:[^\\s\"]+", RegexOptions.IgnoreCase);
        return m.Success ? Parse(m.Value) : null;
    }

    public static DafLink? Parse(string text)
    {
        if (!Uri.TryCreate(text.Trim(), UriKind.Absolute, out var u) || !u.Scheme.Equals("daf", StringComparison.OrdinalIgnoreCase)) return null;
        switch (u.Host.ToLowerInvariant())
        {
            case "save":
            {
                var q = Query(u.Query);
                var link = q.GetValueOrDefault("url") is { Length: > 0 } given ? given : Links.FirstLink(q.GetValueOrDefault("text"));
                return new DafLink("save", link, q.GetValueOrDefault("title"), q.GetValueOrDefault("text"));
            }
            case "go":
            {
                var route = Uri.UnescapeDataString(u.AbsolutePath.Trim('/'));
                return route.Length == 0 ? null : new DafLink("go", Route: route);
            }
            default:
                return null;
        }
    }

    /// <summary>A query's names and values, decoded; the first of each name counts.</summary>
    public static Dictionary<string, string> Query(string query)
    {
        var d = new Dictionary<string, string>();
        foreach (var part in query.TrimStart('?').Split('&', StringSplitOptions.RemoveEmptyEntries))
        {
            var i = part.IndexOf('=');
            var name = Uri.UnescapeDataString(i < 0 ? part : part[..i]);
            var value = i < 0 ? "" : Uri.UnescapeDataString(part[(i + 1)..].Replace('+', ' '));
            d.TryAdd(name, value);
        }
        return d;
    }
}

public static class Links
{
    /// <summary>The first http(s) address in a piece of text.</summary>
    public static string? FirstLink(string? text)
    {
        if (string.IsNullOrWhiteSpace(text)) return null;
        var m = Regex.Match(text.Trim(), @"https?://\S+");
        return m.Success ? m.Value : null;
    }

    /// <summary>
    /// The name this PC's device token goes by in Daf (POST /api/devices): "windows-" and the
    /// PC's name, lower case, letters, digits and dashes, 24 at most, so two PCs don't take
    /// each other's token. Preferences → Account shows it as "Daf for Windows · DESKTOP".
    /// </summary>
    public static string DeviceName(string? machine)
    {
        var sb = new StringBuilder();
        foreach (var c in (machine ?? "").ToLowerInvariant())
        {
            if (c is >= 'a' and <= 'z' or >= '0' and <= '9') sb.Append(c);
            else if ((c == '-' || c == '_' || c == ' ' || c == '.') && sb.Length > 0 && sb[^1] != '-') sb.Append('-');
        }
        var name = sb.ToString().Trim('-');
        if (name.Length == 0) return "windows";
        name = name.Length > 16 ? name[..16].TrimEnd('-') : name;
        return "windows-" + name;
    }
}
