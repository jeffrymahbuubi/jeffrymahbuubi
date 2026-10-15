from __future__ import annotations

import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from xml.etree import ElementTree

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from profile_stats.cli import main
from test_render import momentum_stats


class AccountCliTests(unittest.TestCase):
    def render(self, out, config=None, extra=()):
        args = ["--config", str(config)] if config else []
        args += ["account", "--username", "trsdn", "--out", str(out), *extra]
        with (
            patch("profile_stats.cli.GitHubClient"),
            patch(
                "profile_stats.cli.collect_account_stats", return_value=momentum_stats()
            ) as collect,
            patch("builtins.print"),
        ):
            main(args)
        return collect.call_args.kwargs

    def test_defaults_generate_momentum_not_repository_table_in_both_themes(self):
        with TemporaryDirectory() as directory:
            out = Path(directory)
            options = self.render(out)
            expected = {
                f"{name}-card{suffix}.svg"
                for name in ("overview", "activity", "language", "momentum")
                for suffix in ("", "-dark")
            }
            self.assertEqual({path.name for path in out.iterdir()}, expected)
            self.assertTrue(options["include_momentum"])
            for path in out.iterdir():
                ElementTree.fromstring(path.read_text())
            self.assertIn("Change: +30 (+50.0%)", (out / "momentum-card.svg").read_text())

    def test_explicit_legacy_cards_do_not_collect_momentum(self):
        with TemporaryDirectory() as directory:
            config = Path(directory) / "config.yml"
            config.write_text("cards:\n  account:\n    - repos-table\n    - now-building\n")
            out = Path(directory) / "cards"
            options = self.render(out, config=config, extra=("--theme", "dark"))
            self.assertEqual(
                {path.name for path in out.iterdir()},
                {"repos-table-card-dark.svg", "now-building-card-dark.svg"},
            )
            self.assertFalse(options["include_momentum"])

    def test_momentum_stays_public_when_private_repository_option_is_enabled(self):
        with TemporaryDirectory() as directory:
            config = Path(directory) / "config.yml"
            config.write_text("cards:\n  account:\n    - momentum\n")
            out = Path(directory) / "cards"
            options = self.render(
                out, config=config, extra=("--include-private", "--theme", "light")
            )
            self.assertTrue(options["include_private"])
            self.assertEqual({path.name for path in out.iterdir()}, {"momentum-card.svg"})
            self.assertIn("Public contributions", (out / "momentum-card.svg").read_text())

    def test_invalid_selection_fails_before_network_or_writes(self):
        with TemporaryDirectory() as directory:
            config = Path(directory) / "config.yml"
            config.write_text("cards:\n  account:\n    - unknown\n")
            out = Path(directory) / "cards"
            with patch("profile_stats.cli.GitHubClient") as client:
                with self.assertRaisesRegex(ValueError, "unknown account card"):
                    main(["--config", str(config), "account", "--out", str(out)])
                client.assert_not_called()
            self.assertFalse(out.exists())
