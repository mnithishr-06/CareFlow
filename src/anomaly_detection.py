"""Detect timestamp, transition-wait, and incomplete-trace anomalies."""

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

from data_loader import COLUMN_ALIASES, EXPECTED_MILESTONES, REQUIRED_COLUMNS


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = REPOSITORY_ROOT / "data" / "raw" / "clinical_events.csv"
DEFAULT_OUTPUT = (
    REPOSITORY_ROOT / "data" / "processed" / "clinical_anomalies.csv"
)
DEFAULT_VISUAL_OUTPUT = (
    REPOSITORY_ROOT / "visuals" / "anomaly_distribution.png"
)
ANOMALY_TYPES = (
    "timestamp_inversion",
    "extreme_wait_outlier",
    "incomplete_trace",
)
AUDIT_COLUMNS = (
    "case_id",
    "patient_id",
    "anomaly_type",
    "source_stage",
    "target_stage",
    "observed_wait_hours",
    "threshold_hours",
    "details",
)


def load_audit_events(path):
    """Load and normalize event columns without rejecting incomplete traces."""
    events = pd.read_csv(path)
    missing = [column for column in REQUIRED_COLUMNS if column not in events.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    for canonical, aliases in COLUMN_ALIASES.items():
        if canonical not in events.columns:
            found = next((alias for alias in aliases if alias in events.columns), None)
            if found is None:
                raise ValueError(f"Missing required column (any of): {aliases}")
            events[canonical] = events[found]

    if events["case_id"].isna().any():
        raise ValueError("The event log contains rows with an empty case_id")
    if events["event_timestamp"].isna().any():
        raise ValueError("The event log contains rows with an empty event timestamp")
    try:
        events["event_timestamp"] = pd.to_datetime(
            events["event_timestamp"], errors="raise"
        )
    except (TypeError, ValueError) as error:
        raise ValueError(f"Failed to parse event timestamps: {error}") from error
    return events


def detect_anomalies(events):
    """Return audit records for inversions, 3-sigma waits, and incomplete traces."""
    records = []
    transition_waits = {pair: [] for pair in zip(
        EXPECTED_MILESTONES, EXPECTED_MILESTONES[1:]
    )}
    case_events_by_id = {}

    for case_id, case_events in events.groupby("case_id", sort=False):
        counts = case_events["event_name"].value_counts()
        missing_stages = [
            stage for stage in EXPECTED_MILESTONES if counts.get(stage, 0) == 0
        ]
        patient_id = case_events["patient_id"].dropna()
        patient_id = patient_id.iloc[0] if not patient_id.empty else ""
        if missing_stages:
            records.append(
                {
                    "case_id": case_id,
                    "patient_id": patient_id,
                    "anomaly_type": "incomplete_trace",
                    "source_stage": "",
                    "target_stage": "",
                    "observed_wait_hours": "",
                    "threshold_hours": "",
                    "details": "Missing milestones: " + ", ".join(missing_stages),
                }
            )

        stage_timestamps = {}
        for stage in EXPECTED_MILESTONES:
            stage_rows = case_events.loc[case_events["event_name"] == stage]
            if len(stage_rows) == 1:
                stage_timestamps[stage] = stage_rows["event_timestamp"].iloc[0]
        case_events_by_id[case_id] = (patient_id, stage_timestamps)

        for source, target in transition_waits:
            if source not in stage_timestamps or target not in stage_timestamps:
                continue
            wait_hours = (
                stage_timestamps[target] - stage_timestamps[source]
            ).total_seconds() / 3600
            if wait_hours < 0:
                records.append(
                    {
                        "case_id": case_id,
                        "patient_id": patient_id,
                        "anomaly_type": "timestamp_inversion",
                        "source_stage": source,
                        "target_stage": target,
                        "observed_wait_hours": wait_hours,
                        "threshold_hours": "",
                        "details": (
                            f"{target} timestamp precedes {source} in the "
                            "canonical pathway"
                        ),
                    }
                )
            else:
                transition_waits[(source, target)].append((case_id, wait_hours))

    thresholds = {}
    for transition, observations in transition_waits.items():
        if not observations:
            continue
        values = pd.Series([wait for _, wait in observations], dtype="float64")
        thresholds[transition] = values.mean() + 3 * values.std(ddof=0)

    for transition, observations in transition_waits.items():
        if transition not in thresholds:
            continue
        source, target = transition
        threshold = thresholds[transition]
        for case_id, wait_hours in observations:
            if wait_hours > threshold:
                patient_id, _ = case_events_by_id[case_id]
                records.append(
                    {
                        "case_id": case_id,
                        "patient_id": patient_id,
                        "anomaly_type": "extreme_wait_outlier",
                        "source_stage": source,
                        "target_stage": target,
                        "observed_wait_hours": wait_hours,
                        "threshold_hours": threshold,
                        "details": (
                            "Transition wait exceeds the per-transition mean "
                            "plus 3 population standard deviations"
                        ),
                    }
                )

    return pd.DataFrame(records, columns=AUDIT_COLUMNS)


def plot_anomaly_distribution(anomalies, output_path):
    """Save a bar chart of flagged audit records by anomaly type."""
    counts = (
        anomalies["anomaly_type"]
        .value_counts()
        .reindex(ANOMALY_TYPES, fill_value=0)
    )
    labels = [
        "Timestamp inversions",
        "Extreme wait outliers",
        "Incomplete traces",
    ]
    figure, axis = plt.subplots(figsize=(8, 5))
    bars = axis.bar(labels, counts.values, color=["#E45756", "#F2CF5B", "#4C78A8"])
    axis.bar_label(bars, padding=3)
    axis.set_title("Clinical Process Anomaly Distribution")
    axis.set_ylabel("Flagged audit records")
    axis.grid(axis="y", linestyle=":", alpha=0.5)
    axis.tick_params(axis="x", rotation=12)
    figure.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close(figure)


def main():
    parser = argparse.ArgumentParser(
        description="Audit clinical events for process anomalies."
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--visual-output", type=Path, default=DEFAULT_VISUAL_OUTPUT)
    args = parser.parse_args()

    events = load_audit_events(args.input)
    anomalies = detect_anomalies(events)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    anomalies.to_csv(args.output, index=False)
    plot_anomaly_distribution(anomalies, args.visual_output)

    counts = anomalies["anomaly_type"].value_counts()
    print(f"Audited {events['case_id'].nunique()} patient traces.")
    for anomaly_type in ANOMALY_TYPES:
        print(f"{anomaly_type}: {int(counts.get(anomaly_type, 0))} flagged records.")
    print(f"Wrote anomaly audit records to {args.output}.")
    print(f"Wrote anomaly distribution chart to {args.visual_output}.")


if __name__ == "__main__":
    main()
