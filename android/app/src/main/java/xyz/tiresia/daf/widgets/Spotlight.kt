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
import androidx.glance.Image
import androidx.glance.ImageProvider
import androidx.glance.LocalContext
import androidx.glance.LocalSize
import androidx.glance.action.clickable
import androidx.glance.appwidget.GlanceAppWidget
import androidx.glance.appwidget.GlanceAppWidgetManager
import androidx.glance.appwidget.GlanceAppWidgetReceiver
import androidx.glance.appwidget.SizeMode
import androidx.glance.appwidget.appWidgetBackground
import androidx.glance.appwidget.cornerRadius
import androidx.glance.appwidget.provideContent
import androidx.glance.background
import androidx.glance.currentState
import androidx.glance.layout.Alignment
import androidx.glance.layout.Box
import androidx.glance.layout.Column
import androidx.glance.layout.ContentScale
import androidx.glance.layout.fillMaxSize
import androidx.glance.layout.fillMaxWidth
import androidx.glance.layout.padding
import androidx.glance.text.Text

/**
 * Spotlight: one piece with its picture filling the widget and its title over it: what's left in
 * today's Edition first, then the Feed's newest. It moves on every two hours (a different one on
 * each Spotlight placed). As Capy Reader's Spotlight.
 */
class Spotlight : GlanceAppWidget() {
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
        val all = Board.list(w?.optJSONArray("spotlight"))
        if (w == null) return Look.Empty("Connect in Daf", Look.go(c, "#today"))
        if (all.isEmpty()) return Look.Empty("Nothing new", Look.go(c, "#feed"))
        val slot = (System.currentTimeMillis() / (2 * 3600 * 1000L)).toInt()
        val p = all[Math.floorMod(slot + wid, all.size)]
        val pic = Board.bitmap(c, p.optString("thumb"))
        val size = LocalSize.current
        val small = size.width < 200.dp
        Box(GlanceModifier.fillMaxSize().appWidgetBackground().cornerRadius(android.R.dimen.system_app_widget_background_radius)
                .background(GlanceTheme.colors.primaryContainer).clickable(Look.go(c, p.optString("route"))),
            contentAlignment = Alignment.BottomStart) {
            if (pic != null) Image(ImageProvider(pic), contentDescription = null, contentScale = ContentScale.Crop, modifier = GlanceModifier.fillMaxSize())
            val on = if (pic != null) Look.White else GlanceTheme.colors.onPrimaryContainer
            Column(GlanceModifier.fillMaxWidth().let { if (pic != null) it.background(Look.Shade) else it }.padding(horizontal = 14.dp, vertical = 10.dp)) {
                val from = listOf(p.optString("label").takeIf { it.isNotBlank() && it != "null" }, p.optString("source")).filterNotNull().filter { it.isNotBlank() }.distinct()
                if (from.isNotEmpty()) Text(from.joinToString(" · "), maxLines = 1, style = Look.sub(11.sp, on))
                Text(p.optString("title"), maxLines = if (small) 3 else 2, style = Look.title(if (small) 13.sp else 16.sp, color = on))
            }
        }
    }
}

class SpotlightReceiver : GlanceAppWidgetReceiver() {
    override val glanceAppWidget = Spotlight()

    override fun onUpdate(context: Context, appWidgetManager: AppWidgetManager, appWidgetIds: IntArray) {
        super.onUpdate(context, appWidgetManager, appWidgetIds)
        Board.refreshIfOlder(context, 10 * 60 * 1000L)
    }
}
