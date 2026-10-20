package xyz.tiresia.daf;

import android.app.PendingIntent;
import android.appwidget.AppWidgetManager;
import android.appwidget.AppWidgetProvider;
import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.ShortcutInfo;
import android.content.pm.ShortcutManager;
import android.graphics.drawable.Icon;
import android.util.ArrayMap;
import android.util.SizeF;
import android.widget.RemoteViews;

import org.json.JSONArray;
import org.json.JSONObject;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;

/**
 * The hour on the home screen, where the feed apps are: a ring of the main goal
 * (Preferences → Goals; today's minutes unless he picks another) with its count in
 * it, the day of Year 30 or the goal's own name under it, and on the 4×2 the day's
 * highlight and its book (or "That's the hour." once it's done). Tap the ring for
 * Today, the highlight for Review.
 *
 * It asks /api/phone/widget with the phone's token: every half hour (Android's own
 * update), on unlock at most every 10 minutes (Daf.java), and when the app goes to
 * the background. If Daf can't be reached it keeps the last numbers, dimmed.
 */
public class Widget extends AppWidgetProvider {
    private static final String KEPT = "widget.json", AT = "widget.at", FAILED = "widget.failed";
    private static volatile boolean asking;

    @Override
    public void onUpdate(Context context, AppWidgetManager widgets, int[] ids) {
        render(context);
        PendingResult done = goAsync();
        Context app = context.getApplicationContext();
        new Thread(() -> {
            try { fetch(app); } finally { done.finish(); }
        }).start();
    }

    @Override
    public void onAppWidgetOptionsChanged(Context context, AppWidgetManager widgets, int id, android.os.Bundle options) {
        render(context);
    }

    /** Asks again if the last answer is older than this, in the background. */
    static void refreshIfOlder(Context context, long ms) {
        Context app = context.getApplicationContext();
        if (System.currentTimeMillis() - Server.prefs(app).getLong(AT, 0) < ms || asking) return;
        new Thread(() -> fetch(app)).start();
    }

    /** /api/phone/widget, kept, then every placed widget and the shortcuts drawn again. */
    static void fetch(Context c) {
        if (asking) return;
        asking = true;
        SharedPreferences p = Server.prefs(c);
        try {
            JSONObject w = Server.widget(c);
            p.edit().putString(KEPT, w.toString()).putLong(AT, System.currentTimeMillis()).putBoolean(FAILED, false).apply();
            shortcuts(c, w);
        } catch (Exception e) {
            p.edit().putBoolean(FAILED, true).apply();
        } finally {
            asking = false;
            render(c);
        }
    }

    static JSONObject kept(Context c) {
        String s = Server.prefs(c).getString(KEPT, null);
        try { return s == null ? null : new JSONObject(s); } catch (Exception e) { return null; }
    }

    /** Every placed copy, in both sizes: the launcher shows whichever fits. */
    static void render(Context c) {
        AppWidgetManager widgets = AppWidgetManager.getInstance(c);
        int[] ids = widgets.getAppWidgetIds(new ComponentName(c, Widget.class));
        if (ids.length == 0) return;
        JSONObject w = kept(c);
        boolean dim = w == null || Server.prefs(c).getBoolean(FAILED, false);
        Map<SizeF, RemoteViews> sizes = new ArrayMap<>();
        sizes.put(new SizeF(100f, 100f), views(c, R.layout.widget_small, w, dim));
        sizes.put(new SizeF(240f, 100f), views(c, R.layout.widget_wide, w, dim));
        for (int id : ids) widgets.updateAppWidget(id, new RemoteViews(sizes));
    }

