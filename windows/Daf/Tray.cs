using System.Drawing;
using System.Drawing.Drawing2D;
using System.Drawing.Imaging;
using System.Runtime.InteropServices;
using Microsoft.Win32;

namespace Daf;

/// <summary>
/// Today's minutes in the notification area, the Windows place for the Mac's menu-bar
/// minutes: a ring filled to today's minutes (the goal's colour once it's met, dimmed
/// when it's old), "Daf: 38 of 60 minutes today" under the pointer, the ring, the day's
/// highlight and a few commands on a click (TodayPanel), and a menu on a right-click.
/// The point is to see it, not to click it.
/// </summary>
static class Tray
{
    /// <summary>The notification area is on in Settings, so Daf stays when its last window closes.</summary>
    public static bool Shown => Settings.Current.Tray;
    /// <summary>Windows took the icon (the self-test asks).</summary>
    public static bool Added { get; private set; }
    public static string Tip { get; private set; } = "Daf";

    static IntPtr window, icon;
    static WndProc? proc;
    static uint taskbarCreated;
    static bool versionFour, listening;
    const int CallbackMessage = 0x8000 + 1, IconId = 1;

    public static void Install()
    {
        if (!Settings.Current.Tray) return;
        if (window == IntPtr.Zero) Create();
        if (!listening)
        {
            Today.Changed += Update;
            listening = true;
        }
        if (!Added) Add();
    }

    public static void Remove()
    {
        if (Added)
        {
            var data = Data(0);
            Shell_NotifyIcon(NIM_DELETE, ref data);
            Added = false;
        }
        if (listening)
        {
            Today.Changed -= Update;
            listening = false;
        }
    }

    public static void SetShown(bool on)
    {
        Settings.Current.Tray = on;
        Settings.Save();
        if (on) Install(); else Remove();
    }

    /// <summary>A window of its own that is never shown, for the icon's messages.</summary>
    static void Create()
    {
        proc = WindowProc;
        var instance = GetModuleHandle(null);
        var cls = new WNDCLASSEX
        {
            cbSize = Marshal.SizeOf<WNDCLASSEX>(),
            lpfnWndProc = Marshal.GetFunctionPointerForDelegate(proc),
            hInstance = instance,
            lpszClassName = "DafNotificationArea",
        };
        RegisterClassEx(ref cls);
        window = CreateWindowEx(0, "DafNotificationArea", "Daf", 0, 0, 0, 0, 0, IntPtr.Zero, IntPtr.Zero, instance, IntPtr.Zero);
        taskbarCreated = RegisterWindowMessage("TaskbarCreated");
    }

    static void Add()
    {
        var data = Data(NIF_MESSAGE | NIF_ICON | NIF_TIP | NIF_SHOWTIP);
        Added = Shell_NotifyIcon(NIM_ADD, ref data);
        if (!Added) return;
        data.uVersion = 4;
        versionFour = Shell_NotifyIcon(NIM_SETVERSION, ref data);
    }

    /// <summary>The ring and the words again, from what Today knows.</summary>
    public static void Update()
    {
        if (!Added) return;
        var data = Data(NIF_ICON | NIF_TIP | NIF_SHOWTIP);
        Shell_NotifyIcon(NIM_MODIFY, ref data);
    }

    static NOTIFYICONDATA Data(int flags)
    {
        var old = icon;
        icon = Draw();
        if (old != IntPtr.Zero) DestroyIcon(old);
        var w = Today.Last;
        Tip = w == null ? "Daf" : "Daf: " + (w.Done ? w.MetLine + " " + w.Line : w.Line) + (Today.Stale ? " (offline)" : "");
        return new NOTIFYICONDATA
        {
            cbSize = Marshal.SizeOf<NOTIFYICONDATA>(),
            hWnd = window,
            uID = IconId,
            uFlags = flags,
            uCallbackMessage = CallbackMessage,
            hIcon = icon,
            szTip = Tip.Length > 120 ? Tip[..120] : Tip,
            szInfo = "",
            szInfoTitle = "",
        };
    }

    // ---- what a click does ------------------------------------------------------------------------

    static IntPtr WindowProc(IntPtr hWnd, uint msg, IntPtr wParam, IntPtr lParam)
    {
        if (msg == CallbackMessage)
        {
            var what = (int)(lParam.ToInt64() & 0xFFFF);
            if (versionFour ? what is NIN_SELECT or NIN_KEYSELECT : what == WM_LBUTTONUP) TodayPanel.Toggle();
            else if (versionFour ? what == WM_CONTEXTMENU : what == WM_RBUTTONUP) ShowMenu();
            return IntPtr.Zero;
        }
        if (msg == taskbarCreated && taskbarCreated != 0)
        {
            // Explorer started again: the icon again
            Added = false;
            Add();
        }
        return DefWindowProc(hWnd, msg, wParam, lParam);
    }

