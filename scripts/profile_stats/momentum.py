"""Date-based Momentum metrics for consecutive, completed UTC days."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, timedelta

from .models import AccountStats


@dataclass(frozen=True)
class ContributionPeriod:
    start: date
    end: date
    total: int | None
    active_days: int | None
    observed_days: int

    @property
    def days(self) -> int:
        return (self.end - self.start).days + 1


@dataclass(frozen=True)
class Momentum:
    previous: ContributionPeriod
    current: ContributionPeriod
    weeks: list[ContributionPeriod]


def account_momentum(stats: AccountStats) -> Momentum:
    end = stats.generated_at.astimezone(UTC).date() - timedelta(days=1)
    start = end - timedelta(days=59)
    counts: dict[date, int] = {}
    for item in stats.public_contribution_days or []:
        if not start <= item.day <= end:
            continue
        if item.day in counts or item.count < 0:
            raise ValueError("public contribution days must be unique with non-negative counts")
        counts[item.day] = item.count

    def period(first: date, last: date) -> ContributionPeriod:
        values = [
            counts[first + timedelta(days=i)]
            for i in range((last - first).days + 1)
            if first + timedelta(days=i) in counts
        ]
        complete = len(values) == (last - first).days + 1
        return ContributionPeriod(
            first,
            last,
            sum(values) if complete else None,
            sum(value > 0 for value in values) if complete else None,
            len(values),
        )

    weeks = []
    first = start
    while first <= end:
        last = min(first + timedelta(days=6 - first.weekday()), end)
        weeks.append(period(first, last))
        first = last + timedelta(days=1)
    return Momentum(
        period(start, start + timedelta(days=29)),
        period(start + timedelta(days=30), end),
        weeks,
    )
