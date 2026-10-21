"""Generate the README graph from completed, matching local benchmark manifests."""

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SOURCES = (
    ("Baseline", "2026-10-12-baseline", "#AFBAB3"),
    ("Schema cache + pagination indexes", "2026-10-12-optimized", "#729582"),
    ("Automatic scalar filtering", "2026-10-12-auto-index-conditional", "#39805A"),
    ("Scalar ordering + lazy totals", "2026-10-12-ordering", "#3B5F4C"),
    ("Compact indexes + request lookups", "2026-10-13-mixed-load", "#173D2A"),
)
OPERATIONS = (("list", "List"), ("filter", "Exact filter"), ("generated", "Generated query"), ("save", "Draft save"))


def plot(sources, size, seconds, destination, subtitle, operations=OPERATIONS):
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 12, "svg.hashsalt": "mosscms-benchmarks"})
    figure, axis = plt.subplots(figsize=(11, 9.8 if len(operations) > 4 else 8.5 if len(sources) > 2 else 7.2), dpi=144)
    figure.subplots_adjust(left=0.19, right=0.96, top=0.66 if len(sources) > 2 else 0.73, bottom=0.22)
    rows = np.arange(len(operations))
    for offset, (label, directory, color) in zip(np.linspace(-0.32, 0.32, len(sources)), sources, strict=True):
        manifest = json.loads((ROOT / "docs/benchmarks" / directory / "manifest.json").read_text())
        run = next(run for run in manifest["runs"] if run["size"] == size)
        load = run["load"]
        assert manifest["complete"] and not load["errors"], directory
        assert (load["requestedSeconds"], load["readers"], load["writers"]) == (seconds, 20, 3), directory
        values = [load["operations"][key]["p95Ms"] for key, _ in operations]
        bars = axis.barh(
            rows + offset, values, height=0.13 if len(sources) > 2 else 0.25, color=color, label=label, zorder=3
        )
        for bar, value in zip(bars, values, strict=True):
            axis.text(value + 28, bar.get_y() + bar.get_height() / 2, f"{value:,.0f}", va="center", fontsize=10.5)
    max_value = max(bar.get_width() for bar in axis.patches)
    axis.set(yticks=rows, yticklabels=[label for _, label in operations], xlim=(0, max_value * 1.15))
    axis.invert_yaxis()
    axis.set_xlabel("p95 latency (milliseconds) · lower is better", labelpad=12)
    axis.xaxis.grid(True, color="#E4E8E5", zorder=0)
    axis.set_axisbelow(True)
    axis.tick_params(axis="both", length=0, pad=8, colors="#35433A")
    for spine in axis.spines.values():
        spine.set_visible(False)
    figure.text(0.055, 0.935, f"MossCMS · {size:,}-entry performance", fontsize=20, weight="bold", color="#173D2A")
    figure.text(0.055, 0.88, subtitle, fontsize=12, color="#53635A")
    axis.legend(loc="lower left", bbox_to_anchor=(-0.18, 1.04), frameon=False, ncol=1, fontsize=11, borderaxespad=0)
    figure.text(
        0.055,
        0.12,
        "Shared macOS/ARM64 Docker host. App and database each capped at 2 CPUs / 4 GiB.",
        fontsize=10.5,
        color="#53635A",
    )
    figure.text(
        0.055,
        0.085,
        "Database storage and migration costs are recorded in each source manifest.",
        fontsize=10.5,
        color="#53635A",
    )
    figure.text(
        0.055,
        0.05,
        "Separate samples, not service guarantees. This graph does not measure OpenTelemetry overhead.",
        fontsize=10.5,
        color="#53635A",
    )
    destination = ROOT / "docs/benchmarks" / destination
    figure.savefig(destination.with_suffix(".png"), facecolor="white")
    figure.savefig(destination.with_suffix(".svg"), facecolor="white", metadata={"Date": None})
    plt.close(figure)
    print(destination.with_suffix(".png"))


def main():
    plot(
        SOURCES,
        50000,
        60,
        "performance-50000-2026-10-13",
        "60-second local samples · 20 readers + 3 writers · 12–13 October 2026",
    )
    plot(
        (
            ("Original baseline", "2026-10-12-baseline", "#AFBAB3"),
            ("Compact indexes + request lookups", "2026-10-13-sustained-100k", "#729582"),
            ("Covering filter counts + scoped types", "2026-10-13-filter-sustained-100k", "#39805A"),
            ("Trigram substring search", "2026-10-14-search-sustained-100k", "#173D2A"),
        ),
        100000,
        1800,
        "performance-100000-sustained-2026-10-14",
        "30-minute local runs · 20 readers + 3 writers · 12–14 October 2026",
        operations=OPERATIONS + (("search", "Substring search miss"),),
    )


if __name__ == "__main__":
    main()
