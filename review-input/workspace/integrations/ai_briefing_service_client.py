from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

DEFAULT_BASE_URL = "http://127.0.0.1:8766"


@dataclass
class ServiceResponse:
    status_code: int
    payload: dict[str, Any]


class AIBriefingServiceClient:
    def __init__(self, base_url: str = DEFAULT_BASE_URL, timeout: int = 30):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _request(self, method: str, path: str, body: dict[str, Any] | None = None) -> ServiceResponse:
        url = f"{self.base_url}{path}"
        data = None
        headers = {"Accept": "application/json"}
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = Request(url, data=data, headers=headers, method=method)
        with urlopen(req, timeout=self.timeout) as resp:
            raw = resp.read().decode("utf-8")
            payload = json.loads(raw) if raw else {}
            return ServiceResponse(status_code=resp.getcode(), payload=payload)

    def health(self) -> ServiceResponse:
        return self._request("GET", "/health")

    def list_runs(self) -> ServiceResponse:
        return self._request("GET", "/runs")

    def run_summary(self, run_id: int) -> ServiceResponse:
        return self._request("GET", f"/runs/{run_id}/summary")

    def create_run(self, name: str, mode: str = "generate_only", notes: str | None = None) -> ServiceResponse:
        return self._request("POST", "/runs/create", {"name": name, "mode": mode, "notes": notes})

    def mark_run_for_prepare(self, run_id: int) -> ServiceResponse:
        return self._request("POST", "/runs/mark-for-prepare", {"run_id": run_id})

    def watch_run(self, run_id: int) -> ServiceResponse:
        return self._request("POST", "/runs/watch", {"run_id": run_id})

    def preview_crm_targets(self, limit: int | None = None) -> ServiceResponse:
        qs = ""
        if limit is not None:
            qs = "?" + urlencode({"limit": limit})
        return self._request("GET", f"/crm/preview{qs}")

    def import_crm_targets(self, limit: int | None = None, force_regenerate: bool = False, run_id: int | None = None, post_generation_action: str = "generate_only") -> ServiceResponse:
        body = {"force_regenerate": force_regenerate, "post_generation_action": post_generation_action}
        if limit is not None:
            body["limit"] = limit
        if run_id is not None:
            body["run_id"] = run_id
        return self._request("POST", "/crm/import", body)

    def add_target(self, crm_id: str, company_name: str, website_url: str, contact_email: str, contact_name: str | None = None, campaign_segment: str | None = None, force_regenerate: bool = False, run_id: int | None = None, post_generation_action: str = "generate_only") -> ServiceResponse:
        return self._request(
            "POST",
            "/targets/add",
            {
                "crm_id": crm_id,
                "company_name": company_name,
                "website_url": website_url,
                "contact_email": contact_email,
                "contact_name": contact_name,
                "campaign_segment": campaign_segment,
                "force_regenerate": force_regenerate,
                "run_id": run_id,
                "post_generation_action": post_generation_action,
            },
        )

    def list_briefings(self, run_id: int | None = None) -> ServiceResponse:
        qs = ""
        if run_id is not None:
            qs = "?" + urlencode({"run_id": run_id})
        return self._request("GET", f"/briefings{qs}")

    def submit_briefings(self, run_id: int | None = None) -> ServiceResponse:
        body = {}
        if run_id is not None:
            body["run_id"] = run_id
        return self._request("POST", "/briefings/submit", body)

    def poll_briefings(self, once: bool = True, run_id: int | None = None, until_run_complete: bool = False) -> ServiceResponse:
        body: dict[str, Any] = {"once": once, "until_run_complete": until_run_complete}
        if run_id is not None:
            body["run_id"] = run_id
        return self._request("POST", "/briefings/poll", body)

    def list_send_packs(self) -> ServiceResponse:
        return self._request("GET", "/send-packs")

    def send_pack_review_card(self, send_pack_id: int) -> ServiceResponse:
        return self._request("GET", f"/send-packs/{send_pack_id}/review-card")

    def build_send_packs(self, run_id: int | None = None, include_generate_only: bool = False) -> ServiceResponse:
        body = {"include_generate_only": include_generate_only}
        if run_id is not None:
            body["run_id"] = run_id
        return self._request("POST", "/send-packs/build", body)

    def validate_send_pack(self, send_pack_id: int) -> ServiceResponse:
        return self._request("POST", "/send-packs/validate", {"send_pack_id": send_pack_id})

    def verify_outbound(self, send_pack_id: int) -> ServiceResponse:
        return self._request("POST", "/outbound/verify", {"send_pack_id": send_pack_id})

    def approve_send_pack(self, send_pack_id: int) -> ServiceResponse:
        return self._request("POST", "/send-packs/approve", {"send_pack_id": send_pack_id})

    def list_outbound(self) -> ServiceResponse:
        return self._request("GET", "/outbound")

    def schedule_send(self, send_pack_id: int, scheduled_send_at: str) -> ServiceResponse:
        return self._request("POST", "/outbound/schedule", {"send_pack_id": send_pack_id, "scheduled_send_at": scheduled_send_at})

    def run_send_queue(self, execute: bool = False, limit: int = 10) -> ServiceResponse:
        return self._request("POST", "/outbound/run", {"execute": execute, "limit": limit})