    private static RemoteViews views(Context c, int layout, JSONObject w, boolean dim) {
        RemoteViews v = new RemoteViews(c.getPackageName(), layout);
        int minutes = w == null ? 0 : (int) Math.round(w.optDouble("minutes", 0));
        int goal = w == null ? 60 : Math.max(1, (int) Math.round(w.optDouble("goal", 60)));
        // the main goal from Preferences → Goals; an older Daf has only the day's minutes
        JSONObject m = w == null ? null : w.optJSONObject("main");
        boolean daily = m == null || ("minutes".equals(m.optString("kind")) && "day".equals(m.optString("period")));
        int shown = m != null ? (int) Math.round(m.optDouble("done", 0)) : minutes;
        int pct = m != null ? Math.max(0, Math.min(100, m.optInt("pct", 0))) : Math.min(100, 100 * minutes / goal);
        boolean done = m != null ? m.optBoolean("met", false) : minutes >= goal;
        v.setProgressBar(R.id.ring, 100, pct, false);
        v.setTextViewText(R.id.minutes, w == null ? "–" : String.valueOf(shown));
        int day = w == null ? 0 : w.optInt("year_day", 0);
        v.setTextViewText(R.id.day, w == null ? "Connect in Daf" : !daily ? m.optString("label")
                : day > 0 ? "Year 30 · day " + day : "Today");
        if (layout == R.layout.widget_wide) {
            JSONObject h = w == null ? null : w.optJSONObject("highlight");
            String said = m != null ? m.optString("text") : minutes + " of " + goal + " minutes today";
            if (done) {
                v.setTextViewText(R.id.quote, metLine(m));
                v.setTextViewText(R.id.book, said);
            } else if (h != null && !h.optString("text").isEmpty()) {
                v.setTextViewText(R.id.quote, h.optString("text"));
                v.setTextViewText(R.id.book, h.optString("title"));
            } else {
                v.setTextViewText(R.id.quote, w == null ? "Open Daf and connect this phone in its settings." : said + ".");
                v.setTextViewText(R.id.book, "");
            }
            v.setOnClickPendingIntent(R.id.quoteBox, pending(c, 2, "#review"));
            if (dim) v.setColorStateList(R.id.quote, "setTextColor", R.color.widgetText2);
        }
        if (dim) {
            v.setColorStateList(R.id.minutes, "setTextColor", R.color.widgetText2);
            v.setColorStateList(R.id.ring, "setProgressTintList", R.color.widgetText2);
        }
        v.setOnClickPendingIntent(R.id.today, pending(c, 1, "#today"));
        return v;
    }

    /** "That's the hour." only while the goal is the hour; otherwise the main goal's period. */
    static String metLine(JSONObject m) {
        if (m == null || ("minutes".equals(m.optString("kind")) && "day".equals(m.optString("period")) && m.optDouble("target") == 60)) {
            return "That's the hour.";
        }
        switch (m.optString("period_label")) {
            case "today": return "That's today's goal.";
            case "this week": return "That's this week's goal.";
            case "this month": return "That's this month's goal.";
            case "this year": return "That's this year's goal.";
            default: return "That's the goal.";
        }
    }

    private static PendingIntent pending(Context c, int code, String route) {
        return PendingIntent.getActivity(c, code, MainActivity.open(c, route, null),
                PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
    }

    /** Long-press Daf's icon: Review, Continue reading (the first book on the nightstand), Log paper, Settings. */
    static void shortcuts(Context c, JSONObject w) {
        ShortcutManager sm = c.getSystemService(ShortcutManager.class);
        if (sm == null) return;
        List<ShortcutInfo> list = new ArrayList<>();
        list.add(shortcut(c, "review", c.getString(R.string.shortcutReview), null, R.drawable.ic_shortcut_review, "#review", null));
        JSONArray stand = w == null ? null : w.optJSONArray("nightstand");
        JSONObject first = stand == null ? null : stand.optJSONObject(0);
        if (first != null && first.optString("id").startsWith("cal:")) {
            list.add(shortcut(c, "continue", c.getString(R.string.shortcutContinue), first.optString("title"),
                    R.drawable.ic_shortcut_book, "#ebook/" + android.net.Uri.encode(first.optString("id")), null));
        }
        list.add(shortcut(c, "paper", c.getString(R.string.shortcutPaper), c.getString(R.string.shortcutPaperLong),
                R.drawable.ic_shortcut_paper, "#today", "paper"));
        list.add(new ShortcutInfo.Builder(c, "settings").setShortLabel("Settings").setLongLabel("Daf settings")
                .setIcon(Icon.createWithResource(c, R.drawable.ic_shortcut_settings))
                .setIntent(new Intent(Intent.ACTION_VIEW).setClass(c, SettingsActivity.class)).build());
        try {
            sm.setDynamicShortcuts(list);
        } catch (IllegalStateException | IllegalArgumentException ignored) {
            // the launcher's limit on shortcuts; nothing lost but them
        }
    }

    private static ShortcutInfo shortcut(Context c, String id, String label, String longLabel, int icon, String route, String command) {
        ShortcutInfo.Builder b = new ShortcutInfo.Builder(c, id)
                .setShortLabel(label)
                .setIcon(Icon.createWithResource(c, icon))
                .setIntent(MainActivity.open(c, route, command).setFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_CLEAR_TOP));
        if (longLabel != null && !longLabel.isEmpty()) b.setLongLabel(longLabel.length() > 25 ? longLabel.substring(0, 24) + "…" : longLabel);
        return b.build();
    }
}
