"""Theme definitions for generated SVG cards."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True)
class Theme:
    name: str
    bg: str
    panel: str
    text: str
    muted: str
    border: str
    accent: str
    accent2: str
    track: str
    good: str
    warn: str
    shadow: str


LIGHT = Theme(
    name="light",
    bg="#f8fafc",
    panel="#ffffff",
    text="#182235",
    muted="#64748b",
    border="#dbe3ef",
    accent="#6d5dfc",
    accent2="#06b6d4",
    track="#e8edf5",
    good="#22c55e",
    warn="#f59e0b",
    shadow="#94a3b8",
)

DARK = Theme(
    name="dark",
    bg="#0b1020",
    panel="#111827",
    text="#e5e7eb",
    muted="#94a3b8",
    border="#263247",
    accent="#a78bfa",
    accent2="#22d3ee",
    track="#1f2937",
    good="#34d399",
    warn="#fbbf24",
    shadow="#000000",
)


def from_config(name: str, config: Mapping[str, object] | None = None) -> Theme:
    base = DARK if name == "dark" else LIGHT
    themes = (config or {}).get("themes", {}) if isinstance(config, Mapping) else {}
    override = themes.get(name, {}) if isinstance(themes, Mapping) else {}
    if not isinstance(override, Mapping):
        return base
    data = {field: getattr(base, field) for field in base.__dataclass_fields__}
    data.update({k: str(v) for k, v in override.items() if k in data})
    data["name"] = name
    return Theme(**data)


def defs(theme: Theme) -> str:
    return f'''
<defs>
  <filter id="shadow" x="-10%" y="-10%" width="120%" height="120%">
    <feDropShadow dx="0" dy="8" stdDeviation="10" flood-color="{theme.shadow}" flood-opacity="0.16"/>
  </filter>
  <style>
    .title {{ font: 700 20px -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; fill: {theme.text}; }}
    .subtitle {{ font: 500 12px -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; fill: {theme.muted}; }}
    .label {{ font: 600 11px -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; fill: {theme.muted}; text-transform: uppercase; letter-spacing: .06em; }}
    .value {{ font: 700 17px ui-monospace,SFMono-Regular,Menlo,monospace; fill: {theme.text}; }}
    .small {{ font: 500 11px -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; fill: {theme.muted}; }}
    .tiny {{ font: 500 10px -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; fill: {theme.muted}; }}
    .mono {{ font: 650 12px ui-monospace,SFMono-Regular,Menlo,monospace; fill: {theme.text}; }}
  </style>
</defs>'''


def card_bg(width: int, height: int, theme: Theme) -> str:
    return (
        f'<rect x="1" y="1" width="{width - 2}" height="{height - 2}" rx="12" '
        f'fill="{theme.panel}" stroke="{theme.border}" filter="url(#shadow)"/>'
    )
