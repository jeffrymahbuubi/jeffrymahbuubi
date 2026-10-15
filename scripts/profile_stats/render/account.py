"""Account-level SVG card renderers.

Every card computes its own height from its content. Nothing is animated: a
card has to render identically in a browser, in a static rasteriser and in a
thumbnail, so the finished state is the only state.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from math import ceil

from ..languages import color_for
from ..models import AccountStats, ContributionDay, LanguageShare
from ..momentum import account_momentum
from .svg import esc, footer, n, relative_time, svg_root, truncate
from .theme import Theme, card_bg, defs

MARGIN = 28
FOOTER_GAP = 30
BOTTOM_PAD = 16

MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def _metric(x: int, y: int, label: str, value: object) -> str:
    return (
        f'<text x="{x}" y="{y}" class="label">{esc(label)}</text>'
        f'<text x="{x}" y="{y + 24}" class="value">{esc(value)}</text>'
    )


def _repo_count(stats: AccountStats) -> str:
    """Sources over everything the account owns.

    The rendered cards describe sources only, because forks say nothing about
    the account's own work. GitHub's own profile counts forks, so showing the
    bare source count invites the reader to conclude the card is wrong.
    """
    sources = len(stats.repos)
    if stats.total_repos <= sources:
        return n(sources)
    return f"{n(sources)} / {n(stats.total_repos)}"


def render_overview_card(stats: AccountStats, theme: Theme) -> str:
    width = 820
    rows = (116, 196)
    content_bottom = rows[-1] + 24
    footer_y = content_bottom + FOOTER_GAP
    height = footer_y + BOTTOM_PAD

    body = [defs(theme), card_bg(width, height, theme)]
    body.append(f'<text x="28" y="44" class="title">{esc(stats.username)} account overview</text>')
    body.append(
        '<text x="28" y="68" class="subtitle">Public GitHub activity. Repositories reads sources / all; the difference is forks.</text>'
    )
    metrics = [
        (28, rows[0], "Total commits", n(stats.total_commits)),
        (188, rows[0], "Stars", n(stats.total_stars)),
        (328, rows[0], "Merged PRs", n(stats.merged_prs)),
        (488, rows[0], "Issues", n(stats.authored_issues)),
        (638, rows[0], "Reviews", n(stats.code_reviews)),
        (28, rows[1], "Followers", n(stats.followers)),
        (188, rows[1], "Active repos", n(stats.active_repos)),
        (328, rows[1], "Current streak", f"{stats.current_streak}d"),
        (488, rows[1], "Longest streak", f"{stats.longest_streak}d"),
        (638, rows[1], "Repositories", _repo_count(stats)),
    ]
    body.extend(_metric(*m) for m in metrics)
    body.append(footer(width - MARGIN, footer_y, stats.generated_at))
    return svg_root(width, height, "".join(body))


def _heat_levels(theme: Theme) -> tuple[str, ...]:
    """A single-hue ramp.

    A multi-hue scale cannot be ordered by eye: nothing tells a reader that
    green outranks purple. Keeping one hue and varying only its lightness makes
    the busiest days obvious without a legend lookup.
    """
    if theme.name == "dark":
        return (theme.track, "#3b3170", "#5b4ac4", "#8468ee", theme.accent)
    return (theme.track, "#ddd6fe", "#b4a2fb", "#8a72f9", theme.accent)


def _heat_color(count: int, theme: Theme) -> str:
    levels = _heat_levels(theme)
    if count <= 0:
        return levels[0]
    if count < 2:
        return levels[1]
    if count < 5:
        return levels[2]
    if count < 10:
        return levels[3]
    return levels[4]


def _calendar(days: list[ContributionDay]) -> tuple[date, list[tuple[int, int, ContributionDay]]]:
    """Place each day on a Sunday-aligned grid using its real weekday.

    Slicing the day list and using the index modulo seven only lines up when
    the slice happens to start on a Sunday, which silently mislabels the rows.
    Deriving the column and row from the date itself always holds.
    """
    if not days:
        return date.today(), []
    first = days[0].day
    origin = first - timedelta(days=(first.weekday() + 1) % 7)
    return origin, [(((d.day - origin).days) // 7, ((d.day - origin).days) % 7, d) for d in days]


def _month_labels(origin: date, columns: int, x0: int, step: int) -> str:
    parts = []
    previous_month = None
    last_labelled = -3
    for col in range(columns):
        day = origin + timedelta(days=col * 7)
        if day.month != previous_month:
            if previous_month is not None and col - last_labelled >= 3:
                parts.append(
                    f'<text x="{x0 + col * step}" y="90" class="tiny">{MONTHS[day.month - 1]}</text>'
                )
                last_labelled = col
            previous_month = day.month
    return "".join(parts)


def render_activity_card(stats: AccountStats, theme: Theme) -> str:
    width = 820
    cell, gap = 10, 3
    step = cell + gap
    grid_x, grid_y = 62, 100

    days = stats.contribution_days[-371:]
    origin, placed = _calendar(days)
    columns = max((col for col, _, _ in placed), default=0) + 1
    grid_bottom = grid_y + 7 * step - gap
    legend_y = grid_bottom + 24
    height = legend_y + BOTTOM_PAD

    body = [defs(theme), card_bg(width, height, theme)]
    body.append('<text x="28" y="44" class="title">Contribution activity</text>')
    body.append(
        f'<text x="28" y="68" class="subtitle">Last 12 months · '
        f"current streak {stats.current_streak}d · longest streak {stats.longest_streak}d</text>"
    )
    body.append(_month_labels(origin, columns, grid_x, step))
    for row, name in ((1, "Mon"), (3, "Wed"), (5, "Fri")):
        body.append(
            f'<text x="54" y="{grid_y + row * step + cell - 1}" text-anchor="end" class="tiny">{name}</text>'
        )
    for col, row, day in placed:
        x = grid_x + col * step
        y = grid_y + row * step
        body.append(
            f'<rect x="{x}" y="{y}" width="{cell}" height="{cell}" rx="2" '
            f'fill="{_heat_color(day.count, theme)}"><title>{day.day.isoformat()}: {day.count}</title></rect>'
        )

    swatch_x = 62
    body.append(f'<text x="{swatch_x}" y="{legend_y}" class="tiny">Less</text>')
    swatch_x += 30
    for colour in _heat_levels(theme):
        body.append(
            f'<rect x="{swatch_x}" y="{legend_y - 9}" width="{cell}" height="{cell}" rx="2" fill="{colour}"/>'
        )
        swatch_x += step
    body.append(f'<text x="{swatch_x + 2}" y="{legend_y}" class="tiny">More</text>')
    body.append(footer(width - MARGIN, legend_y, stats.generated_at))
    return svg_root(width, height, "".join(body))


def render_momentum_card(stats: AccountStats, theme: Theme) -> str:
    momentum = account_momentum(stats)
    current, previous = momentum.current, momentum.previous
    current_total, previous_total = current.total, previous.total
    if current_total is None or previous_total is None:
        change = "Change unavailable: both periods need complete public data"
    else:
        delta = current_total - previous_total
        if previous_total:
            change = f"Change: {delta:+,} ({delta / previous_total:+.1%})"
        elif current_total:
            change = f"Change: +{delta:,} (previous period was zero; % undefined)"
        else:
            change = "Change: 0 (both periods zero; % undefined)"

    notes = []
    if current_total is None or previous_total is None:
        notes.append(
            f"Public data incomplete: {current.observed_days}/30 recent days, "
            f"{previous.observed_days}/30 previous days; missing is not zero."
        )
    chart_heading = 220 + len(notes) * 22
    chart_top, chart_bottom = chart_heading + 38, chart_heading + 98
    labels_y = chart_bottom + 22
    semantics_y = labels_y + 26
    footer_y = semantics_y + FOOTER_GAP
    width, height = 820, footer_y + BOTTOM_PAD
    body = [defs(theme), card_bg(width, height, theme)]
    body.append(
        "<title>Momentum: public contributions over two consecutive 30-day periods</title>"
        "<desc>Completed UTC days only. Weekly points are Monday to Sunday, clipped "
        "to the displayed 60-day range. Missing data is not zero.</desc>"
        '<text x="28" y="44" class="title">Momentum</text>'
        '<text x="28" y="68" class="subtitle">'
        "Public contributions | Completed UTC days; today excluded</text>"
    )
    for x, label, period in (
        (28, "Last 30 days", current),
        (292, "Previous 30 days", previous),
    ):
        total = f"{period.total:,}" if period.total is not None else "Unavailable"
        body.append(_metric(x, 104, label, total))
        body.append(
            f'<text x="{x}" y="151" class="small">'
            f"{period.start.isoformat()} to {period.end.isoformat()}</text>"
        )
    active = f"{current.active_days} / 30" if current.active_days is not None else "Unavailable"
    body.append(_metric(568, 104, "Active days", active))
    body.append(
        '<text x="568" y="151" class="small">Last 30 days; at least 1 contribution</text>'
        f'<text x="28" y="184" class="mono">{esc(change)}</text>'
    )
    for i, note in enumerate(notes):
        body.append(f'<text x="28" y="{208 + i * 22}" class="small">{esc(note)}</text>')
    body.append(
        f'<text x="28" y="{chart_heading}" class="label">Weekly contributions</text>'
        f'<text x="792" y="{chart_heading}" text-anchor="end" class="small">'
        f"{previous.start.isoformat()} to {current.end.isoformat()} UTC</text>"
    )
    peak = max((week.total or 0 for week in momentum.weeks), default=0) or 1
    points: list[str] = []

    def flush() -> None:
        if len(points) > 1:
            body.append(
                f'<polyline points="{" ".join(points)}" fill="none" '
                f'stroke="{theme.accent}" stroke-width="2" stroke-linejoin="round"/>'
            )
        points.clear()

    for i, week in enumerate(momentum.weeks):
        x = 64 + i * 692 / (len(momentum.weeks) - 1)
        label = week.start.strftime("%m-%d") + ("*" if week.days < 7 else "")
        body.append(f'<text x="{x - 18:.2f}" y="{labels_y}" class="tiny">{label}</text>')
        if week.total is None:
            flush()
            body.append(
                f'<text x="{x - 18:.2f}" y="{chart_top + 30}" class="tiny">N/A'
                f"<title>{week.start} to {week.end}: unavailable "
                f"({week.observed_days}/{week.days} days)</title></text>"
            )
            continue
        y = chart_bottom - (chart_bottom - chart_top) * week.total / peak
        points.append(f"{x:.2f},{y:.2f}")
        body.append(
            f'<circle cx="{x:.2f}" cy="{y:.2f}" r="3" fill="{theme.accent}">'
            f"<title>{week.start} to {week.end}: {week.total:,} public contributions "
            f"({week.days} days{'; partial week' if week.days < 7 else ''})</title></circle>"
            f'<text x="{x - 18:.2f}" y="{y - 10:.2f}" class="tiny">{week.total:,}</text>'
        )
    flush()
    body.append(
        f'<text x="28" y="{semantics_y}" class="small">'
        "Mon-Sun totals; labels are week starts. * Partial boundary week, not extrapolated.</text>"
    )
    body.append(footer(width - MARGIN, footer_y, stats.generated_at))
    return svg_root(width, height, "".join(body))


def _language_bar(
    langs: list[LanguageShare], total: int, x: int, y: int, width: int, theme: Theme
) -> str:
    if total <= 0:
        return f'<rect x="{x}" y="{y}" width="{width}" height="18" rx="9" fill="{theme.track}"/>'
    parts = []
    offset = 0.0
    for lang in langs[:10]:
        w = max(3, width * lang.size / total)
        parts.append(
            f'<rect x="{x + offset:.2f}" y="{y}" width="{w:.2f}" height="18" rx="9" '
            f'fill="{color_for(lang.name, lang.color)}"><title>{esc(lang.name)}</title></rect>'
        )
        offset += w
    return "".join(parts)


def render_language_card(stats: AccountStats, theme: Theme) -> str:
    width = 820
    langs = stats.weighted_languages[:12]
    total = sum(language.size for language in stats.weighted_languages)
    legend_top, legend_step = 150, 32
    rows = max(1, ceil(len(langs) / 3))
    content_bottom = legend_top + (rows - 1) * legend_step
    footer_y = content_bottom + FOOTER_GAP
    height = footer_y + BOTTOM_PAD

    body = [defs(theme), card_bg(width, height, theme)]
    body.append('<text x="28" y="44" class="title">Language distribution</text>')
    body.append(
        '<text x="28" y="68" class="subtitle">Weighted by repository language bytes; forks excluded</text>'
    )
    body.append(_language_bar(stats.weighted_languages, total, 28, 98, 764, theme))
    for i, lang in enumerate(langs):
        x = 28 + (i % 3) * 255
        y = legend_top + (i // 3) * legend_step
        pct = (lang.size / total * 100) if total else 0
        body.append(
            f'<circle cx="{x + 5}" cy="{y - 5}" r="5" fill="{color_for(lang.name, lang.color)}"/>'
            f'<text x="{x + 18}" y="{y}" class="mono">{esc(truncate(lang.name, 18))}</text>'
            f'<text x="{x + 185}" y="{y}" class="small">{pct:.1f}%</text>'
        )
    body.append(footer(width - MARGIN, footer_y, stats.generated_at))
    return svg_root(width, height, "".join(body))


_TABLE_COLUMNS = (
    (28, "Repo"),
    (340, "Stars"),
    (400, "Commits"),
    (490, "Last commit"),
    (610, "Release"),
    (760, "Issues"),
    (820, "Lang"),
)


def render_repos_table_card(stats: AccountStats, theme: Theme, top_n: int = 12) -> str:
    repos = sorted(
        stats.repos,
        key=lambda r: r.last_commit_at or r.updated_at or datetime(1970, 1, 1, tzinfo=UTC),
        reverse=True,
    )[:top_n]
    width = 980
    row_h, first_row = 34, 130
    last_row = first_row + (len(repos) - 1) * row_h if repos else first_row
    content_bottom = last_row + 9
    footer_y = content_bottom + 26
    height = footer_y + 14

    body = [defs(theme), card_bg(width, height, theme)]
    body.append('<text x="28" y="44" class="title">Recently active repositories</text>')
    body.append(
        f'<text x="28" y="68" class="subtitle">Top {len(repos)} sorted by last activity</text>'
    )
    for x, label in _TABLE_COLUMNS:
        body.append(f'<text x="{x}" y="100" class="label">{esc(label)}</text>')
    for i, repo in enumerate(repos):
        y = first_row + i * row_h
        fill = theme.track if i % 2 else theme.panel
        body.append(
            f'<rect x="20" y="{y - 21}" width="940" height="30" rx="7" fill="{fill}" opacity=".42"/>'
        )
        release = (
            repo.latest_release.tag if repo.latest_release and repo.latest_release.tag else "—"
        )
        if repo.latest_release and repo.latest_release.published_at:
            release = f"{release} {repo.latest_release.published_at.date().isoformat()}"
        body.append(f'<text x="28" y="{y}" class="mono">{esc(truncate(repo.full_name, 34))}</text>')
        body.append(
            f'<text x="340" y="{y}" class="small">{esc(n(repo.stars))}</text>'
            f'<text x="400" y="{y}" class="small">{esc(n(repo.commits))}</text>'
            f'<text x="490" y="{y}" class="small">{esc(relative_time(repo.last_commit_at, stats.generated_at))}</text>'
            f'<text x="610" y="{y}" class="small">{esc(truncate(release, 21))}</text>'
            f'<text x="760" y="{y}" class="small">{esc(n(repo.open_issues))}</text>'
            f'<circle cx="825" cy="{y - 5}" r="5" fill="{color_for(repo.primary_language, repo.primary_language_color)}"/>'
            f'<text x="838" y="{y}" class="small">{esc(truncate(repo.primary_language or "—", 12))}</text>'
        )
    body.append(footer(width - 20, footer_y, stats.generated_at))
    return svg_root(width, height, "".join(body))


def render_now_building_card(stats: AccountStats, theme: Theme) -> str:
    repos = sorted(
        stats.repos,
        key=lambda r: r.last_commit_at or r.updated_at or datetime(1970, 1, 1, tzinfo=UTC),
        reverse=True,
    )[:3]
    width = 820
    first_row, row_step = 112, 54
    content_bottom = first_row + max(0, len(repos) - 1) * row_step + 10
    footer_y = content_bottom + FOOTER_GAP
    height = footer_y + BOTTOM_PAD

    body = [defs(theme), card_bg(width, height, theme)]
    body.append('<text x="28" y="44" class="title">Now building</text>')
    body.append(
        '<text x="28" y="68" class="subtitle">The three repositories with the most recent commits</text>'
    )
    for i, repo in enumerate(repos):
        y = first_row + i * row_step
        body.append(
            f'<circle cx="38" cy="{y - 7}" r="7" fill="{color_for(repo.primary_language, repo.primary_language_color)}"/>'
            f'<text x="56" y="{y - 12}" class="mono">{esc(truncate(repo.full_name, 45))}</text>'
            f'<text x="56" y="{y + 10}" class="small">'
            f"{esc(relative_time(repo.last_commit_at, stats.generated_at))} · "
            f"{esc(truncate(repo.last_commit_message or '—', 78))}</text>"
        )
    body.append(footer(width - MARGIN, footer_y, stats.generated_at))
    return svg_root(width, height, "".join(body))
