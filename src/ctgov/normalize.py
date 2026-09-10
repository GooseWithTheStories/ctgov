"""Normalize free-text ClinicalTrials.gov endpoints into structured fields.

This module is the value-add of the dataset. Raw registry endpoints are prose, e.g.
  "Primary Safety: Freedom From Index Procedure Related Major Complications"
  "Serum Markers (HbA1c) to Follow the Evolution of Liver Damage"
and timeframes range from "Baseline" to "0, 0.5, 1, 1.5, 2 ... hours post-dose".

Per endpoint we emit: clinical domain, measure type, canonical endpoint concept,
directionality, and a parsed time horizon in days -- each with a confidence score,
always alongside untouched raw text so a buyer can audit every row.

Rules are ordered specific -> general; first match wins.
"""
import re


def _rx(p):
    return re.compile(p, re.I)


DOMAIN_RULES = [
    ("safety", 0.95, _rx(r"\b(adverse events?|AEs?|SAEs?|treatment[- ]emergent|toxicit|tolerabilit|safety|side effects?|dose[- ]limiting|mortality|deaths?|complications?|hypoglyc(a)?emi|overdose|withdrawal due to)\b")),
    ("pharmacokinetics", 0.95, _rx(r"\b(Cmax|Tmax|AUC|pharmacokinetic|plasma concentration|serum concentration|half[- ]life|clearance|bioavailab|trough)\b")),
    ("immunogenicity", 0.90, _rx(r"\b(immune response|immunogenic|(antibody|neutralizing|inhibitor|anti-\w+)\s*tit(er|re)|tit(er|re)s?\b|seroconversion|seroprotect|neutralizing antibod|GMT|GMR|IgG|IgA|vaccine response)\b")),
    ("diagnostic_accuracy", 0.90, _rx(r"\b(sensitivit|specificit|positive predictive|negative predictive|PPV|NPV|diagnostic accuracy|ROC)\b")),
    ("patient_reported", 0.85, _rx(r"\b(quality of life|QoL|questionnaire|patient[- ]reported|satisfaction|EQ-5D|SF-36|VAS|visual analog)\b")),
    ("efficacy", 0.75, _rx(r"\b(efficacy|survival|response rate|remission|cure|progression|recurrence|relapse|success rate|improvement|reduction in|incidence of \w+|treatment failure|clearance of|eradication|healing|symptom resolution)\b")),
    # --- broader categories added after inspecting real unclassified endpoints ---
    ("biomarker_laboratory", 0.80, _rx(r"\b(insulin|glucose|cholesterol|triglycerid|creatinine|h(a)?emoglobin|platelet|leukocyte|lymphocyte|neutrophil|bilirubin|albumin|enzyme|biomarker|serum|plasma|urinary|lipid|CRP|ferritin|vitamin|hormone|cytokine|eGFR|liver function|renal function|lab(oratory)? (value|parameter|test))\b")),
    ("clinical_assessment", 0.80, _rx(r"\b(ECOG|performance status|Karnofsky|electrocardiogram|ECG|EKG|echocardiogra|imaging|MRI|CT scan|ultrasound|endoscop|colonoscop|biopsy|histolog|radiograph|physical examination|vital signs|spirometry|FEV1|bone mineral density|body composition|joint count|RECIST|disease control rate|mechanical ventilation|clinician[- ]administered|assessed (with|by) the|investigator[- ]assessed|global (impression|assessment))\b")),
    ("healthcare_utilization", 0.80, _rx(r"\b(hospitali[sz]|re-?admission|length of stay|ICU|intensive care|transfus|surger|surgical|operative|re-?operation|discharge|treatment duration|discontinuation|drop-?out|adherence|compliance|rescue medication|concomitant medication|health(care)? (cost|resource|utili))\b")),
    ("behavioral_functional", 0.78, _rx(r"\b(physical activity|sleep|walking|gait|mobility|functional (status|capacity|independence)|exercise|dietary|nutrition|knowledge|behavio(u)?r|smoking|alcohol|self-?efficacy|caregiver|breastfeed|muscle (strength|endurance))\b")),
    # Pilot / implementation trials measure whether the study itself worked.
    ("feasibility_implementation", 0.82, _rx(r"\b(feasibilit|acceptabilit|fidelity|recruitment|retention rate|participation rate|implementation|usability|enrol(l)?ment rate|protocol deviation|completion rate|attendance)\b")),
]

MEASURE_RULES = [
    ("time_to_event", 0.92, _rx(r"\b(time to|time until|duration of|overall survival|progression[- ]free|event[- ]free|disease[- ]free)\b")),
    ("pk_parameter", 0.92, _rx(r"\b(Cmax|Tmax|AUC|half[- ]life|clearance|volume of distribution|trough concentration)\b")),
    ("diagnostic_accuracy", 0.90, _rx(r"\b(sensitivit|specificit|predictive value|diagnostic accuracy)\b")),
    ("change_from_baseline", 0.90, _rx(r"\b(change from baseline|mean change|absolute change|percent change|changes? in)\b")),
    ("proportion", 0.85, _rx(r"\b(percentage of|percent of|proportion of|rates? of|incidence( rate)? (of|per)|freedom from|% of|prevalence of)\b")),
    ("count", 0.80, _rx(r"\b(number of|count of|episodes of|total number|frequency of)\b")),
    ("score_scale", 0.80, _rx(r"\b(score|scale|index|questionnaire|assessment|rating|grade)\b")),
    ("concentration", 0.70, _rx(r"\b(levels?|concentrations?|tit(er|re)s?|markers?)\b")),
]

