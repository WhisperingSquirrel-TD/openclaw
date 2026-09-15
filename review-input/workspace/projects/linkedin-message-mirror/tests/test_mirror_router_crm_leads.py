import importlib.util
import sys
import tempfile
from pathlib import Path

SCRIPT = (Path(__file__).resolve().parents[2] / ".." / "scripts" / "mirror_router.py").resolve()
spec = importlib.util.spec_from_file_location("mirror_router", SCRIPT)
module = importlib.util.module_from_spec(spec)
sys.modules["mirror_router"] = module
spec.loader.exec_module(module)  # type: ignore[union-attr]


def test_lead_row_email_and_domain_are_routing_candidates():
    with tempfile.TemporaryDirectory() as tmp:
        crm = Path(tmp) / "crm.md"
        crm.write_text(
            """
# CRM

## Leads

| Company | Domain | ICP | Location | Contact | Title | Email | Campaign | Status | Bounce Date | Reply Date | Notes |
|---------|--------|-----|----------|---------|-------|-------|----------|--------|-------------|------------|-------|
| Humand | humand.co.uk | — | — | Joseph | — | Joseph@humand.co.uk | Direct | Sent | | | AI Opportunity Report sent |
""".strip()
        )
        candidates = module.load_crm_entity_candidates(crm)
    assert ("Humand", ["Humand", "Joseph", "Joseph@humand.co.uk", "humand.co.uk"]) in candidates
    assert module.known_entity_hits("From: Jamie Kennedy <Jamie@humand.co.uk>", candidates) == ["Humand"]


def test_external_reply_from_lead_domain_classifies_as_crm():
    candidates = [("Humand", ["Humand", "Joseph", "Joseph@humand.co.uk", "humand.co.uk"])]
    event = module.MirrorEvent(
        surface="microsoft_external",
        source_type="email",
        source_timestamp="2026-07-06T10:29:00Z",
        direction="inbound",
        sender="Jamie Kennedy <Jamie@humand.co.uk>",
        subject_or_location="RE: Speaking opportunity — Building an Agentic Company",
        body_preview="[Body not shown — external sender]",
        raw_evidence_ref="MICROSOFT_EXTERNAL.md",
    )
    classified = module.classify_mirror_event(event, entity_candidates=candidates)
    assert classified["management_relevance"] == "needs_management"
    assert "CRM" in classified["routing_flags"]
    assert classified["candidate_entities"] == ["Humand"]
