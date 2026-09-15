from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass

from config import Config


@dataclass
class ApiResponse:
    status_code: int
    payload: dict


class BriefingApiClient:
    def __init__(self, config: Config):
        self.config = config
        self.base_url = config.briefing_api_base_url.rstrip("/")

    def _request(self, method: str, path: str, body: dict | None = None) -> ApiResponse:
        url = f"{self.base_url}{path}"
        data = None
        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if body is not None:
            data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                text = resp.read().decode("utf-8")
                payload = json.loads(text) if text else {}
                return ApiResponse(status_code=resp.getcode(), payload=payload)
        except urllib.error.HTTPError as e:
            text = e.read().decode("utf-8")
            try:
                payload = json.loads(text) if text else {}
            except json.JSONDecodeError:
                payload = {"success": False, "error": text or f"HTTP {e.code}"}
            return ApiResponse(status_code=e.code, payload=payload)
        except urllib.error.URLError as e:
            return ApiResponse(status_code=0, payload={"success": False, "error": str(e)})

    def create_briefing(self, company_name: str, website_url: str, source: str | None = None,
                        external_ref: str | None = None, force_regenerate: bool = False) -> ApiResponse:
        body = {
            "company_name": company_name,
            "website_url": website_url,
        }
        if source:
            body["source"] = source
        if external_ref:
            body["external_ref"] = external_ref
        if force_regenerate:
            body["force_regenerate"] = True
        return self._request("POST", "/api/briefings", body)

    def get_briefing(self, job_id: str) -> ApiResponse:
        return self._request("GET", f"/api/briefings/{job_id}")
