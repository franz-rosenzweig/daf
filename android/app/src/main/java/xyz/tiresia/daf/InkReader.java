package xyz.tiresia.daf;

import android.webkit.WebView;

import com.google.mlkit.common.MlKitException;
import com.google.mlkit.common.model.DownloadConditions;
import com.google.mlkit.common.model.RemoteModelManager;
import com.google.mlkit.vision.digitalink.DigitalInkRecognition;
import com.google.mlkit.vision.digitalink.DigitalInkRecognitionModel;
import com.google.mlkit.vision.digitalink.DigitalInkRecognitionModelIdentifier;
import com.google.mlkit.vision.digitalink.DigitalInkRecognizer;
import com.google.mlkit.vision.digitalink.DigitalInkRecognizerOptions;
import com.google.mlkit.vision.digitalink.Ink;

import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;

import java.util.HashMap;
import java.util.Map;

/**
 * Handwriting read as text by Google's ML Kit Digital Ink Recognition, on the device, for the
 * languages Grape (the page's own reader, pens.js) doesn't know: Hebrew. The page sends a line of
 * strokes at a time over the message port (Shell.java's "ink") and hears back there. A language's
 * reader is fetched from Google once (about 20 MB), and window.__dafInkStatus says so meanwhile;
 * after that it works offline. Moshe's InkReader, answering over Daf's port.
 *
 * ML Kit isn't free software: Daf's licence lets the Android app be combined with it (an
 * additional permission under the GPL's section 7, in README.md).
 */
final class InkReader {
    interface Answer {
        void text(String text, String error);
    }

    private final WebView web;
    private final Map<String, DigitalInkRecognizer> readers = new HashMap<>();

    InkReader(WebView web) {
        this.web = web;
    }

    /** Whether a language can be read here at all (it may still have to be fetched). */
    boolean has(String lang) {
        return model(lang) != null;
    }

    /** Read one line: strokes as [[[x, y], …], …], in the page's pixels. */
    void read(String lang, String strokes, Answer answer) {
        DigitalInkRecognitionModel model = model(lang);
        if (model == null) { answer.text(null, "this device can't read " + lang); return; }
        Ink ink;
        try {
            ink = inkOf(new JSONArray(strokes));
        } catch (JSONException e) {
            answer.text(null, "the strokes didn't arrive whole");
            return;
        }
        RemoteModelManager models = RemoteModelManager.getInstance();
        models.isModelDownloaded(model).addOnSuccessListener(have -> {
            if (have) { recognize(lang, model, ink, answer); return; }
            status("Getting the reader for this language from Google, once (about 20 MB)…");
            models.download(model, new DownloadConditions.Builder().build())
                    .addOnSuccessListener(v -> recognize(lang, model, ink, answer))
                    .addOnFailureListener(e -> answer.text(null, "its reader couldn't be fetched: " + e.getMessage()));
        }).addOnFailureListener(e -> answer.text(null, e.getMessage()));
    }

    private void recognize(String lang, DigitalInkRecognitionModel model, Ink ink, Answer answer) {
        DigitalInkRecognizer reader = readers.get(lang);
        if (reader == null) {
            reader = DigitalInkRecognition.getClient(DigitalInkRecognizerOptions.builder(model).build());
            readers.put(lang, reader);
        }
        reader.recognize(ink)
                .addOnSuccessListener(result -> answer.text(result.getCandidates().isEmpty() ? "" : result.getCandidates().get(0).getText(), null))
                .addOnFailureListener(e -> answer.text(null, e.getMessage()));
    }

    private static DigitalInkRecognitionModel model(String lang) {
        try {
            DigitalInkRecognitionModelIdentifier which = DigitalInkRecognitionModelIdentifier.fromLanguageTag(lang);
            return which == null ? null : DigitalInkRecognitionModel.builder(which).build();
        } catch (MlKitException e) {
            return null;
        }
    }

    private static Ink inkOf(JSONArray strokes) throws JSONException {
        Ink.Builder ink = Ink.builder();
        for (int i = 0; i < strokes.length(); i++) {
            JSONArray pts = strokes.getJSONArray(i);
            Ink.Stroke.Builder stroke = Ink.Stroke.builder();
            for (int j = 0; j < pts.length(); j++) {
                JSONArray p = pts.getJSONArray(j);
                stroke.addPoint(Ink.Point.create((float) p.getDouble(0), (float) p.getDouble(1)));
            }
            ink.addStroke(stroke.build());
        }
        return ink.build();
    }

    private void status(String text) {
        web.post(() -> web.evaluateJavascript("window.__dafInkStatus && window.__dafInkStatus(" + JSONObject.quote(text) + ")", null));
    }
}
