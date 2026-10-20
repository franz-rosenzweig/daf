package xyz.tiresia.daf;

import android.content.Intent;
import android.net.Uri;
import android.os.Handler;
import android.os.Looper;
import android.util.Base64;
import android.webkit.WebMessage;
import android.webkit.WebMessagePort;
import android.webkit.WebView;

import org.json.JSONObject;

import java.io.File;
import java.io.FileOutputStream;
import java.io.OutputStream;
import java.util.UUID;

/**
 * window.dafShell's Android half (docs/SHELL.md §2): share, download, openExternal, haptic,
 * media (what read-aloud is doing, for listening with the screen off: Listen.java), offline
 * (books kept on the phone: Offline.java), screen (the manga reader's whole screen), and alerts
 * (notifications for new posts: FeedNews.java).
 *
 * The page and the app talk over a message port, which the app hands to the main
 * frame after each load, addressed to Daf's own origin; shell.js builds dafShell on
 * it. A port reaches only the page it was posted to, where addJavascriptInterface
 * would have put the app's calls in every frame, a video's included.
 *
 * The first port goes as soon as the page shows, so its calls don't wait for every picture
 * to load; if nothing has come back on it by the time the page has finished loading (shell.js
 * wasn't listening yet), another goes. A document's ports stay open until the next one starts,
 * so a call made on an earlier port still gets its answer there.
 */
final class Shell {
    private final MainActivity activity;
    private final WebView web;
    private final Handler main = new Handler(Looper.getMainLooper());
    private final java.util.List<WebMessagePort> ports = new java.util.ArrayList<>();
    /** Something came back on this document's ports: the page has one. */
    private boolean heard;

    Shell(MainActivity activity, WebView web) {
        this.activity = activity;
        this.web = web;
    }

    /** A port for the page in the window (another one, if it hasn't answered on the first). */
    void connect() {
        WebMessagePort[] ch = web.createWebMessageChannel();
        ports.add(ch[0]);
        ch[0].setWebMessageCallback(new WebMessagePort.WebMessageCallback() {
            @Override
            public void onMessage(WebMessagePort p, WebMessage m) {
                heard = true;
                handle(p, m.getData());
            }
        }, main);
        web.postWebMessage(new WebMessage("daf-shell", new WebMessagePort[]{ch[1]}), Uri.parse(Server.base(activity)));
    }

    /** Whether the page has used a port since its document started. */
    boolean heard() {
        return heard;
    }

    /** A new document: the last one's ports go. */
    void close() {
        for (WebMessagePort p : ports) {
            try { p.close(); } catch (RuntimeException ignored) { }
        }
        ports.clear();
        heard = false;
    }

    private void handle(WebMessagePort p, String data) {
        int id = -1;
        try {
            JSONObject m = new JSONObject(data);
            id = m.optInt("id", -1);
            JSONObject a = m.optJSONObject("args");
            if (a == null) a = new JSONObject();
            switch (m.optString("op")) {
                case "share":
                    reply(p, id, share(a.optString("text"), a.optString("url"), a.optString("png"), a.optString("name")));
                    break;
                case "download":
                    download(p, id, a);
                    break;
                case "media":
                    String state = a.optString("state", "stopped");
                    activity.listening(!"stopped".equals(state));
                    Listen.update(activity, state, a.optString("title"), a.optString("sub"));
                    reply(p, id, true);
                    break;
                case "haptic":
                    reply(p, id, haptic(a.optString("kind")));
                    break;
                case "offline":
                    offline(p, id, a);
                    break;
                case "alerts":
                    // notifications for new posts: ask Android once, then the job looks every 15 minutes
                    FeedNews.start(activity);
                    final int asked = id;
                    if (FeedNews.allowed(activity)) reply(p, asked, true);
                    else activity.askToNotify(granted -> reply(p, asked, granted));
                    break;
                case "screen":
                    activity.screen(a.optBoolean("immersive"), a.optBoolean("awake"));
                    reply(p, id, true);
                    break;
                case "reading":
                    // volume buttons turn pages (the page's switch), and the page's text menu stands in for Android's
                    activity.reading(a.optBoolean("volumeKeys"), a.optBoolean("ownMenu"));
                    reply(p, id, true);
                    break;
                case "bars":
                    // the theme's background behind the status and navigation bars (themes.js's daf-theme)
                    reply(p, id, activity.bars(a.optString("bg"), a.optBoolean("dark")));
                    break;
                case "openExternal":
                    reply(p, id, activity.outside(Uri.parse(a.optString("url"))));
                    break;
                default:
                    fail(p, id, "no such shell call: " + m.optString("op"));
            }
        } catch (Exception e) {
            fail(p, id, String.valueOf(e.getMessage()));
        }
    }

    /** A tap felt in the hand, the way native apps answer: confirm (Keep), reject (Less often,
     *  Never again), tick (a tab, a highlight). */
    private boolean haptic(String kind) {
        int k = "confirm".equals(kind) ? android.view.HapticFeedbackConstants.CONFIRM
                : "reject".equals(kind) ? android.view.HapticFeedbackConstants.REJECT
                : android.view.HapticFeedbackConstants.CLOCK_TICK;
        return web.performHapticFeedback(k);
    }

