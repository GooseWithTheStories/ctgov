"""Tests for endpoint normalization. No network required."""
import pytest

from ctgov import normalize_endpoint, parse_timeframe


class TestCanonicalConcepts:
    def test_overall_survival(self):
        r = normalize_endpoint("Overall Survival", "", "From randomization up to 60 months")
        assert r["endpoint_canonical"] == "overall_survival"
        assert r["endpoint_domain"] == "efficacy"
        assert r["endpoint_measure_type"] == "time_to_event"
        assert r["endpoint_direction"] == "higher_is_better"

    def test_pk_parameter(self):
        r = normalize_endpoint("Cmax of midazolam", "", "0, 0.5, 1, 2 hours post-dose")
        assert r["endpoint_domain"] == "pharmacokinetics"
        assert r["endpoint_measure_type"] == "pk_parameter"

    def test_adverse_events_are_safety_and_lower_is_better(self):
        r = normalize_endpoint(
            "Number of Participants With Treatment-Emergent Adverse Events", "", "90 days"
        )
        assert r["endpoint_domain"] == "safety"
        assert r["endpoint_direction"] == "lower_is_better"

    def test_glycosylated_spelling(self):
        """The registry writes "Glycosylated Haemoglobin" as often as "HbA1c"."""
        r = normalize_endpoint("Change in Glycosylated Haemoglobin", "", "6 months")
        assert r["endpoint_canonical"] == "hba1c_change"
        assert r["endpoint_domain"] == "biomarker_laboratory"

    def test_domain_inferred_from_canonical_is_flagged(self):
        """"Anxiety Rating" hits no domain keyword; the domain comes from the concept."""
        r = normalize_endpoint("Anxiety Rating", "", "Baseline")
        assert r["endpoint_canonical"] == "anxiety_score"
        assert r["endpoint_domain"] == "patient_reported"
        assert r["endpoint_domain_inferred"] is True

    def test_unclassifiable_is_labelled_not_guessed(self):
        r = normalize_endpoint("Bowel Filling Properties: Distension/Distal Ileum", "", "")
        assert r["endpoint_canonical"] is None
        assert r["normalization_confidence"] < 0.7

    def test_raw_text_always_preserved(self):
        raw = "Primary Safety: Freedom From Index Procedure Related Major Complications"
        assert normalize_endpoint(raw, "", "30 days")["endpoint_raw"] == raw


class TestTimeframeParsing:
    @pytest.mark.parametrize(
        "text,days",
        [
            ("6 months", 182.64),
            ("30 days", 30.0),
            ("2 years", 730.5),
            ("12 hours", 0.5),
            ("4 weeks", 28.0),
        ],
    )
    def test_units_convert(self, text, days):
        assert parse_timeframe(text)["horizon_days"] == pytest.approx(days, rel=1e-3)

    def test_takes_the_maximum_and_flags_longitudinal(self):
        r = parse_timeframe("0, 0.5, 1, 1.5, 2, 3, 4, 6, 8, 12 hours post-dose")
        assert r["horizon_days"] == pytest.approx(0.5)
        assert r["is_longitudinal"] is True
        assert r["timepoint_count"] == 10
        # A dense PK schedule is a horizon, not a schedule -- confidence must say so.
        assert r["timeframe_confidence"] < 0.9

    def test_baseline_only(self):
        r = parse_timeframe("Baseline")
        assert r["horizon_days"] == 0.0
        assert r["baseline_anchored"] is True

    def test_unparseable_returns_none_not_zero(self):
        """A missing horizon must be distinguishable from a horizon of zero."""
        r = parse_timeframe("Throughout the study period")
        assert r["horizon_days"] is None
        assert r["timeframe_confidence"] == 0.0

    def test_empty(self):
        assert parse_timeframe("")["horizon_days"] is None


