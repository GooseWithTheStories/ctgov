"""ctgov -- paginating ClinicalTrials.gov client with endpoint normalization.

Two things the registry makes harder than it should be:

1. **Pagination.** A response is capped at 1,000 studies. :class:`Client` follows
   `nextPageToken` for you, so your result set is bounded by your query, not the page size.
2. **Free-text endpoints.** Outcome measures are prose. The registry will hand you
   ``"Serum Markers (HbA1c) to Follow the Evolution of Liver Damage"`` with a timeframe of
   ``"0, 0.5, 1, 1.5, 2 ... hours post-dose"``. You cannot group or compare across trials
   with that. :func:`normalize_endpoint` turns it into structured fields.

Quick start::

    from ctgov import endpoints

    for row in endpoints("AREA[Phase]PHASE3", max_studies=200):
        print(row["endpoint_canonical"], row["horizon_days"], row["condition_primary"])

Normalization is deterministic and rule-based -- no model inference, no API key, no network
call beyond the registry itself. Every normalized field sits beside the raw text it came
from, and each row carries a ``normalization_confidence`` so you can filter to the precision
your analysis needs (``>= 0.7`` is a sensible default).

Data source: ClinicalTrials.gov, U.S. National Library of Medicine. Public domain.
NLM asks that products using its data carry this notice:

    This product uses publicly available data from the U.S. National Library of Medicine
    (NLM), National Institutes of Health, Department of Health and Human Services; NLM is
    not responsible for the product and does not endorse or recommend this or any other
    product.
"""
from __future__ import annotations

from typing import Any, Dict, Iterator, Optional, Sequence

from .client import BASE_URL, Client, CTGovError
from .normalize import normalize_endpoint, parse_timeframe

__version__ = "0.1.1"
__all__ = [
    "Client",
    "CTGovError",
    "normalize_endpoint",
    "parse_timeframe",
    "endpoints",
    "study_context",
    "BASE_URL",
    "__version__",
]

# Minimal field set needed to build normalized endpoint rows. Requesting only these
# makes the fetch substantially faster and lighter on the registry than pulling
# whole study records.
ENDPOINT_FIELDS = (
    "protocolSection.identificationModule.nctId",
    "protocolSection.statusModule.overallStatus",
    "protocolSection.statusModule.startDateStruct",
    "protocolSection.designModule.phases",
    "protocolSection.designModule.studyType",
    "protocolSection.designModule.enrollmentInfo",
    "protocolSection.designModule.designInfo",
    "protocolSection.conditionsModule.conditions",
    "protocolSection.armsInterventionsModule.interventions",
    "protocolSection.outcomesModule",
    "protocolSection.sponsorCollaboratorsModule.leadSponsor",
    "hasResults",
)


def _join(values) -> str:
    return "; ".join(v for v in values if v) if values else ""


def study_context(study: Dict[str, Any]) -> Dict[str, Any]:
    """Flatten the study-level fields worth carrying onto every endpoint row."""
    protocol = study.get("protocolSection", {})
    ident = protocol.get("identificationModule", {})
    status = protocol.get("statusModule", {})
    design = protocol.get("designModule", {})
    conditions = protocol.get("conditionsModule", {}).get("conditions", []) or []
    interventions = protocol.get("armsInterventionsModule", {}).get("interventions", []) or []
    sponsor = protocol.get("sponsorCollaboratorsModule", {}).get("leadSponsor", {}) or {}
    enrollment = design.get("enrollmentInfo", {}) or {}
    design_info = design.get("designInfo", {}) or {}

    return {
        "nct_id": ident.get("nctId"),
        "overall_status": status.get("overallStatus"),
        "start_date": (status.get("startDateStruct", {}) or {}).get("date"),
        "phase": _join(design.get("phases", []) or []),
        "study_type": design.get("studyType"),
        "enrollment_count": enrollment.get("count"),
        "enrollment_type": enrollment.get("type"),
        "condition_primary": conditions[0] if conditions else "",
        "conditions_all": _join(conditions),
        "intervention_types": _join(i.get("type", "") for i in interventions),
        "intervention_names": _join(i.get("name", "") for i in interventions),
        "lead_sponsor": sponsor.get("name"),
        "sponsor_class": sponsor.get("class"),
        "allocation": design_info.get("allocation"),
        "masking": (design_info.get("maskingInfo", {}) or {}).get("masking"),
        "primary_purpose": design_info.get("primaryPurpose"),
        "has_results": study.get("hasResults"),
    }


def endpoints(
    query: str = "",
    *,
    filters: Optional[Dict[str, str]] = None,
    max_studies: Optional[int] = None,
    client: Optional[Client] = None,
    fields: Sequence[str] = ENDPOINT_FIELDS,
) -> Iterator[Dict[str, Any]]:
    """Stream normalized endpoint rows -- one per (study, outcome measure).

    This is the function most users want: it goes from a query straight to structured
    rows, handling pagination and normalization in between.

    Each row carries the study context (phase, condition, enrollment, sponsor...), the
    normalized endpoint fields (domain, measure type, canonical concept, direction,
    ``horizon_days``), and the untouched raw text so any row can be audited.

    Args:
        query: `query.term` expression. Empty matches all studies.
        filters: extra `filter.*` params, e.g. ``{"overallStatus": "COMPLETED"}``.
        max_studies: stop after this many *studies* (not endpoints).
        client: supply your own :class:`Client` to control rate limiting or user agent.
        fields: field paths to request; defaults to the minimum this function needs.

    Yields:
        dict: one normalized endpoint row.

    Example::

        rows = [r for r in endpoints("AREA[Phase]PHASE3", max_studies=100)
                if r["normalization_confidence"] >= 0.7]
    """
    client = client or Client()
    for study in client.iter_studies(
        query, fields=fields, filters=filters, max_studies=max_studies
    ):
        context = study_context(study)
        if not context["nct_id"]:
            continue
        outcomes = study.get("protocolSection", {}).get("outcomesModule", {}) or {}
        for role in ("primary", "secondary"):
            for index, outcome in enumerate(outcomes.get(f"{role}Outcomes", []) or []):
                measure = outcome.get("measure")
                if not measure:
                    continue
                row = dict(context)
                row.update(
                    normalize_endpoint(
                        measure,
                        outcome.get("description", ""),
                        outcome.get("timeFrame", ""),
                    )
                )
                row["endpoint_role"] = role
                row["endpoint_index"] = index
                yield row
