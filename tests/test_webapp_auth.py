"""Offline unit tests for the HTTP Basic Auth gate.

No network: `_credentials_ok` is a pure check of an Authorization header against
an expected user/password. These lock in that a correct credential passes and
that the obvious ways to get in without one (missing header, wrong scheme, wrong
user, wrong password, malformed base64) all fail.

    python -m unittest discover -s tests
"""

from __future__ import annotations

import base64
import unittest

from phenofit.webapp import _credentials_ok


def _hdr(user: str, password: str) -> str:
    token = base64.b64encode(f"{user}:{password}".encode()).decode()
    return f"Basic {token}"


class CredentialsTests(unittest.TestCase):
    def test_correct_credentials_pass(self):
        self.assertTrue(_credentials_ok(_hdr("matt", "s3cret"), "matt", "s3cret"))

    def test_wrong_password_fails(self):
        self.assertFalse(_credentials_ok(_hdr("matt", "nope"), "matt", "s3cret"))

    def test_wrong_user_fails(self):
        self.assertFalse(_credentials_ok(_hdr("eve", "s3cret"), "matt", "s3cret"))

    def test_missing_header_fails(self):
        self.assertFalse(_credentials_ok(None, "matt", "s3cret"))

    def test_wrong_scheme_fails(self):
        token = base64.b64encode(b"matt:s3cret").decode()
        self.assertFalse(_credentials_ok(f"Bearer {token}", "matt", "s3cret"))

    def test_malformed_base64_fails(self):
        self.assertFalse(_credentials_ok("Basic not-base64!!", "matt", "s3cret"))

    def test_password_containing_colon(self):
        # Only the first ':' splits user from password, so colons in the password
        # are preserved.
        self.assertTrue(_credentials_ok(_hdr("matt", "a:b:c"), "matt", "a:b:c"))


if __name__ == "__main__":
    unittest.main()
