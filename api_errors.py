"""Turn httpx API failures into short user-facing messages."""

from __future__ import annotations

import httpx


def api_error_message(err: Exception) -> str:
    if isinstance(err, httpx.HTTPStatusError):
        code = err.response.status_code
        detail = ""
        try:
            payload = err.response.json()
            if isinstance(payload, dict):
                detail = str(payload.get("detail") or "")
        except Exception:
            detail = (err.response.text or "")[:240]
        if code == 401:
            return detail or "Session expired — sign out from Profile and sign in again."
        if code in (502, 503, 504):
            return (
                f"The API returned {code} (server busy or waking up). "
                "Wait ~60 seconds and reload the page."
            )
        if detail:
            return f"API error {code}: {detail}"
        return f"API error {code}."
    if isinstance(err, httpx.TimeoutException):
        return "The recipe list took too long. Wait a moment and try again."
    if isinstance(err, httpx.RequestError):
        return f"Could not reach the API: {err}"
    return str(err)
