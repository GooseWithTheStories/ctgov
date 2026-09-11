# Changelog

## 0.1.1 — 2026-09-10

Fixes found by building an endpoint benchmark with 0.1.0 and auditing every change row by row
against real registry text: the 124,790-endpoint companion dataset, compared before and after.

### Fixed

- **Dose-limiting toxicity was unrecognised or mislabelled.** DLT / MTD / RP2D — the standard
  Phase 1 oncology primary endpoint — had no concept, and some were classified as the
  `hospitalization` concept because DLT definitions say "requiring hospitalization". They are
  now `dose_limiting_toxicity`, domain `safety`.
- **A definition no longer overrides the endpoint's name.** Concepts are matched on the measure
  name first; the description is read only when the name names no concept. Before, a definition
  could take over its own endpoint: "Serious Adverse Events", defined as "adverse events that
  result in death or hospitalization", was filed under the concepts its definition mentioned.
  Serious-AE endpoints are now `serious_adverse_events` unless they also count any or
  non-serious AEs.
- **Word stems that could never match.** Patterns such as `\b(toxicit|feasib)\b` demand a word
  boundary straight after the stem, so they never fired; plurals ("Hospitalizations", "Scores")
  were missed the same way. Fixing them reclassified 6,099 endpoints' domains in the companion
  dataset (hypoglycaemia endpoints now `safety`, feasibility endpoints now
  `feasibility_implementation`).
- **Diagnostic accuracy needs diagnostic context.** Bare "sensitivity" is mostly insulin, contrast
  or dentin sensitivity, high-sensitivity CRP or a statistical sensitivity analysis. It now
  counts only with specificity, predictive values, ROC or "sensitivity of the test / assay / device".
- **"Hospitalized" counts only when it names the outcome.** "Participants who were hospitalized"
  is an endpoint; "in hospitalized adults" is the population. Hospital stays, admissions and
  ICU admissions always count.
- **Ordinal clinical-status scales are the endpoint, not their categories.** WHO / NIAID scales
  define themselves as a list ("8) Death ... 3) Hospitalized, no oxygen ... 1) Not hospitalized"),
  which had filed them as hospitalization. They are now `clinical_status_ordinal_scale`. Generic
  wording ("a 5-point ordinal scale", "clinical status") counts only alongside the scale's
  categories or setting, so PGIC, vIGA-AD and EDSS do not match.
- **`pCR` is its own concept, `pathologic_complete_response`**, distinct from clinical
  `complete_response`. It is matched case-sensitively, so "PCR" (polymerase chain reaction) in
  COVID-19 endpoints is not.
- **Abbreviated serious AEs are serious.** "Serious AE (SAE)", "Serious TEAEs", "TESAEs" and
  "STEAEs" are `serious_adverse_events`. Before, removing "SAE" from "Serious AE (SAE)" left a
  bare "AE", which read as "this endpoint also counts any AE".
- **"DOR" beside antiretroviral context is doravirine**, not duration of response ("Change in
  BMI After a Switch to DOR/TDF/3TC"). The scan continues, so that row reaches `body_weight_bmi`.
- **Glucose AUC is not drug exposure.** AUC from a glucose tolerance test no longer maps to
  `pk_exposure`.
- **Recognised concepts no longer fall below the confidence bar for terse phrasing.** A bare
  "HbA1c", "Overall Response Rate" or "Systolic Blood Pressure" scored 0.64 because the text
  named no measure. The measure type is now taken from the concept and flagged in the new
  `endpoint_measure_inferred` field. In a breast-cancer cohort this had pushed 24% of objective
  response rate rows and 30% of complete-response rows under the 0.7 bar.

### Added

- 17 concepts (21 → 38).
  - Oncology: `invasive_disease_free_survival`, `invasive_breast_cancer_free_survival` (STEEP
    2.0: excludes second non-breast primaries, unlike iDFS), `recurrence_free_survival`,
    `distant_recurrence_free_survival`, `locoregional_recurrence`, `duration_of_response`,
    `disease_control_rate`, `clinical_benefit_rate`, `pathologic_complete_response`,
    `ki67_response`, `time_to_next_treatment`, `dose_limiting_toxicity`.
  - Metabolic: `fasting_glucose`, `cgm_time_in_range`, `cgm_glycemic_metric`,
    `urine_albumin_creatinine_ratio`. UACR is matched spelled out or as "UACR" only; bare "ACR"
    is the rheumatology ACR20/50/70 response criterion.
  - Infectious disease: `clinical_status_ordinal_scale`.
- Measure type `continuous_value` (blood pressure, body weight, glycaemic variability).
- Field `endpoint_measure_inferred`.
- Test suite: 129 regression tests, each taken from a real misclassified registry row.

### Changed

- `endpoint_domain_inferred` is `true` whenever a recognised concept set the domain. Since
  0.1.0 the concept outranks loose keywords, so this flag marks the **stronger** signal. Earlier
  documentation described it as weaker and suggested filtering those rows out — doing so would
  drop every Overall Survival, PFS and HbA1c row. Do not filter on it.

## 0.1.0 — 2026-09-09

- Initial release: paginating ClinicalTrials.gov API v2 client and endpoint normalizer.
- Overall Survival and PFS are classified `efficacy`. Their definitions ("time until death")
  had caused a keyword-only pass to classify them as `safety`.
