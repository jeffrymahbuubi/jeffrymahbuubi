from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import unittest
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from xml.etree import ElementTree

from profile_stats.models import (
    AccountStats,
    ContributionDay,
    LanguageShare,
    ReleaseStats,
    RepoStats,
)
from profile_stats.render.account import (
    render_activity_card,
    render_language_card,
    render_momentum_card,
    render_now_building_card,
    render_overview_card,
    render_repos_table_card,
)
from profile_stats.render.repo import render_repo_card
from profile_stats.render.svg import relative_time, stamp
from profile_stats.render.theme import DARK, LIGHT

# Rough advance width per character, in units of the font size, per CSS class.
# Deliberately generous: the point is to catch content leaving the card, not to
# reproduce a text shaper.
_CHAR_WIDTH = {
    "title": 11.0,
    "subtitle": 6.6,
    "label": 7.8,
    "value": 10.4,
    "small": 6.3,
    "tiny": 5.8,
    "mono": 7.3,
}
_EDGE = 6


def _text_width(node) -> float:
    return len(node.text or "") * _CHAR_WIDTH.get(node.get("class", ""), 7.0)


def repo_stats():
    return RepoStats(
        owner="trsdn",
        name="demo",
        full_name="trsdn/demo",
        description="Demo <repo>",
        default_branch="main",
        is_private=False,
        stars=12,
        forks=3,
        watchers=4,
        open_issues=1,
        open_prs=2,
        releases=1,
        latest_release=ReleaseStats("v1.0.0", datetime(2026, 8, 20, tzinfo=UTC), 5),
        commits=99,
        last_commit_at=datetime(2026, 8, 24, tzinfo=UTC),
        last_commit_message="Fix & ship",
        contributors=4,
        primary_language="Python",
        primary_language_color="#3572A5",
        languages=[LanguageShare("Python", 90, "#3572A5"), LanguageShare("Shell", 10, "#89e051")],
        language_total=100,
        disk_usage_kb=2048,
        license_name="MIT",
        commit_activity=[0, 1, 3] * 18,
        updated_at=datetime(2026, 8, 24, tzinfo=UTC),
    )


def account_stats():
    days = [ContributionDay(datetime(2026, 8, d, tzinfo=UTC).date(), d % 4) for d in range(1, 25)]
    return AccountStats(
        "trsdn",
        datetime(2026, 8, 24, tzinfo=UTC),
        [repo_stats()],
        99,
        12,
        7,
        8,
        9,
        10,
        1,
        3,
        days,
        2,
        8,
        [LanguageShare("Python", 90, "#3572A5")],
    )


def momentum_stats(now=datetime(2026, 9, 7, 12, tzinfo=UTC), previous=2, current=3):
    start = now.astimezone(UTC).date() - timedelta(days=60)
    days = [
        ContributionDay(start + timedelta(days=i), previous if i < 30 else current)
        for i in range(60)
    ]
    return replace(account_stats(), generated_at=now, public_contribution_days=days)


def crowded_account_stats():
    """A worst case: a full table, a full year of days and a full legend.

    The card sizes used to be hard-coded, so the twelfth table row rendered
    below the card and the language column ran past its right edge. Only a
    fixture that fills every card catches that.
    """
    repos = []
    for i in range(12):
        repo = repo_stats()
        repos.append(
            replace(
                repo,
                name=f"repository-with-a-long-name-{i}",
                full_name=f"trsdn/repository-with-a-long-name-{i}",
                primary_language="JavaScript",
                stars=123456,
                commits=98765,
                open_issues=4321,
                latest_release=ReleaseStats("v10.20.30-rc.1", datetime(2026, 8, 20, tzinfo=UTC), 5),
            )
        )
    days = [
        ContributionDay((datetime(2025, 8, 24, tzinfo=UTC) + timedelta(days=i)).date(), i % 13)
        for i in range(371)
    ]
    languages = [LanguageShare(f"LanguageName{i}", 100 - i, "#3572A5") for i in range(14)]
    return AccountStats(
        "trsdn",
        datetime(2026, 8, 29, tzinfo=UTC),
        repos,
        1234567,
        98765,
        4321,
        8765,
        999,
        555,
        66,
        999999,
        days,
        42,
        365,
        languages,
    )


