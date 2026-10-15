"""GitHub data aggregation."""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from typing import Any

from .github_api import GitHubClient
from .languages import color_for
from .models import AccountStats, ContributionDay, LanguageShare, ReleaseStats, RepoStats


def parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


_REPO_QUERY = """
query RepoStats($owner: String!, $name: String!) {
  repository(owner: $owner, name: $name) {
    name
    nameWithOwner
    description
    isPrivate
    stargazerCount
    forkCount
    diskUsage
    updatedAt
    watchers { totalCount }
    issues(states: OPEN) { totalCount }
    pullRequests(states: OPEN) { totalCount }
    releases { totalCount }
    latestRelease { tagName publishedAt releaseAssets(first: 100) { nodes { downloadCount } } }
    licenseInfo { name spdxId }
    primaryLanguage { name color }
    languages(first: 10, orderBy: {field: SIZE, direction: DESC}) { totalSize edges { size node { name color } } }
    defaultBranchRef { name target { ... on Commit { history(first: 1) { totalCount nodes { committedDate messageHeadline } } } } }
    owner { login }
  }
}
"""


def collect_repo_stats(
    client: GitHubClient, repository: str, *, include_activity: bool = True
) -> RepoStats:
    owner, name = repository.split("/", 1)
    repo = client.graphql(_REPO_QUERY, {"owner": owner, "name": name})["repository"]
    release = repo.get("latestRelease")
    latest_release = None
    if release:
        downloads = sum(
            int(a.get("downloadCount") or 0)
            for a in release.get("releaseAssets", {}).get("nodes", [])
        )
        latest_release = ReleaseStats(
            release.get("tagName"), parse_datetime(release.get("publishedAt")), downloads
        )
    history = ((repo.get("defaultBranchRef") or {}).get("target") or {}).get("history") or {}
    last_node = (history.get("nodes") or [{}])[0] if history.get("nodes") else {}
    languages = [
        LanguageShare(
            edge["node"]["name"],
            int(edge.get("size") or 0),
            color_for(edge["node"].get("name"), edge["node"].get("color")),
        )
        for edge in (repo.get("languages") or {}).get("edges", [])
    ]
    contributors = 0
    try:
        contributors = client.count_paginated(
            f"/repos/{owner}/{name}/contributors", params={"anon": "1"}
        )
    except Exception:
        contributors = 0
    activity = []
    if include_activity:
        try:
            activity = client.stats_commit_activity(owner, name)
        except Exception:
            activity = []
    license_info = repo.get("licenseInfo") or {}
    primary = repo.get("primaryLanguage") or {}
    return RepoStats(
        owner=repo["owner"]["login"],
        name=repo["name"],
        full_name=repo["nameWithOwner"],
        description=repo.get("description"),
        default_branch=(repo.get("defaultBranchRef") or {}).get("name") or "main",
        is_private=bool(repo.get("isPrivate")),
        stars=int(repo.get("stargazerCount") or 0),
        forks=int(repo.get("forkCount") or 0),
        watchers=int((repo.get("watchers") or {}).get("totalCount") or 0),
        open_issues=int((repo.get("issues") or {}).get("totalCount") or 0),
        open_prs=int((repo.get("pullRequests") or {}).get("totalCount") or 0),
        releases=int((repo.get("releases") or {}).get("totalCount") or 0),
        latest_release=latest_release,
        commits=int(history.get("totalCount") or 0),
        last_commit_at=parse_datetime(last_node.get("committedDate")),
        last_commit_message=last_node.get("messageHeadline"),
        contributors=contributors,
        primary_language=primary.get("name"),
        primary_language_color=color_for(primary.get("name"), primary.get("color"))
        if primary
        else None,
        languages=languages,
        language_total=int((repo.get("languages") or {}).get("totalSize") or 0),
        disk_usage_kb=int(repo.get("diskUsage") or 0),
        license_name=license_info.get("spdxId") or license_info.get("name"),
        commit_activity=activity,
        updated_at=parse_datetime(repo.get("updatedAt")),
    )


_ACCOUNT_PROFILE_QUERY = """
query AccountProfile($login: String!, $from: DateTime!, $to: DateTime!) {
  user(login: $login) {
    login
    followers { totalCount }
    contributionsCollection(from: $from, to: $to) {
      contributionCalendar { weeks { contributionDays { date contributionCount } } }
    }
  }
}
"""

_ACCOUNT_REPOS_QUERY = """
query AccountRepos($login: String!, $cursor: String) {
  user(login: $login) {
    repositories(first: 25, after: $cursor, ownerAffiliations: OWNER, orderBy: {field: UPDATED_AT, direction: DESC}) {
      pageInfo { hasNextPage endCursor }
      nodes {
        name nameWithOwner description isPrivate isFork isArchived stargazerCount forkCount diskUsage updatedAt
        watchers { totalCount }
        issues(states: OPEN) { totalCount }
        pullRequests(states: OPEN) { totalCount }
        releases { totalCount }
        latestRelease { tagName publishedAt releaseAssets(first: 100) { nodes { downloadCount } } }
        licenseInfo { name spdxId }
        primaryLanguage { name color }
        languages(first: 10, orderBy: {field: SIZE, direction: DESC}) { totalSize edges { size node { name color } } }
        defaultBranchRef { name target { ... on Commit { history(first: 1) { totalCount nodes { committedDate messageHeadline } } } } }
        owner { login }
      }
    }
  }
}
"""

