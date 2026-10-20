package xyz.tiresia.daf;

import android.content.Context;
import android.content.SharedPreferences;
import android.net.Uri;
import android.webkit.CookieManager;
import android.webkit.WebResourceRequest;
import android.webkit.WebResourceResponse;

import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

/**
 * Daf's data on the device, for reading with no network: what the server says Daf should keep
 * (GET /api/offline/plan: today, the review for the next days, the lists, the articles and their
 * pictures), fetched with the window's sign-in on Wi-Fi and kept by its address, query included.
 * While the network is down (Net.down), the WebView and the service worker get them from here;
 * otherwise everything goes to Daf as usual. What's done offline waits in the page's outbox.
 *
 * What nothing names any more (not the plan, not an article kept by hand, not their pictures or
 * PDFs) leaves three weeks after it was last kept or read here, so the store doesn't grow forever.
 */
final class DataStore {
    private static final long MAX_IMAGE = 4L * 1024 * 1024;
    private static final int MAX_IMAGES = 400;
    private static final long KEEP_FOR = 21 * 24 * 60 * 60 * 1000L;
    private static final Object LOCK = new Object();

    private static SharedPreferences prefs(Context c) {
        return c.getSharedPreferences("datastore", Context.MODE_PRIVATE);
    }

    private static File dir(Context c) {
        File d = new File(c.getFilesDir(), "data");
        //noinspection ResultOfMethodCallIgnored
        d.mkdirs();
        return d;
    }

    /** The key for an address: Daf's own by path and query, others by the whole URL. */
    static String key(Context c, Uri u) {
        if (Server.isOurs(c, u)) return u.getEncodedPath() + (u.getEncodedQuery() == null ? "" : "?" + u.getEncodedQuery());
        return u.toString();
    }

    private static File file(Context c, String key) {
        return new File(dir(c), sha1(key));
    }

    private static final String[] SAME = {"where", "tab", "kind", "cat", "feed"};

    /** A list kept in another order or with other filters still answers for the same list: the
     *  Library's and Feed's lists by where, tab, kind, cat and feed; Highlights whatever its query. */
    static String anyKey(String key) {
        int q = key.indexOf('?');
        String path = q < 0 ? key : key.substring(0, q);
        if (path.equals("/api/highlights")) return "/api/highlights?_any";
        if (!path.equals("/api/docs")) return null;
        Uri u = Uri.parse("http://x" + key);
        StringBuilder out = new StringBuilder("/api/docs?_any");
        for (String k : SAME) out.append('&').append(k).append('=').append(u.getQueryParameter(k) == null ? "" : u.getQueryParameter(k));
        return out.toString();
    }

    /** id → type, so an answer has the type it came with. */
    private static JSONObject index(Context c) {
        try { return new JSONObject(prefs(c).getString("index", "{}")); } catch (JSONException e) { return new JSONObject(); }
    }

    // ---- served while the network is down ----

    static WebResourceResponse intercept(Context c, WebResourceRequest r) {
        if (!"GET".equalsIgnoreCase(r.getMethod())) return null;
        Uri u = r.getUrl();
        if (u.getScheme() == null || !u.getScheme().startsWith("http")) return null;
        String k = key(c, u);
        File f = file(c, k);
        if (!f.isFile() && Server.isOurs(c, u) && u.getEncodedQuery() != null) {
            f = file(c, u.getEncodedPath());                  // a doc kept without its ?prefetch=1
            k = u.getEncodedPath();
            String any = anyKey(key(c, u));
            if (!f.isFile() && any != null) { f = file(c, any); k = any; }
        }
        if (!f.isFile()) return null;
        //noinspection ResultOfMethodCallIgnored
        f.setLastModified(System.currentTimeMillis());            // read here: it stays three weeks more
        String type;
        synchronized (LOCK) { type = index(c).optString(sha1(k), "application/json"); }
        try {
            Map<String, String> h = new HashMap<>();
            h.put("Content-Length", String.valueOf(f.length()));
            h.put("Cache-Control", "no-store");
            h.put("X-Daf-Offline", "1");
            return new WebResourceResponse(type, type.contains("json") || type.startsWith("text/") ? "utf-8" : null, 200, "OK", h, new FileInputStream(f));
        } catch (IOException e) {
            return null;
        }
    }

    // ---- kept up to date on Wi-Fi ----

