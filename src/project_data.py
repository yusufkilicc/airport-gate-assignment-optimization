from __future__ import annotations

import random
from typing import Dict, List, Tuple

import pandas as pd

AIRLINE_ZONE_MAP: Dict[str, str] = {
    "TK": "A",
    "PC": "B",
    "AJ": "C",
    "VF": "B",
    "XQ": "D",
}

# (bank_name, start_min, end_min, normal_count)
BANKS: List[Tuple[str, int, int, int]] = [
    ("Morning Bank", 360, 520, 14),
    ("Midday Bank", 690, 810, 10),
    ("Evening Bank", 1020, 1160, 12),
]

# Heavy scenario: +2 flights per bank (42 total flights, about 17% more traffic)
HEAVY_EXTRA: Dict[str, int] = {
    "Morning Bank": 2,
    "Midday Bank": 2,
    "Evening Bank": 2,
}


def minute_to_clock(minute: int) -> str:
    return f"{minute // 60:02d}:{minute % 60:02d}"


def create_gates() -> pd.DataFrame:
    gates = [
        {"gate_id": "A1", "zone": "A", "gate_type": "contact", "max_size": "wide",
         "walking_distance_m": 170, "taxi_penalty_min": 5, "international_capable": 1},
        {"gate_id": "A2", "zone": "A", "gate_type": "contact", "max_size": "narrow",
         "walking_distance_m": 230, "taxi_penalty_min": 6, "international_capable": 1},
        {"gate_id": "B1", "zone": "B", "gate_type": "contact", "max_size": "wide",
         "walking_distance_m": 180, "taxi_penalty_min": 4, "international_capable": 1},
        {"gate_id": "B2", "zone": "B", "gate_type": "contact", "max_size": "narrow",
         "walking_distance_m": 240, "taxi_penalty_min": 5, "international_capable": 1},
        {"gate_id": "C1", "zone": "C", "gate_type": "contact", "max_size": "narrow",
         "walking_distance_m": 280, "taxi_penalty_min": 7, "international_capable": 0},
        {"gate_id": "C2", "zone": "C", "gate_type": "contact", "max_size": "narrow",
         "walking_distance_m": 320, "taxi_penalty_min": 7, "international_capable": 1},
        {"gate_id": "D1", "zone": "D", "gate_type": "contact", "max_size": "narrow",
         "walking_distance_m": 260, "taxi_penalty_min": 6, "international_capable": 1},
        {"gate_id": "R1", "zone": "REMOTE", "gate_type": "remote", "max_size": "wide",
         "walking_distance_m": 920, "taxi_penalty_min": 14, "international_capable": 1},
        {"gate_id": "R2", "zone": "REMOTE", "gate_type": "remote", "max_size": "wide",
         "walking_distance_m": 980, "taxi_penalty_min": 15, "international_capable": 1},
        {"gate_id": "R3", "zone": "REMOTE", "gate_type": "remote", "max_size": "wide",
         "walking_distance_m": 1050, "taxi_penalty_min": 16, "international_capable": 1},
        {"gate_id": "R4", "zone": "REMOTE", "gate_type": "remote", "max_size": "wide",
         "walking_distance_m": 1110, "taxi_penalty_min": 17, "international_capable": 1},
    ]
    return pd.DataFrame(gates)


def _turnaround_minutes(rng: random.Random, aircraft_size: str) -> int:
    return rng.randint(105, 155) if aircraft_size == "wide" else rng.randint(55, 95)


def _passengers(rng: random.Random, aircraft_size: str) -> int:
    return rng.randint(250, 340) if aircraft_size == "wide" else rng.randint(120, 205)


