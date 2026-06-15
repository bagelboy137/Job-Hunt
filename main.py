#!/usr/bin/env python3
"""
Pharma Job Alert — daily runner
================================
Searches major pharma/biotech companies for openings within a 1-hour commute
of 8059 Winston Rd, Philadelphia PA 19118, optionally scores them against your
resume, and emails an HTML digest.

Quick start:
  cp .env.example .env && nano .env   # fill in your API keys
  pip install -r requirements.txt
  python main.py                      # run once to verify

Daily automation (8 AM):
  0 8 * * * /path/to/venv/bin/python /home/user/Job-Hunt/main.py
  (see run_daily.sh for a ready-to-use cron wrapper)
"""
import json
import logging
import sys
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from config import Config
from commute import CommuteFilter
from email_digest import EmailSender
from job_search import JobSearcher
from resume_match import ResumeMatcher

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("pharma_alerts.log"),
    ],
)
log = logging.getLogger(__name__)


# ── State helpers ─────────────────────────────────────────────────────────────

def load_seen(path: str) -> set[str]:
    try:
        return set(json.loads(Path(path).read_text()))
    except FileNotFoundError:
        return set()


def save_seen(path: str, seen: set[str]) -> None:
    Path(path).write_text(json.dumps(sorted(seen), indent=2))


# ── Resume loading ────────────────────────────────────────────────────────────

def load_resume(path: str) -> str | None:
    p = Path(path)
    if not p.exists():
        log.info("No resume found at '%s' — skipping fit scoring", path)
        return None

    suffix = p.suffix.lower()
    if suffix == ".pdf":
        try:
            import pdfplumber
        except ImportError:
            log.warning(
                "pdfplumber is not installed; cannot read PDF resume.\n"
                "  pip install pdfplumber\n"
                "  Or save your resume as a .txt file instead."
            )
            return None
        with pdfplumber.open(p) as pdf:
            text = "\n".join(page.extract_text() or "" for page in pdf.pages)
        log.info("Resume loaded from '%s' (%d chars)", path, len(text))
        return text or None

    if suffix in {".txt", ".md", ""}:
        text = p.read_text(encoding="utf-8")
        log.info("Resume loaded from '%s' (%d chars)", path, len(text))
        return text or None

    log.warning("Unsupported resume format '%s'; use .pdf or .txt", suffix)
    return None


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    config = Config()

    # Validate required secrets before doing any network work
    required = {
        "ADZUNA_APP_ID": config.adzuna_app_id,
        "ADZUNA_APP_KEY": config.adzuna_app_key,
        "EMAIL_FROM": config.email_from,
        "EMAIL_TO": config.email_to,
        "GMAIL_APP_PASSWORD": config.gmail_app_password,
    }
    missing = [k for k, v in required.items() if not v]
    if missing:
        log.error("Missing required environment variables: %s", ", ".join(missing))
        log.error("Copy .env.example to .env and fill in your credentials.")
        sys.exit(1)

    log.info("=== Pharma Job Alert — %s ===", date.today())

    seen = load_seen(config.seen_jobs_file)
    resume_text = load_resume(config.resume_path)

    # 1. Search ---------------------------------------------------------------
    jobs = JobSearcher(config).search_all()
    log.info("Total pharma jobs found: %d", len(jobs))

    # 2. Deduplicate against previously-seen postings -------------------------
    new_jobs = [j for j in jobs if j["id"] not in seen]
    log.info("New (unseen) jobs: %d", len(new_jobs))

    # 3. Commute filter -------------------------------------------------------
    reachable = CommuteFilter(config).filter(new_jobs)
    log.info("Within commute distance: %d", len(reachable))

    # 4. Resume-fit scoring (only if resume + Anthropic key are present) ------
    resume_used = False
    if resume_text and config.anthropic_api_key and reachable:
        matcher = ResumeMatcher(config, resume_text)
        reachable = matcher.score_and_filter(reachable)
        # Sort best-fit first
        reachable.sort(key=lambda j: j.get("fit_score", 0), reverse=True)
        resume_used = True
    elif resume_text and not config.anthropic_api_key:
        log.info("ANTHROPIC_API_KEY not set — skipping resume scoring")

    # 5. Mark all new jobs as seen (regardless of commute/score result) -------
    for j in new_jobs:
        seen.add(j["id"])
    save_seen(config.seen_jobs_file, seen)

    # 6. Email digest ---------------------------------------------------------
    if reachable:
        EmailSender(config).send_daily_digest(reachable, resume_present=resume_used)
        log.info("Digest sent with %d jobs", len(reachable))
    else:
        log.info("No new reachable jobs today — skipping email")

    log.info("Done.")


if __name__ == "__main__":
    main()