    static void ShowMenu()
    {
        var menu = CreatePopupMenu();
        var items = new (string Text, Action? Act)[]
        {
            ("Open Daf", () => OpenDaf()), ("Review", () => ShellWindow.Show("#review")), ("Reading Goals…", () => ShellWindow.Show("#prefs/goals")), ("", null),
            ("Save a Link…", () => _ = SaveLink.Ask()), ("Log Paper Minutes…", () => LogPaper()), ("", null),
            ("Settings…", () => SettingsWindow.Show()), ("Exit Daf", () => App.Quit()),
        };
        for (var i = 0; i < items.Length; i++)
            AppendMenu(menu, items[i].Act == null ? MF_SEPARATOR : MF_STRING, (UIntPtr)(i + 1), items[i].Text);
        Win32.GetCursorPos(out var p);
        Win32.SetForegroundWindow(window);
        var chosen = TrackPopupMenuEx(menu, TPM_RETURNCMD | TPM_RIGHTBUTTON | TPM_BOTTOMALIGN, p.X, p.Y, window, IntPtr.Zero);
        PostMessage(window, 0, IntPtr.Zero, IntPtr.Zero);
        DestroyMenu(menu);
        if (chosen > 0 && chosen <= items.Length) items[chosen - 1].Act?.Invoke();
    }

    public static void OpenDaf() => ShellWindow.Show(ShellWindow.All.Any(w => w.Start == null) ? null : "#today");

    /// <summary>Log Paper Minutes…: Daf's own dialog, once the page has had a moment to be there.</summary>
    public static async void LogPaper()
    {
        var had = ShellWindow.All.Any(w => w.Start == null);
        ShellWindow.Show(had ? null : "#today");
        await Task.Delay(had ? 200 : 2500);
        if (ShellWindow.Front is { } w) await w.Run("paper");
    }

    // ---- the ring ---------------------------------------------------------------------------------

    /// <summary>The taskbar is light (Windows' "Choose your default Windows mode").</summary>
    static bool TaskbarLight()
    {
        using var key = Registry.CurrentUser.OpenSubKey(@"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize");
        return key?.GetValue("SystemUsesLightTheme") is int v && v == 1;
    }

    static IntPtr Draw()
    {
        var size = Math.Max(16, GetSystemMetricsForDpi(SM_CXSMICON, GetDpiForSystem()));
        var w = Today.Last;
        if (w == null)
        {
            var ico = Path.Join(AppContext.BaseDirectory, "Assets", "Daf.ico");
            if (File.Exists(ico))
            {
                var loaded = LoadImage(IntPtr.Zero, ico, 1, size, size, 0x10);
                if (loaded != IntPtr.Zero) return loaded;
            }
        }
        using var bitmap = new Bitmap(size, size, PixelFormat.Format32bppArgb);
        using (var g = Graphics.FromImage(bitmap))
        {
            g.SmoothingMode = SmoothingMode.AntiAlias;
            g.Clear(Color.Transparent);
            var light = TaskbarLight();
            var fg = light ? Color.FromArgb(0x1f, 0x1f, 0x1f) : Color.White;
            var stroke = Math.Max(2f, size / 6.5f);
            var r = new RectangleF(stroke / 2 + 0.5f, stroke / 2 + 0.5f, size - stroke - 1, size - stroke - 1);
            var dim = Today.Stale;
            using (var track = new Pen(Color.FromArgb(dim ? 55 : 85, fg), stroke)) g.DrawEllipse(track, r);
            if (w != null)
            {
                // Daf's blue, lighter on a dark taskbar; green once the goal is met
                var color = w.Done ? (light ? Color.FromArgb(0x2e, 0x9e, 0x4f) : Color.FromArgb(0x4c, 0xc2, 0x6a))
                                   : (light ? Color.FromArgb(0x1a, 0x7d, 0xa3) : Color.FromArgb(0x59, 0xb5, 0xdb));
                if (dim) color = Color.FromArgb(150, color);
                using var arc = new Pen(color, stroke) { StartCap = LineCap.Round, EndCap = LineCap.Round };
                if (w.Fraction >= 1) g.DrawEllipse(arc, r);
                else g.DrawArc(arc, r, -90, (float)(360 * Math.Max(0.03, w.Fraction)));
            }
        }
        return bitmap.GetHicon();
    }

