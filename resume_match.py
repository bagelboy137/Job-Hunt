"""Resume-to-job fit scoring via Claude.

Sends jobs to Claude in batches (≤20 per API call) and asks it to score each
one on a 1–10 scale against the provided resume text.  Jobs scoring below
config.min_fit_score are dropped from the email digest.

If ANTHROPIC_API_KEY is absent the module simply returns all jobs unfiltered.
"""
import json
import logging
from typing import Any

import anthropic

log = logging.getLogger(__name__)

BATCH_SIZE = 20

_SYSTEM = (
    "You are a career advisor evaluating pharmaceutical/biotech job postings "
    "against a candidate's resume. Be concise and objective."
)

_USER_TMPL = """\
RESUME:
{resume}

JOBS (JSON array):
{jobs_json}

For EACH job return a fit score 1–10 (10 = perfect match) and a one-sentence reason.
Reply with ONLY valid JSON — no markdown fences, no extra text:
{{
  "scores": [
    {{"job_id": "...", "score": 8, "reason": "Strong match because ..."}}
  ]
}}
"""


class ResumeMatcher:
    def __init__(self, config, resume_text: str):
        self.config = config
        self.resume = resume_text.strip()
        self.client = anthropic.Anthropic(api_key=config.anthropic_api_key)

    # ── Public ────────────────────────────────────────────────────────────────

    def score_and_filter(self, jobs: list[dict]) -> list[dict]:
        """Score every job and return those meeting config.min_fit_score."""
        if not jobs:
            return jobs

        scores: dict[str, dict] = {}
        for i in range(0, len(jobs), BATCH_SIZE):
            batch = jobs[i : i + BATCH_SIZE]
            self._score_batch(batch, scores)

        for job in jobs:
            result = scores.get(job["id"])
            if result:
                job["fit_score"] = result["score"]
                job["fit_reason"] = result["reason"]

        kept = [j for j in jobs if j.get("fit_score", 10) >= self.config.min_fit_score]
        log.info(
            "Resume filter: %d → %d jobs (min score %d/10)",
            len(jobs), len(kept), self.config.min_fit_score,
        )
        return kept

    # ── Private ───────────────────────────────────────────────────────────────

    def _score_batch(self, batch: list[dict], scores: dict[str, dict]) -> None:
        jobs_for_claude = [
            {
                "job_id": j["id"],
                "title": j["title"],
                "company": j["company"],
                # Truncate description to keep token count manageable
                "description": j.get("description", "")[:1500],
            }
            for j in batch
        ]

        prompt = _USER_TMPL.format(
            resume=self.resume[:4000],
            jobs_json=json.dumps(jobs_for_claude, indent=2),
        )

        try:
            msg = self.client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=1024,
                system=_SYSTEM,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = msg.content[0].text.strip()

            # Strip accidental markdown code fences
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]

            result = json.loads(raw)
            for entry in result.get("scores", []):
                scores[entry["job_id"]] = {
                    "score": int(entry.get("score", 0)),
                    "reason": str(entry.get("reason", "")),
                }
        except json.JSONDecodeError as exc:
            log.warning("Claude returned non-JSON response: %s", exc)
        except Exception as exc:
            log.warning("Resume scoring batch failed: %s", exc)