    /** Fetches what the server's plan names. Returns a short summary. */
    static String sync(Context c) throws IOException {
        JSONObject plan;
        try {
            plan = new JSONObject(new String(get(c, Server.url(c, "/api/offline/plan"), true).body, StandardCharsets.UTF_8));
        } catch (JSONException | IOException e) {
            plan = fallbackPlan();
        }
        Set<String> wanted = new LinkedHashSet<>(), live = new java.util.HashSet<>();
        JSONArray urls = plan.optJSONArray("urls");
        for (int i = 0; urls != null && i < urls.length(); i++) wanted.add(urls.optString(i));
        for (String u : wanted) { live.add(u); if (anyKey(u) != null) live.add(anyKey(u)); }
        JSONArray docs = plan.optJSONArray("docs");
        List<String> images = new ArrayList<>();
        JSONArray imgs = plan.optJSONArray("images");
        for (int i = 0; imgs != null && i < imgs.length(); i++) images.add(imgs.optString(i));
        int got = 0, failed = 0;
        for (String path : wanted) {
            try { keep(c, path, Server.url(c, path), true); got++; } catch (IOException e) { failed++; }
        }
        java.util.Set<String> kept = new java.util.HashSet<>();
        for (int i = 0; docs != null && i < docs.length(); i++) {
            String id = docs.optString(i), path = "/api/docs/" + Uri.encode(id);
            try {
                byte[] b = keep(c, path, Server.url(c, path + "?prefetch=1"), true);
                images.addAll(pictures(b));
                pdf(c, path, b, live);
                kept.add(id);
                live.add(path);
                got++;
            } catch (IOException e) { failed++; }
        }
        prefs(c).edit().putStringSet("plandocs", kept).apply();
        // the articles kept by hand, brought up to date too; one deleted in Daf goes
        java.util.Set<String> dropped = new java.util.HashSet<>();
        for (String id : pinned(c)) {
            String path = "/api/docs/" + Uri.encode(id);
            live.add(path);
            try {
                byte[] b = kept.contains(id) ? read(file(c, path)) : keep(c, path, Server.url(c, path + "?prefetch=1"), true);
                if (deleted(b)) throw new Gone();
                for (String img : pictures(b)) live.add(key(c, Uri.parse(img.startsWith("/") ? Server.url(c, img) : img)));
                pdf(c, path, b, live);
            } catch (Gone e) {                                       // deleted in Daf: it goes from here too
                dropped.add(id);
                live.remove(path);
                //noinspection ResultOfMethodCallIgnored
                file(c, path).delete();
            } catch (IOException e) {
                // no answer now: what's here stays, and its pictures with it
                try { for (String img : pictures(read(file(c, path)))) live.add(key(c, Uri.parse(img.startsWith("/") ? Server.url(c, img) : img))); } catch (IOException ignored) { }
            }
        }
        if (!dropped.isEmpty()) synchronized (LOCK) {                // only these: one kept meanwhile stays
            java.util.Set<String> now = pinned(c);
            now.removeAll(dropped);
            prefs(c).edit().putStringSet("pinned", now).commit();
        }
        JSONArray ebooks = plan.optJSONArray("ebooks");                 // the books to have on the device too
        for (int i = 0; ebooks != null && i < ebooks.length(); i++) {
            try { Offline.fetch(c, ebooks.optString(i), false); } catch (IOException ignored) { }
        }
        int pics = 0;
        for (String img : images) {
            if (pics >= MAX_IMAGES) break;
            if (img == null || img.isEmpty() || img.startsWith("data:")) continue;
            String abs = img.startsWith("/") ? Server.url(c, img) : img;
            Uri u = Uri.parse(abs);
            live.add(key(c, u));
            if (file(c, key(c, u)).isFile()) { pics++; continue; }
            try { keep(c, key(c, u), abs, Server.isOurs(c, u)); pics++; } catch (IOException ignored) { }
        }
        int gone = prune(c, live);
        prefs(c).edit().putLong("synced", System.currentTimeMillis()).apply();
        return got + " kept" + (failed > 0 ? ", " + failed + " didn't come" : "") + ", " + pics + " pictures" + (gone > 0 ? ", " + gone + " let go" : "");
    }

    /** Until the server names the plan: the pages Daf opens on. */
    private static JSONObject fallbackPlan() {
        JSONObject p = new JSONObject();
        try {
            p.put("urls", new JSONArray(new String[]{"/api/me", "/api/settings", "/api/today", "/api/review", "/api/home", "/api/books",
                    "/api/highlights", "/api/docs/counts", "/api/stats"}));
        } catch (JSONException ignored) { }
        return p;
    }

