"""Central configuration for the pharma job alert system.

All secrets are loaded from environment variables (see .env.example).
"""
import os
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Config:
    # ── Home location ────────────────────────────────────────────────────
    home_address: str = "8059 Winston Rd, Philadelphia, PA 19118"
    # Pre-geocoded so we don't hit a geocoding API on every run.
    # Chestnut Hill, Philadelphia — update if address changes.
    home_lat: float = 40.0654
    home_lon: float = -75.2108
    # Straight-line radius that approximates a 1-hour drive from this address.
    max_commute_miles: float = 40.0

    # ── Job search ───────────────────────────────────────────────────────
    # How many days back to search (3-day window is robust against API delays)
    days_back: int = 3
    # Minimum Claude resume-fit score (1–10) a job must have to appear in email
    min_fit_score: int = 6

    # ── API keys ─────────────────────────────────────────────────────────
    # Free tier: 200 req/month — https://rapidapi.com/letscrape-6bRBa3QguO5/api/jsearch
    rapidapi_key: str = field(default_factory=lambda: os.getenv("RAPIDAPI_KEY", ""))
    # Required only for resume matching — https://console.anthropic.com
    anthropic_api_key: str = field(default_factory=lambda: os.getenv("ANTHROPIC_API_KEY", ""))
    # Optional: enables exact driving-time checks near the 40-mile boundary
    google_maps_key: Optional[str] = field(default_factory=lambda: os.getenv("GOOGLE_MAPS_KEY"))

    # ── Gmail SMTP ───────────────────────────────────────────────────────
    email_from: str = field(default_factory=lambda: os.getenv("EMAIL_FROM", ""))
    email_to: str = field(default_factory=lambda: os.getenv("EMAIL_TO", ""))
    # Use a Gmail App Password, NOT your account password.
    # Google Account → Security → 2-Step Verification → App passwords
    gmail_app_password: str = field(default_factory=lambda: os.getenv("GMAIL_APP_PASSWORD", ""))
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587

    # ── Paths ────────────────────────────────────────────────────────────
    # Drop your resume here as resume.pdf (or resume.txt for plain text)
    resume_path: str = field(default_factory=lambda: os.getenv("RESUME_PATH", "resume/resume.pdf"))
    # Tracks job IDs already emailed so you only see each posting once
    seen_jobs_file: str = ".seen_jobs.json"
