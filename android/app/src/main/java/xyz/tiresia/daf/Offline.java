package xyz.tiresia.daf;

import android.app.job.JobInfo;
import android.app.job.JobParameters;
import android.app.job.JobScheduler;
import android.app.job.JobService;
import android.content.ComponentName;
import android.content.Context;
import android.content.SharedPreferences;
import android.net.ConnectivityManager;
import android.net.NetworkCapabilities;
import android.net.Uri;
import android.util.Base64;
import android.webkit.CookieManager;
import android.webkit.WebResourceRequest;
import android.webkit.WebResourceResponse;

import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;

import java.io.ByteArrayInputStream;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.Iterator;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * Books on the phone, for reading with no signal (Round 3). A book opened in the app is kept
 * in the app's own storage, and so are the books being read (the nightstand, then the last few
 * read anywhere) and any kept by hand; a job brings them up to date on Wi-Fi.
 *
 * The WebView, and the page's service worker, get a book's file from here, so it opens at once
 * and offline; its details (/api/ebooks/{id}: the place, the highlights) come from Daf when it
 * answers and from the copy here when it doesn't. What's done offline waits in the page's
 * outbox (app.js) and goes when the network is back.
 *
 * Only the window's sign-in (its cookie) fetches, and only from Daf's own address.
 */
public class Offline extends JobService {
    private static final Pattern FILE = Pattern.compile("^/api/ebooks/([^/]+)/file$"), INFO = Pattern.compile("^/api/ebooks/([^/]+)$");
    private static final Pattern MPAGE = Pattern.compile("^/api/manga/books/([^/]+)/pages/(\\d+)$"), MBOOK = Pattern.compile("^/api/manga/books/([^/]+)$");
    private static final ExecutorService MANGA = Executors.newSingleThreadExecutor();   // one volume at a time
    private static final int JOB = 32;
    private static final long DAY = 24 * 60 * 60 * 1000L;
    private static final int READING = 4;                 // besides the nightstand, the last few read
    private static final Object LOCK = new Object();
    private static final ExecutorService WORK = Executors.newSingleThreadExecutor();
    private static final Map<String, Object> FETCHING = new HashMap<>();

    // ---- settings ----

    static SharedPreferences prefs(Context c) {
        return c.getSharedPreferences("offline", Context.MODE_PRIVATE);
    }

    /** Keep the books being read on the phone, not only the ones opened here. */
    static boolean reading(Context c) { return prefs(c).getBoolean("reading", true); }
    /** The job downloads only on Wi-Fi (or any unmetered network). */
    static boolean wifiOnly(Context c) { return prefs(c).getBoolean("wifi", true); }

    static void setReading(Context c, boolean on) { prefs(c).edit().putBoolean("reading", on).apply(); schedule(c, true); }
    static void setWifiOnly(Context c, boolean on) { prefs(c).edit().putBoolean("wifi", on).apply(); schedule(c, true); }

    // ---- the store: books/<id>.book and .json, and an index in the preferences ----

    private static File dir(Context c) {
        File d = new File(c.getFilesDir(), "books");
        //noinspection ResultOfMethodCallIgnored
        d.mkdirs();
        return d;
    }

    private static String safe(String id) {
        return Base64.encodeToString(id.getBytes(StandardCharsets.UTF_8), Base64.URL_SAFE | Base64.NO_WRAP | Base64.NO_PADDING);
    }

    private static File file(Context c, String id) { return new File(dir(c), safe(id) + ".book"); }
    private static File info(Context c, String id) { return new File(dir(c), safe(id) + ".json"); }

    /** id → {title, private, format, size, type, saved, checked, opened, kept}. */
    private static JSONObject index(Context c) {
        try { return new JSONObject(prefs(c).getString("index", "{}")); } catch (JSONException e) { return new JSONObject(); }
    }

    private static void store(Context c, JSONObject idx) {
        prefs(c).edit().putString("index", idx.toString()).apply();
    }

