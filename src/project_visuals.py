"""project_visuals.py — All static (Matplotlib/Seaborn) visualisations.

Each function saves a PNG to *output_path* and closes the figure cleanly.
"""
from __future__ import annotations

from typing import List

import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

sns.set_theme(style="whitegrid", font_scale=1.05)

PALETTE = {
    "Baseline FCFS": "#CC5A3C",
    "Priority Dispatch": "#E8A838",
    "Optimized MILP": "#1F5E7A",
    "contact": "#2A7F62",
    "remote": "#D78C1F",
    "narrow": "#4C78A8",
    "wide": "#F58518",
}

METHOD_ORDER = ["Baseline FCFS", "Priority Dispatch", "Optimized MILP"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _minute_to_clock(minute: int) -> str:
    return f"{minute // 60:02d}:{minute % 60:02d}"


def _add_improvement_label(ax, bars, baseline_val: float, fmt: str = ".0f") -> None:
    """Annotate bars with their absolute value; mark % change from baseline."""
    for i, bar in enumerate(bars):
        h = bar.get_height()
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            h + max(baseline_val, 1) * 0.02,
            f"{h:{fmt}}",
            ha="center", va="bottom", fontsize=8.5, fontweight="bold",
        )
        if i > 0 and baseline_val > 0:
            pct = 100.0 * (h - baseline_val) / baseline_val
            color = "#1a7a40" if pct < 0 else "#a02020"
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                h * 0.50,
                f"{pct:+.1f}%",
                ha="center", va="center", fontsize=7.5,
                color="white", fontweight="bold",
            )


# ---------------------------------------------------------------------------
# 1. Capacity demand profile
# ---------------------------------------------------------------------------

def plot_capacity_profile(
    flights: pd.DataFrame,
    contact_gate_count: int,
    output_path: str,
) -> None:
    timeline = list(range(
        int(flights["arrival_min"].min()) - 15,
        int(flights["occupied_until_min"].max()) + 15,
        15,
    ))
    load_rows = []
    for minute in timeline:
        n = int(((flights["arrival_min"] <= minute) & (minute < flights["occupied_until_min"])).sum())
        load_rows.append({"minute": minute, "concurrent_flights": n})
    load_df = pd.DataFrame(load_rows)

    fig, ax = plt.subplots(figsize=(13, 5))
    ax.plot(
        load_df["minute"], load_df["concurrent_flights"],
        color=PALETTE["Optimized MILP"], linewidth=2.5, label="Concurrent flights",
    )
    ax.axhline(
        contact_gate_count, color=PALETTE["Baseline FCFS"],
        linestyle="--", linewidth=2, label=f"Contact gate capacity ({contact_gate_count})",
    )
    ax.fill_between(
        load_df["minute"], contact_gate_count, load_df["concurrent_flights"],
        where=load_df["concurrent_flights"] > contact_gate_count,
        color=PALETTE["Baseline FCFS"], alpha=0.20, interpolate=True,
        label="Overflow → remote stand required",
    )
    # Annotate traffic banks
    bank_spans = [
        ("Morning\nBank", 360, 520),
        ("Midday\nBank", 690, 810),
        ("Evening\nBank", 1020, 1160),
    ]
    for label, start, end in bank_spans:
        ax.axvspan(start, end, color="#aaaaaa", alpha=0.10)
        ax.text((start + end) / 2, contact_gate_count + 0.4, label,
                ha="center", va="bottom", fontsize=8, color="#555555")

    ticks = load_df["minute"][::4]
    ax.set_xticks(ticks)
    ax.set_xticklabels([_minute_to_clock(m) for m in ticks], rotation=45)
    ax.set_title("Peak-Day Gate Demand Profile", fontsize=14, pad=12)
    ax.set_xlabel("Time of day")
    ax.set_ylabel("Flights occupying stands")
    ax.legend(frameon=True, loc="upper right")
    fig.tight_layout()
    fig.savefig(output_path, dpi=200)
    plt.close(fig)


# ---------------------------------------------------------------------------
# 2. KPI comparison — three methods side by side
# ---------------------------------------------------------------------------

