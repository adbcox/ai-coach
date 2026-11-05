"""Minimal client for Garmin's Personal API.

Endpoint paths follow Garmin's published client
(https://github.com/garmin/connect-personal-api-python, Apache-2.0) and the
Personal API docs. Written from scratch; no code copied.

Response shapes for the activity search are NOT verified against a live
account yet; callers must read fields defensively.
"""

from __future__ import annotations

import base64
import json
import time
from collections.abc import Callable
from typing import Any

import httpx

TOKEN_PATH = "/personalapitoken-service/personal-api/personal-api-key/token"
SEARCH_PATH = "/activitylist-service/activities/search/activities"
DOWNLOAD_PATH = "/download-service/files/activity/{id}"
_REFRESH_WINDOW_S = 3600  # refresh a token that expires within the hour


class GarminError(Exception):
    """kind: auth | http | network | bad_response"""

    def __init__(self, kind: str, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.kind = kind
        self.status = status


def jwt_expiry(token: str) -> float:
    try:
        payload = token.split(".")[1]
        data = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        return float(data["exp"])
    except (IndexError, KeyError, TypeError, ValueError) as exc:
        raise GarminError("bad_response", "Token endpoint did not return a valid JWT.") from exc


class GarminClient:
    def __init__(
        self,
        api_key: str,
        base_url: str,
        *,
        transport: httpx.BaseTransport | None = None,
        timeout: float = 30.0,
        clock: Callable[[], float] = time.time,
        sleep: Callable[[float], None] = time.sleep,
        retry_delay: float = 5.0,
        raise_on_rate_limit: bool = False,
    ) -> None:
        self._api_key = api_key.strip()
        if not self._api_key:
            raise GarminError("auth", "No API key provided.")
        self._base = base_url.rstrip("/")
        self._http = httpx.Client(transport=transport, timeout=timeout)
        self._clock = clock
        self._sleep = sleep
        self._retry_delay = retry_delay
        # When true (used for backfill), a 429 raises immediately instead of
        # retrying in a loop — the throttle layer owns the pause.
        self._raise_on_rate_limit = raise_on_rate_limit
        self._token: str | None = None
        self._expires = 0.0

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> GarminClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def __repr__(self) -> str:  # never include the key
        return f"GarminClient(base_url={self._base!r})"

    def ensure_token(self, *, force: bool = False) -> None:
        if not force and self._token and self._expires - self._clock() > _REFRESH_WINDOW_S:
            return
        try:
            resp = self._http.post(
                self._base + TOKEN_PATH,
                headers={"Accept": "*/*", "Authorization": f"ApiKey {self._api_key}"},
            )
        except httpx.HTTPError as exc:
            raise GarminError("network", f"Could not reach Garmin: {type(exc).__name__}") from exc
        if resp.status_code in (401, 403):
            raise GarminError("auth", "Garmin rejected the API key (wrong, deleted or expired).")
        if resp.status_code != 200:
            raise GarminError("http", f"Token exchange failed (HTTP {resp.status_code}).")
        token = resp.text.strip()
        self._expires = jwt_expiry(token)
        self._token = token

    def _get(
        self, path: str, *, params: dict[str, Any] | None = None, accept: str
    ) -> httpx.Response:
        refreshed = False
        rate_waits = 0
        while True:
            self.ensure_token()
            try:
                resp = self._http.get(
                    self._base + path,
                    params=params,
                    headers={"Accept": accept, "Authorization": f"Bearer {self._token}"},
                )
            except httpx.HTTPError as exc:
                raise GarminError("network", f"Could not reach Garmin: {type(exc).__name__}") from exc
            if resp.status_code == 401 and not refreshed:
                refreshed = True  # token may have been revoked/expired early: refresh once
                self.ensure_token(force=True)
                continue
            if resp.status_code == 429:
                if self._raise_on_rate_limit:
                    raise GarminError("http", "Garmin returned HTTP 429 (rate limited).", 429)
                if rate_waits < 4:
                    rate_waits += 1  # rate limited: back off and retry
                    self._sleep(self._retry_delay * rate_waits)
                    continue
            if resp.status_code in (401, 403):
                raise GarminError("auth", "Garmin refused access (key expired or revoked?).", resp.status_code)
            if resp.status_code >= 400:
                raise GarminError("http", f"Garmin returned HTTP {resp.status_code} for {path}.", resp.status_code)
            return resp

    def get_json(self, path: str, params: dict[str, Any] | None = None) -> Any:
        """GET any Personal API path and return decoded JSON (None if empty)."""
        resp = self._get(path, params=params, accept="application/json")
        if not resp.content:
            return None
        try:
            return resp.json()
        except ValueError as exc:
            raise GarminError("bad_response", f"Not valid JSON from {path}.") from exc

    def search_activities(
        self, *, start: int = 0, limit: int = 50, start_date: str | None = None,
        end_date: str | None = None,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"start": start, "limit": limit}
        if start_date:
            params["startDate"] = start_date
        if end_date:
            params["endDate"] = end_date
        resp = self._get(SEARCH_PATH, params=params, accept="application/json")
        if not resp.content:
            return []
        try:
            data = resp.json()
        except ValueError as exc:
            raise GarminError("bad_response", "Activity list was not valid JSON.") from exc
        if isinstance(data, dict):
            data = data.get("activities") or data.get("data") or []
        if not isinstance(data, list):
            raise GarminError("bad_response", "Unexpected activity list shape.")
        return [item for item in data if isinstance(item, dict)]

    def download_activity(self, activity_id: str) -> bytes:
        if not activity_id.isascii() or not activity_id.isdecimal() or int(activity_id) <= 0:
            raise GarminError("bad_response", "Invalid activity id.")
        resp = self._get(
            DOWNLOAD_PATH.format(id=activity_id),
            accept="application/zip, application/x-zip-compressed, application/octet-stream",
        )
        if not resp.content:
            raise GarminError("bad_response", "Empty activity file.")
        return resp.content
