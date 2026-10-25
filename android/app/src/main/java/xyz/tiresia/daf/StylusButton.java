package xyz.tiresia.daf;

import android.view.MotionEvent;
import android.webkit.WebView;

/**
 * The S Pen's button, for the page (web/pens.js). Android tells the app when it's
 * pressed (BUTTON_STYLUS_PRIMARY on the pen's events), but the WebView doesn't pass
 * that on to the page. So here, as Moshe's app does it (its StylusButton, which
 * this is):
 *
 *  - pressed and let go (a click) with the pen just over the glass, it opens
 *    the page's round pen menu (window.dafStylusButton, at the pen's place);
 *  - held while the pen writes, the stroke goes to the page as the eraser
 *    end's (pointerType "pen", buttons 32), which the page erases with.
 *
 * While the button is down over the glass the pen's events are kept from the
 * page, so it doesn't take them for writing. A page that has no
 * window.dafStylusButton just never hears the button.
 */
final class StylusButton {
    private static final int BUTTONS = MotionEvent.BUTTON_STYLUS_PRIMARY | MotionEvent.BUTTON_STYLUS_SECONDARY;
    private final WebView web;
    private boolean held;               // the button down, over the glass
    private boolean touched;            // and the pen came down while it was: a stroke to erase, not a menu
    private boolean erasing;            // this stroke, from the pen's touch to its lift, is the eraser's
    private float atX, atY;             // where the button was pressed
    private long atTime;                // and when: held longer than a click, it's no menu

    StylusButton(WebView web) {
        this.web = web;
    }

    private static boolean pen(MotionEvent ev) {
        return ev.getPointerCount() > 0 && ev.getToolType(0) == MotionEvent.TOOL_TYPE_STYLUS;
    }

    /** The pen over the glass (a hover, or the button's own press and release). → true when it's been dealt with here. */
    boolean hover(MotionEvent ev) {
        if (!pen(ev)) return false;
        boolean down = (ev.getButtonState() & BUTTONS) != 0;
        if (down && !held) {
            held = true;
            touched = false;
            atX = ev.getX();
            atY = ev.getY();
            atTime = ev.getEventTime();
        } else if (!down && held) {
            held = false;
            if (!touched && ev.getEventTime() - atTime < 1500) menu(atX, atY);
            return true;
        }
        int a = ev.getActionMasked();
        return down || a == MotionEvent.ACTION_BUTTON_PRESS || a == MotionEvent.ACTION_BUTTON_RELEASE;
    }

    /** The pen on the glass. → the event for the page: with the button held as it came down, the eraser end's. */
    MotionEvent touch(MotionEvent ev) {
        if (!pen(ev) && !erasing) return ev;
        int a = ev.getActionMasked();
        if (a == MotionEvent.ACTION_DOWN) {
            erasing = (ev.getButtonState() & BUTTONS) != 0;
            if (erasing) touched = true;
        }
        if (!erasing) return ev;
        MotionEvent out = asEraser(ev);
        if (a == MotionEvent.ACTION_UP || a == MotionEvent.ACTION_CANCEL) erasing = false;
        return out;
    }

    /** The round pen menu, where the pen is (the page's own pixels). */
    private void menu(float x, float y) {
        int[] at = new int[2];
        web.getLocationInWindow(at);
        float d = web.getResources().getDisplayMetrics().density;
        web.evaluateJavascript("window.dafStylusButton && window.dafStylusButton("
                + Math.round((x - at[0]) / d) + ", " + Math.round((y - at[1]) / d) + ")", null);
    }

    /** The same event, every sample of it, as from the pen's eraser end, and without the button. */
    private static MotionEvent asEraser(MotionEvent ev) {
        int n = ev.getPointerCount(), h = ev.getHistorySize();
        MotionEvent.PointerProperties[] props = new MotionEvent.PointerProperties[n];
        MotionEvent.PointerCoords[] coords = new MotionEvent.PointerCoords[n];
        for (int i = 0; i < n; i++) {
            props[i] = new MotionEvent.PointerProperties();
            ev.getPointerProperties(i, props[i]);
            if (props[i].toolType == MotionEvent.TOOL_TYPE_STYLUS) props[i].toolType = MotionEvent.TOOL_TYPE_ERASER;
            coords[i] = new MotionEvent.PointerCoords();
        }
        // the oldest sample first, then the rest added on, as the pen took them
        for (int i = 0; i < n; i++) {
            if (h > 0) ev.getHistoricalPointerCoords(i, 0, coords[i]);
            else ev.getPointerCoords(i, coords[i]);
        }
        MotionEvent out = MotionEvent.obtain(ev.getDownTime(), h > 0 ? ev.getHistoricalEventTime(0) : ev.getEventTime(), ev.getAction(),
                n, props, coords, ev.getMetaState(), ev.getButtonState() & ~BUTTONS, ev.getXPrecision(), ev.getYPrecision(),
                ev.getDeviceId(), ev.getEdgeFlags(), ev.getSource(), ev.getFlags());
        for (int s = 1; s <= h; s++) {
            for (int i = 0; i < n; i++) {
                if (s < h) ev.getHistoricalPointerCoords(i, s, coords[i]);
                else ev.getPointerCoords(i, coords[i]);
            }
            out.addBatch(s < h ? ev.getHistoricalEventTime(s) : ev.getEventTime(), coords, ev.getMetaState());
        }
        return out;
    }
}