_PUBLIC_COMMITS_QUERY = """
query PublicContributions($login: String!, $from: DateTime!, $to: DateTime!) {
  user(login: $login) {
    contributionsCollection(from: $from, to: $to) {
      totalRepositoriesWithContributedCommits
      commitContributionsByRepository(maxRepositories: 100) {
        repository { visibility }
        contributions(first: 100) {
          pageInfo { hasNextPage }
          nodes { occurredAt commitCount isRestricted }
        }
      }
    }
  }
}
"""

_PUBLIC_CONNECTIONS = {
    "issueContributions": "issue { repository { visibility } }",
    "pullRequestContributions": "pullRequest { repository { visibility } }",
    "pullRequestReviewContributions": "repository { visibility }",
    "repositoryContributions": "repository { visibility }",
}


def _collect_public_contribution_days(
    client: GitHubClient,
    username: str,
    generated_at: datetime,
    calendar_days: list[ContributionDay],
) -> list[ContributionDay] | None:
    """Count public, repository-attributed contributions, not private calendar totals."""
    end = generated_at.astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    start = end - timedelta(days=60)
    variables = {
        "login": username,
        "from": start.isoformat(),
        "to": (end - timedelta(seconds=1)).isoformat(),
    }
    # Reuse the calendar's coverage, never its potentially private counts.
    counts = {d.day: 0 for d in calendar_days if start.date() <= d.day < end.date()}

    def add(node: dict[str, Any], count: int) -> None:
        occurred = parse_datetime(node["occurredAt"])
        if occurred is None:
            raise ValueError("public contribution is missing occurredAt")
        day = occurred.astimezone(UTC).date()
        if day in counts and not node["isRestricted"]:
            counts[day] += count

    collection = client.graphql(_PUBLIC_COMMITS_QUERY, variables)["user"]["contributionsCollection"]
    groups = collection["commitContributionsByRepository"]
    if len(groups) != collection["totalRepositoriesWithContributedCommits"] or any(
        group["contributions"]["pageInfo"]["hasNextPage"] for group in groups
    ):
        logging.warning("Public contribution data is truncated; Momentum is unavailable")
        return None
    for group in groups:
        if group["repository"]["visibility"] == "PUBLIC":
            for node in group["contributions"]["nodes"]:
                add(node, int(node["commitCount"]))

    for field, selection in _PUBLIC_CONNECTIONS.items():
        query = f"""
query PublicContributionPage($login: String!, $from: DateTime!, $to: DateTime!, $cursor: String) {{
  user(login: $login) {{
    contributionsCollection(from: $from, to: $to) {{
      {field}(first: 100, after: $cursor) {{
        pageInfo {{ hasNextPage endCursor }}
        nodes {{ occurredAt isRestricted {selection} }}
      }}
    }}
  }}
}}
"""
        cursor = None
        while True:
            page = client.graphql(query, {**variables, "cursor": cursor})["user"][
                "contributionsCollection"
            ][field]
            for node in page["nodes"]:
                if node["isRestricted"]:
                    continue
                resource = node.get("issue", node.get("pullRequest", node))
                if resource["repository"]["visibility"] == "PUBLIC":
                    add(node, 1)
            if not page["pageInfo"]["hasNextPage"]:
                break
            next_cursor = page["pageInfo"]["endCursor"]
            if not next_cursor or next_cursor == cursor:
                raise ValueError(f"{field} pagination did not advance")
            cursor = next_cursor
    return [ContributionDay(day, count) for day, count in sorted(counts.items())]