CANONICAL = [
    ("overall_survival", _rx(r"\boverall survival\b")),
    ("progression_free_survival", _rx(r"\bprogression[- ]free survival\b|\bPFS\b")),
    ("disease_free_survival", _rx(r"\bdisease[- ]free survival\b|\bDFS\b")),
    ("event_free_survival", _rx(r"\bevent[- ]free survival\b|\bEFS\b")),
    ("objective_response_rate", _rx(r"\bobjective response rate\b|\bORR\b|\boverall response rate\b")),
    ("complete_response", _rx(r"\bcomplete (response|remission)\b")),
    ("adverse_event_incidence", _rx(r"\b(number|percentage|incidence|frequency) of .{0,40}adverse events?\b|\btreatment[- ]emergent adverse events?\b")),
    ("serious_adverse_events", _rx(r"\bserious adverse events?\b|\bSAEs?\b")),
    ("all_cause_mortality", _rx(r"\bmortality\b|\bdeath rate\b")),
    ("hba1c_change", _rx(r"\bHbA1c\b|\bA1c\b|\bglyc(ated|osylated) h(a)?emoglobin\b")),
    ("blood_pressure", _rx(r"\bblood pressure\b|\bsystolic\b|\bdiastolic\b|\bSBP\b|\bDBP\b")),
    ("body_weight_bmi", _rx(r"\bbody weight\b|\bBMI\b|\bbody mass index\b|\bweight loss\b")),
    ("pain_score", _rx(r"\bpain\b.{0,20}(score|scale|intensity|VAS|NRS)|\b(VAS|NRS)\b.{0,20}pain")),
    ("depression_score", _rx(r"\bdepression\b|\bMADRS\b|\bHAM-D\b|\bPHQ-9\b|\bBDI\b")),
    ("anxiety_score", _rx(r"\banxiety\b|\bHAM-A\b|\bGAD-7\b|\bSTAI\b")),
    ("cognitive_score", _rx(r"\bcognitive\b|\bMMSE\b|\bMoCA\b|\bADAS-Cog\b")),
    ("quality_of_life", _rx(r"\bquality of life\b|\bQoL\b|\bEQ-5D\b|\bSF-36\b")),
    ("seroconversion", _rx(r"\bseroconversion\b|\bseroprotection\b|\bantibody tit(er|re)\b|\bGMT\b")),
    ("viral_load", _rx(r"\bviral load\b|\bviral clearance\b|\bundetectable\b")),
    ("hospitalization", _rx(r"\bhospitali[sz]ation\b|\blength of stay\b|\bICU admission\b")),
    ("pk_exposure", _rx(r"\bCmax\b|\bAUC\b|\bTmax\b|\bhalf[- ]life\b")),
]

# Fallback: if no domain rule fires but we recognised the canonical concept,
# infer the domain from it. Without this, "Anxiety Rating" and "HbA1c" -- both
# clearly classifiable -- fall through to "unclassified".
CANONICAL_DOMAIN = {
    "overall_survival": "efficacy",
    "progression_free_survival": "efficacy",
    "disease_free_survival": "efficacy",
    "event_free_survival": "efficacy",
    "objective_response_rate": "efficacy",
    "complete_response": "efficacy",
    # These name what is being measured, not whether the trial calls it an efficacy
    # endpoint. HbA1c is a lab value even when it is the primary efficacy measure.
    "viral_load": "biomarker_laboratory",
    "hba1c_change": "biomarker_laboratory",
    "blood_pressure": "clinical_assessment",
    "body_weight_bmi": "clinical_assessment",
    "hospitalization": "healthcare_utilization",
    "adverse_event_incidence": "safety",
    "serious_adverse_events": "safety",
    "all_cause_mortality": "safety",
    "pain_score": "patient_reported",
    "depression_score": "patient_reported",
    "anxiety_score": "patient_reported",
    "quality_of_life": "patient_reported",
    "cognitive_score": "clinical_assessment",
    "seroconversion": "immunogenicity",
    "pk_exposure": "pharmacokinetics",
}

HIGHER_BETTER = _rx(r"\b(survival|response rate|remission|improvement|efficacy|seroconversion|seroprotection|cure|success|freedom from|adherence|satisfaction|quality of life|recovery)\b")
LOWER_BETTER = _rx(r"\b(adverse events?|mortality|death|toxicit|pain|progression|recurrence|relapse|failure|hospitali[sz]ation|viral load|HbA1c|blood pressure|symptoms?|severity|incidence of)\b")

