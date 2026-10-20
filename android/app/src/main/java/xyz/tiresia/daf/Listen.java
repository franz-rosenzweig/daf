package xyz.tiresia.daf;

import android.app.Notification;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Context;
import android.content.Intent;
import android.content.pm.ServiceInfo;
import android.graphics.drawable.Icon;
import android.media.MediaMetadata;
import android.media.session.MediaSession;
import android.media.session.PlaybackState;
import android.os.IBinder;
import android.os.PowerManager;

/**
 * Listening with the screen off. Daf's own read-aloud (Kokoro, a paragraph at a time)
 * keeps playing in the page; this keeps the app alive while it does (a media-playback
 * service), puts it on the lock screen and the headphones' buttons (a media session),
 * and holds the processor awake so the next paragraph is fetched and started. shell.js
 * tells it what the page's player is doing (op "media"); its buttons press the page's.
 */
public class Listen extends Service {
    static final String CHANNEL = "listen";
    private static final int NOTE = 41;
    /** The running service, so a change while the app is behind the lock screen goes straight
     *  to it: Android won't let a background app start a foreground service again. */
    private static Listen running;
    private MediaSession session;
    private PowerManager.WakeLock lock;
    private String state = "stopped", title = "", sub = "";

    /** The page's player changed: playing, paused or stopped. */
    static void update(Context c, String state, String title, String sub) {
        if ("stopped".equals(state)) {
            if (running != null) c.stopService(new Intent(c, Listen.class));
        } else if (running != null) {
            running.apply(state, title, sub);
        } else {
            c.startForegroundService(new Intent(c, Listen.class).putExtra("state", state).putExtra("title", title).putExtra("sub", sub));
        }
    }

    @Override
    public void onCreate() {
        super.onCreate();
        session = new MediaSession(this, "Daf");
        session.setCallback(new MediaSession.Callback() {
            @Override public void onPlay() { MainActivity.command("listen:play"); }
            @Override public void onPause() { MainActivity.command("listen:pause"); }
            @Override public void onSkipToNext() { MainActivity.command("listen:next"); }
            @Override public void onSkipToPrevious() { MainActivity.command("listen:prev"); }
            @Override public void onStop() { MainActivity.command("listen:stop"); }
        });
        session.setActive(true);
        running = this;
        PowerManager pm = getSystemService(PowerManager.class);
        lock = pm.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "Daf:listen");
        lock.setReferenceCounted(false);
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        String cmd = intent == null ? null : intent.getStringExtra("cmd");
        if (cmd != null) {
            // a button on the notification: the page does it, and tells us what changed
            if (!MainActivity.command(cmd)) stopSelf();
            return START_NOT_STICKY;
        }
        apply(intent == null ? null : intent.getStringExtra("state"), intent == null ? null : intent.getStringExtra("title"),
                intent == null ? null : intent.getStringExtra("sub"));
        return START_NOT_STICKY;
    }

    private void apply(String newState, String newTitle, String newSub) {
        if (newState != null) state = newState;
        if (newTitle != null) title = newTitle;
        if (newSub != null) sub = newSub;
        boolean playing = "playing".equals(state);
        session.setMetadata(new MediaMetadata.Builder()
                .putString(MediaMetadata.METADATA_KEY_TITLE, title)
                .putString(MediaMetadata.METADATA_KEY_ARTIST, sub)
                .build());
        session.setPlaybackState(new PlaybackState.Builder()
                .setActions(PlaybackState.ACTION_PLAY | PlaybackState.ACTION_PAUSE | PlaybackState.ACTION_PLAY_PAUSE
                        | PlaybackState.ACTION_SKIP_TO_NEXT | PlaybackState.ACTION_SKIP_TO_PREVIOUS | PlaybackState.ACTION_STOP)
                .setState(playing ? PlaybackState.STATE_PLAYING : PlaybackState.STATE_PAUSED, PlaybackState.PLAYBACK_POSITION_UNKNOWN, 1f)
                .build());
        startForeground(NOTE, note(playing), ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PLAYBACK);
        // awake while it plays, so the next paragraph comes; asleep again once it's paused
        if (playing) lock.acquire(2 * 60 * 60 * 1000L); else if (lock.isHeld()) lock.release();
    }

    private Notification note(boolean playing) {
        Notification.Action prev = action("listen:prev", 1, android.R.drawable.ic_media_previous, "Previous paragraph");
        Notification.Action play = playing ? action("listen:pause", 2, android.R.drawable.ic_media_pause, "Pause")
                : action("listen:play", 2, android.R.drawable.ic_media_play, "Play");
        Notification.Action next = action("listen:next", 3, android.R.drawable.ic_media_next, "Next paragraph");
        PendingIntent open = PendingIntent.getActivity(this, 4, new Intent(this, MainActivity.class).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK),
                PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
        PendingIntent stop = PendingIntent.getService(this, 5, new Intent(this, Listen.class).putExtra("cmd", "listen:stop"),
                PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
        return new Notification.Builder(this, CHANNEL)
                .setSmallIcon(R.drawable.ic_notify)
                .setColor(getColor(R.color.dafBlue))
                .setContentTitle(title)
                .setContentText(sub)
                .setContentIntent(open)
                .setDeleteIntent(stop)
                .setOngoing(playing)
                .setVisibility(Notification.VISIBILITY_PUBLIC)
                .addAction(prev).addAction(play).addAction(next)
                .setStyle(new Notification.MediaStyle().setMediaSession(session.getSessionToken()).setShowActionsInCompactView(0, 1, 2))
                .build();
    }

    private Notification.Action action(String cmd, int code, int icon, String label) {
        PendingIntent p = PendingIntent.getService(this, code, new Intent(this, Listen.class).putExtra("cmd", cmd),
                PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
        return new Notification.Action.Builder(Icon.createWithResource(this, icon), label, p).build();
    }

    @Override
    public void onDestroy() {
        if (running == this) running = null;
        if (lock != null && lock.isHeld()) lock.release();
        if (session != null) session.release();
        stopForeground(STOP_FOREGROUND_REMOVE);
        super.onDestroy();
    }

    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }
}
