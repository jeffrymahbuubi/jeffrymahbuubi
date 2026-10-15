"""Command-line entry point for profile-stats."""

from __future__ import annotations

import argparse
from pathlib import Path

from .collect import collect_account_stats, collect_repo_stats
from .config import load_config
from .github_api import GitHubClient
from .render.account import (
    render_activity_card,
    render_language_card,
    render_momentum_card,
    render_now_building_card,
    render_overview_card,
    render_repos_table_card,
)
from .render.repo import render_repo_card
from .render.svg import validate_svg
from .render.theme import from_config


def _themes(names: str, config: dict) -> list[str]:
    return ["light", "dark"] if names == "both" else [names]


def _write(path: Path, text: str) -> None:
    validate_svg(text)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    print(path)


def repo_command(args: argparse.Namespace) -> None:
    config = load_config(args.config)
    client = GitHubClient(args.token)
    stats = collect_repo_stats(client, args.repo)
    out = Path(args.out)
    for theme_name in _themes(args.theme, config):
        suffix = "-dark" if theme_name == "dark" else ""
        theme = from_config(theme_name, config)
        _write(out / f"repo-card{suffix}.svg", render_repo_card(stats, theme))


def account_command(args: argparse.Namespace) -> None:
    config = load_config(args.config)
    client = GitHubClient(args.token)
    repo_cfg = config.get("repo", {})
    stats = collect_account_stats(
        client,
        args.username or config["username"],
        include_private=args.include_private
        if args.include_private is not None
        else bool(config.get("include_private")),
        include=repo_cfg.get("include", []),
        exclude=repo_cfg.get("exclude", []),
        include_momentum="momentum" in config["cards"]["account"],
    )
    top_n = args.top_n or int(config.get("top_n", 12))
    selected = config.get("cards", {}).get("account") or []
    renderers = {
        "overview": lambda theme: render_overview_card(stats, theme),
        "activity": lambda theme: render_activity_card(stats, theme),
        "language": lambda theme: render_language_card(stats, theme),
        "momentum": lambda theme: render_momentum_card(stats, theme),
        "repos-table": lambda theme: render_repos_table_card(stats, theme, top_n=top_n),
        "now-building": lambda theme: render_now_building_card(stats, theme),
    }
    unknown = [name for name in selected if name not in renderers]
    if unknown:
        raise SystemExit(f"unknown account card(s): {', '.join(sorted(unknown))}")
    out = Path(args.out)
    for theme_name in _themes(args.theme, config):
        suffix = "-dark" if theme_name == "dark" else ""
        theme = from_config(theme_name, config)
        for name in selected:
            _write(out / f"{name}-card{suffix}.svg", renderers[name](theme))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="profile-stats", description="Render self-hosted GitHub statistics SVG cards."
    )
    parser.add_argument(
        "--config", help="Path to YAML config. Defaults to scripts/profile_stats/config.yml."
    )
    parser.add_argument("--token", help="GitHub token. Defaults to STATS_TOKEN or GITHUB_TOKEN.")
    sub = parser.add_subparsers(dest="command", required=True)
    repo = sub.add_parser("repo", help="Render cards for one repository.")
    repo.add_argument(
        "--repo", required=True, help="Repository in owner/name form, for example trsdn/OpenLens."
    )
    repo.add_argument("--out", required=True, help="Output directory.")
    repo.add_argument("--theme", choices=["light", "dark", "both"], default="both")
    repo.set_defaults(func=repo_command)
    account = sub.add_parser("account", help="Render account-level cards.")
    account.add_argument("--username", help="GitHub username. Defaults to config username.")
    account.add_argument("--out", required=True, help="Output directory.")
    account.add_argument("--top-n", type=int, help="Number of repositories for the table card.")
    account.add_argument("--include-private", action=argparse.BooleanOptionalAction, default=None)
    account.add_argument("--theme", choices=["light", "dark", "both"], default="both")
    account.set_defaults(func=account_command)
    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)