_UNIT_DAYS = {
    "hour": 1 / 24, "hr": 1 / 24, "h": 1 / 24,
    "day": 1.0, "d": 1.0,
    "week": 7.0, "wk": 7.0,
    "month": 30.44, "mo": 30.44,
    "year": 365.25, "yr": 365.25,
    "minute": 1 / 1440, "min": 1 / 1440,
    "cycle": 21.0,
}
_UNITS = r"hours?|hrs?|h|days?|d|weeks?|wks?|months?|mo|years?|yrs?|minutes?|mins?|cycles?"
_NUM_UNIT = _rx(r"(\d+(?:\.\d+)?)\s*(" + _UNITS + r")\b")
# Sampling schedules share one trailing unit across a comma-separated run, e.g.
# "0, 0.5, 1, 1.5, 2, 3, 4, 6, 8, 12 hours post-dose". Matching only "12 hours" would
# report a ten-point schedule as a single timepoint, so capture the whole run.
_LIST_UNIT = _rx(
    r"((?:\d+(?:\.\d+)?\s*(?:,|and)\s*)+\d+(?:\.\d+)?)\s*(" + _UNITS + r")\b"
)
_NUM = _rx(r"\d+(?:\.\d+)?")
_BASELINE = _rx(r"\bbaseline\b|\bpre[- ]?dose\b|\bpre[- ]?treatment\b")
_ONLY_BASELINE = _rx(r"^\s*baseline\s*$")


def parse_timeframe(tf):
    """Free-text timeframe -> structured horizon. Reports its own confidence."""
    out = {
        "timeframe_raw": tf,
        "horizon_days": None,
        "timepoint_count": None,
        "is_longitudinal": None,
        "baseline_anchored": None,
        "timeframe_confidence": 0.0,
    }
    if not tf or not tf.strip():
        return out
    t = tf.strip()
    out["baseline_anchored"] = bool(_BASELINE.search(t))
    # Expand shared-unit runs first, and remember their spans so the per-number pass
    # below does not count the run's final number twice.
    pairs = []
    consumed = []
    for m in _LIST_UNIT.finditer(t):
        unit = m.group(2)
        for num in _NUM.findall(m.group(1)):
            pairs.append((num, unit))
        consumed.append((m.start(), m.end()))

    for m in _NUM_UNIT.finditer(t):
        if any(start <= m.start() < end for start, end in consumed):
            continue
        pairs.append((m.group(1), m.group(2)))

    if not pairs:
        if _ONLY_BASELINE.search(t):
            out.update(horizon_days=0.0, timepoint_count=1,
                       is_longitudinal=False, timeframe_confidence=0.85)
        return out
    days = []
    for num, unit in pairs:
        u = unit.lower().rstrip("s")
        u = {"hrs": "hr", "mins": "min", "wks": "wk"}.get(u, u)
        f = _UNIT_DAYS.get(u)
        if f is None:
            for k, v in _UNIT_DAYS.items():
                if u.startswith(k[:2]):
                    f = v
                    break
        if f:
            days.append(float(num) * f)
    if not days:
        return out
    out["horizon_days"] = round(max(days), 3)
    out["timepoint_count"] = len(days)
    out["is_longitudinal"] = len(days) > 1
    # A single clean "6 months" is high confidence. A 14-timepoint PK schedule
    # yields a horizon, not a schedule, so we flag lower confidence.
    out["timeframe_confidence"] = 0.9 if len(days) == 1 else 0.65
    return out


def _first(rules, text):
    for name, conf, rx in rules:
        if rx.search(text):
            return name, conf
    return None, 0.0


def normalize_endpoint(measure, description="", timeframe=""):
    blob = "{} {}".format(measure or "", description or "").strip()
    mtype, mconf = _first(MEASURE_RULES, blob)

    canon = None
    for name, rx in CANONICAL:
        if rx.search(blob):
            canon = name
            break

    # A recognised standard concept outranks a loose keyword match. Overall Survival is
    # defined as "length of time until death", so the keyword pass alone labels the single
    # most important oncology endpoint as `safety`. The concept is the stronger signal.
    if canon in CANONICAL_DOMAIN:
        domain, dconf, domain_from_concept = CANONICAL_DOMAIN[canon], 0.85, True
    else:
        domain, dconf = _first(DOMAIN_RULES, blob)
        domain_from_concept = False

    domain_inferred = domain_from_concept

    hb = bool(HIGHER_BETTER.search(blob))
    lb = bool(LOWER_BETTER.search(blob))
    if hb and not lb:
        direction = "higher_is_better"
    elif lb and not hb:
        direction = "lower_is_better"
    elif hb and lb:
        direction = "ambiguous"
    else:
        direction = "unspecified"

    conf = dconf * 0.4 + mconf * 0.4 + (0.3 if canon else 0.0)

    rec = {
        "endpoint_raw": measure,
        "endpoint_domain": domain or "unclassified",
        "endpoint_measure_type": mtype or "unclassified",
        "endpoint_canonical": canon,
        "endpoint_direction": direction,
        "endpoint_domain_inferred": domain_inferred,
        "normalization_confidence": round(min(1.0, conf), 3),
    }
    rec.update(parse_timeframe(timeframe))
    return rec