    private static void note(Context c, String id, String key, Object value) {
        synchronized (LOCK) {
            JSONObject idx = index(c), e = idx.optJSONObject(id);
            if (e == null) return;
            try { e.put(key, value); idx.put(id, e); } catch (JSONException ignored) { }
            store(c, idx);
        }
    }

    // ---- the WebView and the service worker ask ----

    /** A book's file from the phone (fetched and kept first, if it isn't here yet); its details
     *  from Daf, or from the phone's copy when Daf doesn't answer. Null: the network as usual. */
    static WebResourceResponse intercept(Context c, WebResourceRequest r) {
        if (!"GET".equalsIgnoreCase(r.getMethod())) return null;
        Uri u = r.getUrl();
        String path = u.getPath();
        if (path == null || !Server.isOurs(c, u)) return null;
        Matcher mm = MPAGE.matcher(path);
        if (mm.matches()) {                        // a manga page kept on the device, whatever ?size= asks
            File f = mangaPage(c, Uri.decode(mm.group(1)), Integer.parseInt(mm.group(2)));
            return f.exists() ? answer(f, mangaEntry(c, Uri.decode(mm.group(1))).optString("type", "image/webp")) : null;
        }
        mm = MBOOK.matcher(path);
        if (mm.matches()) {
            String id = Uri.decode(mm.group(1));
            File f = new File(mangaDir(c, id), "book.json");
            if (!f.exists()) return null;
            try {
                byte[] b = get(c, path);
                if (b == null) return null;
                return new WebResourceResponse("application/json", "utf-8", 200, "OK", headers(b.length), new ByteArrayInputStream(b));
            } catch (IOException offline) {
                return answer(f, "application/json");
            }
        }
        Matcher m = FILE.matcher(path);
        if (m.matches()) {
            String id = Uri.decode(m.group(1));
            File f = file(c, id);
            if (!f.exists()) {
                try { fetch(c, id, true); } catch (Exception e) { return null; }       // the page shows Daf's own answer
            } else if (System.currentTimeMillis() - entry(c, id).optLong("checked") > DAY) {
                WORK.execute(() -> { try { fetch(c, id, false); } catch (Exception ignored) { } });
            }
            JSONObject e = entry(c, id);
            if (!f.exists()) return null;
            note(c, id, "opened", System.currentTimeMillis());
            return answer(f, e.optString("type", "application/epub+zip"));
        }
        m = INFO.matcher(path);
        if (m.matches()) {
            String id = Uri.decode(m.group(1));
            File f = info(c, id);
            if (!f.exists() && !file(c, id).exists()) return null;     // not a book on the phone: as usual
            try {
                byte[] b = get(c, "/api/ebooks/" + Uri.encode(id));
                if (b == null) return null;                                       // Daf said no: let the page hear it
                write(f, b);
                return new WebResourceResponse("application/json", "utf-8", 200, "OK", headers(b.length), new ByteArrayInputStream(b));
            } catch (IOException offline) {
                return f.exists() ? answer(f, "application/json") : null;
            }
        }
        return null;
    }

    private static JSONObject entry(Context c, String id) {
        synchronized (LOCK) {
            JSONObject e = index(c).optJSONObject(id);
            return e == null ? new JSONObject() : e;
        }
    }

    private static WebResourceResponse answer(File f, String type) {
        try {
            return new WebResourceResponse(type, type.startsWith("application/json") ? "utf-8" : null, 200, "OK", headers(f.length()), new FileInputStream(f));
        } catch (IOException e) {
            return null;
        }
    }

    private static Map<String, String> headers(long length) {
        Map<String, String> h = new HashMap<>();
        h.put("Content-Length", String.valueOf(length));
        h.put("Cache-Control", "no-store");
        return h;
    }

    // ---- fetching ----