class TestRegressions:
    def test_deaths_plural_matches_safety(self):
        """`death\\b` never matched "Deaths" -- caught by inspecting real registry text."""
        assert normalize_endpoint("Number of Deaths.", "", "")["endpoint_domain"] == "safety"

    def test_count_not_limited_to_participants(self):
        """`number of (participants)` missed "Number of Episodes"."""
        r = normalize_endpoint("Number of Episodes of Treatment Failure", "", "")
        assert r["endpoint_measure_type"] == "count"

    def test_overall_survival_is_efficacy_not_safety(self):
        """OS is defined as "time until death"; the keyword pass alone called it safety."""
        r = normalize_endpoint(
            "Overall Survival (OS), the Length of Time From Randomization Until Death", "", "24 months"
        )
        assert r["endpoint_canonical"] == "overall_survival"
        assert r["endpoint_domain"] == "efficacy"


class TestV011Fixes:
    """Defects found by auditing the v1 endpoint benchmark against real registry text."""

    # --- a recognised concept must not be discarded for terse phrasing
    @pytest.mark.parametrize(
        "text,canon,measure",
        [
            ("HbA1c", "hba1c_change", "concentration"),
            ("Hemoglobin A1c", "hba1c_change", "concentration"),
            ("Overall Response Rate", "objective_response_rate", "proportion"),
            ("Systolic Blood Pressure", "blood_pressure", "continuous_value"),
        ],
    )
    def test_terse_concept_clears_confidence_bar(self, text, canon, measure):
        r = normalize_endpoint(text, "", "6 months")
        assert r["endpoint_canonical"] == canon
        assert r["endpoint_measure_type"] == measure
        assert r["endpoint_measure_inferred"] is True
        assert r["normalization_confidence"] >= 0.7

    def test_stated_measure_is_not_overridden(self):
        r = normalize_endpoint("Mean Change From Baseline in HbA1c", "", "26 weeks")
        assert r["endpoint_measure_type"] == "change_from_baseline"
        assert r["endpoint_measure_inferred"] is False

    # --- dose-limiting toxicity: the standard Phase 1 primary endpoint
    def test_dlt_is_safety_not_hospitalization(self):
        """DLT definitions say "requiring hospitalization"; that keyword hijacked the concept."""
        r = normalize_endpoint(
            "Number of Participants With Dose-Limiting Toxicities (DLTs) Requiring Hospitalization", "", ""
        )
        assert r["endpoint_canonical"] == "dose_limiting_toxicity"
        assert r["endpoint_domain"] == "safety"

    @pytest.mark.parametrize("text", ["Maximum Tolerated Dose (MTD)", "Recommended Phase 2 Dose (RP2D)"])
    def test_phase1_dose_finding_endpoints(self, text):
        assert normalize_endpoint(text, "", "")["endpoint_canonical"] == "dose_limiting_toxicity"

    # --- pCR vs PCR: the case-sensitivity trap
    def test_pcr_abbreviation_is_pathologic_complete_response(self):
        r = normalize_endpoint("pCR Rate in the Breast and Axilla", "", "")
        assert r["endpoint_canonical"] == "pathologic_complete_response"

    def test_covid_pcr_is_not_complete_response(self):
        """Polymerase chain reaction appears in hundreds of COVID endpoints and must stay out."""
        r = normalize_endpoint("Percentage of Participants With Positive SARS-CoV-2 RT-PCR", "", "")
        assert r["endpoint_canonical"] != "complete_response"
        assert r["endpoint_canonical"] != "pathologic_complete_response"

    # --- oncology real-world endpoints
    def test_time_to_next_treatment(self):
        r = normalize_endpoint("Time to Next Treatment (TTNT)", "", "")
        assert r["endpoint_canonical"] == "time_to_next_treatment"
        assert r["endpoint_measure_type"] == "time_to_event"

    def test_chemo_free_endpoint_is_efficacy_despite_death(self):
        r = normalize_endpoint("Probability of Participants Without Subsequent Chemotherapy or Death", "", "")
        assert r["endpoint_canonical"] == "time_to_next_treatment"
        assert r["endpoint_domain"] == "efficacy"

    def test_clinical_benefit_rate(self):
        assert normalize_endpoint("Clinical Benefit Rate (CBR)", "", "")["endpoint_canonical"] == "clinical_benefit_rate"

    # --- modern diabetes endpoints
    def test_time_in_range_beats_generic_cgm(self):
        r = normalize_endpoint("Percent Time in Range (70-180 mg/dL) Measured by CGM", "", "")
        assert r["endpoint_canonical"] == "cgm_time_in_range"

    def test_glycemic_variability(self):
        r = normalize_endpoint("Mean Amplitude of Glycemic Excursion (MAGE)", "", "")
        assert r["endpoint_canonical"] == "cgm_glycemic_metric"

    def test_fasting_glucose_keeps_stated_measure(self):
        r = normalize_endpoint("Change From Baseline in Fasting Plasma Glucose", "", "")
        assert r["endpoint_canonical"] == "fasting_glucose"
        assert r["endpoint_measure_type"] == "change_from_baseline"
        assert r["endpoint_measure_inferred"] is False

    def test_uacr(self):
        r = normalize_endpoint("Change in Urine Albumin-to-Creatinine Ratio", "", "")
        assert r["endpoint_canonical"] == "urine_albumin_creatinine_ratio"

    def test_rheumatology_acr20_is_not_uacr(self):
        r = normalize_endpoint("Percentage of Participants Achieving ACR20 Response", "", "")
        assert r["endpoint_canonical"] != "urine_albumin_creatinine_ratio"


