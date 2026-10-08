from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from hsk import HSK3_LEVELS

if TYPE_CHECKING:
    from new_over_time import (
        CategoryBreakdown,
        Coverage,
        Groups,
        NewOverTime,
        Occurrences,
        SeenSoFar,
        TextLengths,
    )

SERIES = "#2a78d6"
RAINBOW = ["#e34948", "#eb6834", "#eda100", "#008300", "#1baf7a", "#2a78d6", "#4a3aa7"]
TEXT_SECONDARY = "#52514e"
GRID = "#e8e7e3"
OVERFLOW = "#d9d8d3"
ANKI_COLOURS = {
    "know_well": "#008300",
    "read": "#1baf7a",
    "learning": "#2a78d6",
    "present": "#eda100",
    "missing": "#e34948",
}
DPI = 150
LEGEND_PX = 70


@dataclass
class ChartSettings:
    width_px: int = 1650
    height_px: int = 1050
    x_limits: list = field(default_factory=lambda: [None, None])
    y_limits: dict = field(default_factory=dict)
    coverage_targets: list = field(default_factory=lambda: [95, 98])
    known_label: str = "known in Anki"
    known_source: str = "Anki"
    known_prefix: str = "anki_"

    def y_limits_for(self, chart: str, panel: str) -> tuple:
        limits = list(self.y_limits.get(chart, {}).get(panel) or [])
        return tuple((limits + [None, None])[:2])


def style_axes(ax, title: str) -> None:
    ax.set_title(title, loc="left", fontsize=12, fontweight="bold", pad=10)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(TEXT_SECONDARY)
    ax.tick_params(colors=TEXT_SECONDARY, labelsize=9, length=0, pad=6)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.set_ylim(bottom=0)
    ax.margins(x=0.01)


def count_formatter():
    from matplotlib.ticker import FuncFormatter

    return FuncFormatter(lambda y, _: f"{y:,.0f}")


def panel_axes(settings: ChartSettings, n: int):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    figsize = (settings.width_px / DPI, settings.height_px / DPI)
    fig, axes = plt.subplots(n, 1, figsize=figsize, dpi=DPI, sharex=True, squeeze=False)
    return fig, list(axes[:, 0])


def style_x_axis(axes, by_chapter: bool) -> None:
    from matplotlib.ticker import FuncFormatter, MaxNLocator

    for ax in axes:
        ax.tick_params(labelbottom=True)
        if by_chapter:
            ax.set_xlabel("Chapter", color=TEXT_SECONDARY, fontsize=10)
            ax.xaxis.set_major_locator(MaxNLocator(integer=True))
        else:
            ax.set_xlabel("Words read", color=TEXT_SECONDARY, fontsize=10)
            ax.xaxis.set_major_formatter(FuncFormatter(lambda x, _: f"{x / 1000:,.0f}k" if x else "0"))


def apply_limits(settings: ChartSettings, chart: str, ax, panel: str, by_chapter: bool, percent: bool) -> None:
    left, right = (list(settings.x_limits or []) + [None, None])[:2]
    if by_chapter:
        left = None if left is None else left - 0.5
        right = None if right is None else right + 0.5
    ax.set_xlim(left=left, right=right)
    scale = 100 if percent else 1
    bottom, top = settings.y_limits_for(chart, panel)
    ax.set_ylim(bottom=None if bottom is None else bottom / scale, top=None if top is None else top / scale)


def finish(
    fig,
    axes: list,
    panels: list[str],
    chart: str,
    path: str | Path,
    groups: Groups,
    settings: ChartSettings,
    percent: bool | list[bool] = False,
) -> None:
    import matplotlib.pyplot as plt

    style_x_axis(axes, groups.by_chapter)
    flags = percent if isinstance(percent, list) else [percent] * len(axes)
    for ax, panel, flag in zip(axes, panels, flags):
        apply_limits(settings, chart, ax, panel, groups.by_chapter, flag)

    legend_space = LEGEND_PX / settings.height_px if fig.legends else 0
    fig.tight_layout(h_pad=2.5, rect=(0, legend_space, 1, 1))
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=DPI)
    plt.close(fig)


def anki_title(title: str, excluding_known: bool, settings: ChartSettings) -> str:
    return f"{settings.known_source}: {title} (excluding known)" if excluding_known else title


def unit_label(groups: Groups) -> str:
    return "chapter" if groups.by_chapter else f"{groups.bucket_words:,} words"


def bucket_starts(positions: list[int]) -> list[int]:
    return [0, *positions[:-1]]


def point_xs(groups: Groups) -> list[float]:
    if groups.by_chapter:
        return groups.positions
    return [(start + end) / 2 for start, end in zip(bucket_starts(groups.positions), groups.positions)]


def draw_bars(ax, groups: Groups, values: list[float], **kwargs) -> None:
    kwargs.setdefault("color", SERIES)
    if groups.by_chapter:
        ax.bar(groups.positions, values, width=0.8, **kwargs)
    else:
        starts = bucket_starts(groups.positions)
        widths = [(end - start) * 0.9 for start, end in zip(starts, groups.positions)]
        ax.bar(starts, values, width=widths, align="edge", **kwargs)


