package xyz.tiresia.daf

import android.content.Context
import android.graphics.Bitmap
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.TextUnit
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.glance.ColorFilter
import androidx.glance.GlanceModifier
import androidx.glance.GlanceTheme
import androidx.glance.Image
import androidx.glance.ImageProvider
import androidx.glance.action.Action
import androidx.glance.action.clickable
import androidx.glance.appwidget.LinearProgressIndicator
import androidx.glance.appwidget.action.actionStartActivity
import androidx.glance.appwidget.appWidgetBackground
import androidx.glance.appwidget.cornerRadius
import androidx.glance.background
import androidx.glance.layout.Alignment
import androidx.glance.layout.Box
import androidx.glance.layout.Column
import androidx.glance.layout.ColumnScope
import androidx.glance.layout.ContentScale
import androidx.glance.layout.fillMaxSize
import androidx.glance.layout.fillMaxWidth
import androidx.glance.layout.height
import androidx.glance.layout.padding
import androidx.glance.layout.size
import androidx.glance.text.FontFamily
import androidx.glance.text.FontWeight
import androidx.glance.text.Text
import androidx.glance.text.TextAlign
import androidx.glance.text.TextDecoration
import androidx.glance.text.TextStyle
import androidx.glance.unit.ColorProvider

/** What every widget shares: the frame, a cover, the progress line, the words. Material You's colours, light or dark as the phone is. */
object Look {
    /** The widget's own rounded background, the launcher's corner radius. */
    @Composable
    fun Frame(modifier: GlanceModifier = GlanceModifier, pad: Dp = 12.dp, content: @Composable ColumnScope.() -> Unit) {
        Column(
            modifier = modifier.fillMaxSize().appWidgetBackground().background(GlanceTheme.colors.widgetBackground)
                .cornerRadius(android.R.dimen.system_app_widget_background_radius).padding(pad),
            content = content,
        )
    }

    /** A book's cover or a piece's picture, cropped to its box; a quiet block when there's none. */
    @Composable
    fun Picture(bitmap: Bitmap?, w: Dp, h: Dp, radius: Dp = 6.dp, modifier: GlanceModifier = GlanceModifier, letter: String? = null) {
        if (bitmap != null) {
            Image(ImageProvider(bitmap), contentDescription = null, contentScale = ContentScale.Crop,
                modifier = modifier.size(w, h).cornerRadius(radius))
        } else {
            Box(modifier.size(w, h).cornerRadius(radius).background(GlanceTheme.colors.secondaryContainer), contentAlignment = Alignment.Center) {
                if (!letter.isNullOrBlank() && w >= 36.dp) {
                    Text(letter, maxLines = 3, style = TextStyle(color = GlanceTheme.colors.onSecondaryContainer, fontSize = 10.sp,
                        fontFamily = FontFamily.Serif, textAlign = TextAlign.Center), modifier = GlanceModifier.padding(4.dp))
                }
            }
        }
    }

    @Composable
    fun Bar(fraction: Float, modifier: GlanceModifier = GlanceModifier.fillMaxWidth()) {
        LinearProgressIndicator(progress = fraction.coerceIn(0f, 1f), modifier = modifier.height(4.dp).cornerRadius(2.dp),
            color = GlanceTheme.colors.primary, backgroundColor = GlanceTheme.colors.secondaryContainer)
    }

    @Composable
    fun title(size: TextUnit = 14.sp, done: Boolean = false, serif: Boolean = false, color: ColorProvider? = null) = TextStyle(
        color = color ?: GlanceTheme.colors.onSurface, fontSize = size, fontWeight = FontWeight.Medium,
        fontFamily = if (serif) FontFamily.Serif else null, textDecoration = if (done) TextDecoration.LineThrough else null)

    @Composable
    fun sub(size: TextUnit = 12.sp, color: ColorProvider? = null) =
        TextStyle(color = color ?: GlanceTheme.colors.onSurfaceVariant, fontSize = size)

    @Composable
    fun Icon(res: Int, label: String?, size: Dp = 20.dp, color: ColorProvider = GlanceTheme.colors.onSurfaceVariant, modifier: GlanceModifier = GlanceModifier) {
        Image(ImageProvider(res), contentDescription = label, colorFilter = ColorFilter.tint(color), modifier = modifier.size(size))
    }

    /** Nothing to show: a label in the middle (and the whole widget opens Daf). */
    @Composable
    fun Empty(text: String, open: Action) {
        Frame(GlanceModifier.clickable(open)) {
            Box(GlanceModifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                Text(text, style = sub(13.sp).copy(textAlign = TextAlign.Center))
            }
        }
    }

    fun go(c: Context, route: String?, command: String? = null): Action = actionStartActivity(Board.open(c, route, command))

    val White = ColorProvider(Color.White)
    val Shade = ColorProvider(Color(0x99000000))
}