def plot_kpi_comparison(kpi_df: pd.DataFrame, output_path: str) -> None:
    metrics = [
        ("total_assignment_cost",               "Total Assignment Cost"),
        ("weighted_avg_walking_m",              "Weighted Avg Walk (m)"),
        ("zone_mismatch_flights",               "Zone Mismatch Flights"),
        ("narrow_on_wide_gates",                "Narrow on Wide Gates"),
        ("total_expected_service_extension_min","Service Extension (min)"),
        ("remote_flights",                      "Remote Flights"),
    ]

    present = [m for m in METHOD_ORDER if m in kpi_df["solution"].values]
    colors = [PALETTE[m] for m in present]

    fig, axes = plt.subplots(2, 3, figsize=(15, 9))
    axes = axes.flatten()

    for ax, (col, label) in zip(axes, metrics):
        subset = kpi_df[kpi_df["solution"].isin(present)].copy()
        subset = subset.set_index("solution").reindex(present).reset_index()
        bars = ax.bar(subset["solution"], subset[col], color=colors, width=0.55)
        baseline_val = subset.loc[subset["solution"] == "Baseline FCFS", col]
        bv = float(baseline_val.iloc[0]) if len(baseline_val) else 0.0
        _add_improvement_label(ax, bars, bv)
        ax.set_title(label, fontsize=11, fontweight="bold")
        ax.set_xlabel("")
        ax.tick_params(axis="x", rotation=20, labelsize=8)
        ax.grid(axis="y", linestyle="--", alpha=0.4)
        ax.set_ylim(0, max(subset[col].max() * 1.25, 1))

    fig.suptitle("Algorithm Comparison — KPI Dashboard", fontsize=15, y=1.01)
    # Legend
    patches = [mpatches.Patch(color=PALETTE[m], label=m) for m in present]
    fig.legend(handles=patches, loc="lower center", ncol=3, fontsize=10,
               bbox_to_anchor=(0.5, -0.04))
    fig.tight_layout()
    fig.savefig(output_path, dpi=200, bbox_inches="tight")
    plt.close(fig)


# ---------------------------------------------------------------------------
# 3. Gantt chart
# ---------------------------------------------------------------------------

def plot_assignment_gantt(assignment_df: pd.DataFrame, output_path: str) -> None:
    gate_order = (
        assignment_df[["gate_id", "gate_type"]]
        .drop_duplicates()
        .sort_values(["gate_type", "gate_id"])["gate_id"]
        .tolist()
    )
    y_pos = {g: i for i, g in enumerate(gate_order)}

    fig, ax = plt.subplots(figsize=(15, 6))

    for _, row in assignment_df.iterrows():
        color = PALETTE[row["aircraft_size"]]
        edge = "#ffffff"
        ax.barh(
            y=y_pos[row["gate_id"]],
            width=row["occupied_until_min"] - row["arrival_min"],
            left=row["arrival_min"],
            height=0.68,
            color=color,
            edgecolor=edge,
            alpha=0.92,
        )
        # Flight ID label
        bar_width = row["occupied_until_min"] - row["arrival_min"]
        if bar_width > 20:
            ax.text(
                row["arrival_min"] + bar_width / 2,
                y_pos[row["gate_id"]],
                f"{row['flight_id']}\n{row['passengers']}pax",
                va="center", ha="center",
                fontsize=6.5, color="white", fontweight="bold",
            )

    # Remote/contact divider
    n_contact = sum(1 for g in gate_order if assignment_df.loc[
        assignment_df["gate_id"] == g, "gate_type"].iloc[0] == "contact")
    ax.axhline(n_contact - 0.5, color="#888", linestyle=":", linewidth=1.2)
    ax.text(
        assignment_df["arrival_min"].min() - 20, n_contact - 0.5,
        "remote ↓", va="center", ha="right", fontsize=8, color="#888",
    )

    ax.set_yticks(list(y_pos.values()))
    ax.set_yticklabels(gate_order)
    ticks = list(range(
        int(assignment_df["arrival_min"].min()) - 30,
        int(assignment_df["occupied_until_min"].max()) + 30, 60,
    ))
    ax.set_xticks(ticks)
    ax.set_xticklabels([_minute_to_clock(t) for t in ticks], rotation=45)
    ax.set_xlabel("Time of day")
    ax.set_ylabel("Gate / Stand")
    ax.set_title(
        f"{assignment_df['solution'].iat[0]} — Gate Schedule",
        fontsize=13, fontweight="bold",
    )

    patches = [
        mpatches.Patch(color=PALETTE["narrow"], label="Narrow-body"),
        mpatches.Patch(color=PALETTE["wide"], label="Wide-body"),
    ]
    ax.legend(handles=patches, loc="upper right", fontsize=9)
    fig.tight_layout()
    fig.savefig(output_path, dpi=200)
    plt.close(fig)


