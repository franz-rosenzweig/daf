package xyz.tiresia.daf;

import android.app.Activity;
import android.content.ActivityNotFoundException;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.ApplicationInfo;
import android.content.res.Configuration;
import android.graphics.Insets;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Message;
import android.view.KeyEvent;
import android.view.MotionEvent;
import android.view.View;
import android.view.WindowInsets;
import android.view.WindowInsetsController;
import android.webkit.CookieManager;
import android.webkit.ServiceWorkerClient;
import android.webkit.ServiceWorkerController;
import android.webkit.URLUtil;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceRequest;
import android.webkit.WebResourceResponse;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Toast;
import android.window.OnBackInvokedDispatcher;

import org.json.JSONObject;

import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;

/**
 * Daf: the live site in a WebView (docs/SHELL.md). The page is the whole interface
 * and already has a phone layout; this adds Back through the page (dafBack), the
 * volume keys turning a book's pages, downloads, the share sheet (Shell), and
 * opening on a page of Daf from the widget, the shortcuts and the nudge.
 *
 * Only Daf loads here: any other address goes to the browser or the app it belongs to.
 */
public class MainActivity extends Activity {
    static final String EXTRA_ROUTE = "daf.route", EXTRA_COMMAND = "daf.command";
    private static final int SAVE = 1, FILES = 2;

    private WebView web;
    private Shell shell;
    /** The window, for the listening controls on the lock screen and the notification. */
    private static java.lang.ref.WeakReference<MainActivity> live = new java.lang.ref.WeakReference<>(null);
    private String loadedBase;

    private ValueCallback<Uri> saving;            // a download waiting for its place
    private ValueCallback<Uri[]> choosing;        // an <input type=file> waiting for files

    /** Opens Daf on a page ("#review"), and runs a command there ("paper"). */
    static Intent open(android.content.Context c, String route, String command) {
        Intent i = new Intent(c, MainActivity.class).setAction(Intent.ACTION_VIEW)
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
        // distinct data, so PendingIntents for different pages stay different
        i.setData(Uri.parse("daf://go/" + (route == null ? "" : route.replaceFirst("^#", ""))
                + (command == null ? "" : "?command=" + command)));
        return i;
    }

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        if ((getApplicationInfo().flags & ApplicationInfo.FLAG_DEBUGGABLE) != 0) {
            WebView.setWebContentsDebuggingEnabled(true);
            // the test build is pointed at a sandbox by check.py, never the real app
            Intent in = getIntent();
            if (in.getStringExtra("daf.base") != null) Server.setBase(this, in.getStringExtra("daf.base"));
            if (in.getStringExtra("daf.token") != null) {
                Server.setToken(this, in.getStringExtra("daf.token"));
                Server.prefs(this).edit().putString("tokenName", Server.deviceName()).apply();   // the check's, kept as this device's
            }
        }
        CookieManager.getInstance().setAcceptCookie(true);

