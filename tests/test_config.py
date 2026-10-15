from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from profile_stats.config import DEFAULT_CONFIG, load_config


class ConfigTests(unittest.TestCase):
    def setUp(self) -> None:
        self.out = Path("out")
        self.out.mkdir(exist_ok=True)

    def tearDown(self) -> None:
        for path in self.out.glob("test-config*.yml"):
            path.unlink(missing_ok=True)
        try:
            self.out.rmdir()
        except OSError:
            pass

    def write_config(self, name: str, text: str) -> Path:
        path = self.out / name
        path.write_text(text)
        return path

    def test_load_config_merges_defaults(self) -> None:
        path = self.write_config(
            "test-config.yml",
            "username: trsdn\ntop_n: 5\nrepo:\n  exclude:\n    - old\n",
        )
        cfg = load_config(path)
        self.assertEqual(cfg["username"], "trsdn")
        self.assertEqual(cfg["top_n"], 5)
        self.assertEqual(cfg["repo"]["exclude"], ["old"])
        self.assertEqual(cfg["cards"]["repo"], ["repo-card"])
        self.assertEqual(cfg["cards"]["account"], ["overview", "activity", "language", "momentum"])

    def test_config_rejects_invalid_top_n(self) -> None:
        path = self.write_config("test-config-invalid.yml", "top_n: 0\n")
        with self.assertRaises(ValueError):
            load_config(path)

    def test_default_config_loads_without_third_party_yaml(self) -> None:
        cfg = load_config("scripts/profile_stats/config.yml")
        self.assertEqual(cfg["cards"]["account"][0], "overview")
        self.assertEqual(cfg["repo"]["include"], [])
        self.assertEqual(cfg["cards"]["account"], DEFAULT_CONFIG["cards"]["account"])
        self.assertNotIn("repos-table", cfg["cards"]["account"])

    def test_optional_cards_and_empty_selection_remain_supported(self) -> None:
        for text, expected in (
            (
                "cards:\n  account:\n    - momentum\n    - repos-table\n    - now-building\n",
                ["momentum", "repos-table", "now-building"],
            ),
            ("cards:\n  account: []\n", []),
        ):
            cfg = load_config(self.write_config("test-config-cards.yml", text))
            self.assertEqual(cfg["cards"]["account"], expected)

    def test_invalid_card_configuration_is_rejected(self) -> None:
        for text, message in (
            ("cards: []\n", "cards.account must be a list"),
            ("cards:\n  account: momentum\n", "cards.account must be a list"),
            ("cards:\n  account:\n    - typo\n", "unknown account card"),
            ("cards:\n  account:\n    - 1\n", "unknown account card"),
            ("cards:\n  account:\n    - momentum\n    - momentum\n", "duplicate names"),
        ):
            with self.subTest(text=text), self.assertRaisesRegex(ValueError, message):
                load_config(self.write_config("test-config-invalid-cards.yml", text))


if __name__ == "__main__":
    unittest.main()