    /** A book's details and file onto the phone; the file only when it changed (format, size). */
    static void fetch(Context c, String id, boolean opened) throws IOException {
        Object mine;
        synchronized (FETCHING) {
            mine = FETCHING.get(id);
            if (mine == null) FETCHING.put(id, mine = new Object());
        }
        synchronized (mine) {
            try {
                byte[] b = get(c, "/api/ebooks/" + Uri.encode(id));
                if (b == null) { remove(c, id); return; }                   // no readable file in Calibre any more
                JSONObject d;
                try { d = new JSONObject(new String(b, StandardCharsets.UTF_8)); } catch (JSONException e) { throw new IOException("not JSON"); }
                write(info(c, id), b);
                JSONObject e = entry(c, id);
                File f = file(c, id);
                String type = e.optString("type", null);
                boolean same = f.exists() && d.optString("format").equals(e.optString("format")) && d.optLong("size", -1) == f.length();
                if (!same) type = download(c, "/api/ebooks/" + Uri.encode(id) + "/file", f);
                synchronized (LOCK) {
                    JSONObject idx = index(c), now = idx.optJSONObject(id);
                    if (now == null) now = new JSONObject();
                    now.put("title", d.optString("title"));
                    now.put("private", d.optBoolean("private"));
                    now.put("format", d.optString("format"));
                    now.put("size", f.length());
                    now.put("type", type == null ? "application/epub+zip" : type);
                    now.put("checked", System.currentTimeMillis());
                    if (!same) now.put("saved", System.currentTimeMillis());
                    if (opened) now.put("opened", System.currentTimeMillis());
                    idx.put(id, now);
                    store(c, idx);
                }
            } catch (JSONException e) {
                throw new IOException(e.getMessage());
            }
        }
    }

    private static HttpURLConnection open(Context c, String path) throws IOException {
        HttpURLConnection h = (HttpURLConnection) new URL(Server.url(c, path)).openConnection();
        h.setConnectTimeout(8000);
        h.setReadTimeout(30000);
        h.setUseCaches(false);
        h.setRequestProperty("User-Agent", "Daf/" + Daf.version(c) + " (Android shell)");
        String cookie = CookieManager.getInstance().getCookie(Server.base(c));
        if (cookie != null) h.setRequestProperty("Cookie", cookie);
        return h;
    }

    /** Daf's answer, or null when it says there's no such thing (404); IOException: no answer. */
    private static byte[] get(Context c, String path) throws IOException {
        HttpURLConnection h = open(c, path);
        try {
            int s = h.getResponseCode();
            if (s == 404) return null;
            if (s != 200) throw new IOException("Daf answered " + s);
            try (InputStream in = h.getInputStream()) {
                java.io.ByteArrayOutputStream out = new java.io.ByteArrayOutputStream();
                byte[] chunk = new byte[16384];
                for (int n; (n = in.read(chunk)) > 0; ) out.write(chunk, 0, n);
                return out.toByteArray();
            }
        } finally {
            h.disconnect();
        }
    }

    /** A file from Daf into place, whole or not at all. Returns its type. */
    private static String download(Context c, String path, File into) throws IOException {
        HttpURLConnection h = open(c, path);
        File part = new File(into.getPath() + ".part");
        try {
            if (h.getResponseCode() != 200) throw new IOException("Daf answered " + h.getResponseCode());
            try (InputStream in = h.getInputStream(); OutputStream out = new FileOutputStream(part)) {
                byte[] chunk = new byte[65536];
                for (int n; (n = in.read(chunk)) > 0; ) out.write(chunk, 0, n);
            }
            if (!part.renameTo(into)) throw new IOException("couldn't keep the file");
            return h.getContentType();
        } finally {
            h.disconnect();
            //noinspection ResultOfMethodCallIgnored
            part.delete();
        }
    }

    private static void write(File f, byte[] b) throws IOException {
        File part = new File(f.getPath() + ".part");
        try (OutputStream out = new FileOutputStream(part)) { out.write(b); }
        if (!part.renameTo(f)) throw new IOException("couldn't keep the file");
    }

    static void remove(Context c, String id) {
        //noinspection ResultOfMethodCallIgnored
        file(c, id).delete();
        //noinspection ResultOfMethodCallIgnored
        info(c, id).delete();
        synchronized (LOCK) {
            JSONObject idx = index(c);
            idx.remove(id);
            store(c, idx);
        }
    }

