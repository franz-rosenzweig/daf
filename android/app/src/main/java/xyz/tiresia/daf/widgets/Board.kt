// In Daf's own package (Server and MainActivity.open are package-private), kept in a folder of their own.
package xyz.tiresia.daf

import android.appwidget.AppWidgetManager
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.util.LruCache
import androidx.datastore.preferences.core.longPreferencesKey
import androidx.glance.appwidget.GlanceAppWidget
import androidx.glance.appwidget.GlanceAppWidgetManager
import androidx.glance.appwidget.GlanceAppWidgetReceiver
import androidx.glance.appwidget.state.updateAppWidgetState
import kotlinx.coroutines.runBlocking
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.security.MessageDigest
import java.util.concurrent.atomic.AtomicBoolean
import kotlin.concurrent.thread

/**
 * What the widgets show, kept on the phone so they draw at once and with no signal: one answer from
 * GET /api/phone/widgets (Keep reading, the Edition, Spotlight, highlights, Listen, the Feed's
 * sources), each Feed widget's headlines (/api/phone/widget-feed), and their pictures, made small
 * and kept as files. Asked again every half hour (Android's own update of a widget), when the phone
 * is unlocked and when the app goes to the background (Widget.refreshIfOlder), and by a Feed
 * widget's refresh button. If Daf can't be reached the widgets keep what they last had.
 */
object Board {
    private const val KEPT = "widgets.json"
    private const val AT = "widgets.at"
    private const val FAILED = "widgets.failed"
    private val asking = AtomicBoolean(false)
    private val bitmaps = LruCache<String, Bitmap>(24)

    /** In each widget's own state: bumped after an answer, so a widget that's showing draws it. */
    val V = longPreferencesKey("v")

    /** The widgets and their receivers, the ones placed are drawn again after each answer. */
    val all: List<Pair<Class<out GlanceAppWidgetReceiver>, () -> GlanceAppWidget>> = listOf(
        KeepReadingReceiver::class.java to { KeepReading() },
        HighlightReceiver::class.java to { HighlightWidget() },
        SpotlightReceiver::class.java to { Spotlight() },
        EditionReceiver::class.java to { EditionWidget() },
        FeedReceiver::class.java to { FeedWidget() },
        ListenReceiver::class.java to { ListenWidget() },
    )

    private fun prefs(c: Context) = Server.prefs(c)

    fun placed(c: Context, receiver: Class<*>): IntArray =
        AppWidgetManager.getInstance(c).getAppWidgetIds(ComponentName(c, receiver))

    fun anyPlaced(c: Context) = all.any { placed(c, it.first).isNotEmpty() }

    /** The last answer, or null before the first. */
    fun kept(c: Context): JSONObject? =
        prefs(c).getString(KEPT, null)?.let { runCatching { JSONObject(it) }.getOrNull() }

    fun failed(c: Context) = prefs(c).getBoolean(FAILED, false)

    /** Asks if the last answer is older than this, in the background. */
    @JvmStatic
    fun refreshIfOlder(c: Context, ms: Long) {
        val app = c.applicationContext
        if (System.currentTimeMillis() - prefs(app).getLong(AT, 0) < ms || asking.get() || !anyPlaced(app)) return
        thread(name = "daf-widgets") { refresh(app) }
    }

    @JvmStatic
    fun refreshSoon(c: Context) {
        val app = c.applicationContext
        thread(name = "daf-widgets") { refresh(app) }
    }

    /** Asks Daf (on this thread: never the main one), keeps the answer and its pictures, draws every widget. */
    @JvmStatic
    fun refresh(c: Context) {
        if (!anyPlaced(c) || !asking.compareAndSet(false, true)) return
        try {
            val w = Server.widgets(c)
            val feeds = JSONObject()
            for (src in feedSources(c)) runCatching { feeds.put(src, Server.widgetFeed(c, src)) }
            w.put("feed", feeds)
            pictures(c, w)
            prefs(c).edit().putString(KEPT, w.toString()).putLong(AT, System.currentTimeMillis()).putBoolean(FAILED, false).apply()
            previews(c)
        } catch (e: Exception) {
            prefs(c).edit().putBoolean(FAILED, true).apply()
        } finally {
            asking.set(false)
            drawAll(c)
        }
    }

    /** Every placed widget drawn again from what's kept. */
    @JvmStatic
    fun drawAll(c: Context) = runBlocking {
        val m = GlanceAppWidgetManager(c)
        for ((_, make) in all) {
            val w = make()
            for (id in runCatching { m.getGlanceIds(w.javaClass) }.getOrDefault(emptyList())) {
                runCatching {                       // one widget gone meanwhile mustn't stop the others
                    updateAppWidgetState(c, id) { it[V] = System.currentTimeMillis() }
                    w.update(c, id)
                }
            }
        }
    }

    /** The widget picker's pictures (Android 15 on), drawn from the phone's own answer: once a day. */
    private fun previews(c: Context) {
        if (android.os.Build.VERSION.SDK_INT < 35) return
        val p = prefs(c)
        if (System.currentTimeMillis() - p.getLong("widgets.previews", 0) < 24 * 3600 * 1000L) return
        p.edit().putLong("widgets.previews", System.currentTimeMillis()).apply()
        runBlocking {
            val m = GlanceAppWidgetManager(c)
            for ((receiver, _) in all) {
                runCatching { m.setWidgetPreviews(receiver.kotlin) }
                    .onSuccess { r -> if (r != GlanceAppWidgetManager.SET_WIDGET_PREVIEWS_RESULT_SUCCESS) android.util.Log.w("Daf", "widget preview ${receiver.simpleName}: $r") }
                    .onFailure { e -> android.util.Log.w("Daf", "widget preview ${receiver.simpleName}", e) }
            }
        }
    }

