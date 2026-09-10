# ctgov

**Paginating ClinicalTrials.gov API v2 client with free-text endpoint normalization.**

Zero dependencies. Pure standard library. No API key.

```bash
pip install ctgov
```

---

## Why

Two things the registry makes harder than they should be.

### 1. You cannot get more than 1,000 studies

The API caps a response at 1,000 and hands back a `nextPageToken`. Existing wrappers stop
there, so "how do I pull more than 1000 studies?" is the question that keeps getting asked
and never answered.

`ctgov` follows the token for you. Your result set is bounded by your query, not by the page size.

```python
from ctgov import Client

client = Client()
studies = client.studies("AREA[Phase]PHASE3", max_studies=5000)   # pages automatically
print(len(studies))                                                # 5000

for study in client.iter_studies("cancer"):     # streams; one page in memory at a time
    ...
```

### 2. Endpoints are prose, so you cannot compare across trials

Straight from the API, an outcome measure looks like this:

| raw endpoint | raw timeframe |
|---|---|
| `Serum Markers (HbA1c) to Follow the Evolution of Liver Damage` | `6 months` |
| `Primary Safety: Freedom From Index Procedure Related Major Complications` | `30 days` |
| `Cmax of midazolam` | `0, 0.5, 1, 1.5, 2, 3, 4, 6, 8, 12 hours post-dose` |
| `Anxiety Rating` | `Baseline` |

You cannot group, filter, or compare on that. `ctgov` structures it:

| domain | measure type | canonical | horizon_days | direction |
|---|---|---|---|---|
| biomarker_laboratory | change_from_baseline | hba1c_change | 182.64 | lower_is_better |
| safety | proportion | — | 30.0 | higher_is_better |
| pharmacokinetics | pk_parameter | pk_exposure | 0.5 | unspecified |
| patient_reported | score_scale | anxiety_score | 0.0 | lower_is_better |

---

## Query to structured rows in one call

```python
from ctgov import endpoints

rows = [r for r in endpoints("AREA[Phase]PHASE3", max_studies=200)
        if r["normalization_confidence"] >= 0.7]

for r in rows[:3]:
    print(r["endpoint_canonical"], r["horizon_days"], r["condition_primary"])
```

Each row carries the study context (phase, condition, enrollment, sponsor, allocation,
masking), the normalized endpoint fields, **and the untouched raw text**, so any row can be
audited rather than taken on trust.

Straight into pandas:

```python
import pandas as pd
df = pd.DataFrame(endpoints("AREA[Condition]diabetes", max_studies=500))
df.groupby("endpoint_canonical")["horizon_days"].median().sort_values()
```

## Counting without downloading

```python
client.count("AREA[Phase]PHASE3", filters={"advanced": "AREA[HasResults]true"})   # 14748
```

---

## What you get per endpoint

| field | meaning |
|---|---|
| `endpoint_raw` | untouched registry text |
| `endpoint_domain` | `safety`, `efficacy`, `patient_reported`, `pharmacokinetics`, `biomarker_laboratory`, `clinical_assessment`, `behavioral_functional`, `healthcare_utilization`, `immunogenicity`, `feasibility_implementation`, `diagnostic_accuracy`, `unclassified` |
| `endpoint_measure_type` | `change_from_baseline`, `proportion`, `count`, `score_scale`, `time_to_event`, `pk_parameter`, `concentration`, `diagnostic_accuracy`, `unclassified` |
| `endpoint_canonical` | recognised concept: `overall_survival`, `progression_free_survival`, `objective_response_rate`, `adverse_event_incidence`, `hba1c_change`, `quality_of_life`, `seroconversion`, … |
| `endpoint_direction` | `higher_is_better` / `lower_is_better` / `ambiguous` / `unspecified` |
| `horizon_days` | free-text timeframe parsed to a number |
| `timepoint_count`, `is_longitudinal`, `baseline_anchored` | schedule shape |
| `normalization_confidence` | 0–1. **Filter on `>= 0.7`** for high-precision work. |

## Honesty about coverage

Normalization is deterministic and rule-based — no model inference, so it is reproducible,
auditable, and free to run. It does not classify everything, and it says so rather than
guessing: across the full registry, **~67% of endpoints get a domain, ~87% a measure type,
~61% a parsed time horizon.** The rest is a genuine long tail of disease-specific measures
("Swollen Joint Count", "Bowel Filling Properties: Distension/Distal Ileum") and is labelled
`unclassified` with raw text retained.

`normalization_confidence` exists so you can pick your own precision/recall tradeoff.

## Being a good citizen

NLM asks for no more than 20 requests/second per IP. `ctgov` defaults to roughly 3/s and
retries with exponential backoff. Please set a contactable user agent:

```python
Client(user_agent="my-project (me@example.com)")
```

## Relationship to `pytrials`

[`pytrials`](https://github.com/jvfe/pytrials) is a good, focused API wrapper. `ctgov` is not
a replacement for it so much as a different scope: pagination past the 1,000 cap, and a
normalization layer over the free-text outcome fields. If you only need to pull a few hundred
studies as a DataFrame, `pytrials` is a smaller dependency and will serve you fine.

## Licence and attribution

MIT. Source data is ClinicalTrials.gov (U.S. National Library of Medicine), public domain.

> This product uses publicly available data from the U.S. National Library of Medicine (NLM),
> National Institutes of Health, Department of Health and Human Services; NLM is not
> responsible for the product and does not endorse or recommend this or any other product.
