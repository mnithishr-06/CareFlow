"""
Generate a synthetic clinical event log CSV with 500 patients and 7 milestones each.
Writes to data/raw/clinical_events.csv (relative to repo root).
"""
import csv
import random
from datetime import datetime, timedelta
from pathlib import Path

RANDOM_SEED = 42
NUM_PATIENTS = 500
OUTPUT_PATH = "data/raw/clinical_events.csv"
MILESTONES = [
    "Emergency_Admission",
    "Triage_Assessment",
    "Diagnostic_Lab_Orders",
    "Physician_Consultation",
    "Treatment_or_Surgery",
    "Inpatient_Ward_Transfer",
    "Discharge",
]

random.seed(RANDOM_SEED)

def random_datetime(start, end):
    """Return random datetime between start and end."""
    delta = end - start
    sec = random.randint(0, int(delta.total_seconds()))
    return start + timedelta(seconds=sec)


def generate_patient_events(patient_idx):
    # Base admission between 2026-01-01 and 2026-03-31
    admit_start = datetime(2026, 1, 1)
    admit_end = datetime(2026, 3, 31, 23, 59, 59)
    admission_time = random_datetime(admit_start, admit_end)

    timestamps = [admission_time]
    # Generate delays (in minutes) between milestones with realistic ranges
    delays_min = [5, 10, 30, 20, 60, 240]  # minimum minutes between successive milestones
    delays_max = [60, 180, 360, 240, 720, 1440]  # maximum minutes

    current = admission_time
    for i in range(len(MILESTONES) - 1):
        delay_minutes = random.randint(delays_min[i], delays_max[i])
        current = current + timedelta(minutes=delay_minutes)
        timestamps.append(current)

    # Build rows
    rows = []
    case_id = f"C{patient_idx:05d}"
    patient_id = f"P{patient_idx:05d}"
    severity = random.Random(RANDOM_SEED + patient_idx).choice(
        ["High", "Moderate", "Low"]
    )
    # random department / provider
    departments = ["ED", "Triage", "Lab", "Consult", "OR", "Ward"]
    for m, ts in zip(MILESTONES, timestamps):
        row = {
            "case_id": case_id,
            "patient_id": patient_id,
            "severity": severity,
            "event_name": m,
            "event_timestamp": ts.isoformat(sep=" "),
            "department": random.choice(departments),
            "provider_id": f"DR{random.randint(100,999)}",
        }
        rows.append(row)
    return rows


def main():
    header = [
        "case_id",
        "patient_id",
        "severity",
        "event_name",
        "event_timestamp",
        "department",
        "provider_id",
    ]
    Path(OUTPUT_PATH).parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=header)
        writer.writeheader()
        for i in range(1, NUM_PATIENTS + 1):
            for r in generate_patient_events(i):
                writer.writerow(r)
    print(f"Wrote synthetic event log: {OUTPUT_PATH} (patients={NUM_PATIENTS}, events={NUM_PATIENTS * len(MILESTONES)})")

if __name__ == "__main__":
    main()