def _generate_bank(
    rng: random.Random,
    bank_name: str,
    bank_start: int,
    bank_end: int,
    count: int,
) -> List[dict]:
    """Generate one bank of flights using the shared RNG."""
    arrivals = sorted(rng.randint(bank_start, bank_end) for _ in range(count))
    records = []
    for arrival_min in arrivals:
        airline = rng.choices(
            population=list(AIRLINE_ZONE_MAP.keys()),
            weights=[0.42, 0.20, 0.10, 0.14, 0.14],
            k=1,
        )[0]
        preferred_zone = AIRLINE_ZONE_MAP[airline]
        aircraft_size = rng.choices(["narrow", "wide"], weights=[0.78, 0.22], k=1)[0]
        international = int(rng.random() < (0.65 if aircraft_size == "wide" else 0.45))
        turnaround_min = _turnaround_minutes(rng, aircraft_size)
        if bank_name != "Midday Bank" and rng.random() < 0.30:
            turnaround_min += rng.randint(8, 20)
        departure_min = arrival_min + turnaround_min
        passengers = _passengers(rng, aircraft_size)
        records.append({
            "bank_name": bank_name,
            "airline": airline,
            "preferred_zone": preferred_zone,
            "aircraft_size": aircraft_size,
            "international": international,
            "arrival_min": arrival_min,
            "turnaround_min": turnaround_min,
            "departure_min": departure_min,
            "occupied_until_min": departure_min + 15,
            "passengers": passengers,
        })
    return records


def _finalise(records: List[dict]) -> pd.DataFrame:
    flights = (
        pd.DataFrame(records)
        .sort_values(["arrival_min", "departure_min"])
        .reset_index(drop=True)
    )
    flights["flight_id"] = [f"F{i:02d}" for i in range(1, len(flights) + 1)]
    flights["arrival_clock"] = flights["arrival_min"].apply(minute_to_clock)
    flights["departure_clock"] = flights["departure_min"].apply(minute_to_clock)
    ordered = [
        "flight_id", "bank_name", "airline", "preferred_zone", "aircraft_size",
        "international", "arrival_min", "arrival_clock", "departure_min",
        "departure_clock", "turnaround_min", "occupied_until_min", "passengers",
    ]
    return flights[ordered]


def create_flights(seed: int = 4313) -> pd.DataFrame:
    """Normal scenario: 36 flights across three traffic banks."""
    rng = random.Random(seed)
    records = []
    for bank_name, bank_start, bank_end, count in BANKS:
        records.extend(_generate_bank(rng, bank_name, bank_start, bank_end, count))
    return _finalise(records)


def create_scenario_flights(scenario: str = "normal", seed: int = 4313) -> pd.DataFrame:
    """Generate flights for a named operating scenario.

    Parameters
    ----------
    scenario:
        ``"normal"`` - 36 flights, baseline day (identical to create_flights).
        ``"heavy"`` - 42 flights, about 17% more traffic; tests stand-capacity limits.
        ``"disruption"`` - 36 flights with pre-applied random arrival delays on
        about 35% of flights (15-50 min), simulating a disrupted day.
    seed:
        Random seed for reproducibility.
    """
    if scenario == "normal":
        return create_flights(seed)

    rng = random.Random(seed)
    records = []

    if scenario == "heavy":
        for bank_name, bank_start, bank_end, count in BANKS:
            extra = HEAVY_EXTRA.get(bank_name, 0)
            records.extend(
                _generate_bank(rng, bank_name, bank_start, bank_end, count + extra)
            )

    elif scenario == "disruption":
        for bank_name, bank_start, bank_end, count in BANKS:
            records.extend(_generate_bank(rng, bank_name, bank_start, bank_end, count))
        # Apply disruptions: about 35% of flights delayed 15-50 min.
        delay_rng = random.Random(seed + 1)
        for rec in records:
            if delay_rng.random() < 0.35:
                delay = delay_rng.randint(15, 50)
                rec["arrival_min"] += delay
                rec["departure_min"] += delay
                rec["occupied_until_min"] += delay

    else:
        raise ValueError(f"Unknown scenario '{scenario}'. Choose normal/heavy/disruption.")

    return _finalise(records)
