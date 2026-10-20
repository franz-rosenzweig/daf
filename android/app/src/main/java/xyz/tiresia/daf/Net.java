package xyz.tiresia.daf;

import android.content.Context;
import android.net.ConnectivityManager;
import android.net.NetworkCapabilities;

/**
 * Whether Daf's server can be reached now. Down when Android has no network at all, and for five
 * minutes after a page load failed for want of the server (the network is up, Daf isn't: out of
 * range of the tailnet, the tunnel down). While it's down, the app answers from what it keeps:
 * its own copy of the screens (AppFiles), the data it kept (DataStore), the books and manga
 * (Offline).
 */
final class Net {
    private static volatile long cutUntil;

    static boolean down(Context c) {
        if (System.currentTimeMillis() < cutUntil) return true;
        ConnectivityManager cm = c.getSystemService(ConnectivityManager.class);
        NetworkCapabilities n = cm == null ? null : cm.getNetworkCapabilities(cm.getActiveNetwork());
        return n == null || !n.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET);
    }

    /** A load just failed for want of the server: the device's copy for the next five minutes,
     *  or until Android says a network is back. */
    static void unreachable() {
        cutUntil = System.currentTimeMillis() + 5 * 60_000L;
    }

    static void reachable() {
        cutUntil = 0;
    }
}
