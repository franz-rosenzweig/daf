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
import androidx.glance.action.clickable
import androidx.glance.appwidget.GlanceAppWidget
import androidx.glance.appwidget.GlanceAppWidgetReceiver
import androidx.glance.appwidget.SizeMode
import androidx.glance.appwidget.provideContent
import androidx.glance.currentState
import androidx.glance.layout.Alignment
import androidx.glance.layout.Column
import androidx.glance.layout.Row
import androidx.glance.layout.Spacer
import androidx.glance.layout.fillMaxHeight
import androidx.glance.layout.fillMaxSize
import androidx.glance.layout.fillMaxWidth
import androidx.glance.layout.height
import androidx.glance.layout.padding
import androidx.glance.layout.width
import androidx.glance.text.Text
import org.json.JSONObject
import kotlin.math.max
import kotlin.math.roundToInt

/**
 * Keep reading: the books you're in the middle of (the nightstand first, then the others read
 * lately), each with its cover and how far along you are; a book opens in Daf's reader where you
 * left off (its page when Daf has no file of it). As Mihon's cover grid: 2×2 one book, wider a
 * row of covers, taller a list with the author and Daf's note on where you are.
 */
class KeepReading : GlanceAppWidget() {
    override val sizeMode = SizeMode.Exact
    override val previewSizeMode = SizeMode.Responsive(setOf(DpSize(250.dp, 120.dp)))

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
        val books = Board.list(w?.optJSONArray("reading"))
        if (w == null) return Look.Empty("Connect in Daf", Look.go(c, "#today"))
        if (books.isEmpty()) return Look.Empty("Nothing on the nightstand", Look.go(c, "#books"))
        val size = LocalSize.current
        when {
            size.height >= 200.dp && size.width >= 220.dp -> Rows(books, ((size.height.value - 24) / 84).toInt().coerceIn(1, books.size))
            size.width >= 200.dp -> Shelf(books, max(1, ((size.width.value - 16) / 92).toInt()).coerceAtMost(books.size))
            else -> One(books[0])
        }
    }

    private fun frac(b: JSONObject): Float {
        val p = if (b.isNull("progress")) b.optDouble("audio", 0.0) else b.optDouble("progress", 0.0)
        return (if (p.isNaN()) 0.0 else p / 100.0).toFloat()
    }

    private fun pct(b: JSONObject) = "${(frac(b) * 100).roundToInt()}%"

    /** Where you are, as Daf says it on Today ("58% in Daf", or the audiobook's time). */
    private fun note(b: JSONObject): String {
        val n = b.optString("note")
        return if (n.isNotBlank()) n else b.optString("audio_note").ifBlank { pct(b) }
    }

    /** 2×2: the first book's cover, as large as it fits, its line under it. */
    @Composable
    private fun One(b: JSONObject) {
        val c = LocalContext.current
        val size = LocalSize.current
        Look.Frame(GlanceModifier.clickable(Look.go(c, b.optString("route"))), pad = 10.dp) {
            val h = (size.height - 40.dp).coerceAtLeast(40.dp)
            Row(GlanceModifier.fillMaxWidth().defaultWeight(), horizontalAlignment = Alignment.CenterHorizontally) {
                Look.Picture(Board.bitmap(c, b.optString("cover")), h * 2 / 3, h, letter = b.optString("title"))
            }
            Spacer(GlanceModifier.height(6.dp))
            Look.Bar(frac(b))
            Text(pct(b) + " · " + b.optString("title"), maxLines = 1, style = Look.sub(11.sp), modifier = GlanceModifier.padding(top = 3.dp))
        }
    }

    /** Wider: a row of covers, each with its line and its title. */
    @Composable
    private fun Shelf(books: List<JSONObject>, n: Int) {
        val c = LocalContext.current
        val size = LocalSize.current
        Look.Frame(pad = 10.dp) {
            Row(GlanceModifier.fillMaxSize()) {
                books.take(n).forEachIndexed { i, b ->
                    if (i > 0) Spacer(GlanceModifier.width(10.dp))
                    Column(GlanceModifier.defaultWeight().fillMaxHeight().clickable(Look.go(c, b.optString("route"))),
                        horizontalAlignment = Alignment.CenterHorizontally) {
                        val h = (size.height - 46.dp).coerceAtLeast(36.dp)
                        Look.Picture(Board.bitmap(c, b.optString("cover")), h * 2 / 3, h, letter = b.optString("title"))
                        Spacer(GlanceModifier.height(6.dp))
                        Look.Bar(frac(b))
                        Text(b.optString("title"), maxLines = 1, style = Look.title(11.sp), modifier = GlanceModifier.padding(top = 3.dp))
                    }
                }
            }
        }
    }

    /** Taller: a list, each book with its author and where you are. */
    @Composable
    private fun Rows(books: List<JSONObject>, n: Int) {
        val c = LocalContext.current
        Look.Frame(pad = 12.dp) {
            books.take(n).forEach { b ->
                Row(GlanceModifier.fillMaxWidth().defaultWeight().clickable(Look.go(c, b.optString("route"))), verticalAlignment = Alignment.CenterVertically) {
                    Look.Picture(Board.bitmap(c, b.optString("cover")), 44.dp, 66.dp, letter = b.optString("title"))
                    Spacer(GlanceModifier.width(12.dp))
                    Column(GlanceModifier.defaultWeight()) {
                        Text(b.optString("title"), maxLines = 1, style = Look.title(14.sp))
                        if (b.optString("author").isNotBlank()) Text(b.optString("author"), maxLines = 1, style = Look.sub(12.sp))
                        Spacer(GlanceModifier.height(6.dp))
                        Look.Bar(frac(b))
                        Text(note(b), maxLines = 1, style = Look.sub(11.sp), modifier = GlanceModifier.padding(top = 3.dp))
                    }
                }
            }
        }
    }
}

class KeepReadingReceiver : GlanceAppWidgetReceiver() {
    override val glanceAppWidget = KeepReading()

    override fun onUpdate(context: Context, appWidgetManager: AppWidgetManager, appWidgetIds: IntArray) {
        super.onUpdate(context, appWidgetManager, appWidgetIds)
        Board.refreshIfOlder(context, 10 * 60 * 1000L)
    }
}
