from __future__ import annotations

from pathlib import Path
from textwrap import fill

import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch


ROOT = Path(__file__).resolve().parents[1]
FIG_DIR = ROOT / "outputs" / "figures"

BLUE = "#1F4E79"
LIGHT_BLUE = "#D9EAF7"
MID_BLUE = "#8FB9D6"
GREEN = "#DDEED9"
LIGHT_ORANGE = "#FCE4D6"
GRAY = "#F4F6F8"
DARK = "#1F2933"


def add_box(
    ax,
    x: float,
    y: float,
    w: float,
    h: float,
    title: str,
    body: str = "",
    fill_color: str = LIGHT_BLUE,
    edge_color: str = BLUE,
    title_size: int = 11,
    body_size: int = 9,
    wrap_title: int = 24,
    wrap_body: int = 34,
) -> None:
    box = FancyBboxPatch(
        (x, y),
        w,
        h,
        boxstyle="round,pad=0.02,rounding_size=0.035",
        linewidth=1.4,
        edgecolor=edge_color,
        facecolor=fill_color,
    )
    ax.add_patch(box)
    ax.text(
        x + w / 2,
        y + h * 0.63,
        fill(title, wrap_title),
        ha="center",
        va="center",
        fontsize=title_size,
        fontweight="bold",
        color=DARK,
    )
    if body:
        ax.text(
            x + w / 2,
            y + h * 0.30,
            fill(body, wrap_body),
            ha="center",
            va="center",
            fontsize=body_size,
            color=DARK,
        )


def add_arrow(ax, start: tuple[float, float], end: tuple[float, float], rad: float = 0.0) -> None:
    arrow = FancyArrowPatch(
        start,
        end,
        arrowstyle="-|>",
        mutation_scale=15,
        linewidth=1.4,
        color=BLUE,
        connectionstyle=f"arc3,rad={rad}",
    )
    ax.add_patch(arrow)


def add_line(ax, start: tuple[float, float], end: tuple[float, float]) -> None:
    ax.plot([start[0], end[0]], [start[1], end[1]], color=BLUE, linewidth=1.4)


def setup_ax(width: float = 13.0, height: float = 7.2):
    fig, ax = plt.subplots(figsize=(width, height), dpi=220)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")
    return fig, ax


def save(fig, filename: str) -> Path:
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    out = FIG_DIR / filename
    fig.savefig(out, bbox_inches="tight", pad_inches=0.18)
    plt.close(fig)
    return out


def create_gate_assignment_logic() -> Path:
    fig, ax = setup_ax(8.2, 8.0)
    ax.text(
        0.5,
        0.96,
        "Conceptual Gate Assignment Decision Flow",
        ha="center",
        va="top",
        fontsize=15,
        fontweight="bold",
        color=BLUE,
    )

    top_w, top_h = 0.32, 0.12
    add_box(
        ax,
        0.12,
        0.78,
        top_w,
        top_h,
        "Flight Schedule",
        "arrival, departure, aircraft type, passengers",
        LIGHT_BLUE,
        title_size=10,
        body_size=8.5,
    )
    add_box(
        ax,
        0.56,
        0.78,
        top_w,
        top_h,
        "Gate and Stand Inventory",
        "contact gates, remote stands, walking distances",
        LIGHT_BLUE,
        title_size=10,
        body_size=8.5,
    )

    center_w, center_h = 0.48, 0.115
    stages = [
        (0.26, 0.61, "Feasibility Screening", "aircraft compatibility and time-overlap constraints", GREEN),
        (0.26, 0.45, "Cost Evaluation", "walking distance, remote use, zone mismatch, gate scarcity", LIGHT_ORANGE),
        (0.26, 0.29, "Assignment Policy", "FCFS, Priority Dispatch, or MILP optimization", LIGHT_ORANGE),
        (0.26, 0.13, "Final Gate / Stand Plan", "feasible daily assignment and operational KPIs", GRAY),
    ]
    for x, y, title, body, color in stages:
        add_box(
            ax,
            x,
            y,
            center_w,
            center_h,
            title,
            body,
            color,
            title_size=10,
            body_size=8.5,
            wrap_body=42,
        )

    # Two clean input arrows feed the central decision flow. All remaining
    # arrows are vertical to avoid visual crossings when inserted in Word.
    add_arrow(ax, (0.28, 0.78), (0.40, 0.725), rad=-0.07)
    add_arrow(ax, (0.72, 0.78), (0.60, 0.725), rad=0.07)
    add_arrow(ax, (0.50, 0.61), (0.50, 0.565))
    add_arrow(ax, (0.50, 0.45), (0.50, 0.405))
    add_arrow(ax, (0.50, 0.29), (0.50, 0.245))

    ax.text(
        0.5,
        0.05,
        "Each flight is assigned only after feasibility checks, then evaluated against service and capacity trade-offs.",
        ha="center",
        va="center",
        fontsize=8.8,
        color="#4B5563",
    )
    return save(fig, "gate_assignment_logic.png")


def create_methodology_flowchart() -> Path:
    fig, ax = setup_ax(8.5, 9.0)
    ax.text(
        0.5,
        0.965,
        "Gate Allocation and Apron-Capacity Methodology",
        ha="center",
        va="top",
        fontsize=15,
        fontweight="bold",
        color=BLUE,
    )

    w, h = 0.58, 0.105
    x = 0.21
    stages = [
        (0.80, "1. Data Preparation", "flight schedule, aircraft information, and stand inventory", LIGHT_BLUE),
        (0.665, "2. Parameter and Matrix Construction", "compatibility, time-overlap, walking-distance, and penalty matrices", GREEN),
        (0.530, "3. Assignment Model Evaluation", "FCFS baseline, Priority Dispatch, and Optimized MILP", LIGHT_ORANGE),
        (0.395, "4. KPI Comparison", "total cost, remote use, walking burden, mismatch, and feasibility", GRAY),
        (0.260, "5. Robustness Testing", "sensitivity analysis, delay simulation, and demand scenarios", GREEN),
        (0.125, "6. Planning Interpretation", "capacity insight and operational recommendations", LIGHT_BLUE),
    ]
    for y, title, body, color in stages:
        add_box(
            ax,
            x,
            y,
            w,
            h,
            title,
            body,
            color,
            title_size=10,
            body_size=8.4,
            wrap_title=36,
            wrap_body=54,
        )

    for start_y, end_y in [
        (0.80, 0.770),
        (0.665, 0.635),
        (0.530, 0.500),
        (0.395, 0.365),
        (0.260, 0.230),
    ]:
        add_arrow(ax, (0.50, start_y), (0.50, end_y))

    ax.text(
        0.5,
        0.055,
        "The workflow compares rule-based and optimization-based assignments under the same airport-capacity assumptions.",
        ha="center",
        va="center",
        fontsize=8.8,
        color="#4B5563",
    )
    return save(fig, "methodology_flowchart.png")


def main() -> None:
    out1 = create_gate_assignment_logic()
    out2 = create_methodology_flowchart()
    print(out1)
    print(out2)


if __name__ == "__main__":
    main()