class TestBenchmarkAuditFixes:
    """Defects found by reading benchmark v2 and by a buyer review of it."""

    # --- serious vs any adverse events
    def test_serious_only_is_sae(self):
        r = normalize_endpoint("Number of Participants With Serious Adverse Events (SAEs)", "", "")
        assert r["endpoint_canonical"] == "serious_adverse_events"

    def test_combined_ae_and_sae_stays_ae(self):
        """Broader than SAEs alone; reordering SAE ahead of AE would have mislabelled this."""
        r = normalize_endpoint("Incidence of Adverse Events (AEs), Serious Adverse Events (SAEs)", "", "")
        assert r["endpoint_canonical"] == "adverse_event_incidence"

    @pytest.mark.parametrize("text", ["Adverse Events", "Number of AEs", "Incidence of TEAEs"])
    def test_bare_adverse_events(self, text):
        assert normalize_endpoint(text, "", "")["endpoint_canonical"] == "adverse_event_incidence"

    def test_bare_saes(self):
        assert normalize_endpoint("SAEs", "", "")["endpoint_canonical"] == "serious_adverse_events"

    # --- pharmacokinetics
    @pytest.mark.parametrize("text", [
        "AUC0-t",
        "AUCτ of Drug X at Steady State",
        "Area Under the Concentration-Time Curve From Time 0 to Infinity",
        "Maximum Observed Plasma Concentration",
        "Cmax,ss",
        "Maximum Observed Serum Drug Concentration",
    ])
    def test_pk_variants(self, text):
        assert normalize_endpoint(text, "", "")["endpoint_canonical"] == "pk_exposure"

    def test_glucose_auc_is_not_drug_exposure(self):
        r = normalize_endpoint("Glucose AUC During Oral Glucose Tolerance Test", "", "")
        assert r["endpoint_canonical"] != "pk_exposure"

    def test_insulin_product_auc_is_still_pk(self):
        r = normalize_endpoint("AUC of Insulin Degludec", "", "")
        assert r["endpoint_canonical"] == "pk_exposure"

    # --- oncology concepts a breast cancer specialist looks for first
    def test_duration_of_response(self):
        r = normalize_endpoint("Duration of Response (DOR) in Participants With ORR", "", "")
        assert r["endpoint_canonical"] == "duration_of_response"

    def test_disease_control_rate(self):
        r = normalize_endpoint("Disease Control Rate (DCR) Based on RECIST v1.1", "", "")
        assert r["endpoint_canonical"] == "disease_control_rate"
        assert r["endpoint_domain"] == "efficacy"

    def test_ibcfs_is_its_own_concept(self):
        r = normalize_endpoint("Invasive Breast Cancer-free Survival (IBCFS)", "", "")
        assert r["endpoint_canonical"] == "invasive_breast_cancer_free_survival"

    def test_invasive_dfs(self):
        r = normalize_endpoint("Invasive Disease-Free Survival (iDFS)", "", "")
        assert r["endpoint_canonical"] == "invasive_disease_free_survival"

    def test_plain_dfs_unchanged(self):
        assert normalize_endpoint("Disease-Free Survival", "", "")["endpoint_canonical"] == "disease_free_survival"

    @pytest.mark.parametrize("text", ["Pathological Complete Response (pCR)", "tpCR", "bpCR Rate"])
    def test_pathologic_complete_response(self, text):
        assert normalize_endpoint(text, "", "")["endpoint_canonical"] == "pathologic_complete_response"

    def test_clinical_complete_response_stays_distinct(self):
        r = normalize_endpoint("Complete Response Rate", "", "")
        assert r["endpoint_canonical"] == "complete_response"


