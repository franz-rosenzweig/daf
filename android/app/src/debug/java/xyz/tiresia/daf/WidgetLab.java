package xyz.tiresia.daf;

import android.app.Activity;
import android.appwidget.AppWidgetHost;
import android.appwidget.AppWidgetHostView;
import android.appwidget.AppWidgetManager;
import android.appwidget.AppWidgetProviderInfo;
import android.content.ComponentName;
import android.content.Intent;
import android.graphics.Color;
import android.os.Bundle;
import android.util.SizeF;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

import java.util.ArrayList;
import java.util.Collections;

/**
 * The test build only: the widgets on a page of their own, each at the sizes asked for, so they
 * can be looked at and photographed without putting anything on the home screen.
 *
 *   adb shell appwidget grantbind --package xyz.tiresia.daf.debug
 *   adb shell am start -n xyz.tiresia.daf.debug/xyz.tiresia.daf.WidgetLab \
 *       --es w KeepReadingReceiver --es sizes 110x110,300x130,300x300 [--ez dark true] [--es feed folder:Craft]
 *
 * Several kinds at once, each at the sizes asked for: --es w KeepReadingReceiver,FeedReceiver,FeedReceiver,
 * and with --es feeds "folder:Craft,," each Feed widget in turn gets its own part of the Feed
 * ("" is everything), the way two Feed widgets on a home screen are set to different things.
 *
 * Each widget is bound to a host of this page's own, and let go again when the page closes.
 */
public class WidgetLab extends Activity {
    private static final int HOST = 4711;
    private AppWidgetHost host;
    private final ArrayList<Integer> ids = new ArrayList<>();

    @Override
    protected void onCreate(Bundle saved) {
        super.onCreate(saved);
        host = new AppWidgetHost(this, HOST);
        host.deleteHost();                                   // what an earlier page left bound
        host.startListening();
        Intent in = getIntent();
        // a build of the release kind (shrunk as the release is) has no debug extras in MainActivity: Daf's address here
        if (in.getStringExtra("base") != null) Server.setBase(this, in.getStringExtra("base"));
        if (in.getStringExtra("token") != null) Server.setToken(this, in.getStringExtra("token"));
        String which = in.getStringExtra("w") == null ? "KeepReadingReceiver" : in.getStringExtra("w");
        String sizes = in.getStringExtra("sizes") == null ? "110x110,300x130,300x300" : in.getStringExtra("sizes");
        boolean dark = in.getBooleanExtra("dark", false);
        float dp = getResources().getDisplayMetrics().density;
        LinearLayout col = new LinearLayout(this);
        col.setOrientation(LinearLayout.VERTICAL);
        int pad = (int) (16 * dp);
        col.setPadding(pad, pad * 3, pad, pad);
        col.setBackgroundColor(dark ? Color.rgb(30, 30, 34) : Color.rgb(232, 230, 226));
        ScrollView scroll = new ScrollView(this);
        scroll.addView(col);
        setContentView(scroll);
        AppWidgetManager m = AppWidgetManager.getInstance(this);
        String[] feeds = in.getStringExtra("feeds") == null ? null : in.getStringExtra("feeds").split(",", -1);
        int feedNo = 0;
        java.util.LinkedHashMap<String, ArrayList<Integer>> byKind = new java.util.LinkedHashMap<>();
        for (String kind : which.split(",")) {
        ComponentName cn = new ComponentName(this, "xyz.tiresia.daf." + kind.trim());
        for (String s : sizes.split(",")) {
            String[] wh = s.trim().split("x");
            int w = Integer.parseInt(wh[0]), h = Integer.parseInt(wh[1]);
            int id = host.allocateAppWidgetId();
            ids.add(id);
            Bundle o = new Bundle();
            o.putInt(AppWidgetManager.OPTION_APPWIDGET_MIN_WIDTH, w);
            o.putInt(AppWidgetManager.OPTION_APPWIDGET_MAX_WIDTH, w);
            o.putInt(AppWidgetManager.OPTION_APPWIDGET_MIN_HEIGHT, h);
            o.putInt(AppWidgetManager.OPTION_APPWIDGET_MAX_HEIGHT, h);
            o.putParcelableArrayList(AppWidgetManager.OPTION_APPWIDGET_SIZES, new ArrayList<>(Collections.singletonList(new SizeF(w, h))));
            TextView label = new TextView(this);
            label.setText(kind.trim().replace("Receiver", "") + " " + w + "×" + h);
            label.setTextColor(dark ? Color.LTGRAY : Color.DKGRAY);
            col.addView(label);
            if (!m.bindAppWidgetIdIfAllowed(id, cn, o)) {
                label.setText(label.getText() + ": not allowed to bind (adb shell appwidget grantbind --package " + getPackageName() + ")");
                continue;
            }
            if (in.getStringExtra("feed") != null) Board.INSTANCE.setFeedSource(this, id, in.getStringExtra("feed"));
            if (feeds != null && kind.trim().equals("FeedReceiver") && feedNo < feeds.length) {
                Board.INSTANCE.setFeedSource(this, id, feeds[feedNo].trim());
                label.setText(label.getText() + " · " + (feeds[feedNo].trim().isEmpty() ? "Everything" : feeds[feedNo].trim()));
                feedNo++;
            }
            if (!byKind.containsKey(cn.getClassName())) byKind.put(cn.getClassName(), new ArrayList<>());
            byKind.get(cn.getClassName()).add(id);
            AppWidgetProviderInfo info = m.getAppWidgetInfo(id);
            AppWidgetHostView v = host.createView(this, id, info);
            v.updateAppWidgetSize(o, Collections.singletonList(new SizeF(w, h)));
            LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams((int) (w * dp), (int) (h * dp));
            lp.setMargins(0, (int) (4 * dp), 0, (int) (20 * dp));
            col.addView(v, lp);
        }
        }
        for (java.util.Map.Entry<String, ArrayList<Integer>> e : byKind.entrySet()) {
            int[] all = new int[e.getValue().size()];
            for (int i = 0; i < all.length; i++) all[i] = e.getValue().get(i);
            sendBroadcast(new Intent(AppWidgetManager.ACTION_APPWIDGET_UPDATE).setComponent(new ComponentName(this, e.getKey()))
                    .putExtra(AppWidgetManager.EXTRA_APPWIDGET_IDS, all));
        }
    }

    @Override
    protected void onDestroy() {
        for (int id : ids) host.deleteAppWidgetId(id);
        host.stopListening();
        super.onDestroy();
    }
}
