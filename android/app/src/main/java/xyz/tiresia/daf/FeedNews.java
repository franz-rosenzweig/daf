package xyz.tiresia.daf;

import android.Manifest;
import android.app.Notification;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.job.JobInfo;
import android.app.job.JobParameters;
import android.app.job.JobScheduler;
import android.app.job.JobService;
import android.content.ComponentName;
import android.content.Context;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;

import org.json.JSONArray;
import org.json.JSONObject;

/**
 * New posts from the feeds set to notify (the Feed's sources sheet → a feed → "Notify me of new
 * posts"). Every 15 minutes, Android's shortest for a job, the phone asks /api/phone/feed-news with
 * its token and posts one notification a post; tapping one opens it in Daf. The cursor is Daf's own
 * order of arrival, so nothing rings twice and the backlog never does. With no feed set to notify
 * any more, the job stops until the page asks again (dafShell.alerts).
 */
public class FeedNews extends JobService {
    static final String CHANNEL = "feed";
    private static final int JOB = 33;

    static SharedPreferences prefs(Context c) {
        return c.getSharedPreferences("feednews", Context.MODE_PRIVATE);
    }

    static boolean allowed(Context c) {
        return c.checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) == PackageManager.PERMISSION_GRANTED;
    }

    /** On: the job, and the cursor from now, so only what comes after rings. */
    static void start(Context c) {
        prefs(c).edit().putBoolean("on", true).apply();
        JobScheduler js = c.getSystemService(JobScheduler.class);
        if (js == null || js.getPendingJob(JOB) != null) return;
        try {
            js.schedule(new JobInfo.Builder(JOB, new ComponentName(c, FeedNews.class))
                    .setPeriodic(15 * 60 * 1000L)
                    .setRequiredNetworkType(JobInfo.NETWORK_TYPE_ANY)
                    .setPersisted(true)
                    .build());
        } catch (RuntimeException ignored) { }
        new Thread(() -> { try { check(c); } catch (Exception ignored) { } }).start();
    }

    static void stop(Context c) {
        prefs(c).edit().putBoolean("on", false).remove("cursor").apply();
        JobScheduler js = c.getSystemService(JobScheduler.class);
        if (js != null) js.cancel(JOB);
    }

    /** One look: new posts become notifications. */
    static void check(Context c) throws Exception {
        if (Server.token(c) == null) return;
        long cursor = prefs(c).getLong("cursor", -1);
        JSONObject r = Server.feedNews(c, cursor);
        if (r.optInt("feeds") == 0) { stop(c); return; }
        JSONArray items = r.optJSONArray("items");
        NotificationManager nm = c.getSystemService(NotificationManager.class);
        if (cursor >= 0 && items != null && nm != null && allowed(c)) {
            for (int i = 0; i < items.length(); i++) {
                JSONObject x = items.getJSONObject(i);
                String id = x.optString("id");
                PendingIntent open = PendingIntent.getActivity(c, id.hashCode(), MainActivity.open(c, x.optString("route"), null),
                        PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
                nm.notify(CHANNEL, id.hashCode(), new Notification.Builder(c, CHANNEL)
                        .setSmallIcon(R.drawable.ic_notify)
                        .setColor(c.getColor(R.color.dafBlue))
                        .setContentTitle(x.optString("title"))
                        .setContentText(x.optString("source"))
                        .setContentIntent(open)
                        .setAutoCancel(true)
                        .setGroup(CHANNEL)
                        .build());
            }
            if (items.length() > 1) {
                nm.notify(CHANNEL, 0, new Notification.Builder(c, CHANNEL)
                        .setSmallIcon(R.drawable.ic_notify)
                        .setColor(c.getColor(R.color.dafBlue))
                        .setGroup(CHANNEL).setGroupSummary(true).setAutoCancel(true)
                        .build());
            }
        }
        prefs(c).edit().putLong("cursor", r.optLong("cursor", cursor)).apply();
    }

    @Override
    public boolean onStartJob(JobParameters params) {
        new Thread(() -> {
            boolean again = false;
            try { check(getApplicationContext()); } catch (Exception e) { again = true; }
            jobFinished(params, again);
        }).start();
        return true;
    }

    @Override
    public boolean onStopJob(JobParameters params) {
        return true;
    }
}