class TestDescriptionCannotHijack:
    """Descriptions define terms; the endpoint's name says what it is."""

    def test_sae_defined_in_terms_of_aes_stays_sae(self):
        r = normalize_endpoint(
            "Serious Adverse Events",
            "SAEs are adverse events that result in death, are life-threatening or require hospitalization.",
            "",
        )
        assert r["endpoint_canonical"] == "serious_adverse_events"

    def test_non_serious_and_serious_means_all_aes(self):
        r = normalize_endpoint("Number of Participants With Non-serious and Serious Adverse Events", "", "")
        assert r["endpoint_canonical"] == "adverse_event_incidence"

    def test_blood_pressure_with_ae_note_stays_blood_pressure(self):
        r = normalize_endpoint(
            "Change From Baseline in Systolic Blood Pressure", "Adverse events were also recorded.", ""
        )
        assert r["endpoint_canonical"] == "blood_pressure"

    def test_hospitalization_with_ae_wording_stays_hospitalization(self):
        r = normalize_endpoint(
            "Hospitalization for Heart Failure", "Hospitalizations due to adverse events are included.", ""
        )
        assert r["endpoint_canonical"] == "hospitalization"

    def test_drug_pk_with_glucose_in_description_stays_pk(self):
        """The glucose-AUC guard must read the name, not a note about glucose-lowering effect."""
        r = normalize_endpoint("Elimination Half-Life (t1/2)", "Effect on plasma glucose was also assessed.", "")
        assert r["endpoint_canonical"] == "pk_exposure"

    def test_glucose_auc_in_the_name_is_still_not_pk(self):
        r = normalize_endpoint("Glucose AUC", "Measured during a mixed-meal tolerance test.", "")
        assert r["endpoint_canonical"] != "pk_exposure"

    def test_silent_name_falls_back_to_description(self):
        r = normalize_endpoint("Primary Efficacy Endpoint", "Change from baseline in HbA1c at week 26.", "")
        assert r["endpoint_canonical"] == "hba1c_change"

    def test_overall_survival_unchanged(self):
        r = normalize_endpoint("Overall Survival", "Time from randomization to death from any cause.", "")
        assert r["endpoint_canonical"] == "overall_survival"
        assert r["endpoint_domain"] == "efficacy"


class TestAdjuvantEndpoints:
    """Checked against breast cancer benchmark primaries before being added."""

    @pytest.mark.parametrize("text,canon", [
        ("Distant Recurrence-Free Survival (DRFS)", "distant_recurrence_free_survival"),
        ("Distant Disease-Free Survival", "distant_recurrence_free_survival"),
        ("Recurrence-Free Survival (RFS)", "recurrence_free_survival"),
        ("Ipsilateral Breast Tumor Recurrence", "locoregional_recurrence"),
        ("Local Recurrence-Free Survival", "locoregional_recurrence"),
        ("Disease-Free Survival", "disease_free_survival"),
        ("Complete Cell Cycle Arrest (CCCA) Rate", "ki67_response"),
        ("Change in Ki67 Expression", "ki67_response"),
    ])
    def test_concepts(self, text, canon):
        assert normalize_endpoint(text, "", "")["endpoint_canonical"] == canon

    def test_named_pcr_beats_ki67(self):
        r = normalize_endpoint("Pathologic Complete Response and Ki67 Change", "", "")
        assert r["endpoint_canonical"] == "pathologic_complete_response"

    def test_recurrence_free_is_stated_time_to_event(self):
        r = normalize_endpoint("Recurrence-Free Survival", "", "")
        assert r["endpoint_measure_type"] == "time_to_event"
        assert r["endpoint_measure_inferred"] is False


