"""Configuration loading and validation."""

from __future__ import annotations

from pathlib import Path
from typing import Any

ACCOUNT_CARDS = {"overview", "activity", "language", "momentum", "repos-table", "now-building"}

DEFAULT_CONFIG: dict[str, Any] = {
    "username": "trsdn",
    "top_n": 12,
    "include_private": False,
    "repo": {"include": [], "exclude": []},
    "cards": {
        "repo": ["repo-card"],
        "account": ["overview", "activity", "language", "momentum"],
    },
    "themes": {},
}


def _merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    result = dict(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _merge(result[key], value)
        else:
            result[key] = value
    return result


def _scalar(value: str) -> Any:
    value = value.strip()
    if value in {"[]", ""}:
        return [] if value == "[]" else ""
    if value.lower() == "true":
        return True
    if value.lower() == "false":
        return False
    if value.startswith('"') and value.endswith('"'):
        return value[1:-1]
    try:
        return int(value)
    except ValueError:
        return value


def _parse_simple_yaml(text: str) -> dict[str, Any]:
    """Parse the restricted YAML shape used by profile_stats/config.yml."""
    lines = [
        (number, raw)
        for number, raw in enumerate(text.splitlines(), start=1)
        if raw.strip() and not raw.lstrip().startswith("#")
    ]
    root: dict[str, Any] = {}
    stack: list[tuple[int, dict[str, Any] | list[Any]]] = [(-1, root)]

    for index, (number, raw) in enumerate(lines):
        indent = len(raw) - len(raw.lstrip(" "))
        line = raw.strip()
        while stack and indent <= stack[-1][0]:
            stack.pop()
        parent = stack[-1][1]
        if line.startswith("- "):
            if not isinstance(parent, list):
                raise ValueError(f"line {number}: list item without list parent")
            parent.append(_scalar(line[2:]))
            continue
        if ":" not in line or isinstance(parent, list):
            raise ValueError(f"line {number}: cannot parse configuration")
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        if value:
            parent[key] = _scalar(value)
            continue
        next_is_list = False
        if index + 1 < len(lines):
            _, next_raw = lines[index + 1]
            next_indent = len(next_raw) - len(next_raw.lstrip(" "))
            next_is_list = next_indent > indent and next_raw.strip().startswith("- ")
        container: dict[str, Any] | list[Any] = [] if next_is_list else {}
        parent[key] = container
        stack.append((indent, container))

    return root


def _fix_empty_lists(config: dict[str, Any]) -> dict[str, Any]:
    for section, keys in {"repo": ("include", "exclude"), "cards": ("repo", "account")}.items():
        if isinstance(config.get(section), dict):
            for key in keys:
                if config[section].get(key) == {}:
                    config[section][key] = []
    return config


def load_config(path: str | Path | None = None) -> dict[str, Any]:
    cfg = dict(DEFAULT_CONFIG)
    config_path = Path(path) if path else Path(__file__).with_name("config.yml")
    if config_path.exists():
        loaded = _fix_empty_lists(_parse_simple_yaml(config_path.read_text()))
        if not isinstance(loaded, dict):
            raise ValueError("configuration root must be a mapping")
        cfg = _merge(cfg, loaded)
    if not isinstance(cfg.get("username"), str) or not cfg["username"]:
        raise ValueError("username must be a non-empty string")
    top_n = cfg.get("top_n")
    if not isinstance(top_n, int) or top_n < 1 or top_n > 100:
        raise ValueError("top_n must be an integer between 1 and 100")
    repo = cfg.get("repo", {})
    for key in ("include", "exclude"):
        if key in repo and not isinstance(repo[key], list):
            raise ValueError(f"repo.{key} must be a list")
    cards = cfg.get("cards")
    if not isinstance(cards, dict) or not isinstance(cards.get("account"), list):
        raise ValueError("cards.account must be a list")
    selected = cards["account"]
    if any(not isinstance(name, str) or name not in ACCOUNT_CARDS for name in selected):
        raise ValueError("cards.account contains an unknown account card")
    if len(set(selected)) != len(selected):
        raise ValueError("cards.account must not contain duplicate names")
    return cfg
