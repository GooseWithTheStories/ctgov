"""Paginating client for the ClinicalTrials.gov API v2.

The registry caps a single response at 1,000 studies and hands back a `nextPageToken`.
Existing wrappers stop there, which is why "how do I get more than 1000 studies?" is the
most-repeated open request against them. This client follows the token for you, so the
result set is bounded by your query rather than by the page size.

    from ctgov import Client

    client = Client()
    studies = client.studies("AREA[Phase]PHASE3", max_studies=5000)   # paginates
    for study in client.iter_studies("cancer"):                       # streams
        ...

Politeness is built in, not left to the caller: NLM asks for no more than 20 requests/second
per IP, and this client stays well under by default and retries with backoff on failure.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, Iterator, List, Optional, Sequence

__all__ = ["Client", "CTGovError"]

BASE_URL = "https://clinicaltrials.gov/api/v2/"
PAGE_MAX = 1000  # hard cap imposed by the API


class CTGovError(RuntimeError):
    """Raised when the registry cannot be reached or returns an unusable response."""


class Client:
    """A ClinicalTrials.gov API v2 client that pages through results transparently.

    Args:
        delay: seconds to sleep between requests. Default 0.34 (~3/s), far below NLM's
            20/s ceiling. Lower it only if you know your use case justifies it.
        retries: attempts per request before giving up. Backoff is exponential.
        timeout: per-request socket timeout, seconds.
        user_agent: sent on every request. Please set something identifying so NLM can
            contact you rather than blocking you.
    """

    def __init__(
        self,
        delay: float = 0.34,
        retries: int = 5,
        timeout: int = 120,
        user_agent: str = "ctgov-python (+https://pypi.org/project/ctgov/)",
    ) -> None:
        self.delay = delay
        self.retries = retries
        self.timeout = timeout
        self.user_agent = user_agent

    # ------------------------------------------------------------------ internals
    def _get(self, path: str, params: Dict[str, Any]) -> Dict[str, Any]:
        url = BASE_URL + path + "?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, headers={"User-Agent": self.user_agent})
        last: Optional[Exception] = None
        for attempt in range(self.retries):
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    payload = json.loads(resp.read().decode("utf-8"))
                time.sleep(self.delay)
                return payload
            except urllib.error.HTTPError as exc:
                # 4xx other than rate-limiting will not fix themselves; fail fast.
                if exc.code < 500 and exc.code != 429:
                    raise CTGovError(f"HTTP {exc.code} for {url}") from exc
                last = exc
            except Exception as exc:  # network flakiness, malformed JSON
                last = exc
            time.sleep(2 ** attempt)
        raise CTGovError(f"failed after {self.retries} attempts: {last}")

    # -------------------------------------------------------------------- public
    def version(self) -> Dict[str, Any]:
        """Return the API version block. Useful as a connectivity check."""
        return self._get("version", {})

    def iter_studies(
        self,
        query: str = "",
        *,
        fields: Optional[Sequence[str]] = None,
        filters: Optional[Dict[str, str]] = None,
        page_size: int = PAGE_MAX,
        max_studies: Optional[int] = None,
    ) -> Iterator[Dict[str, Any]]:
        """Yield studies one at a time, following pagination for as long as needed.

        Prefer this over :meth:`studies` for large result sets: it never holds more than
        one page in memory, so pulling six figures of studies stays flat in RAM.

        Args:
            query: `query.term` expression, e.g. ``"AREA[Phase]PHASE3"``. Empty matches all.
            fields: restrict the payload to these field paths. Fewer fields is markedly
                faster and lighter on the registry.
            filters: extra `filter.*` params, e.g. ``{"overallStatus": "COMPLETED"}``.
            page_size: studies per request, capped at 1000 by the API.
            max_studies: stop after this many. ``None`` means every match.
        """
        params: Dict[str, Any] = {
            "pageSize": min(page_size, PAGE_MAX),
            "format": "json",
        }
        if query:
            params["query.term"] = query
        if fields:
            params["fields"] = "|".join(fields)
        for key, value in (filters or {}).items():
            params[f"filter.{key}" if not key.startswith("filter.") else key] = value

        seen = 0
        token: Optional[str] = None
        while True:
            if token:
                params["pageToken"] = token
            payload = self._get("studies", params)
            batch = payload.get("studies", [])
            if not batch:
                return
            for study in batch:
                yield study
                seen += 1
                if max_studies is not None and seen >= max_studies:
                    return
            token = payload.get("nextPageToken")
            if not token:
                return

    def studies(
        self,
        query: str = "",
        *,
        fields: Optional[Sequence[str]] = None,
        filters: Optional[Dict[str, str]] = None,
        max_studies: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Return studies as a list, paginating past the 1,000-per-response cap.

        Convenience wrapper around :meth:`iter_studies`. Pass ``max_studies`` when you do
        not actually need everything -- an unbounded query against the whole registry is
        hundreds of thousands of records.
        """
        return list(
            self.iter_studies(
                query, fields=fields, filters=filters, max_studies=max_studies
            )
        )

    def count(self, query: str = "", filters: Optional[Dict[str, str]] = None) -> int:
        """Return how many studies match, without downloading them."""
        params: Dict[str, Any] = {"pageSize": 1, "countTotal": "true", "format": "json"}
        if query:
            params["query.term"] = query
        for key, value in (filters or {}).items():
            params[f"filter.{key}" if not key.startswith("filter.") else key] = value
        payload = self._get("studies", params)
        total = payload.get("totalCount")
        if total is None:
            raise CTGovError("registry did not return totalCount")
        return int(total)

    def study(self, nct_id: str) -> Dict[str, Any]:
        """Fetch a single study by its NCT identifier."""
        return self._get(f"studies/{nct_id}", {"format": "json"})
