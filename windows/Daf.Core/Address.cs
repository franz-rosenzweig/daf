namespace Daf.Core;

/// <summary>
/// Where Daf is (the Mac's Server in mac/Daf/Server.swift). The window loads the live
/// site (docs/SHELL.md); the address is a setting, with the public one as the default
/// and a tailnet one (http://&lt;server&gt;:8440) as the other.
/// </summary>
public static class Address
{
    public const string Default = "https://daf.tiresia.xyz";

    /// <summary>The app's own copy of Daf, for no connection (LocalCopy): .example is reserved, so no real site is ever there.</summary>
    public const string CopyOrigin = "https://daf-app.example";

    /// <summary>An address as Daf keeps it: http or https, a host, a port if any, no path. Null if it isn't one.</summary>
    public static Uri? Normal(string? text)
    {
        if (string.IsNullOrWhiteSpace(text) || !Uri.TryCreate(text.Trim(), UriKind.Absolute, out var u)) return null;
        if (u.Scheme is not ("http" or "https") || u.Host.Length == 0) return null;
        var b = new UriBuilder(u.Scheme, u.Host, u.IsDefaultPort ? -1 : u.Port);
        return new Uri(b.Uri.GetLeftPart(UriPartial.Authority));
    }

    /// <summary>A page of the app ("#today"), or a path on the server ("/api/save").</summary>
    public static Uri Url(Uri baseUrl, string where)
    {
        var root = baseUrl.GetLeftPart(UriPartial.Authority);
        if (where.StartsWith('#')) return new Uri(root + "/" + where);
        return new Uri(root + (where.StartsWith('/') ? where : "/" + where));
    }

    /// <summary>The origin of an address, as a page's location.origin says it.</summary>
    public static string Origin(Uri u) => u.GetLeftPart(UriPartial.Authority);

    /// <summary>A page the window may show: Daf's own origin, or the app's copy.</summary>
    public static bool IsOurs(Uri u, Uri baseUrl) =>
        string.Equals(Origin(u), CopyOrigin, StringComparison.OrdinalIgnoreCase) || IsDaf(u, baseUrl);

    /// <summary>Daf's own origin: the same scheme, host and port as the address.</summary>
    public static bool IsDaf(Uri u, Uri baseUrl) =>
        u.Scheme == baseUrl.Scheme && string.Equals(u.Host, baseUrl.Host, StringComparison.OrdinalIgnoreCase) && u.Port == baseUrl.Port;

    public static bool IsCopy(Uri? u) => u != null && string.Equals(Origin(u), CopyOrigin, StringComparison.OrdinalIgnoreCase);

    /// <summary>The page's route, "#today", from either address; null without one.</summary>
    public static string? Route(Uri? u) => u == null || u.Fragment.Length <= 1 ? null : u.Fragment;
}
