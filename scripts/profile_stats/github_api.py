"""Small GitHub GraphQL and REST client with retry handling."""

from __future__ import annotations

import os
import time
from collections.abc import Iterator
from datetime import datetime
from typing import Any


class GitHubApiError(RuntimeError):
    """Raised when GitHub returns a failed API response."""


class GitHubClient:
    def __init__(self, token: str | None = None, *, timeout: int = 20, retries: int = 4) -> None:
        self.token = token or os.getenv("STATS_TOKEN") or os.getenv("GITHUB_TOKEN")
        self.timeout = timeout
        self.retries = retries
        import requests

        self.session = requests.Session()
        self.session.headers.update(
            {
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "trsdn-profile-stats",
            }
        )
        if self.token:
            self.session.headers["Authorization"] = f"Bearer {self.token}"

    def graphql(self, query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = {"query": query, "variables": variables or {}}
        response = self._request("POST", "https://api.github.com/graphql", json=payload)
        data = response.json()
        if data.get("errors"):
            raise GitHubApiError(str(data["errors"]))
        return data["data"]

    def get_json(
        self, path: str, *, params: dict[str, Any] | None = None, accept_202: bool = False
    ) -> Any:
        url = path if path.startswith("http") else f"https://api.github.com{path}"
        response = self._request("GET", url, params=params, accept_202=accept_202)
        return response.json() if response.content else None

    def paginate(self, path: str, *, params: dict[str, Any] | None = None) -> Iterator[Any]:
        params = dict(params or {})
        params.setdefault("per_page", 100)
        url = path if path.startswith("http") else f"https://api.github.com{path}"
        while url:
            response = self._request("GET", url, params=params)
            data = response.json()
            if isinstance(data, list):
                yield from data
            else:
                yield data
            url = response.links.get("next", {}).get("url")
            params = None

    def count_paginated(self, path: str, *, params: dict[str, Any] | None = None) -> int:
        params = dict(params or {})
        params["per_page"] = 1
        url = path if path.startswith("http") else f"https://api.github.com{path}"
        response = self._request("GET", url, params=params)
        if "last" in response.links:
            last_url = response.links["last"]["url"]
            from urllib.parse import parse_qs, urlparse

            return int(parse_qs(urlparse(last_url).query).get("page", ["1"])[0])
        data = response.json()
        return len(data) if isinstance(data, list) else 0

    def stats_commit_activity(self, owner: str, repo: str) -> list[int]:
        path = f"/repos/{owner}/{repo}/stats/commit_activity"
        data = self.get_json(path, accept_202=True)
        if not data:
            return []
        return [int(item.get("total", 0)) for item in data]

    def search_count(self, query: str) -> int:
        data = self.get_json("/search/issues", params={"q": query, "per_page": 1})
        return int(data.get("total_count", 0)) if isinstance(data, dict) else 0

    def _request(self, method: str, url: str, *, accept_202: bool = False, **kwargs: Any) -> Any:
        delay = 1.0
        last_response: Any | None = None
        for attempt in range(self.retries + 1):
            response = self.session.request(method, url, timeout=self.timeout, **kwargs)
            last_response = response
            if response.status_code == 202 and accept_202:
                time.sleep(min(delay, 10))
                delay *= 1.8
                continue
            if response.status_code in {429, 500, 502, 503, 504} or self._rate_limited(response):
                if attempt >= self.retries:
                    break
                time.sleep(self._retry_after(response, delay))
                delay *= 2
                continue
            if response.ok:
                return response
            break
        assert last_response is not None
        raise GitHubApiError(
            f"{method} {url} failed with {last_response.status_code}: {last_response.text[:300]}"
        )

    @staticmethod
    def _rate_limited(response: Any) -> bool:
        return response.status_code == 403 and response.headers.get("X-RateLimit-Remaining") == "0"

    @staticmethod
    def _retry_after(response: Any, fallback: float) -> float:
        retry_after = response.headers.get("Retry-After")
        if retry_after:
            try:
                return max(1.0, float(retry_after))
            except ValueError:
                pass
        reset = response.headers.get("X-RateLimit-Reset")
        if reset:
            try:
                return max(1.0, float(reset) - datetime.now().timestamp() + 1)
            except ValueError:
                pass
        return min(fallback, 30.0)
