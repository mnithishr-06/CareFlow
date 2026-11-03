# Clinical Pathway Executive Briefing

## Executive summary

This briefing summarizes processed analytics for **500 synthetic patient cases**. The baseline median length of stay (LoS) is **27.13 h**. The longest mean stage wait is **13.65 h** from **Inpatient Ward Transfer** to **Discharge**. A modeled 50% reduction in that discharge delay corresponds to **6.83 h mean LoS improvement per case** and **3,412.81 bed-hours saved** across the cohort.

> **Scope:** All source records and results are synthetic. These analyses are operational demonstrations, not estimates of actual hospital performance, validated clinical guidance, or patient-care recommendations.

## Key clinical KPIs

| KPI | Result |
|---|---:|
| Patient cases analyzed | 500 |
| Median admission-to-discharge LoS | 27.13 h |
| Mean admission-to-discharge LoS | 27.56 h |
| Mean wait at longest transition | 13.65 h |
| Mean fitness against configured canonical path | 1.000 |
| Cases fitting configured canonical path | 500 / 500 (100.00%) |

## Bottleneck diagnostics

The longest mean wait occurs between **Inpatient Ward Transfer** and **Discharge**: mean 13.65 h, median 13.51 h, across 500 cases.

| Transition | Mean wait | Median wait | Cases |
|---|---:|---:|---:|
| Inpatient Ward Transfer → Discharge | 13.65 h | 13.51 h | 500 |
| Treatment or Surgery → Inpatient Ward Transfer | 6.45 h | 6.25 h | 500 |
| Diagnostic Lab Orders → Physician Consultation | 3.17 h | 3.13 h | 500 |
| Physician Consultation → Treatment or Surgery | 2.16 h | 2.15 h | 500 |
| Triage Assessment → Diagnostic Lab Orders | 1.58 h | 1.62 h | 500 |
| Emergency Admission → Triage Assessment | 0.55 h | 0.55 h | 500 |

## Compliance audit findings

The breach-only SLA audit contains **997 flagged transition records** across **500 cases**.

| SLA transition | Target | Breaches | Mean observed wait | Mean excess | Maximum excess |
|---|---:|---:|---:|---:|---:|
| Inpatient Ward Transfer → Discharge | 4.00 h | 500 | 13.65 h | 9.65 h | 19.97 h |
| Triage Assessment → Physician Consultation | 1.00 h | 497 | 4.77 h | 3.77 h | 7.72 h |

Breaches by destination department: OR: 179, Triage: 173, Ward: 169, Consult: 163, ED: 162, Lab: 151.

The supplied SLA file contains breaches only, not all evaluated compliant and non-compliant transitions. Therefore this briefing does not infer a compliance rate or denominator from that file. Thresholds should be treated as illustrative unless approved by clinical and operational owners.

## Conformance review

Token-replay scores show 500 of 500 cases fitting the configured canonical seven-stage pathway. Mean trace fitness is 1.000 (median 1.000). This checks the generated traces against the configured model; it does not establish adherence to an independently approved clinical SOP.

## What-if capacity scenario

The 50% discharge-delay reduction scenario reduces mean LoS from 27.56 h to 20.73 h, an average improvement of 6.83 h per case and 3,412.81 aggregate bed-hours saved.

This is a proportional what-if calculation on synthetic transfer-to-discharge waits, not a forecast of realized throughput, occupancy, or capacity expansion.

## Strategic operational recommendations

1. **Validate the signal on governed operational data.** Confirm timestamp semantics, pathway definitions, department ownership, case completeness, and metric denominators before interpreting the bottleneck or breach patterns.
2. **Investigate discharge coordination as a hypothesis.** On validated data, examine readiness documentation, medication reconciliation, transport, placement, and downstream bed constraints; do not infer causes from elapsed time alone.
3. **Review and approve SLA definitions.** Confirm target thresholds, clock start/stop events, exclusions, and department attribution with clinical and operational stakeholders, then report both breaches and all evaluated transitions.
4. **Treat scenario savings as capacity hypotheses.** Pilot an explicitly defined process change and measure observed LoS, occupancy, demand, and throughput before making capacity claims.
5. **Use an approved SOP and realistic pathway variation for conformance.** Define permitted exceptions and evaluate detours, incomplete traces, and rework before treating conformance scores as operational evidence.

## Data sources

- `data/processed/transition_metrics.csv`
- `data/processed/sla_violations.csv`
- `data/processed/conformance_scores.csv`
- `data/processed/simulation_results.csv`