class TestHospitalizationAndAbbreviations:
    @pytest.mark.parametrize("text,canon", [
        ("Number of Cardiovascular-Related Hospitalizations", "hospitalization"),
        ("Number of Participants Hospitalized", "hospitalization"),
        ("Number of Participants With Any MAAEs", "adverse_event_incidence"),
        ("Incidence of AESIs", "adverse_event_incidence"),
    ])
    def test_concepts(self, text, canon):
        assert normalize_endpoint(text, "", "")["endpoint_canonical"] == canon


class TestStemsInsideWordBoundaries:
    """`\\b(toxicit|...)\\b` never matched "toxicity": the trailing boundary killed every stem."""

    @pytest.mark.parametrize("text,domain", [
        ("Toxicity", "safety"),
        ("Incidence of Hypoglycemia", "safety"),
        ("Feasibility of Enrollment", "feasibility_implementation"),
        ("Number of Participants Requiring Red Blood Cell Transfusion", "healthcare_utilization"),
        ("Immunogenicity", "immunogenicity"),
        ("Sensitivity and Specificity of the Assay", "diagnostic_accuracy"),
    ])
    def test_domain(self, text, domain):
        assert normalize_endpoint(text, "", "")["endpoint_domain"] == domain

    def test_plural_scores(self):
        assert normalize_endpoint("Total Symptom Scores", "", "")["endpoint_measure_type"] == "score_scale"


class TestRulesSwitchedOnByPatchE:
    """Fixing the stems un-broke rules that had never fired, so had never been tested for precision."""

    @pytest.mark.parametrize("text", [
        "Insulin Sensitivity",
        "Contrast Sensitivity",
        "Mean Schiff Sensitivity Score",
        "Change in High-Sensitivity C-Reactive Protein",
        "Sensitivity Analysis of Neurologist Visits",
    ])
    def test_everyday_sensitivity_is_not_diagnostic(self, text):
        r = normalize_endpoint(text, "", "")
        assert r["endpoint_measure_type"] != "diagnostic_accuracy"
        assert r["endpoint_domain"] != "diagnostic_accuracy"

    @pytest.mark.parametrize("text", [
        "Sensitivity and Specificity of the Assay",
        "Sensitivity of the Irregular Rhythm Notification Feature",
        "Positive Predictive Value",
        "Area Under the ROC Curve",
    ])
    def test_diagnostic_context_still_counts(self, text):
        assert normalize_endpoint(text, "", "")["endpoint_domain"] == "diagnostic_accuracy"

    @pytest.mark.parametrize("text", [
        "Number of Participants That Were Hospitalized Due to COVID-19 Symptoms",
        "Nights Hospitalized",
        "Length of Hospital Stay",
        "Number of Hospital Admissions",
    ])
    def test_hospitalization_outcomes(self, text):
        assert normalize_endpoint(text, "", "")["endpoint_canonical"] == "hospitalization"

    @pytest.mark.parametrize("text", [
        "Clinical Management of Influenza-like Illness in Hospitalised Adults",
        "Changes in Platelets Over Time (Hospitalised Participants Only)",
        "Viral Clearance in Adults Hospitalized With COVID-19",
    ])
    def test_hospitalized_population_is_not_the_outcome(self, text):
        assert normalize_endpoint(text, "", "")["endpoint_canonical"] != "hospitalization"

    def test_dead_or_hospitalised_composite(self):
        r = normalize_endpoint("Days Dead or Hospitalised During the First 60 Days", "", "")
        assert r["endpoint_canonical"] == "hospitalization"

    def test_alive_and_not_hospitalized_composite(self):
        r = normalize_endpoint("Days Alive and Not Hospitalized", "", "")
        assert r["endpoint_canonical"] == "hospitalization"


