package xyz.tiresia.daf;

import android.Manifest;
import android.app.Activity;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.graphics.Insets;
import android.net.Uri;
import android.os.Bundle;
import android.provider.Settings;
import android.view.View;
import android.view.WindowInsets;
import android.widget.Button;
import android.widget.EditText;
import android.widget.Switch;
import android.widget.TextView;
import android.widget.Toast;

import org.json.JSONObject;

/**
 * The app's own settings (the page has its own Preferences): Daf's address, this
 * phone's token, and the evening nudge with what it needs from Android. Reached
 * from the long-press menu on Daf's icon.
 */
public class SettingsActivity extends Activity {
    private TextView status, access, offline;
    private Switch nudge;

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        setContentView(R.layout.settings);
        View root = findViewById(R.id.scroll);
        root.setOnApplyWindowInsetsListener((v, in) -> {
            Insets bars = in.getInsets(WindowInsets.Type.systemBars() | WindowInsets.Type.ime());
            v.setPadding(bars.left, bars.top, bars.right, bars.bottom);
            return WindowInsets.CONSUMED;
        });

        EditText base = findViewById(R.id.base);
        base.setText(Server.base(this));
        findViewById(R.id.useBase).setOnClickListener(v -> {
            TextView note = findViewById(R.id.baseNote);
            if (Server.setBase(this, base.getText().toString())) {
                base.setText(Server.base(this));
                note.setText("Daf opens from " + Server.base(this) + ". Sign in there once.");
            } else {
                note.setText("That isn't an address Daf can use. It starts with https:// or http://.");
            }
        });

        status = findViewById(R.id.status);
        access = findViewById(R.id.access);
        Button connect = findViewById(R.id.connect);
        connect.setOnClickListener(v -> {
            connect.setEnabled(false);
            new Thread(() -> {
                String said;
                try {
                    Server.setToken(this, Server.connect(this));
                    Widget.fetch(this);
                    said = "This phone is connected";
                } catch (Exception e) {
                    said = e.getMessage();
                }
                String s = said;
                runOnUiThread(() -> { connect.setEnabled(true); Toast.makeText(this, s, Toast.LENGTH_LONG).show(); show(); });
            }).start();
        });
        findViewById(R.id.forget).setOnClickListener(v -> { Server.setToken(this, null); show(); });

        findViewById(R.id.goals).setOnClickListener(v -> { startActivity(MainActivity.open(this, "#prefs/goals", null)); finish(); });

        Switch offReading = findViewById(R.id.offReading), offWifi = findViewById(R.id.offWifi);
        offReading.setChecked(Offline.reading(this));
        offWifi.setChecked(Offline.wifiOnly(this));
        offReading.setOnCheckedChangeListener((b, on) -> Offline.setReading(this, on));
        offWifi.setOnCheckedChangeListener((b, on) -> Offline.setWifiOnly(this, on));
        Button offSync = findViewById(R.id.offSync);
        offSync.setOnClickListener(v -> {
            offSync.setEnabled(false);
            offline.setText("Updating…");
            new Thread(() -> {
                String said;
                try { said = Offline.sync(this); } catch (Exception e) { said = "Daf didn't answer: " + e.getMessage(); }
                String s = said;
                runOnUiThread(() -> { offSync.setEnabled(true); Toast.makeText(this, s, Toast.LENGTH_SHORT).show(); show(); });
            }).start();
        });
        findViewById(R.id.offClear).setOnClickListener(v -> new android.app.AlertDialog.Builder(this)
                .setMessage("Remove the books from this phone? Daf keeps them, and the ones you're reading come back on the next update unless you turn that off.")
                .setPositiveButton("Remove", (d, w) -> {
                    JSONObject all = Offline.list(this);
                    org.json.JSONArray books = all.optJSONArray("books"), manga = all.optJSONArray("manga");
                    for (int i = 0; books != null && i < books.length(); i++) Offline.remove(this, books.optJSONObject(i).optString("id"));
                    for (int i = 0; manga != null && i < manga.length(); i++) Offline.removeManga(this, manga.optJSONObject(i).optString("id"));
                    show();
                })
                .setNegativeButton("Cancel", null)
                .show());
        offline = findViewById(R.id.offStatus);