def draw_stacked(ax, groups: Groups, band_values: list[list[float]], colours: list) -> None:
    base = [0.0] * len(groups.positions)
    for values, colour in zip(band_values, colours):
        draw_bars(ax, groups, values, bottom=base, color=colour, edgecolor="white", linewidth=0.6)
        base = [b + v for b, v in zip(base, values)]


def stacked_legend(fig, colours: list, labels: list[str], title: str) -> None:
    from matplotlib.patches import Patch

    fig.legend(
        handles=[Patch(color=c, label=label) for c, label in zip(colours, labels)],
        title=title,
        loc="lower center",
        bbox_to_anchor=(0.5, 0.005),
        ncol=len(labels),
        frameon=False,
        fontsize=9,
        title_fontsize=9,
        labelcolor=TEXT_SECONDARY,
        handlelength=1,
        handleheight=1,
    )


def ordinal(n: int) -> str:
    suffix = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def band_labels(bands: list[int], name=ordinal) -> list[str]:
    starts = [1, *(b + 1 for b in bands[:-1])]
    labels = [name(end) if start == end else f"{name(start)}-{name(end)}" for start, end in zip(starts, bands)]
    return [*labels, f"{name(bands[-1] + 1)}+"]


def band_colours(n: int) -> list:
    if n == 1:
        return [RAINBOW[0]]
    if n > len(RAINBOW):
        from matplotlib import colormaps

        return [colormaps["turbo"](0.95 - 0.85 * i / (n - 1)) for i in range(n)]
    return [RAINBOW[round(i * (len(RAINBOW) - 1) / (n - 1))] for i in range(n)]


def hsk_colours(levels: int) -> list:
    return [*band_colours(len(HSK3_LEVELS))[:levels], OVERFLOW]


def occurrence_colours(bands: list[int]) -> list:
    return [*band_colours(len(bands) + 1)[:-1], OVERFLOW]


def plot_new_over_time(
    data: NewOverTime,
    noun: str,
    path: str | Path,
    groups: Groups,
    settings: ChartSettings,
    excluding_known: bool = False,
) -> None:
    fig, (top, bottom) = panel_axes(settings, 2)
    unit = unit_label(groups)

    cumulative = data.cumulative
    draw_bars(top, groups, data.new)
    if groups.by_chapter:
        xs, ys = groups.positions, cumulative
    else:
        xs, ys = [0, *groups.positions], [0, *cumulative]

    bottom.fill_between(xs, ys, color=SERIES, alpha=0.25, linewidth=0)
    bottom.plot(xs, ys, color=SERIES, linewidth=2)
    bottom.annotate(
        f"{cumulative[-1]:,}",
        (xs[-1], ys[-1]),
        xytext=(6, 0),
        textcoords="offset points",
        va="center",
        fontsize=10,
        fontweight="bold",
    )

    style_axes(top, anki_title(f"Unique new {noun} per {unit}", excluding_known, settings))
    style_axes(bottom, anki_title(f"Cumulative unique {noun} seen", excluding_known, settings))
    for ax in (top, bottom):
        ax.yaxis.set_major_formatter(count_formatter())

    finish(fig, [top, bottom], ["new", "total"], f"unique_new_{noun}", path, groups, settings)


def plot_occurrences(
    panels: list[tuple[str, Occurrences]],
    chart: str,
    path: str | Path,
    groups: Groups,
    settings: ChartSettings,
    as_ratio: bool = False,
    excluding_known: bool = False,
    overflow: bool = True,
) -> None:
    from matplotlib.ticker import PercentFormatter

    fig, axes = panel_axes(settings, len(panels))
    unit = unit_label(groups)
    bands = panels[0][1].bands
    labels = band_labels(bands)
    colours = occurrence_colours(bands)
    if not overflow:
        labels, colours = labels[:-1], colours[:-1]

    for ax, (noun, data) in zip(axes, panels):
        draw_stacked(ax, groups, data.band_values(as_ratio, overflow), colours)
        measure = f"{noun.capitalize()} ÷ total {noun}" if as_ratio else noun.capitalize()
        style_axes(ax, anki_title(f"{measure} per {unit}, by which time they're seen", excluding_known, settings))
        ax.yaxis.set_major_formatter(PercentFormatter(1.0) if as_ratio else count_formatter())

    stacked_legend(fig, colours, labels, "Time seen")
    finish(fig, axes, [noun for noun, _ in panels], chart, path, groups, settings, as_ratio)


def plot_band_stacks(
    panels: list[tuple[str, list[list[int]]]],
    title: str,
    labels: list[str],
    legend_title: str,
    chart: str,
    path: str | Path,
    groups: Groups,
    settings: ChartSettings,
    excluding_known: bool,
) -> None:
    fig, axes = panel_axes(settings, len(panels))
    colours = band_colours(len(labels))

    for ax, (noun, band_values) in zip(axes, panels):
        draw_stacked(ax, groups, band_values[::-1], colours[::-1])
        style_axes(ax, anki_title(title.format(noun=noun, unit=unit_label(groups)), excluding_known, settings))
        ax.yaxis.set_major_formatter(count_formatter())

    stacked_legend(fig, colours, labels, legend_title)
    finish(fig, axes, [noun for noun, _ in panels], chart, path, groups, settings)