# ---------------------------------------------------------------------------
# 4. Turnaround distribution
# ---------------------------------------------------------------------------

def plot_turnaround_distribution(flights: pd.DataFrame, output_path: str) -> None:
    fig, ax = plt.subplots(figsize=(10, 5))
    sns.boxplot(
        data=flights, x="aircraft_size", y="turnaround_min",
        hue="international",
        palette=["#4C78A8", "#CC5A3C"],
        ax=ax,
    )
    ax.set_title("Turnaround Time Distribution by Aircraft Type", fontsize=13)
    ax.set_xlabel("Aircraft size")
    ax.set_ylabel("Turnaround time (min)")
    handles, _ = ax.get_legend_handles_labels()
    ax.legend(handles, ["Domestic", "International"], title="")
    fig.tight_layout()
    fig.savefig(output_path, dpi=200)
    plt.close(fig)


# ---------------------------------------------------------------------------
# 5. Sensitivity analysis — four-panel line chart
# ---------------------------------------------------------------------------

def plot_sensitivity(sensitivity_df: pd.DataFrame, output_path: str) -> None:
    """Four-panel plot: one panel per swept parameter, showing how KPIs respond."""
    params = sensitivity_df["param_label"].unique()
    kpi_lines = [
        ("total_assignment_cost",  "Total Cost",         PALETTE["Optimized MILP"], "-"),
        ("zone_mismatch_flights",  "Zone Mismatches",    PALETTE["Baseline FCFS"],  "--"),
        ("weighted_avg_walking_m", "Avg Walk (m)",       PALETTE["Priority Dispatch"], "-."),
    ]

    n = len(params)
    cols = 2
    rows = (n + 1) // cols
    fig, axes = plt.subplots(rows, cols, figsize=(14, rows * 4.5))
    axes = axes.flatten()

    for ax, param in zip(axes, params):
        sub = sensitivity_df[sensitivity_df["param_label"] == param].copy()
        ax2 = ax.twinx()

        for col, label, color, ls in kpi_lines:
            if col == "weighted_avg_walking_m":
                ax2.plot(sub["param_value"], sub[col], color=color, linestyle=ls,
                         linewidth=2, marker="s", markersize=5, label=label)
            else:
                ax.plot(sub["param_value"], sub[col], color=color, linestyle=ls,
                        linewidth=2, marker="o", markersize=5, label=label)

        # Mark default value
        param_name = sub["param_name"].iat[0]
        from project_model import CostWeights
        default_val = getattr(CostWeights(), param_name)
        ax.axvline(default_val, color="#aaaaaa", linestyle=":", linewidth=1.5,
                   label=f"Default ({default_val})")

        ax.set_title(param, fontsize=11, fontweight="bold")
        ax.set_xlabel("Parameter value")
        ax.set_ylabel("Cost / Mismatch count", color=PALETTE["Optimized MILP"])
        ax2.set_ylabel("Avg walk (m)", color=PALETTE["Priority Dispatch"])

        lines1, labels1 = ax.get_legend_handles_labels()
        lines2, labels2 = ax2.get_legend_handles_labels()
        ax.legend(lines1 + lines2, labels1 + labels2, fontsize=8, loc="upper right")

    for ax in axes[n:]:
        ax.axis("off")

    fig.suptitle("Sensitivity Analysis — MILP Objective Weights", fontsize=14, y=1.01)
    fig.tight_layout()
    fig.savefig(output_path, dpi=200, bbox_inches="tight")
    plt.close(fig)


