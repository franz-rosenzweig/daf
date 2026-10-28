using System.Runtime.InteropServices;
using System.Text.Json.Nodes;
using Microsoft.Web.WebView2.Core;
using Windows.ApplicationModel.DataTransfer;
using Windows.Storage;
using Windows.Storage.Pickers;
using WinRT.Interop;

namespace Daf;

/// <summary>
/// window.dafShell (docs/SHELL.md §2): the share sheet, the save dialog, the browser,
/// notifications for new posts, the reader's full screen, the title bar's colour, and
/// what's kept on this PC for no connection. Each call is a message with a reply, so the
/// page's promise settles when the dialog closes. The Mac's is mac/Daf/ShellServices.swift.
/// Downloads (<c>&lt;a download&gt;</c>, attachments, blob links) come here too, to the save dialog.
/// </summary>
sealed class ShellServices(ShellWindow owner)
{
    /// <summary>What the self-test saw arrive.</summary>
    public static readonly List<string> Finished = [];

    DataPackage? sharing;

    public async void Handle(int id, string op, JsonObject args)
    {
        JsonObject reply;
        try { reply = new JsonObject { ["channel"] = "shell", ["id"] = id, ["ok"] = await Answer(op, args) }; }
        catch (Exception e)
        {
            Log.Write($"dafShell.{op}: {e.Message}");
            reply = new JsonObject { ["channel"] = "shell", ["id"] = id, ["error"] = e.Message };
        }
        owner.Post(reply);
    }

    async Task<JsonNode?> Answer(string op, JsonObject args)
    {
        string? Str(string k) => J.Text(args[k]) is { Length: > 0 } s ? s : null;
        switch (op)
        {
            case "share":
                return await Share(Str("text"), Str("url"), Str("png"), Str("name"));
            case "download":
            {
                if (Str("url") is { } u)
                {
                    // fetched by the page itself, with its sign-in; the save dialog comes from OnDownloadStarting
                    await (owner.Core ?? throw new ShellError("no page")).ExecuteScriptAsync(
                        $"(() => {{ const a = document.createElement('a'); a.href = {J.Quote(u)}; a.download = ''; a.style.display = 'none'; document.body.appendChild(a); a.click(); a.remove(); }})()");
                    return true;
                }
                byte[] data;
                try { data = Convert.FromBase64String(Str("base64") ?? throw new ShellError("the file's bytes didn't arrive")); }
                catch (FormatException) { throw new ShellError("the file's bytes didn't arrive"); }
                var path = await ChoosePath(SafeName(Str("name") ?? "Daf"));
                if (path == null) return false;
                await File.WriteAllBytesAsync(path, data);
                lock (Finished) Finished.Add(path);
                return true;
            }
            case "openExternal":
                return Uri.TryCreate(Str("url"), UriKind.Absolute, out var url) && Outside.Open(url);
            case "fullscreen":
                return owner.ReaderFullScreen();
            case "alerts":
                return await FeedNews.Start();
            case "offline":
                try { return await App.Keeper.Answer(args); }
                catch (InvalidOperationException e) { throw new ShellError(e.Message); }
            case "bars":
            {
                var dark = J.Bool(args["dark"]);
                if (!owner.Paint(Str("bg"), dark)) return false;
                Settings.Current.BarColor = Str("bg");
                Settings.Current.BarDark = dark;
                Settings.Save();
                return true;
            }
            default:
                throw new ShellError($"no such shell call: {op}");
        }
    }

    // ---- the share sheet ------------------------------------------------------------------------

