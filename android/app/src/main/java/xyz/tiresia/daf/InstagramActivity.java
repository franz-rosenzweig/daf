package xyz.tiresia.daf;

import android.app.Activity;
import android.graphics.Insets;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.view.ViewGroup;
import android.view.WindowInsets;
import android.webkit.CookieManager;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.LinearLayout;
import android.widget.TextView;

import java.io.IOException;

/**
 * Sign in to Instagram (Preferences → Instagram, through Shell's "instagram" call): Instagram's own
 * sign-in page in a window of its own. Once Instagram has signed you in (its sessionid cookie), its
 * cookies go to Daf (POST /api/instagram/cookies, daf/social.py) with this device's token, and the
 * window closes. Daf fetches reels with that sign-in.
 *
 * The cookies are never logged, and they're cleared from the app when the window goes, so
 * Instagram's sign-in stays only in Daf.
 */
public class InstagramActivity extends Activity {
    private static final String IG = "https://www.instagram.com";
    private final Handler main = new Handler(Looper.getMainLooper());
    private WebView web;
    private TextView note;
    /** Sending it, or it failed: no more looking until the window opens again. */
    private boolean done;

    /** Instagram signs in with a page of scripts; the cookie is looked for every second. */
    private final Runnable look = new Runnable() {
        @Override
        public void run() {
            if (done || isFinishing()) return;
            check();
            main.postDelayed(this, 1000);
        }
    };

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        LinearLayout box = new LinearLayout(this);
        box.setOrientation(LinearLayout.VERTICAL);
        box.setOnApplyWindowInsetsListener((v, in) -> {
            Insets bars = in.getInsets(WindowInsets.Type.systemBars() | WindowInsets.Type.ime());
            v.setPadding(bars.left, bars.top, bars.right, bars.bottom);
            return WindowInsets.CONSUMED;
        });
        int pad = Math.round(14 * getResources().getDisplayMetrics().density);
        note = new TextView(this);
        note.setPadding(pad, pad, pad, pad);
        note.setText("Sign in as you would on instagram.com. Daf takes the sign-in once you're in.");
        box.addView(note, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT));

        web = new WebView(this);
        WebSettings s = web.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        CookieManager.getInstance().setAcceptCookie(true);
        CookieManager.getInstance().setAcceptThirdPartyCookies(web, true);
        web.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                return false;               // Instagram's own steps (a code, a check) stay in this window
            }

            @Override
            public void onPageFinished(WebView view, String url) {
                check();
            }
        });
        box.addView(web, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 0, 1f));
        setContentView(box);
        web.loadUrl(IG + "/accounts/login/");
        main.postDelayed(look, 1000);
    }

    /** Signed in: the cookies to Daf, then the window closes. */
    private void check() {
        if (done) return;
        String cookies = CookieManager.getInstance().getCookie(IG);
        if (!signedIn(cookies)) return;
        done = true;
        note.setText("Signed in. Sending it to Daf…");
        final android.content.Context app = getApplicationContext();
        new Thread(() -> {
            try {
                Server.instagram(app, cookies);
                main.post(() -> {
                    setResult(RESULT_OK);
                    finish();
                });
            } catch (IOException e) {
                String why = e.getMessage();
                main.post(() -> note.setText(why != null ? why : "Daf didn't take it. Try again in a moment."));
            }
        }, "instagram").start();
    }

    private static boolean signedIn(String cookies) {
        if (cookies == null) return false;
        for (String part : cookies.split(";")) {
            String p = part.trim();
            if (p.startsWith("sessionid=") && p.length() > "sessionid=".length()) return true;
        }
        return false;
    }

    /** Instagram's cookies out of the app: Daf has its own copy. */
    private static void forget() {
        CookieManager cm = CookieManager.getInstance();
        String cookies = cm.getCookie(IG);
        if (cookies == null) return;
        for (String part : cookies.split(";")) {
            int eq = part.indexOf('=');
            if (eq <= 0) continue;
            String name = part.substring(0, eq).trim();
            cm.setCookie(IG, name + "=; Max-Age=0; Path=/; Domain=.instagram.com");
            cm.setCookie(IG, name + "=; Max-Age=0; Path=/");
        }
        cm.flush();
    }

    @Override
    protected void onDestroy() {
        main.removeCallbacks(look);
        if (web != null) {
            web.stopLoading();
            web.destroy();
        }
        forget();
        super.onDestroy();
    }
}
