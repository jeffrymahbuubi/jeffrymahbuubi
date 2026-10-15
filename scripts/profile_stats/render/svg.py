"""SVG primitives and formatting helpers."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from html import escape as html_escape
from xml.etree import ElementTree

_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def clean(value: object | None) -> str:
    if value is None:
        return ""
    return _CONTROL_RE.sub("", str(value))


def esc(value: object | None) -> str:
    return html_escape(clean(value), quote=True)


def truncate(value: object | None, max_chars: int) -> str:
    text = clean(value).strip()
    if max_chars <= 0 or len(text) <= max_chars:
        return text
    return text[: max_chars - 1].rstrip() + "…"


def n(value: int | float | None) -> str:
    if value is None:
        return "—"
    value = float(value)
    sign = "-" if value < 0 else ""
    value = abs(value)
    for suffix, threshold in (("b", 1_000_000_000), ("m", 1_000_000), ("k", 1_000)):
        if value >= threshold:
            out = value / threshold
            return f"{sign}{out:.1f}{suffix}" if out < 10 else f"{sign}{out:.0f}{suffix}"
    return f"{sign}{int(value)}"


def bytesize(kb: int | None) -> str:
    if kb is None:
        return "—"
    if kb >= 1024 * 1024:
        return f"{kb / 1024 / 1024:.1f} GB"
    if kb >= 1024:
        return f"{kb / 1024:.1f} MB"
    return f"{kb} KB"


def relative_time(then: datetime | None, now: datetime | None = None) -> str:
    if then is None:
        return "—"
    now = now or datetime.now(UTC)
    if then.tzinfo is None:
        then = then.replace(tzinfo=UTC)
    delta = now - then
    seconds = max(0, int(delta.total_seconds()))
    units = (
        ("y", 31536000),
        ("mo", 2592000),
        ("w", 604800),
        ("d", 86400),
        ("h", 3600),
        ("min", 60),
    )
    for label, size in units:
        if seconds >= size:
            return f"{seconds // size}{label} ago"
    return "just now"


def iso_date(value: datetime | None) -> str:
    if value is None:
        return "—"
    return value.date().isoformat()


def stamp(value: datetime | None) -> str:
    """Render a generation timestamp at minute precision in UTC."""
    if value is None:
        return "—"
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).strftime("%Y-%m-%d %H:%M UTC")


def footer(right: int, y: int, generated_at: datetime | None) -> str:
    return (
        f'<text x="{right}" y="{y}" text-anchor="end" class="small">'
        f"auto-generated · {esc(stamp(generated_at))}</text>"
    )


def svg_root(width: int, height: int, body: str) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img">{body}</svg>\n'
    )


def validate_svg(text: str) -> None:
    ElementTree.fromstring(text)
