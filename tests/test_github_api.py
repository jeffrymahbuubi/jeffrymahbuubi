from __future__ import annotations

import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from profile_stats.github_api import GitHubClient


class _FakeSession:
    def __init__(self):
        self.headers = {}


def fake_requests():
    # Session construction never touches the network; a stub keeps the test
    # independent of whether requests is installed.
    return patch.dict(sys.modules, {"requests": types.SimpleNamespace(Session=_FakeSession)})


class TokenTests(unittest.TestCase):
    def test_github_token_alone_is_not_a_fallback(self):
        with patch.dict("os.environ", {"GITHUB_TOKEN": "ghs_other"}, clear=True):
            with self.assertRaisesRegex(Exception, "STATS_TOKEN"):
                GitHubClient()

    def test_empty_stats_token_counts_as_unset(self):
        with patch.dict("os.environ", {"STATS_TOKEN": "", "GITHUB_TOKEN": "x"}, clear=True):
            with self.assertRaisesRegex(Exception, "STATS_TOKEN"):
                GitHubClient()

    def test_stats_token_is_sent_as_bearer(self):
        with patch.dict("os.environ", {"STATS_TOKEN": "tok123"}, clear=True), fake_requests():
            client = GitHubClient()
        self.assertEqual(client.session.headers["Authorization"], "Bearer tok123")
        self.assertEqual(client.session.headers["User-Agent"], "jeffrymahbuubi-profile-stats")

    def test_explicit_token_is_used(self):
        with patch.dict("os.environ", {}, clear=True), fake_requests():
            client = GitHubClient("explicit")
        self.assertEqual(client.session.headers["Authorization"], "Bearer explicit")


if __name__ == "__main__":
    unittest.main()
