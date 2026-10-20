package xyz.tiresia.daf;

import android.app.Application;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.content.pm.PackageManager;
import android.os.Build;

/**
 * The process: the nudge's notification channel, and the widget asking again when
 * the phone is unlocked (at most every 10 minutes). Android delivers "unlocked" only
 * to a running process, so this is on while Daf's process is alive, which the
 * widget's own half-hourly refresh keeps it being for a good part of the day.
 */
public class Daf extends Application {
    static final String NUDGE_CHANNEL = "nudge";

    @Override
    public void onCreate() {
        super.onCreate();
        NotificationManager nm = getSystemService(NotificationManager.class);
        if (nm != null) {
            NotificationChannel ch = new NotificationChannel(NUDGE_CHANNEL, "Evening nudge", NotificationManager.IMPORTANCE_DEFAULT);
            ch.setDescription("One highlight and the minutes left, when a feed app opens in the evening");
            nm.createNotificationChannel(ch);
            NotificationChannel listen = new NotificationChannel(Listen.CHANNEL, "Listening", NotificationManager.IMPORTANCE_LOW);
            listen.setDescription("Daf reading aloud, with its controls on the lock screen");
            listen.setShowBadge(false);
            nm.createNotificationChannel(listen);
            NotificationChannel feed = new NotificationChannel(FeedNews.CHANNEL, "New posts", NotificationManager.IMPORTANCE_DEFAULT);
            feed.setDescription("New posts from the feeds you chose in Daf");
            nm.createNotificationChannel(feed);
        }
        BroadcastReceiver unlocked = new BroadcastReceiver() {
            @Override
            public void onReceive(Context c, Intent i) {
                Widget.refreshIfOlder(c, 10 * 60 * 1000L);
            }
        };
        IntentFilter filter = new IntentFilter(Intent.ACTION_USER_PRESENT);
        if (Build.VERSION.SDK_INT >= 33) registerReceiver(unlocked, filter, Context.RECEIVER_NOT_EXPORTED);
        else registerReceiver(unlocked, filter);
    }

    static String version(Context c) {
        try {
            return c.getPackageManager().getPackageInfo(c.getPackageName(), 0).versionName;
        } catch (PackageManager.NameNotFoundException e) {
            return "0";
        }
    }
}
