"""Discover clinical pathway variants and summarize repeated-activity rework."""

import argparse
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd

from data_loader import COLUMN_ALIASES, EXPECTED_MILESTONES


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = REPOSITORY_ROOT / "data" / "raw" / "clinical_events.csv"
DEFAULT_VARIANTS_OUTPUT = (
    REPOSITORY_ROOT / "data" / "processed" / "pathway_variants.csv"
)
DEFAULT_REWORK_OUTPUT = (
    REPOSITORY_ROOT / "data" / "processed" / "rework_summary.csv"
)


def load_events(path):
    """Load and normalize the event columns without rejecting pathway variants."""
    events = pd.read_csv(path)
    if "case_id" not in events.columns:
        raise ValueError("Missing required column: case_id")

    for canonical, aliases in COLUMN_ALIASES.items():
        column = next((name for name in aliases if name in events.columns), None)
        if column is None:
            raise ValueError(f"Missing required column (any of): {aliases}")
        events[canonical] = events[column]

    if events[["case_id", "event_name", "event_timestamp"]].isna().any().any():
        raise ValueError("case_id, event name, and event timestamp cannot be empty")

    try:
        events["event_timestamp"] = pd.to_datetime(
            events["event_timestamp"], errors="raise"
        )
    except (TypeError, ValueError) as error:
        raise ValueError(f"Failed to parse event timestamps: {error}") from error

    return events.sort_values(
        ["case_id", "event_timestamp"], kind="mergesort"
    ).reset_index(drop=True)


def discover_variants(events):
    """Return pathway-variant records and standard-path adherence percentage."""
    pathways = {
        case_id: tuple(case_events["event_name"].astype(str))
        for case_id, case_events in events.groupby("case_id", sort=True)
    }
    if not pathways:
        raise ValueError("The event log contains no patient cases")

    variant_counts = Counter(pathways.values())
    standard_path = tuple(EXPECTED_MILESTONES)
    standard_patient_count = variant_counts.get(standard_path, 0)
    adherence_percentage = 100 * standard_patient_count / len(pathways)

    ordered_variants = sorted(
        variant_counts.items(), key=lambda item: (-item[1], item[0])
    )
    rows = [
        {
            "variant_id": f"V{index:03d}",
            "pathway": " -> ".join(pathway),
            "patient_count": patient_count,
            "patient_percentage": 100 * patient_count / len(pathways),
            "is_standard_happy_path": pathway == standard_path,
            "standard_happy_path_adherence_percentage": adherence_percentage,
        }
        for index, (pathway, patient_count) in enumerate(ordered_variants, start=1)
    ]
    return pd.DataFrame(rows), adherence_percentage, pathways


def summarize_rework(events, pathways):
    """Aggregate patients and extra occurrences for each repeated activity."""
    activity_patients = defaultdict(set)
    activity_occurrences = Counter()
    activity_extra_occurrences = Counter()

    for case_id, _case_events in events.groupby("case_id", sort=True):
        activity_counts = Counter(pathways[case_id])
        for activity, occurrences in activity_counts.items():
            if occurrences > 1:
                activity_patients[activity].add(case_id)
                activity_occurrences[activity] += occurrences
                activity_extra_occurrences[activity] += occurrences - 1

    total_patients = len(pathways)
    rows = [
        {
            "activity": activity,
            "patient_count": len(activity_patients[activity]),
            "extra_occurrences": activity_extra_occurrences[activity],
            "total_occurrences": activity_occurrences[activity],
            "patient_percentage": (
                100 * len(activity_patients[activity]) / total_patients
            ),
        }
        for activity in sorted(activity_patients)
    ]
    if not rows:
        rows.append(
            {
                "activity": "None detected",
                "patient_count": 0,
                "extra_occurrences": 0,
                "total_occurrences": 0,
                "patient_percentage": 0.0,
            }
        )
    return pd.DataFrame(rows)


def main():
    parser = argparse.ArgumentParser(
        description="Discover pathway variants and repeated-activity rework."
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--variants-output", type=Path, default=DEFAULT_VARIANTS_OUTPUT)
    parser.add_argument("--rework-output", type=Path, default=DEFAULT_REWORK_OUTPUT)
    args = parser.parse_args()

    events = load_events(args.input)
    variants, adherence_percentage, pathways = discover_variants(events)
    rework = summarize_rework(events, pathways)

    args.variants_output.parent.mkdir(parents=True, exist_ok=True)
    args.rework_output.parent.mkdir(parents=True, exist_ok=True)
    variants.to_csv(args.variants_output, index=False)
    rework.to_csv(args.rework_output, index=False)

    rework_patients = set()
    for case_id, pathway in pathways.items():
        if len(pathway) != len(set(pathway)):
            rework_patients.add(case_id)

    print(f"Analyzed {len(pathways)} patient cases.")
    print(f"Discovered {len(variants)} unique pathway variants.")
    print(f"Standard happy-path adherence: {adherence_percentage:.2f}%.")
    print(f"Patients with repeated activities: {len(rework_patients)}.")
    print(f"Wrote pathway variants to {args.variants_output}.")
    print(f"Wrote rework summary to {args.rework_output}.")


if __name__ == "__main__":
    main()
