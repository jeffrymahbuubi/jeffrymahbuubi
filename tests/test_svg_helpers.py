from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import unittest
from datetime import UTC, datetime, timedelta
from xml.etree import ElementTree

from profile_stats.render.svg import esc, n, relative_time, svg_root, truncate


class SvgHelperTests(unittest.TestCase):
    def test_escapes_xml_and_strips_control_characters(self) -> None:
        self.assertEqual(esc('A&B <tag> "quote" \x01'), "A&amp;B &lt;tag&gt; &quot;quote&quot; ")

    def test_truncate_is_unicode_safe(self) -> None:
        self.assertEqual(truncate("abcdef", 4), "abc…")
        self.assertEqual(truncate("åß∂ƒ", 3), "åß…")

    def test_number_formatting(self) -> None:
        self.assertEqual(n(999), "999")
        self.assertEqual(n(1200), "1.2k")
        self.assertEqual(n(12_500), "12k")
        self.assertEqual(n(1_200_000), "1.2m")

    def test_relative_time(self) -> None:
        now = datetime(2026, 8, 24, tzinfo=UTC)
        self.assertEqual(relative_time(now - timedelta(days=3), now), "3d ago")
        self.assertEqual(relative_time(now, now), "just now")

    def test_svg_root_is_well_formed(self) -> None:
        ElementTree.fromstring(svg_root(10, 10, "<text>A&amp;B</text>"))


if __name__ == "__main__":
    unittest.main()