    // ---- Win32 ----------------------------------------------------------------------------------------

    delegate IntPtr WndProc(IntPtr hWnd, uint msg, IntPtr wParam, IntPtr lParam);

    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
    struct WNDCLASSEX
    {
        public int cbSize;
        public int style;
        public IntPtr lpfnWndProc;
        public int cbClsExtra;
        public int cbWndExtra;
        public IntPtr hInstance;
        public IntPtr hIcon;
        public IntPtr hCursor;
        public IntPtr hbrBackground;
        public string? lpszMenuName;
        public string lpszClassName;
        public IntPtr hIconSm;
    }

    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
    struct NOTIFYICONDATA
    {
        public int cbSize;
        public IntPtr hWnd;
        public int uID;
        public int uFlags;
        public int uCallbackMessage;
        public IntPtr hIcon;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 128)] public string szTip;
        public int dwState;
        public int dwStateMask;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 256)] public string szInfo;
        public int uVersion;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 64)] public string szInfoTitle;
        public int dwInfoFlags;
        public Guid guidItem;
        public IntPtr hBalloonIcon;
    }

    const int NIM_ADD = 0, NIM_MODIFY = 1, NIM_DELETE = 2, NIM_SETVERSION = 4;
    const int NIF_MESSAGE = 1, NIF_ICON = 2, NIF_TIP = 4, NIF_SHOWTIP = 0x80;
    const int NIN_SELECT = 0x400, NIN_KEYSELECT = 0x401, WM_LBUTTONUP = 0x202, WM_RBUTTONUP = 0x205, WM_CONTEXTMENU = 0x7B;
    const uint MF_STRING = 0, MF_SEPARATOR = 0x800, TPM_RETURNCMD = 0x100, TPM_RIGHTBUTTON = 0x2, TPM_BOTTOMALIGN = 0x20;
    const int SM_CXSMICON = 49;

    [DllImport("shell32.dll", CharSet = CharSet.Unicode, EntryPoint = "Shell_NotifyIconW")]
    static extern bool Shell_NotifyIcon(int message, ref NOTIFYICONDATA data);

    [DllImport("user32.dll", CharSet = CharSet.Unicode, EntryPoint = "RegisterClassExW")]
    static extern ushort RegisterClassEx(ref WNDCLASSEX cls);

    [DllImport("user32.dll", CharSet = CharSet.Unicode, EntryPoint = "CreateWindowExW")]
    static extern IntPtr CreateWindowEx(int exStyle, string className, string windowName, int style, int x, int y, int width, int height,
        IntPtr parent, IntPtr menu, IntPtr instance, IntPtr param);

    [DllImport("user32.dll", EntryPoint = "DefWindowProcW")]
    static extern IntPtr DefWindowProc(IntPtr hWnd, uint msg, IntPtr wParam, IntPtr lParam);

    [DllImport("user32.dll", CharSet = CharSet.Unicode, EntryPoint = "RegisterWindowMessageW")]
    static extern uint RegisterWindowMessage(string name);

    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, EntryPoint = "GetModuleHandleW")]
    static extern IntPtr GetModuleHandle(string? name);

    [DllImport("user32.dll")]
    static extern IntPtr CreatePopupMenu();

    [DllImport("user32.dll", CharSet = CharSet.Unicode, EntryPoint = "AppendMenuW")]
    static extern bool AppendMenu(IntPtr menu, uint flags, UIntPtr id, string text);

    [DllImport("user32.dll")]
    static extern int TrackPopupMenuEx(IntPtr menu, uint flags, int x, int y, IntPtr hWnd, IntPtr tpm);

    [DllImport("user32.dll")]
    static extern bool DestroyMenu(IntPtr menu);

    [DllImport("user32.dll", EntryPoint = "PostMessageW")]
    static extern bool PostMessage(IntPtr hWnd, uint msg, IntPtr wParam, IntPtr lParam);

    [DllImport("user32.dll")]
    static extern bool DestroyIcon(IntPtr icon);

    [DllImport("user32.dll", CharSet = CharSet.Unicode, EntryPoint = "LoadImageW")]
    static extern IntPtr LoadImage(IntPtr instance, string name, uint type, int cx, int cy, uint flags);

    [DllImport("user32.dll")]
    static extern int GetSystemMetricsForDpi(int index, uint dpi);

    [DllImport("user32.dll")]
    static extern uint GetDpiForSystem();
}
