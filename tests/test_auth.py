"""Sign-in cookies (auth.py): with no secret in auth.json no cookie is valid, so an install that has no
password yet can't be entered with a cookie signed under a key anyone could guess."""
import base64
import hashlib
import hmac
import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).parent
os.environ.setdefault("DAF_STATE", str(HERE / "state-unused"))   # importing daf never touches the real state

from daf import auth, config  # noqa: E402


def forged(key=b"\x00"):
    payload = base64.urlsafe_b64encode(json.dumps({"exp": int(time.time()) + 3600}).encode())
    return payload.decode() + "." + hmac.new(key, payload, hashlib.sha256).hexdigest()


class Secret(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        state = Path(self.tmp.name)
        self.p = [mock.patch.object(config, "STATE", state), mock.patch.object(config, "AUTH_PATH", state / "auth.json")]
        for p in self.p:
            p.start()

    def tearDown(self):
        for p in self.p:
            p.stop()
        self.tmp.cleanup()

    def write(self, text):
        config.AUTH_PATH.write_text(text)

    def test_no_secret_no_cookie(self):
        for state in (None, "{}", '{"user": "owner"}', '{"secret": ""}', "not json", '{"secret": "zz"}'):
            if state is None:
                config.AUTH_PATH.unlink(missing_ok=True)
            else:
                self.write(state)
            self.assertFalse(auth.check_cookie(forged()), state)
            self.assertFalse(auth.check_cookie(forged(b"")), state)
            with self.assertRaises(RuntimeError):
                auth.make_cookie()

    def test_with_a_password(self):
        auth.set_password("a long test password")
        good = auth.make_cookie()
        self.assertTrue(auth.check_cookie(good))
        self.assertFalse(auth.check_cookie(forged()))
        self.assertFalse(auth.check_cookie(good[:-1] + ("0" if good[-1] != "0" else "1")))
        self.assertFalse(auth.check_cookie(good.split(".")[0] + ".ünicode"))   # no 500 on odd bytes
        auth.sign_out_everywhere()
        self.assertFalse(auth.check_cookie(good))

    def test_set_user_makes_a_secret(self):
        auth.set_user("Owner")
        self.assertTrue(json.loads(config.AUTH_PATH.read_text()).get("secret"))
        self.assertFalse(auth.check_cookie(forged()))
        self.assertEqual(auth.username(), "owner")


if __name__ == "__main__":
    unittest.main()
