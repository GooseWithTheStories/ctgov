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


# Diagnostic accuracy needs diagnostic context. Bare "sensitivity" is not a signal in this
# registry: it is mostly contrast sensitivity, Schiff dentin sensitivity, high-sensitivity CRP,
# insulin sensitivity or a statistical sensitivity analysis (687 of 799 rows, measured).
_DIAG_PATTERN = (
    r"\b(sensitivity and specificity|specificity and sensitivity|specificit\w*|positive predictive"
    r"|negative predictive|PPV|NPV|predictive values?|diagnostic (accuracy|performance|yield)"
    r"|(diagnostic|analytical|clinical) sensitivit\w*|ROC|area under the (receiver|ROC))\b"
    r"|\bsensitivit\w* of (the |a |an )?([\w-]+ ){0,4}(test|assay|method|device|feature|algorithm|scan"
    r"|imaging|screening|biopsy|detection|tool|model|criteria|classifier|mammograph\w*|ultrasound|MRI|PET|CT)\b"
)

DOMAIN_RULES = [
    ("safety", 0.95, _rx(r"\b(adverse events?|AEs?|SAEs?|treatment[- ]emergent|toxicit\w*|tolerabilit\w*|safety|side effects?|dose[- ]limiting|mortality|deaths?|complications?|hypoglyc(a)?emi\w*|overdose|withdrawal due to)\b")),
    # No trailing \b: "AUC0-t", "AUCtau", "AUCinf" and "Cmax,ss" continue straight after the
    # abbreviation, and a trailing boundary silently dropped all of them.
    ("pharmacokinetics", 0.95, _rx(r"\b(Cmax\w*|Tmax\w*|AUC\w*|pharmacokinetic\w*|plasma concentration|serum concentration|half[- ]life|clearance|bioavailab\w*|trough|area under ((the|plasma|serum|blood|drug) )*concentration|maximum ((observed|plasma|serum|blood|drug) )*concentration)")),
    ("immunogenicity", 0.90, _rx(r"\b(immune response|immunogenic\w*|(antibody|neutralizing|inhibitor|anti-\w+)\s*tit(er|re)|tit(er|re)s?\b|seroconversion|seroprotect\w*|neutralizing antibod\w*|GMT|GMR|IgG|IgA|vaccine response)\b")),
    ("diagnostic_accuracy", 0.90, _rx(_DIAG_PATTERN)),
    ("patient_reported", 0.85, _rx(r"\b(quality of life|QoL|questionnaires?|patient[- ]reported|satisfaction|EQ-5D|SF-36|VAS|visual analog)\b")),
    ("efficacy", 0.75, _rx(r"\b(efficacy|survival|response rate|remission|cure|progression|recurrence|relapse|success rate|improvement|reduction in|incidence of \w+|treatment failure|clearance of|eradication|healing|symptom resolution)\b")),
    # --- broader categories added after inspecting real unclassified endpoints ---
    ("biomarker_laboratory", 0.80, _rx(r"\b(insulin|glucose|cholesterol|triglycerid\w*|creatinine|h(a)?emoglobin|platelets?|leukocytes?|lymphocytes?|neutrophils?|bilirubin|albumin|enzymes?|biomarkers?|serum|plasma|urinary|lipids?|CRP|ferritin|vitamins?|hormones?|cytokines?|eGFR|liver function|renal function|lab(oratory)? (value|parameter|test))\b")),
    ("clinical_assessment", 0.80, _rx(r"\b(ECOG|performance status|Karnofsky|electrocardiogram|ECG|EKG|echocardiogra\w*|imaging|MRI|CT scan|ultrasound|endoscop\w*|colonoscop\w*|biops(y|ies)|histolog\w*|radiograph\w*|physical examination|vital signs|spirometry|FEV1|bone mineral density|body composition|joint count|RECIST|disease control rate|mechanical ventilation|clinician[- ]administered|assessed (with|by) the|investigator[- ]assessed|global (impression|assessment))\b")),
    ("healthcare_utilization", 0.80, _rx(r"\b(hospitali[sz]\w*|re-?admission|length of stay|ICU|intensive care|transfus\w*|surger\w*|surgical|operative|re-?operation|discharge|treatment duration|discontinuation|drop-?outs?|adherence|compliance|rescue medications?|concomitant medications?|health(care)? (cost|resource|utili\w*))\b")),
    ("behavioral_functional", 0.78, _rx(r"\b(physical activity|sleep|walking|gait|mobility|functional (status|capacity|independence)|exercis\w*|dietary|nutrition\w*|knowledge|behavio(u)?r\w*|smoking|alcohol|self-?efficacy|caregivers?|breastfeed\w*|muscle (strength|endurance))\b")),
    # Pilot / implementation trials measure whether the study itself worked.
    ("feasibility_implementation", 0.82, _rx(r"\b(feasibilit\w*|acceptabilit\w*|fidelity|recruitment|retention rate|participation rate|implementation|usability|enrol(l)?ment rate|protocol deviation|completion rate|attendance)\b")),
]