def _repo_from_node(repo: dict[str, Any]) -> RepoStats:
    release = repo.get("latestRelease")
    latest_release = None
    if release:
        downloads = sum(
            int(a.get("downloadCount") or 0)
            for a in release.get("releaseAssets", {}).get("nodes", [])
        )
        latest_release = ReleaseStats(
            release.get("tagName"), parse_datetime(release.get("publishedAt")), downloads
        )
    history = ((repo.get("defaultBranchRef") or {}).get("target") or {}).get("history") or {}
    last_node = (history.get("nodes") or [{}])[0] if history.get("nodes") else {}
    primary = repo.get("primaryLanguage") or {}
    license_info = repo.get("licenseInfo") or {}
    languages = [
        LanguageShare(
            edge["node"]["name"],
            int(edge.get("size") or 0),
            color_for(edge["node"].get("name"), edge["node"].get("color")),
        )
        for edge in (repo.get("languages") or {}).get("edges", [])
    ]
    return RepoStats(
        owner=repo["owner"]["login"],
        name=repo["name"],
        full_name=repo["nameWithOwner"],
        description=repo.get("description"),
        default_branch=(repo.get("defaultBranchRef") or {}).get("name") or "main",
        is_private=bool(repo.get("isPrivate")),
        stars=int(repo.get("stargazerCount") or 0),
        forks=int(repo.get("forkCount") or 0),
        watchers=int((repo.get("watchers") or {}).get("totalCount") or 0),
        open_issues=int((repo.get("issues") or {}).get("totalCount") or 0),
        open_prs=int((repo.get("pullRequests") or {}).get("totalCount") or 0),
        releases=int((repo.get("releases") or {}).get("totalCount") or 0),
        latest_release=latest_release,
        commits=int(history.get("totalCount") or 0),
        last_commit_at=parse_datetime(last_node.get("committedDate")),
        last_commit_message=last_node.get("messageHeadline"),
        contributors=0,
        primary_language=primary.get("name"),
        primary_language_color=color_for(primary.get("name"), primary.get("color"))
        if primary
        else None,
        languages=languages,
        language_total=int((repo.get("languages") or {}).get("totalSize") or 0),
        disk_usage_kb=int(repo.get("diskUsage") or 0),
        license_name=license_info.get("spdxId") or license_info.get("name"),
        commit_activity=[],
        updated_at=parse_datetime(repo.get("updatedAt")),
    )


def _streaks(days: list[ContributionDay]) -> tuple[int, int]:
    longest = current = running = 0
    for item in days:
        if item.count > 0:
            running += 1
            longest = max(longest, running)
        else:
            running = 0
    for item in reversed(days):
        if item.count > 0:
            current += 1
        else:
            break
    return current, longest


def collect_account_stats(
    client: GitHubClient,
    username: str,
    *,
    include_private: bool = False,
    include: list[str] | None = None,
    exclude: list[str] | None = None,
    include_momentum: bool = True,
) -> AccountStats:
    generated_at = datetime.now(UTC)
    # GitHub accepts at most one year per contributionsCollection query.
    since = generated_at.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=364)
    repos: list[RepoStats] = []
    contribution_days: list[ContributionDay] = []
    followers = 0
    cursor = None
    total_repos = 0
    include_set = set(include or [])
    exclude_set = set(exclude or [])
    profile = client.graphql(
        _ACCOUNT_PROFILE_QUERY,
        {"login": username, "from": since.isoformat(), "to": generated_at.isoformat()},
    )["user"]
    followers = int((profile.get("followers") or {}).get("totalCount") or 0)
    for week in profile["contributionsCollection"]["contributionCalendar"]["weeks"]:
        for day in week["contributionDays"]:
            contribution_days.append(
                ContributionDay(date.fromisoformat(day["date"]), int(day["contributionCount"]))
            )
    while True:
        data = client.graphql(_ACCOUNT_REPOS_QUERY, {"login": username, "cursor": cursor})["user"]
        page = data["repositories"]
        for node in page["nodes"]:
            if node.get("isPrivate") and not include_private:
                continue
            # Counted before the fork and include/exclude filters, so it stays
            # comparable to the repository count GitHub shows on the profile.
            total_repos += 1
            if node.get("isFork"):
                continue
            full_name = node["nameWithOwner"]
            if include_set and full_name not in include_set and node["name"] not in include_set:
                continue
            if full_name in exclude_set or node["name"] in exclude_set:
                continue
            repos.append(_repo_from_node(node))
        if not page["pageInfo"]["hasNextPage"]:
            break
        cursor = page["pageInfo"]["endCursor"]
    language_bytes: dict[str, int] = defaultdict(int)
    language_colors: dict[str, str] = {}
    for repo in repos:
        for lang in repo.languages:
            language_bytes[lang.name] += lang.size
            language_colors[lang.name] = lang.color
    weighted_languages = [
        LanguageShare(name, size, language_colors.get(name, color_for(name)))
        for name, size in sorted(language_bytes.items(), key=lambda item: item[1], reverse=True)
    ]
    current_streak, longest_streak = _streaks(contribution_days)
    total_commits = sum(r.commits for r in repos)
    total_stars = sum(r.stars for r in repos)
    active_repos = sum(
        1
        for r in repos
        if (r.last_commit_at or r.updated_at)
        and (generated_at - (r.last_commit_at or r.updated_at)).days <= 365
    )
    merged_prs = client.search_count(f"author:{username} type:pr is:merged")
    authored_issues = client.search_count(f"author:{username} type:issue")
    code_reviews = client.search_count(f"reviewed-by:{username} type:pr")
    public_days = (
        _collect_public_contribution_days(client, username, generated_at, contribution_days)
        if include_momentum
        else None
    )
    return AccountStats(
        username,
        generated_at,
        repos,
        total_commits,
        total_stars,
        merged_prs,
        authored_issues,
        code_reviews,
        followers,
        active_repos,
        total_repos,
        contribution_days,
        current_streak,
        longest_streak,
        weighted_languages,
        public_days,
    )