# ---------------------------------------------------------------------------
# 6. Simulation robustness — box plots
# ---------------------------------------------------------------------------

def plot_simulation_results(sim_df: pd.DataFrame, output_path: str) -> None:
    """Box-plot comparison of all three methods across 100 delay scenarios."""
    feasible = sim_df[sim_df["feasible"]].copy()
    present_methods = [m for m in METHOD_ORDER if m in feasible["method"].unique()]
    colors = [PALETTE[m] for m in present_methods]

    metrics = [
        ("total_cost",       "Total Assignment Cost"),
        ("remote_flights",   "Remote Flights"),
        ("zone_mismatches",  "Zone Mismatches"),
        ("weighted_walk_m",  "Weighted Avg Walk (m)"),
    ]

    fig, axes = plt.subplots(2, 2, figsize=(13, 9))
    axes = axes.flatten()

    for ax, (col, label) in zip(axes, metrics):
        sns.boxplot(
            data=feasible[feasible["method"].isin(present_methods)],
            x="method", y=col,
            order=present_methods,
            hue="method",
            palette={m: PALETTE[m] for m in present_methods},
            legend=False,
            ax=ax,
            width=0.55,
            flierprops=dict(marker="o", markersize=3, alpha=0.4),
        )
        ax.set_title(label, fontsize=11, fontweight="bold")
        ax.set_xlabel("")
        ax.set_ylabel(label)
        ax.tick_params(axis="x", rotation=15, labelsize=8)
        ax.grid(axis="y", linestyle="--", alpha=0.35)

    # Feasibility rate annotation
    feas_rate = sim_df.groupby("method")["feasible"].mean()
    title_suffix = "  |  Feasibility: " + ", ".join(
        f"{m}: {feas_rate.get(m, 0):.0%}" for m in present_methods
    )

    fig.suptitle(
        f"Robustness Simulation — {sim_df['scenario'].nunique()} Delay Scenarios{title_suffix}",
        fontsize=12, y=1.01,
    )
    fig.tight_layout()
    fig.savefig(output_path, dpi=200, bbox_inches="tight")
    plt.close(fig)


# ---------------------------------------------------------------------------
# 7. Scenario comparison (normal / heavy / disruption)
# ---------------------------------------------------------------------------

def plot_scenario_comparison(scenario_kpi_df: pd.DataFrame, output_path: str) -> None:
    """Bar chart comparing MILP KPIs across three operating scenarios."""
    metrics = [
        ("total_assignment_cost",  "Total Cost"),
        ("remote_flights",         "Remote Flights"),
        ("weighted_avg_walking_m", "Avg Walk (m)"),
        ("zone_mismatch_flights",  "Zone Mismatches"),
    ]
    scenarios = scenario_kpi_df["scenario"].unique()
    scenario_colors = {"normal": "#1F5E7A", "heavy": "#CC5A3C", "disruption": "#E8A838"}

    fig, axes = plt.subplots(2, 2, figsize=(13, 8))
    axes = axes.flatten()

    for ax, (col, label) in zip(axes, metrics):
        sub = scenario_kpi_df[scenario_kpi_df["solution"] == "Optimized MILP"]
        bars = ax.bar(
            sub["scenario"], sub[col],
            color=[scenario_colors.get(s, "#888") for s in sub["scenario"]],
            width=0.55,
        )
        for bar in bars:
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() * 1.02,
                f"{bar.get_height():.0f}",
                ha="center", va="bottom", fontsize=9, fontweight="bold",
            )
        ax.set_title(label, fontsize=11, fontweight="bold")
        ax.set_xlabel("Scenario")
        ax.set_ylabel(label)
        ax.grid(axis="y", linestyle="--", alpha=0.35)

    fig.suptitle("MILP Performance Across Operating Scenarios", fontsize=13)
    patches = [mpatches.Patch(color=c, label=s.capitalize())
               for s, c in scenario_colors.items()]
    fig.legend(handles=patches, loc="lower center", ncol=3, bbox_to_anchor=(0.5, -0.04))
    fig.tight_layout()
    fig.savefig(output_path, dpi=200, bbox_inches="tight")
    plt.close(fig)