    // ---- manga: a volume's pages, for reading with no Wi-Fi (the series page's download buttons) ----

    private static File mangaDir(Context c, String id) {
        return new File(new File(c.getFilesDir(), "manga"), safe(id));
    }

    private static File mangaPage(Context c, String id, int n) {
        return new File(mangaDir(c, id), "p" + n);
    }

    private static JSONObject mangaEntry(Context c, String id) {
        synchronized (LOCK) {
            JSONObject e = index(c).optJSONObject("manga:" + id);
            return e == null ? new JSONObject() : e;
        }
    }

    private static void mangaNote(Context c, String id, JSONObject fields) {
        synchronized (LOCK) {
            JSONObject idx = index(c), e = idx.optJSONObject("manga:" + id);
            try {
                if (e == null) e = new JSONObject().put("kind", "manga");
                for (Iterator<String> it = fields.keys(); it.hasNext(); ) { String k = it.next(); e.put(k, fields.get(k)); }
                idx.put("manga:" + id, e);
            } catch (JSONException ignored) { }
            store(c, idx);
        }
    }

    /** Downloads a volume's pages at the size this screen's reader asks for, one volume at a time;
     *  what's already here is kept, so tapping again carries on. */
    static void keepManga(Context c, String id, int size) {
        try {
            mangaNote(c, id, new JSONObject().put("state", "waiting").put("size", size).put("at", System.currentTimeMillis()));
        } catch (JSONException ignored) { }
        MANGA.execute(() -> {
            try {
                byte[] b = get(c, "/api/manga/books/" + Uri.encode(id));
                if (b == null) throw new IOException("Komga doesn't have it any more");
                JSONObject d = new JSONObject(new String(b, StandardCharsets.UTF_8));
                File dir = mangaDir(c, id);
                //noinspection ResultOfMethodCallIgnored
                dir.mkdirs();
                write(new File(dir, "book.json"), b);
                int total = d.optJSONArray("pages") == null ? 0 : d.optJSONArray("pages").length();
                JSONObject series = d.optJSONObject("series");
                mangaNote(c, id, new JSONObject().put("state", "loading").put("total", total).put("title", d.optString("name"))
                        .put("series", series == null ? "" : series.optString("name")));
                long bytes = 0;
                String type = "image/webp";
                for (int n = 1; n <= total; n++) {
                    File f = mangaPage(c, id, n);
                    if (!f.exists()) {
                        String t = download(c, "/api/manga/books/" + Uri.encode(id) + "/pages/" + n + "?size=" + size, f);
                        if (t != null) type = t;
                    }
                    bytes += f.length();
                    if (n % 5 == 0 || n == total) mangaNote(c, id, new JSONObject().put("done", n).put("bytes", bytes).put("type", type));
                    if (!mangaEntry(c, id).has("state")) return;            // removed while it loaded
                }
                mangaNote(c, id, new JSONObject().put("state", "done").put("saved", System.currentTimeMillis()));
            } catch (Exception e) {
                try { mangaNote(c, id, new JSONObject().put("state", "failed").put("error", String.valueOf(e.getMessage()))); } catch (JSONException ignored) { }
            }
        });
    }

    static void removeManga(Context c, String id) {
        synchronized (LOCK) {
            JSONObject idx = index(c);
            idx.remove("manga:" + id);
            store(c, idx);
        }
        File dir = mangaDir(c, id);
        File[] files = dir.listFiles();
        if (files != null) for (File f : files) //noinspection ResultOfMethodCallIgnored
            f.delete();
        //noinspection ResultOfMethodCallIgnored
        dir.delete();
    }

    // ---- the page's calls (dafShell.offline) and Settings ----

