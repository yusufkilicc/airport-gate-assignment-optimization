"""simulation.py — Stochastic robustness simulation for gate-assignment policies.

We generate N random delay scenarios by applying random arrival/departure
delays to a fraction of flights, then re-run all three assignment algorithms
(FCFS, Priority Dispatch, MILP) on each perturbed schedule and compare the
resulting KPIs.

This answers: "Which policy degrades least gracefully under operational
disruptions?"

Usage (standalone):
    python simulation.py
"""
from __future__ import annotations

import random
from typing import List

import pandas as pd

from project_data import create_flights, create_gates
from project_model import (
    CostWeights,
    greedy_fcfs_assignment,
    optimize_gate_assignment,
    priority_dispatch_assignment,
    summarize_solution,
)

# ---------------------------------------------------------------------------
# Default simulation parameters
# ---------------------------------------------------------------------------
N_SCENARIOS: int = 100
DELAY_PROB: float = 0.30        # fraction of flights that receive a delay
MIN_DELAY_MIN: int = 10         # minimum delay in minutes
MAX_DELAY_MIN: int = 60         # maximum delay in minutes
BASE_SEED: int = 2025


def apply_delays(
    flights: pd.DataFrame,
    delay_prob: float = DELAY_PROB,
    min_delay: int = MIN_DELAY_MIN,
    max_delay: int = MAX_DELAY_MIN,
    rng: random.Random | None = None,
) -> pd.DataFrame:
    """Return a copy of *flights* with random arrival/departure shifts applied.

    Each flight is independently delayed with probability *delay_prob* by a
    uniform draw from [min_delay, max_delay] minutes.
    """
    if rng is None:
        rng = random.Random()
    df = flights.copy()
    for idx in df.index:
        if rng.random() < delay_prob:
            delay = rng.randint(min_delay, max_delay)
            df.at[idx, "arrival_min"] += delay
            df.at[idx, "departure_min"] += delay
            df.at[idx, "occupied_until_min"] += delay
    return df


_METHODS = {
    "FCFS": greedy_fcfs_assignment,
    "Priority Dispatch": priority_dispatch_assignment,
    "Optimized MILP": optimize_gate_assignment,
}


def run_simulation(
    flights: pd.DataFrame | None = None,
    gates: pd.DataFrame | None = None,
    n_scenarios: int = N_SCENARIOS,
    delay_prob: float = DELAY_PROB,
    min_delay: int = MIN_DELAY_MIN,
    max_delay: int = MAX_DELAY_MIN,
    seed: int = BASE_SEED,
    weights: CostWeights | None = None,
) -> pd.DataFrame:
    """Run *n_scenarios* random delay scenarios and evaluate all three policies.

    Returns a tidy DataFrame with one row per (scenario, method):

    Columns
    -------
    scenario         : int, scenario index 0..n-1
    method           : str, algorithm name
    feasible         : bool, True if a valid assignment was found
    total_cost       : float or NaN
    remote_flights   : int or NaN
    zone_mismatches  : int or NaN
    weighted_walk_m  : float or NaN
    service_ext_min  : float or NaN
    n_delayed        : int, number of flights that received a delay
    """
    if flights is None:
        flights = create_flights()
    if gates is None:
        gates = create_gates()
    if weights is None:
        weights = CostWeights()

    master_rng = random.Random(seed)
    scenario_seeds: List[int] = [master_rng.randint(0, 2**31) for _ in range(n_scenarios)]

    # Extend horizon to accommodate worst-case delays
    horizon_start = int(flights["arrival_min"].min()) - 30
    horizon_end = int(flights["occupied_until_min"].max()) + max_delay + 30

    records = []
    for i, sc_seed in enumerate(scenario_seeds):
        rng = random.Random(sc_seed)
        delayed = apply_delays(flights, delay_prob, min_delay, max_delay, rng)
        n_delayed = int((delayed["arrival_min"] != flights["arrival_min"]).sum())

        for method_name, func in _METHODS.items():
            try:
                assignment = func(delayed, gates, weights=weights)
                summary = summarize_solution(assignment, horizon_start, horizon_end)
                records.append({
                    "scenario": i,
                    "method": method_name,
                    "feasible": True,
                    "total_cost": summary["total_assignment_cost"].iat[0],
                    "remote_flights": summary["remote_flights"].iat[0],
                    "zone_mismatches": summary["zone_mismatch_flights"].iat[0],
                    "weighted_walk_m": summary["weighted_avg_walking_m"].iat[0],
                    "service_ext_min": summary["total_expected_service_extension_min"].iat[0],
                    "n_delayed": n_delayed,
                })
            except Exception:
                records.append({
                    "scenario": i,
                    "method": method_name,
                    "feasible": False,
                    "total_cost": float("nan"),
                    "remote_flights": float("nan"),
                    "zone_mismatches": float("nan"),
                    "weighted_walk_m": float("nan"),
                    "service_ext_min": float("nan"),
                    "n_delayed": n_delayed,
                })

    return pd.DataFrame(records)


def summarize_simulation(sim_df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate simulation results: mean, std, feasibility rate per method."""
    metrics = ["total_cost", "remote_flights", "zone_mismatches",
               "weighted_walk_m", "service_ext_min"]
    agg = (
        sim_df[sim_df["feasible"]]
        .groupby("method")[metrics]
        .agg(["mean", "std"])
    )
    agg.columns = [f"{m}_{s}" for m, s in agg.columns]
    agg = agg.reset_index()

    feasibility = (
        sim_df.groupby("method")["feasible"]
        .mean()
        .reset_index()
        .rename(columns={"feasible": "feasibility_rate"})
    )
    return agg.merge(feasibility, on="method")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    from pathlib import Path

    out_dir = Path(__file__).resolve().parents[1] / "outputs"
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"Running simulation ({N_SCENARIOS} scenarios)...")
    sim_df = run_simulation()
    sim_path = out_dir / "simulation_results.csv"
    sim_df.to_csv(sim_path, index=False)
    print(f"Saved raw results → {sim_path}")

    summary = summarize_simulation(sim_df)
    print("\nSimulation summary:")
    print(summary.to_string(index=False))