        web = new DafWebView(this);
        stylus = new StylusButton(web);
        volumeKeys = getSharedPreferences("reading", MODE_PRIVATE).getBoolean("volumeKeys", false);
        WebSettings s = web.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setAllowFileAccess(false);
        s.setAllowContentAccess(false);
        s.setSupportMultipleWindows(true);             // target=_blank comes to onCreateWindow, and goes out
        // read-aloud goes on to the next paragraph by itself, also with the screen off (Listen)
        s.setMediaPlaybackRequiresUserGesture(false);
        s.setOffscreenPreRaster(true);                 // draws ahead of the scroll: smoother lists and articles
        s.setTextZoom(100);                            // the page sizes its own text (Aa), not the phone's font scale twice
        s.setUserAgentString(s.getUserAgentString() + " Daf/" + Daf.version(this) + " (Android shell)");
        web.setWebViewClient(new Pages());
        // books on the phone (Offline): the page's service worker fetches them too
        ServiceWorkerController.getInstance().setServiceWorkerClient(new ServiceWorkerClient() {
            @Override
            public WebResourceResponse shouldInterceptRequest(WebResourceRequest request) {
                return answer(getApplicationContext(), request);
            }
        });
        watchNetwork();
        web.setWebChromeClient(new Chrome());
        web.setDownloadListener((url, agent, disposition, mime, length) -> download(url, URLUtil.guessFileName(url, disposition, mime), mime));
        shell = new Shell(this, web);
        live = new java.lang.ref.WeakReference<>(this);
        setContentView(web);
        insets();
        if (Build.VERSION.SDK_INT >= 33) {
            getOnBackInvokedDispatcher().registerOnBackInvokedCallback(OnBackInvokedDispatcher.PRIORITY_DEFAULT, this::back);
        }
        loadedBase = Server.base(this);
        web.loadUrl(startUrl(getIntent()));
        Widget.shortcuts(this, Widget.kept(this));
    }

    /** Signed in, and no token yet: this phone makes its own ("android"), with the window's
     *  sign-in, so the widget and Save to Daf work without a trip to Settings. Once a run. */
    private boolean connecting;
    private void connectIfSignedIn() {
        // no token yet, it was refused (Server drops it), or it was made under the name every phone
        // once shared ("android"): a token of this device's own
        if (connecting || web == null || (Server.token(this) != null && Server.ownToken(this))) return;
        web.evaluateJavascript("!!(window.dafState && dafState().signedIn)", yes -> {
            if (!"true".equals(yes) || connecting) return;
            connecting = true;
            new Thread(() -> {
                try {
                    Server.setToken(this, Server.connect(this));
                    Widget.fetch(this);
                    runOnUiThread(() -> Toast.makeText(this, "This phone is connected to Daf", Toast.LENGTH_SHORT).show());
                } catch (Exception e) {
                    connecting = false;
                }
            }).start();
        });
    }

    /** The page the intent asks for, or Today. */
    private String startUrl(Intent intent) {
        String route = route(intent);
        return Server.url(this, route == null ? "" : route);
    }

    /** daf://go/review → "#review"; a Daf address (the nudge's) as it is. */
    private String route(Intent intent) {
        Uri d = intent == null ? null : intent.getData();
        if (d == null) return intent == null ? null : intent.getStringExtra(EXTRA_ROUTE);
        if ("daf".equals(d.getScheme()) && "go".equals(d.getHost())) {
            String p = d.getPath() == null ? "" : d.getPath().replaceFirst("^/", "");
            return p.isEmpty() ? null : "#" + p;
        }
        if (Server.isOurs(this, d) && d.getFragment() != null) return "#" + d.getFragment();
        return null;
    }

    private static String command(Intent intent) {
        Uri d = intent == null ? null : intent.getData();
        String c = d != null && "daf".equals(d.getScheme()) ? d.getQueryParameter("command") : null;
        return c != null ? c : intent == null ? null : intent.getStringExtra(EXTRA_COMMAND);
    }

    // ---- the S Pen's button (StylusButton): the WebView doesn't pass it on ----

    private StylusButton stylus;

    @Override
    public boolean dispatchGenericMotionEvent(MotionEvent ev) {
        if (stylus != null && stylus.hover(ev)) return true;
        return super.dispatchGenericMotionEvent(ev);
    }

    @Override
    public boolean dispatchTouchEvent(MotionEvent ev) {
        MotionEvent e = stylus != null ? stylus.touch(ev) : ev;
        try {
            return super.dispatchTouchEvent(e);
        } finally {
            if (e != ev) e.recycle();
        }
    }

    @Override
    protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        setIntent(intent);
        go(route(intent), command(intent));
    }

    /** One of the page's commands from outside the window (the lock screen, headphones,
     *  the notification). False when there's no window to run it in. */
    static boolean command(String name) {
        MainActivity a = live.get();
        if (a == null || a.web == null) return false;
        a.web.evaluateJavascript("window.dafCommand && window.dafCommand(" + JSONObject.quote(name) + ")", null);
        return true;
    }

    /** While Daf reads aloud the page must keep running behind a locked screen. */
    void listening(boolean on) {
        if (web != null) web.setRendererPriorityPolicy(WebView.RENDERER_PRIORITY_IMPORTANT, !on);
    }

    /** The page goes to a route, then runs a command, once it's there. */
    void go(String route, String command) {
        if (web == null) return;
        String js = (route == null ? "" : "location.hash = " + JSONObject.quote(route) + ";")
                + (command == null ? "" : "setTimeout(() => window.dafCommand && window.dafCommand(" + JSONObject.quote(command) + "), 500);");
        if (!js.isEmpty()) web.evaluateJavascript(js, null);
    }

    @Override
    protected void onResume() {
        super.onResume();
        flushOutbox();
        // the address changed in Settings: the page again, from there
        if (web != null && !Server.base(this).equals(loadedBase)) {
            loadedBase = Server.base(this);
            web.loadUrl(Server.url(this, ""));
        }
    }

    @Override
    protected void onPause() {
        super.onPause();
        CookieManager.getInstance().flush();
        connectIfSignedIn();
        // reading in the app moves the hour: the widget asks again
        Widget.refreshIfOlder(this, 60 * 1000L);
    }

    // ---- Back ----

    /** Whatever is open closes, then Daf goes back; only with nowhere to go does Back leave. */
    private void back() {
        if (web == null) {
            moveTaskToBack(true);
            return;
        }
        web.evaluateJavascript("(() => { try { return !!(window.dafBack && window.dafBack()); } catch (e) { return false; } })()",
                went -> { if (!"true".equals(went)) moveTaskToBack(true); });
    }

    @Override
    @SuppressWarnings("deprecation")
    public void onBackPressed() {
        if (Build.VERSION.SDK_INT >= 33) super.onBackPressed();
        else back();
    }

    // ---- the volume keys turn a book's pages, and a manga's ----

    @Override
    public boolean dispatchKeyEvent(KeyEvent e) {
        int k = e.getKeyCode();
        if (k == KeyEvent.KEYCODE_VOLUME_DOWN || k == KeyEvent.KEYCODE_VOLUME_UP) {
            // pages, only if the page's switch says so (Preferences → Reader, off by default), a book or a
            // manga is open, and nothing is playing (music, or Daf's own read-aloud): else the volume
            if (e.getAction() == KeyEvent.ACTION_DOWN && e.getRepeatCount() == 0) {
                android.media.AudioManager audio = getSystemService(android.media.AudioManager.class);
                turning = volumeKeys && inBook() && (audio == null || !audio.isMusicActive());
            }
            if (turning) {
                if (e.getAction() == KeyEvent.ACTION_DOWN) {
                    web.evaluateJavascript("window.dafCommand && window.dafCommand('" + (k == KeyEvent.KEYCODE_VOLUME_DOWN ? "next" : "prev") + "')", null);
                }
                return true;      // both halves of the press, or the volume changes too
            }
        }
        return super.dispatchKeyEvent(e);
    }

    /** Whether this press of a volume button turns pages (decided as it goes down, kept until it's up). */
    private boolean turning;
    private boolean volumeKeys;

    /** What the page says about reading (Shell's "reading"): whether the volume buttons turn pages,
     *  kept for the next start, and whether the page's own text menu stands in for Android's. */
    void reading(boolean volume, boolean ownMenu) {
        if (volume != volumeKeys) getSharedPreferences("reading", MODE_PRIVATE).edit().putBoolean("volumeKeys", volume).apply();
        volumeKeys = volume;
        ((DafWebView) web).ownMenu(ownMenu);
    }

    private boolean inBook() {
        String u = web == null ? null : web.getUrl();
        return u != null && (u.contains("#ebook/") || u.contains("#mread/"));
    }

    // ---- with no network: the device's own copy (AppFiles, DataStore, Offline) ----

    static WebResourceResponse answer(android.content.Context c, WebResourceRequest r) {
        if (Net.down(c)) {
            WebResourceResponse a = AppFiles.intercept(c, r);
            if (a == null) a = DataStore.intercept(c, r);
            if (a != null) return a;
        }
        return Offline.intercept(c, r);
    }

    private long copyAt;

    /** Daf's server didn't answer the page: show the copy on the device, once a minute at most. */
    private void offlineCopy(WebView view) {
        Net.unreachable();
        if (!AppFiles.ready(this) || System.currentTimeMillis() - copyAt < 60_000L) return;
        copyAt = System.currentTimeMillis();
        view.postDelayed(view::reload, 300);
    }

    /** The network back: what was done offline goes (the page's outbox), and Daf's screens and data
     *  are brought up to date in the background. */
    private void watchNetwork() {
        android.net.ConnectivityManager cm = getSystemService(android.net.ConnectivityManager.class);
        if (cm == null) return;
        cm.registerDefaultNetworkCallback(new android.net.ConnectivityManager.NetworkCallback() {
            @Override
            public void onAvailable(android.net.Network n) {
                Net.reachable();
                runOnUiThread(() -> { flushOutbox(); keepUpToDate(); });
            }
        });
    }

    private void flushOutbox() {
        if (web != null) web.evaluateJavascript("window.DafCore && DafCore.outbox && DafCore.outbox.flush && DafCore.outbox.flush(), 1", null);
    }

    private long refreshedAt;

    /** Daf's own screens (cheap: one request, then only what changed), and the books and data on Wi-Fi. */
    private void keepUpToDate() {
        if (Net.down(this) || System.currentTimeMillis() - refreshedAt < 10 * 60_000L) return;
        refreshedAt = System.currentTimeMillis();
        android.content.Context app = getApplicationContext();
        new Thread(() -> {
            try { AppFiles.refresh(app); }
            catch (AppFiles.Bad e) { }                                    // Daf answered, one file wasn't right (a deploy midway): next time
            catch (java.io.IOException e) { Net.unreachable(); }         // the network's up but Daf isn't
            catch (Exception ignored) { }
        }).start();
        Offline.soon(app);
    }

    // ---- Sign in to Instagram (InstagramActivity), asked for by the page through Shell ----

    private static final int INSTAGRAM = 8;
    private java.util.function.Consumer<Boolean> instagramAnswer;

    void signInInstagram(java.util.function.Consumer<Boolean> answer) {
        if (instagramAnswer != null) instagramAnswer.accept(false);
        instagramAnswer = answer;
        startActivityForResult(new Intent(this, InstagramActivity.class), INSTAGRAM);
    }

    // ---- permission to notify (new posts), asked for by the page through Shell ----

    private static final int NOTIFY = 7;
    private java.util.function.Consumer<Boolean> notifyAnswer;

    void askToNotify(java.util.function.Consumer<Boolean> answer) {
        notifyAnswer = answer;
        requestPermissions(new String[]{android.Manifest.permission.POST_NOTIFICATIONS}, NOTIFY);
    }

    @Override
    public void onRequestPermissionsResult(int request, String[] permissions, int[] results) {
        super.onRequestPermissionsResult(request, permissions, results);
        if (request == NOTIFY && notifyAnswer != null) {
            notifyAnswer.accept(results.length > 0 && results[0] == android.content.pm.PackageManager.PERMISSION_GRANTED);
            notifyAnswer = null;
        }
    }

    // ---- the manga reader: the whole screen, kept on ----

    private boolean immersive;

    /** The page asks (shell.js, while #mread is open): the status and navigation bars away, a
     *  swipe from the edge shows them for a moment; and the screen on while it reads. */
    void screen(boolean immersive, boolean awake) {
        this.immersive = immersive;
        WindowInsetsController c = getWindow().getInsetsController();
        if (c != null) {
            c.setSystemBarsBehavior(WindowInsetsController.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE);
            if (immersive) c.hide(WindowInsets.Type.systemBars()); else c.show(WindowInsets.Type.systemBars());
        }
        if (awake) getWindow().addFlags(android.view.WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        else getWindow().clearFlags(android.view.WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        web.post(() -> edges(immersive));
    }

    /** The manga reader swipes its own pages: the middle of each side edge (Android grants 200dp an
     *  edge) is the page's, not the system's Back gesture. */
    private void edges(boolean reader) {
        if (web == null) return;
        java.util.List<android.graphics.Rect> rects = new java.util.ArrayList<>();
        WindowInsets in = web.getRootWindowInsets();
        if (reader && in != null) {
            Insets g = in.getInsets(WindowInsets.Type.systemGestures());
            int band = Math.round(200 * getResources().getDisplayMetrics().density), mid = web.getHeight() / 2;
            int left = Math.max(g.left, Math.round(24 * getResources().getDisplayMetrics().density));
            int right = Math.max(g.right, Math.round(24 * getResources().getDisplayMetrics().density));
            rects.add(new android.graphics.Rect(0, mid - band / 2, left, mid + band / 2));
            rects.add(new android.graphics.Rect(web.getWidth() - right, mid - band / 2, web.getWidth(), mid + band / 2));
        }
        web.setSystemGestureExclusionRects(rects);
    }

    @Override
    public void onWindowFocusChanged(boolean focus) {
        super.onWindowFocusChanged(focus);
        if (focus && immersive) screen(true, (getWindow().getAttributes().flags & android.view.WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON) != 0);
    }

    // ---- the window ----

    /** The page sits between the status bar and the navigation bar, or the keyboard when
     *  it's open (the WebView gets shorter, so the page's own bars stay on screen). */
    private void insets() {
        View content = findViewById(android.R.id.content);
        content.setOnApplyWindowInsetsListener((v, in) -> {
            Insets bars = in.getInsets(WindowInsets.Type.systemBars() | WindowInsets.Type.displayCutout());
            int ime = in.getInsets(WindowInsets.Type.ime()).bottom;
            v.setPadding(bars.left, bars.top, bars.right, Math.max(bars.bottom, ime));
            return WindowInsets.CONSUMED;
        });
        paintBars();
    }

    /** Behind the bars, the page's own background: the theme's, once the page has said it (bars()),
     *  else light or dark as the phone is. */
    private void paintBars() {
        boolean night = (getResources().getConfiguration().uiMode & Configuration.UI_MODE_NIGHT_MASK) == Configuration.UI_MODE_NIGHT_YES;
        SharedPreferences t = getSharedPreferences("theme", MODE_PRIVATE);
        String key = night ? "night" : "day";
        int colour = t.getInt(key + ".bg", night ? 0xFF16171A : 0xFFFFFFFF);
        boolean dark = t.getBoolean(key + ".dark", night);
        getWindow().getDecorView().setBackgroundColor(colour);
        web.setBackgroundColor(colour);
        WindowInsetsController c = getWindow().getInsetsController();
        int light = WindowInsetsController.APPEARANCE_LIGHT_STATUS_BARS | WindowInsetsController.APPEARANCE_LIGHT_NAVIGATION_BARS;
        if (c != null) c.setSystemBarsAppearance(dark ? 0 : light, light);
    }

    /** The theme's background (#rrggbb) and whether it's dark, from the page; kept for the phone's
     *  current mode, so the next start paints the same before the page loads. */
    boolean bars(String bg, boolean dark) {
        int colour;
        try { colour = 0xFF000000 | Integer.parseInt(bg.replaceFirst("^#", ""), 16); } catch (NumberFormatException e) { return false; }
        boolean night = (getResources().getConfiguration().uiMode & Configuration.UI_MODE_NIGHT_MASK) == Configuration.UI_MODE_NIGHT_YES;
        String key = night ? "night" : "day";
        getSharedPreferences("theme", MODE_PRIVATE).edit().putInt(key + ".bg", colour).putBoolean(key + ".dark", dark).apply();
        paintBars();
        return true;
    }

    @Override
    public void onConfigurationChanged(Configuration config) {
        super.onConfigurationChanged(config);
        paintBars();
    }

    @Override
    protected void onDestroy() {
        if (live.get() == this) live.clear();
        Listen.update(this, "stopped", null, null);
        if (shell != null) shell.close();
        if (web != null) web.destroy();
        super.onDestroy();
    }

    // ---- downloads: the export, a book's file; blob links come through Shell ----

    /** Fetches one of Daf's files with the window's cookie, into a place the person picks. */
    void download(String url, String name, String mime) {
        Uri u = Uri.parse(url);
        if (!Server.isOurs(this, u)) { outside(u); return; }
        createDocument(name, mime == null || mime.isEmpty() ? "application/octet-stream" : mime, where -> {
            if (where == null) return;
            new Thread(() -> {
                String problem = null;
                try {
                    HttpURLConnection h = (HttpURLConnection) new URL(url).openConnection();
                    String cookie = CookieManager.getInstance().getCookie(url);
                    if (cookie != null) h.setRequestProperty("Cookie", cookie);
                    if (h.getResponseCode() != 200) throw new java.io.IOException("Daf answered " + h.getResponseCode());
                    try (InputStream in = h.getInputStream(); OutputStream out = getContentResolver().openOutputStream(where)) {
                        if (out == null) throw new java.io.IOException("no place to write");
                        byte[] chunk = new byte[65536];
                        for (int n; (n = in.read(chunk)) > 0; ) out.write(chunk, 0, n);
                    }
                } catch (Exception e) {
                    problem = e.getMessage();
                }
                String said = problem == null ? "Saved" : "The download didn't finish: " + problem;
                runOnUiThread(() -> Toast.makeText(this, said, Toast.LENGTH_SHORT).show());
            }).start();
        });
    }

    /** A place for a file, from the system's create-document screen. */
    void createDocument(String name, String mime, ValueCallback<Uri> done) {
        if (saving != null) saving.onReceiveValue(null);
        saving = done;
        Intent save = new Intent(Intent.ACTION_CREATE_DOCUMENT).addCategory(Intent.CATEGORY_OPENABLE)
                .setType(mime).putExtra(Intent.EXTRA_TITLE, name);
        try {
            startActivityForResult(save, SAVE);
        } catch (ActivityNotFoundException e) {
            saving = null;
            done.onReceiveValue(null);
        }
    }

    /** Anything that isn't Daf: the browser, Mail, Obsidian. */
    boolean outside(Uri url) {
        String scheme = url.getScheme() == null ? "" : url.getScheme().toLowerCase();
        if (!(scheme.equals("http") || scheme.equals("https") || scheme.equals("mailto") || scheme.equals("obsidian"))) return false;
        try {
            startActivity(new Intent(Intent.ACTION_VIEW, url).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));
            return true;
        } catch (ActivityNotFoundException e) {
            return false;
        }
    }

    @Override
    protected void onActivityResult(int request, int result, Intent data) {
        super.onActivityResult(request, result, data);
        Uri uri = result == RESULT_OK && data != null ? data.getData() : null;
        if (request == SAVE) {
            if (saving != null) saving.onReceiveValue(uri);
            saving = null;
        } else if (request == FILES) {
            if (choosing != null) choosing.onReceiveValue(WebChromeClient.FileChooserParams.parseResult(result, data));
            choosing = null;
        } else if (request == INSTAGRAM) {
            if (instagramAnswer != null) instagramAnswer.accept(result == RESULT_OK);
            instagramAnswer = null;
        }
    }

    /** Only Daf in the window. */
    private final class Pages extends WebViewClient {
        @Override
        public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
            Uri url = request.getUrl();
            if (Server.isOurs(MainActivity.this, url) || "about".equals(url.getScheme())) return false;
            if (!request.isForMainFrame()) return false;
            outside(url);
            return true;
        }

        /** With the network down: Daf's own screens and the data kept on the device. Always: a
         *  book's file and a manga's pages from the device (Offline). */
        @Override
        public WebResourceResponse shouldInterceptRequest(WebView view, WebResourceRequest request) {
            return answer(getApplicationContext(), request);
        }

        /** The page itself didn't come for want of the server: the device's own copy. */
        @Override
        public void onReceivedError(WebView view, WebResourceRequest request, android.webkit.WebResourceError error) {
            if (!request.isForMainFrame() || !Server.isOurs(MainActivity.this, request.getUrl())) return;
            int code = error.getErrorCode();
            if (code == ERROR_HOST_LOOKUP || code == ERROR_CONNECT || code == ERROR_TIMEOUT || code == ERROR_IO || code == ERROR_UNKNOWN) offlineCopy(view);
        }

        @Override
        public void onReceivedHttpError(WebView view, WebResourceRequest request, WebResourceResponse response) {
            int code = response.getStatusCode();
            if (request.isForMainFrame() && Server.isOurs(MainActivity.this, request.getUrl()) && (code == 502 || code == 503 || code == 504 || code >= 520 && code <= 530)) offlineCopy(view);
        }

        /** A new document: it needs its own port (Shell). A route change in the page (#…) doesn't
         *  start one, but WebView still calls onPageFinished for it; the page keeps its port then. */
        private boolean fresh = true, shown;

        @Override
        public void onPageStarted(WebView view, String url, android.graphics.Bitmap favicon) {
            fresh = true;
            shown = false;
            shell.close();
        }

        /** The page shows: its port now, so the app's calls don't wait for every picture to load. */
        @Override
        public void onPageCommitVisible(WebView view, String url) {
            if (shown || url == null || !Server.isOurs(MainActivity.this, Uri.parse(url))) return;
            shown = true;
            shell.connect();
        }

        @Override
        public void onPageFinished(WebView view, String url) {
            if (url == null || !Server.isOurs(MainActivity.this, Uri.parse(url))) return;
            if (!shell.heard()) shell.connect();           // shell.js wasn't listening for the first yet
            if (!fresh) return;
            fresh = false;
            view.postDelayed(MainActivity.this::connectIfSignedIn, 3000);
            view.postDelayed(() -> { Offline.schedule(MainActivity.this, false); keepUpToDate(); }, 8000);
        }
    }

    private final class Chrome extends WebChromeClient {
        /** <input type=file>: a photo of a paper page, say. */
        @Override
        public boolean onShowFileChooser(WebView view, ValueCallback<Uri[]> callback, FileChooserParams params) {
            if (choosing != null) choosing.onReceiveValue(null);
            choosing = callback;
            try {
                startActivityForResult(params.createIntent(), FILES);
                return true;
            } catch (ActivityNotFoundException e) {
                choosing = null;
                return false;
            }
        }

        /** target=_blank and window.open: Daf's own files are downloads (the PDF as printed),
         *  anything else goes out. The new WebView only ever learns the address. */
        @Override
        public boolean onCreateWindow(WebView view, boolean dialog, boolean gesture, Message result) {
            WebView probe = new WebView(MainActivity.this);
            probe.setWebViewClient(new WebViewClient() {
                @Override
                public boolean shouldOverrideUrlLoading(WebView v, WebResourceRequest r) {
                    Uri u = r.getUrl();
                    if (Server.isOurs(MainActivity.this, u)) download(u.toString(), URLUtil.guessFileName(u.toString(), null, null), null);
                    else outside(u);
                    v.destroy();
                    return true;
                }
            });
            ((WebView.WebViewTransport) result.obj).setWebView(probe);
            result.sendToTarget();
            return true;
        }
    }
}