MEASURE_RULES = [
    ("time_to_event", 0.92, _rx(r"\b(time to|time until|duration of|overall survival|progression[- ]free|event[- ]free|disease[- ]free|recurrence[- ]free|metastasis[- ]free|cancer[- ]free)\b")),
    ("pk_parameter", 0.92, _rx(r"\b(Cmax\w*|Tmax\w*|AUC\w*|half[- ]life|clearance|volume of distribution|trough concentration|area under ((the|plasma|serum|blood|drug) )*concentration|maximum ((observed|plasma|serum|blood|drug) )*concentration)")),
    ("diagnostic_accuracy", 0.90, _rx(_DIAG_PATTERN)),
    ("change_from_baseline", 0.90, _rx(r"\b(change from baseline|mean change|absolute change|percent change|changes? in)\b")),
    ("proportion", 0.85, _rx(r"\b(percentage of|percent of|proportion of|rates? of|incidence( rate)? (of|per)|freedom from|% of|prevalence of)\b")),
    ("count", 0.80, _rx(r"\b(number of|count of|episodes of|total number|frequency of)\b")),
    ("score_scale", 0.80, _rx(r"\b(scores?|scales?|index|indices|questionnaires?|assessments?|ratings?|grades?)\b")),
    ("concentration", 0.70, _rx(r"\b(levels?|concentrations?|tit(er|re)s?|markers?)\b")),
]

