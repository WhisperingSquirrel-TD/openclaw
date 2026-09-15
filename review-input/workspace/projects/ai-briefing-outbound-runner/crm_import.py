from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

CRM_PATH = Path.home() / ".openclaw" / "workspace" / "stackstone" / "crm.md"
SENT_EMAILS_PATH = Path.home() / ".openclaw" / "workspace" / "stackstone" / "sent-emails.md"

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


@dataclass
class CrmLead:
    crm_id: str
    company_name: str
    website_url: str
    contact_name: str | None
    contact_email: str
    campaign_segment: str | None
    status: str


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def _extract_sent_emails() -> set[str]:
    if not SENT_EMAILS_PATH.exists():
        return set()
    text = SENT_EMAILS_PATH.read_text(encoding="utf-8")
    return {m.group(0).lower() for m in EMAIL_RE.finditer(text)}


def _normalise_website(domain_or_url: str) -> str:
    value = (domain_or_url or "").strip()
    if not value:
        return ""
    if value.startswith("http://") or value.startswith("https://"):
        return value
    return f"https://{value}"


def load_leads() -> list[CrmLead]:
    text = CRM_PATH.read_text(encoding="utf-8")
    start = text.index("## Leads")
    tail = text[start:]
    lines = tail.splitlines()

    rows: list[CrmLead] = []
    data_started = False
    row_num = 0
    for line in lines:
        if not line.startswith("|"):
            if data_started and line.strip().startswith("---"):
                break
            continue
        parts = [p.strip() for p in line.strip().strip("|").split("|")]
        if len(parts) < 9:
            continue
        if parts[0] == "Company" or set(parts[0]) == {"-"}:
            data_started = True
            continue
        data_started = True
        company, domain, _icp, _location, contact, _title, email, campaign, status = parts[:9]
        email = email.strip()
        if not email or not EMAIL_RE.fullmatch(email):
            continue
        row_num += 1
        crm_id = f"lead-{_slug(company)}-{row_num}"
        rows.append(
            CrmLead(
                crm_id=crm_id,
                company_name=company,
                website_url=_normalise_website(domain),
                contact_name=None if contact in ("", "—") else contact,
                contact_email=email,
                campaign_segment=None if campaign in ("", "—") else campaign,
                status=status,
            )
        )
    return rows


def eligible_leads(limit: int = 20) -> list[CrmLead]:
    sent = _extract_sent_emails()
    allowed_statuses = {"New"}
    results: list[CrmLead] = []
    for lead in load_leads():
        if lead.status not in allowed_statuses:
            continue
        if not lead.website_url:
            continue
        if lead.contact_email.lower() in sent:
            continue
        results.append(lead)
        if len(results) >= limit:
            break
    return results
