"""Summarize patient length of stay and clinical-stage transition waits."""

import argparse
from pathlib import Path
from statistics import mean, median

import pandas as pd

from data_loader import EXPECTED_MILESTONES, load_event_log


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = REPOSITORY_ROOT / "data" / "raw" / "clinical_events.csv"
DEFAULT_OUTPUT = REPOSITORY_ROOT / "data" / "processed" / "transition_metrics.csv"


def summarize_durations(metric, stage, from_stage, to_stage, durations_hours):
    """Build a summary row for one metric and its duration observations."""
    return {
        "metric": metric,
        "stage": stage,
        "from_stage": from_stage,
        "to_stage": to_stage,
        "patient_count": len(durations_hours),
        "mean_duration_hours": mean(durations_hours),
        "median_duration_hours": median(durations_hours),
        "min_duration_hours": min(durations_hours),
        "max_duration_hours": max(durations_hours),
    }


def analyze_transitions(events):
    """Return summary rows and the median length of stay in hours."""
    length_of_stay_hours = []
    transition_hours = {stage: [] for stage in EXPECTED_MILESTONES[1:]}

    for case_id, case_events in events.groupby("case_id", sort=False):
        event_counts = case_events["event_name"].value_counts()
        invalid = {
            stage: int(event_counts.get(stage, 0))
            for stage in EXPECTED_MILESTONES
            if event_counts.get(stage, 0) != 1
        }
        if invalid or len(case_events) != len(EXPECTED_MILESTONES):
            raise ValueError(
                f"Case {case_id} must contain each expected milestone exactly once; "
                f"invalid counts: {invalid or 'unexpected extra events'}"
            )

        timestamps = (
            case_events.set_index("event_name")
            .loc[EXPECTED_MILESTONES, "event_timestamp"]
            .tolist()
        )
        if any(earlier > later for earlier, later in zip(timestamps, timestamps[1:])):
            raise ValueError(f"Case {case_id} has milestones out of clinical pathway order")

        length_of_stay_hours.append(
            (timestamps[-1] - timestamps[0]).total_seconds() / 3600
        )
        for index, destination in enumerate(EXPECTED_MILESTONES[1:], start=1):
            transition_hours[destination].append(
                (timestamps[index] - timestamps[index - 1]).total_seconds() / 3600
            )

    rows = [
        summarize_durations(
            "patient_los",
            "Length_of_Stay",
            EXPECTED_MILESTONES[0],
            EXPECTED_MILESTONES[-1],
            length_of_stay_hours,
        )
    ]

    for index, destination in enumerate(EXPECTED_MILESTONES[1:], start=1):
        rows.append(
            summarize_durations(
                "transition_wait",
                destination,
                EXPECTED_MILESTONES[index - 1],
                destination,
                transition_hours[destination],
            )
        )

    bottleneck_stage = max(
        EXPECTED_MILESTONES[1:],
        key=lambda stage: mean(transition_hours[stage]),
    )
    bottleneck_index = EXPECTED_MILESTONES.index(bottleneck_stage)
    rows.append(
        summarize_durations(
            "top_bottleneck",
            bottleneck_stage,
            EXPECTED_MILESTONES[bottleneck_index - 1],
            bottleneck_stage,
            transition_hours[bottleneck_stage],
        )
    )
    return rows, median(length_of_stay_hours), bottleneck_stage


def main():
    parser = argparse.ArgumentParser(
        description="Calculate length of stay and stage transition waiting times."
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    events = load_event_log(str(args.input))
    rows, median_los, bottleneck_stage = analyze_transitions(events)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(args.output, index=False)

    bottleneck = next(row for row in rows if row["metric"] == "top_bottleneck")
    print(f"Analyzed {events['case_id'].nunique()} patient cases.")
    print(f"Median length of stay: {median_los:.2f} hours.")
    print(
        f"Top bottleneck stage: {bottleneck_stage} "
        f"(mean wait {bottleneck['mean_duration_hours']:.2f} hours)."
    )
    print(f"Wrote transition metrics to {args.output}.")


if __name__ == "__main__":
    main()
