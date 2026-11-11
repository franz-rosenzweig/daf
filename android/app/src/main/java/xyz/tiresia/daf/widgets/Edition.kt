package xyz.tiresia.daf

import android.appwidget.AppWidgetManager
import android.content.Context
import androidx.compose.runtime.Composable
import androidx.compose.ui.unit.DpSize
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.glance.GlanceId
import androidx.glance.GlanceModifier
import androidx.glance.GlanceTheme
import androidx.glance.LocalContext
import androidx.glance.action.clickable
import androidx.glance.appwidget.GlanceAppWidget
import androidx.glance.appwidget.GlanceAppWidgetReceiver
import androidx.glance.appwidget.SizeMode
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
import org.json.JSONObject

/**
 * The Edition: today's pieces, ticked off as they're read, and how many are done. A piece opens in
 * Daf; the title opens the Edition. As Read You's article list.
 */
class EditionWidget : GlanceAppWidget() {
    override val sizeMode = SizeMode.Exact
    override val previewSizeMode = SizeMode.Responsive(setOf(DpSize(220.dp, 250.dp)))

    /** The widget picker's picture: drawn on the phone from what Daf last said (Board.previews). */
    override suspend fun providePreview(context: Context, widgetCategory: Int) {
        provideContent { GlanceTheme { Content(0L) } }
    }

    override suspend fun provideGlance(context: Context, id: GlanceId) {
        provideContent {
            val v = currentState(Board.V)       // a new answer: drawn again (Content reads Board then)
            GlanceTheme { Content(v) }
        }
    }

    @Suppress("UNUSED_PARAMETER")
    @Composable
    private fun Content(v: Long?) {
        val c = LocalContext.current
        val w = Board.kept(c)
        if (w == null) return Look.Empty("Connect in Daf", Look.go(c, "#today"))
        val e = w.optJSONObject("edition") ?: return Look.Empty("No Edition today", Look.go(c, "#edition"))
        val items = Board.list(e.optJSONArray("items"))
        val done = items.count { it.optBoolean("done") }
        Look.Frame(pad = 12.dp) {
            Row(GlanceModifier.fillMaxWidth().padding(bottom = 6.dp).clickable(Look.go(c, "#edition")), verticalAlignment = Alignment.CenterVertically) {
                Text("Edition", style = Look.title(15.sp))
                Text("  $done of ${items.size}", style = Look.sub(13.sp))
            }
            LazyColumn {
                items(items, itemId = { it.optString("id").hashCode().toLong() }) { Piece(it) }
            }
        }
    }

    @Composable
    private fun Piece(p: JSONObject) {
        val c = LocalContext.current
        val done = p.optBoolean("done")
        val kind = when (p.optString("kind")) { "video" -> "Video"; "podcast" -> "Episode"; else -> null }
        val mins = p.optInt("minutes", 0).takeIf { it > 0 }?.let { "$it min" }
        val sub = listOfNotNull(p.optString("source").takeIf { it.isNotBlank() }, kind, mins).joinToString(" · ")
        Column(GlanceModifier.fillMaxWidth().padding(vertical = 6.dp).clickable(Look.go(c, p.optString("route")))) {
            Row(GlanceModifier.fillMaxWidth(), verticalAlignment = Alignment.Top) {
                Look.Icon(if (done) R.drawable.w_done else R.drawable.w_todo, if (done) "Read" else null, 18.dp,
                    if (done) GlanceTheme.colors.primary else GlanceTheme.colors.outline, GlanceModifier.padding(top = 1.dp))
                Spacer(GlanceModifier.width(10.dp))
                Column(GlanceModifier.defaultWeight()) {
                    Text(p.optString("title"), maxLines = 2, style = Look.title(13.sp, done = done,
                        color = if (done) GlanceTheme.colors.onSurfaceVariant else null).copy(fontWeight = null))
                    if (sub.isNotBlank()) Text(sub, maxLines = 1, style = Look.sub(11.sp))
                }
            }
        }
    }
}

class EditionReceiver : GlanceAppWidgetReceiver() {
    override val glanceAppWidget = EditionWidget()

    override fun onUpdate(context: Context, appWidgetManager: AppWidgetManager, appWidgetIds: IntArray) {
        super.onUpdate(context, appWidgetManager, appWidgetIds)
        Board.refreshIfOlder(context, 10 * 60 * 1000L)
    }
}
