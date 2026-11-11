package xyz.tiresia.daf

import android.app.Activity
import android.appwidget.AppWidgetManager
import android.content.Context
import android.content.Intent
import android.graphics.Typeface
import android.os.Bundle
import android.util.TypedValue
import android.view.View
import android.view.ViewGroup
import android.widget.ArrayAdapter
import android.widget.LinearLayout
import android.widget.ListView
import android.widget.TextView
import androidx.compose.runtime.Composable
import androidx.compose.ui.unit.DpSize
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.glance.GlanceId
import androidx.glance.GlanceModifier
import androidx.glance.GlanceTheme
import androidx.glance.LocalContext
import androidx.glance.action.ActionParameters
import androidx.glance.action.clickable
import androidx.glance.appwidget.GlanceAppWidget
import androidx.glance.appwidget.GlanceAppWidgetManager
import androidx.glance.appwidget.GlanceAppWidgetReceiver
import androidx.glance.appwidget.SizeMode
import androidx.glance.appwidget.action.ActionCallback
import androidx.glance.appwidget.action.actionRunCallback
import androidx.glance.appwidget.lazy.LazyColumn
import androidx.glance.appwidget.lazy.items
import androidx.glance.appwidget.provideContent
import androidx.glance.currentState
import androidx.glance.layout.Alignment
import androidx.glance.layout.Column
import androidx.glance.layout.Row
import androidx.glance.layout.Spacer
import androidx.glance.layout.fillMaxWidth
import androidx.glance.layout.padding
import androidx.glance.layout.width
import androidx.glance.text.Text
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONObject
import kotlin.concurrent.thread

/**
 * The Feed: the newest unseen headlines from the whole Feed, a folder or one feed (picked when it's
 * placed, and again from the widget's own settings), each with its source, how long ago and its
 * picture; a refresh button asks Daf now. As Capy Reader's Headlines, Feeder's and FeedFlow's lists.
 */
class FeedWidget : GlanceAppWidget() {
    override val sizeMode = SizeMode.Exact
    override val previewSizeMode = SizeMode.Responsive(setOf(DpSize(250.dp, 250.dp)))

    /** The widget picker's picture: drawn on the phone from what Daf last said (Board.previews). */
    override suspend fun providePreview(context: Context, widgetCategory: Int) {
        provideContent { GlanceTheme { Content(0L, 0) } }
    }

    override suspend fun provideGlance(context: Context, id: GlanceId) {
        val wid = Board.wid(context, id)
        provideContent {
            val v = currentState(Board.V)       // a new answer: drawn again (Content reads Board then)
            GlanceTheme { Content(v, wid) }
        }
    }

    @Suppress("UNUSED_PARAMETER")
    @Composable
    private fun Content(v: Long?, wid: Int) {
        val c = LocalContext.current
        val w = Board.kept(c) ?: return Look.Empty("Connect in Daf", Look.go(c, "#today"))
        val src = Board.feedSource(c, wid)
        val name = if (src.isEmpty()) "Feed" else Board.list(w.optJSONArray("feeds")).firstOrNull { it.optString("key") == src }?.optString("name") ?: "Feed"
        val items = Board.list(Board.feed(c, src)?.optJSONArray("items"))
        Look.Frame(pad = 12.dp) {
            Row(GlanceModifier.fillMaxWidth().padding(bottom = 6.dp), verticalAlignment = Alignment.CenterVertically) {
                Text(name, maxLines = 1, style = Look.title(15.sp), modifier = GlanceModifier.defaultWeight().clickable(Look.go(c, "#feed")))
                Look.Icon(R.drawable.w_refresh, "Refresh", 20.dp, modifier = GlanceModifier.padding(start = 8.dp).clickable(actionRunCallback<RefreshFeed>()))
            }
            if (items.isEmpty()) {
                Text(if (Board.feed(c, src) == null) "…" else "Nothing new", style = Look.sub(13.sp), modifier = GlanceModifier.padding(top = 8.dp))
            } else {
                LazyColumn {
                    items(items, itemId = { it.optString("id").hashCode().toLong() }) { Headline(it, one = src.startsWith("feed:")) }
                }
            }
        }
    }

    @Composable
    private fun Headline(d: JSONObject, one: Boolean) {
        val c = LocalContext.current
        val pic = Board.bitmap(c, d.optString("thumb"))
        val sub = listOf(if (one) "" else d.optString("source"), ago(d.optLong("published"))).filter { it.isNotBlank() }.joinToString(" · ")
        Row(GlanceModifier.fillMaxWidth().padding(vertical = 6.dp).clickable(Look.go(c, d.optString("route"))), verticalAlignment = Alignment.CenterVertically) {
            Column(GlanceModifier.defaultWeight()) {
                Text(d.optString("title"), maxLines = 2, style = Look.title(13.sp).copy(fontWeight = null))
                if (sub.isNotBlank()) Text(sub, maxLines = 1, style = Look.sub(11.sp))
            }
            if (pic != null) {
                Spacer(GlanceModifier.width(10.dp))
                Look.Picture(pic, 44.dp, 44.dp)
            }
        }
    }

