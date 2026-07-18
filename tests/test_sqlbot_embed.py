from __future__ import annotations

import os
import unittest
from unittest.mock import patch

import jwt

from backend.api.sqlbot import get_sqlbot_embed_token


class SqlBotEmbedTokenTest(unittest.TestCase):
    def test_token_is_short_lived_and_secret_is_not_returned(self) -> None:
        settings = {
            "SQLBOT_BASE_URL": "http://localhost:8080",
            "SQLBOT_APP_ID": "app-test",
            "SQLBOT_APP_SECRET": "test-secret-at-least-32-bytes-long",
            "SQLBOT_EMBED_ACCOUNT": "receivables-internal",
            "SQLBOT_EMBEDDED_ID": "42",
        }
        with patch.dict(os.environ, settings):
            result = get_sqlbot_embed_token()

        payload = jwt.decode(
            result["token"],
            "test-secret-at-least-32-bytes-long",
            algorithms=["HS256"],
        )
        self.assertEqual(payload["appId"], "app-test")
        self.assertEqual(payload["embeddedId"], 42)
        self.assertEqual(payload["account"], "receivables-internal")
        self.assertNotIn("appSecret", result)
        self.assertLessEqual(result["expiresAt"] - int(__import__("time").time()), 300)


if __name__ == "__main__":
    unittest.main()