    /** The share sheet: a PNG (Share as image) from the app's cache, a link or text. */
    private boolean share(String text, String url, String png, String name) throws Exception {
        Intent send = new Intent(Intent.ACTION_SEND);
        if (!png.isEmpty()) {
            File dir = new File(new File(activity.getCacheDir(), "share"), UUID.randomUUID().toString());
            if (!dir.mkdirs()) throw new Exception("no room in the cache");
            String file = (name.isEmpty() ? "Daf highlight" : name.replace("/", "-")).replaceAll("\\.png$", "") + ".png";
            File f = new File(dir, file);
            try (OutputStream out = new FileOutputStream(f)) { out.write(Base64.decode(png, Base64.DEFAULT)); }
            send.setType("image/png").putExtra(Intent.EXTRA_STREAM, ShareProvider.uriFor(activity, f))
                    .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
        } else {
            String all = (text + (url.isEmpty() || text.contains(url) ? "" : (text.isEmpty() ? "" : "\n") + url)).trim();
            if (all.isEmpty()) return false;
            send.setType("text/plain").putExtra(Intent.EXTRA_TEXT, all);
        }
        activity.startActivity(Intent.createChooser(send, null));
        return true;
    }

    /** A Daf address with the window's cookie, or bytes (a blob link, through shell.js). */
    private void download(WebMessagePort p, int id, JSONObject a) {
        String url = a.optString("url");
        if (!url.isEmpty()) {
            String full = url.startsWith("/") ? Server.base(activity) + url : url;
            activity.download(full, android.webkit.URLUtil.guessFileName(full, null, null), null);
            reply(p, id, true);
            return;
        }
        byte[] bytes = Base64.decode(a.optString("base64"), Base64.DEFAULT);
        String name = a.optString("name", "Daf").replace("/", "-");
        String mime = a.optString("mime");
        activity.createDocument(name.isEmpty() ? "Daf" : name, mime.isEmpty() ? "application/octet-stream" : mime, where -> {
            if (where == null) { reply(p, id, false); return; }
            try (OutputStream out = activity.getContentResolver().openOutputStream(where)) {
                if (out == null) throw new Exception("no place to write");
                out.write(bytes);
                reply(p, id, true);
            } catch (Exception e) {
                fail(p, id, String.valueOf(e.getMessage()));
            }
        });
    }

    /** What's on the phone for no signal: list, has, keep {id, on}, doc {id, on}, manga {id, on, size}, sync. Downloads happen away from the window. */
    private void offline(WebMessagePort p, int id, JSONObject a) {
        String what = a.optString("op", "list"), book = a.optString("id");
        new Thread(() -> {
            try {
                JSONObject out;
                switch (what) {
                    case "has":
                        out = new JSONObject().put("has", Offline.has(activity, book));
                        break;
                    case "keep":
                        if (book.isEmpty()) throw new Exception("which book?");
                        Offline.keep(activity, book, a.optBoolean("on", true));
                        Offline.schedule(activity, true);
                        out = Offline.list(activity);
                        break;
                    case "sync":
                        String said = Offline.sync(activity);
                        out = Offline.list(activity).put("said", said);
                        break;
                    case "doc":
                        // an article kept on the device for good (the reader's ⋯ menu), or let go
                        if (book.isEmpty()) throw new Exception("which article?");
                        DataStore.keepDoc(activity, book, a.optBoolean("on", true));
                        out = Offline.list(activity);
                        break;
                    case "manga":
                        // a manga volume for reading with no Wi-Fi: downloads away from the window
                        if (book.isEmpty()) throw new Exception("which volume?");
                        if (a.optBoolean("on", true)) Offline.keepManga(activity, book, Math.max(600, Math.min(2400, a.optInt("size", 1800))));
                        else Offline.removeManga(activity, book);
                        out = Offline.list(activity);
                        break;
                    default:
                        out = Offline.list(activity);
                }
                send(p, "{\"id\":" + id + ",\"ok\":true,\"value\":" + out + "}");
            } catch (Exception e) {
                fail(p, id, e instanceof java.io.IOException ? "Daf didn't answer: " + e.getMessage() : String.valueOf(e.getMessage()));
            }
        }).start();
    }

    private void reply(WebMessagePort p, int id, boolean value) {
        send(p, "{\"id\":" + id + ",\"ok\":true,\"value\":" + value + "}");
    }

    private void fail(WebMessagePort p, int id, String error) {
        send(p, "{\"id\":" + id + ",\"ok\":false,\"error\":" + JSONObject.quote(error) + "}");
    }

    private void send(WebMessagePort p, String json) {
        main.post(() -> {
            try { p.postMessage(new WebMessage(json)); } catch (RuntimeException ignored) { /* the page has gone */ }
        });
    }
}
