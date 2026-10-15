from __future__ import annotations

import sys
import unittest
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from profile_stats.models import ContributionDay
from profile_stats.momentum import account_momentum
from test_render import momentum_stats


class MomentumTests(unittest.TestCase):
    def test_consecutive_periods_are_date_based_and_exclude_today(self):
        stats = momentum_stats()
        days = list(reversed(stats.public_contribution_days))
        days += [ContributionDay(date(2026, 9, 7), 999), ContributionDay(date(2026, 7, 8), 999)]
        data = account_momentum(replace(stats, public_contribution_days=days))
        self.assertEqual(
            (data.previous.start, data.previous.end), (date(2026, 7, 9), date(2026, 8, 7))
        )
        self.assertEqual(
            (data.current.start, data.current.end), (date(2026, 8, 8), date(2026, 9, 6))
        )
        self.assertEqual((data.previous.total, data.current.total), (60, 90))
        self.assertEqual(data.current.active_days, 30)

    def test_zero_counts_and_active_days(self):
        stats = momentum_stats(previous=0, current=0)
        days = stats.public_contribution_days
        days[-1] = ContributionDay(days[-1].day, 7)
        data = account_momentum(stats)
        self.assertEqual(data.previous.total, 0)
        self.assertEqual(data.current.total, 7)
        self.assertEqual(data.current.active_days, 1)

    def test_missing_dates_do_not_turn_into_zero(self):
        stats = momentum_stats()
        data = account_momentum(
            replace(stats, public_contribution_days=stats.public_contribution_days[1:])
        )
        self.assertIsNone(data.previous.total)
        self.assertEqual(data.previous.observed_days, 29)
        self.assertEqual(data.current.total, 90)
        self.assertIsNone(data.weeks[0].total)
        for days in (None, []):
            data = account_momentum(replace(stats, public_contribution_days=days))
            self.assertIsNone(data.current.total)
            self.assertIsNone(data.current.active_days)
            self.assertTrue(all(week.total is None for week in data.weeks))

    def test_weeks_are_monday_aligned_and_clipped_without_extrapolation(self):
        data = account_momentum(momentum_stats())
        self.assertEqual(data.weeks[0].days, 4)
        self.assertEqual(data.weeks[0].total, 8)
        self.assertEqual(sum(w.days for w in data.weeks), 60)
        self.assertEqual(sum(w.total for w in data.weeks), 150)
        for week in data.weeks[1:]:
            self.assertEqual(week.start.weekday(), 0)
        self.assertEqual(data.weeks[-1].days, 7)
        data = account_momentum(momentum_stats(now=datetime(2026, 9, 9, tzinfo=UTC)))
        self.assertEqual(data.weeks[-1].days, 2)
        self.assertEqual(data.weeks[-1].total, 6)

    def test_year_leap_day_and_timezone_boundaries(self):
        for now in (
            datetime(2026, 1, 1, tzinfo=UTC),
            datetime(2024, 3, 1, tzinfo=UTC),
            datetime(2026, 9, 8, 1, tzinfo=timezone(timedelta(hours=2))),
        ):
            data = account_momentum(momentum_stats(now=now))
            self.assertEqual(data.current.end, now.astimezone(UTC).date() - timedelta(days=1))
            self.assertEqual(data.current.days, 30)
            self.assertEqual(data.previous.days, 30)
            self.assertEqual(sum(w.days for w in data.weeks), 60)
        data = account_momentum(momentum_stats(now=datetime(2024, 3, 1, tzinfo=UTC)))
        self.assertEqual(data.current.end, date(2024, 2, 29))

    def test_invalid_daily_data_is_rejected(self):
        stats = momentum_stats()
        days = stats.public_contribution_days
        for invalid in (days + days[:1], [ContributionDay(days[0].day, -1)]):
            with self.assertRaisesRegex(ValueError, "unique with non-negative"):
                account_momentum(replace(stats, public_contribution_days=invalid))
