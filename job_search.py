"""Job search via JSearch (RapidAPI) — searches Indeed, LinkedIn, Glassdoor.

Strategy: run a handful of broad pharma/biotech queries near Philadelphia,
deduplicate by job ID, then keep only results whose employer name matches
a known pharmaceutical or CRO company.
"""
import logging
import time
from typing import Any

import requests

log = logging.getLogger(__name__)

# ── Company allow-list ────────────────────────────────────────────────────────
# Checked as substrings (lowercase) against the employer_name field.
PHARMA_COMPANIES: set[str] = {
    # Global big pharma
    "abbvie", "allergan", "amgen", "astrazeneca", "bayer", "biogen",
    "biomarin", "biontech", "bristol myers squibb", "bms",
    "eli lilly", "lilly", "emergent biosolutions", "genentech",
    "gilead", "glaxosmithkline", "gsk", "johnson & johnson", "j&j",
    "janssen", "merck", "moderna", "novartis", "novo nordisk",
    "pfizer", "regeneron", "roche", "sanofi", "shire", "takeda",
    "ucb", "united therapeutics", "vertex", "viatris",
    # Mid-size & specialty pharma
    "acadia pharmaceuticals", "achaogen", "alexion", "amicus",
    "arena pharmaceuticals", "corcept", "exelixis",
    "horizon therapeutics", "incyte", "jazz pharmaceuticals",
    "mallinckrodt", "passage bio", "recro pharma",
    "relay therapeutics", "spark therapeutics", "sun pharma", "teva",
    # CROs & CDMOs (frequent pharma employers near Philadelphia)
    "catalent", "charles river", "covance", "icon plc",
    "iqvia", "labcorp", "lonza", "medpace", "parexel",
    "ppd", "pra health", "syneos", "thermo fisher",
    "west pharmaceutical", "wuxi",
    # Biotech hubs in PA / NJ / DE
    "agenus", "ionis", "neurocrine", "seagen",
}

# Queries sent to JSearch. Kept intentionally small to stay within the free
# 200-request/month tier (5 queries × ~2 pages × 30 days ≈ 300 req — upgrade
# to Basic tier ($10/mo) for larger volumes).
SEARCH_QUERIES = [
    "pharmaceutical scientist",
    "biotech clinical research",
    "drug development regulatory affairs",
    "pharmacovigilance medical affairs",
    "pharmaceutical manufacturing quality assurance",
]

DATE_POSTED_MAP = {1: "today", 2: "today", 3: "3days", 7: "week"}


class JobSearcher:
    _BASE_URL = "https://jsearch.p.rapidapi.com/search"

    def __init__(self, config):
        self.config = config
        self._headers = {
            "X-RapidAPI-Key": config.rapidapi_key,
            "X-RapidAPI-Host": "jsearch.p.rapidapi.com",
        }

    # ── Public ────────────────────────────────────────────────────────────────

    def search_all(self) -> list[dict]:
        """Return deduplicated, normalised pharma jobs near home address."""
        seen: dict[str, dict] = {}
        date_posted = DATE_POSTED_MAP.get(self.config.days_back, "3days")

        for query in SEARCH_QUERIES:
            for raw in self._search(query, date_posted):
                jid = raw.get("job_id", "")
                if jid and jid not in seen:
                    seen[jid] = raw
            time.sleep(1.2)  # Stay well within RapidAPI rate limits

        pharma = [j for j in seen.values() if self._is_pharma(j.get("employer_name", ""))]
        log.info("Kept %d/%d jobs matching pharma company list", len(pharma), len(seen))
        return [self.normalize(j) for j in pharma]

    # ── Private ───────────────────────────────────────────────────────────────

    def _search(self, query: str, date_posted: str) -> list[dict]:
        params = {
            "query": f"{query} near Philadelphia PA",
            "page": "1",
            "num_pages": "2",
            "date_posted": date_posted,
            "radius": str(int(self.config.max_commute_miles)),
        }
        try:
            resp = requests.get(
                self._BASE_URL, headers=self._headers, params=params, timeout=20
            )
            resp.raise_for_status()
            jobs = resp.json().get("data", [])
            log.info("Query '%s': %d results", query, len(jobs))
            return jobs
        except requests.HTTPError as exc:
            log.warning("JSearch HTTP error for '%s': %s", query, exc)
        except Exception as exc:
            log.warning("JSearch error for '%s': %s", query, exc)
        return []

    @staticmethod
    def _is_pharma(employer: str) -> bool:
        low = employer.lower()
        return any(name in low for name in PHARMA_COMPANIES)

    # ── Normalisation ─────────────────────────────────────────────────────────

    @staticmethod
    def normalize(raw: dict) -> dict:
        """Convert a raw JSearch job dict into our internal schema."""
        salary = ""
        lo, hi = raw.get("job_min_salary"), raw.get("job_max_salary")
        if lo and hi:
            salary = f"${lo:,.0f} – ${hi:,.0f} / yr"
        elif raw.get("job_salary_period"):
            salary = raw["job_salary_period"]

        # Coordinates may be absent or 0.0 — store None so commute.py knows
        lat = raw.get("job_latitude") or None
        lon = raw.get("job_longitude") or None

        return {
            "id": raw.get("job_id", ""),
            "title": raw.get("job_title", ""),
            "company": raw.get("employer_name", ""),
            "location": f"{raw.get('job_city', '')}, {raw.get('job_state', '')}",
            "lat": lat,
            "lon": lon,
            "description": (raw.get("job_description") or "")[:3000],
            "apply_url": raw.get("job_apply_link", ""),
            "posted_at": raw.get("job_posted_at_datetime_utc", ""),
            "employment_type": raw.get("job_employment_type", ""),
            "salary": salary,
        }
