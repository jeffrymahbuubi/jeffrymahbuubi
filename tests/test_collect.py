from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import unittest
from datetime import UTC, date, datetime, timedelta
from unittest.mock import patch

from profile_stats.collect import (
    _collect_public_contribution_days,
    collect_account_stats,
    collect_repo_stats,
)
from profile_stats.models import ContributionDay


class FakeClient:
    def graphql(self, query, variables):
        if "query PublicContributions(" in query:
            return {
                "user": {
                    "contributionsCollection": {
                        "totalRepositoriesWithContributedCommits": 0,
                        "commitContributionsByRepository": [],
                    }
                }
            }
        if "query PublicContributionPage(" in query:
            field = next(
                field
                for field in (
                    "issueContributions",
                    "pullRequestContributions",
                    "pullRequestReviewContributions",
                    "repositoryContributions",
                )
                if f"{field}(" in query
            )
            return {
                "user": {
                    "contributionsCollection": {
                        field: {"nodes": [], "pageInfo": {"hasNextPage": False, "endCursor": None}},
                    }
                }
            }
        if "RepoStats" in query:
            return {"repository": repo_node("trsdn/OpenLens")}
        if "AccountProfile" in query:
            return {
                "user": {
                    "login": "trsdn",
                    "followers": {"totalCount": 7},
                    "contributionsCollection": {
                        "contributionCalendar": {
                            "weeks": [
                                {
                                    "contributionDays": [
                                        {"date": "2026-08-21", "contributionCount": 1},
                                        {"date": "2026-08-22", "contributionCount": 0},
                                        {"date": "2026-08-23", "contributionCount": 2},
                                        {"date": "2026-08-24", "contributionCount": 3},
                                    ]
                                }
                            ]
                        }
                    },
                }
            }
        return {
            "user": {
                "repositories": {
                    "pageInfo": {"hasNextPage": False, "endCursor": None},
                    "nodes": [repo_node("trsdn/OpenLens"), repo_node("trsdn/fork", is_fork=True)],
                }
            }
        }

    def count_paginated(self, path, params=None):
        return 3

    def stats_commit_activity(self, owner, repo):
        return [0, 1, 2]

    def search_count(self, query):
        return 4


def repo_node(full_name, is_fork=False):
    owner, name = full_name.split("/")
    return {
        "name": name,
        "nameWithOwner": full_name,
        "description": "Example & repo",
        "isPrivate": False,
        "isFork": is_fork,
        "isArchived": False,
        "stargazerCount": 5,
        "forkCount": 2,
        "diskUsage": 123,
        "updatedAt": "2026-08-24T10:00:00Z",
        "watchers": {"totalCount": 1},
        "issues": {"totalCount": 6},
        "pullRequests": {"totalCount": 1},
        "releases": {"totalCount": 2},
        "latestRelease": {
            "tagName": "v1.0.0",
            "publishedAt": "2026-08-20T00:00:00Z",
            "releaseAssets": {"nodes": [{"downloadCount": 9}]},
        },
        "licenseInfo": {"name": "MIT License", "spdxId": "MIT"},
        "primaryLanguage": {"name": "Python", "color": "#3572A5"},
        "languages": {
            "totalSize": 100,
            "edges": [
                {"size": 80, "node": {"name": "Python", "color": "#3572A5"}},
                {"size": 20, "node": {"name": "Shell", "color": "#89e051"}},
            ],
        },
        "defaultBranchRef": {
            "name": "main",
            "target": {
                "history": {
                    "totalCount": 42,
                    "nodes": [
                        {
                            "committedDate": "2026-08-24T09:00:00Z",
                            "messageHeadline": "Update <stats>",
                        }
                    ],
                }
            },
        },
        "owner": {"login": owner},
    }


class CollectTests(unittest.TestCase):
    def test_collect_repo_stats_maps_fields(self) -> None:
        stats = collect_repo_stats(FakeClient(), "trsdn/OpenLens")
        self.assertEqual(stats.full_name, "trsdn/OpenLens")
        self.assertEqual(stats.commits, 42)
        self.assertEqual(stats.contributors, 3)
        self.assertEqual(stats.latest_release.asset_downloads, 9)
        self.assertEqual(stats.commit_activity, [0, 1, 2])

    def test_collect_account_stats_filters_forks_and_builds_language_weights(self) -> None:
        stats = collect_account_stats(FakeClient(), "trsdn")
        self.assertEqual(len(stats.repos), 1)
        self.assertEqual(stats.total_commits, 42)
        self.assertEqual(stats.total_stars, 5)
        self.assertEqual(stats.followers, 7)
        self.assertEqual(stats.current_streak, 2)
        self.assertEqual(stats.longest_streak, 2)
        self.assertEqual(stats.weighted_languages[0].name, "Python")

    def test_profile_range_fits_github_limit_and_momentum_can_be_disabled(self):
        calls = []

        class Client(FakeClient):
            def graphql(self, query, variables):
                calls.append((query, variables))
                return super().graphql(query, variables)

        stats = collect_account_stats(Client(), "trsdn", include_momentum=False)
        self.assertIsNone(stats.public_contribution_days)
        self.assertFalse(any("query PublicContribution" in query for query, _ in calls))
        variables = next(variables for query, variables in calls if "AccountProfile" in query)
        start, end = (
            datetime.fromisoformat(variables["from"]),
            datetime.fromisoformat(variables["to"]),
        )
        self.assertLessEqual(end - start, timedelta(days=365))
        self.assertEqual((start.hour, start.minute, start.second, start.microsecond), (0, 0, 0, 0))


class PublicContributionTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 9, 7, 21, 0, tzinfo=UTC)
        self.days = [ContributionDay(date(2026, 7, 9) + timedelta(days=i), 9999) for i in range(61)]

    def test_public_counts_exclude_private_internal_and_restricted_and_paginate(self):
        calls = []

        class Client(FakeClient):
            def graphql(self, query, variables):
                calls.append((query, variables))
                if "query PublicContributions(" in query:
                    groups = []
                    for visibility in ("PUBLIC", "PRIVATE", "INTERNAL"):
                        groups.append(
                            {
                                "repository": {"visibility": visibility},
                                "contributions": {
                                    "pageInfo": {"hasNextPage": False},
                                    "nodes": [
                                        {
                                            "occurredAt": "2026-09-06T00:00:00Z",
                                            "commitCount": 4,
                                            "isRestricted": False,
                                        },
                                        {
                                            "occurredAt": "2026-09-06T00:00:00Z",
                                            "commitCount": 500,
                                            "isRestricted": True,
                                        },
                                        {
                                            "occurredAt": "2026-09-07T00:00:00Z",
                                            "commitCount": 900,
                                            "isRestricted": False,
                                        },
                                    ],
                                },
                            }
                        )
                    return {
                        "user": {
                            "contributionsCollection": {
                                "totalRepositoriesWithContributedCommits": 3,
                                "commitContributionsByRepository": groups,
                            }
                        }
                    }
                response = super().graphql(query, variables)
                field, page = next(iter(response["user"]["contributionsCollection"].items()))
                nodes = []
                for visibility in ("PUBLIC", "PRIVATE", "INTERNAL"):
                    node = {"occurredAt": "2026-09-06T01:00:00Z", "isRestricted": False}
                    resource = {"repository": {"visibility": visibility}}
                    if field == "issueContributions":
                        node["issue"] = resource
                    elif field == "pullRequestContributions":
                        node["pullRequest"] = resource
                    else:
                        node.update(resource)
                    nodes.append(node)
                nodes.append({"isRestricted": True})
                page["nodes"] = nodes
                if field == "issueContributions" and variables["cursor"] is None:
                    page["pageInfo"] = {"hasNextPage": True, "endCursor": "next"}
                return response

        days = _collect_public_contribution_days(Client(), "trsdn", self.now, self.days)
        self.assertEqual(len(days), 60)
        self.assertEqual(sum(d.count for d in days), 9)
        self.assertEqual(days[-1], ContributionDay(date(2026, 9, 6), 9))
        self.assertEqual(days[0].count, 0)
        self.assertEqual(len(calls), 6)
        for query, variables in calls:
            self.assertEqual(variables["from"], "2026-07-09T00:00:00+00:00")
            self.assertEqual(variables["to"], "2026-09-06T23:59:59+00:00")
            self.assertIn("visibility", query)

    def test_missing_calendar_dates_are_not_filled_with_zero(self):
        days = _collect_public_contribution_days(FakeClient(), "trsdn", self.now, self.days[1:])
        self.assertEqual(len(days), 59)
        self.assertNotIn(date(2026, 7, 9), [d.day for d in days])
        self.assertEqual(_collect_public_contribution_days(FakeClient(), "trsdn", self.now, []), [])

    def test_truncated_commit_repositories_or_days_are_unavailable(self):
        for extra_repo, extra_page in ((True, False), (False, True)):

            class Client(FakeClient):
                def graphql(self, query, variables, extra_repo=extra_repo, extra_page=extra_page):
                    return {
                        "user": {
                            "contributionsCollection": {
                                "totalRepositoriesWithContributedCommits": 2 if extra_repo else 1,
                                "commitContributionsByRepository": [
                                    {
                                        "repository": {"visibility": "PUBLIC"},
                                        "contributions": {
                                            "pageInfo": {"hasNextPage": extra_page},
                                            "nodes": [],
                                        },
                                    }
                                ],
                            }
                        }
                    }

            with self.subTest(extra_repo=extra_repo), self.assertLogs(level="WARNING"):
                self.assertIsNone(
                    _collect_public_contribution_days(Client(), "trsdn", self.now, self.days)
                )

    def test_nonadvancing_pagination_fails_explicitly(self):
        class Client(FakeClient):
            def graphql(self, query, variables):
                response = super().graphql(query, variables)
                if "query PublicContributionPage(" in query:
                    page = next(iter(response["user"]["contributionsCollection"].values()))
                    page["pageInfo"] = {"hasNextPage": True, "endCursor": None}
                return response

        with self.assertRaisesRegex(ValueError, "pagination did not advance"):
            _collect_public_contribution_days(Client(), "trsdn", self.now, self.days)

    def test_api_errors_are_not_replaced_with_zero_activity(self):
        client = FakeClient()
        with patch.object(client, "graphql", side_effect=RuntimeError("API unavailable")):
            with self.assertRaisesRegex(RuntimeError, "API unavailable"):
                _collect_public_contribution_days(client, "trsdn", self.now, self.days)


if __name__ == "__main__":
    unittest.main()
