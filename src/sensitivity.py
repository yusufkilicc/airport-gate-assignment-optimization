"""sensitivity.py — Parametric sensitivity analysis for gate-assignment costs.

For each cost parameter in CostWeights we sweep a range of values, re-solve
the MILP, and record how every KPI responds.  The result is a tidy DataFrame
that can be plotted to answer: "how sensitive is the optimal solution to how
we weight each friction type?"

Usage (standalone):
    python sensitivity.py
"""
from __future__ import annotations

from dataclasses import replace
from typing import Dict, List

import pandas as pd

from project_data import create_flights, create_gates
from project_model import CostWeights, optimize_gate_assignment, summarize_solution

# ---------------------------------------------------------------------------
# Parameter sweep definitions
# Each entry: (param_name, display_label, values_to_sweep)
# ---------------------------------------------------------------------------
SWEEP_SPECS: List[tuple] = [
    (
        "remote_penalty",
        "Remote-Stand Penalty",
        [300, 600, 900, 1200, 1500, 1800, 2100, 2400],
    ),
    (
        "zone_penalty",
        "Zone-Mismatch Penalty",
        [0, 70, 140, 210, 280, 350, 420],
    ),
    (
        "walking_multiplier",
        "Walking-Cost Multiplier",
        [0.25, 0.50, 0.75, 1.00, 1.25, 1.50, 1.75, 2.00],
    ),
    (
        "scarcity_penalty",
        "Gate-Scarcity Penalty",
        [0, 60, 120, 180, 240, 300, 360],
    ),
]

KPI_COLS = [
    "total_assignment_cost",
    "remote_flights",
    "zone_mismatch_flights",
    "weighted_avg_walking_m",
    "narrow_on_wide_gates",
    "total_expected_service_extension_min",
]


def run_single_sweep(
    param_name: str,
    param_values: List[float],
    flights: pd.DataFrame,
    gates: pd.DataFrame,
    base_weights: CostWeights | None = None,
) -> pd.DataFrame:
    """Vary one parameter across param_values, keep others at default.

    Returns a DataFrame with columns: [param_name, param_value, *KPI_COLS].
    """
    if base_weights is None:
        base_weights = CostWeights()

    horizon_start = int(flights["arrival_min"].min())
    horizon_end = int(flights["occupied_until_min"].max())

    rows = []
    for value in param_values:
        weights = replace(base_weights, **{param_name: value})
        try:
            assignment = optimize_gate_assignment(flights, gates, weights=weights)
            summary = summarize_solution(assignment, horizon_start, horizon_end)
            row = {col: summary[col].iat[0] for col in KPI_COLS}
        except Exception as exc:
            row = {col: None for col in KPI_COLS}
            row["_error"] = str(exc)
        row["param_name"] = param_name
        row["param_label"] = param_name  # filled in by run_full_sensitivity
        row["param_value"] = value
        rows.append(row)

    return pd.DataFrame(rows)


def run_full_sensitivity(
    flights: pd.DataFrame | None = None,
    gates: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Run all four parameter sweeps and return one combined DataFrame.

    Columns: param_name, param_label, param_value, <KPI columns...>
    """
    if flights is None:
        flights = create_flights()
    if gates is None:
        gates = create_gates()

    base = CostWeights()
    parts = []

    for param_name, display_label, values in SWEEP_SPECS:
        print(f"  Sensitivity sweep: {display_label} ({len(values)} values)...")
        sweep_df = run_single_sweep(param_name, values, flights, gates, base)
        sweep_df["param_label"] = display_label
        parts.append(sweep_df)

    return pd.concat(parts, ignore_index=True)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    from pathlib import Path

    out_dir = Path(__file__).resolve().parents[1] / "outputs"
    out_dir.mkdir(parents=True, exist_ok=True)

    print("Running sensitivity analysis...")
    df = run_full_sensitivity()
    out_path = out_dir / "sensitivity_results.csv"
    df.to_csv(out_path, index=False)
    print(f"Saved → {out_path}")
    print(df.groupby("param_label")[["param_value", "total_assignment_cost", "remote_flights"]].head(3))