    /** What's on the phone: {books: [{id, title, size, kept, opened}], bytes, reading, wifi}. */
    static JSONObject list(Context c) {
        JSONObject out = new JSONObject();
        try {
            JSONArray books = new JSONArray();
            long bytes = 0;
            JSONObject idx;
            synchronized (LOCK) { idx = index(c); }
            JSONArray manga = new JSONArray();
            for (Iterator<String> it = idx.keys(); it.hasNext(); ) {
                String id = it.next();
                JSONObject e = idx.getJSONObject(id);
                if (id.startsWith("manga:")) {
                    bytes += e.optLong("bytes");
                    manga.put(new JSONObject().put("id", id.substring(6)).put("title", e.optString("title")).put("series", e.optString("series"))
                            .put("state", e.optString("state")).put("done", e.optInt("done")).put("total", e.optInt("total"))
                            .put("bytes", e.optLong("bytes")).put("error", e.optString("error", null)));
                    continue;
                }
                if (!file(c, id).exists()) continue;
                bytes += e.optLong("size");
                books.put(new JSONObject().put("id", id)
                        .put("title", e.optBoolean("private") ? "Private reading" : e.optString("title"))
                        .put("size", e.optLong("size")).put("kept", e.optBoolean("kept")).put("opened", e.optLong("opened")));
            }
            out.put("app", AppFiles.state(c)).put("data", DataStore.synced(c)).put("docs", DataStore.docs(c))
                    .put("books", books).put("manga", manga).put("bytes", bytes).put("reading", reading(c)).put("wifi", wifiOnly(c))
                    .put("synced", prefs(c).getLong("synced", 0));
        } catch (JSONException ignored) { }
        return out;
    }

    /** Keep a book on the phone (it stays until it's let go), or let it go. */
    static void keep(Context c, String id, boolean on) throws IOException {
        if (on) {
            fetch(c, id, false);
            note(c, id, "kept", true);
        } else {
            remove(c, id);
        }
    }

    static boolean has(Context c, String id) {
        return file(c, id).exists();
    }

    /** Brings the phone's books up to date: the ones being read and the ones kept; a book that
     *  was only being read leaves three weeks after it was last opened here. Returns a summary. */
    static String sync(Context c) throws IOException {
        // One at a time (the job, Settings, the page, the app's start). Asked while one runs: that
        // one is this one, waited for, rather than a second right after it.
        if (!SYNC.tryLock()) {
            SYNC.lock();
            SYNC.unlock();
            return said;
        }
        try {
            return said = syncNow(c);
        } finally {
            SYNC.unlock();
        }
    }

    private static final java.util.concurrent.locks.ReentrantLock SYNC = new java.util.concurrent.locks.ReentrantLock();
    private static volatile String said = "";

    private static String syncNow(Context c) throws IOException {
        Set<String> want = new LinkedHashSet<>();
        if (reading(c)) {
            byte[] b = get(c, "/api/books");
            if (b == null) throw new IOException("Daf has no book list");
            try {
                JSONObject books = new JSONObject(new String(b, StandardCharsets.UTF_8));
                JSONArray stand = books.optJSONArray("nightstand"), others = books.optJSONArray("others");
                for (int i = 0; stand != null && i < stand.length(); i++)
                    if (stand.getJSONObject(i).optBoolean("readable")) want.add(stand.getJSONObject(i).getString("id"));
                for (int i = 0, n = 0; others != null && i < others.length() && n < READING; i++) {
                    JSONObject x = others.getJSONObject(i);
                    if (x.optBoolean("readable")) { want.add(x.getString("id")); n++; }
                }
            } catch (JSONException e) {
                throw new IOException("Daf's book list wasn't JSON");
            }
        }
        JSONObject idx;
        synchronized (LOCK) { idx = index(c); }
        List<String> drop = new ArrayList<>();
        for (Iterator<String> it = idx.keys(); it.hasNext(); ) {
            String id = it.next();
            JSONObject e = idx.optJSONObject(id);
            if (e == null || id.startsWith("manga:")) continue;           // a manga volume stays until it's let go
            if (e.optBoolean("kept") || System.currentTimeMillis() - e.optLong("opened") < 21 * DAY) want.add(id);
            else if (!want.contains(id)) drop.add(id);
        }
        int got = 0;
        IOException last = null;
        for (String id : want) {
            try { fetch(c, id, false); got++; } catch (IOException e) { last = e; }
        }
        for (String id : drop) remove(c, id);
        // Daf's own screens and the data it says to keep (today, the review ahead, lists, articles)
        String data = "";
        try { AppFiles.refresh(c); } catch (IOException e) { last = e; }
        try { data = "; " + DataStore.sync(c); } catch (IOException e) { last = e; }
        if (got == 0 && last != null && want.size() > 0) throw last;
        prefs(c).edit().putLong("synced", System.currentTimeMillis()).apply();
        return got + (got == 1 ? " book" : " books") + " on the device" + data;
    }

