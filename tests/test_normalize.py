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
