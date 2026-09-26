"""The one HTTP call every local backend makes."""

from __future__ import annotations

import json
import urllib.request
from typing import Optional


def post(url: str, payload: dict, timeout: float,
          headers: Optional[dict] = None) -> dict:
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url, data=body, method="POST",
        headers={"content-type": "application/json", **(headers or {})})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))