    /** Runs a sync away from the window, unless one ran within the hour. */
    static void soon(Context c) {
        if (System.currentTimeMillis() - prefs(c).getLong("synced", 0) < 60 * 60 * 1000L) return;
        if (wifiOnly(c) && !unmetered(c)) return;
        WORK.execute(() -> { try { sync(c); } catch (IOException ignored) { } });
    }

    static boolean unmetered(Context c) {
        ConnectivityManager cm = c.getSystemService(ConnectivityManager.class);
        NetworkCapabilities n = cm == null ? null : cm.getNetworkCapabilities(cm.getActiveNetwork());
        return n != null && n.hasCapability(NetworkCapabilities.NET_CAPABILITY_NOT_METERED) && n.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET);
    }

    // ---- the job: every few hours, on Wi-Fi unless that's off ----

    /** Again only when a setting changed: scheduling anew starts the six hours over. */
    static void schedule(Context c, boolean again) {
        JobScheduler js = c.getSystemService(JobScheduler.class);
        if (js == null) return;
        if (!reading(c) && !hasKept(c)) { js.cancel(JOB); return; }
        if (!again && js.getPendingJob(JOB) != null) return;
        try {
            js.schedule(new JobInfo.Builder(JOB, new ComponentName(c, Offline.class))
                    .setPeriodic(6 * 60 * 60 * 1000L)
                    .setRequiredNetworkType(wifiOnly(c) ? JobInfo.NETWORK_TYPE_UNMETERED : JobInfo.NETWORK_TYPE_ANY)
                    .setPersisted(true)
                    .build());
        } catch (RuntimeException ignored) { }
    }

    private static boolean hasKept(Context c) {
        JSONObject idx;
        synchronized (LOCK) { idx = index(c); }
        for (Iterator<String> it = idx.keys(); it.hasNext(); ) {
            JSONObject e = idx.optJSONObject(it.next());
            if (e != null && e.optBoolean("kept")) return true;
        }
        return false;
    }

    @Override
    public boolean onStartJob(JobParameters params) {
        WORK.execute(() -> {
            boolean again = false;
            try { sync(getApplicationContext()); } catch (IOException e) { again = true; }
            jobFinished(params, again);
        });
        return true;
    }

    @Override
    public boolean onStopJob(JobParameters params) {
        return true;
    }

    /** For Settings: "3 books, 4.2 MB". */
    static String summary(Context c) {
        JSONObject l = list(c);
        int n = l.optJSONArray("books") == null ? 0 : l.optJSONArray("books").length();
        int m = l.optJSONArray("manga") == null ? 0 : l.optJSONArray("manga").length();
        String data = String.format(java.util.Locale.US, "%.0f MB", DataStore.bytes(c) / 1048576.0);
        if (n == 0 && m == 0) return "No books on this device yet. Articles, lists and pictures: " + data + ".";
        return (n > 0 ? n + (n == 1 ? " book" : " books") : "") + (n > 0 && m > 0 ? " and " : "") + (m > 0 ? m + (m == 1 ? " manga volume" : " manga volumes") : "")
                + ", " + String.format(java.util.Locale.US, "%.1f MB", l.optLong("bytes") / 1048576.0) + ". Articles, lists and pictures: " + data + ".";
    }
}