        nudge = findViewById(R.id.nudge);
        nudge.setChecked(NudgeJob.on(this));
        nudge.setOnCheckedChangeListener((b, on) -> {
            if (!NudgeJob.set(this, on) && on) {
                b.setChecked(false);
                Toast.makeText(this, "Android didn't take the nudge's check. Try again in a moment.", Toast.LENGTH_LONG).show();
                return;
            }
            if (on && checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
                requestPermissions(new String[]{Manifest.permission.POST_NOTIFICATIONS}, 1);
            }
            show();
        });
        findViewById(R.id.grant).setOnClickListener(v -> {
            Intent i = new Intent(Settings.ACTION_USAGE_ACCESS_SETTINGS).setData(Uri.parse("package:" + getPackageName()));
            try { startActivity(i); } catch (RuntimeException e) { startActivity(new Intent(Settings.ACTION_USAGE_ACCESS_SETTINGS)); }
        });
        findViewById(R.id.tryNudge).setOnClickListener(v -> new Thread(() -> {
            String said;
            try {
                android.app.NotificationManager nm = getSystemService(android.app.NotificationManager.class);
                if (nm == null || !nm.areNotificationsEnabled()) {
                    said = "Notifications are off for Daf. Turn them on, then try again.";
                } else {
                    JSONObject n = NudgeJob.ask(this, "test", true);
                    said = n.optBoolean("show") ? "Sent. Look in the notifications." : "Daf said no: " + n.optString("reason");
                }
            } catch (Exception e) {
                said = e.getMessage();
            }
            String s = said;
            runOnUiThread(() -> Toast.makeText(this, s, Toast.LENGTH_LONG).show());
        }).start());
    }

    @Override
    protected void onResume() {
        super.onResume();
        show();
    }

    private void show() {
        JSONObject w = Widget.kept(this);
        if (Server.token(this) == null) status.setText("Not connected yet. Sign in to Daf in the app, then press Connect.");
        else if (w != null) status.setText("Connected: " + (w.optJSONObject("main") != null ? w.optJSONObject("main").optString("text")
                : Math.round(w.optDouble("minutes")) + " of " + Math.round(w.optDouble("goal", 60)) + " minutes today") + ".");
        else status.setText("Connected.");
        findViewById(R.id.forget).setVisibility(Server.token(this) == null ? View.GONE : View.VISIBLE);

        JSONObject off = Offline.list(this);
        org.json.JSONArray books = off.optJSONArray("books");
        StringBuilder t = new StringBuilder(Offline.summary(this));
        for (int i = 0; books != null && i < books.length() && i < 8; i++) {
            JSONObject b = books.optJSONObject(i);
            t.append("\n· ").append(b.optString("title")).append(b.optBoolean("kept") ? " (kept)" : "");
        }
        org.json.JSONArray manga = off.optJSONArray("manga");
        for (int i = 0; manga != null && i < manga.length() && i < 12; i++) {
            JSONObject b = manga.optJSONObject(i);
            t.append("\n· ").append(b.optString("title")).append("done".equals(b.optString("state")) ? "" : " (" + b.optInt("done") + " of " + b.optInt("total") + " pages)");
        }
        long synced = off.optLong("synced");
        if (synced > 0) t.append("\nUpdated ").append(android.text.format.DateUtils.getRelativeTimeSpanString(synced)).append(".");
        offline.setText(t);

        boolean usage = NudgeJob.usageAccess(this);
        boolean notes = checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) == PackageManager.PERMISSION_GRANTED;
        access.setText(!nudge.isChecked() ? "Off." : !usage ? "Daf needs Usage Access to see which app is in front."
                : !notes ? "Daf needs permission to post notifications." : "On. Daf can see which app is in front.");
        findViewById(R.id.grant).setVisibility(nudge.isChecked() && !usage ? View.VISIBLE : View.GONE);
        findViewById(R.id.tryNudge).setVisibility(Server.token(this) != null ? View.VISIBLE : View.GONE);
    }
}
