"""Tests for the clinical event data and core analytics pipeline."""

import sys
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from anomaly_detection import detect_anomalies
from bottleneck_simulation import build_patient_metrics, simulate_reductions
from data_loader import EXPECTED_MILESTONES, load_event_log, validate_schema
from eda_transitions import analyze_transitions


EVENT_LOG_PATH = REPOSITORY_ROOT / "data" / "raw" / "clinical_events.csv"


@pytest.fixture(scope="module")
def events():
    return load_event_log(str(EVENT_LOG_PATH))


def test_clinical_event_log_has_required_columns_and_nonempty_records():
    raw_events = pd.read_csv(EVENT_LOG_PATH)

    assert not raw_events.empty
    assert {
        "case_id",
        "patient_id",
        "department",
        "event_name",
        "event_timestamp",
    }.issubset(raw_events.columns)
    assert raw_events[
        ["case_id", "patient_id", "department", "event_name", "event_timestamp"]
    ].notna().all().all()
    assert raw_events["case_id"].astype(str).str.strip().ne("").all()


def test_loader_returns_complete_cases_with_expected_milestones(events):
    assert not events.empty
    assert events["case_id"].nunique() > 0
    for _, case_events in events.groupby("case_id"):
        assert case_events["event_name"].value_counts().to_dict() == {
            milestone: 1 for milestone in EXPECTED_MILESTONES
        }


def test_schema_validation_rejects_missing_required_columns():
    incomplete = pd.DataFrame(
        {
            "case_id": ["C1"],
            "patient_id": ["P1"],
            "event_name": ["Emergency_Admission"],
            "event_timestamp": ["2026-01-01T00:00:00"],
        }
    )

    with pytest.raises(ValueError, match="department"):
        validate_schema(incomplete)


def test_all_clinical_transition_durations_are_positive(events):
    for _, case_events in events.groupby("case_id"):
        ordered = case_events.set_index("event_name").loc[EXPECTED_MILESTONES]
        timestamps = ordered["event_timestamp"].tolist()
        durations = [
            (later - earlier).total_seconds()
            for earlier, later in zip(timestamps, timestamps[1:])
        ]
        assert all(duration > 0 for duration in durations)


def test_transition_analysis_reports_positive_waits_and_discharge_bottleneck(events):
    rows, median_los, bottleneck_stage = analyze_transitions(events)

    assert median_los > 0
    assert bottleneck_stage == "Discharge"
    assert all(row["mean_duration_hours"] > 0 for row in rows)
    assert next(row for row in rows if row["metric"] == "top_bottleneck")[
        "mean_duration_hours"
    ] == pytest.approx(13.6512333333)


def test_simulation_reductions_improve_los_and_save_bed_hours(events):
    patient_metrics = build_patient_metrics(events)
    results = simulate_reductions(patient_metrics)

    assert results["discharge_delay_reduction_percentage"].tolist() == [0, 30, 50, 70]
    assert results["simulated_mean_los_hours"].is_monotonic_decreasing
    assert results["total_bed_hours_saved"].is_monotonic_increasing
    assert results.loc[0, "total_bed_hours_saved"] == 0
    for _, result in results.iterrows():
        assert result["total_bed_hours_saved"] == pytest.approx(
            result["mean_los_improvement_hours"] * result["patient_count"]
        )


def test_anomaly_detection_flags_timestamp_inversion_and_incomplete_trace():
    start = datetime(2026, 1, 1)
    rows = []
    for index, milestone in enumerate(EXPECTED_MILESTONES):
        timestamp = start + timedelta(hours=index)
        if milestone == "Triage_Assessment":
            timestamp = start - timedelta(minutes=1)
        rows.append(
            {
                "case_id": "INVERTED",
                "patient_id": "P1",
                "event_name": milestone,
                "event_timestamp": timestamp,
            }
        )
    rows.extend(
        [
            {
                "case_id": "INCOMPLETE",
                "patient_id": "P2",
                "event_name": EXPECTED_MILESTONES[0],
                "event_timestamp": start,
            }
        ]
    )

    anomalies = detect_anomalies(pd.DataFrame(rows))

    assert (
        (anomalies["case_id"] == "INVERTED")
        & (anomalies["anomaly_type"] == "timestamp_inversion")
    ).any()
    incomplete = anomalies.loc[
        (anomalies["case_id"] == "INCOMPLETE")
        & (anomalies["anomaly_type"] == "incomplete_trace")
    ]
    assert len(incomplete) == 1
    assert "Discharge" in incomplete.iloc[0]["details"]