class RenderTests(unittest.TestCase):
    def assert_well_formed(self, svg: str) -> None:
        ElementTree.fromstring(svg)
        self.assertNotIn("<script", svg)
        self.assertNotIn("<foreignObject", svg)

    def assert_content_inside_card(self, svg: str) -> None:
        root = ElementTree.fromstring(svg)
        width, height = int(root.get("width")), int(root.get("height"))
        ns = "{http://www.w3.org/2000/svg}"
        for node in root.iter():
            tag = node.tag.removeprefix(ns)
            if tag == "text":
                x, y = float(node.get("x")), float(node.get("y"))
                w = _text_width(node)
                left, right = (x - w, x) if node.get("text-anchor") == "end" else (x, x + w)
                self.assertGreaterEqual(left, _EDGE, f"text left of card: {node.text!r}")
                self.assertLessEqual(right, width - _EDGE, f"text past right edge: {node.text!r}")
                self.assertLessEqual(y + 4, height - _EDGE, f"text below card: {node.text!r}")
            elif tag in {"rect", "circle"}:
                if tag == "rect":
                    x0, y0 = float(node.get("x")), float(node.get("y"))
                    x1 = x0 + float(node.get("width"))
                    y1 = y0 + float(node.get("height"))
                else:
                    r = float(node.get("r"))
                    x0, x1 = float(node.get("cx")) - r, float(node.get("cx")) + r
                    y0, y1 = float(node.get("cy")) - r, float(node.get("cy")) + r
                self.assertGreaterEqual(min(x0, y0), 0, f"{tag} starts outside the card")
                self.assertLessEqual(x1, width, f"{tag} past right edge")
                self.assertLessEqual(y1, height, f"{tag} past bottom edge")

    def all_cards(self, stats):
        for theme in (LIGHT, DARK):
            yield render_overview_card(stats, theme)
            yield render_activity_card(stats, theme)
            yield render_language_card(stats, theme)
            yield render_momentum_card(stats, theme)
            yield render_repos_table_card(stats, theme)
            yield render_now_building_card(stats, theme)
            yield render_repo_card(repo_stats(), theme, datetime(2026, 8, 24, tzinfo=UTC))

    def test_repo_card_states_missing_commit_activity(self) -> None:
        stats = replace(repo_stats(), commit_activity=[])
        svg = render_repo_card(stats, LIGHT, datetime(2026, 8, 24, tzinfo=UTC))
        self.assertIn("Not available yet", svg)
        self.assert_content_inside_card(svg)
        self.assertNotIn(
            "Not available yet",
            render_repo_card(repo_stats(), LIGHT, datetime(2026, 8, 24, tzinfo=UTC)),
        )

    def test_repo_card_is_well_formed(self) -> None:
        self.assert_well_formed(
            render_repo_card(repo_stats(), LIGHT, datetime(2026, 8, 24, tzinfo=UTC))
        )

    def test_account_cards_are_well_formed(self) -> None:
        stats = account_stats()
        for svg in [
            render_overview_card(stats, LIGHT),
            render_activity_card(stats, LIGHT),
            render_language_card(stats, LIGHT),
            render_momentum_card(stats, LIGHT),
            render_repos_table_card(stats, LIGHT),
            render_now_building_card(stats, LIGHT),
        ]:
            with self.subTest(svg=svg[:40]):
                self.assert_well_formed(svg)

    def test_content_stays_inside_the_card(self) -> None:
        for stats in (account_stats(), crowded_account_stats()):
            for svg in self.all_cards(stats):
                with self.subTest(svg=svg[:60]):
                    self.assert_content_inside_card(svg)

    def test_cards_are_not_animated(self) -> None:
        """A static rasteriser snapshots frame zero.

        Animating opacity or width from zero renders an empty card in
        thumbnails, previews and any non-SMIL renderer.
        """
        for svg in self.all_cards(crowded_account_stats()):
            with self.subTest(svg=svg[:60]):
                self.assertNotIn("<animate", svg)

    def test_momentum_metrics_changes_and_static_theme_variants(self) -> None:
        for previous, current, expected in (
            (2, 3, "Change: +30 (+50.0%)"),
            (2, 1, "Change: -30 (-50.0%)"),
            (2, 0, "Change: -60 (-100.0%)"),
            (2, 2, "Change: +0 (+0.0%)"),
            (0, 1, "Change: +30 (previous period was zero; % undefined)"),
            (0, 0, "Change: 0 (both periods zero; % undefined)"),
            (40000, 50000, "Change: +300,000 (+25.0%)"),
        ):
            for theme in (LIGHT, DARK):
                with self.subTest(previous=previous, current=current, theme=theme.name):
                    svg = render_momentum_card(
                        momentum_stats(previous=previous, current=current), theme
                    )
                    self.assertIn(expected, svg)
                    self.assertIn("2026-08-08 to 2026-09-06", svg)
                    self.assertIn("2026-07-09 to 2026-08-07", svg)
                    self.assertIn(theme.accent, svg)
                    self.assertIn("partial week", svg)
                    self.assertIn("today excluded", svg)
                    self.assert_well_formed(svg)
                    self.assert_content_inside_card(svg)
                    for unsafe in ("<animate", "<script", "<foreignObject", "<image", "href="):
                        self.assertNotIn(unsafe, svg)

    def test_momentum_gaps_are_not_plotted_as_zero_or_bridged(self) -> None:
        stats = momentum_stats()
        days = [d for i, d in enumerate(stats.public_contribution_days) if i != 20]
        svg = render_momentum_card(replace(stats, public_contribution_days=days), LIGHT)
        self.assertIn("Change unavailable", svg)
        self.assertIn("30/30 recent days, 29/30 previous days", svg)
        self.assertIn(">N/A", svg)
        self.assertEqual(svg.count("<polyline"), 2)
        self.assert_content_inside_card(svg)
        for days in (None, []):
            svg = render_momentum_card(replace(stats, public_contribution_days=days), LIGHT)
            self.assertIn("0/30 recent days, 0/30 previous days", svg)
            self.assertNotIn("<polyline", svg)
            self.assertNotIn("<circle", svg)
            self.assert_content_inside_card(svg)

    def test_overview_reports_sources_and_total_repositories(self) -> None:
        """Forks are excluded from the cards but not from GitHub's own count.

        Showing only the source count made the card look wrong next to the
        number GitHub prints on the profile page.
        """
        svg = render_overview_card(account_stats(), LIGHT)
        self.assertIn(">1 / 3<", svg)
        self.assertIn("the difference is forks", svg)

    def test_overview_omits_the_total_when_there_are_no_forks(self) -> None:
        svg = render_overview_card(replace(account_stats(), total_repos=1), LIGHT)
        self.assertIn('class="value">1<', svg)
        self.assertNotIn(">1 / ", svg)

    def test_relative_minutes_are_not_confusable_with_months(self) -> None:
        now = datetime(2026, 8, 24, 12, 0, tzinfo=UTC)
        self.assertEqual(relative_time(now - timedelta(minutes=5), now), "5min ago")
        self.assertEqual(relative_time(now - timedelta(days=60), now), "2mo ago")

    def test_generated_stamp_is_minute_precision_utc(self) -> None:
        self.assertEqual(
            stamp(datetime(2026, 8, 25, 5, 57, 18, tzinfo=UTC)), "2026-08-25 05:57 UTC"
        )


if __name__ == "__main__":
    unittest.main()
