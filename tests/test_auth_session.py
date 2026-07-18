from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from backend.auth.session import sign_session, verify_session


class AuthSessionTest(unittest.TestCase):
    def test_signed_session_round_trip_and_tamper(self) -> None:
        with patch.dict(os.environ, {"APP_SESSION_SECRET": "test-secret", "SESSION_TTL_SECONDS": "600"}):
            token = sign_session({"userid": "u1", "name": "张三"}, now=1000)
            self.assertEqual(verify_session(token, now=1200)["userid"], "u1")
            self.assertIsNone(verify_session(token + "x", now=1200))

    def test_expired_session_is_rejected(self) -> None:
        with patch.dict(os.environ, {"APP_SESSION_SECRET": "test-secret", "SESSION_TTL_SECONDS": "300"}):
            token = sign_session({"userid": "u1", "name": "张三"}, now=1000)
            self.assertIsNone(verify_session(token, now=1301))


if __name__ == "__main__":
    unittest.main()
