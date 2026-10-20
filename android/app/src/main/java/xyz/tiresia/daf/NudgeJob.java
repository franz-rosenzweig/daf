package xyz.tiresia.daf;

import android.app.AppOpsManager;
import android.app.Notification;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.job.JobInfo;
import android.app.job.JobParameters;
import android.app.job.JobScheduler;
import android.app.job.JobService;
import android.app.usage.UsageEvents;
import android.app.usage.UsageStatsManager;
import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;
import android.net.Uri;
import android.os.PowerManager;
import android.os.Process;

import org.json.JSONObject;

import java.util.Arrays;
import java.util.Calendar;
import java.util.List;

/**
 * The evening nudge, replacing the Tasker setup. Every 15 minutes while it's on
 * (Android's shortest interval for a job, and no notification of its own sitting in
 * the shade all evening), between 21:00 and 03:00: if Instagram, Reddit, X or
 * Discord is in front, ask /api/phone/nudge and, if Daf says so, post its
 * notification, which opens Daf. Daf keeps the rules (one every 25 minutes, none
 * once the hour is done) and counts what was shown and whether reading followed.
 *
 * Off until switched on in Daf's settings; needs Usage Access, granted by hand.
 */
public class NudgeJob extends JobService {
    private static final int JOB = 30, NOTE = 31;
    static final List<String> APPS = Arrays.asList(
            "com.instagram.android", "com.reddit.frontpage", "com.twitter.android", "com.discord");
    private static final String ON = "nudge.on";

    static boolean on(Context c) {
        return Server.prefs(c).getBoolean(ON, false);
    }

    /** Switches the nudge on or off. False, and off, if Android wouldn't take the job. */
    static boolean set(Context c, boolean on) {
        JobScheduler js = c.getSystemService(JobScheduler.class);
        boolean ok = js != null;
        if (js != null && !on) js.cancel(JOB);
        if (js != null && on) {
            try {
                ok = js.schedule(new JobInfo.Builder(JOB, new ComponentName(c, NudgeJob.class))
                        .setPeriodic(15 * 60 * 1000L)
                        .setRequiredNetworkType(JobInfo.NETWORK_TYPE_ANY)
                        .setPersisted(true)
                        .build()) == JobScheduler.RESULT_SUCCESS;
            } catch (RuntimeException e) {
                ok = false;
            }
        }
        Server.prefs(c).edit().putBoolean(ON, on && ok).apply();
        return ok;
    }

    /** Usage Access: Settings → Apps → Special access → Usage access → Daf. (Android 16 renames
     *  the call; the old one answers on every version from 12 on.) */
    @SuppressWarnings("deprecation")
    static boolean usageAccess(Context c) {
        AppOpsManager ops = c.getSystemService(AppOpsManager.class);
        return ops != null && ops.unsafeCheckOpNoThrow(AppOpsManager.OPSTR_GET_USAGE_STATS, Process.myUid(), c.getPackageName())
                == AppOpsManager.MODE_ALLOWED;
    }

    static boolean evening() {
        int h = Calendar.getInstance().get(Calendar.HOUR_OF_DAY);
        return h >= 21 || h < 3;
    }

    @Override
    public boolean onStartJob(JobParameters params) {
        if (!on(this) || !evening() || !usageAccess(this)) return false;
        Context app = getApplicationContext();
        new Thread(() -> {
            try {
                String front = front(app);
                if (front != null) ask(app, front, false);
            } catch (Exception ignored) {
                // offline or refused: the next check asks again
            } finally {
                jobFinished(params, false);
            }
        }).start();
        return true;
    }

    @Override
    public boolean onStopJob(JobParameters params) {
        return false;
    }

    /** The feed app in front now, if one is: the last one resumed, not paused since, screen on. */
    static String front(Context c) {
        PowerManager pm = c.getSystemService(PowerManager.class);
        UsageStatsManager usage = c.getSystemService(UsageStatsManager.class);
        if (usage == null || pm == null || !pm.isInteractive()) return null;
        long now = System.currentTimeMillis();
        UsageEvents events = usage.queryEvents(now - 60 * 60 * 1000L, now);
        UsageEvents.Event e = new UsageEvents.Event();
        String resumed = null;
        while (events.hasNextEvent()) {
            events.getNextEvent(e);
            if (e.getEventType() == UsageEvents.Event.ACTIVITY_RESUMED) resumed = e.getPackageName();
            else if (e.getEventType() == UsageEvents.Event.ACTIVITY_PAUSED && e.getPackageName().equals(resumed)) resumed = null;
        }
        return resumed != null && APPS.contains(resumed) ? resumed : null;
    }

    /** Asks Daf, and posts its nudge if it says so. Answers what Daf said. */
    static JSONObject ask(Context c, String app, boolean force) throws Exception {
        JSONObject n = Server.nudge(c, app, force);
        if (!n.optBoolean("show")) return n;
        NotificationManager nm = c.getSystemService(NotificationManager.class);
        if (nm == null || !nm.areNotificationsEnabled()) return n;
        Intent open = new Intent(c, MainActivity.class).setAction(Intent.ACTION_VIEW)
                .setData(Uri.parse(n.optString("url", Server.url(c, "#today"))))
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
        Notification note = new Notification.Builder(c, Daf.NUDGE_CHANNEL)
                .setSmallIcon(R.drawable.ic_notify)
                .setColor(c.getColor(R.color.dafBlue))
                .setContentTitle(n.optString("title"))
                .setContentText(n.optString("text"))
                .setStyle(new Notification.BigTextStyle().bigText(n.optString("text")))
                .setContentIntent(PendingIntent.getActivity(c, NOTE, open, PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE))
                .setAutoCancel(true)
                .build();
        nm.notify(NOTE, note);
        return n;
    }
}
