"""hwrmodel.response: the learned handwriting model at /api/hwr/model (a made-up file, no real model)."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fastapi import HTTPException
from fastapi.responses import FileResponse

from daf import config, hwrmodel


class HwrModel(unittest.TestCase):
    def setUp(self):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.file = Path(d.name) / "personal.bin"
        self.file.write_bytes(b"HWRB" + b"\0" * 60)

    def use(self, value):
        p = mock.patch.object(config, "HWR_MODEL", value)
        p.start()
        self.addCleanup(p.stop)

    def test_none_set_is_404(self):
        self.use("")
        with self.assertRaises(HTTPException) as e:
            hwrmodel.response()
        self.assertEqual(e.exception.status_code, 404)

    def test_missing_file_is_404(self):
        self.use(str(self.file.with_name("gone.bin")))
        with self.assertRaises(HTTPException) as e:
            hwrmodel.response()
        self.assertEqual(e.exception.status_code, 404)

    def test_serves_the_file_with_an_etag_and_no_cache(self):
        self.use(str(self.file))
        r = hwrmodel.response()
        self.assertIsInstance(r, FileResponse)
        self.assertEqual(Path(r.path), self.file)
        self.assertEqual(r.headers["cache-control"], "private, no-cache")
        self.assertEqual(r.headers["etag"], hwrmodel.etag(self.file))

    def test_same_etag_is_304_and_a_new_file_is_not(self):
        self.use(str(self.file))
        tag = hwrmodel.etag(self.file)
        self.assertEqual(hwrmodel.response(f'"other", {tag}').status_code, 304)
        # Learning again replaces the file: a new tag, so the device fetches it again.
        st = self.file.stat()
        os.utime(self.file, ns=(st.st_atime_ns, st.st_mtime_ns + 1_000_000_000))
        self.assertIsInstance(hwrmodel.response(tag), FileResponse)


if __name__ == "__main__":
    unittest.main()