class TestAbbreviationsFoundInTheV12Diff:
    """Defects found by auditing the exact row-level diff between dataset v1.1 and v1.2."""

    @pytest.mark.parametrize("text", [
        "Number of Participants Who Experienced One or More Serious AE (SAE)",
        "Number of Participants With Serious TEAEs",
        "Number of Participants With Treatment-Emergent Serious Adverse Events (TESAEs)",
    ])
    def test_abbreviated_serious_aes_are_serious(self, text):
        assert normalize_endpoint(text, "", "")["endpoint_canonical"] == "serious_adverse_events"

    def test_any_and_serious_teaes_together_is_any_ae(self):
        r = normalize_endpoint("Number of Participants With TEAEs and Serious TEAEs", "", "")
        assert r["endpoint_canonical"] == "adverse_event_incidence"

    @pytest.mark.parametrize("text", [
        "Number of Participants Who Experienced a Change in Weight After a Switch to DOR/TDF/3TC at 1 Year",
        "Percentage of Participants Receiving DOR or ISL With HIV-1 RNA <50 Copies/mL",
    ])
    def test_doravirine_is_not_duration_of_response(self, text):
        assert normalize_endpoint(text, "", "")["endpoint_canonical"] != "duration_of_response"

    def test_weight_endpoint_still_reaches_its_concept(self):
        # The scan must continue past the refused DOR to the concept the name actually names.
        r = normalize_endpoint("Number of Participants Who Experienced a Change in BMI Category After a Switch to DOR/TDF/3TC", "", "")
        assert r["endpoint_canonical"] == "body_weight_bmi"

    @pytest.mark.parametrize("text", ["Duration of Response (DOR) Per RECIST v1.1 by BICR", "Part 2: DoR"])
    def test_oncology_dor_still_counts(self, text):
        assert normalize_endpoint(text, "", "")["endpoint_canonical"] == "duration_of_response"


class TestOrdinalScaleIsTheEndpoint:
    """A scale that lists "Death" and "Hospitalized" as categories is not a death or hospitalization endpoint."""

    SCALE = ("Ordinal scale: 1) not hospitalized with resumption of normal activities; 2) not hospitalized, "
             "limitation of activities; 3) hospitalized, no oxygen; 7) hospitalized, on invasive mechanical "
             "ventilation; 8) death.")

    def test_named_scale(self):
        r = normalize_endpoint("Clinical Status on the WHO 8-Point Ordinal Scale", "", "")
        assert r["endpoint_canonical"] == "clinical_status_ordinal_scale"
        assert r["endpoint_domain"] == "efficacy"

    def test_silent_name_with_scale_definition_is_the_scale(self):
        r = normalize_endpoint("Time to Improvement of One Category", self.SCALE, "")
        assert r["endpoint_canonical"] == "clinical_status_ordinal_scale"

    def test_not_hospitalized_in_a_definition_is_not_an_outcome(self):
        r = normalize_endpoint("Time to Recovery", "Recovery means not hospitalized and back to usual activities.", "")
        assert r["endpoint_canonical"] != "hospitalization"

    @pytest.mark.parametrize("text", [
        "Clinical Improvement of >= 2 Points Using the WHO-OSCI",
        "Improvement of 1 Category at World Health Organization 7 Point Scale",
        "Time to Sustained Improvement on the 6-point Ordinal Clinical Recovery Scale",
        "Adaptive COVID-19 Treatment Trial Scale (ACTT) Version II",
    ])
    def test_scale_name_variants(self, text):
        assert normalize_endpoint(text, "", "")["endpoint_canonical"] == "clinical_status_ordinal_scale"

    def test_lowercase_who_is_not_the_organisation(self):
        r = normalize_endpoint("Proportion of Participants who Rated Pain on a 7-point Scale", "", "")
        assert r["endpoint_canonical"] != "clinical_status_ordinal_scale"

    @pytest.mark.parametrize("measure, description", [
        ("Achievement of vIGA-AD Success at Week 16", "The vIGA-AD is a 5-point ordinal scale from 0 (clear) to 4 (severe)."),
        ("Patient Global Impression of Change", "PGIC is a 7-point ordinal scale of overall clinical status."),
        ("Severity of White Spot Lesions by Nyvad Criteria", "Clinical status of each lesion was scored."),
        ("Time to Confirmed Disability Progression", "EDSS is an ordinal clinical rating scale from 0 to 10."),
    ])
    def test_everyday_ordinal_wording_is_not_the_clinical_status_scale(self, measure, description):
        assert normalize_endpoint(measure, description, "")["endpoint_canonical"] != "clinical_status_ordinal_scale"

    def test_generic_wording_counts_with_the_scale_setting(self):
        r = normalize_endpoint("Responses on WHO 11-point Ordinal Outcomes Score", "", "")
        assert r["endpoint_canonical"] == "clinical_status_ordinal_scale"