    /** "5m", "2h", "3d": how long ago it was posted. */
    private fun ago(t: Long): String {
        if (t <= 0) return ""
        val s = System.currentTimeMillis() / 1000 - t
        return when {
            s < 3600 -> "${maxOf(1, s / 60)}m"
            s < 86400 -> "${s / 3600}h"
            else -> "${s / 86400}d"
        }
    }
}

/** The refresh button: this widget's headlines asked for now. */
class RefreshFeed : ActionCallback {
    override suspend fun onAction(context: Context, glanceId: GlanceId, parameters: ActionParameters) {
        val wid = GlanceAppWidgetManager(context).getAppWidgetId(glanceId)
        withContext(Dispatchers.IO) { Board.refreshFeed(context, Board.feedSource(context, wid)) }
    }
}

class FeedReceiver : GlanceAppWidgetReceiver() {
    override val glanceAppWidget = FeedWidget()

    override fun onUpdate(context: Context, appWidgetManager: AppWidgetManager, appWidgetIds: IntArray) {
        super.onUpdate(context, appWidgetManager, appWidgetIds)
        Board.refreshIfOlder(context, 10 * 60 * 1000L)
        // a widget just placed shows its part of the Feed now, not at the next half hour
        val missing = appWidgetIds.map { Board.feedSource(context, it) }.filter { Board.feed(context, it) == null }.toSet()
        if (missing.isNotEmpty()) {
            val app = context.applicationContext
            thread(name = "daf-widgets") { missing.forEach { Board.refreshFeed(app, it) } }
        }
    }
}

/** Which part of the Feed a Feed widget shows: the whole Feed, a folder, or one feed. */
class FeedPick : Activity() {
    private var wid = AppWidgetManager.INVALID_APPWIDGET_ID
    private data class Choice(val key: String, val name: String, val folder: Boolean, val inside: Boolean)

    override fun onCreate(saved: Bundle?) {
        super.onCreate(saved)
        wid = intent?.getIntExtra(AppWidgetManager.EXTRA_APPWIDGET_ID, AppWidgetManager.INVALID_APPWIDGET_ID) ?: AppWidgetManager.INVALID_APPWIDGET_ID
        setResult(RESULT_CANCELED, Intent().putExtra(AppWidgetManager.EXTRA_APPWIDGET_ID, wid))
        if (wid == AppWidgetManager.INVALID_APPWIDGET_ID) return finish()
        val dp = resources.displayMetrics.density
        val list = ListView(this)
        val head = TextView(this).apply {
            text = "Feed"
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 22f)
            setPadding((20 * dp).toInt(), (24 * dp).toInt(), (20 * dp).toInt(), (12 * dp).toInt())
        }
        setContentView(LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            fitsSystemWindows = true
            addView(head)
            addView(list, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 0, 1f))
        })
        val now = Board.feedSource(this, wid)
        fun fill(feeds: List<JSONObject>) {
            val choices = listOf(Choice("", "Everything", true, false)) + feeds.map {
                Choice(it.optString("key"), it.optString("name"), it.optString("key").startsWith("folder:"), it.optString("folder").isNotBlank())
            }
            list.adapter = object : ArrayAdapter<Choice>(this, android.R.layout.simple_list_item_1, choices) {
                override fun getView(position: Int, convertView: View?, parent: ViewGroup): View {
                    val v = super.getView(position, convertView, parent) as TextView
                    val ch = getItem(position)!!
                    v.text = (if (ch.key == now) "✓  " else "") + ch.name
                    v.setTypeface(null, if (ch.folder) Typeface.BOLD else Typeface.NORMAL)
                    v.setPadding(((if (ch.inside) 40 else 20) * dp).toInt(), v.paddingTop, v.paddingRight, v.paddingBottom)
                    return v
                }
            }
            list.setOnItemClickListener { _, _, i, _ ->
                val ch = choices[i]
                Board.setFeedSource(this, wid, ch.key)
                setResult(RESULT_OK, Intent().putExtra(AppWidgetManager.EXTRA_APPWIDGET_ID, wid))
                val app = applicationContext
                thread(name = "daf-widgets") { Board.refreshFeed(app, ch.key) }
                finish()
            }
        }
        val kept = Board.kept(this)?.optJSONArray("feeds")
        if (kept != null) fill(Board.list(kept))
        else {
            fill(emptyList())
            val app = applicationContext
            thread(name = "daf-widgets") {
                val feeds = runCatching { Board.list(Server.widgets(app).optJSONArray("feeds")) }.getOrDefault(emptyList())
                runOnUiThread { if (!isFinishing) fill(feeds) }
            }
        }
    }
}
