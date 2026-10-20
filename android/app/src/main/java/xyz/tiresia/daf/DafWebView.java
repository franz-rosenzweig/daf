package xyz.tiresia.daf;

import android.content.Context;
import android.graphics.Rect;
import android.view.ActionMode;
import android.view.Menu;
import android.view.MenuItem;
import android.view.View;
import android.webkit.WebView;

/**
 * The window's WebView, with one difference: while the page says it has a text menu of its own
 * (Shell's "reading" op: an article or a book open, nothing editable in focus), Android's floating
 * text menu (Copy, Select all, Share…) comes up empty, so it doesn't sit on top of Daf's highlight
 * bar. The selection and its handles stay; a note box or a tag field keeps Android's menu.
 */
final class DafWebView extends WebView {
    private boolean ownMenu;
    private ActionMode mode;

    DafWebView(Context c) {
        super(c);
    }

    /** The page's own menu stands in for Android's (true), or not. */
    void ownMenu(boolean on) {
        if (on == ownMenu) return;
        ownMenu = on;
        if (mode != null) mode.invalidate();           // a menu that's up already: emptied (or left) at once
    }

    @Override
    public ActionMode startActionMode(ActionMode.Callback callback) {
        return startActionMode(callback, ActionMode.TYPE_PRIMARY);
    }

    @Override
    public ActionMode startActionMode(ActionMode.Callback callback, int type) {
        mode = super.startActionMode(new Quiet(callback), type);
        return mode;
    }

    /** Android's callback, with its menu emptied while the page has its own. */
    private final class Quiet extends ActionMode.Callback2 {
        private final ActionMode.Callback inner;

        Quiet(ActionMode.Callback inner) {
            this.inner = inner;
        }

        @Override
        public boolean onCreateActionMode(ActionMode m, Menu menu) {
            boolean shown = inner.onCreateActionMode(m, menu);
            if (ownMenu) menu.clear();
            return shown;
        }

        @Override
        public boolean onPrepareActionMode(ActionMode m, Menu menu) {
            boolean changed = inner.onPrepareActionMode(m, menu);
            if (ownMenu && menu.size() > 0) { menu.clear(); return true; }
            return changed;
        }

        @Override
        public boolean onActionItemClicked(ActionMode m, MenuItem item) {
            return inner.onActionItemClicked(m, item);
        }

        @Override
        public void onDestroyActionMode(ActionMode m) {
            inner.onDestroyActionMode(m);
            if (mode == m) mode = null;
        }

        @Override
        public void onGetContentRect(ActionMode m, View view, Rect outRect) {
            if (inner instanceof ActionMode.Callback2) ((ActionMode.Callback2) inner).onGetContentRect(m, view, outRect);
            else super.onGetContentRect(m, view, outRect);
        }
    }
}