    /// <summary>The share sheet with a picture (Share as image), a link or some text. True once it's up; false with nothing to share.</summary>
    async Task<bool> Share(string? text, string? url, string? png, string? name)
    {
        var package = new DataPackage();
        package.Properties.Title = name ?? "Daf";
        var any = false;
        if (png != null)
        {
            byte[] bytes;
            try { bytes = Convert.FromBase64String(png); }
            catch (FormatException) { throw new ShellError("the picture didn't arrive"); }
            var dir = Path.Join(Path.GetTempPath(), "Daf Share", Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(dir);
            var file = Path.Join(dir, WithExtension(SafeName(name ?? "Daf highlight"), "png"));
            await File.WriteAllBytesAsync(file, bytes);
            if (App.Options.SaveDir is { } saveDir) File.Copy(file, Path.Join(saveDir, "shared-" + Path.GetFileName(file)), overwrite: true);
            package.SetStorageItems([await StorageFile.GetFileFromPathAsync(file)]);
            any = true;
        }
        if (url != null && Uri.TryCreate(url, UriKind.Absolute, out var link)) { package.SetWebLink(link); any = true; }
        if (text != null) { package.SetText(url != null ? $"{text}\n{url}" : text); any = true; }
        if (!any) return false;
        if (App.Options.SelfTest) return true;
        sharing = package;
        var interop = DataTransferManager.As<IDataTransferManagerInterop>();
        var manager = WinRT.MarshalInterface<DataTransferManager>.FromAbi(interop.GetForWindow(owner.Handle, ref DataTransferManagerId));
        manager.DataRequested -= OnDataRequested;
        manager.DataRequested += OnDataRequested;
        interop.ShowShareUIForWindow(owner.Handle);
        return true;
    }

    void OnDataRequested(DataTransferManager sender, DataRequestedEventArgs e)
    {
        if (sharing != null) e.Request.Data = sharing;
    }

    // The share sheet for a desktop window (learn.microsoft.com, "Display WinRT UI objects that depend on CoreWindow").
    [ComImport, Guid("3A3DCD6C-3EAB-43DC-BCDE-45671CE800C8"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    interface IDataTransferManagerInterop
    {
        IntPtr GetForWindow([In] IntPtr appWindow, [In] ref Guid riid);
        void ShowShareUIForWindow(IntPtr appWindow);
    }

    static Guid DataTransferManagerId = new(0xa5caee9b, 0x8708, 0x49d1, 0x8d, 0x36, 0x67, 0xd2, 0x5a, 0x8d, 0xa0, 0x0c);

    // ---- saving ---------------------------------------------------------------------------------

    /// <summary>
    /// The highlight exports, a book's file, the PDF as printed, Share as image's Download:
    /// to the save dialog, by the name the server or the page gave. Not the browser's own
    /// download bar.
    /// </summary>
    public async void OnDownloadStarting(CoreWebView2 sender, CoreWebView2DownloadStartingEventArgs e)
    {
        var deferral = e.GetDeferral();
        try
        {
            e.Handled = true;
            var path = await ChoosePath(SafeName(Path.GetFileName(e.ResultFilePath) is { Length: > 0 } n ? n : "Daf"));
            if (path == null) { e.Cancel = true; return; }
            // the dialog asked about replacing it; WebView2 won't write over a file
            try { File.Delete(path); } catch (Exception) { }
            e.ResultFilePath = path;
            e.DownloadOperation.StateChanged += (o, _) =>
            {
                if (o.State == CoreWebView2DownloadState.Completed) lock (Finished) Finished.Add(path);
                else if (o.State == CoreWebView2DownloadState.Interrupted) Log.Write($"a download didn't finish: {o.InterruptReason}");
            };
        }
        catch (Exception x)
        {
            Log.Write($"download: {x.Message}");
            e.Cancel = true;
        }
        finally { deferral.Complete(); }
    }

    /// <summary>A save dialog for <paramref name="name"/>, in Downloads; the chosen path, or null if cancelled. The self-test's --save-dir saves there without one.</summary>
    async Task<string?> ChoosePath(string name)
    {
        if (App.Options.SaveDir is { } dir) return Path.Join(dir, name);
        var picker = new FileSavePicker
        {
            SuggestedFileName = Path.GetFileNameWithoutExtension(name),
            SuggestedStartLocation = PickerLocationId.Downloads,
        };
        var extension = Path.GetExtension(name);
        picker.FileTypeChoices.Add(extension.Length > 1 ? $"{extension[1..].ToUpperInvariant()} file" : "File",
            new List<string> { extension.Length > 1 ? extension : ".txt" });
        InitializeWithWindow.Initialize(picker, owner.Handle);
        var file = await picker.PickSaveFileAsync();
        return file?.Path;
    }

    /// <summary>A name Windows takes for a file: none of / \ : * ? " &lt; &gt; |.</summary>
    public static string SafeName(string name)
    {
        var cleaned = string.Concat(name.Select(c => "/\\:*?\"<>|".Contains(c) || c < ' ' ? '-' : c)).Trim().TrimEnd('.');
        return cleaned.Length == 0 ? "Daf" : cleaned;
    }

    public static string WithExtension(string name, string extension) =>
        Path.GetExtension(name).Equals("." + extension, StringComparison.OrdinalIgnoreCase) ? name : $"{name}.{extension}";
}
