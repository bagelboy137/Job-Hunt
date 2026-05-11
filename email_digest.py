"""Build and send the daily HTML email digest via Gmail SMTP."""
import logging
import smtplib
from datetime import date
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

log = logging.getLogger(__name__)

# Score colour bands for the fit indicator
def _score_colour(score: int) -> str:
    if score >= 8:
        return "#2e7d32"   # dark green
    if score >= 6:
        return "#f57f17"   # amber
    return "#c62828"       # red

_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<style>
  body  {{ font-family: Arial, sans-serif; max-width: 780px; margin: 0 auto;
           color: #222; background: #f5f5f5; padding: 16px; }}
  h1   {{ color: #1a3a5c; margin-bottom: 4px; }}
  .sub {{ color: #555; font-size: 14px; margin-bottom: 20px; }}
  .card {{ background: #fff; border-radius: 8px; border: 1px solid #ddd;
           padding: 18px; margin-bottom: 14px; }}
  .title a {{ font-size: 18px; font-weight: bold; color: #1a3a5c;
              text-decoration: none; }}
  .title a:hover {{ text-decoration: underline; }}
  .meta  {{ color: #555; font-size: 13px; margin: 4px 0; }}
  .badge {{ display: inline-block; border-radius: 4px; padding: 2px 8px;
            font-size: 12px; font-weight: bold; color: #fff; margin-right: 6px; }}
  .fit-box {{ margin-top: 10px; padding: 8px 12px; border-radius: 4px;
              background: #f1f8e9; border-left: 4px solid #558b2f; font-size: 13px; }}
  footer {{ color: #999; font-size: 11px; margin-top: 24px; }}
</style>
</head>
<body>
<h1>Pharma Job Alert</h1>
<p class="sub">{date} &mdash; {count} new role{plural} within ~1 hr of Philadelphia, PA</p>
{cards}
<footer>
  Commute radius: 40 miles from 8059 Winston Rd, Philadelphia PA 19118 &bull;
  {resume_note}
</footer>
</body>
</html>
"""

_CARD = """\
<div class="card">
  <div class="title"><a href="{apply_url}">{title}</a></div>
  <div class="meta">
    <strong>{company}</strong> &bull; {location}
    {emp_type_badge}
  </div>
  {salary_row}
  <div class="meta">{commute_info}</div>
  {fit_block}
</div>
"""


class EmailSender:
    def __init__(self, config):
        self.config = config

    def send_daily_digest(self, jobs: list[dict], resume_present: bool = False) -> None:
        today = date.today().strftime("%B %-d, %Y")

        if resume_present:
            resume_note = (
                f"Jobs scored by Claude AI against your uploaded resume "
                f"(min fit score shown: {self.config.min_fit_score}/10)."
            )
        else:
            resume_note = (
                "Drop your resume into resume/resume.pdf to enable AI fit scoring."
            )

        cards_html = "\n".join(self._render_card(j) for j in jobs)

        html_body = _HTML.format(
            date=today,
            count=len(jobs),
            plural="s" if len(jobs) != 1 else "",
            cards=cards_html,
            resume_note=resume_note,
        )

        plain_body = self._plain(jobs, today)

        msg = MIMEMultipart("alternative")
        msg["Subject"] = (
            f"Pharma Job Alert — {len(jobs)} new role{'s' if len(jobs) != 1 else ''} "
            f"— {today}"
        )
        msg["From"] = self.config.email_from
        msg["To"] = self.config.email_to
        msg.attach(MIMEText(plain_body, "plain"))
        msg.attach(MIMEText(html_body, "html"))

        with smtplib.SMTP(self.config.smtp_host, self.config.smtp_port) as server:
            server.starttls()
            server.login(self.config.email_from, self.config.gmail_app_password)
            server.sendmail(self.config.email_from, self.config.email_to, msg.as_string())

        log.info("Email sent to %s (%d jobs)", self.config.email_to, len(jobs))

    # ── Rendering helpers ─────────────────────────────────────────────────────

    def _render_card(self, job: dict) -> str:
        # Employment-type badge
        etype = job.get("employment_type", "")
        emp_type_badge = (
            f'<span class="badge" style="background:#546e7a;">{etype}</span>'
            if etype else ""
        )

        # Salary row
        salary_row = (
            f'<div class="meta">&#128181; {job["salary"]}</div>'
            if job.get("salary") else ""
        )

        # Commute info
        if job.get("commute_minutes"):
            commute_info = f"&#128664; ~{job['commute_minutes']} min drive"
        elif job.get("commute_miles"):
            commute_info = f"&#128205; ~{job['commute_miles']} mi from home"
        else:
            commute_info = ""

        # Fit block (only shown when resume was evaluated)
        fit_block = ""
        if "fit_score" in job:
            score = job["fit_score"]
            colour = _score_colour(score)
            bar_width = max(score * 10, 5)
            fit_block = (
                f'<div class="fit-box">'
                f'<span style="color:{colour};font-weight:bold;">Fit: {score}/10</span>'
                f'&nbsp;<span style="display:inline-block;width:{bar_width}%;height:8px;'
                f'background:{colour};border-radius:4px;vertical-align:middle;"></span>'
                f'<br>{job.get("fit_reason", "")}'
                f"</div>"
            )

        return _CARD.format(
            apply_url=job.get("apply_url") or "#",
            title=job.get("title", "Untitled"),
            company=job.get("company", ""),
            location=job.get("location", ""),
            emp_type_badge=emp_type_badge,
            salary_row=salary_row,
            commute_info=commute_info,
            fit_block=fit_block,
        )

    @staticmethod
    def _plain(jobs: list[dict], date_str: str) -> str:
        lines = [f"Pharma Job Alert — {date_str}", f"{len(jobs)} new roles\n"]
        for j in jobs:
            lines.append(f"{j['title']} | {j['company']} | {j['location']}")
            if j.get("salary"):
                lines.append(f"  Salary: {j['salary']}")
            if j.get("fit_score"):
                lines.append(f"  Fit: {j['fit_score']}/10 — {j.get('fit_reason', '')}")
            lines.append(f"  Apply: {j.get('apply_url', 'N/A')}")
            lines.append("")
        return "\n".join(lines)
