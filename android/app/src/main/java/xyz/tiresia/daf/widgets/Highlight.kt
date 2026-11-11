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
import androidx.glance.LocalSize
import androidx.glance.action.ActionParameters
import androidx.glance.action.clickable
import androidx.glance.appwidget.GlanceAppWidget
import androidx.glance.appwidget.GlanceAppWidgetManager
import androidx.glance.appwidget.GlanceAppWidgetReceiver
import androidx.glance.appwidget.SizeMode
import androidx.glance.appwidget.action.ActionCallback
import androidx.glance.appwidget.action.actionRunCallback
import androidx.glance.appwidget.provideContent
import androidx.glance.appwidget.state.updateAppWidgetState
import androidx.glance.currentState
import androidx.glance.layout.Alignment
import androidx.glance.layout.Row
import androidx.glance.layout.Spacer
import androidx.glance.layout.fillMaxWidth
import androidx.glance.layout.height
import androidx.glance.layout.padding
import androidx.glance.text.Text

/**
 * A highlight on its own: the day's review first, then ones kept in Review, in a serif face, with
 * its book. The shuffle button goes on to the next (with no signal too: twenty come with each
 * answer); the words open Review. As Readwise's highlight widget on the iPhone.
 */
class HighlightWidget : GlanceAppWidget() {
    override val sizeMode = SizeMode.Exact
    override val previewSizeMode = SizeMode.Responsive(setOf(DpSize(250.dp, 120.dp)))

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
        val w = Board.kept(c)
        val all = Board.list(w?.optJSONArray("highlights"))
        if (w == null) return Look.Empty("Connect in Daf", Look.go(c, "#today"))
        if (all.isEmpty()) return Look.Empty("No highlights yet", Look.go(c, "#highlights"))
        val h = all[Math.floorMod(Board.int(c, "hl", wid), all.size)]
        val size = LocalSize.current
        val big = size.width >= 220.dp && size.height >= 160.dp
        val small = size.width < 200.dp
        val lines = ((size.height.value - 48) / (if (big) 22f else if (small) 17f else 19f)).toInt().coerceAtLeast(2)
        Look.Frame(pad = 14.dp) {
            Text("“" + h.optString("text").trim() + "”", maxLines = lines,
                style = Look.title(if (big) 16.sp else if (small) 12.sp else 14.sp, serif = true).copy(fontWeight = null),
                modifier = GlanceModifier.fillMaxWidth().defaultWeight().clickable(Look.go(c, h.optString("route", "#review"))))
            Spacer(GlanceModifier.height(6.dp))
            Row(GlanceModifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                Text(h.optString("title"), maxLines = 1, style = Look.sub(12.sp), modifier = GlanceModifier.defaultWeight())
                Look.Icon(R.drawable.w_shuffle, "Another", 20.dp,
                    modifier = GlanceModifier.padding(start = 8.dp).clickable(actionRunCallback<Shuffle>()))
            }
        }
    }
}

/** The shuffle button: the next highlight on this widget. */
class Shuffle : ActionCallback {
    override suspend fun onAction(context: Context, glanceId: GlanceId, parameters: ActionParameters) {
        val wid = GlanceAppWidgetManager(context).getAppWidgetId(glanceId)
        Board.setInt(context, "hl", wid, Board.int(context, "hl", wid) + 1)
        updateAppWidgetState(context, glanceId) { it[Board.V] = System.currentTimeMillis() }
        HighlightWidget().update(context, glanceId)
    }
}

class HighlightReceiver : GlanceAppWidgetReceiver() {
    override val glanceAppWidget = HighlightWidget()

    override fun onUpdate(context: Context, appWidgetManager: AppWidgetManager, appWidgetIds: IntArray) {
        super.onUpdate(context, appWidgetManager, appWidgetIds)
        Board.refreshIfOlder(context, 10 * 60 * 1000L)
    }
}
