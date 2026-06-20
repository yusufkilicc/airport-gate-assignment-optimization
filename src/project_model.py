from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from typing import Dict, List, Optional, Tuple

import pandas as pd
import pulp

SIZE_RANK = {"narrow": 1, "wide": 2}


@dataclass
class CostWeights:
    """Tunable cost coefficients for the gate-assignment objective.

    Varying these weights drives the sensitivity analysis: each parameter
    controls how heavily one friction type is penalised relative to others.
    """

    walking_multiplier: float = 1.0
    """Scales the per-passenger walking burden (passengers × distance / 100)."""

    taxi_multiplier: float = 1.0
    """Scales the aircraft taxi-time penalty (30 × taxi_penalty_min)."""

    remote_penalty: float = 1200.0
    """Flat penalty added whenever a flight is sent to a remote stand."""

    zone_penalty: float = 140.0
    """Penalty for assigning a contact gate that is in the wrong terminal zone."""

    scarcity_penalty: float = 180.0
    """Penalty for placing a narrow-body aircraft on a wide-body contact gate."""


DEFAULT_WEIGHTS = CostWeights()


# ---------------------------------------------------------------------------
# Core helpers
# ---------------------------------------------------------------------------


def intervals_overlap(start_a: int, end_a: int, start_b: int, end_b: int) -> bool:
    return not (end_a <= start_b or end_b <= start_a)


def is_compatible(flight: pd.Series, gate: pd.Series) -> bool:
    size_ok = SIZE_RANK[gate["max_size"]] >= SIZE_RANK[flight["aircraft_size"]]
    intl_ok = (flight["international"] == 0) or (gate["international_capable"] == 1)
    return size_ok and intl_ok


def assignment_cost(
    flight: pd.Series,
    gate: pd.Series,
    weights: Optional[CostWeights] = None,
) -> float:
    w = weights if weights is not None else DEFAULT_WEIGHTS
    walking = w.walking_multiplier * flight["passengers"] * gate["walking_distance_m"] / 100.0
    taxi = w.taxi_multiplier * 30.0 * gate["taxi_penalty_min"]
    remote = w.remote_penalty if gate["gate_type"] == "remote" else 0.0
    zone = (
        w.zone_penalty
        if gate["zone"] != flight["preferred_zone"] and gate["gate_type"] == "contact"
        else 0.0
    )
    scarcity = (
        w.scarcity_penalty
        if (
            flight["aircraft_size"] == "narrow"
            and gate["max_size"] == "wide"
            and gate["gate_type"] == "contact"
        )
        else 0.0
    )
    return round(walking + taxi + remote + zone + scarcity, 2)


# ---------------------------------------------------------------------------
# Table builders
# ---------------------------------------------------------------------------


def build_compatibility_table(
    flights: pd.DataFrame, gates: pd.DataFrame
) -> Dict[Tuple[str, str], bool]:
    return {
        (f["flight_id"], g["gate_id"]): is_compatible(f, g)
        for _, f in flights.iterrows()
        for _, g in gates.iterrows()
    }


def build_cost_table(
    flights: pd.DataFrame,
    gates: pd.DataFrame,
    weights: Optional[CostWeights] = None,
) -> Dict[Tuple[str, str], float]:
    w = weights if weights is not None else DEFAULT_WEIGHTS
    return {
        (f["flight_id"], g["gate_id"]): assignment_cost(f, g, w)
        for _, f in flights.iterrows()
        for _, g in gates.iterrows()
        if is_compatible(f, g)
    }


def build_conflict_pairs(flights: pd.DataFrame) -> List[Tuple[str, str]]:
    records = flights.to_dict("records")
    return [
        (a["flight_id"], b["flight_id"])
        for a, b in combinations(records, 2)
        if intervals_overlap(
            a["arrival_min"], a["occupied_until_min"],
            b["arrival_min"], b["occupied_until_min"],
        )
    ]


def _can_use_gate(flight: pd.Series, schedule: List[Tuple[int, int]]) -> bool:
    return all(
        not intervals_overlap(
            flight["arrival_min"], flight["occupied_until_min"], s, e
        )
        for s, e in schedule
    )


# ---------------------------------------------------------------------------
# Assignment algorithms
# ---------------------------------------------------------------------------