def plot_seen_so_far(panels: list[tuple[str, SeenSoFar]], *args, excluding_known: bool = False) -> None:
    plot_band_stacks(
        [(noun, data.band_values()) for noun, data in panels],
        "Cumulative unique {noun} seen by {unit}, by how many times they've been seen",
        band_labels(panels[0][1].bands, str),
        "Times seen so far",
        *args,
        excluding_known,
    )


def plot_read_so_far(panels: list[tuple[str, Occurrences]], *args, excluding_known: bool = False) -> None:
    plot_band_stacks(
        [(noun, data.cumulative_band_values()) for noun, data in panels],
        "Cumulative {noun} read by {unit}, by which time each was seen",
        band_labels(panels[0][1].bands),
        "Time seen",
        *args,
        excluding_known,
    )


def coverage_title(noun: str, unit: str, learned_after: int, with_anki: bool, overall: float, settings: ChartSettings) -> str:
    rules = ([settings.known_label] if with_anki else []) + ([f"seen {learned_after}+ times in the text so far"] if learned_after else [])
    title = f"{noun.capitalize()} known per {unit} ({' or '.join(rules)}), whole text {overall:.1%}"
    return f"{settings.known_source}: {title}" if with_anki else title


def plot_coverage(
    panels: list[tuple[str, Coverage]],
    chart: str,
    path: str | Path,
    groups: Groups,
    settings: ChartSettings,
    learned_after: int,
    with_anki: bool = False,
) -> None:
    import math

    from matplotlib.ticker import PercentFormatter

    fig, axes = panel_axes(settings, len(panels))
    unit = unit_label(groups)
    xs = point_xs(groups)
    highest = max(settings.coverage_targets, default=None)

    for ax, (noun, data) in zip(axes, panels):
        ax.plot(xs, data.shares, color=SERIES, linewidth=2, marker="o", markersize=4)
        style_axes(ax, coverage_title(noun, unit, learned_after, with_anki, data.overall, settings))
        valid = [s for s in data.shares if not math.isnan(s)]
        lowest = min(valid + [t / 100 for t in settings.coverage_targets], default=0)
        ax.set_ylim(max(0.0, math.floor((lowest - 0.02) * 20) / 20), 1.0)
        for target in settings.coverage_targets:
            ax.axhline(target / 100, color=TEXT_SECONDARY, linewidth=1, linestyle="--", zorder=1)
            ax.annotate(
                f"{target:g}%",
                (1, target / 100),
                xycoords=("axes fraction", "data"),
                xytext=(4, 1 if target == highest else -1),
                textcoords="offset points",
                va="bottom" if target == highest else "top",
                color=TEXT_SECONDARY,
                fontsize=9,
            )
        ax.yaxis.set_major_formatter(PercentFormatter(1.0))

    finish(fig, axes, [noun for noun, _ in panels], chart, path, groups, settings, True)


def plot_breakdown(
    data: CategoryBreakdown,
    name: str,
    colours: list,
    chart: str,
    path: str | Path,
    groups: Groups,
    settings: ChartSettings,
) -> None:
    from matplotlib.ticker import PercentFormatter

    fig, axes = panel_axes(settings, 3)
    unit = unit_label(groups)
    panels = [
        (f"Words per {unit} by {name}, share of the {unit}", data.shares(), PercentFormatter(1.0)),
        (f"Cumulative words read by {unit}, by {name}", data.cumulative_read(), count_formatter()),
        (f"Cumulative unique words seen by {unit}, by {name}", data.cumulative_unique(), count_formatter()),
    ]
    for ax, (title, values, formatter) in zip(axes, panels):
        draw_stacked(ax, groups, values, colours)
        style_axes(ax, title)
        ax.yaxis.set_major_formatter(formatter)

    stacked_legend(fig, colours, data.categories, name[:1].upper() + name[1:])
    finish(fig, axes, ["share", "read", "unique"], chart, path, groups, settings, [True, False, False])


def plot_text_lengths(data: TextLengths, path: str | Path, groups: Groups, settings: ChartSettings) -> None:
    fig, axes = panel_axes(settings, 2)
    unit = unit_label(groups)
    xs = point_xs(groups)

    panels = [
        ("sentence", data.sentence, data.overall_sentence),
        ("paragraph", data.paragraph, data.overall_paragraph),
    ]
    for ax, (noun, values, overall) in zip(axes, panels):
        ax.plot(xs, values, color=SERIES, linewidth=2, marker="o", markersize=4)
        style_axes(ax, f"Average hanzi per {noun}, per {unit}, whole text {overall:.1f}")
        ax.yaxis.set_major_formatter(count_formatter())

    finish(fig, axes, ["sentence", "paragraph"], "text_lengths", path, groups, settings)