    /** A PDF's own file, for its pages as printed: kept once (a PDF doesn't change). */
    private static void pdf(Context c, String path, byte[] doc, Set<String> live) {
        try {
            JSONObject d = new JSONObject(new String(doc, StandardCharsets.UTF_8));
            if (!"pdf".equals(d.optString("kind")) && !d.optBoolean("has_pdf")) return;
        } catch (JSONException e) { return; }
        String key = path + "/pdf";
        live.add(key);
        if (file(c, key).isFile()) return;
        try { keep(c, key, Server.url(c, key), true); } catch (IOException ignored) { }
    }

    /** Lets go of what nothing names any more (live: the keys that stay), once it hasn't been kept
     *  or read here for three weeks. Returns how many files went. */
    private static int prune(Context c, Set<String> live) {
        Set<String> names = new java.util.HashSet<>();
        for (String k : live) names.add(sha1(k));
        long old = System.currentTimeMillis() - KEEP_FOR;
        File[] files = dir(c).listFiles();
        if (files == null) return 0;
        int n = 0;
        synchronized (LOCK) {
            for (File f : files) {
                if (names.contains(f.getName()) || f.lastModified() >= old) continue;
                if (f.delete()) n++;
            }
            JSONObject idx = index(c), now = new JSONObject();
            for (java.util.Iterator<String> it = idx.keys(); it.hasNext(); ) {
                String k = it.next();
                if (new File(dir(c), k).isFile()) try { now.put(k, idx.get(k)); } catch (JSONException ignored) { }
            }
            prefs(c).edit().putString("index", now.toString()).apply();
        }
        return n;
    }

    /** How much is kept here, for Settings. */
    static long bytes(Context c) {
        long n = 0;
        File[] files = dir(c).listFiles();
        if (files != null) for (File f : files) n += f.length();
        return n;
    }

    private static byte[] read(File f) throws IOException {
        try (InputStream in = new FileInputStream(f)) {
            ByteArrayOutputStream out = new ByteArrayOutputStream();
            byte[] chunk = new byte[65536];
            for (int k; (k = in.read(chunk)) > 0; ) out.write(chunk, 0, k);
            return out.toByteArray();
        }
    }

    /** A doc deleted in Daf (it still answers, for Undo). */
    private static boolean deleted(byte[] doc) {
        try { return "deleted".equals(new JSONObject(new String(doc, StandardCharsets.UTF_8)).optString("status")); } catch (JSONException e) { return false; }
    }

    /** Daf says there's no such thing (any more). */
    static final class Gone extends IOException {
        Gone() { super("not in Daf any more"); }
    }

    /** The pictures in a doc's blocks. */
    private static List<String> pictures(byte[] doc) {
        List<String> out = new ArrayList<>();
        try {
            JSONObject d = new JSONObject(new String(doc, StandardCharsets.UTF_8));
            JSONArray blocks = d.optJSONArray("blocks");
            for (int i = 0; blocks != null && i < blocks.length(); i++) {
                JSONObject b = blocks.optJSONObject(i);
                if (b != null && "img".equals(b.optString("t"))) {
                    String src = b.optString("src", b.optString("x"));
                    if (src.startsWith("http") || src.startsWith("/")) out.add(src);
                }
            }
            String thumb = d.optString("thumb");
            if (!thumb.isEmpty()) out.add(thumb);
        } catch (JSONException ignored) { }
        return out;
    }

    private static byte[] keep(Context c, String key, String url, boolean ours) throws IOException {
        Got g = get(c, url, ours);
        if (!ours && g.body.length > MAX_IMAGE) throw new IOException("too big");
        String any = ours ? anyKey(key) : null;
        for (String k : any == null ? new String[]{key} : new String[]{key, any}) {
            File f = file(c, k);
            File part = new File(f.getPath() + ".part");
            try (OutputStream out = new FileOutputStream(part)) { out.write(g.body); }
            if (!part.renameTo(f)) throw new IOException("couldn't keep it");
            synchronized (LOCK) {
                JSONObject idx = index(c);
                try { idx.put(sha1(k), g.type == null ? "application/octet-stream" : g.type.split(";")[0].trim()); } catch (JSONException ignored) { }
                prefs(c).edit().putString("index", idx.toString()).apply();
            }
        }
        return g.body;
    }