def greedy_fcfs_assignment(
    flights: pd.DataFrame,
    gates: pd.DataFrame,
    weights: Optional[CostWeights] = None,
) -> pd.DataFrame:
    """Baseline heuristic: processes flights in arrival order, picks first
    available compatible gate (contact preferred, then remote)."""
    w = weights if weights is not None else DEFAULT_WEIGHTS
    schedule: Dict[str, List[Tuple[int, int]]] = {g: [] for g in gates["gate_id"]}
    assignments = []

    for _, flight in flights.sort_values(["arrival_min", "departure_min", "flight_id"]).iterrows():
        candidates = [
            gate
            for _, gate in gates.iterrows()
            if is_compatible(flight, gate) and _can_use_gate(flight, schedule[gate["gate_id"]])
        ]
        candidates.sort(
            key=lambda g: (
                1 if g["gate_type"] == "remote" else 0,
                g["walking_distance_m"],
                g["taxi_penalty_min"],
                g["gate_id"],
            )
        )
        if not candidates:
            raise RuntimeError(f"No feasible gate for {flight['flight_id']}.")
        chosen = candidates[0]
        schedule[chosen["gate_id"]].append((flight["arrival_min"], flight["occupied_until_min"]))
        assignments.append({"flight_id": flight["flight_id"], "gate_id": chosen["gate_id"]})

    return decorate_assignment(pd.DataFrame(assignments), flights, gates, "Baseline FCFS", w)


def priority_dispatch_assignment(
    flights: pd.DataFrame,
    gates: pd.DataFrame,
    weights: Optional[CostWeights] = None,
) -> pd.DataFrame:
    """Priority Dispatch heuristic: highest-passenger flights are processed
    first so they get first pick of the best available gates.  Within each
    flight the gate is chosen by minimising assignment cost (contact preferred).
    This heuristic outperforms FCFS when passenger load is heterogeneous."""
    w = weights if weights is not None else DEFAULT_WEIGHTS
    schedule: Dict[str, List[Tuple[int, int]]] = {g: [] for g in gates["gate_id"]}
    assignments = []

    # High-passenger flights get priority access to the best gates
    for _, flight in flights.sort_values("passengers", ascending=False).iterrows():
        candidates = [
            gate
            for _, gate in gates.iterrows()
            if is_compatible(flight, gate) and _can_use_gate(flight, schedule[gate["gate_id"]])
        ]
        candidates.sort(
            key=lambda g: (
                1 if g["gate_type"] == "remote" else 0,
                assignment_cost(flight, g, w),
                g["gate_id"],
            )
        )
        if not candidates:
            raise RuntimeError(f"No feasible gate for {flight['flight_id']}.")
        chosen = candidates[0]
        schedule[chosen["gate_id"]].append((flight["arrival_min"], flight["occupied_until_min"]))
        assignments.append({"flight_id": flight["flight_id"], "gate_id": chosen["gate_id"]})

    return decorate_assignment(pd.DataFrame(assignments), flights, gates, "Priority Dispatch", w)


