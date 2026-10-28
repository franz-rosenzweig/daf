using System.Net;
using System.Net.Http.Headers;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Text.Json.Serialization;

namespace Daf.Core;

/// <summary>/api/phone/widget: today's minutes, the day's highlight, the nightstand (docs/NATIVE.md).</summary>
public sealed class Widget
{
    public sealed class Highlight
    {
        [JsonPropertyName("text")] public string Text { get; set; } = "";
        [JsonPropertyName("title")] public string? Title { get; set; }
    }

    /// <summary>One of the goals in Preferences → Goals; Main is the one the ring follows.</summary>
    public sealed class Goal
    {
        [JsonPropertyName("id")] public string Id { get; set; } = "";
        [JsonPropertyName("kind")] public string Kind { get; set; } = "";
        [JsonPropertyName("label")] public string? Label { get; set; }
        [JsonPropertyName("done")] public double Done { get; set; }
        [JsonPropertyName("target")] public double Target { get; set; }
        [JsonPropertyName("period")] public string Period { get; set; } = "";
        [JsonPropertyName("period_label")] public string? PeriodLabel { get; set; }
        [JsonPropertyName("met")] public bool? Met { get; set; }
        [JsonPropertyName("pct")] public double? Pct { get; set; }
        [JsonPropertyName("text")] public string? Text { get; set; }
        /// <summary>Minutes a day: the hour's own goal, shown the way it always was.</summary>
        [JsonIgnore] public bool IsDailyMinutes => Kind == "minutes" && Period == "day";
    }

    public sealed class Book
    {
        [JsonPropertyName("id")] public string Id { get; set; } = "";
        [JsonPropertyName("title")] public string Title { get; set; } = "";
        [JsonPropertyName("progress")] public double? Progress { get; set; }
    }

    [JsonPropertyName("date")] public string Date { get; set; } = "";
    [JsonPropertyName("minutes")] public double Minutes { get; set; }
    [JsonPropertyName("goal")] public double GoalMinutes { get; set; } = 60;
    [JsonPropertyName("year_day")] public double? YearDay { get; set; }
    [JsonPropertyName("year_hours")] public double? YearHours { get; set; }
    [JsonPropertyName("highlight")] public Highlight? Today { get; set; }
    [JsonPropertyName("nightstand")] public List<Book>? Nightstand { get; set; }
    [JsonPropertyName("main")] public Goal? Main { get; set; }

    public static Widget? Parse(string json)
    {
        try { return JsonSerializer.Deserialize<Widget>(json); }
        catch (JsonException) { return null; }
    }

    // What the notification area and its panel say (the Mac's Today and MenuBar).

    /// <summary>The main goal met (Preferences → Goals), or the day's minutes for an older Daf.</summary>
    [JsonIgnore] public bool Done => Main is { } m ? m.Met ?? m.Done >= m.Target : Minutes >= GoalMinutes;

    /// <summary>How far along the main goal is, 0 to 1.</summary>
    [JsonIgnore]
    public double Fraction => Main is { } m
        ? Math.Clamp((m.Pct ?? (m.Target > 0 ? 100 * m.Done / m.Target : 0)) / 100, 0, 1)
        : GoalMinutes > 0 ? Math.Clamp(Minutes / GoalMinutes, 0, 1) : 0;

    /// <summary>"38′", "60′ ✓", or another main goal as "33/200".</summary>
    [JsonIgnore]
    public string Short
    {
        get
        {
            var check = Done ? " ✓" : "";
            if (Main is { IsDailyMinutes: false } m) return $"{(int)m.Done}/{(int)m.Target}{check}";
            return $"{(int)Minutes}′{check}";
        }
    }

    /// <summary>"38 of 60 minutes today", or the main goal's own words.</summary>
    [JsonIgnore] public string Line => Main?.Text is { Length: > 0 } t ? t : $"{(int)Minutes} of {(int)GoalMinutes} minutes today";

    /// <summary>What to say once it's met: "That's the hour." only while the goal is the hour.</summary>
    [JsonIgnore]
    public string MetLine
    {
        get
        {
            if (Main is not { } m || (m.IsDailyMinutes && m.Target == 60)) return "That's the hour.";
            return (m.PeriodLabel ?? "") switch
            {
                "today" => "That's today's goal.",
                "this week" => "That's this week's goal.",
                "this month" => "That's this month's goal.",
                "this year" => "That's this year's goal.",
                _ => "That's the goal.",
            };
        }
    }

