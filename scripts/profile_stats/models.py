"""Dataclasses for collected GitHub statistics."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime


@dataclass(frozen=True)
class LanguageShare:
    name: str
    size: int
    color: str


@dataclass(frozen=True)
class ReleaseStats:
    tag: str | None
    published_at: datetime | None
    asset_downloads: int = 0


@dataclass(frozen=True)
class RepoStats:
    owner: str
    name: str
    full_name: str
    description: str | None
    default_branch: str
    is_private: bool
    stars: int
    forks: int
    watchers: int
    open_issues: int
    open_prs: int
    releases: int
    latest_release: ReleaseStats | None
    commits: int
    last_commit_at: datetime | None
    last_commit_message: str | None
    contributors: int
    primary_language: str | None
    primary_language_color: str | None
    languages: list[LanguageShare]
    language_total: int
    disk_usage_kb: int
    license_name: str | None
    commit_activity: list[int] = field(default_factory=list)
    updated_at: datetime | None = None


@dataclass(frozen=True)
class ContributionDay:
    day: date
    count: int


@dataclass(frozen=True)
class AccountStats:
    username: str
    generated_at: datetime
    repos: list[RepoStats]
    total_commits: int
    total_stars: int
    merged_prs: int
    authored_issues: int
    code_reviews: int
    followers: int
    active_repos: int
    total_repos: int
    contribution_days: list[ContributionDay]
    current_streak: int
    longest_streak: int
    weighted_languages: list[LanguageShare]
    public_contribution_days: list[ContributionDay] | None = None
