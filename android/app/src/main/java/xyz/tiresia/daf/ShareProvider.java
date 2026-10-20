package xyz.tiresia.daf;

import android.content.ContentProvider;
import android.content.ContentValues;
import android.content.Context;
import android.database.Cursor;
import android.database.MatrixCursor;
import android.net.Uri;
import android.os.ParcelFileDescriptor;
import android.provider.OpenableColumns;
import android.webkit.MimeTypeMap;

import java.io.File;
import java.io.FileNotFoundException;
import java.io.IOException;
import java.util.List;
import java.util.Locale;

/**
 * Hands the share sheet a file (Shell.share: Share as image) from the app's cache:
 * cache/share/<id>/<name>, read-only, and nothing else. A few lines instead of
 * a library for FileProvider.
 */
public final class ShareProvider extends ContentProvider {
    static Uri uriFor(Context c, File file) {
        File dir = file.getParentFile();
        return new Uri.Builder().scheme("content").authority(authority(c))
                .appendPath(dir == null ? "" : dir.getName()).appendPath(file.getName()).build();
    }

    private static String authority(Context c) {
        return c.getPackageName() + ".share";
    }

    private File file(Uri uri) throws FileNotFoundException {
        List<String> seg = uri.getPathSegments();
        if (getContext() == null || seg.size() != 2 || seg.get(0).contains("..") || seg.get(1).contains("..")) {
            throw new FileNotFoundException(String.valueOf(uri));
        }
        File root = new File(getContext().getCacheDir(), "share");
        File f = new File(new File(root, seg.get(0)), seg.get(1));
        try {
            if (!f.getCanonicalPath().startsWith(root.getCanonicalPath() + "/") || !f.isFile()) throw new FileNotFoundException(String.valueOf(uri));
        } catch (IOException e) {
            throw new FileNotFoundException(String.valueOf(uri));
        }
        return f;
    }

    @Override
    public ParcelFileDescriptor openFile(Uri uri, String mode) throws FileNotFoundException {
        if (!"r".equals(mode)) throw new FileNotFoundException("read only");
        return ParcelFileDescriptor.open(file(uri), ParcelFileDescriptor.MODE_READ_ONLY);
    }

    @Override
    public String getType(Uri uri) {
        String name = uri.getLastPathSegment() == null ? "" : uri.getLastPathSegment();
        String ext = name.contains(".") ? name.substring(name.lastIndexOf('.') + 1).toLowerCase(Locale.ROOT) : "";
        String type = MimeTypeMap.getSingleton().getMimeTypeFromExtension(ext);
        return type == null ? "application/octet-stream" : type;
    }

    @Override
    public Cursor query(Uri uri, String[] projection, String selection, String[] args, String sort) {
        MatrixCursor c = new MatrixCursor(new String[]{OpenableColumns.DISPLAY_NAME, OpenableColumns.SIZE});
        try {
            File f = file(uri);
            c.addRow(new Object[]{f.getName(), f.length()});
        } catch (FileNotFoundException ignored) {
            // an empty answer
        }
        return c;
    }

    @Override public boolean onCreate() { return true; }
    @Override public Uri insert(Uri uri, ContentValues values) { return null; }
    @Override public int delete(Uri uri, String selection, String[] args) { return 0; }
    @Override public int update(Uri uri, ContentValues values, String selection, String[] args) { return 0; }
}
