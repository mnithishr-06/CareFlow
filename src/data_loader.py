"""
Simple data loader and validator for the synthetic clinical event log.

Notes:
- Accepts either of the common column-name variants for event and timestamp: "event_name" or "activity" for the activity column; "event_timestamp" or "timestamp" for the timestamp column.
- Exposes load_event_log(path) -> pandas.DataFrame and basic schema checks.
"""
from typing import List
import pandas as pd

# Always require a case identifier and patient identifier. Event/timestamp column
# names are resolved to canonical names below to accept either variant.
REQUIRED_COLUMNS: List[str] = [
    "case_id",
    "patient_id",
]

# canonical column aliases we accept
COLUMN_ALIASES = {
    "event_name": ["event_name", "activity"],
    "event_timestamp": ["event_timestamp", "timestamp"],
}

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
    # basic required columns
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    # Resolve aliases for event name and timestamp. Create canonical columns
    # 'event_name' and 'event_timestamp' for downstream logic.
    df = df.copy()
    for canonical, aliases in COLUMN_ALIASES.items():
        found = None
        for a in aliases:
            if a in df.columns:
                found = a
                break
        if not found:
            raise ValueError(f"Missing required column (any of): {aliases}")
        # only copy if canonical name not already present (prefer existing canonical)
        if canonical not in df.columns:
            df[canonical] = df[found]

    # parse timestamps
    try:
        df["event_timestamp"] = pd.to_datetime(df["event_timestamp"])
    except Exception as e:
        raise ValueError(f"Failed to parse event timestamp column: {e}")

    # check that each case has expected milestones (not necessarily enforced order here)
    counts = df.groupby("case_id")["event_name"].nunique()
    if (counts != len(EXPECTED_MILESTONES)).any():
        bad = counts[counts != len(EXPECTED_MILESTONES)]
        raise ValueError(
            f"Some cases do not have the expected {len(EXPECTED_MILESTONES)} milestones. Examples: {bad.head().to_dict()}"
        )


def load_event_log(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    df = validate_schema_and_return(df)
    # ensure events are sorted for each case
    df = df.sort_values(["case_id", "event_timestamp"]).reset_index(drop=True)
    return df


def validate_schema_and_return(df: pd.DataFrame) -> pd.DataFrame:
    """Validate the dataframe and return a normalized copy with canonical columns.

    The returned DataFrame will always contain 'case_id', 'patient_id', 'event_name',
    and 'event_timestamp' (as datetime).
    """
    validate_schema(df)  # will raise on error
    # Re-run alias resolution to return the normalized copy
    df = df.copy()
    for canonical, aliases in COLUMN_ALIASES.items():
        if canonical not in df.columns:
            for a in aliases:
                if a in df.columns:
                    df[canonical] = df[a]
                    break
    df["event_timestamp"] = pd.to_datetime(df["event_timestamp"])  # ensure dtype
    return df


if __name__ == "__main__":
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else "data/raw/clinical_events.csv"
    print(f"Loading: {path}")
    print("Accepting column name variants: event_name|activity and event_timestamp|timestamp")
    df = load_event_log(path)
    n_cases = df["case_id"].nunique()
    n_events = len(df)
    print(
        f"Loaded {n_events} events for {n_cases} cases. Time span: {df['event_timestamp'].min()} to {df['event_timestamp'].max()}"
    )