    private static final class Got { byte[] body; String type; }

    private static Got get(Context c, String url, boolean ours) throws IOException {
        HttpURLConnection h = (HttpURLConnection) new URL(url).openConnection();
        h.setConnectTimeout(10000);
        h.setReadTimeout(30000);
        h.setUseCaches(false);
        h.setInstanceFollowRedirects(true);
        h.setRequestProperty("User-Agent", "Daf/" + Daf.version(c) + " (Android shell)");
        if (ours) {
            String cookie = CookieManager.getInstance().getCookie(Server.base(c));
            if (cookie != null) h.setRequestProperty("Cookie", cookie);
            String t = Server.token(c);
            if (t != null && cookie == null) h.setRequestProperty("Authorization", "Bearer " + t);
        }
        try {
            int s = h.getResponseCode();
            if (ours && (s == 404 || s == 410)) throw new Gone();
            if (s != 200) throw new IOException("answered " + s);
            Got g = new Got();
            g.type = h.getContentType();
            try (InputStream in = h.getInputStream()) {
                ByteArrayOutputStream out = new ByteArrayOutputStream();
                byte[] chunk = new byte[65536];
                long n = 0;
                for (int k; (k = in.read(chunk)) > 0; ) { out.write(chunk, 0, k); if ((n += k) > 64L * 1024 * 1024) throw new IOException("too big"); }
                g.body = out.toByteArray();
            }
            return g;
        } finally {
            h.disconnect();
        }
    }

    static long synced(Context c) {
        return prefs(c).getLong("synced", 0);
    }

    // ---- articles kept by hand (the reader's ⋯ menu), beside the ones the plan names ----

    /** Keeps an article and its pictures on the device for good, or lets it go. */
    static void keepDoc(Context c, String id, boolean on) throws IOException {
        if (on) {
            String path = "/api/docs/" + Uri.encode(id);
            byte[] b = keep(c, path, Server.url(c, path + "?prefetch=1"), true);
            for (String img : pictures(b)) {
                String abs = img.startsWith("/") ? Server.url(c, img) : img;
                Uri u = Uri.parse(abs);
                try { keep(c, key(c, u), abs, Server.isOurs(c, u)); } catch (IOException ignored) { }
            }
            pdf(c, path, b, new java.util.HashSet<>());
        } else if (!prefs(c).getStringSet("plandocs", new java.util.HashSet<>()).contains(id)) {
            String path = "/api/docs/" + Uri.encode(id);               // the plan doesn't want it either: it goes now
            //noinspection ResultOfMethodCallIgnored
            file(c, path).delete();
            //noinspection ResultOfMethodCallIgnored
            file(c, path + "/pdf").delete();
        }
        synchronized (LOCK) {                                   // read again here: a sync may have changed it meanwhile
            java.util.Set<String> now = pinned(c);
            if (on) now.add(id); else now.remove(id);
            prefs(c).edit().putStringSet("pinned", now).commit();
        }
    }

    /** The articles kept by hand: a copy, to change and put back. */
    private static java.util.Set<String> pinned(Context c) {
        return new java.util.HashSet<>(prefs(c).getStringSet("pinned", new java.util.HashSet<>()));
    }

    /** The articles on the device: [{id, pinned}]. */
    static JSONArray docs(Context c) {
        JSONArray out = new JSONArray();
        java.util.Set<String> pinned = prefs(c).getStringSet("pinned", new java.util.HashSet<>());
        java.util.Set<String> seen = new java.util.HashSet<>();
        for (String id : pinned) { add(out, id, true); seen.add(id); }
        for (String id : prefs(c).getStringSet("plandocs", new java.util.HashSet<>())) if (seen.add(id)) add(out, id, false);
        return out;
    }

    private static void add(JSONArray out, String id, boolean pinned) {
        try { out.put(new JSONObject().put("id", id).put("pinned", pinned)); } catch (JSONException ignored) { }
    }

    private static String sha1(String s) {
        try {
            StringBuilder out = new StringBuilder();
            for (byte x : MessageDigest.getInstance("SHA-1").digest(s.getBytes(StandardCharsets.UTF_8))) out.append(String.format("%02x", x));
            return out.toString();
        } catch (Exception e) {
            return Integer.toHexString(s.hashCode());
        }
    }
}