    /// <summary>"Year 30, day 19", and the day's minutes when the line above doesn't say them.</summary>
    [JsonIgnore]
    public string Subtitle
    {
        get
        {
            var parts = new List<string>();
            if (Done || Main is { IsDailyMinutes: false }) parts.Add($"{(int)Minutes} minutes today");
            if (YearDay is { } d) parts.Add($"Year 30, day {(int)d}");
            return string.Join(" · ", parts);
        }
    }
}

/// <summary>/api/phone/feed-news: new posts in the feeds set to notify.</summary>
public sealed class FeedNewsAnswer
{
    public sealed class Item
    {
        [JsonPropertyName("id")] public string Id { get; set; } = "";
        [JsonPropertyName("title")] public string Title { get; set; } = "";
        [JsonPropertyName("source")] public string Source { get; set; } = "";
        [JsonPropertyName("route")] public string Route { get; set; } = "";
    }

    [JsonPropertyName("cursor")] public int Cursor { get; set; }
    [JsonPropertyName("feeds")] public int Feeds { get; set; }
    [JsonPropertyName("items")] public List<Item> Items { get; set; } = [];
}

/// <summary>Why a call to Daf with the device token didn't work.</summary>
public sealed class DafFailure(string kind, string message) : Exception(message)
{
    /// <summary>"token" (none yet), "refused" (Daf said no; "unknown" for a token Daf doesn't know), or "unreachable".</summary>
    public string Kind { get; } = kind;
}

/// <summary>
/// The endpoints the native parts use with the device token (docs/NATIVE.md), never the
/// window's cookie. The Mac's are Client in mac/Daf/Server.swift.
/// </summary>
public sealed class DafClient(HttpClient http, Func<Uri> baseUrl, Func<string?> token, string userAgent)
{
    public async Task<Widget> GetWidget()
    {
        var json = await Request("/api/phone/widget");
        return Widget.Parse(json) ?? throw new DafFailure("refused", "Daf's answer wasn't the minutes");
    }

    public async Task<FeedNewsAnswer> GetFeedNews(int cursor)
    {
        var json = await Request("/api/phone/feed-news" + (cursor >= 0 ? $"?cursor={cursor}" : ""));
        return JsonSerializer.Deserialize<FeedNewsAnswer>(json) ?? new FeedNewsAnswer();
    }

    public Task Save(string url, string? title = null, string? text = null)
    {
        var body = new JsonObject { ["url"] = url };
        if (!string.IsNullOrEmpty(title)) body["title"] = title;
        if (!string.IsNullOrEmpty(text)) body["text"] = text;
        return Request("/api/save", body);
    }

    async Task<string> Request(string path, JsonObject? json = null)
    {
        var t = token() ?? throw new DafFailure("token", "This PC isn't connected to Daf yet. Sign in to Daf in its window, or connect it in Settings.");
        using var r = new HttpRequestMessage(json == null ? HttpMethod.Get : HttpMethod.Post, Address.Url(baseUrl(), path));
        r.Headers.Authorization = new AuthenticationHeaderValue("Bearer", t);
        r.Headers.TryAddWithoutValidation("User-Agent", userAgent);
        if (json != null) r.Content = new StringContent(json.ToJsonString(), Encoding.UTF8, "application/json");
        HttpResponseMessage response;
        try
        {
            using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(20));
            response = await http.SendAsync(r, timeout.Token);
        }
        catch (Exception e) when (e is HttpRequestException or TaskCanceledException)
        {
            throw new DafFailure("unreachable", "Daf didn't answer: " + e.Message);
        }
        using (response)
        {
            var body = await response.Content.ReadAsStringAsync();
            if (response.IsSuccessStatusCode) return body;
            if (response.StatusCode == HttpStatusCode.Unauthorized)
                throw new DafFailure("unknown", "Daf doesn't know this PC's token any more. Connect it again in Settings.");
            if ((int)response.StatusCode is 502 or 503 or 504 or (>= 520 and <= 530))
                throw new DafFailure("unreachable", $"Daf didn't answer ({(int)response.StatusCode})");
            string? detail = null;
            try { detail = JsonNode.Parse(body)?["detail"]?.GetValue<string>(); } catch (Exception) { }
            throw new DafFailure("refused", detail ?? $"Daf answered {(int)response.StatusCode}");
        }
    }
}