CANONICAL = [
    ("overall_survival", _rx(r"\boverall survival\b")),
    ("progression_free_survival", _rx(r"\bprogression[- ]free survival\b|\bPFS\b")),
    # STEEP 2.0 defines IBCFS (invasive breast cancer-free survival) separately from iDFS, and
    # the registry names them separately, so they stay separate concepts.
    ("invasive_breast_cancer_free_survival", _rx(r"\binvasive breast cancer[- ]free survival\b|\bIBCFS\b")),
    ("invasive_disease_free_survival", _rx(r"\binvasive disease[- ]free survival\b|\biDFS\b")),
    # Distant before any other recurrence- or disease-free concept: "distant disease-free
    # survival" contains "disease-free survival", and the first match wins. Locoregional before
    # plain RFS so "local recurrence-free survival" lands there.
    ("distant_recurrence_free_survival", _rx(r"\bdistant (recurrence|relapse|disease|metastasis)[- ]free (survival|interval)\b|\bD(R|D|M)FS\b|\bDRFI\b")),
    ("locoregional_recurrence", _rx(r"\bipsilateral breast (tumou?r )?recurrence\b|\bIBTR\b|\bloco-?regional recurrence\b|\blocal recurrence\b")),
    ("recurrence_free_survival", _rx(r"\brecurrence[- ]free (survival|interval)\b|\bRFS\b")),
    ("disease_free_survival", _rx(r"\bdisease[- ]free survival\b|\bDFS\b")),
    ("event_free_survival", _rx(r"\bevent[- ]free survival\b|\bEFS\b")),
    # WHO / NIAID ordinal clinical-status scales define themselves by listing categories --
    # "Death", "Hospitalized, on oxygen", "Not hospitalized". The scale is the endpoint; its
    # categories are not. Listed early so it outranks the concepts its definition mentions.
    ("clinical_status_ordinal_scale", _rx(
        # Named clinical-status scales count on sight.
        r"\bclinical progression scale\b|\bordinal clinical (recovery|status|improvement|progression)\b|\bordinal CRS\b"
        # WHO is case-sensitive: "patients who rated it on a 7-point scale" is not the organisation.
        r"|(?-i:\b(WHO|NIAID)[- ](OS|OSCI)\b)|\b(WHO|NIAID)[- ]ordinal\b|\b((?-i:WHO)|World Health Organization)( [\w-]+){0,3} \d+[- ](point|category) (ordinal )?scale\b"
        r"|\bACTT scale\b|\bAdaptive COVID-19 Treatment Trial Scale\b"
        # "7-point ordinal scale" and "clinical status" are everyday wording for any scale (PGIC, vIGA-AD,
        # Nyvad caries criteria: 246 off-target rows, measured), so they count only when the same text
        # names the scale's categories or its setting.
        r"|^(?=[\s\S]*?(hospitali[sz]ed|ventilat|supplemental oxygen|oxygen (therapy|supplementation)|\bon oxygen\b|high[- ]flow|\bECMO\b|(?-i:\bWHO\b)|World Health Organization|NIAID|COVID|SARS-CoV-2))"
        r"[\s\S]*?(\bordinal (scale|outcome|score)s?\b|\b\d+[- ](point|category) ordinal\b|\bclinical status\b)")),
    # Before ORR: DoR definitions routinely mention "ORR" ("in participants with an objective
    # response"), and the first match wins.
    # "DOR" is also doravirine ("Switch to DOR/TDF/3TC"): the abbreviation does not count beside
    # antiretroviral context. In the regex, not a post-check, so the scan goes on to later concepts.
    ("duration_of_response", _rx(r"\bduration of (overall |objective |complete )?response\b"
        r"|^(?![\s\S]*\b(doravirine|islatravir|ISL|TDF|3TC|lamivudine|tenofovir|HIV)\b)[\s\S]*?(?-i:\bDOR\b|\bDoR\b)")),
    ("objective_response_rate", _rx(r"\bobjective response rate\b|\bORR\b|\boverall response rate\b")),
    ("disease_control_rate", _rx(r"\bdisease control rate\b|(?-i:\bDCR\b)")),
    # Pathologic CR (residual-disease-free surgical specimen; an FDA-recognised surrogate in
    # high-risk early breast cancer) is a different endpoint from clinical or radiographic CR.
    # "pCR" is matched case-sensitively: under re.I it would also swallow "PCR" (polymerase
    # chain reaction) in hundreds of COVID-19 endpoints. [tTbB]? catches "tpCR" (total) and
    # "bpCR" (breast), which have no word boundary before the "p".
    ("pathologic_complete_response", _rx(r"\bpatholog\w* complete (response|remission)\b|(?-i:\b[tTbB]?pCR\b)")),
    ("complete_response", _rx(r"\bcomplete (response|remission)\b")),
    ("clinical_benefit_rate", _rx(r"\bclinical benefit rate\b|\bCBR\b")),
    # Neoadjuvant endocrine "window" trials use Ki67 suppression / complete cell-cycle arrest as
    # their primary endpoint: 37 breast cancer benchmark trials did, every one unmapped.
    ("ki67_response", _rx(r"\bcomplete cell[- ]cycle arrest\b|\bCCCA\b|\bKi-?67\b")),
    ("time_to_next_treatment", _rx(r"\btime to (next|subsequent|first subsequent) (treatment|therapy|line)|\btime to treatment discontinuation\b|\bTTNT\b|\bwithout subsequent (line of )?(chemo)?therap|\bwithout first[- ]line treatment discontinuation")),
    # Must precede adverse_event_incidence and hospitalization: DLT definitions routinely
    # say "adverse events ... requiring hospitalization", and the first match wins.
    ("dose_limiting_toxicity", _rx(r"\bdose[- ]limiting toxicit|\bDLTs?\b|\bmaximum tolerated dose\b|\bMTD\b|\brecommended phase (2|II) dose\b|\bRP2D\b")),
    # Any adverse-event endpoint, including a bare "Adverse Events". Serious-only endpoints are
    # re-filed as serious_adverse_events in normalize_endpoint (a combined AE+SAE endpoint is
    # broader than SAEs, so it must stay here); "SAEs" alone never matches \bAEs?\b.
    ("adverse_event_incidence", _rx(r"\badverse events?\b|\b(TE|MA)?AEs?\b|\bAES?Is?\b|\bAECIs?\b")),
    ("serious_adverse_events", _rx(r"\bserious (treatment[- ]emergent )?(adverse events?|AEs?|TEAEs?)\b|\b(SAEs?|STEAEs?|TESAEs?)\b")),
    ("all_cause_mortality", _rx(r"\bmortality\b|\bdeath rate\b")),
    ("hba1c_change", _rx(r"\bHbA1c\b|\bA1c\b|\bglyc(ated|osylated) h(a)?emoglobin\b")),
    ("fasting_glucose", _rx(r"\bfasting (plasma |serum |blood )?glucose\b|\bFPG\b")),
    # Time in range before the generic CGM concept: it is the more specific metric.
    ("cgm_time_in_range", _rx(r"\btime in (target )?range\b|\bTIR\b")),
    ("cgm_glycemic_metric", _rx(r"\bcontinuous glucose monitor|\bCGM\b|\bglyc(a)?emic (variability|excursion)|\bMAGE\b|\bglucose variability\b")),
    # Spelled out on purpose: bare "ACR" is the rheumatology response criterion (ACR20/50/70).
    ("urine_albumin_creatinine_ratio", _rx(r"\balbumin[- ]to[- ]creatinine\b|\bUACR\b")),
    ("blood_pressure", _rx(r"\bblood pressure\b|\bsystolic\b|\bdiastolic\b|\bSBP\b|\bDBP\b")),
    ("body_weight_bmi", _rx(r"\bbody weight\b|\bBMI\b|\bbody mass index\b|\bweight loss\b")),
    ("pain_score", _rx(r"\bpain\b.{0,20}(score|scale|intensity|VAS|NRS)|\b(VAS|NRS)\b.{0,20}pain")),
    ("depression_score", _rx(r"\bdepression\b|\bMADRS\b|\bHAM-D\b|\bPHQ-9\b|\bBDI\b")),
    ("anxiety_score", _rx(r"\banxiety\b|\bHAM-A\b|\bGAD-7\b|\bSTAI\b")),
    ("cognitive_score", _rx(r"\bcognitive\b|\bMMSE\b|\bMoCA\b|\bADAS-Cog\b")),
    ("quality_of_life", _rx(r"\bquality of life\b|\bQoL\b|\bEQ-5D\b|\bSF-36\b")),
    ("seroconversion", _rx(r"\bseroconversion\b|\bseroprotection\b|\bantibody tit(er|re)\b|\bGMT\b")),
    ("viral_load", _rx(r"\bviral load\b|\bviral clearance\b|\bundetectable\b")),
    # Nouns always name the outcome (`hospitalization\b` alone never matched the plural). The
    # participle names it only in outcome phrasing: "participants who were hospitalized" is an
    # endpoint, "in hospitalised adults" is the population and must not match.
    ("hospitalization", _rx(
        r"\bhospitali[sz]ations?\b|\bhospital (admissions?|stays?|days)\b|\blength of (hospital )?stay\b|\bICU admissions?\b"
        r"|(?<!\bin )(?<!\bamong )\b(participants|patients|subjects|people|children|infants|adults)( who| that)?"
        r"( (were|are|was|had been))? (re-?)?hospitali[sz]ed\b"
        r"|\b(were|was|being|ever|days|nights) (re-?)?hospitali[sz]ed\b|\bhospitali[sz]ed (for|due to|because)\b"
        r"|\b(dead|died|death|alive) (or|and) (not )?(re-?)?hospitali[sz]ed\b"
        r"|\bnumber of hospitali[sz]ed (participants|patients|subjects)\b")),
    ("pk_exposure", _rx(r"\bCmax\w*|\bAUC\w*|\bTmax\w*|\bhalf[- ]life\b|\barea under ((the|plasma|serum|blood|drug) )*concentration|\bmaximum ((observed|plasma|serum|blood|drug) )*concentration|\bpharmacokinetic\w* (parameter|profile|exposure)")),
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
    "clinical_benefit_rate": "efficacy",
    "time_to_next_treatment": "efficacy",
    "dose_limiting_toxicity": "safety",
    "fasting_glucose": "biomarker_laboratory",
    "cgm_time_in_range": "biomarker_laboratory",
    "cgm_glycemic_metric": "biomarker_laboratory",
    "urine_albumin_creatinine_ratio": "biomarker_laboratory",
    "invasive_disease_free_survival": "efficacy",
    "pathologic_complete_response": "efficacy",
    "duration_of_response": "efficacy",
    "disease_control_rate": "efficacy",
    "invasive_breast_cancer_free_survival": "efficacy",
    "distant_recurrence_free_survival": "efficacy",
    "locoregional_recurrence": "efficacy",
    "recurrence_free_survival": "efficacy",
    "ki67_response": "biomarker_laboratory",
    "clinical_status_ordinal_scale": "efficacy",
}

