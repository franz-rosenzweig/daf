package xyz.tiresia.daf;

import android.content.Context;
import android.content.SharedPreferences;
import android.net.Uri;
import android.webkit.MimeTypeMap;
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
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;

/**
 * Daf's own screens on the device, so the app starts and shows Daf with no network at all: a copy
 * of every file in the server's web/ (from /api/app-files, with their hashes; a file is fetched
 * again only when its hash changes), its fonts among them. When the network is down (Net.down),
 * the WebView and the page's service worker get these files from here.
 */
final class AppFiles {
    private static final Object LOCK = new Object();

    private static SharedPreferences prefs(Context c) {
        return c.getSharedPreferences("appfiles", Context.MODE_PRIVATE);
    }

    private static File root(Context c) {
        return new File(c.getFilesDir(), "app");
    }

    private static File local(Context c, String path) {
        return new File(root(c), path.replaceFirst("^/+", ""));
    }

    static boolean ready(Context c) {
        return local(c, "/index.html").exists();
    }

    /** {version, at}: which copy of Daf's screens is on the device, and since when. */
    static JSONObject state(Context c) {
        JSONObject o = new JSONObject();
        try { o.put("ready", ready(c)).put("version", prefs(c).getString("version", "")).put("at", prefs(c).getLong("at", 0)); } catch (JSONException ignored) { }
        return o;
    }

    // ---- served when the network is down ----

    static WebResourceResponse intercept(Context c, WebResourceRequest r) {
        if (!"GET".equalsIgnoreCase(r.getMethod())) return null;
        Uri u = r.getUrl();
        if (!Server.isOurs(c, u)) return null;
        String path = u.getPath() == null || u.getPath().isEmpty() || u.getPath().equals("/") ? "/index.html" : u.getPath();
        if (path.startsWith("/api/")) return null;
        File f = local(c, path);
        if (!f.isFile()) return null;
        return answer(f, type(path));
    }

    private static String type(String path) {
        String ext = MimeTypeMap.getFileExtensionFromUrl(path);
        if (path.endsWith(".mjs") || path.endsWith(".js")) return "text/javascript";
        if (path.endsWith(".webmanifest")) return "application/manifest+json";
        String t = ext == null ? null : MimeTypeMap.getSingleton().getMimeTypeFromExtension(ext.toLowerCase());
        return t != null ? t : "application/octet-stream";
    }

    private static WebResourceResponse answer(File f, String type) {
        try {
            Map<String, String> h = new HashMap<>();
            h.put("Content-Length", String.valueOf(f.length()));
            h.put("Cache-Control", "no-store");
            boolean text = type.startsWith("text/") || type.contains("json") || type.contains("javascript");
            return new WebResourceResponse(type, text ? "utf-8" : null, 200, "OK", h, new FileInputStream(f));
        } catch (IOException e) {
            return null;
        }
    }

    // ---- kept up to date while there's a network ----

    /** Brings the copy up to date with the server's web/. Returns the number of files fetched. */
    static int refresh(Context c) throws IOException {
        synchronized (LOCK) {
            byte[] b = get(Server.url(c, "/api/app-files"));
            JSONObject d;
            try { d = new JSONObject(new String(b, StandardCharsets.UTF_8)); } catch (JSONException e) { throw new Bad("not JSON"); }
            String version = d.optString("version");
            if (version.equals(prefs(c).getString("version", "")) && ready(c)) return 0;
            JSONArray files = d.optJSONArray("files");
            if (files == null) throw new Bad("no files");
            JSONObject had;
            try { had = new JSONObject(prefs(c).getString("hashes", "{}")); } catch (JSONException e) { had = new JSONObject(); }
            JSONObject now = new JSONObject();
            Set<String> keep = new HashSet<>();
            int got = 0;
            try {
                for (int i = 0; i < files.length(); i++) {
                    JSONObject f = files.getJSONObject(i);
                    String path = f.getString("path"), sha = f.getString("sha1");
                    File to = local(c, path);
                    keep.add(to.getCanonicalPath());
                    if (!sha.equals(had.optString(path)) || !to.isFile()) {
                        byte[] body = get(Server.url(c, path));
                        if (!sha.equals(sha1(body))) throw new Bad(path + " changed while it was fetched");
                        write(to, body);
                        got++;
                    }
                    now.put(path, sha);
                }
            } catch (JSONException e) {
                throw new Bad(e.getMessage());
            }
            prune(root(c), keep);                 // Google's fonts (.fonts) too, from before Daf had its own
            prefs(c).edit().putString("hashes", now.toString()).putString("version", version).putLong("at", System.currentTimeMillis()).apply();
            return got;
        }
    }

    private static void prune(File dir, Set<String> keep) throws IOException {
        File[] list = dir.listFiles();
        if (list == null) return;
        for (File f : list) {
            if (f.isDirectory()) prune(f, keep);
            else if (!keep.contains(f.getCanonicalPath())) //noinspection ResultOfMethodCallIgnored
                f.delete();
        }
    }

    private static byte[] get(String url) throws IOException {
        HttpURLConnection h = (HttpURLConnection) new URL(url).openConnection();
        h.setConnectTimeout(10000);
        h.setReadTimeout(30000);
        h.setUseCaches(false);
        try {
            int code = h.getResponseCode();
            if (code >= 400 && code < 500) throw new Bad(url + " answered " + code);   // Daf answered: not out of reach
            if (code != 200) throw new IOException(url + " answered " + code);
            try (InputStream in = h.getInputStream()) { return readAll(in); }
        } finally {
            h.disconnect();
        }
    }

    private static byte[] readAll(InputStream in) throws IOException {
        ByteArrayOutputStream out = new ByteArrayOutputStream();
        byte[] chunk = new byte[65536];
        for (int n; (n = in.read(chunk)) > 0; ) out.write(chunk, 0, n);
        return out.toByteArray();
    }

    private static void write(File f, byte[] b) throws IOException {
        File dir = f.getParentFile();
        if (dir != null && !dir.isDirectory() && !dir.mkdirs()) throw new Bad("no room for " + f);
        File part = new File(f.getPath() + ".part");
        try (OutputStream out = new FileOutputStream(part)) { out.write(b); }
        if (!part.renameTo(f)) throw new Bad("couldn't keep " + f.getName());
    }

    /** Something wrong with what came, or with keeping it here; Daf itself answered. */
    static final class Bad extends IOException {
        Bad(String what) { super(what); }
    }

    private static String sha1(byte[] b) {
        try {
            StringBuilder s = new StringBuilder();
            for (byte x : MessageDigest.getInstance("SHA-1").digest(b)) s.append(String.format("%02x", x));
            return s.toString();
        } catch (Exception e) {
            return "";
        }
    }
}
