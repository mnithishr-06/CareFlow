"""
Simple data loader and validator for the synthetic clinical event log.
Provides load_event_log(path) -> pandas.DataFrame and basic schema checks.
"""
from typing import List
import pandas as pd

REQUIRED_COLUMNS: List[str] = [
    "case_id",
    "patient_id",
    "event_name",
    "event_timestamp",
]

EXPECTED_MILESTONES = [
    "Emergency_Admission",
    "Triage_Assessment",
    "Diagnostic_Lab_Orders",
    "Physician_Consultation",
    "Treatment_or_Surgery",
    "Inpatient_Ward_Transfer",
    "Discharge",
]


def validate_schema(df: pd.DataFrame) -> None:
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    # parse timestamps
    try:
        df["event_timestamp"] = pd.to_datetime(df["event_timestamp"])
    except Exception as e:
        raise ValueError(f"Failed to parse event_timestamp: {e}")

    # check that each case has expected milestones (not necessarily enforced order here)
    counts = df.groupby("case_id")["event_name"].nunique()
    if (counts != len(EXPECTED_MILESTONES)).any():
        bad = counts[counts != len(EXPECTED_MILESTONES)]
        raise ValueError(f"Some cases do not have the expected {len(EXPECTED_MILESTONES)} milestones. Examples: {bad.head().to_dict()}")


def load_event_log(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    validate_schema(df)
    # ensure events are sorted for each case
    df = df.sort_values(["case_id", "event_timestamp"]) .reset_index(drop=True)
    return df


if __name__ == "__main__":
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else "data/raw/clinical_events.csv"
    print(f"Loading: {path}")
    df = load_event_log(path)
    n_cases = df["case_id"].nunique()
    n_events = len(df)
    print(f"Loaded {n_events} events for {n_cases} cases. Time span: {df['event_timestamp'].min()} to {df['event_timestamp'].max()}")
