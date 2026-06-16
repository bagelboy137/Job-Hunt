"""Job search via the Adzuna API.

Free tier: 1,000 requests/month — sign up at https://developer.adzuna.com/
5 queries × 1 page × 30 days = 150 requests/month (well within free tier).

Strategy: run broad pharma/biotech queries near Philadelphia, deduplicate by
job ID, then keep only results whose company name matches our pharma allow-list.
"""
import hashlib
import logging
import time

import requests

log = logging.getLogger(__name__)

# ── Company allow-list ────────────────────────────────────────────────────────
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
    # CROs & CDMOs (common near Philadelphia)
    "catalent", "charles river", "covance", "icon plc",
    "iqvia", "labcorp", "lonza", "medpace", "parexel",
    "ppd", "pra health", "syneos", "thermo fisher",
    "west pharmaceutical", "wuxi",
    # Biotech in PA / NJ / DE corridor
    "agenus", "ionis", "neurocrine", "seagen",
}

SEARCH_QUERIES = [
    "pharmaceutical scientist",
    "biotech clinical research",
    "drug development regulatory affairs",
    "pharmacovigilance medical affairs",
    "pharmaceutical manufacturing quality",
]

_BASE_URL = "https://api.adzuna.com/v1/api/jobs/us/search/1"


class JobSearcher:
    def __init__(self, config):
        self.config = config

    # ── Public ────────────────────────────────────────────────────────────────

    def search_all(self) -> list[dict]:
        seen: dict[str, dict] = {}

        for query in SEARCH_QUERIES:
            for job in self._search(query):
                jid = job.get("id", "")
                if jid and jid not in seen:
                    seen[jid] = job
            time.sleep(1.0)

        pharma = [j for j in seen.values() if self._is_pharma(j.get("company", ""))]
        log.info("Kept %d/%d jobs matching pharma company list", len(pharma), len(seen))

        if self.config.min_salary:
            before = len(pharma)
            pharma = [j for j in pharma if self._salary_ok(j)]
            log.info("Salary filter ($%s+): %d -> %d jobs", f"{self.config.min_salary:,}", before, len(pharma))

        return pharma

    # ── Private ───────────────────────────────────────────────────────────────

    def _search(self, query: str) -> list[dict]:
        params = {
            "app_id": self.config.adzuna_app_id,
            "app_key": self.config.adzuna_app_key,
            "what": query,
            "where": "Philadelphia, PA",
            "distance": int(self.config.max_commute_miles),
            "max_days_old": self.config.days_back,
            "results_per_page": 50,
            "content-type": "application/json",
        }
        if self.config.min_salary:
            params["salary_min"] = self.config.min_salary
        try:
            resp = requests.get(_BASE_URL, params=params, timeout=20)
            resp.raise_for_status()
            raw_jobs = resp.json().get("results", [])
            log.info("Query '%s': %d results", query, len(raw_jobs))
            return [self._normalize(j) for j in raw_jobs]
        except requests.HTTPError as exc:
            log.warning("Adzuna HTTP error for '%s': %s", query, exc)
        except Exception as exc:
            log.warning("Adzuna error for '%s': %s", query, exc)
        return []

    @staticmethod
    def _is_pharma(company: str) -> bool:
        low = company.lower()
        return any(name in low for name in PHARMA_COMPANIES)

    def _salary_ok(self, job: dict) -> bool:
        # If no salary is listed we can't rule it out — include it
        sal_max = job.get("_raw_salary_max")
        if sal_max is None:
            return True
        return sal_max >= self.config.min_salary

    @staticmethod
    def _normalize(raw: dict) -> dict:
        salary = ""
        lo = raw.get("salary_min")
        hi = raw.get("salary_max")
        if lo and hi and lo != hi:
            salary = f"${lo:,.0f} – ${hi:,.0f} / yr"
        elif hi:
            salary = f"Up to ${hi:,.0f} / yr"

        loc = raw.get("location", {})
        area = loc.get("display_name", "")

        # Adzuna doesn't always include lat/lon — store None if missing
        lat = raw.get("latitude") or None
        lon = raw.get("longitude") or None

        return {
            "id": raw.get("id", ""),
            "title": raw.get("title", ""),
            "company": raw.get("company", {}).get("display_name", ""),
            "location": area,
            "lat": lat,
            "lon": lon,
            "description": (raw.get("description") or "")[:3000],
            "apply_url": raw.get("redirect_url", ""),
            "posted_at": raw.get("created", ""),
            "employment_type": raw.get("contract_time", ""),
            "salary": salary,
            # Raw value kept for salary floor filtering; not shown in email
            "_raw_salary_max": hi,
        }
