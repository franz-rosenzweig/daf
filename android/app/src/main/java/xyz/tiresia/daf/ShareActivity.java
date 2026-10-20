package xyz.tiresia.daf;

import android.app.Activity;
import android.content.Context;
import android.content.Intent;
import android.net.Uri;
import android.os.Bundle;
import android.widget.TextView;

import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.util.ArrayList;
import java.util.List;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * Save to Daf, from any app's share sheet, with a card at the bottom saying what
 * happened. A link (or text with a link in it) goes to the Library, through
 * /api/save with this phone's token, or through the page's own share target with
 * the window's sign-in if the phone isn't connected yet. A photo of a marked page
 * goes to /share and becomes a paper page; Daf then opens on it while the lines
 * are read.
 */
public class ShareActivity extends Activity {
    private static final Pattern LINK = Pattern.compile("https?://\\S+");
    private TextView title, detail;
    private boolean leaving;

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        setContentView(R.layout.share);
        title = findViewById(R.id.shareTitle);
        detail = findViewById(R.id.shareDetail);
        findViewById(R.id.shareRoot).setOnClickListener(v -> leave(0));

        Intent in = getIntent();
        Context app = getApplicationContext();
        List<Uri> photos = photos(in);
        String text = in.getStringExtra(Intent.EXTRA_TEXT), subject = in.getStringExtra(Intent.EXTRA_SUBJECT);
        String link = link(text);
        detail.setText(!photos.isEmpty() ? (photos.size() == 1 ? "A photo of a page" : photos.size() + " photos of pages")
                : subject != null && !subject.isEmpty() ? subject : link != null ? Uri.parse(link).getHost() : "");
        new Thread(() -> {
            try {
                if (!photos.isEmpty()) {
                    // read while this screen still holds the sharing app's permission to them
                    List<byte[]> bytes = new ArrayList<>();
                    List<String> types = new ArrayList<>();
                    for (Uri p : photos) { bytes.add(read(app, p)); types.add(app.getContentResolver().getType(p)); }
                    String where = null;
                    for (int i = 0; i < bytes.size(); i++) where = Server.sharePhoto(app, bytes.get(i), types.get(i), subject);
                    String route = where;
                    say("Sent to Daf", photos.size() == 1 ? "Daf is reading the page" : "Daf is reading " + photos.size() + " pages");
                    runOnUiThread(() -> title.postDelayed(() -> {
                        startActivity(MainActivity.open(app, route, null));
                        leave(0);
                    }, 900));
                } else {
                    if (link == null) throw new Exception("There's no link in what was shared.");
                    String rest = text.replace(link, "").trim();
                    if (Server.token(app) == null) Server.shareLink(app, link, subject, rest);
                    else try {
                        Server.save(app, link, subject, rest);
                    } catch (Server.Failure f) {
                        if (f.status != 401) throw f;
                        Server.shareLink(app, link, subject, rest);           // the token was refused: the sign-in still saves it
                    }
                    say("Saved to Daf", "In your Library on the next sync");
                    leave(1400);
                }
            } catch (Exception e) {
                say("Not saved", e.getMessage());
                leave(4000);
            }
        }).start();
    }

    private void say(String t, String d) {
        runOnUiThread(() -> { title.setText(t); detail.setText(d == null ? "" : d); });
    }

    private void leave(long after) {
        runOnUiThread(() -> title.postDelayed(() -> {
            if (leaving) return;
            leaving = true;
            finish();
        }, after));
    }

    static String link(String text) {
        if (text == null) return null;
        Matcher m = LINK.matcher(text);
        return m.find() ? m.group() : null;
    }

    @SuppressWarnings("deprecation")
    private static List<Uri> photos(Intent in) {
        List<Uri> out = new ArrayList<>();
        String type = in.getType() == null ? "" : in.getType();
        if (!type.startsWith("image/")) return out;
        if (Intent.ACTION_SEND_MULTIPLE.equals(in.getAction())) {
            ArrayList<Uri> many = in.getParcelableArrayListExtra(Intent.EXTRA_STREAM);
            if (many != null) out.addAll(many);
        } else {
            Uri one = in.getParcelableExtra(Intent.EXTRA_STREAM);
            if (one != null) out.add(one);
        }
        return out;
    }

    private static byte[] read(Context c, Uri u) throws Exception {
        try (InputStream in = c.getContentResolver().openInputStream(u)) {
            if (in == null) throw new Exception("the photo couldn't be read");
            ByteArrayOutputStream out = new ByteArrayOutputStream();
            byte[] chunk = new byte[65536];
            for (int n; (n = in.read(chunk)) > 0; ) out.write(chunk, 0, n);
            return out.toByteArray();
        }
    }
}
