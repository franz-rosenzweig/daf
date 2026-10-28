using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text;
using Microsoft.UI.Dispatching;
using Microsoft.UI.Xaml;
using Microsoft.Windows.AppLifecycle;

namespace Daf;

/// <summary>
/// Daf runs once for each person: a second start (a daf:// link, the Start menu while
/// Daf sits in the notification area, a notification's click) hands what it was asked
/// to the Daf already running and leaves. The self-test's own --data folder is a Daf of its own.
/// </summary>
public static class Program
{
    [STAThread]
    static int Main(string[] args)
    {
        WinRT.ComWrappersSupport.InitializeComWrappers();
        var options = Options.Parse(args);
        var instance = AppInstance.FindOrRegisterForKey(Key(options));
        if (!instance.IsCurrent)
        {
            Redirect(instance);
            return 0;
        }
        instance.Activated += (_, e) => App.Redirected(e);
        Application.Start(_ =>
        {
            SynchronizationContext.SetSynchronizationContext(new DispatcherQueueSynchronizationContext(DispatcherQueue.GetForCurrentThread()));
            _ = new App();
        });
        return 0;
    }

    /// <summary>"Daf" for the person's own Daf; another data folder (the self-test's) is another Daf.</summary>
    static string Key(Options options) => options.Data == null
        ? "Daf"
        : "Daf-" + Convert.ToHexStringLower(SHA1.HashData(Encoding.UTF8.GetBytes(Path.GetFullPath(options.Data).ToLowerInvariant())))[..12];

    /// <summary>
    /// Hands this start to the Daf already running, without blocking its own thread's COM
    /// calls (learn.microsoft.com, "Create a single-instanced WinUI app"). That Daf may
    /// bring its window to the front.
    /// </summary>
    static void Redirect(AppInstance running)
    {
        var activation = AppInstance.GetCurrent().GetActivatedEventArgs();
        AllowSetForegroundWindow(running.ProcessId);
        var done = CreateEvent(IntPtr.Zero, true, false, null);
        _ = Task.Run(() =>
        {
            try { running.RedirectActivationToAsync(activation).AsTask().Wait(TimeSpan.FromSeconds(20)); }
            finally { SetEvent(done); }
        });
        _ = CoWaitForMultipleObjects(0, 0xFFFFFFFF, 1, [done], out _);
        CloseHandle(done);
    }

    [DllImport("kernel32.dll", CharSet = CharSet.Unicode)]
    static extern IntPtr CreateEvent(IntPtr attributes, bool manualReset, bool initialState, string? name);

    [DllImport("kernel32.dll")]
    static extern bool SetEvent(IntPtr handle);

    [DllImport("kernel32.dll")]
    static extern bool CloseHandle(IntPtr handle);

    [DllImport("ole32.dll")]
    static extern uint CoWaitForMultipleObjects(uint flags, uint milliseconds, uint count, IntPtr[] handles, out uint index);

    [DllImport("user32.dll")]
    static extern bool AllowSetForegroundWindow(uint processId);
}