# Fallback measure type for a recognised concept whose text names no measure. Without it a
# bare "HbA1c", "Overall Response Rate" or "Systolic Blood Pressure" scores 0.64 and falls
# under the 0.7 confidence bar -- the concept was recognised, only the phrasing was terse.
# Inferred values are flagged via `endpoint_measure_inferred`, never presented as matched.
CANONICAL_MEASURE = {
    "overall_survival": "time_to_event",
    "progression_free_survival": "time_to_event",
    "disease_free_survival": "time_to_event",
    "event_free_survival": "time_to_event",
    "time_to_next_treatment": "time_to_event",
    "objective_response_rate": "proportion",
    "complete_response": "proportion",
    "clinical_benefit_rate": "proportion",
    "cgm_time_in_range": "proportion",
    "seroconversion": "proportion",
    "adverse_event_incidence": "proportion",
    "serious_adverse_events": "proportion",
    "dose_limiting_toxicity": "proportion",
    "all_cause_mortality": "proportion",
    "hospitalization": "count",
    "hba1c_change": "concentration",
    "fasting_glucose": "concentration",
    "urine_albumin_creatinine_ratio": "concentration",
    "viral_load": "concentration",
    "blood_pressure": "continuous_value",
    "body_weight_bmi": "continuous_value",
    "cgm_glycemic_metric": "continuous_value",
    "pain_score": "score_scale",
    "depression_score": "score_scale",
    "anxiety_score": "score_scale",
    "cognitive_score": "score_scale",
    "quality_of_life": "score_scale",
    "pk_exposure": "pk_parameter",
    "invasive_disease_free_survival": "time_to_event",
    "duration_of_response": "time_to_event",
    "pathologic_complete_response": "proportion",
    "disease_control_rate": "proportion",
    "invasive_breast_cancer_free_survival": "time_to_event",
    "distant_recurrence_free_survival": "time_to_event",
    "locoregional_recurrence": "time_to_event",
    "recurrence_free_survival": "time_to_event",
    "ki67_response": "proportion",
    "clinical_status_ordinal_scale": "score_scale",
}