def optimize_gate_assignment(
    flights: pd.DataFrame,
    gates: pd.DataFrame,
    weights: Optional[CostWeights] = None,
) -> pd.DataFrame:
    """MILP (Mixed-Integer Linear Program) solved with CBC.

    Decision variable: x[f,g] ∈ {0,1}
    Objective: minimise Σ c_fg · x_fg
    Constraints:
      1. Each flight assigned to exactly one compatible gate.
      2. Two time-overlapping flights cannot share a gate.
    """
    w = weights if weights is not None else DEFAULT_WEIGHTS

    flight_ids = flights["flight_id"].tolist()
    gate_ids = gates["gate_id"].tolist()
    compat = build_compatibility_table(flights, gates)
    costs = build_cost_table(flights, gates, w)
    conflicts = build_conflict_pairs(flights)

    prob = pulp.LpProblem("gate_assignment", pulp.LpMinimize)
    x = pulp.LpVariable.dicts(
        "x",
        [(f, g) for f in flight_ids for g in gate_ids if compat[(f, g)]],
        cat=pulp.LpBinary,
    )

    # Objective
    prob += pulp.lpSum(costs[(f, g)] * x[(f, g)] for (f, g) in x)

    # Each flight gets exactly one gate
    for f in flight_ids:
        feasible = [g for g in gate_ids if compat[(f, g)]]
        prob += pulp.lpSum(x[(f, g)] for g in feasible) == 1, f"assign_{f}"

    # No two overlapping flights on the same gate
    for f1, f2 in conflicts:
        for g in gate_ids:
            if compat[(f1, g)] and compat[(f2, g)]:
                prob += x[(f1, g)] + x[(f2, g)] <= 1, f"no_overlap_{f1}_{f2}_{g}"

    status = prob.solve(pulp.PULP_CBC_CMD(msg=False))
    if pulp.LpStatus[status] not in {"Optimal", "Feasible"}:
        raise RuntimeError(f"Solver failed: {pulp.LpStatus[status]}")

    assignments = [
        {"flight_id": f, "gate_id": g}
        for f in flight_ids
        for g in gate_ids
        if compat[(f, g)] and pulp.value(x[(f, g)]) > 0.5
    ]
    return decorate_assignment(pd.DataFrame(assignments), flights, gates, "Optimized MILP", w)


# ---------------------------------------------------------------------------
# Post-processing
# ---------------------------------------------------------------------------


def decorate_assignment(
    assignment_df: pd.DataFrame,
    flights: pd.DataFrame,
    gates: pd.DataFrame,
    solution_name: str,
    weights: Optional[CostWeights] = None,
) -> pd.DataFrame:
    w = weights if weights is not None else DEFAULT_WEIGHTS
    merged = (
        assignment_df
        .merge(flights, on="flight_id", how="left")
        .merge(gates, on="gate_id", how="left")
        .sort_values(["arrival_min", "gate_id"])
        .reset_index(drop=True)
    )
    merged["assignment_cost"] = merged.apply(
        lambda row: assignment_cost(row, row, w), axis=1
    )
    merged["expected_service_extension_min"] = (
        merged["taxi_penalty_min"]
        + merged["gate_type"].map({"contact": 0, "remote": 12})
        + (merged["zone"] != merged["preferred_zone"]).astype(int) * 4
    )
    merged["solution"] = solution_name
    return merged


def gate_utilization(
    assignment_df: pd.DataFrame, horizon_start: int, horizon_end: int
) -> pd.DataFrame:
    total = horizon_end - horizon_start
    util = (
        assignment_df
        .assign(occ=lambda df: df["occupied_until_min"] - df["arrival_min"])
        .groupby(["solution", "gate_id", "gate_type"], as_index=False)["occ"]
        .sum()
    )
    util["utilization_pct"] = 100.0 * util["occ"] / total
    return util


def summarize_solution(
    assignment_df: pd.DataFrame, horizon_start: int, horizon_end: int
) -> pd.DataFrame:
    gate_stats = gate_utilization(assignment_df, horizon_start, horizon_end)
    pax = assignment_df["passengers"]
    dist = assignment_df["walking_distance_m"]
    return pd.DataFrame([{
        "solution": assignment_df["solution"].iat[0],
        "total_assignment_cost": round(assignment_df["assignment_cost"].sum(), 2),
        "remote_flights": int((assignment_df["gate_type"] == "remote").sum()),
        "contact_gate_share": round(
            100.0 * (assignment_df["gate_type"] == "contact").mean(), 2
        ),
        "weighted_avg_walking_m": round((pax * dist).sum() / pax.sum(), 2),
        "weighted_passenger_distance_km": round((pax * dist).sum() / 1000.0, 2),
        "zone_mismatch_flights": int(
            (
                (assignment_df["gate_type"] == "contact")
                & (assignment_df["zone"] != assignment_df["preferred_zone"])
            ).sum()
        ),
        "narrow_on_wide_gates": int(
            (
                (assignment_df["gate_type"] == "contact")
                & (assignment_df["aircraft_size"] == "narrow")
                & (assignment_df["max_size"] == "wide")
            ).sum()
        ),
        "total_expected_service_extension_min": round(
            assignment_df["expected_service_extension_min"].sum(), 2
        ),
        "max_gate_utilization_pct": round(gate_stats["utilization_pct"].max(), 2),
    }])
