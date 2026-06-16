"""Central configuration for the pharma job alert system.

All secrets are loaded from environment variables (see .env.example).
"""
import os
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Config:
    # Home location (pre-geocoded — update if address changes)
    home_address: str = "8059 Winston Rd, Philadelphia, PA 19118"
    home_lat: float = 40.0654
    home_lon: float = -75.2108
    max_commute_miles: float = 40.0

    # Job search settings
    days_back: int = 3
    min_fit_score: int = 6
    min_salary: int = 100000

    # Adzuna API — free tier 1,000 req/month: https://developer.adzuna.com/
    adzuna_app_id: str = field(default_factory=lambda: os.getenv("ADZUNA_APP_ID", ""))
    adzuna_app_key: str = field(default_factory=lambda: os.getenv("ADZUNA_APP_KEY", ""))

    # Anthropic API — required only for resume matching
    anthropic_api_key: str = field(default_factory=lambda: os.getenv("ANTHROPIC_API_KEY", ""))

    # Google Maps — optional, enables exact driving-time checks
    google_maps_key: Optional[str] = field(default_factory=lambda: os.getenv("GOOGLE_MAPS_KEY"))

    # Gmail SMTP — use an App Password, not your regular Gmail password
    email_from: str = field(default_factory=lambda: os.getenv("EMAIL_FROM", ""))
    email_to: str = field(default_factory=lambda: os.getenv("EMAIL_TO", ""))
    gmail_app_password: str = field(default_factory=lambda: os.getenv("GMAIL_APP_PASSWORD", ""))
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587

    # Paths
    resume_path: str = field(default_factory=lambda: os.getenv("RESUME_PATH", "resume/resume.pdf"))
    seen_jobs_file: str = ".seen_jobs.json"