    // ---- a Feed widget's source, per placed widget ("" is the whole Feed) ----

    fun feedSource(c: Context, appWidgetId: Int): String = prefs(c).getString("widget.feed.$appWidgetId", "") ?: ""

    fun setFeedSource(c: Context, appWidgetId: Int, src: String) {
        prefs(c).edit().putString("widget.feed.$appWidgetId", src).apply()
    }

    private fun feedSources(c: Context): Set<String> =
        placed(c, FeedReceiver::class.java).map { feedSource(c, it) }.toSet()

    /** A Feed widget's headlines: from the last answer, or asked for now (a widget just placed or changed). */
    fun feed(c: Context, src: String): JSONObject? = kept(c)?.optJSONObject("feed")?.optJSONObject(src)

    fun refreshFeed(c: Context, src: String) {
        // another ask under way: this one waits its turn (up to half a minute) rather than being lost
        var turn = false
        for (i in 0 until 60) { if (asking.compareAndSet(false, true)) { turn = true; break }; Thread.sleep(500) }
        if (!turn) return
        val w = kept(c) ?: run { asking.set(false); return refresh(c) }
        try {
            val f = Server.widgetFeed(c, src)
            val feeds = w.optJSONObject("feed") ?: JSONObject()
            feeds.put(src, f)
            w.put("feed", feeds)
            pictures(c, w)
            prefs(c).edit().putString(KEPT, w.toString()).apply()
        } catch (_: Exception) {
        } finally {
            asking.set(false)
            drawAll(c)
        }
    }

    /** A placed widget's number; 0 for the picker's preview, which has none. */
    fun wid(c: Context, id: androidx.glance.GlanceId): Int = runCatching { GlanceAppWidgetManager(c).getAppWidgetId(id) }.getOrDefault(0)

    // ---- a widget's own small numbers, by its id (the highlight shuffled to) ----

    fun int(c: Context, key: String, appWidgetId: Int, def: Int = 0) = prefs(c).getInt("widget.$key.$appWidgetId", def)

    fun setInt(c: Context, key: String, appWidgetId: Int, v: Int) {
        prefs(c).edit().putInt("widget.$key.$appWidgetId", v).apply()
    }

    // ---- pictures: made small and kept as files, the ones no widget shows any more removed ----

    private fun dir(c: Context) = File(c.filesDir, "widgets").apply { mkdirs() }

    private fun name(url: String): String =
        MessageDigest.getInstance("SHA-1").digest(url.toByteArray()).joinToString("") { "%02x".format(it) }.take(20) + ".jpg"

    /** Every picture the answer names, fetched if it isn't here yet; [largest] side in pixels. */
    private fun pictures(c: Context, w: JSONObject) {
        val want = linkedMapOf<String, Int>()
        fun add(u: String?, px: Int) { if (!u.isNullOrBlank() && u != "null") want[u] = maxOf(px, want[u] ?: 0) }
        each(w.optJSONArray("reading")) { add(it.optString("cover"), 420) }
        each(w.optJSONArray("spotlight")) { add(it.optString("thumb"), 900) }
        w.optJSONObject("listen")?.let { add(it.optString("image"), 240) }
        w.optJSONObject("feed")?.let { f -> f.keys().forEach { k -> each(f.optJSONObject(k)?.optJSONArray("items")) { add(it.optString("thumb"), 200) } } }
        val d = dir(c)
        val keep = HashSet<String>()
        for ((u, px) in want) {
            val f = File(d, name(u))
            keep += f.name
            if (f.exists() && f.length() > 0) continue
            runCatching {
                val bytes = Server.picture(c, u)
                val b = decode(bytes, px) ?: return@runCatching
                f.outputStream().use { b.compress(Bitmap.CompressFormat.JPEG, 85, it) }
            }
        }
        d.listFiles()?.forEach { if (it.name !in keep) it.delete() }
        bitmaps.evictAll()
    }

    private fun decode(bytes: ByteArray, px: Int): Bitmap? {
        val o = BitmapFactory.Options().apply { inJustDecodeBounds = true }
        BitmapFactory.decodeByteArray(bytes, 0, bytes.size, o)
        if (o.outWidth <= 0) return null
        var s = 1
        while (maxOf(o.outWidth, o.outHeight) / (s * 2) >= px) s *= 2
        val b = BitmapFactory.decodeByteArray(bytes, 0, bytes.size, BitmapFactory.Options().apply { inSampleSize = s }) ?: return null
        val big = maxOf(b.width, b.height)
        if (big <= px) return b
        val k = px.toFloat() / big
        return Bitmap.createScaledBitmap(b, (b.width * k).toInt().coerceAtLeast(1), (b.height * k).toInt().coerceAtLeast(1), true)
    }

    /** A kept picture, or null (not fetched yet, or none). */
    fun bitmap(c: Context, url: String?): Bitmap? {
        if (url.isNullOrBlank() || url == "null") return null
        bitmaps.get(url)?.let { return it }
        val f = File(dir(c), name(url))
        if (!f.exists()) return null
        return BitmapFactory.decodeFile(f.path)?.also { bitmaps.put(url, it) }
    }

    // ---- going somewhere in Daf ----

    fun open(c: Context, route: String?, command: String? = null): Intent = MainActivity.open(c, route, command)

    inline fun each(a: JSONArray?, f: (JSONObject) -> Unit) {
        if (a == null) return
        for (i in 0 until a.length()) a.optJSONObject(i)?.let(f)
    }

    fun list(a: JSONArray?): List<JSONObject> = buildList { each(a) { add(it) } }
}
