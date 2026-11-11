package xyz.tiresia.daf

import android.appwidget.AppWidgetManager
import android.content.Context
import android.content.Intent
import androidx.compose.runtime.Composable
import androidx.compose.ui.unit.DpSize
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.glance.GlanceId
import androidx.glance.GlanceModifier
import androidx.glance.GlanceTheme
import androidx.glance.LocalContext
import androidx.glance.LocalSize
import androidx.glance.action.Action
import androidx.glance.action.ActionParameters
import androidx.glance.action.actionParametersOf
import androidx.glance.action.clickable
import androidx.glance.appwidget.GlanceAppWidget
import androidx.glance.appwidget.GlanceAppWidgetReceiver
import androidx.glance.appwidget.SizeMode
import androidx.glance.appwidget.action.ActionCallback
import androidx.glance.appwidget.action.actionRunCallback
import androidx.glance.appwidget.cornerRadius
import androidx.glance.appwidget.provideContent
import androidx.glance.background
import androidx.glance.currentState
import androidx.glance.layout.Alignment
import androidx.glance.layout.Box
import androidx.glance.layout.Column
import androidx.glance.layout.Row
import androidx.glance.layout.Spacer
import androidx.glance.layout.fillMaxSize
import androidx.glance.layout.fillMaxWidth
import androidx.glance.layout.height
import androidx.glance.layout.padding
import androidx.glance.layout.size
import androidx.glance.layout.width
import androidx.glance.text.Text
import kotlin.concurrent.thread

/**
 * Listen: what Daf's player is playing (an episode, an audiobook, read-aloud), with back, play or
 * pause, and ahead, as the lock screen has them (Listen.java tells the widget as it changes). With
 * nothing in the player, the episode last played, and Play opens Daf and plays it on from where it
 * stopped (the page's listen:resume).
 */
class ListenWidget : GlanceAppWidget() {
    override val sizeMode = SizeMode.Exact
    override val previewSizeMode = SizeMode.Responsive(setOf(DpSize(250.dp, 64.dp)))

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
        val p = Server.prefs(c)
        val state = p.getString(LIVE_STATE, "stopped")
        val live = Listen.isRunning() && (state == "playing" || state == "paused")
        val ep = Board.kept(c)?.optJSONObject("listen")
        if (!live && ep == null) return Look.Empty("Nothing playing", Look.go(c, "#podcasts"))
        val title = if (live) p.getString(LIVE_TITLE, "") ?: "" else ep!!.optString("title")
        val sub = if (live) p.getString(LIVE_SUB, "") ?: "" else ep!!.optString("show")
        val open = if (live) Look.go(c, null) else Look.go(c, ep!!.optString("route"))
        val art = if (!live || title == ep?.optString("title")) Board.bitmap(c, ep?.optString("image")) else null
        val at = ep?.optDouble("at", 0.0) ?: 0.0
        val dur = ep?.optDouble("duration", 0.0) ?: 0.0
        val size = LocalSize.current
        val side = (size.height - 20.dp).coerceIn(36.dp, 72.dp)
        Look.Frame(pad = 10.dp) {
            Row(GlanceModifier.fillMaxSize(), verticalAlignment = Alignment.CenterVertically) {
                Box(GlanceModifier.clickable(open)) { Look.Picture(art, side, side, radius = 8.dp, letter = sub) }
                Spacer(GlanceModifier.width(12.dp))
                Column(GlanceModifier.defaultWeight().clickable(open)) {
                    Text(title, maxLines = if (size.height >= 100.dp) 2 else 1, style = Look.title(14.sp))
                    if (sub.isNotBlank()) Text(sub, maxLines = 1, style = Look.sub(12.sp))
                    if (!live && dur > 0) {
                        Spacer(GlanceModifier.height(6.dp))
                        Look.Bar((at / dur).toFloat())
                    }
                }
                Spacer(GlanceModifier.width(6.dp))
                if (live) {
                    Button(R.drawable.w_back, "Back", press("listen:prev"))
                    Button(if (state == "playing") R.drawable.w_pause else R.drawable.w_play, if (state == "playing") "Pause" else "Play",
                        press(if (state == "playing") "listen:pause" else "listen:play"), big = true)
                    Button(R.drawable.w_ahead, "Ahead", press("listen:next"))
                } else {
                    Button(R.drawable.w_play, "Play", Look.go(c, ep!!.optString("route"), "listen:resume"), big = true)
                }
            }
        }
    }

    @Composable
    private fun Button(icon: Int, label: String, action: Action, big: Boolean = false) {
        val s = if (big) 44.dp else 36.dp
        Box(GlanceModifier.size(s).cornerRadius(s / 2).let { if (big) it.background(GlanceTheme.colors.primaryContainer) else it }.clickable(action),
            contentAlignment = Alignment.Center) {
            Look.Icon(icon, label, if (big) 26.dp else 24.dp, if (big) GlanceTheme.colors.onPrimaryContainer else GlanceTheme.colors.onSurfaceVariant)
        }
    }

    private fun press(cmd: String): Action = actionRunCallback<ListenPress>(actionParametersOf(CMD to cmd))

    companion object {
        const val LIVE_STATE = "listen.state"
        const val LIVE_TITLE = "listen.title"
        const val LIVE_SUB = "listen.sub"
        val CMD = ActionParameters.Key<String>("cmd")

        /** Listen.java: the player changed (playing, paused, stopped); the widget shows it. */
        @JvmStatic
        fun tell(c: Context, state: String?, title: String?, sub: String?) {
            val app = c.applicationContext
            val p = Server.prefs(app)
            if (state == p.getString(LIVE_STATE, null) && (title == null || title == p.getString(LIVE_TITLE, null))
                && (sub == null || sub == p.getString(LIVE_SUB, null))) return
            p.edit().apply {
                if (state != null) putString(LIVE_STATE, state)
                if (title != null) putString(LIVE_TITLE, title)
                if (sub != null) putString(LIVE_SUB, sub)
            }.apply()
            if (Board.placed(app, ListenReceiver::class.java).isEmpty()) return
            thread(name = "daf-widgets") { Board.drawAll(app) }
        }
    }
}

/** Back, play or pause, ahead: the player's own buttons, through Listen as the lock screen's are. */
class ListenPress : ActionCallback {
    override suspend fun onAction(context: Context, glanceId: GlanceId, parameters: ActionParameters) {
        val cmd = parameters[ListenWidget.CMD] ?: return
        if (Listen.isRunning()) context.startService(Intent(context, Listen::class.java).putExtra("cmd", cmd))
        else Board.drawAll(context)
    }
}

class ListenReceiver : GlanceAppWidgetReceiver() {
    override val glanceAppWidget = ListenWidget()

    override fun onUpdate(context: Context, appWidgetManager: AppWidgetManager, appWidgetIds: IntArray) {
        super.onUpdate(context, appWidgetManager, appWidgetIds)
        Board.refreshIfOlder(context, 10 * 60 * 1000L)
    }
}
