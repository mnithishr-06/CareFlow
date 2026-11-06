# CareFlow: Clinical Pathway Process Mining

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![CI](https://github.com/mnithishr-06/CareFlow/actions/workflows/ci.yml/badge.svg?branch=member)](https://github.com/mnithishr-06/CareFlow/actions/workflows/ci.yml)
[![PM4Py](https://img.shields.io/badge/process%20mining-pm4py-5B8FF9)](https://pm4py.fit.fraunhofer.de/)

CareFlow is an end-to-end clinical process-mining portfolio project. It turns a synthetic patient event log into pathway, waiting-time, conformance, SLA, cohort, and capacity-scenario analyses, with a Streamlit dashboard for interactive review. The project demonstrates a reproducible analytics workflow; it is not a clinical decision-support system.

> **Data and interpretation:** The included 500-patient, 3,500-event dataset is entirely synthetic. Findings, cohort labels, example SLA thresholds, process adherence, and modeled savings are demonstrations only; they do not represent actual hospital operations, validated clinical standards, or patient outcomes.

## Executive summary

The pipeline models a seven-stage journey from emergency admission through discharge. It validates event data, measures patient length of stay (LoS) and stage-to-stage waits, discovers a Petri net with PM4Py, checks traces against a canonical pathway, and provides outputs for dashboarding and operational hypothesis generation.

| Baseline finding | Result |
|---|---:|
| Cases and events | 500 patients / 3,500 events |
| Median admission-to-discharge LoS | **27.13 hours** |
| Longest mean transition wait | **13.65 hours**, Inpatient Ward Transfer → Discharge |
| Modeled 50% discharge-delay reduction | **6.83 hours mean LoS improvement per patient** and **3,412.81 bed-hours saved** across 500 simulated cases |

The 50% result is a proportional what-if calculation applied to the synthetic transfer-to-discharge interval. It is not a forecast of realized throughput, occupancy, or capacity expansion.

## Canonical clinical pathway

1. Emergency Admission (`Emergency_Admission`)
2. Triage Assessment (`Triage_Assessment`)
3. Diagnostic Lab Orders (`Diagnostic_Lab_Orders`)
4. Physician Consultation (`Physician_Consultation`)
5. Treatment or Surgery (`Treatment_or_Surgery`)
6. Inpatient Ward Transfer (`Inpatient_Ward_Transfer`)
7. Discharge (`Discharge`)

## System architecture

```text
Synthetic event log
data/raw/clinical_events.csv
          |
          v
Schema validation and timestamp normalization
src/data_loader.py
          |
          +--> Transition, pathway, SLA, cohort, and anomaly analyses
          |    src/eda_transitions.py
          |    src/variant_analysis.py
          |    src/sla_compliance.py
          |    src/cohort_analysis.py
          |    src/anomaly_detection.py
          |
          +--> What-if discharge delay simulation
          |    src/bottleneck_simulation.py
          |
          +--> PM4Py discovery and canonical-path replay
          |    src/process_mining_discovery.py
          |    src/conformance_checking.py
          |
          v
Processed CSVs, PNML model, and visual reports
          |
          v
Interactive Streamlit dashboard
src/dashboard_app.py
```

The CI workflow runs the pytest suite on pushes to the `member` branch.

## Repository map

```text
.
├── .github/workflows/ci.yml      # GitHub Actions pytest workflow
├── main.py                       # Sequential end-to-end pipeline runner
├── data/
│   ├── raw/clinical_events.csv   # Synthetic source event log
│   └── processed/                # Analytics, SLA, conformance, and audit outputs
├── docs/                         # Week 1 and Week 2 project reports
├── models/                       # Discovered clinical Petri net (PNML)
├── src/
│   ├── data_loader.py            # Schema validation and event-log loading
│   ├── eda_transitions.py        # LoS and transition waiting-time analysis
│   ├── process_map.py            # Transition edge list and process map
│   ├── variant_analysis.py       # Pathway variants and rework
│   ├── sla_compliance.py         # Example transition SLA analysis
│   ├── cohort_analysis.py        # Synthetic severity cohort comparison
│   ├── process_mining_discovery.py # PM4Py discovery and PNML export
│   ├── conformance_checking.py   # Token-replay conformance scores
│   ├── bottleneck_simulation.py  # Discharge-delay what-if scenarios
│   ├── anomaly_detection.py      # Inversions, outliers, incomplete traces
│   └── dashboard_app.py          # Interactive Streamlit dashboard
├── tests/test_pipeline.py        # Pytest coverage of core pipeline behavior
└── visuals/                      # Generated pathway, cohort, and scenario charts
```

## Setup and reproduction

Python 3.10 or later is recommended. From the repository root, create and activate a virtual environment, then install the project dependencies:

```powershell
py -3.10 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

On macOS or Linux, use `python3 -m venv .venv` and `source .venv/bin/activate` instead.

Run the complete pipeline from the repository root:

```powershell
python main.py
```

For headless execution without generating process-discovery or simulation charts:

```powershell
python main.py --skip-viz
```

Both commands validate the raw event log and run transition analytics, pathway variant and rework discovery, SLA checks, PM4Py process discovery, conformance checking, the discharge-delay simulation, and executive briefing generation. Outputs are written to `data/processed/`, `models/`, `visuals/` (unless skipped), and `reports/`. Use `python main.py --help` to see CLI options.

Run the automated tests:

```powershell
python -m pytest
```

Launch the Streamlit dashboard:

```powershell
python -m streamlit run src/dashboard_app.py
```

The checked-in processed outputs let the dashboard run immediately after dependency installation. To regenerate individual outputs outside the orchestrated pipeline:

```powershell
python src/eda_transitions.py
python src/process_map.py
python src/variant_analysis.py
python src/sla_compliance.py
python src/cohort_analysis.py
python src/process_mining_discovery.py
python src/conformance_checking.py
python src/bottleneck_simulation.py
python src/anomaly_detection.py
```

Most analysis scripts accept `--help` for input/output path options. Process discovery uses a matplotlib fallback when Graphviz is unavailable.

## Interpretation and limitations

- The event log, timestamps, departments, provider IDs, and severity cohorts are generated for demonstration. The synthetic severity label is not a clinical assessment.
- All 500 generated cases follow the same complete canonical route. The resulting 100% happy-path adherence and conformance scores describe the generated data, not real SOP adherence.
- SLA thresholds are illustrative examples and require clinical and operational approval before real-world use.
- The simulation reduces the observed synthetic transfer-to-discharge interval proportionally; it does not model staffing, bed occupancy, arrival rates, downstream demand, or realized throughput.
- This repository is an analytics prototype. It is not validated for patient care or production clinical operations.

See [`docs/week_1_writeup.md`](docs/week_1_writeup.md) and [`docs/week_2_writeup.md`](docs/week_2_writeup.md) for detailed methods, findings, and recommendations.

## Contributors

- **mnithishr-06** — project author and repository maintainer.
- **GitHub Copilot** — AI-assisted development support.