_SAE = _rx(r"\bserious (treatment[- ]emergent )?(adverse events?|AEs?|TEAEs?)\b|\b(SAEs?|STEAEs?|TESAEs?)\b")
_ANY_AE = _rx(r"\badverse events?\b|\b(TE|MA)?AEs?\b|\bAES?Is?\b|\bAECIs?\b")
# A glucose or C-peptide AUC (tolerance tests) is a metabolic response, not drug exposure.
# Insulin is deliberately absent: an insulin AUC is often genuine PK of an insulin product.
_METABOLIC_AUC = _rx(r"\b(glucose|c-?peptide)\b")
# "Non-serious and serious adverse events" shares one noun between two adjectives: all AEs.
_NON_SERIOUS = _rx(r"\bnon[- ]?serious\b")

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

    # Name first, description only as a fallback. Descriptions define terms, and definitions
    # hijack concepts: Overall Survival is "time until death", a DLT is an adverse event
    # "requiring hospitalization", an SAE is an "adverse event that...". The endpoint's own
    # name says what it is; the description is consulted only when the name is silent
    # (e.g. a name of "Primary Efficacy Endpoint").
    canon, source = None, ""
    for text in (measure or "", description or ""):
        for name, rx in CANONICAL:
            if rx.search(text):
                canon, source = name, text
                break
        if canon:
            break

    # Both rules below read the text that produced the match, not the definitions around it.
    if (canon == "adverse_event_incidence" and _SAE.search(source)
            and not _NON_SERIOUS.search(source)
            and not _ANY_AE.search(_SAE.sub(" ", source))):
        canon = "serious_adverse_events"
    if canon == "pk_exposure" and _METABOLIC_AUC.search(source):
        canon = None

    # A recognised standard concept outranks a loose keyword match. Overall Survival is
    # defined as "length of time until death", so the keyword pass alone labels the single
    # most important oncology endpoint as `safety`. The concept is the stronger signal.
    if canon in CANONICAL_DOMAIN:
        domain, dconf, domain_from_concept = CANONICAL_DOMAIN[canon], 0.85, True
    else:
        domain, dconf = _first(DOMAIN_RULES, blob)
        domain_from_concept = False

    measure_inferred = False
    if mtype is None and canon in CANONICAL_MEASURE:
        mtype, mconf, measure_inferred = CANONICAL_MEASURE[canon], 0.75, True

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
        "endpoint_measure_inferred": measure_inferred,
        "normalization_confidence": round(min(1.0, conf), 3),
    }
    rec.update(parse_timeframe(timeframe))
    return rec
